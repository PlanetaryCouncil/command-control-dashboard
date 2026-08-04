#!/usr/bin/env python3
"""Who is knocking on the funnel.

  visitors.py --summary [hours]      print the aggregate for the last n hours
  visitors.py --tail [n]             print the last n raw hits

The fleet is public on purpose — the funnel forwards the world to :8787 — but
until now every visit vanished unrecorded. This module is the guest book:
`record()` is called from the server's log hook for every request that arrived
through the funnel (X-Forwarded-For present), appends one JSONL row to
logs/access.jsonl, and keeps workers/visitors.json fresh so the board and the
council see traffic the same way they see any other worker.

Local requests are never recorded: the browser tab polls workers.json every
6 seconds and a guest book full of the host walking past is not a guest book.

Levels of identity, best-effort by User-Agent substring: AI crawlers and
assistants ("ai"), search engines ("search"), SEO harvesters ("seo"),
scanners and script tools ("scanner"), human browsers ("browser"), the rest
("unknown"). First match wins, so bot names are checked before "Mozilla" —
nearly every bot wears a Mozilla/5.0 prefix.
"""

import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
LOG = FLEET / "logs" / "access.jsonl"
SEEN = FLEET / "logs" / ".visitors-seen.json"
WORKER = FLEET / "workers" / "visitors.json"
MAX_BYTES = 4_000_000          # same contract as events.jsonl: rotate, not grow

# (substring, name, kind) — order matters, first match wins.
KNOWN = (
    # AI crawlers and assistants
    ("gptbot", "GPTBot", "ai"),
    ("oai-searchbot", "OAI-SearchBot", "ai"),
    ("chatgpt-user", "ChatGPT-User", "ai"),
    ("claudebot", "ClaudeBot", "ai"),
    ("claude-user", "Claude-User", "ai"),
    ("claude-searchbot", "Claude-SearchBot", "ai"),
    ("claude-web", "Claude-Web", "ai"),
    ("anthropic-ai", "anthropic-ai", "ai"),
    ("perplexity-user", "Perplexity-User", "ai"),
    ("perplexitybot", "PerplexityBot", "ai"),
    ("google-extended", "Google-Extended", "ai"),
    ("applebot-extended", "Applebot-Extended", "ai"),
    ("bytespider", "Bytespider", "ai"),
    ("ccbot", "CCBot", "ai"),
    ("meta-externalagent", "Meta-External", "ai"),
    ("facebookbot", "FacebookBot", "ai"),
    ("cohere-ai", "cohere-ai", "ai"),
    ("mistralai", "MistralAI", "ai"),
    ("duckassistbot", "DuckAssistBot", "ai"),
    # Search engines
    ("googlebot", "Googlebot", "search"),
    ("googleother", "GoogleOther", "search"),
    ("bingbot", "bingbot", "search"),
    ("duckduckbot", "DuckDuckBot", "search"),
    ("yandex", "Yandex", "search"),
    ("applebot", "Applebot", "search"),
    ("baiduspider", "Baiduspider", "search"),
    ("amazonbot", "Amazonbot", "search"),
    # SEO / link harvesters
    ("ahrefsbot", "AhrefsBot", "seo"),
    ("semrushbot", "SemrushBot", "seo"),
    ("mj12bot", "MJ12bot", "seo"),
    ("dotbot", "DotBot", "seo"),
    ("dataforseobot", "DataForSeoBot", "seo"),
    ("petalbot", "PetalBot", "seo"),
    # Scanners and script tools
    ("zgrab", "zgrab", "scanner"),
    ("masscan", "masscan", "scanner"),
    ("nmap", "nmap", "scanner"),
    ("nuclei", "nuclei", "scanner"),
    ("censys", "Censys", "scanner"),
    ("expanse", "Expanse", "scanner"),
    ("internetmeasurement", "InternetMeasurement", "scanner"),
    ("odinscanner", "Odin", "scanner"),
    ("curl/", "curl", "scanner"),
    ("wget/", "wget", "scanner"),
    ("python-requests", "python-requests", "scanner"),
    ("python-httpx", "python-httpx", "scanner"),
    ("aiohttp", "aiohttp", "scanner"),
    ("go-http-client", "Go-http-client", "scanner"),
    ("scrapy", "Scrapy", "scanner"),
    ("okhttp", "okhttp", "scanner"),
    ("libwww", "libwww", "scanner"),
)

