#!/usr/bin/env python3
"""Mine Claude Code session transcripts for friction signals.

Emits a clustered, evidence-bearing JSON report to stdout. Every observation
carries verbatim excerpts so the proposing agent argues from what actually
happened rather than from what it imagines happens.
"""

import json
import re
import sys
import hashlib
import collections
from pathlib import Path
from datetime import datetime, timedelta, timezone

PROJECTS = Path.home() / ".claude" / "projects"

# Phrases that mark a user correcting or redirecting the agent. Deliberately
# narrow: precision matters more than recall, since each hit becomes evidence.
CORRECTION_PATTERNS = [
    r"\bno[,.]? (?:actually|that's|thats|it's|its|don't|dont|stop)\b",
    r"\bthat'?s (?:wrong|not right|not what|incorrect)\b",
    r"\bi (?:said|asked|told you)\b",
    r"\b(?:stop|undo|revert|rollback) (?:that|it|this)\b",
    r"\bwhy did you\b",
    r"\bdon'?t do that\b",
    r"\byou (?:broke|missed|forgot|ignored)\b",
    r"\bnot what i (?:wanted|asked)\b",
]
CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.I)

# Volatile substrings stripped before hashing so the same failure across
# different files/ids collapses into one cluster.
NOISE = [
    (re.compile(r"/[\w./~-]+"), "<path>"),
    (re.compile(r"\b[0-9a-f]{8,}\b", re.I), "<hash>"),
    (re.compile(r"\b\d+\b"), "<n>"),
    (re.compile(r"'[^']{1,80}'"), "'<v>'"),
    (re.compile(r'"[^"]{1,80}"'), '"<v>"'),
]


# Secrets, redacted before anything leaves this file.
#
# The loop quotes transcripts verbatim into CHANGELOG.md and commits it, which
# is exactly right for friction and exactly wrong for a key. Session transcripts
# are 51 MB of everything ever typed here, and on 2026-08-03 a live HMAC secret
# was pasted into one nine hours before the nightly cycle.
#
# Redaction happens in `redact`, which every verbatim path calls — not at the
# point of printing. A rule applied at the last step is a rule that misses the
# next output format someone adds.
SECRETS = [
    (re.compile(r"\b[a-f0-9]{64}\b"), "<sha256-or-secret>"),
    (re.compile(r"\b[a-f0-9]{40}\b"), "<sha1-or-secret>"),
    (re.compile(r"\btskey-[A-Za-z0-9-]+"), "<tailscale-key>"),
    (re.compile(r"\b(?:sk|ghp|gho|github_pat|xox[baprs])-[A-Za-z0-9_-]{10,}"),
     "<api-token>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<aws-key>"),
    # NODE_SECRETS=id:secret, and the header that carries the signature.
    (re.compile(r"(NODE_SECRETS\s*=\s*)\S+"), r"\1<redacted>"),
    (re.compile(r"(x-node-signature\s*:\s*)\S+", re.I), r"\1<redacted>"),
    (re.compile(r"(-hmac\s+)\S+"), r"\1<redacted>"),
    # Twelve lowercase words in a row is a BIP39 mnemonic far more often than
    # it is a sentence — English prose that long without punctuation is rare.
    (re.compile(r"\b(?:[a-z]{3,8} ){11}[a-z]{3,8}\b"), "<mnemonic>"),
    (re.compile(r"\blogin\.tailscale\.com/a/\S+"), "login.tailscale.com/a/<auth>"),
]


def redact(text: str) -> str:
    """Strip anything that looks like a credential. Over-redacts on purpose.

    A false positive costs the proposing agent one blurred excerpt. A false
    negative commits a live key to a git repository and pushes it.
    """
    for pat, repl in SECRETS:
        text = pat.sub(repl, text)
    return text


def normalize(text: str) -> str:
    t = redact(text.strip())[:400]
    for pat, repl in NOISE:
        t = pat.sub(repl, t)
    return re.sub(r"\s+", " ", t).strip()


def sig(text: str) -> str:
    return hashlib.sha1(normalize(text).encode()).hexdigest()[:10]


