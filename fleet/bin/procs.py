#!/usr/bin/env python3
"""Process inspection and the kill switch.

Three rules, because this is a destructive action reachable from a browser:

1. **The browser never names a process.** It asks to kill "fleet work"; the
   server decides what that means. Accepting a PID from a page would be a
   remote-kill-anything endpoint.
2. **Scope is fleet-spawned work only.** Hermes and OpenClaw run their own
   gateways under their own launch agents — Hermes has been up for days serving
   Telegram. Those are listed but never killed here; taking them down is a
   different decision from stopping a stuck test run.
3. **The serving process excludes itself and its parent.** Otherwise the kill
   request has nobody left to answer it. Excluding only its own PID is not
   enough: when the server was started from a shell, killing that shell takes
   the server down with it.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess

# Patterns for things the fleet starts. Matched against the full command line.
FLEET_PATTERNS = [
    (r"bin/run-watchdogs\.sh", "watchdog sweep"),
    (r"bin/watchdog\.sh", "project tests"),
    (r"bin/fixer\.sh", "fix proposer"),
    (r"bin/comms-heartbeat\.py", "comms heartbeat"),
    (r"bin/plusone\.py", "plus-one relay"),
    (r"bin/game\.py", "deduction game"),
    (r"bin/blackboard\.py", "blackboard proof"),
    (r"loop/run-cycle\.sh", "self-improve cycle"),
    (r"bin/fleet\.py serve", "fleet board"),
    (r"/pytest\b", "test run"),
]

# Agent runtimes the fleet talks to but does not own. Shown, never killed.
EXTERNAL_PATTERNS = [
    (r"hermes_cli\.main gateway", "Hermes gateway"),
    (r"openclaw/dist/index\.js gateway", "OpenClaw gateway"),
    (r"tui_gateway\.slash_worker", "Hermes worker"),
    (r"llama-server|ollama", "Ollama"),
    (r"uvicorn app\.main:app", "cockpit"),
    (r"/bin/grok\b|\bgrok\b", "Grok"),
    (r"/bin/claude\b|\bclaude\b", "Claude CLI"),
]

HEAVY_MIN_MB = 40
HEAVY_TOP = 15

# Which agent a process belongs to. An agent IS a process — the board used to
# show the two as separate lists, so the same fact ("openclaw is up") appeared
# twice with no line drawn between them. Attributing the process here lets one
# pane render an agent with its own processes underneath it.
PROC_AGENT = {
    "Hermes gateway": "hermes",
    "Hermes worker": "hermes",
    "OpenClaw gateway": "openclaw",
    "Ollama": "ollama",
}


def _ps():
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,etime=,pcpu=,pmem=,rss=,command="],
            capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.strip().split(None, 6)
        if len(parts) < 7:
            continue
        pid, ppid, etime, cpu, mem, rss, cmd = parts
        try:
            rows.append({"pid": int(pid), "ppid": int(ppid), "elapsed": etime,
                         "cpu": float(cpu), "mem": float(mem),
                         "rss_kb": int(rss), "cmd": cmd})
        except ValueError:
            continue
    return rows


def _classify(cmd):
    for pat, label in FLEET_PATTERNS:
        if re.search(pat, cmd):
            return "fleet", label
    for pat, label in EXTERNAL_PATTERNS:
        if re.search(pat, cmd):
            return "external", label
    return None, None


def _protected():
    """PIDs that must survive a kill: this process and whatever launched it."""
    keep = {os.getpid()}
    try:
        keep.add(os.getppid())
    except Exception:
        pass
    return keep


def snapshot():
    """Everything worth showing, split into what we own and what we don't."""
    keep = _protected()
    fleet, external = [], []
    rows = _ps()
    for r in rows:
        kind, label = _classify(r["cmd"])
        if not kind:
            continue
        # The shell wrapper launchd uses shows up alongside the real process;
        # both are genuine, so keep them rather than guessing which matters.
        item = {"pid": r["pid"], "label": label, "agent": PROC_AGENT.get(label),
                "elapsed": r["elapsed"],
                "cpu": r["cpu"], "mem": r["mem"],
                "rss_mb": round(r["rss_kb"] / 1024, 1),
                "cmd": r["cmd"][:160],
                # Untruncated, for matching: a 160-char display cap once ate
                # "--name e2e-victim" off the end and made the scoped kill
                # blind to its own canary.
                "cmd_full": r["cmd"],
                "is_self": r["pid"] in keep}
        (fleet if kind == "fleet" else external).append(item)
    fleet.sort(key=lambda x: -x["cpu"])
    external.sort(key=lambda x: -x["cpu"])
    return {"fleet": fleet, "external": external,
            "heavies": heavies(rows),
            "killable": sum(1 for f in fleet if not f["is_self"]),
            "machine": machine()}


