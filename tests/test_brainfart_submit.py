"""A brain fart is collected here; publishing it is a scored human decision."""

import importlib.util
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.main import app

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
spec = importlib.util.spec_from_file_location(
    "brainfart_submit", BIN / "brainfart_submit.py")
bfs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bfs)

client = TestClient(app)


def _scored(**kw):
    defaults = dict(
        claim="the suite is green",
        reality="14 tests failed",
        confidence=5, wrongness=4, consequence=3, recoverability=5,
        source="watchdog", agent="claude",
    )
    defaults.update(kw)
    return bfs.submit(**defaults)


def test_argv_append_is_one_published_json_line(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINFARTS_JSONL", str(tmp_path / "brainfarts.jsonl"))
    rc = bfs.main([
        "--claim", "the suite is green",
        "--reality", "14 tests failed",
        "--confidence", "5", "--wrongness", "4",
        "--consequence", "3", "--recoverability", "5",
        "--source", "watchdog", "--agent", "claude",
    ])
    assert rc == 0
    recs = [json.loads(l) for l in
            (tmp_path / "brainfarts.jsonl").read_text().splitlines()]
    assert len(recs) == 1
    rec = recs[0]
    assert rec["claim"] == "the suite is green"
    assert rec["reality"] == "14 tests failed"
    assert rec["axes"] == {
        "confidence": 5, "wrongness": 4,
        "consequence": 3, "recoverability": 5,
    }
    assert rec["source"] == "watchdog"
    assert rec["agent"] == "claude"
    assert rec["published"] is True
    assert rec["ts"]
    assert bfs.is_published(rec)


def test_stdin_json_is_the_same_as_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINFARTS_JSONL", str(tmp_path / "brainfarts.jsonl"))
    payload = json.dumps({
        "claim": "quota is fine",
        "reality": "quota reached",
        "source": "rota",
        "agent": "codex",
        "axes": {"confidence": 5, "wrongness": 5,
                 "consequence": 2, "recoverability": 5},
    })
    rc = bfs.main([], stdin=io.StringIO(payload))
    assert rc == 0
    rec = json.loads((tmp_path / "brainfarts.jsonl").read_text())
    assert rec["claim"] == "quota is fine"
    assert rec["reality"] == "quota reached"
    assert rec["published"] is True
    assert rec["axes"]["wrongness"] == 5


def test_missing_scores_stay_unpublished_and_off_the_feed(monkeypatch):
    """Collection is automatic; the public feed is not."""
    rec = bfs.submit(
        claim="I proposed something",
        reality="the turn produced nothing",
        source="board",
        agent="codex",
    )
    assert rec["published"] is False
    assert rec["axes"] == {}
    assert not bfs.is_published(rec)

    scored = _scored()
    body = client.get("/brainfarts.json").json()
    assert scored in body
    assert rec not in body
    assert all(r.get("published") is not False for r in body)


def test_from_board_drafts_todays_errors_only(tmp_path, monkeypatch):
    ledger = tmp_path / "fleet" / "rota" / "proposals.jsonl"
    ledger.parent.mkdir(parents=True)
    rows = [
        {"ts": "2026-08-19T10:00:00Z", "agent": "codex", "outcome": "error",
         "text": "[error] quota reached"},
        {"ts": "2026-08-19T11:00:00Z", "agent": "codex", "outcome": "error",
         "text": "[stderr] Individual quota reached"},
        {"ts": "2026-08-19T12:00:00Z", "agent": "claude", "outcome": "proposed",
         "text": "Write the submit script"},
        {"ts": "2026-08-18T09:00:00Z", "agent": "codex", "outcome": "error",
         "text": "[error] yesterday"},
    ]
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setenv("FLEET_PATH", str(tmp_path / "fleet"))
    monkeypatch.setenv("BRAINFARTS_JSONL", str(tmp_path / "brainfarts.jsonl"))

    first = bfs.from_board(today="2026-08-19")
    assert [r["agent"] for r in first] == ["codex", "codex"]
    assert all(r["published"] is False for r in first)
    assert all(r["source"] == "board" for r in first)
    assert first[0]["claim"] == "[error] quota reached"
    assert "outcome: error" in first[0]["reality"]
    assert first[0]["board_ts"] == "2026-08-19T10:00:00Z"

    again = bfs.from_board(today="2026-08-19")
    assert again == []
    recs = bfs.load()
    assert len(recs) == 2
    assert all(not bfs.is_published(r) for r in recs)


def test_from_board_cli_reads_the_ledger(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2099, 1, 1, 12, 0, 0, tzinfo=tz or timezone.utc)

    ledger = tmp_path / "proposals.jsonl"
    ledger.write_text(json.dumps({
        "ts": "2099-01-01T00:00:00Z", "agent": "codex", "outcome": "error",
        "text": "[error] still nothing",
    }) + "\n")
    monkeypatch.setenv("ROTA_PROPOSALS", str(ledger))
    monkeypatch.setenv("BRAINFARTS_JSONL", str(tmp_path / "brainfarts.jsonl"))
    monkeypatch.setattr(bfs, "datetime", Frozen)
    rc = bfs.main(["--from-board"])
    assert rc == 0
    recs = bfs.load()
    assert len(recs) == 1
    assert recs[0]["agent"] == "codex"
    assert recs[0]["published"] is False
    assert recs[0]["board_ts"] == "2099-01-01T00:00:00Z"


def test_partial_or_bad_scores_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINFARTS_JSONL", str(tmp_path / "brainfarts.jsonl"))
    assert bfs.main([
        "--claim", "x", "--reality", "y", "--confidence", "5",
    ]) == 2
    assert bfs.main([
        "--claim", "x", "--reality", "y",
        "--confidence", "5", "--wrongness", "4",
        "--consequence", "3", "--recoverability", "9",
    ]) == 2
    assert bfs.main(["--claim", "x"]) == 2
    assert not (tmp_path / "brainfarts.jsonl").exists()
