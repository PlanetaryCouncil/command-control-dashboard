"""A signature has to be earned, stable, and different per agent.

The claim the whole feature rests on is that an agent's working rhythm has a
shape — so the failure modes that matter are not crashes. They are: two agents
getting the same mark (then it is a decoration, not a signature), a mark that
changes when nothing happened (then it cannot be checked), and a mark that
survives an agent doing more work (then it is a name badge, not a record).
"""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "signature.py"
spec = importlib.util.spec_from_file_location("signature", BIN)
signature = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signature)


def write_events(tmp_path, rows):
    p = tmp_path / "events.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def trace(agent, n, gap_s=60, seconds=None, level="info", start=None):
    t0 = start or datetime(2026, 8, 1, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        e = {"ts": (t0 + timedelta(seconds=i * gap_s)).isoformat().replace("+00:00", "Z"),
             "agent": agent, "level": level, "msg": f"{agent} {i}"}
        if seconds is not None:
            e["seconds"] = seconds
        out.append(e)
    return out


def test_two_rhythms_do_not_collide(tmp_path):
    """A steady hourly worker and a bursty one must not share a mark."""
    rows = trace("steady", 40, gap_s=3600) + trace("bursty", 40, gap_s=3)
    sigs = {s["agent"]: s["seed"] for s in signature.signatures(write_events(tmp_path, rows))}
    assert sigs["steady"] != sigs["bursty"]


def test_effort_changes_the_mark(tmp_path):
    """Same rhythm, different amount of work — different signature."""
    rows = trace("quick", 30, seconds=2) + trace("slow", 30, seconds=280)
    sigs = {s["agent"]: s["seed"] for s in signature.signatures(write_events(tmp_path, rows))}
    assert sigs["quick"] != sigs["slow"]


def test_the_same_history_gives_the_same_seed(tmp_path):
    """Determinism is what makes a signature checkable rather than pretty."""
    p = write_events(tmp_path, trace("claude", 25))
    first = signature.signatures(p)[0]["seed"]
    second = signature.signatures(p)[0]["seed"]
    assert first == second


def test_more_work_moves_the_mark(tmp_path):
    """A mark is the accumulated shape of the work, not an identity assigned once."""
    before = signature.signatures(write_events(tmp_path, trace("hermes", 20)))[0]["seed"]
    after = signature.signatures(write_events(tmp_path, trace("hermes", 40)))[0]["seed"]
    assert before != after


def test_too_few_strokes_is_not_a_signature(tmp_path):
    rows = trace("newborn", 3) + trace("established", 30)
    names = [s["agent"] for s in signature.signatures(write_events(tmp_path, rows))]
    assert names == ["established"]


def test_a_long_history_is_thinned_not_truncated(tmp_path):
    """Keep the ends. A mark that drops the last month is a stale mark."""
    rows = trace("busy", 1200, gap_s=30)
    sig = signature.signatures(write_events(tmp_path, rows))[0]
    assert len(sig["points"]) == signature.MAX_POINTS
    assert sig["points"][0]["x"] == pytest.approx(0.0, abs=1e-6)
    assert sig["points"][-1]["x"] > 0.99, "the most recent work fell off the end"


def test_missing_fleet_is_a_normal_state(tmp_path):
    """This repo must run on a machine that has never had a fleet."""
    assert signature.signatures(tmp_path / "nope.jsonl") == []


def test_the_path_carries_effort_and_alternates_sides(tmp_path):
    """One-sided traces fold into a fan; crossing is what reads as handwriting."""
    pts = signature.path_for(trace("x", 10, seconds=100))
    assert any(p["y"] > 0 for p in pts) and any(p["y"] < 0 for p in pts)