_lock = threading.Lock()
_last_worker_write = 0.0


def classify(ua):
    """(name, kind) for a User-Agent string, best effort."""
    low = (ua or "").lower()
    if not low:
        return "no-agent", "unknown"
    for needle, name, kind in KNOWN:
        if needle in low:
            return name, kind
    if "bot" in low or "crawler" in low or "spider" in low:
        return (ua or "")[:40], "unknown"
    if "mozilla/" in low:
        return "browser", "browser"
    return (ua or "")[:40], "unknown"


def record(method, path, status, ip, ua):
    """Append one funnelled request and keep the worker file fresh.

    Called from the server's log hook on every remote request; must stay
    cheap. The worker file is recomputed at most once a minute.
    """
    global _last_worker_write
    name, kind = classify(ua)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ip": str(ip or "")[:60],
        "method": str(method)[:8],
        "path": str(path)[:200],
        "status": int(status),
        "name": name,
        "kind": kind,
        "ua": str(ua or "")[:200],
    }
    with _lock:
        try:
            if LOG.exists() and LOG.stat().st_size > MAX_BYTES:
                LOG.rename(LOG.with_suffix(".jsonl.1"))
            with LOG.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            return rec
        _announce_first_sighting(name, kind)
        now = time.time()
        if now - _last_worker_write > 60:
            _last_worker_write = now
            try:
                write_worker()
            except OSError:
                pass
    return rec


def _announce_first_sighting(name, kind):
    """One event per newly-seen crawler name, so the stream shows arrivals."""
    if kind in ("browser", "unknown"):
        return
    try:
        seen = set(json.loads(SEEN.read_text()))
    except (OSError, ValueError):
        seen = set()
    if name in seen:
        return
    seen.add(name)
    try:
        SEEN.write_text(json.dumps(sorted(seen)))
    except OSError:
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import events as ev
    ev.emit("visitors", "info", f"[visitors] first sighting: {name} ({kind})")


def hits(hours=24):
    """Parsed rows from the last n hours, oldest first."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    out = []
    try:
        lines = LOG.read_text(errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("ts", "") >= cutoff:
            out.append(rec)
    return out


def summarize(hours=24):
    rows = hits(hours)
    by_name, by_kind = {}, {}
    for r in rows:
        by_name[r["name"]] = by_name.get(r["name"], 0) + 1
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    return {"hours": hours, "total": len(rows),
            "by_name": dict(sorted(by_name.items(), key=lambda kv: -kv[1])),
            "by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1]))}


def write_worker():
    """Publish the guest book as a worker, so the board and the council
    pick it up through the same workers/*.json glob as everything else."""
    s = summarize(24)
    top = " · ".join(f"{n} {c}" for n, c in list(s["by_name"].items())[:4])
    summary = (f"24h: {s['total']} public hits · {top}" if s["total"]
               else "24h: no public hits")
    WORKER.parent.mkdir(exist_ok=True)
    WORKER.write_text(json.dumps({
        "worker": "visitors",
        "kind": "traffic",
        "status": "pass" if s["total"] else "idle",
        "last_run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "by_kind": s["by_kind"],
    }, indent=2))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--summary":
        print(json.dumps(summarize(int(a[1]) if len(a) > 1 else 24), indent=2))
    elif a and a[0] == "--tail":
        for r in hits(24 * 365)[-(int(a[1]) if len(a) > 1 else 40):]:
            print(f"{r['ts']} {r['status']} {r['ip']:>15} "
                  f"{r['name']:<20} {r['method']} {r['path']}")
    else:
        print(__doc__.strip())
