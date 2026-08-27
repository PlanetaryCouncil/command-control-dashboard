"""Fleet uplink: read-only view of the agent fleet running on this machine.

The fleet (./fleet, same repo) owns its own scheduling, guards and git
history. The cockpit only *reads* what it publishes, so nothing here can start,
stop or modify a worker — the cockpit is the instrument panel, not the engine.

Absent fleet directory is a normal state, not an error: this repo has to run on
a machine that has never had a fleet.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Same repo: app/ and fleet/ are siblings, so this survives the repo moving.
FLEET_DEFAULT = Path(__file__).resolve().parent.parent.parent / "fleet"

# Event levels the cockpit understands. Anything else is shown as "info" rather
# than trusted verbatim.
LEVELS = {"info", "ok", "warn", "error", "needs_you"}
_HOME_PATH = re.compile(r"(?:^|[\s\"'=:(])/(?:Users|home)/")
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


def _public_text(value: Any, limit: int) -> str:
    """Return public display text without host-specific locations."""
    text = str(value or "")[:limit]
    if _HOME_PATH.search(text):
        return ""
    for match in _IPV4.finditer(text):
        try:
            address = ipaddress.ip_address(match.group())
        except ValueError:
            continue
        if address.is_private or address.is_loopback or address.is_link_local:
            return ""
    return text


def fleet_path() -> Path:
    return Path(os.environ.get("FLEET_PATH", FLEET_DEFAULT)).expanduser()


def ring(agent: str, level: str, msg: str) -> None:
    """The one write this module makes: a doorbell.

    When something arrives from outside — a node pairs, a signed signal
    lands — it appends one line to the fleet's events.jsonl, in the same
    shape fleet/bin/events.py writes, so arrivals surface in the board's
    live stream as well as the cockpit's own event log. Best-effort, never
    raises.
    """
    log = fleet_path() / "events.jsonl"
    if level not in LEVELS:
        level = "info"
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "agent": str(agent)[:60], "level": level, "msg": str(msg)[:400]}
    try:
        with log.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
    except OSError:
        pass


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def _age_seconds(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - t).total_seconds())


# Same thresholds as the fleet board. Six hours behind the freshest check is
# "someone should look"; a full day is no longer a result, it is silence.
# Relative to the fleet, not the wall clock, so a machine that slept ages
# every card together instead of lighting the whole dashboard.
STALE_AFTER_S = 6 * 3600
DEAD_AFTER_S = 24 * 3600


def _when(iso) -> datetime | None:
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def stale_hours(workers: list[dict]) -> dict[str, int]:
    """worker name -> whole hours behind the freshest last_run, when far behind."""
    stamps = {}
    for w in workers:
        t = _when(w.get("last_run"))
        name = w.get("name")
        if t and name:
            stamps[name] = t
    if not stamps:
        return {}
    newest = max(stamps.values())
    return {name: int((newest - t).total_seconds() // 3600)
            for name, t in stamps.items()
            if (newest - t).total_seconds() > STALE_AFTER_S}


def warn_stale(workers: list[dict], lags: dict[str, int]) -> list[dict]:
    """A worker that has not run is not passing.

    The cockpit used to paint the last on-disk status as current, so a
    command-control-dashboard card that last wrote `pass` on 2026-08-07
    stayed green for ten days. The board already downgrades that; this
    is the same rule on the instrument panel the public actually reads.
    fail/alert keep their louder status. busy/thinking are claims about
    right now, so they are never overwritten.
    """
    for w in workers:
        lag_h = lags.get(w.get("name"))
        if lag_h is None:
            continue
        w["stale_hours"] = lag_h
        if w.get("status") != "pass":
            continue
        w["status"] = "stale" if lag_h * 3600 >= DEAD_AFTER_S else "warn"
    return workers


def workers(root: Path | None = None) -> list[dict]:
    """Every worker the fleet publishes, worst status first."""
    root = root or fleet_path()
    out: list[dict] = []

    wdir = root / "workers"
    if wdir.is_dir():
        for p in sorted(wdir.glob("*.json")):
            w = _read_json(p)
            if not isinstance(w, dict):
                continue
            out.append({
                "name": _public_text(w.get("worker", p.stem), 60),
                "kind": _public_text(w.get("kind", "worker"), 20),
                "status": str(w.get("status", "idle"))[:12],
                "summary": _public_text(w.get("summary", ""), 200),
                "last_run": w.get("last_run"),
                "age_s": _age_seconds(w.get("last_run")),
                "digest": w.get("digest"),
            })

    # The self-improvement loop predates the worker protocol and keeps its state
    # as plain logs, so it is adapted here rather than made to write a second file.
    si = root.parent / "self-improve"
    if si.is_dir():
        def count(rel: str) -> int:
            try:
                return len([l for l in (si / rel).read_text(errors="replace").splitlines() if l.strip()])
            except OSError:
                return 0

        cycles, applied = count("state/cycles.log"), count("state/applied.jsonl")
        rejected, breaches = count("state/rejected.jsonl"), count("state/violations.log")
        out.append({
            "name": "self-improve", "kind": "learner",
            "status": "alert" if breaches else ("pass" if cycles else "idle"),
            "summary": f"{cycles} cycles · {applied} applied · {rejected} refuted",
            "last_run": None, "age_s": None, "digest": None,
        })

    warn_stale(out, stale_hours(out))

    # `stale` sits with the failures: a check that has not run in a day is
    # not a minor note. `warn` is the six-hour laggard, still not green.
    rank = {"fail": 0, "stale": 1, "alert": 2, "warn": 3,
            "thinking": 4, "busy": 5, "skip": 6, "pass": 7, "idle": 8}
    return sorted(out, key=lambda w: (rank.get(w["status"], 7), w["name"]))


def events(limit: int = 40, root: Path | None = None) -> list[dict]:
    """Most recent fleet events, oldest first."""
    root = root or fleet_path()
    log = root / "events.jsonl"
    try:
        lines = log.read_text(errors="replace").splitlines()
    except OSError:
        return []

    out: list[dict] = []
    for line in lines[-max(1, limit):]:
        e = None
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(e, dict):
            continue
        lvl = e.get("level")
        out.append({
            "ts": e.get("ts"),
            "agent": _public_text(e.get("agent", "?"), 60),
            "level": lvl if lvl in LEVELS else "info",
            "msg": _public_text(e.get("msg", ""), 240),
        })
    return out


def blocked(evts: list[dict]) -> list[dict]:
    """Agents currently waiting on a human.

    A needs_you stays raised until that same agent reports ok, so the cockpit
    shows a standing alarm rather than a moment that scrolled past.
    """
    raised: dict[str, str] = {}
    for e in evts:
        if e["level"] == "needs_you":
            raised[e["agent"]] = e["msg"]
        elif e["level"] == "ok":
            raised.pop(e["agent"], None)
    return [{"agent": a, "msg": m} for a, m in raised.items()]


def snapshot(root: Path | None = None) -> dict:
    root = root or fleet_path()
    evts = events(root=root)
    ws = workers(root=root)
    return {
        "present": root.is_dir(),
        # This payload is public. The absolute install path identifies the
        # operator account and host layout without helping a remote reader.
        "path": root.name or "fleet",
        "workers": ws,
        "events": evts,
        "blocked": blocked(evts),
        "counts": {
            "total": len(ws),
            "healthy": sum(1 for w in ws if w["status"] == "pass"),
            "attention": sum(1 for w in ws
                             if w["status"] in ("fail", "alert", "stale")),
        },
    }
