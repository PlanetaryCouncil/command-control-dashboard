"""A council turn is only worth spending when the board has moved.

Six proposals landed in 63 minutes on 2026-08-07 — 13:00, 13:50, 13:55, 13:57,
14:00, 14:03 — and across that hour the board's substance did not change:
`pipeline` in `alert` with the same merge queue, the same "341 passed" summary,
the same visitors line. Three of the six restated the same two points.

So the gate: hash the fields that would change what an agent says, skip the turn
when it matches the last one, and let last_run stamps and event churn tick
without waking anybody.
"""

import importlib.util
import json
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "council.py"
spec = importlib.util.spec_from_file_location("council_gate", BIN)
council = importlib.util.module_from_spec(spec)
spec.loader.exec_module(council)


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    (tmp_path / "council").mkdir()
    monkeypatch.setattr(council, "FLEET", tmp_path)
    return tmp_path


def state(status="alert", summary="341 passed", proposals=1, last_run="10:00"):
    return {
        "workers": [{"worker": "pipeline", "status": status,
                     "summary": summary, "alert_since": "09:00",
                     "last_run": last_run}],
        "already_proposed": [{"gist": f"p{i}"} for i in range(proposals)],
        "unmerged_branches": [{"branch": "self-improve/a", "tip": "abc"}],
    }


def test_same_board_same_hash(fleet):
    assert council.board_fingerprint(state()) == council.board_fingerprint(state())


def test_churn_does_not_move_the_hash(fleet):
    """last_run ticks every few minutes; the situation is identical."""
    assert (council.board_fingerprint(state(last_run="10:00"))
            == council.board_fingerprint(state(last_run="10:45")))


@pytest.mark.parametrize("changed", [
    {"status": "ok"},
    {"summary": "340 passed, 1 failed"},
    {"proposals": 2},
])
def test_material_change_moves_the_hash(fleet, changed):
    assert council.board_fingerprint(state()) != council.board_fingerprint(state(**changed))


def test_fingerprint_round_trip(fleet):
    assert council.last_fingerprint() is None
    council.save_fingerprint("deadbeef")
    assert council.last_fingerprint() == "deadbeef"


def _stub(monkeypatch, fleet, board):
    monkeypatch.setattr(council, "board_state", lambda: board)
    monkeypatch.setattr(council.ev, "emit", lambda *a, **k: None)

    def boom(*a, **k):
        raise AssertionError("spawned an agent on an unchanged board")

    monkeypatch.setattr(council, "ask", boom)


def test_run_skips_an_unchanged_board(fleet, monkeypatch):
    _stub(monkeypatch, fleet, state())
    council.save_fingerprint(council.board_fingerprint(state()))
    res = council.run(["claude", "hermes"], rounds=1)
    assert res["adjourned"] == "board unchanged"
    assert res["turns"] == []


def test_force_convenes_anyway(fleet, monkeypatch):
    _stub(monkeypatch, fleet, state())
    council.save_fingerprint(council.board_fingerprint(state()))
    monkeypatch.setattr(council, "ask",
                        lambda agent, prompt, session: "NOTHING TO ADD")
    monkeypatch.setattr(council, "transcript", lambda *a, **k: [])
    monkeypatch.setattr(council, "turns_so_far", lambda: {})
    monkeypatch.setattr(council, "build_prompt", lambda *a: "brief")
    res = council.run(["claude", "hermes"], rounds=1, force=True)
    assert res["adjourned"] != "board unchanged"
    assert [t["agent"] for t in res["turns"]] == ["claude", "hermes"]


def test_changed_board_convenes_and_advances_the_mark(fleet, monkeypatch):
    _stub(monkeypatch, fleet, state(status="ok"))
    council.save_fingerprint(council.board_fingerprint(state()))
    monkeypatch.setattr(council, "ask",
                        lambda agent, prompt, session: "NOTHING TO ADD")
    monkeypatch.setattr(council, "transcript", lambda *a, **k: [])
    monkeypatch.setattr(council, "turns_so_far", lambda: {})
    monkeypatch.setattr(council, "build_prompt", lambda *a: "brief")
    council.run(["claude", "hermes"], rounds=1)
    assert council.last_fingerprint() == council.board_fingerprint(state(status="ok"))


def test_a_skipped_council_leaves_the_mark_alone(fleet, monkeypatch):
    """Otherwise a skip would record the board it never looked at properly."""
    _stub(monkeypatch, fleet, state())
    mark = council.board_fingerprint(state())
    council.save_fingerprint(mark)
    council.run(["claude", "hermes"], rounds=1)
    assert council.last_fingerprint() == mark


def test_real_board_state_is_hashable(monkeypatch):
    """The gate must survive the shape board_state() actually returns."""
    fp = council.board_fingerprint(council.board_state())
    assert isinstance(fp, str) and len(fp) == 16


def test_empty_board_hashes(fleet):
    assert council.board_fingerprint({})
