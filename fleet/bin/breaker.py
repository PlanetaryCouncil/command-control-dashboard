#!/usr/bin/env python3
"""Stop re-running a job that keeps failing the same way.

Proposed by the council on 2026-08-02, in its own words:

    Three relays — 16:44, 17:30, 18:18 — produced byte-identical outcomes.
    Each costs ~16 minutes of wall clock to reproduce a result we already had.
    The fleet is spending its cycles re-observing and re-discussing one
    deterministic failure.

That is the argument. On four cores, sixteen minutes of relay is sixteen minutes
the machine cannot spend on anything else, and a deterministic failure repeated
hourly produces no new information after the second run.

Two properties matter and they pull against each other:

**It only trips on *identical* failure.** A flapping job — different agents
failing on different laps — is still telling you something, so it keeps running.
Sameness is the signal that watching has stopped paying.

**It never hides the failure, only stops repeating it.** A tripped breaker
writes a louder status than the failures did, because a job that quietly stopped
running is the worst outcome available: that is the "silent worker looks
identical to a healthy one" fault this fleet has already been bitten by twice.
Suspended must read as worse than failing, never as calm.

Resetting is manual and deliberate — `--reset`, or delete the state file. A
breaker that resets itself on a timer is just a slower retry loop, and would
re-acquire the cost the council was trying to give back.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
STATE_DIR = FLEET / "state"

# Two identical runs is a coincidence. Three is a pattern, and the fourth teaches
# nothing the third did not — so the third trips it.
THRESHOLD = 3


def _path(job: str) -> Path:
    return STATE_DIR / f"breaker-{job}.json"


def fingerprint(outcome: dict) -> str:
    """What "the same failure" means, deliberately narrow.

    Durations and counters are excluded: a relay that fails identically but two
    seconds slower is the same failure, and including timing would keep the
    breaker permanently reset by noise. What matters is which agent failed, on
    which lap, and how.
    """
    shape = sorted(
        (h.get("agent"), h.get("lap"), h.get("outcome") or ("ok" if h.get("ok") else "fail"))
        for h in outcome.get("hops", [])
    )
    payload = json.dumps({"status": outcome.get("status"), "shape": shape}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def load(job: str) -> dict:
    try:
        return json.loads(_path(job).read_text())
    except (OSError, ValueError):
        return {"job": job, "streak": 0, "digest": None, "tripped": False}


def save(job: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _path(job).write_text(json.dumps(state, indent=2) + "\n")


def should_skip(job: str) -> tuple[bool, dict]:
    """Ask before doing the expensive thing. Cheap: reads one small file."""
    state = load(job)
    return bool(state.get("tripped")), state


def record(job: str, outcome: dict, healthy: bool) -> dict:
    """Log one run and return the updated state.

    A healthy run clears everything. That is the only automatic reset: the job
    itself demonstrating it works is the one piece of evidence worth trusting.
    """
    state = load(job)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if healthy:
        return _write(job, {"job": job, "streak": 0, "digest": None,
                            "tripped": False, "last_ok": now})

    digest = fingerprint(outcome)
    if digest == state.get("digest"):
        state["streak"] = state.get("streak", 0) + 1
    else:
        state["streak"] = 1
        state["digest"] = digest

    state["last_fail"] = now
    if state["streak"] >= THRESHOLD and not state.get("tripped"):
        state["tripped"] = True
        state["tripped_at"] = now
        state["reason"] = (
            f"{state['streak']} consecutive runs failed identically "
            f"(fingerprint {digest}). Suspended to stop spending capacity on a "
            f"result already known. Reset with: python3 fleet/bin/breaker.py "
            f"--reset {job}"
        )
    return _write(job, state)


def _write(job: str, state: dict) -> dict:
    save(job, state)
    return state


def reset(job: str) -> dict:
    return _write(job, {"job": job, "streak": 0, "digest": None, "tripped": False,
                        "reset_at": datetime.now(timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ")})


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Inspect or reset a circuit breaker.")
    ap.add_argument("--reset", metavar="JOB", help="clear a tripped breaker")
    ap.add_argument("--status", metavar="JOB", help="show one breaker's state")
    args = ap.parse_args()

    if args.reset:
        print(json.dumps(reset(args.reset), indent=2))
    elif args.status:
        print(json.dumps(load(args.status), indent=2))
    else:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        found = sorted(STATE_DIR.glob("breaker-*.json"))
        if not found:
            print("no breakers have run yet")
        for f in found:
            s = json.loads(f.read_text())
            mark = "TRIPPED" if s.get("tripped") else f"streak {s.get('streak', 0)}"
            print(f"{s.get('job'):20} {mark}")
