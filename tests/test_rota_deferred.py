"""A load-deferred rota turn is rescheduled, not dropped.

On 2026-08-03 the board showed "[rota] claude's turn deferred — load 18.6
over 6" at 18:02 and the next proposal only at 19:06 — the turn was simply
lost for an hour. Now a deferral leaves a pending marker in state/rota.json,
and `rota.py --retry-deferred` (fired by run-watchdogs.sh once its sweep
ends) takes that exact agent's turn as soon as the load gate allows.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "rota.py"
spec = importlib.util.spec_from_file_location("rota_deferred", BIN)
rota = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rota)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect every write path and stub out the machine and the agents."""
    import heavygate
    monkeypatch.setattr(heavygate, "enabled", lambda: True)
    monkeypatch.setattr(rota, "STATE", tmp_path / "rota.json")
    monkeypatch.setattr(rota, "LEDGER", tmp_path / "proposals.jsonl")
    events = []
    monkeypatch.setattr(rota.ev, "emit",
                        lambda agent, level, msg, **kw: events.append(msg))
    monkeypatch.setattr(rota.council, "board_state", lambda: {})
    asked = []
    monkeypatch.setattr(rota, "ask", lambda agent, prompt, session:
                        asked.append(agent) or "a concrete proposal")
    import quotas as quotas_mod
    monkeypatch.setattr(quotas_mod, "eligible", lambda agents, **k: agents)
    import pressure
    monkeypatch.setattr(pressure, "too_hot", lambda **k: False)
    monkeypatch.setattr(pressure, "snapshot", lambda **k: {
        "load1": 1.2, "ncpu": 4, "max_load": 4, "compressor_gb": 0.2,
        "hot": False, "reason": "ok",
    })
    return {"events": events, "asked": asked, "tmp": tmp_path}


def _hot(monkeypatch, load=18.6):
    import pressure
    monkeypatch.setattr(pressure, "too_hot", lambda **k: True)
    monkeypatch.setattr(pressure, "snapshot", lambda **k: {
        "load1": load, "ncpu": 4, "max_load": 4, "compressor_gb": 2.2,
        "hot": True, "reason": f"load {load:.1f} over 4 on 4 cores",
    })


def run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["rota.py", *argv])
    return rota.main()


def test_deferral_leaves_a_pending_marker(sandbox, monkeypatch):
    _hot(monkeypatch, 18.6)
    assert run(monkeypatch) == 0
    state = json.loads(rota.STATE.read_text())
    assert state["deferred"]["agent"] == "hermes"
    assert state["deferred"]["load"] == 18.6
    assert sandbox["asked"] == []
    assert any("retry pending" in e for e in sandbox["events"])


def test_retry_takes_the_deferred_agents_turn_and_clears_the_marker(
        sandbox, monkeypatch):
    # last=hermes would rotate to openclaw; the marker names claude, so the
    # retry proving it ran claude shows the marker wins over the rotation.
    rota.STATE.write_text(json.dumps(
        {"last": "hermes", "turns": 7,
         "deferred": {"agent": "claude", "load": 18.6,
                      "ts": "2026-08-03T18:02:10Z"}}))
    assert run(monkeypatch, "--retry-deferred",
               "--agents", "claude,hermes,openclaw") == 0
    assert sandbox["asked"] == ["claude"]
    state = json.loads(rota.STATE.read_text())
    assert "deferred" not in state
    assert state["last"] == "claude"
    record = json.loads(rota.LEDGER.read_text().splitlines()[-1])
    assert record["agent"] == "claude"


def test_retry_is_a_noop_when_nothing_is_pending(sandbox, monkeypatch):
    rota.STATE.write_text(json.dumps({"last": "claude", "turns": 3}))
    assert run(monkeypatch, "--retry-deferred") == 0
    assert sandbox["asked"] == []
    assert not rota.LEDGER.exists()


def test_retry_keeps_the_marker_while_the_machine_is_still_busy(
        sandbox, monkeypatch):
    rota.STATE.write_text(json.dumps(
        {"last": "hermes", "turns": 7,
         "deferred": {"agent": "openclaw", "load": 18.6,
                      "ts": "2026-08-03T18:02:10Z"}}))
    _hot(monkeypatch, 9.9)
    assert run(monkeypatch, "--retry-deferred") == 0
    assert sandbox["asked"] == []
    state = json.loads(rota.STATE.read_text())
    assert state["deferred"]["agent"] == "openclaw"


def test_a_completed_ordinary_turn_also_clears_a_stale_marker(
        sandbox, monkeypatch):
    rota.STATE.write_text(json.dumps(
        {"last": "claude", "turns": 3,
         "deferred": {"agent": "hermes", "load": 18.6,
                      "ts": "2026-08-03T18:02:10Z"}}))
    assert run(monkeypatch) == 0
    state = json.loads(rota.STATE.read_text())
    assert "deferred" not in state
