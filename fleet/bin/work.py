#!/usr/bin/env python3
"""What is being worked on right now, read straight out of git.

Every other pane on this board describes the *fleet* — what ran, what is
stale, what is burning CPU. None of them answers the question you actually ask
when you sit down: what am I in the middle of? The board could show ten commits
landed today and not one pane knew it.

So this reads the repository itself. Not a status file somebody has to
remember to update — a status file is a claim, and a claim goes stale the
moment the work moves. git already knows, and git cannot lie about it.

Public and local see different things. Landed commits and the file history are
already on GitHub, so a stranger gets those. Uncommitted work is not published
yet and does not become published by being on a board, so the dirty tree is
local-only — the same split the rest of the server uses: reads are public,
the unfinished stuff stays home.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# A day's work, not an hour's. Short enough that "today" means today, long
# enough that a late night still counts as the same session.
HOT_DAYS = 7
HOT_TOP = 6
RECENT_COMMITS = 8


def _git_raw(*args: str, cwd: Path | None = None) -> str:
    """Run git and return stdout untouched, or "" if anything goes wrong.

    A dashboard pane must never take the page down because a directory is not
    a repo, or git is missing, or the index is locked by a commit happening in
    another window. Every failure here means "nothing to report", never a 500.
    """
    try:
        r = subprocess.run(("git", *args), cwd=str(cwd or REPO),
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _git(*args: str, cwd: Path | None = None) -> str:
    """`_git_raw` with the surrounding whitespace trimmed.

    Convenient for everything except porcelain status, where column 1 is a
    SPACE for an unstaged change — " M path" — and stripping it shifts every
    field left by one. That bug shipped a pane reading "leet/bin/fleet.py".
    Anything parsed by column offset must use `_git_raw`.
    """
    return _git_raw(*args, cwd=cwd).strip()


def _branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD") or "?"


def _ahead_behind() -> tuple[int, int]:
    """Commits ahead of and behind the upstream, or (0, 0) with no upstream.

    "3 unpushed" is the sentence that makes someone go push. A branch with no
    upstream is not behind by infinity, it just has nowhere to be compared to.
    """
    out = _git("rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if not out:
        return 0, 0
    try:
        behind, ahead = (int(x) for x in out.split())
    except ValueError:
        return 0, 0
    return ahead, behind


def _dirty() -> list[dict]:
    """Uncommitted paths with their porcelain status code.

    -z because filenames contain spaces and one of them will eventually
    contain a newline; splitting porcelain output on "\\n" works right up until
    the day it silently drops a file.
    """
    out = _git_raw("status", "--porcelain=1", "-z")
    if not out:
        return []
    items = []
    for entry in out.split("\0"):
        if len(entry) > 3:
            items.append({"code": entry[:2].strip() or "?", "path": entry[3:]})
    return items


def _commits_since_midnight() -> list[dict]:
    """Today's landed work, newest first.

    Local midnight, not UTC: the question is "what did I do today", and today
    is the day the person asking is living in.
    """
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    out = _git("log", "--since", midnight.isoformat(),
               "--format=%h\x1f%s\x1f%cI", f"-{RECENT_COMMITS * 3}")
    rows = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            rows.append({"sha": parts[0], "subject": parts[1], "at": parts[2]})
    return rows


def _recent_commits() -> list[dict]:
    """The last few commits whatever their date.

    A quiet day would otherwise render an empty pane, which reads as "the
    board is broken" rather than "you have not committed yet". There is always
    a last commit; show it.
    """
    out = _git("log", f"-{RECENT_COMMITS}", "--format=%h\x1f%s\x1f%cI")
    rows = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            rows.append({"sha": parts[0], "subject": parts[1], "at": parts[2]})
    return rows


def _hot_files() -> list[dict]:
    """Files touched most often in the last week — where the work actually is.

    Commit subjects say what you meant to do. The file histogram says what you
    kept going back to, which is usually the more honest answer.
    """
    out = _git("log", f"--since={HOT_DAYS}.days", "--name-only",
               "--format=", "--no-merges")
    counts: dict[str, int] = {}
    for line in out.splitlines():
        p = line.strip()
        if p:
            counts[p] = counts.get(p, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"path": p, "touches": n} for p, n in ranked[:HOT_TOP]]


def snapshot(local: bool = False) -> dict:
    """The whole picture. `local` adds the uncommitted tree.

    Ordered the way it gets read: what is unfinished, then what landed, then
    where the work has been sitting.
    """
    today = _commits_since_midnight()
    ahead, behind = _ahead_behind()
    out = {
        "at": datetime.now(timezone.utc).isoformat(),
        "branch": _branch(),
        "ahead": ahead,
        "behind": behind,
        "today": today,
        "today_count": len(today),
        "recent": _recent_commits(),
        "hot": _hot_files(),
        "local": local,
    }
    if local:
        dirty = _dirty()
        out["dirty"] = dirty
        out["dirty_count"] = len(dirty)
    else:
        # Absent, not zero. A public viewer being told "0 uncommitted files"
        # would be a claim about a tree they were not shown.
        out["dirty"] = None
        out["dirty_count"] = None
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(snapshot(local=True), indent=2))
