#!/usr/bin/env python3
"""Every open issue across every repo, in one list.

Marsita, 2026-09-04: "I should work with issues on my other projects...
Currently too much just me in terminal with Claude" -- then, honestly: "I need
to get disciplined to be creating issues and then sorting them out."

Discipline is the wrong lever. There were eighteen open issues across eight
repositories that night, and the reason none of them moved was not willpower:
seeing them meant eight browser tabs, and filing one meant leaving the
terminal. Both of those are friction, and friction is fixable in a way that
discipline is not.

So: one `gh search` call for all of it (1.8s, not eight round trips), cached to
disk because the board polls and GitHub rate-limits. And `bin/issue`, which
turns one typed sentence into a filed issue without opening anything.

Local only. The repos are the operator's, some are private, and an open issue
is a to-do list -- the board publishes what the fleet DID, never what it has
not got round to.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
CACHE = FLEET / "state" / "issues.json"

# Both accounts Marsita publishes under. An owner missing from this list is a
# repo whose issues silently do not exist, so it is deliberately short and
# deliberately here rather than derived from whatever remotes happen to be
# cloned on this machine -- the NUC and the laptop have different clones.
OWNERS = ("PlanetaryCouncil", "marsrobertson")

TTL = 300               # five minutes; issues are not a live stream
LIMIT = 100


def _gh(*args: str, timeout: int = 30) -> str:
    """Run gh, or return "" -- never raise into a page render."""
    try:
        r = subprocess.run(("gh", *args), capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def fetch() -> list[dict]:
    """Open issues across every owner, newest first. One call, not one per repo."""
    args = ["search", "issues"]
    for o in OWNERS:
        args += ["--owner", o]
    args += ["--state", "open", "--limit", str(LIMIT), "--json",
             "number,title,repository,createdAt,labels,url"]
    raw = _gh(*args)
    try:
        rows = json.loads(raw or "[]")
    except ValueError:
        return []
    out = []
    for r in rows:
        repo = (r.get("repository") or {}).get("name") or ""
        out.append({
            "repo": repo,
            "number": r.get("number"),
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "created": r.get("createdAt") or "",
            "labels": [l.get("name") for l in (r.get("labels") or []) if l.get("name")],
        })
    out.sort(key=lambda r: r["created"], reverse=True)
    return out


def age_days(created: str, now: datetime | None = None) -> int | None:
    """How long it has been sitting. The number that makes a list a backlog."""
    try:
        t = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return max(0, int(((now or datetime.now(timezone.utc)) - t).total_seconds() // 86400))


def snapshot(*, ttl: int = TTL, cache: Path | None = None, now: float | None = None) -> dict:
    """The pane's data, from cache when it is fresh enough.

    Served stale rather than empty when gh fails: a rate limit or a dropped
    network should show yesterday's list with its age, not an empty pane that
    reads as "you have no work".
    """
    path = cache or CACHE
    now = now if now is not None else time.time()
    old = {}
    try:
        old = json.loads(path.read_text())
    except (OSError, ValueError):
        old = {}
    if old.get("at") and now - old["at"] < ttl:
        return old

    rows = fetch()
    if not rows and old.get("issues"):
        return old | {"stale": True}       # keep what we had, say that we did

    snap = {"at": now, "issues": rows, "count": len(rows),
            "repos": sorted({r["repo"] for r in rows})}
    for r in snap["issues"]:
        r["age_days"] = age_days(r["created"])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snap, indent=1))
    except OSError:
        pass
    return snap


def create(repo: str, title: str, body: str = "") -> str:
    """File one. Returns the issue URL, or "" if gh would not.

    `repo` may be the short name -- "ux" -- because that is what gets typed.
    The owner is guessed by asking GitHub which of them has it, rather than
    hard-coding one and filing into the wrong account.
    """
    if "/" not in repo:
        for o in OWNERS:
            if _gh("repo", "view", f"{o}/{repo}", "--json", "name", timeout=15):
                repo = f"{o}/{repo}"
                break
        else:
            return ""
    args = ["issue", "create", "--repo", repo, "--title", title]
    if body:
        args += ["--body", body]
    else:
        # gh refuses a create with no body at all, and an empty one is more
        # honest than repeating the title into it.
        args += ["--body", "_filed from the terminal_"]
    return _gh(*args, timeout=30).strip()


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=1))
