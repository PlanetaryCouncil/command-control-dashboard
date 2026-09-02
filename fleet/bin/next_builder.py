#!/usr/bin/env python3
"""Who builds this 15-minute slot.

One name, one slot, then the next name. A hung grok does not own the
following turn: the timer kills the slot at 15 minutes and this file
hands the next slot to someone else.

Pool is who can actually edit (grok, agy). hermes on the NUC is a 3B
local model — a different string, not a different pair of hands.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
STATE = FLEET / "state" / "builder-turn.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import quotas  # noqa: E402

POOL = ["grok", "agy"]


def next_name(last: str, live: list[str]) -> str:
    if not live:
        return POOL[0]
    if last in live:
        return live[(live.index(last) + 1) % len(live)]
    return live[0]


def main() -> int:
    live = quotas.eligible(POOL, quorum=False) or list(POOL)
    last = ""
    if STATE.exists():
        try:
            last = str(json.loads(STATE.read_text()).get("last") or "")
        except (OSError, json.JSONDecodeError, TypeError):
            last = ""
    who = next_name(last, live)
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"last": who}) + "\n")
    print(who)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
