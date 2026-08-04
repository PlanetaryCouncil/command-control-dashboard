#!/usr/bin/env python3
"""Every worker on this machine has a hand. This reads it.

A human signs the pad by moving a pointer for five seconds: the mark is made of
where the hand went and the uneven gaps between when it got there. An agent has
no pointer, so the obvious move is to give it a random number — and a random
number is not a signature, it is a name badge.

An agent does move, though. It moves through work. So the same three numbers
come from the same kind of thing:

    human                        agent
    x   where the hand was       when it acted, along its own lifetime
    y   how far from centre      how hard that act was — seconds, or level
    t   when                     the gap since it last did anything

That path goes through the identical projector the pad uses, so a person and a
process are drawn by the same function and are comparable as marks. Nothing
about the agent's signature is decorative: a worker that runs every hour in
90-second bursts cannot produce the same shape as one that wakes twice a day
and thinks for five minutes.

The seed is SHA-256 over that path, so it is stable while the history is, and
it moves when the agent does more work. An agent's mark is not fixed at birth.
It is the accumulated shape of everything it has done, which is the only
honest thing a signature can be.

    python3 fleet/bin/signature.py            # table of every agent
    python3 fleet/bin/signature.py --json     # full payload for the renderer
"""

import hashlib
import json
import math
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
EVENTS = FLEET / "events.jsonl"

# Levels ordered by how much they mean, not alphabetically. This is the y-axis
# fallback when an event carries no duration, so the ordering is visible in the
# drawing: an agent that mostly fails traces a different line from one that
# mostly passes.
LEVEL_WEIGHT = {"ok": 0.25, "info": 0.4, "warn": 0.7, "alert": 0.85,
                "needs_you": 1.0, "fail": 1.0, "error": 1.0}

MAX_POINTS = 400          # a signature is a gesture, not a chart


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def load_events(path=EVENTS):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if parse_ts(e.get("ts")):
            out.append(e)
    return out


def effort(event):
    """How hard this act was, in 0..1.

    Prefer a real duration when the event carries one — a 300-second council
    turn and a 25-second relay hop are genuinely different amounts of work.
    Log-scaled, because the range spans three orders of magnitude and a linear
    axis would render every fast event as the same flat line.
    """
    for key in ("seconds", "duration", "elapsed"):
        v = event.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return min(math.log10(1 + v) / 3.0, 1.0)
    return LEVEL_WEIGHT.get(str(event.get("level", "")).lower(), 0.5)


def path_for(events):
    """The agent's trace as (x, y, t), in the same shape the pad produces.

    x runs 0..1 across the agent's whole recorded life, so a worker's mark is
    drawn over its own timeline rather than the clock's — two agents with the
    same rhythm look alike even if one started a week later.

    y is signed by alternating sides of the centre line. A one-sided trace
    folds into a fan; alternating gives the mark something to cross, which is
    what makes it read as handwriting rather than a spirograph.
    """
    if len(events) < 2:
        return []

    events = sorted(events, key=lambda e: parse_ts(e["ts"]))
    if len(events) > MAX_POINTS:                # keep the ends, thin the middle
        step = len(events) / MAX_POINTS
        events = [events[int(i * step)] for i in range(MAX_POINTS)]

    t0 = parse_ts(events[0]["ts"])
    span = max((parse_ts(events[-1]["ts"]) - t0).total_seconds(), 1.0)

    pts, prev = [], t0
    for i, e in enumerate(events):
        ts = parse_ts(e["ts"])
        gap = (ts - prev).total_seconds()
        prev = ts
        pts.append({
            "x": (ts - t0).total_seconds() / span,
            "y": effort(e) * (1 if i % 2 == 0 else -1),
            # t is the gap, not the clock: the pad's t is also a delta, and the
            # projector reads it as speed. A burst draws thin, a pause draws heavy.
            "t": round(min(gap, 86400.0), 3),
        })
    return pts


def seed_for(pts):
    """SHA-256 over the path, packed the same way the browser packs the pad's.

    Float64 little-endian triples, so a path captured in the page and a path
    computed here hash identically. If that ever drifts, a human and an agent
    stop being comparable and the whole idea quietly stops meaning anything.
    """
    if not pts:
        return None
    buf = b"".join(struct.pack("<3d", p["x"], p["y"], p["t"]) for p in pts)
    return hashlib.sha256(buf).hexdigest()


def signatures(path=EVENTS, min_events=8):
    """One entry per agent with enough history to have a hand at all."""
    by_agent = {}
    for e in load_events(path):
        by_agent.setdefault(e.get("agent", "?"), []).append(e)

    out = []
    for agent, events in by_agent.items():
        if len(events) < min_events:
            continue                     # too few strokes to be a signature
        pts = path_for(events)
        seed = seed_for(pts)
        if not seed:
            continue
        last = parse_ts(sorted(events, key=lambda e: parse_ts(e["ts"]))[-1]["ts"])
        out.append({
            "agent": agent,
            "seed": seed,
            "events": len(events),
            "points": pts,
            "last_seen": last.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
    out.sort(key=lambda s: -s["events"])
    return out


if __name__ == "__main__":
    sigs = signatures()
    if "--json" in sys.argv:
        print(json.dumps({"signatures": sigs}, indent=2))
    else:
        print(f"{'agent':<28}{'events':>8}  {'seed':<20}{'last seen'}")
        print("-" * 88)
        for s in sigs:
            print(f"{s['agent']:<28}{s['events']:>8}  "
                  f"{s['seed'][:18]:<20}{s['last_seen'][:19]}")
        if not sigs:
            print("no agent has enough history yet")
