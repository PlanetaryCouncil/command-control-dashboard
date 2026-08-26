#!/usr/bin/env python3
"""The dormant drawer, and the one-line summary of everything in it.

We run lean. Code that nothing runs is not free -- it is read during every
audit, it is grepped by every agent looking for prior art, and it lends its
weight to claims about what this system does. Excess code is liability.

Deleting it is the wrong correction, though. Some of these answered a real
question once and the answer is still worth having; some are waiting to be
armed. So they move out of `fleet/bin` -- the live drawer -- into
`fleet/dormant`, and this file renders what is in there, one line each, so a
human can assess the whole drawer in under a minute and decide what earns its
way back or out.

The summaries are read from each module's own docstring at run time. A
manifest maintained by hand is a manifest that lies by Thursday.

Nothing here is imported by anything that runs. That is the entry
requirement, checked by fleet/bin/dormancy.py and pinned by a test.

  dormant.py            the drawer, one line per file
  dormant.py --json     same, for the board
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
DORMANT = FLEET / "dormant"


def summary(path: Path) -> str:
    """First sentence of the module docstring. A module with no docstring
    gets an empty summary rather than a guess -- an invented summary is worse
    than a missing one, because it stops anyone from opening the file."""
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except (OSError, SyntaxError):
        return ""
    doc = ast.get_docstring(tree) or ""
    first = doc.strip().split("\n\n")[0].replace("\n", " ").strip()
    return " ".join(first.split())


def last_touched(path: Path) -> str:
    """Date of the last commit that changed the file. How long something has
    been asleep is most of the case for waking it or dropping it."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--follow", "--format=%ad", "--date=short",
             "--", str(path)],
            cwd=FLEET.parent, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "?"
    except (OSError, subprocess.SubprocessError):
        return "?"


def build() -> list[dict]:
    rows = []
    for p in sorted(DORMANT.glob("*.py")):
        rows.append({
            "module": p.name,
            "path": str(p.relative_to(FLEET.parent)),
            "lines": len(p.read_text(errors="ignore").splitlines()),
            "last_touched": last_touched(p),
            "summary": summary(p),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="the dormant drawer")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = build()
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    total = sum(r["lines"] for r in rows)
    print(f"DORMANT -- {len(rows)} files, {total} lines, nothing runs them\n")
    print("Not deleted, not maintained. Read the line; if it does not earn a "
          "place, drop it.\n")
    width = max((len(r["module"]) for r in rows), default=0)
    for r in rows:
        print(f"  {r['module']:<{width}}  {r['last_touched']}  "
              f"{r['lines']:>4}L")
        print(f"  {'':<{width}}  {r['summary'][:96]}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
