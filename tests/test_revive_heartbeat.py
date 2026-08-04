"""The watchdog restarts the heartbeat it watches.

On 2026-08-04 agent-comms had been silent for 19 hours; a watchdog sweep ran,
reported the board green (258 passed), and left the dead heartbeat dead. The
staleness was already detected twice over — what was missing was the repair.
These tests run revive-heartbeat.sh against a fake `launchctl` on PATH, so the
restart decision is pinned without touching the real launchd job.
"""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
REVIVE = BIN / "revive-heartbeat.sh"


@pytest.fixture
def fake_launchctl(tmp_path):
    """Scriptable `launchctl` first on PATH, plus an events.py stub.

    The events stub matters: the fleet watchdog runs this suite hourly, and
    without it every test run would append fake "kickstarted" warns to the
    live event log — the exact pollution conftest.py exists to prevent.
    """
    binder = tmp_path / "bin"
    binder.mkdir()
    calls = tmp_path / "calls.txt"
    stub = binder / "launchctl"
    stub.write_text(f'#!/bin/sh\necho "launchctl $@" >> {calls}\nexit 0\n')
    stub.chmod(0o755)

    events = tmp_path / "events_stub.py"
    events.write_text(
        "import sys\n"
        f"with open({str(tmp_path / 'events.txt')!r}, 'a') as fh:\n"
        "    fh.write(' '.join(sys.argv[1:]) + '\\n')\n")

    env = dict(os.environ,
               PATH=f"{binder}:{os.environ['PATH']}",
               EVENTS_PY=str(events))
    return env, calls, tmp_path / "events.txt"


def worker_json(tmp_path, age: timedelta) -> Path:
    p = tmp_path / "agent-comms.json"
    stamp = (datetime.now(timezone.utc) - age).strftime("%Y-%m-%dT%H:%M:%SZ")
    p.write_text(json.dumps({"worker": "agent-comms", "status": "pass",
                             "last_run": stamp}))
    return p


def run_revive(env, hb_json) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(REVIVE), str(hb_json)],
                          capture_output=True, text=True, env=env, timeout=30)


def test_a_stale_heartbeat_gets_kickstarted(fake_launchctl, tmp_path):
    env, calls, events = fake_launchctl
    hb = worker_json(tmp_path, age=timedelta(hours=19))
    r = run_revive(env, hb)
    assert r.returncode == 0
    logged = calls.read_text()
    assert "kickstart -k" in logged
    assert "re.genesis.comms-heartbeat" in logged
    assert "kickstarted" in events.read_text()


def test_a_fresh_heartbeat_is_left_alone(fake_launchctl, tmp_path):
    env, calls, _ = fake_launchctl
    hb = worker_json(tmp_path, age=timedelta(minutes=30))
    r = run_revive(env, hb)
    assert r.returncode == 0
    assert not calls.exists()


def test_no_record_means_no_restart(fake_launchctl, tmp_path):
    env, calls, _ = fake_launchctl
    r = run_revive(env, tmp_path / "missing.json")
    assert r.returncode == 0
    assert not calls.exists()


def test_garbage_timestamps_do_not_trigger_a_restart(fake_launchctl, tmp_path):
    """A parse bug must stay a parse bug, not become a process restart."""
    env, calls, _ = fake_launchctl
    hb = tmp_path / "agent-comms.json"
    hb.write_text(json.dumps({"worker": "agent-comms", "last_run": "not-a-time"}))
    r = run_revive(env, hb)
    assert r.returncode == 0
    assert not calls.exists()


def test_the_sweep_calls_the_revive_script_before_the_lock_check():
    """An alive-but-stuck heartbeat can hold the plus-one lock the sweep
    defers to; revival has to run before that early exit."""
    sweep = (BIN / "run-watchdogs.sh").read_text()
    assert "revive-heartbeat.sh" in sweep
    assert sweep.index("revive-heartbeat.sh") < sweep.index("plusone-any.lock")
