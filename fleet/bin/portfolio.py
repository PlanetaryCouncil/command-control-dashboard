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
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
YAML = FLEET / "data" / "projects.yaml"

# Live first, then the ones waiting on a deploy, then everything else. A
# for-sale project is still a project but it is not what you sat down to look
# at, so it goes last rather than being hidden.
ORDER = {"active": 0, "awaiting-deployment": 1, "for-sale": 3}

_CACHE = {"mtime": 0.0, "rows": []}


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
        rows.append({
            "name": str(raw.get("name") or "").strip(),
            # A relative url in that file means a page on this board, and the
            # board is where it is being read, so it works as written.
            "url": url,
            "status": status,
            "tagline": str(raw.get("tagline") or "").strip(),
            # `TODO` is how the file marks a field nobody has filled in. It is
            # honest in the file and noise on a dashboard.
            "live": url.startswith("http"),
        })
    rows = [r for r in rows if r["name"] and r["url"].upper() != "TODO"]
    rows.sort(key=lambda r: (ORDER.get(r["status"], 2), r["name"].lower()))
    if path is None:
        _CACHE.update(mtime=mtime, rows=rows)
    return rows


def snapshot() -> dict:
    rows = projects()
    return {"projects": rows, "count": len(rows),
            "active": sum(1 for r in rows if r["status"] == "active")}


if __name__ == "__main__":
    for r in projects():
        print(f'{r["status"]:<22} {r["name"]:<44} {r["url"]}')
