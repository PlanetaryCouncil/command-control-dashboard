"""Heavy work lives on the NUC. This box keeps the board.

Default ON so a missing file never silences a machine that should think.
Off on Gaia unloads council/rota/heartbeat without touching the NUC's
copy of config.json.
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
    import heavygate
    importlib.reload(heavygate)
    monkeypatch.setattr(heavygate, "STATE", tmp_path / "heavy-gate.json")
    return heavygate


def test_default_is_on_with_no_state_file(gate):
    assert not gate.STATE.exists()
    assert gate.enabled() is True
    assert "default" in gate.read()["reason"]


def test_off_then_on_round_trips(gate):
    rec = gate.set_enabled(False, by="cli", reason="NUC does the sitting")
    assert rec["enabled"] is False
    assert gate.enabled() is False
    assert gate.read()["reason"] == "NUC does the sitting"
    assert gate.set_enabled(True)["enabled"] is True


def test_record_names_the_machine(gate):
    rec = gate.set_enabled(False, by="cli")
    assert rec["host"] == gate.host()
    assert rec["ts"].endswith("+00:00")


def test_corrupt_state_falls_back_to_on(gate):
    gate.STATE.parent.mkdir(parents=True, exist_ok=True)
    gate.STATE.write_text("{not json")
    assert gate.enabled() is True


def test_jobs_list_is_the_launchd_heavy_set(gate):
    jobs = set(gate.JOBS)
    assert "re.genesis.council" in jobs
    assert "re.genesis.rota" in jobs
    assert "re.genesis.comms-heartbeat" in jobs
    assert "re.genesis.board-medic" not in jobs


def test_apply_config_honours_the_gate():
    src = (BIN / "apply-config.sh").read_text()
    assert "heavygate" in src
    assert "re.genesis.council" in src
