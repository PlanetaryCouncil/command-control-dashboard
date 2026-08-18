"""What the pipeline card says now that branches land themselves.

Previously the card handed the operator a paste-able `git merge --no-ff …`,
because approved branches piled up waiting for a human. As of 2026-08-07 the
pipeline merges its own approved work, so that command is not an aid — it is
an instruction to do a job that already ran. Marsita: "fleet can merge... I
don't want to worry about infra / pr / code / issues."

So the contract flipped. Approved-and-landed is quiet. The card only raises
its voice when landing FAILED, because that is the one state a human might
have to care about.
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


def write_row(tmp_path, **row):
    row.setdefault("proposal_ts", row.get("branch"))
    row.setdefault("ts", "2026-08-07T14:42:29+00:00")
    with (tmp_path / "pipeline.jsonl").open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def test_landed_work_is_quiet(isolated_state):
    """A cycle that merged its own work is a good day, not an alert."""
    write_row(isolated_state, stage="land", branch=BRANCH, ok=True)
    pipeline.write_worker()
    card = json.loads(pipeline.WORKER.read_text())
    assert card["status"] == "pass"
    assert "git merge" not in card["summary"]
    assert "landed" in card["summary"]


def test_failed_landing_raises_the_alarm(isolated_state):
    """The one state worth a human's attention: it passed review and still
    could not reach main."""
    write_row(isolated_state, stage="land", branch=BRANCH, ok=False,
              detail="merged tests: 1 failed")
    pipeline.write_worker()
    card = json.loads(pipeline.WORKER.read_text())
    assert card["status"] == "alert"
    assert "could not land" in card["summary"]
    assert BRANCH in card["summary"]


def test_approved_but_not_yet_landed_is_flagged(isolated_state):
    """Approved with no landing record means the merge never ran. Under the
    old design this was normal and permanent; now it means something stopped."""
    write_row(isolated_state, stage="verify", branch=BRANCH, ok=True)
    pipeline.write_worker()
    card = json.loads(pipeline.WORKER.read_text())
    assert card["status"] == "alert"
    assert "not yet landed" in card["summary"]


def test_rejected_work_is_not_an_alert(isolated_state):
    write_row(isolated_state, stage="verify", branch=BRANCH, ok=False)
    pipeline.write_worker()
    card = json.loads(pipeline.WORKER.read_text())
    assert card["status"] == "pass"
    assert "git merge" not in card["summary"]
