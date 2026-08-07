"""The build gate: which machine compiles, and what stays on when it doesn't.

Every box in the fleet keeps every capability. The gate only answers "should
this one spend its cores compiling", so the tests that matter are: the default
is ON (a missing file must never silence the fleet), the state survives a
round trip, and turning it off stops building WITHOUT stopping the proposing,
testing and reviewing that make a proposal worth building.
"""

import importlib
import json
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))


@pytest.fixture
def gate(tmp_path, monkeypatch):
    import buildgate
    importlib.reload(buildgate)
    monkeypatch.setattr(buildgate, "STATE", tmp_path / "build-gate.json")
    return buildgate


def test_default_is_on_with_no_state_file(gate):
    """A fleet that stops improving itself because a file went missing is
    worse than one that builds on a slow box."""
    assert not gate.STATE.exists()
    assert gate.enabled() is True
    assert "default" in gate.read()["reason"]


def test_off_then_on_round_trips(gate):
    rec = gate.set_enabled(False, by="board", reason="NUC is faster")
    assert rec["enabled"] is False
    assert gate.enabled() is False
    assert gate.read()["reason"] == "NUC is faster"
    assert gate.set_enabled(True)["enabled"] is True
    assert gate.enabled() is True


def test_record_names_the_machine_and_the_moment(gate):
    """Per-machine state. "Building is off" is meaningless without which box."""
    rec = gate.set_enabled(False, by="cli")
    assert rec["host"] == gate.host()
    assert rec["by"] == "cli"
    assert rec["ts"].endswith("+00:00")


def test_corrupt_state_falls_back_to_on(gate):
    gate.STATE.parent.mkdir(parents=True, exist_ok=True)
    gate.STATE.write_text("{not json at all")
    assert gate.enabled() is True


def test_written_state_is_readable_json(gate):
    gate.set_enabled(False, by="board", reason="handed to nuc")
    d = json.loads(gate.STATE.read_text())
    assert d["enabled"] is False and d["by"] == "board"


def test_gate_only_guards_building(gate, monkeypatch):
    """Turning building off must leave verify and revise running: a machine
    that handed compiling to its brother still finishes and judges its own
    work. Asserted against the source so a future edit that moves the gate
    above the verify loop fails here rather than silently in production."""
    src = (BIN / "pipeline.py").read_text()
    gate_at = src.index("buildgate.enabled()")
    assert src.index("verify(r)") < gate_at, "verify must run before the gate"
    assert src.index("revise(r)") < gate_at, "revise must run before the gate"
    assert src.index("_picked_items()", gate_at) > gate_at, \
        "building must be gated"
