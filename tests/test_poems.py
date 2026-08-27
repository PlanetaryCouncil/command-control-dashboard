"""A closing couplet has to reach /poems.json, stamped with who wrote it."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"

spec = importlib.util.spec_from_file_location("poems", BIN / "poems.py")
poems = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poems)

rspec = importlib.util.spec_from_file_location("rota", BIN / "rota.py")
rota = importlib.util.module_from_spec(rspec)
rspec.loader.exec_module(rota)


def test_append_writes_one_json_object_per_line(tmp_path, monkeypatch):
    monkeypatch.setenv("POEMS_JSONL", str(tmp_path / "poems.jsonl"))
    rec = poems.append("the door is open now\nthe couplet stays", "Grok", "rota")
    assert rec["author"] == "grok"
    assert rec["task"] == "rota"
    assert rec["lines"] == ["the door is open now", "the couplet stays"]
    assert rec["ts"]
    line = (tmp_path / "poems.jsonl").read_text().strip()
    assert json.loads(line) == rec


def test_a_boxed_closer_is_harvested():
    text = (
        "Write the About page.\n\n"
        "    ╭──────────────────────────╮\n"
        "    │  green tests, quiet night │\n"
        "    │  the couplet is the keep  │\n"
        "    ╰──────────────────────────╯\n"
    )
    assert poems.couplet(text) == [
        "green tests, quiet night",
        "the couplet is the keep",
    ]


def test_a_long_proposal_without_a_closer_is_not_a_poem():
    text = "\n".join(f"point {i} is small and clear" for i in range(8))
    assert poems.couplet(text) == []


def test_nothing_to_add_is_not_kept():
    assert poems.couplet("NOTHING TO ADD") == []
    assert poems.append("NOTHING TO ADD", "claude", "rota") is None


def test_newest_fifty_render_first(tmp_path, monkeypatch):
    monkeypatch.setenv("POEMS_JSONL", str(tmp_path / "poems.jsonl"))
    for i in range(51):
        poems.append(f"line one of {i}\nline two of {i}", "claude", f"task-{i}")
    recs = poems.recent(50)
    assert len(recs) == 50
    assert recs[0]["task"] == "task-50"
    assert recs[-1]["task"] == "task-1"
    page = poems.page("", "")
    assert "line one of 50" in page
    assert "line one of 0" not in page
    feed = json.loads(poems.as_json())
    assert feed[0]["task"] == "task-50"
    assert len(feed) == 51


def test_missing_file_is_an_empty_feed(tmp_path, monkeypatch):
    monkeypatch.setenv("POEMS_JSONL", str(tmp_path / "missing.jsonl"))
    assert poems.as_json() == "[]"
    assert "No poems yet" in poems.page("", "")


def test_page_escapes_markup(tmp_path, monkeypatch):
    monkeypatch.setenv("POEMS_JSONL", str(tmp_path / "poems.jsonl"))
    poems.append("<img src=x onerror=alert(1)>\nnot a tag really",
                 "<b>claude", "rota")
    page = poems.page("", "")
    assert "<img src=x onerror=alert(1)>" not in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page
    assert "&lt;b&gt;claude" in page


@pytest.fixture
def rota_sandbox(tmp_path, monkeypatch):
    import heavygate
    monkeypatch.setenv("POEMS_JSONL", str(tmp_path / "poems.jsonl"))
    monkeypatch.setattr(heavygate, "enabled", lambda: True)
    monkeypatch.setattr(rota, "STATE", tmp_path / "rota.json")
    monkeypatch.setattr(rota, "LEDGER", tmp_path / "proposals.jsonl")
    monkeypatch.setattr(rota.ev, "emit", lambda *a, **k: None)
    monkeypatch.setattr(rota.council, "board_state", lambda: {})
    import quotas as quotas_mod
    monkeypatch.setattr(quotas_mod, "eligible", lambda agents, **k: agents)
    import pressure
    monkeypatch.setattr(pressure, "snapshot", lambda **k: {
        "load1": 1.2, "ncpu": 4, "max_load": 4, "compressor_gb": 0.2,
        "hot": False, "reason": "ok",
    })
    return tmp_path


def test_a_rota_turn_stamps_author_and_task(rota_sandbox, monkeypatch):
    monkeypatch.setattr(rota, "ask", lambda *a, **k: (
        "Write the About page for BaseX.\n\n"
        "the door is open now\n"
        "a couplet stays behind"
    ))
    monkeypatch.setattr(sys, "argv", ["rota.py", "--agents", "grok"])
    assert rota.main() == 0
    recs = [json.loads(l) for l in
            (rota_sandbox / "poems.jsonl").read_text().splitlines()]
    assert recs[-1]["author"] == "grok"
    assert recs[-1]["task"] == "rota"
    assert recs[-1]["lines"] == [
        "the door is open now",
        "a couplet stays behind",
    ]


def test_a_failed_rota_turn_is_not_filed_as_a_poem(rota_sandbox, monkeypatch):
    monkeypatch.setattr(rota, "ask", lambda *a, **k: "[error] quota reached")
    monkeypatch.setattr(sys, "argv", ["rota.py", "--agents", "hermes"])
    assert rota.main() == 0
    assert not (rota_sandbox / "poems.jsonl").exists()
