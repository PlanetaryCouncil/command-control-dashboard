#!/usr/bin/env python3
"""Reboot the box when it is alive but no longer useful.

The hardware watchdog in /dev/watchdog handles a true freeze: the kernel stops
petting it and the Intel TCO chip cuts power. But there is a nastier failure in
between, and this machine has form for it — the box still answers, systemd
still runs timers, and yet nothing finishes because every process is queued
behind swap or a wedged disk. A hardware watchdog never fires there, because
the kernel is fine. It is the work that is dead.

So this measures stall, not load. Load is the wrong trigger on this box: a
legitimate ollama run pins twelve cores for minutes and must not be shot for
it. Pressure Stall Information says something different and much more useful —
what fraction of wall-clock time *every* runnable task spent waiting on memory
or IO. `full avg60 = 30` means that for the last minute, 30% of the time,
nothing could progress at all. No healthy workload does that, however heavy.

Three consecutive bad checks are needed before it acts, so a single ugly
minute is survivable. The operator is told on Telegram before the reboot, not
after, because waking up to a rebooted machine with no explanation is its own
kind of broken.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# /run is root-owned and tmpfs, which is right: strikes must not survive a
# reboot, or a box that just rebooted would arrive already one strike down.
STATE = Path(os.environ.get("STALL_WATCHDOG_STATE", "/run/stall-watchdog.state"))
STRIKES_NEEDED = 3          # x 2min timer = ~6 minutes of sustained stall
MEM_FULL_AVG60 = 20.0       # % of time all tasks stalled on memory
IO_FULL_AVG60 = 60.0        # % of time all tasks stalled on io
CPU_SOME_AVG300 = 90.0      # % of time something was waiting for cpu, 5min
GRACE_AFTER_BOOT = 900      # dont shoot a machine that is still starting up


def psi(resource, kind, field):
    """One number out of /proc/pressure/<resource>. 0.0 if PSI is unavailable."""
    try:
        for line in Path(f"/proc/pressure/{resource}").read_text().splitlines():
            parts = line.split()
            if parts and parts[0] == kind:
                for p in parts[1:]:
                    k, _, v = p.partition("=")
                    if k == field:
                        return float(v)
    except (OSError, ValueError):
        pass
    return 0.0


def save_strikes(n):
    """Best effort. Losing the counter costs a delayed reboot, not a wrong one."""
    try:
        STATE.write_text(json.dumps({"strikes": n}))
    except OSError as e:
        print(f"could not write {STATE}: {e}", file=sys.stderr)


def uptime():
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError):
        return 1e9


def diagnose():
    """Return (unhealthy, reasons). Any one signal is enough to take a strike."""
    mem = psi("memory", "full", "avg60")
    io = psi("io", "full", "avg60")
    cpu = psi("cpu", "some", "avg300")
    load5 = float(Path("/proc/loadavg").read_text().split()[1])

    reasons = []
    if mem > MEM_FULL_AVG60:
        reasons.append(f"memory stalled {mem:.0f}% of the last minute")
    if io > IO_FULL_AVG60:
        reasons.append(f"io stalled {io:.0f}% of the last minute")
    if cpu > CPU_SOME_AVG300:
        reasons.append(f"cpu contended {cpu:.0f}% over 5 min (load5 {load5:.1f})")
    return bool(reasons), reasons


def tell(text):
    """Best effort. A watchdog that dies because Telegram is down is useless."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import telegram
        token, allowed = telegram._load()
        for chat_id in sorted(allowed):
            telegram.send(token, chat_id, text)
    except Exception as e:
        print(f"could not notify: {e}", file=sys.stderr)


def main():
    if uptime() < GRACE_AFTER_BOOT:
        print("within boot grace, skipping")
        return 0

    unhealthy, reasons = diagnose()

    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {"strikes": 0}

    if not unhealthy:
        if state.get("strikes"):
            print(f"recovered after {state[strikes]} strike(s)")
        save_strikes(0)
        return 0

    strikes = state.get("strikes", 0) + 1
    save_strikes(strikes)
    detail = "; ".join(reasons)
    print(f"strike {strikes}/{STRIKES_NEEDED}: {detail}")

    if strikes < STRIKES_NEEDED:
        return 0

    msg = (f"nuc: rebooting. stalled for ~{STRIKES_NEEDED * 2} minutes.\n{detail}\n"
           f"the box was answering but nothing could finish.")
    print(msg)
    tell(msg)
    save_strikes(0)
    time.sleep(5)          # give the message a chance to leave
    subprocess.run(["systemctl", "reboot"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