def _short_name(cmd: str) -> str:
    tok = (cmd or "").split()[0]
    name = tok.rsplit("/", 1)[-1]
    return (name or "proc")[:48]


def heavies(rows=None):
    """Top RAM sitters, fleet or not. Shown, never killable from here."""
    rows = rows if rows is not None else _ps()
    ranked = sorted(rows, key=lambda r: -r.get("rss_kb", 0))
    out = []
    for r in ranked:
        mb = r.get("rss_kb", 0) / 1024
        if mb < HEAVY_MIN_MB and r.get("cpu", 0) < 8:
            continue
        kind, label = _classify(r["cmd"])
        out.append({
            "pid": r["pid"],
            "label": label or _short_name(r["cmd"]),
            "kind": kind or "other",
            "rss_mb": round(mb, 1),
            "cpu": r["cpu"],
            "mem": r["mem"],
            "elapsed": r["elapsed"],
            "cmd": r["cmd"][:160],
            "cmd_full": r["cmd"],
        })
        if len(out) >= HEAVY_TOP:
            break
    return out


def machine() -> dict:
    """Is this thing working hard or chilling?

    Nothing on the board answered that. On 2026-08-02 the load average reached
    20 on four cores — five times oversubscribed, agents timing out because they
    could not be scheduled — and every surface reported it as agents failing to
    pass a message. The number that would have explained it was one syscall away
    and nobody was showing it.

    `state` is deliberately coarse. A number needs interpretation; "saturated"
    does not, and the whole failure was that nobody read the number in time.
    """
    cores = os.cpu_count() or 1
    try:
        one, five, fifteen = os.getloadavg()
    except OSError:
        return {"cores": cores, "load1": None, "state": "unknown"}

    ratio = one / cores
    state = ("idle" if ratio < 0.5 else
             "working" if ratio < 1.0 else
             "busy" if ratio < 1.5 else
             "saturated")
    return {"cores": cores,
            "load1": round(one, 2), "load5": round(five, 2),
            "load15": round(fifteen, 2),
            "per_core": round(ratio, 2), "state": state,
            # Agents are held back above this, so the board should show the same
            # line the schedulers act on rather than a second opinion.
            "gate": _load_gate(),
            "compressor_gb": round(_compressor_gb(), 1),
            "disk": _disk()}


def _load_gate() -> float:
    try:
        import pressure
        return float(pressure.max_load())
    except Exception:
        return float(os.environ.get("MAX_LOAD", os.cpu_count() or 4))


def _compressor_gb() -> float:
    try:
        import pressure
        return float(pressure.compressor_gb())
    except Exception:
        return 0.0


def _disk() -> dict:
    try:
        import pressure
        return pressure.disk()
    except Exception:
        return {}


def kill_fleet(dry_run=False, only=None):
    """SIGKILL every fleet-spawned process except this server and its parent.

    `only` narrows the blast to processes whose command line contains that
    marker. The blanket kill is the panic button and stays; the narrow form
    exists so the e2e check can prove the switch on a sacrificial canary
    instead of shooting the live heartbeat twice a day (council, 2026-08-04:
    "the e2e run tests the kill switch by firing it live").
    """
    keep = _protected()
    killed, failed = [], []
    for p in snapshot()["fleet"]:
        if p["is_self"] or p["pid"] in keep:
            continue
        if only and only not in p.get("cmd_full", p.get("cmd", "")):
            continue
        if dry_run:
            killed.append(p)
            continue
        try:
            os.kill(p["pid"], signal.SIGKILL)
            killed.append(p)
        except ProcessLookupError:
            pass                      # already gone between listing and killing
        except PermissionError as e:
            failed.append({**p, "error": str(e)})
    return {"killed": killed, "failed": failed, "dry_run": dry_run}


if __name__ == "__main__":
    import json
    import sys
    if "--kill" in sys.argv:
        print(json.dumps(kill_fleet(dry_run="--dry-run" in sys.argv), indent=2))
    else:
        s = snapshot()
        print(f"fleet ({len(s['fleet'])}, {s['killable']} killable):")
        for p in s["fleet"]:
            print(f"  {p['pid']:>7} {p['cpu']:>5}% {p['elapsed']:>12}  {p['label']}"
                  + ("  <- this server" if p["is_self"] else ""))
        print(f"external ({len(s['external'])}, never killed here):")
        for p in s["external"]:
            print(f"  {p['pid']:>7} {p['cpu']:>5}% {p['elapsed']:>12}  {p['label']}")
