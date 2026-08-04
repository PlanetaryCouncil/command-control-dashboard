"""Tests for the fleet's agent machinery.

These cover the eight faults the council found in its first three sessions. Each
test names the failure it prevents, because a test whose purpose is unclear gets
deleted the first time it becomes inconvenient.

Unit level: pure functions with fabricated inputs. No agents are spawned, no
subprocesses run, nothing touches the real fleet directory — these must stay
fast enough that the watchdog runs them every hour without noticing.
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

FLEET_BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(FLEET_BIN))

import council  # noqa: E402
import probe    # noqa: E402


def _iso(delta_minutes: float) -> str:
    t = datetime.now(timezone.utc) + timedelta(minutes=delta_minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------- freshness
def _cfg(tmp_path, heartbeat=900, full=1800, watchdog=3600):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "heartbeat": {"every_seconds": heartbeat},
        "full_check": {"every_seconds": full},
        "watchdogs": {"every_seconds": watchdog},
    }))
    return p


def test_a_stopped_worker_stops_reading_pass(tmp_path):
    """The council's sharpest finding: a silent worker looked identical to a
    healthy one, because `pass` carried no freshness qualifier."""
    workers = [{"worker": "agent-comms-full", "status": "pass",
                "summary": "3/3 hops", "last_run": _iso(-125)}]
    out = probe.freshness(workers, _cfg(tmp_path, full=1800))
    assert out[0]["status"] == "skip"
    assert "stale" in out[0]["summary"]


def test_one_missed_run_is_jitter_not_staleness(tmp_path):
    """Scheduling wobble must not raise a false alarm — only a real stop should."""
    workers = [{"worker": "agent-comms", "status": "pass",
                "summary": "2/2 hops", "last_run": _iso(-20)}]
    out = probe.freshness(workers, _cfg(tmp_path, heartbeat=900))
    assert out[0]["status"] == "pass"


def test_freshness_never_upgrades_a_failure(tmp_path):
    """A failing worker that is also fresh must stay failing."""
    workers = [{"worker": "agent-comms", "status": "fail",
                "summary": "0/2 hops", "last_run": _iso(-1)}]
    out = probe.freshness(workers, _cfg(tmp_path))
    assert out[0]["status"] == "fail"


def test_freshness_ignores_workers_with_no_known_schedule(tmp_path):
    workers = [{"worker": "something-else", "status": "pass",
                "summary": "", "last_run": _iso(-9999)}]
    assert probe.freshness(workers, _cfg(tmp_path))[0]["status"] == "pass"


def test_freshness_survives_a_missing_config(tmp_path):
    workers = [{"worker": "agent-comms", "status": "pass", "last_run": _iso(-999)}]
    out = probe.freshness(workers, tmp_path / "absent.json")
    assert out[0]["status"] == "pass"      # degrade quietly, never crash the board


# --------------------------------------------------------------- transcript
def test_transcript_drops_turns_from_an_old_session(tmp_path, monkeypatch):
    """Agents were handed points from four hours earlier — including one already
    fixed — and asked to build on them. Stale context is why the council could
    never reach its own stop condition."""
    f = tmp_path / "transcript.jsonl"
    old = {"ts": (datetime.now(timezone.utc) - timedelta(hours=9)).isoformat(),
           "run": "old", "round": 1, "agent": "claude", "text": "resolved long ago"}
    new = {"ts": datetime.now(timezone.utc).isoformat(),
           "run": "new", "round": 1, "agent": "hermes", "text": "current point"}
    f.write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n")
    monkeypatch.setattr(council, "TRANSCRIPT", f)

    got = council.transcript(max_age_hours=6)
    assert [t["run"] for t in got] == ["new"]


def test_transcript_tolerates_corrupt_lines(tmp_path, monkeypatch):
    f = tmp_path / "transcript.jsonl"
    good = {"ts": datetime.now(timezone.utc).isoformat(), "run": "r",
            "round": 1, "agent": "claude", "text": "fine"}
    f.write_text("not json\n" + json.dumps(good) + "\n{broken\n")
    monkeypatch.setattr(council, "TRANSCRIPT", f)
    assert len(council.transcript()) == 1


def test_transcript_is_empty_when_the_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(council, "TRANSCRIPT", tmp_path / "nope.jsonl")
    assert council.transcript() == []


# --------------------------------------------------------------- the council
def test_a_council_of_one_does_not_convene(monkeypatch):
    """It used to convene and adjourn with zero turns, logging coordination that
    never happened."""
    emitted = []
    monkeypatch.setattr(council.ev, "emit", lambda *a, **k: emitted.append(a))
    res = council.run(["claude"], rounds=1)
    assert res["adjourned"] == "too few participants"
    assert res["turns"] == []
    assert emitted == [], "a council that cannot happen must not log that it did"


def test_nothing_to_add_is_recognised():
    """The stop condition depends on detecting the pass phrase in real replies,
    which arrive wrapped in prose."""
    for reply in ("NOTHING TO ADD",
                  "nothing to add",
                  "After reviewing the board: NOTHING TO ADD"):
        assert council.NOTHING.search(reply)
    assert not council.NOTHING.search("I have something to add about nothing")


def test_prior_turns_reach_the_prompt_intact():
    """Turns were truncated at 400 characters, cutting claims mid-sentence so a
    later agent could not tell what had already been said."""
    long_claim = "x" * 900 + " END-OF-CLAIM"
    prompt = council.build_prompt(
        "hermes",
        {"workers": [], "event_levels": {}, "event_kinds": {}, "recent_events": []},
        [{"agent": "claude", "round": 1, "text": long_claim}])
    assert "END-OF-CLAIM" in prompt


def test_board_state_runs_without_spawning_anything():
    """Checking must stay free: the loop reads the board constantly and may only
    spend an agent turn when it has something to act on."""
    started = time.perf_counter()
    state = council.board_state()
    assert time.perf_counter() - started < 1.0
    for key in ("workers", "event_levels", "event_kinds", "recent_events"):
        assert key in state
