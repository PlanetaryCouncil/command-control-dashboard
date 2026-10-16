#!/usr/bin/env python3
"""Marsita's projects, for the one screen she actually looks at.

Marsita, 2026-09-10: "I don't care about little issues now with architecture,
they should resolve itself... I care about usability of me as the end user...
I see my projects, I see my issues."

Sixteen projects were already written down, in `fleet/data/projects.yaml`, and
the board had a pane for the repo it happens to be running in and none for the
work the repo exists to serve. This reads that file and nothing else -- the
file is the source of truth, edited by hand, and this is not allowed to have an
opinion the file does not already hold.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

FLEET = Path(__file__).resolve().parent.parent
YAML = FLEET / "data" / "projects.yaml"

# Live first, then the ones waiting on a deploy, then everything else. A
# for-sale project is still a project but it is not what you sat down to look
# at, so it goes last rather than being hidden.
ORDER = {"active": 0, "awaiting-deployment": 1, "for-sale": 3}

_CACHE = {"mtime": 0.0, "rows": []}

# How many tiles sit above the fold on /projects: a 4 x 3 board. The rest are
# still there, below it.
FOLD = 12

# Vibe flip: one day a week the least fun projects become the most fun, so
# the ones nobody wants to touch get their turn at the top. Marsita,
# 2026-10-11: "one day of the week we switch vibes, less vibes become the
# most vibes... Fridays? we don't like fridays... Or maybe mondays to sync
# with population?" Monday: the week starts for everyone else, so the chores
# that need other people meet them on the day they are reachable.
FLIP_DAY = 0            # datetime.weekday(): Monday
# Her day runs ~13:00-04:00, so 02:00 on Monday is still Sunday night.
DAY_STARTS_AT = 4


# GitHub on every tile. Marsita, 2026-10-14: "Each tile should have links to
# GitHub... So that anyone can participate... Humans and AI... Building
# civilisations infrastructure." This reverses the old rule that open issues
# stay local (bin/issues.py): on /projects the to-do list IS the invitation.
# Only for repos GitHub confirms are public -- a private repo's name is
# already in projects.yaml, but its issues and a link that 404s are not.
GH_TTL = 300            # five minutes, same as bin/issues.py
_GH = {"at": 0.0, "stats": {}}


def _fetch_stats(repos: list[str]) -> dict[str, dict]:
    """repo (lowercased) -> {"private", "open"}, in one GraphQL call.

    One call for every repo rather than one each: the page polls and GitHub
    rate-limits. A repo that is gone or renamed comes back null and is left
    out. Any failure is {} -- a pane must never take the page down.
    """
    parts = []
    for i, r in enumerate(repos):
        owner, _, name = r.partition("/")
        parts.append(f'r{i}: repository(owner: {json.dumps(owner)}, '
                     f'name: {json.dumps(name)}) {{ nameWithOwner isPrivate '
                     f'issues(states: OPEN) {{ totalCount }} }}')
    if not parts:
        return {}
    try:
        out = subprocess.run(
            ("gh", "api", "graphql", "-f", "query={ " + " ".join(parts) + " }"),
            capture_output=True, text=True, timeout=30).stdout
        data = json.loads(out).get("data") or {}
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return {}
    stats = {}
    for i, r in enumerate(repos):
        node = data.get(f"r{i}")
        if node:
            stats[r.lower()] = {"private": bool(node["isPrivate"]),
                                "open": int(node["issues"]["totalCount"])}
    return stats


def repo_stats(repos: list[str]) -> dict[str, dict]:
    """_fetch_stats, cached. A failed fetch keeps the last good answer."""
    if time.time() - _GH["at"] > GH_TTL:
        fresh = _fetch_stats(repos)
        if fresh:
            _GH["stats"] = fresh
        _GH["at"] = time.time()
    return _GH["stats"]


def github(repos: list[str], stats: dict[str, dict]) -> dict | None:
    """The GitHub corner of one tile: where the code is, what is open.

    A repo GitHub says is private is dropped. One it has not answered for
    keeps its link and has no count: the name is public in projects.yaml
    already, and a missing number is better than a made-up zero.
    """
    shown = [r for r in repos if not stats.get(r.lower(), {}).get("private")]
    if not shown:
        return None
    counts = [stats[r.lower()]["open"] for r in shown if r.lower() in stats]
    owners = {r.split("/")[0] for r in shown}
    if len(shown) == 1:
        home = f"https://github.com/{shown[0]}"
        issues = f"{home}/issues"
    else:
        # Several repos under one owner: the owner's page. Across owners
        # there is no single page, so the first repo stands for them.
        home = (f"https://github.com/{shown[0].split('/')[0]}"
                if len(owners) == 1 else f"https://github.com/{shown[0]}")
        q = " ".join(["is:issue", "is:open"] + [f"repo:{r}" for r in shown])
        issues = "https://github.com/search?" + urlencode({"q": q, "type": "issues"})
    return {"repos": [{"repo": r, "url": f"https://github.com/{r}",
                       "open": stats.get(r.lower(), {}).get("open")}
                      for r in shown],
            "url": home, "issues_url": issues,
            "new_issue_url": f"https://github.com/{shown[0]}/issues/new",
            "open": sum(counts) if counts else None}


def flip_day(now: datetime | None = None) -> bool:
    now = now or datetime.now()
    return (now - timedelta(hours=DAY_STARTS_AT)).weekday() == FLIP_DAY


def _score(v) -> int | None:
    """A 0-10 score from the file, or None when nobody has scored it yet.

    Marsita, 2026-10-11: each project gets importance (in general),
    urgency (now) and vibes (how nice it is to work on), 0 to 10.
    A blank is not a zero -- zero is a decision, blank is the absence of one,
    and inventing a number would put a project above the fold on a guess.
    """
    if isinstance(v, bool) or v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 10 and n == v else None


def _load() -> dict:
    """The YAML file, or {} -- a pane must never take the page down."""
    try:
        import yaml
        return yaml.safe_load(YAML.read_text()) or {}
    except Exception:
        return {}


def projects(*, path: Path | None = None) -> list[dict]:
    """The list, ordered, re-read only when the file has actually changed."""
    p = path or YAML
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return []
    if path is None and mtime == _CACHE["mtime"]:
        return _CACHE["rows"]
    doc = _load() if path is None else (
        __import__("yaml").safe_load(p.read_text()) or {})
    rows = []
    for i, raw in enumerate(doc.get("projects") or []):
        status = str(raw.get("status") or "").strip() or "unknown"
        url = str(raw.get("url") or "").strip()
        repos = [str(r).strip() for r in (raw.get("repos") or []) if str(r).strip()]
        rows.append({
            "name": str(raw.get("name") or "").strip(),
            # Every GitHub repo that IS this project. Several is normal --
            # BaseX is five. None means none yet, not "unknown": guessing a
            # repo would file its issues under the wrong project.
            "repos": repos,
            # A relative url in that file means a page on this board, and the
            # board is where it is being read, so it works as written.
            "url": url,
            "status": status,
            # The pill on its tile, set by hand in the file (ART, META, CORE).
            # Blank = no pill. Marsita, 2026-10-16: "Skip the active pill."
            "label": str(raw.get("label") or "").strip(),
            "tagline": str(raw.get("tagline") or "").strip(),
            # `TODO` is how the file marks a field nobody has filled in. It is
            # honest in the file and noise on a dashboard.
            "live": url.startswith("http"),
            "importance": _score(raw.get("importance")),
            "urgency": _score(raw.get("urgency")),
            "vibes": _score(raw.get("vibes")),
        })
    # A project with a repo and no url is still a project -- send it to the
    # repo. Only a row with nowhere at all to point gets dropped.
    for r in rows:
        if r["url"].upper() == "TODO" or not r["url"]:
            r["url"] = f'https://github.com/{r["repos"][0]}' if r["repos"] else ""
            r["live"] = bool(r["url"])
    rows = [r for r in rows if r["name"] and r["url"]]
    rows.sort(key=lambda r: (ORDER.get(r["status"], 2), r["name"].lower()))
    if path is None:
        _CACHE.update(mtime=mtime, rows=rows)
    return rows


def ranked(rows: list[dict], *, flipped: bool = False) -> list[dict]:
    """The tile order: urgency first, then importance, then vibes.

    Urgency is how important it is now, importance how important in
    general; above the fold is for now. Vibes only break ties -- except on
    flip day, when inverted vibes (10 - vibes) go first, so the least fun
    work leads. Unscored projects come after every scored one, in the
    file's usual order -- a blank never outranks a decision. Sorted is
    stable, so ties keep that order too.
    """
    def n(v):
        return -(v if v is not None else -1)

    def key(r):
        u, i, v = r.get("urgency"), r.get("importance"), r.get("vibes")
        blank = u is None and i is None and v is None
        if flipped:
            fv = None if v is None else 10 - v
            return (blank, n(fv), n(u), n(i))
        return (blank, n(u), n(i), n(v))
    return sorted(rows, key=key)


def title(doc: dict | None = None) -> str:
    """The name at the top of /projects: `title` in the file, else the
    owner's alias. Marsita, 2026-10-11: the YAML names it, and "that can
    become my dashboard"."""
    doc = _load() if doc is None else doc
    owner = doc.get("owner") or {}
    for v in (doc.get("title"), owner.get("alias"), owner.get("name")):
        if isinstance(v, str) and v.strip() and v.strip().upper() != "TODO":
            return v.strip()
    return "Projects"


