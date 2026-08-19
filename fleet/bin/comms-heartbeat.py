#!/usr/bin/env python3
"""Agent-comms heartbeat: can the agents still pass a message to each other?

Runs a short plus-one relay and publishes the result as a fleet worker, so a
break in agent-to-agent communication shows up on the board next to a failing
test suite.

Ollama is excluded by default. It passes messages fine but miscopies digits on
this hardware (observed 19211 -> 19312), and a monitor that cries wolf gets
ignored. Include it explicitly with --agents if you want to track that.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FLEET / "bin"))

import breaker        # noqa: E402
import events as ev   # noqa: E402
import plusone        # noqa: E402

def last_signal(worker_file):
    """When this check last actually completed, whatever it is doing now.

    A worker that is busy or thinking has not stopped existing; it just has
    nothing new to say yet. Carrying the previous timestamp forward keeps the
    staleness maths honest - if the deferral goes on for two days, the card
    still ages into red, because two days of "too busy to check" is a real
    problem even though no single deferral was.
    """
    try:
        return json.loads(worker_file.read_text()).get("last_run")
    except (OSError, ValueError, AttributeError):
        return None


def say(worker_file, name, status, summary, target):
    """Publish a state that is not a result: busy, thinking, deferred.

    The board used to show `fail` for a check the system had deliberately
    declined to run, which is the same lie a stale green tells, only inverted.
    """
    worker_file.parent.mkdir(parents=True, exist_ok=True)
    worker_file.write_text(json.dumps({
        "worker": name, "kind": "heartbeat", "target": target,
        "last_run": last_signal(worker_file),
        "status": status, "summary": summary,
        "detail": "", "digest": None,
        "tests_passed": 0, "tests_failed": 0, "duration_s": 0.0,
    }, indent=2))


def worker_path(name):
    return FLEET / "workers" / f"{name}.json"


def _acquire_lock(name):
    """Refuse to start if a previous run is still going.

    The check is a wall-clock guard, not an interval guard: when a run takes
    longer than its schedule, launchd will happily start another and they pile
    up until the machine is doing nothing else.
    """
    lock = FLEET / "logs" / f".{name}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        if lock.exists():
            pid = int(lock.read_text().strip() or 0)
            try:
                os.kill(pid, 0)
                return None            # still alive
            except (ProcessLookupError, ValueError):
                pass                   # stale, reclaim it
        lock.write_text(str(os.getpid()))
        return lock
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="claude,hermes,openclaw")
    ap.add_argument("--laps", type=int, default=1)
    ap.add_argument("--name", default="agent-comms",
                    help="worker name, so tiers report separately")
    a = ap.parse_args()

    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    import quotas
    agents = quotas.eligible(agents)
    if not agents:
        print(f"{a.name}: no eligible agents (dry or rare); skipping")
        return 0
    WORKER = worker_path(a.name)

    # One relay at a time across ALL tiers. The per-name lock let agent-comms
    # and agent-comms-full start a second apart, so an agent held two plus-one
    # values from games it could not tell apart — which would look like a comms
    # failure rather than a scheduling one. Found by the council.
    lock = _acquire_lock("plusone-any")
    if lock is None:
        print(f"{a.name}: previous run still going; skipping")
        return 0
    # Do not start a 960-second job into a saturated machine. Measured
    # 2026-08-02: the relay degraded 3/3 -> 2/3 -> 1/3 across five hours while
    # load climbed to 20 on four cores, and every one of those misses was
    # recorded as an agent failing to pass a message. It was not. The check
    # costs 2.4 microseconds.
    import pressure
    snap = pressure.snapshot()
    max_load = snap["max_load"]
    load1 = snap["load1"]
    if snap["hot"]:
        ev.emit(a.name, "warn",
                f"[relay] deferred — load {load1:.1f} over {max_load:.0f} on "
                f"{os.cpu_count()} cores; a timeout here would be the machine, "
                f"not the agents")
        say(WORKER, a.name, "busy",
            f"deferred — load {load1:.1f} over {max_load:.0f} on "
            f"{os.cpu_count()} cores; a timeout now would measure the machine, "
            f"not the agents",
            "plus-one relay · waiting for a quiet moment")
        print(f"{a.name}: load {load1:.1f} > {max_load}; deferring")
        lock.unlink(missing_ok=True)
        return 0

    # Ask before paying. Reading this file costs microseconds; the relay it
    # guards costs ~16 minutes of a four-core machine. Proposed by the council
    # after three runs produced byte-identical failures.
    tripped, bstate = breaker.should_skip(a.name)
    if tripped:
        WORKER.parent.mkdir(parents=True, exist_ok=True)
        WORKER.write_text(json.dumps({
            "worker": a.name, "kind": "heartbeat",
            "target": "plus-one relay · SUSPENDED",
            "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            # Louder than the failures it replaces. A job that quietly stopped
            # running is the worst outcome available — suspended must never read
            # as calm.
            "status": "fail",
            "summary": f"relay suspended — {bstate.get('reason', 'breaker tripped')}",
            "detail": json.dumps(bstate)[:1500], "digest": bstate.get("digest"),
            "tests_passed": 0, "tests_failed": 0,
            "duration_s": 0.0,
        }, indent=2))
        ev.emit(a.name, "needs_you",
                f"[relay] suspended after {bstate.get('streak')} identical failures "
                f"— reset with: python3 fleet/bin/breaker.py --reset {a.name}")
        print(f"{a.name}: breaker tripped; skipping")
        lock.unlink(missing_ok=True)
        return 0

    # The relay takes minutes. Without this the card showed the previous run's
    # result the whole time it was working, so a check in progress was
    # indistinguishable from a check that had not started.
    say(WORKER, a.name, "thinking",
        f"relaying now — {len(agents)} agents, {a.laps} lap(s); "
        f"this takes a few minutes",
        "plus-one relay · in flight")

    started = time.time()

    try:
        res = plusone.play(agents, laps=a.laps)
    except Exception as e:                      # a crash is itself a red signal
        WORKER.parent.mkdir(parents=True, exist_ok=True)
        WORKER.write_text(json.dumps({
            "worker": a.name, "kind": "heartbeat",
            "target": "plus-one relay",
            "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "fail", "summary": f"heartbeat crashed: {e}",
            "detail": str(e)[:500], "digest": None,
            "tests_passed": 0, "tests_failed": 1,
            "duration_s": round(time.time() - started, 1),
        }, indent=2))
        ev.emit(a.name, "needs_you", f"comms heartbeat crashed: {e}")
        return 1

    ok, total = res["correct"], res["total"]
    if ok == total:
        status = "pass"
    elif ok == 0:
        status = "fail"          # nothing got through at all
    else:
        status = "alert"         # partial: someone is dropping or fumbling

    bstate = breaker.record(a.name, {"status": status, "hops": res["hops"]},
                            healthy=(status == "pass"))

    # "missed: hermes lap1 (92659->None)" could not say whether hermes was
    # slow or gone — the outcome word ("slow" vs "timeout" vs "silent") is
    # the split the board was missing.
    misses = [f"{h['agent']} lap{h['lap']} "
              f"({h['received']}->{h['got']}, {h['outcome']})"
              for h in res["hops"] if not h["ok"]]
    # Per-agent latency, not just correctness: hermes runs ~4x slower than claude
    # and the old summary made a healthy-but-slow agent invisible.
    per = {}
    for h in res["hops"]:
        per.setdefault(h["agent"], []).append(h["seconds"])
    timing = " · ".join(f"{a} {max(v):.0f}s" for a, v in per.items())
    summary = (f"{ok}/{total} hops · {timing}"
               + (f" · missed: {'; '.join(misses)}" if misses else "")
               + (f" · identical failure {bstate['streak']}x"
                  if bstate.get("streak", 0) > 1 else ""))

    WORKER.parent.mkdir(parents=True, exist_ok=True)
    WORKER.write_text(json.dumps({
        "worker": a.name, "kind": "heartbeat",
        "target": f"plus-one relay · {res['start']} -> {res['final']}",
        "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status, "summary": summary,
        "detail": json.dumps(res["hops"])[:1500], "digest": None,
        "tests_passed": ok, "tests_failed": total - ok,
        "duration_s": round(time.time() - started, 1),
    }, indent=2))

    # Only a total failure is worth waking someone for; a single fumbled digit
    # is a warning, not an emergency.
    if status == "fail":
        ev.emit(a.name, "needs_you", f"agents cannot pass a message: {summary}")
    elif status == "alert":
        ev.emit(a.name, "warn", summary)
    else:
        ev.emit(a.name, "ok", summary)

    try:
        lock.unlink(missing_ok=True)
    except OSError:
        pass
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
