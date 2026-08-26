"""A logged brain fart has to reach /brainfarts.json, or the feed is theatre."""

import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.main import app

BIN = Path(__file__).resolve().parent.parent / "fleet" / "dormant"
spec = importlib.util.spec_from_file_location("brainfart", BIN / "brainfart.py")
brainfart = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brainfart)

client = TestClient(app)


def test_a_logged_fart_is_served_as_json(monkeypatch):
    """The script appends one line; the route serves that object. One path,
    no second store — otherwise the fleet writes and the site still draws
    from a hand-curated gallery."""
    monkeypatch.setattr(brainfart, "LOG", main.BRAINFARTS_PATH)

    empty = client.get("/brainfarts.json")
    assert empty.status_code == 200
    assert empty.json() == []

    rec = brainfart.emit(
        agent="claude",
        claim="the suite is green",
        reality="14 tests failed",
        confidence=5, wrongness=4, consequence=3, recoverability=5,
        source="watchdog",
    )
    assert rec["agent"] == "claude"
    assert rec["claim"] == "the suite is green"
    assert rec["reality"] == "14 tests failed"
    assert rec["axes"] == {
        "confidence": 5, "wrongness": 4,
        "consequence": 3, "recoverability": 5,
    }
    assert rec["source"] == "watchdog"
    assert rec["ts"]

    body = client.get("/brainfarts.json").json()
    assert body == [rec]
    line = main.BRAINFARTS_PATH.read_text().strip()
    assert line == json.dumps(rec)
