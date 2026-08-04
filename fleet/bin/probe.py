#!/usr/bin/env python3
"""Probe the agent runtimes that manage their own lifecycle.

Hermes and OpenClaw already run under their own launch agents and keep their own
state, so making them "fleet workers" means reading what they already publish —
not wrapping them or taking over their scheduling. Each probe is read-only and
time-bounded so a hung runtime slows the board rather than hanging it.
"""

import json
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERMES = Path.home() / ".hermes"
OPENCLAW_PORT = 18789
TIMEOUT = 2


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_json(url):
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode(errors="replace"))
    except Exception:
        return None


def pid_alive(pid):
    try:
        return subprocess.run(["ps", "-p", str(pid)], capture_output=True,
                              timeout=TIMEOUT).returncode == 0
    except Exception:
        return False


def uptime(pid):
    try:
        r = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=TIMEOUT)
        return r.stdout.strip() or "?"
    except Exception:
        return "?"


def count_procs(pattern):
    try:
        r = subprocess.run(["pgrep", "-f", pattern], capture_output=True,
                           text=True, timeout=TIMEOUT)
        return len([l for l in r.stdout.splitlines() if l.strip()])
    except Exception:
        return 0


def probe_openclaw():
    health = http_json(f"http://127.0.0.1:{OPENCLAW_PORT}/health")
    pids = subprocess.run(["pgrep", "-f", "openclaw/dist/index.js gateway"],
                          capture_output=True, text=True)
    pid = next((l for l in pids.stdout.split() if l.strip()), None)

    if health and health.get("ok"):
        status, summary = "pass", f'gateway live on :{OPENCLAW_PORT}'
    elif pid:
        status, summary = "alert", "process up but /health not responding"
    else:
        status, summary = "fail", "gateway not running"

    return {
        "worker": "openclaw", "kind": "runtime",
        "target": f"http://127.0.0.1:{OPENCLAW_PORT}",
        "last_run": now(), "status": status, "summary": summary,
        "metrics": [("state", (health or {}).get("status", "down")),
                    ("uptime", uptime(pid) if pid else "-"),
                    ("port", OPENCLAW_PORT)],
        "note": "Message router — reaches you on chat platforms. Manages its own launch agent.",
        "digest": None,
    }


def probe_hermes():
    if not HERMES.exists():
        return None

    state = {}
    try:
        state = json.loads((HERMES / "gateway_state.json").read_text())
    except Exception:
        pass

    pid = state.get("pid")
    alive = pid_alive(pid) if pid else False

    def count(sub, pat="*"):
        try:
            return len(list((HERMES / sub).glob(pat)))
        except OSError:
            return 0

    jobs = 0
    try:
        d = json.loads((HERMES / "cron" / "jobs.json").read_text())
        jobs = len(d if isinstance(d, list) else d.get("jobs", []))
    except Exception:
        pass

    platforms = state.get("platforms", {}) or {}
    connected = [k for k, v in platforms.items() if (v or {}).get("state") == "connected"]

    # Workers that outlive their session accumulate silently; nothing else on the
    # machine reports them, which is precisely why the board should.
    orphans = count_procs("tui_gateway.slash_worker")

    if not alive:
        status, summary = "fail", "gateway not running"
    elif orphans >= 10:
        status = "alert"
        summary = f"gateway up, but {orphans} leaked worker processes"
    else:
        status = "pass"
        summary = "gateway up" + (f" · {', '.join(connected)}" if connected else "")

    return {
        "worker": "hermes", "kind": "runtime",
        "target": str(HERMES),
        "last_run": now(), "status": status, "summary": summary,
        "metrics": [("uptime", uptime(pid) if alive else "-"),
                    ("skills", count("skills")),
                    ("cron jobs", jobs),
                    ("stray procs", orphans)],
        "note": ("Local agent with its own skill store. "
                 + (f"Leaked workers reclaim with: pkill -f tui_gateway.slash_worker"
                    if orphans >= 10 else "Manages its own launch agent.")),
        "digest": None,
    }


def freshness(workers, config_path=None):
    """Mark a worker stale when its own schedule says it should have run by now.

    Claude raised this in council: `agent-comms-full` read `pass` while its last
    run was 75 minutes old and its sibling fired every 17. A `pass` with no
    freshness qualifier is the most dangerous state on the board — a worker that
    stopped looks exactly like one that is healthy. The status is not wrong, it
    is just stating something it last verified an hour ago.
    """
    import json as _json
    from datetime import datetime, timezone as _tz

    root = Path(__file__).resolve().parent.parent
    expected = {}
    try:
        cfg = _json.loads((config_path or (root / "config.json")).read_text())
        expected["agent-comms"] = cfg["heartbeat"]["every_seconds"]
        expected["agent-comms-full"] = cfg["full_check"]["every_seconds"]
        for w in ("command-control-dashboard",):
            expected[w] = cfg["watchdogs"]["every_seconds"]
    except Exception:
        return workers

    now = datetime.now(_tz.utc)
    for w in workers:
        every = expected.get(w.get("worker"))
        last = w.get("last_run")
        if not every or not last:
            continue
        try:
            t = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        except ValueError:
            continue
        age = (now - t).total_seconds()
        # Twice the interval: one missed run is scheduling jitter, two is a stop.
        if age > every * 2 and w.get("status") == "pass":
            w["status"] = "skip"
            w["summary"] = (f"stale — last ran {int(age // 60)}m ago, "
                            f"expected every {every // 60}m · {w.get('summary','')}")[:200]
    return workers


def probe_all():
    out = []
    for fn in (probe_hermes, probe_openclaw):
        try:
            w = fn()
            if w:
                out.append(w)
        except Exception:
            pass
    return out


# Probing costs about 1.4 seconds per runtime — pgrep walks the whole process
# table and each health check is a network round trip. Paying that inside a page
# render made the board the slowest thing in the system. Serve the last answer
# immediately and refresh it behind the request instead: a status board that
# already reloads on a timer does not need a reading fresher than MAX_AGE.
MAX_AGE = 20
_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()
_refreshing = False


def _refresh():
    global _refreshing
    try:
        data = probe_all()
        with _lock:
            _cache["data"], _cache["at"] = data, time.monotonic()
    finally:
        with _lock:
            _refreshing = False


def probe_all_cached(max_age=MAX_AGE):
    """The cached probe. Never blocks once warm, even when a runtime is hung."""
    global _refreshing
    with _lock:
        data, age = _cache["data"], time.monotonic() - _cache["at"]
        stale = data is None or age > max_age
        # The first caller of a cold cache waits; everyone after gets an answer
        # now and a fresher one next time.
        if stale and data is not None and not _refreshing:
            _refreshing = True
            start = True
        else:
            start = False
    if start:
        threading.Thread(target=_refresh, daemon=True).start()
        return data
    if data is None:
        _refresh()
        with _lock:
            return _cache["data"] or []
    return data


if __name__ == "__main__":
    print(json.dumps(probe_all(), indent=2))
