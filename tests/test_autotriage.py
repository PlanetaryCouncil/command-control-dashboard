"""Cheap autopilot closes noise without building anything."""

import json
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))
import autotriage  # noqa: E402
import pipeline    # noqa: E402


@pytest.fixture
def pile(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PROPOSALS", tmp_path / "proposals.jsonl")
    monkeypatch.setattr(pipeline, "STATE", tmp_path / "pipeline.jsonl")
    monkeypatch.setattr(pipeline, "WORKER", tmp_path / "pipeline.json")
    monkeypatch.setattr(autotriage, "FLEET", tmp_path)
    (tmp_path / "rota").mkdir()
    monkeypatch.setattr(pipeline, "ev",
                        type("E", (), {"emit": staticmethod(lambda *a, **k: None)}))
    monkeypatch.setattr(autotriage, "ev", pipeline.ev)
    return tmp_path


def write_props(pile, rows):
    pipeline.PROPOSALS.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")


def test_errors_and_nothing_drop_without_a_model(pile, monkeypatch):
    monkeypatch.setattr(autotriage, "ask_cheap", lambda p: (_ for _ in ()).throw(
        AssertionError("model should not run on drain-only")))
    write_props(pile, [
        {"ts": "2026-08-20T01:00:00+00:00", "agent": "codex",
         "outcome": "error", "text": "[unknown agent codex]"},
        {"ts": "2026-08-20T01:01:00+00:00", "agent": "hermes",
         "outcome": "nothing", "text": "NOTHING TO ADD"},
        {"ts": "2026-08-20T01:02:00+00:00", "agent": "grok",
         "outcome": "proposed", "text": "Add a stale-but-pass worker state"},
    ])
    res = autotriage.run(drain_only=True)
    seen = pipeline.by_proposal()
    assert seen["2026-08-20T01:00:00+00:00"]["stage"] == "drop"
    assert seen["2026-08-20T01:01:00+00:00"]["stage"] == "drop"
    assert "2026-08-20T01:02:00+00:00" not in seen
    assert res["open"] == 1


def test_duplicate_gists_collapse(pile, monkeypatch):
    monkeypatch.setattr(autotriage, "ask_cheap", lambda p: "")
    write_props(pile, [
        {"ts": "2026-08-20T02:00:00+00:00", "agent": "hermes",
         "outcome": "proposed", "text": "Make staleness a warn not a footnote"},
        {"ts": "2026-08-20T02:01:00+00:00", "agent": "grok",
         "outcome": "proposed",
         "text": "Make   staleness a warn not a footnote"},
    ])
    autotriage.run(drain_only=True)
    seen = pipeline.by_proposal()
    assert "2026-08-20T02:00:00+00:00" not in seen
    assert seen["2026-08-20T02:01:00+00:00"]["detail"].startswith("duplicate")


def test_parse_verdicts_matches_prefix():
    batch = {"2026-08-20T10:24:46+00:00", "2026-08-20T09:00:00Z"}
    blob = "2026-08-20T10:24 | DROP | restatement\n2026-08-20T09:00 | KEEP | real gap\n"
    v = autotriage.parse_verdicts(blob, batch)
    assert v["2026-08-20T10:24:46+00:00"] == "DROP"
    assert v["2026-08-20T09:00:00Z"] == "KEEP"


def test_unparsed_model_output_does_not_drop(pile, monkeypatch):
    monkeypatch.setattr(autotriage, "ask_cheap", lambda p: "sure whatever")
    write_props(pile, [
        {"ts": "2026-08-20T03:00:00+00:00", "agent": "agy",
         "outcome": "proposed", "text": "Publish /submit for the xprize"},
    ])
    autotriage.run(batches=1, drain_only=False)
    assert "2026-08-20T03:00:00+00:00" not in pipeline.by_proposal()


def test_stale_proposals_drop_without_a_model(pile, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(autotriage, "ask_cheap", lambda p: (_ for _ in ()).throw(
        AssertionError("stale drain is free")))
    old = (datetime.now(timezone.utc) - timedelta(hours=36)).isoformat(
        timespec="seconds")
    fresh = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_props(pile, [
        {"ts": old, "agent": "hermes", "outcome": "proposed",
         "text": "Write static/basex/index.html"},
        {"ts": fresh, "agent": "grok", "outcome": "proposed",
         "text": "A fresh unique action for today"},
    ])
    autotriage.run(drain_only=True)
    seen = pipeline.by_proposal()
    assert seen[old]["detail"].startswith("stale")
    assert fresh not in seen


def test_model_drop_closes_without_building(pile, monkeypatch):
    ts = "2026-08-20T04:00:00+00:00"
    monkeypatch.setattr(
        autotriage, "ask_cheap",
        lambda p: f"{ts[:16]} | DROP | already shipped\n")
    write_props(pile, [
        {"ts": ts, "agent": "grok", "outcome": "proposed",
         "text": "Tag E2E traffic out of visitors"},
    ])
    autotriage.run(batches=1)
    rec = pipeline.by_proposal()[ts]
    assert rec["stage"] == "drop"
    assert rec.get("branch") == ""
