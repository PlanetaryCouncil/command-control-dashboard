#!/usr/bin/env python3
"""Append-only event log for the fleet.

  events.py <agent> <level> <message>     record one event
  events.py --tail [n]                    print the last n events

Append-only JSONL so the live view can stream it and you can still read it
after the fact when something went wrong at 3am. Levels: info, ok, warn, error,
needs_you. `needs_you` is what raises the banner in the live view — reserve it
for things that are genuinely blocked on a human.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent

# FLEET_EVENTS redirects the log. This exists because the test suite drives
# the real watchdog.sh, which derives its own FLEET from its own location and
# so wrote into the live board: on 2026-08-26 the public page showed a red
# "3 NEED YOU -- proj2 tests failed" about two projects that have never
# existed, invented by a passing test. A board that cries wolf from its own
# CI is worse than a board with no alerts, because the operator learns to
# scroll past red.
LOG = Path(os.environ.get("FLEET_EVENTS", FLEET / "events.jsonl"))
MAX_BYTES = 4_000_000          # ~20k events; rotate rather than grow forever

LEVELS = {"info", "ok", "warn", "error", "needs_you"}

# docs/TRUST-LAYERS.md, made machine-readable. A layer describes the STATEMENT,
# never the agent that carried it: the nuc is family and trusted, and a web page
# it read aloud is still layer 4 afterwards.
LAYERS = {
    0: "operator",   # Mars
    1: "vouched",    # a trusted human or family machine, speaking as itself
    2: "derived",    # family, repeating or acting on lower-layer material
    3: "medium",     # a source we chose and assume aligned
    4: "hostile",    # open internet, guests, other agents
}
DEFAULT_LAYER = 2    # unsaid means derived: a machine talking about work it did


def emit(agent, level, message, origin=None, layer=None, **extra):
    """Record one event.

    `origin` is where the WORDS came from, which is not always the agent that
    emitted them. A worker reporting its own test results is its own origin;
    a worker quoting a web page names that page, and the event is layer 4 no
    matter how trusted the worker is.
    """
    if level not in LEVELS:
        level = "info"
    # Terminal furniture is contagious: on 2026-08-04 openclaw opened a rota
    # proposal with an 80-block bar it had learned from reading this stream,
    # and the truncated preview became pure decoration — "██████████…", zero
    # information (claude spotted both in council). Block-glyph runs carry no
    # meaning in a log line, so collapse them at the door.
    message = re.sub(r"[█▉▊▋▌▍▎▏▐▓▒░]{3,}", "▍", str(message))
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": str(agent)[:60],
        "level": level,
        "msg": str(message)[:400],
    }
    rec.update(extra)

    # After the update, never before. `extra` is often built from material the
    # caller did not write, and a payload that could set its own layer would be
    # a payload that promotes itself - which is the one thing the model forbids.
    # Anything unparseable lands on the floor, not on the ceiling.
    try:
        lay = DEFAULT_LAYER if layer is None else int(layer)
    except (TypeError, ValueError):
        lay = 4
    rec["layer"] = lay if lay in LAYERS else 4
    rec["trust"] = LAYERS[rec["layer"]]
    rec["origin"] = str(origin if origin is not None else agent)[:80]

    try:
        if LOG.exists() and LOG.stat().st_size > MAX_BYTES:
            LOG.rename(LOG.with_suffix(".jsonl.1"))
        # Line-buffered append; concurrent workers each write one whole line.
        with LOG.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass
    return rec


def tail(n=200):
    try:
        lines = LOG.read_text(errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__.strip())
    elif a[0] == "--tail":
        for e in tail(int(a[1]) if len(a) > 1 else 40):
            print(f"{e['ts']} [{e['level']:>9}] {e['agent']}: {e['msg']}")
    elif len(a) >= 3:
        emit(a[0], a[1], " ".join(a[2:]))
    else:
        print("usage: events.py <agent> <level> <message>", file=sys.stderr)
        sys.exit(2)
