#!/usr/bin/env python3
"""Keep the proposal ledger the size of the queue, not the size of history.

Marsita, 2026-09-04: "4879 rows ----> simplify, triage... I don't want to have
5k proposals waiting."

They were not waiting. Measured the same morning: of 4,885 rows only **12** had
not been through the pipeline. The rest were finished work, 823 of them logged
errors, and 547 identical rows from one agent repeating a single failure. An
append-only ledger had been read as a backlog by everything that opened it --
the board, the report, and anyone glancing at `wc -l`.

So this does not throw away decisions. It moves what is already settled to an
archive beside the live file, and leaves behind exactly what a reader would
call a queue: everything unprocessed, plus a few days of recent context.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
LEDGER = FLEET / "rota" / "proposals.jsonl"
PIPELINE = FLEET / "rota" / "pipeline.jsonl"
ARCHIVE = FLEET / "rota" / "proposals-archive.jsonl"
KEEP_DAYS = 3


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def processed(path: Path = PIPELINE) -> set[str]:
    return {str(r.get("proposal_ts")) for r in rows(path) if r.get("proposal_ts")}


def split(ledger: list[dict], seen: set[str], *, keep_days: int = KEEP_DAYS,
          now: dt.datetime | None = None) -> tuple[list[dict], list[dict]]:
    """(keep, archive). A row is archived only if it is BOTH processed and old.

    Both, not either. Processed-but-recent is the context a reader needs to
    judge what just happened, and unprocessed-but-ancient is still work nobody
    has done -- archiving that would silently drop it, which is the one thing
    this must never do.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=keep_days)
    keep, archive = [], []
    for r in ledger:
        ts = str(r.get("ts") or "")
        try:
            when = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            keep.append(r)          # unparseable: never guess, never drop
            continue
        if ts in seen and when < cutoff:
            archive.append(r)
        else:
            keep.append(r)
    return keep, archive


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=KEEP_DAYS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ledger = rows(LEDGER)
    keep, archive = split(ledger, processed(), keep_days=args.days)
    print(f"{len(ledger)} rows -> keep {len(keep)}, archive {len(archive)}")
    if args.dry_run or not archive:
        return 0

    # Append to the archive before shortening the ledger. If this dies between
    # the two, the worst case is a duplicated row in the archive; the other
    # order loses proposals.
    with ARCHIVE.open("a") as fh:
        for r in archive:
            fh.write(json.dumps(r) + "\n")
    tmp = LEDGER.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in keep))
    tmp.replace(LEDGER)
    print(f"archived to {ARCHIVE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