def as_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                elif b.get("type") == "tool_result":
                    c = b.get("content")
                    parts.append(c if isinstance(c, str) else json.dumps(c))
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts)
    if isinstance(content, dict):
        return json.dumps(content)
    return str(content)


def parse_ts(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def scan(since_days: int):
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    def new_entry():
        return {
            "count": 0,
            "tools": collections.Counter(),
            "samples": [],
            "projects": set(),
            "sessions": set(),
        }

    tool_errors = collections.defaultdict(new_entry)
    corrections = []
    tool_usage = collections.Counter()
    denials = collections.defaultdict(new_entry)
    sessions = 0
    files_scanned = 0

    for path in sorted(PROJECTS.glob("*/*.jsonl")):
        project = path.parent.name
        session_id = path.stem
        files_scanned += 1
        # tool_use id -> name, so an error result can be attributed to its tool
        id_to_tool = {}
        touched = False

        try:
            fh = path.open(errors="replace")
        except OSError:
            continue

        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = parse_ts(rec.get("timestamp"))
                if ts and ts < cutoff:
                    continue
                touched = True

                msg = rec.get("message") or {}
                content = msg.get("content")

                if rec.get("type") == "assistant" and isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            name = b.get("name", "?")
                            tool_usage[name] += 1
                            if b.get("id"):
                                id_to_tool[b["id"]] = name

                if rec.get("type") == "user":
                    if isinstance(content, list):
                        for b in content:
                            if not isinstance(b, dict) or b.get("type") != "tool_result":
                                continue
                            if not b.get("is_error"):
                                continue
                            raw = b.get("content")
                            text = raw if isinstance(raw, str) else json.dumps(raw)
                            tool = id_to_tool.get(b.get("tool_use_id"), "unknown")

                            # Permission denials are a distinct, actionable class.
                            bucket = denials if re.search(
                                r"permission|denied|not allowed|rejected by user|user doesn't want",
                                text, re.I,
                            ) else tool_errors
                            entry = bucket[sig(text)]
                            entry["count"] += 1
                            entry["projects"].add(project)
                            entry["sessions"].add(session_id)
                            if bucket is tool_errors:
                                entry["tools"][tool] += 1
                            if len(entry["samples"]) < 3:
                                entry["samples"].append(
                                    {"tool": tool, "text": redact(text.strip())[:300]}
                                )

                    # Real typed user turns only: skip synthetic/tool-result users.
                    text = as_text(content)
                    if text and not (isinstance(content, list) and any(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content
                    )):
                        snippet = text.strip()
                        if 0 < len(snippet) < 2000 and CORRECTION_RE.search(snippet):
                            corrections.append({
                                "project": project,
                                "timestamp": rec.get("timestamp"),
                                "text": snippet[:400],
                            })

        if touched:
            sessions += 1

    def pack(bucket, min_count):
        """Rank by how many *distinct sessions* a signature appears in, not raw
        count. Five failures in one conversation is one recurring moment; the
        same failure in two sessions is a property of the tool. Ranking on raw
        count made single-session noise read as a strong pattern."""
        out = []
        for k, v in bucket.items():
            if v["count"] < min_count:
                continue
            item = {
                "signature": k,
                "count": v["count"],
                "distinct_sessions": len(v["sessions"]),
                "distinct_projects": len(v["projects"]),
                "single_session_only": len(v["sessions"]) <= 1,
                "projects": sorted(v["projects"]),
                "samples": v["samples"],
            }
            if v.get("tools"):
                item["tools"] = dict(v["tools"])
            out.append(item)
        return sorted(out, key=lambda x: (-x["distinct_sessions"], -x["count"]))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": since_days,
        "sessions_scanned": sessions,
        "files_scanned": files_scanned,
        "tool_usage": dict(tool_usage.most_common(25)),
        # min_count=1: a single hard failure is still a real, citable event.
        "recurring_tool_errors": pack(tool_errors, 1),
        "permission_denials": pack(denials, 1),
        "user_corrections": corrections[:25],
    }


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    print(json.dumps(scan(days), indent=2))
