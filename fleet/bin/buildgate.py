#!/usr/bin/env python3
"""Whether THIS machine builds.

Every box in the fleet can do every job — propose, test, review, build. That
is the design and it stays. But the fleet is two machines with very different
bodies: Gaia is a fanless 4-core laptop that swaps under its own dashboard,
and NUC is 12 cores and 14GB in a cupboard that runs the same test suite six
times faster (327 tests: 6.0s against 36.6s, measured 2026-08-07).

So the switch is not "can this machine build" — it can. It is "should it",
and it is a per-machine answer, kept per-machine. Gaia turns building off and
keeps proposing, testing and reviewing; NUC takes the compiling. Neither
loses a capability, and either can flip back the moment the other is down.

Default is ON. A fleet that stops improving itself because a state file went
missing is worse than one that builds on a slow box.
"""

from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
STATE = FLEET / "state" / "build-gate.json"


def host() -> str:
    return socket.gethostname().split(".")[0]


def read() -> dict:
    """The whole record, including who turned it off and when."""
    try:
        d = json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return {"enabled": True, "host": host(), "by": None, "ts": None,
                "reason": "default — no state file"}
    d.setdefault("enabled", True)
    d.setdefault("host", host())
    return d


def enabled() -> bool:
    return bool(read().get("enabled", True))


def set_enabled(on: bool, by: str = "board", reason: str = "") -> dict:
    rec = {"enabled": bool(on), "host": host(), "by": by,
           "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "reason": reason}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(rec, indent=2) + "\n")
    return rec


if __name__ == "__main__":
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg in ("on", "off"):
        print(json.dumps(set_enabled(arg == "on", by="cli"), indent=2))
    else:
        print(json.dumps(read(), indent=2))
