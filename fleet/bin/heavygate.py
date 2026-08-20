#!/usr/bin/env python3
"""Whether THIS machine runs heavy fleet work.

Same shape as buildgate: every box can do every job, the switch says
whether it should. Gaia is a fanless 4-core laptop; the NUC is 12 cores
and 15G in a cupboard. Council, rota, heartbeat, e2e, watchdogs and
local-voice belong there. This box keeps the board.

Default is ON. A missing file must not silence a machine that is
supposed to think.
"""
from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
STATE = FLEET / "state" / "heavy-gate.json"

# launchd labels apply-config.sh must unload when this gate is off.
JOBS = (
    "re.genesis.council",
    "re.genesis.rota",
    "re.genesis.watchdogs",
    "re.genesis.pipeline",
    "re.genesis.comms-heartbeat",
    "re.genesis.e2e",
    "re.genesis.self-improve",
    "re.genesis.local-voice",
)


def host() -> str:
    return socket.gethostname().split(".")[0]


def read() -> dict:
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
        reason = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        print(json.dumps(set_enabled(arg == "on", by="cli", reason=reason),
                         indent=2))
    else:
        print(json.dumps(read(), indent=2))
