"""Every "awaits your merge" alert carries the paste-able command.

The pipeline sat in alert with "rota/... awaits your merge" while unmerged
branches accumulated one per night. Naming a branch makes the human go
reconstruct the command; the alert should hand them the one line to paste.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))
spec = importlib.util.spec_from_file_location("pipeline", BIN / "pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)

BRANCH = "rota/2026-08-04-1-improve-the-machine-add-a-stale-worker"


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "STATE", tmp_path / "pipeline.jsonl")
    monkeypatch.setattr(pipeline, "WORKER", tmp_path / "workers" / "pipeline.json")
    return tmp_path


def write_verify(tmp_path, branch, ok):
    with (tmp_path / "pipeline.jsonl").open("a") as fh:
        fh.write(json.dumps({"stage": "verify", "proposal_ts": branch,
                             "branch": branch, "ok": ok,
                             "ts": "2026-08-04T14:42:29+00:00"}) + "\n")


def test_the_alert_includes_the_git_merge_line(isolated_state):
    write_verify(isolated_state, BRANCH, ok=True)
    pipeline.write_worker()
    card = json.loads(pipeline.WORKER.read_text())
    assert card["status"] == "alert"
    assert f"git merge --no-ff {BRANCH}" in card["summary"]


def test_the_command_survives_the_summary_cap(isolated_state):
    """A truncated command is worse than none — it pastes and fails."""
    write_verify(isolated_state, BRANCH, ok=True)
    pipeline.write_worker()
    card = json.loads(pipeline.WORKER.read_text())
    assert card["summary"].endswith(BRANCH)


def test_nothing_awaiting_offers_no_command(isolated_state):
    write_verify(isolated_state, BRANCH, ok=False)
    pipeline.write_worker()
    card = json.loads(pipeline.WORKER.read_text())
    assert card["status"] == "pass"
    assert "git merge" not in card["summary"]
