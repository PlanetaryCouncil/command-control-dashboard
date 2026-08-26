#!/usr/bin/env python3
"""Keep the last 1000 lines. That is the context window.

Marsita, issue #45: "trim by default log to 1000 lines as well. That's our
'context window', old and noisy messages are auto purged."

The idea is better than housekeeping. A log nobody can read is not evidence,
it is storage — and a fleet that keeps everything forever is making the same
mistake as a fleet that meets every sixty seconds. What matters is what
happened recently enough to act on.

Line-based, not size-based, deliberately: 1000 lines is a number a human can
reason about ("the last thousand things that happened"), where 8MB is a
number only a disk cares about.

    trim.py            trim the fleet's logs and jsonl ledgers
    trim.py --dry-run  say what it would drop, touch nothing
    trim.py --keep N   a different ceiling

Ledgers that are the fleet's memory rather than its noise — proposals,
pipeline verdicts, the council transcript — are NOT trimmed. Losing the
record of what was decided is not the same as losing chatter.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Overridable so one checkout can trim another's logs — a worktree's fleet/
# directory has no logs in it, and that silently reported "nothing to do".
FLEET = Path(os.environ.get("FLEET_DIR",
                            Path(__file__).resolve().parent.parent))
KEEP = 1000

# Chatter: regenerated constantly, valuable only while recent.
TRIM = [
    "logs/*.log",
    "logs/*.jsonl",
    "events.jsonl",
]

# Memory: what the fleet decided and why. Small, and worth keeping whole.
NEVER = {"proposals.jsonl", "pipeline.jsonl", "transcript.jsonl",
         "signatures-collected.jsonl"}


def targets() -> list[Path]:
    out = []
    for pattern in TRIM:
        out.extend(p for p in FLEET.glob(pattern)
                   if p.is_file() and p.name not in NEVER)
    return sorted(set(out))


def trim(path: Path, keep: int, dry_run: bool = False) -> int:
    """Return how many lines would be (or were) dropped."""
    try:
        lines = path.read_text(errors="replace").splitlines(keepends=True)
    except OSError:
        return 0
    excess = len(lines) - keep
    if excess <= 0:
        return 0
    if not dry_run:
        # Write the whole file rather than seeking: these are small once
        # trimmed, and a partial write on a log being appended to is worse
        # than a moment of extra memory.
        path.write_text("".join(lines[-keep:]))
    return excess


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    keep = KEEP
    if "--keep" in argv:
        try:
            keep = int(argv[argv.index("--keep") + 1])
        except (IndexError, ValueError):
            print("--keep needs a number", file=sys.stderr)
            return 2

    total = 0
    for p in targets():
        dropped = trim(p, keep, dry)
        if dropped:
            total += dropped
            print(f"{'would drop' if dry else 'dropped'} {dropped:>7} lines  "
                  f"{p.relative_to(FLEET)}")
    print(f"{'would keep' if dry else 'kept'} last {keep} lines per file · "
          f"{total} lines {'would be ' if dry else ''}removed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