def repo_owner() -> dict[str, str]:
    """repo (lowercased) -> project name. For grouping issues by project.

    Lowercased because GitHub is case-insensitive about repo names and the
    file is written the way a human types them: DatingRelating.com in one
    place, datingrelating.com in another, the same repo both times.
    """
    out = {}
    for row in projects():
        for repo in row["repos"]:
            out[repo.lower()] = row["name"]
            # An issue only ever knows its own short name, not the owner.
            out[repo.split("/")[-1].lower()] = row["name"]
    return out


def snapshot(now: datetime | None = None) -> dict:
    rows = projects()
    flipped = flip_day(now)
    stats = repo_stats([r for row in rows for r in row["repos"]])
    # Copies: rows is the mtime cache, and counts go stale long before the
    # file changes.
    rows = [{**row, "github": github(row["repos"], stats)} for row in rows]
    return {"title": title(), "projects": rows, "count": len(rows),
            # Names in tile order for /projects; the first FOLD sit above it.
            "tiles": [r["name"] for r in ranked(rows, flipped=flipped)],
            "fold": FOLD, "flipped": flipped,
            "active": sum(1 for r in rows if r["status"] == "active"),
            "repos": repo_owner()}


if __name__ == "__main__":
    for r in projects():
        print(f'{r["status"]:<22} {r["name"]:<44} {r["url"]}')
