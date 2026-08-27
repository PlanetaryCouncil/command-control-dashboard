"""A rota turn is only worth spending when the board has moved.

Six proposals landed in 63 minutes on 2026-08-07 — 13:00, 13:50, 13:55, 13:57,
14:00, 14:03 — and across that hour the board's substance did not change:
`pipeline` in `alert` with the same merge queue, the same "341 passed" summary,
the same visitors line. Three of the six restated the same two points.

The timer still fires. The skip is: hash the fields that would change what an
agent says, store that hash on the already_proposed row, and do not spawn when
it matches the last one.
"""

import importlib.util
import json
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "rota.py"
spec = importlib.util.spec_from_file_location("rota_board_gate", BIN)
rota = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rota)


def board(status="alert", summary="341 passed", last_run="10:00", proposals=1):
    return {
        "workers": [{"worker": "pipeline", "status": status,
                     "summary": summary, "alert_since": "09:00",
                     "last_run": last_run}],
        "already_proposed": [{"gist": f"p{i}"} for i in range(proposals)],
        "unmerged_branches": [{"branch": "self-improve/a", "tip": "abc"}],
    }


def test_same_board_same_hash():
    assert rota.turn_hash(board()) == rota.turn_hash(board())


def test_churn_does_not_move_the_hash():
    """last_run ticks every few minutes; the situation is identical."""
    assert (rota.turn_hash(board(last_run="10:00"))
            == rota.turn_hash(board(last_run="10:45")))


def test_a_new_proposal_does_not_move_the_hash():
    """The hash lives ON already_proposed; counting that list would make
    every filing look like the board moved, and the skip would never fire."""
    assert (rota.turn_hash(board(proposals=1))
            == rota.turn_hash(board(proposals=6)))


def test_material_change_moves_the_hash():
    quiet = rota.turn_hash(board())
    assert quiet != rota.turn_hash(board(status="ok"))
    assert quiet != rota.turn_hash(board(summary="340 passed, 1 failed"))


def sandbox(tmp_path, monkeypatch, board_state):
    import heavygate
    monkeypatch.setattr(heavygate, "enabled", lambda: True)
    monkeypatch.setattr(rota, "STATE", tmp_path / "rota.json")
    monkeypatch.setattr(rota, "LEDGER", tmp_path / "proposals.jsonl")
    events = []
    monkeypatch.setattr(rota.ev, "emit",
                        lambda agent, level, msg, **kw: events.append(msg))
    monkeypatch.setattr(rota.council, "board_state", lambda: board_state())
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
    return {"events": events, "asked": asked}


def run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["rota.py", *argv])
    return rota.main()


def test_run_skips_an_unchanged_board(tmp_path, monkeypatch):
    box = sandbox(tmp_path, monkeypatch, lambda: board())
    assert run(monkeypatch) == 0
    assert box["asked"] == ["hermes"]
    assert run(monkeypatch) == 0
    assert box["asked"] == ["hermes"]
    assert any("board unchanged — skipped" in e for e in box["events"])
    rows = rota.LEDGER.read_text().splitlines()
    assert len(rows) == 1


def test_changed_board_takes_another_turn(tmp_path, monkeypatch):
    current = {"state": board()}
    box = sandbox(tmp_path, monkeypatch, lambda: current["state"])
    assert run(monkeypatch) == 0
    current["state"] = board(status="ok")
    assert run(monkeypatch) == 0
    assert box["asked"] == ["hermes", "grok"]
    rows = [json.loads(l) for l in rota.LEDGER.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["board_hash"] != rows[1]["board_hash"]


def test_last_run_churn_still_skips(tmp_path, monkeypatch):
    current = {"state": board(last_run="10:00")}
    box = sandbox(tmp_path, monkeypatch, lambda: current["state"])
    assert run(monkeypatch) == 0
    current["state"] = board(last_run="10:45")
    assert run(monkeypatch) == 0
    assert box["asked"] == ["hermes"]


def test_a_failed_turn_does_not_pin_the_skip(tmp_path, monkeypatch):
    """A harness error is not a look at the board; the next firing must retry."""
    box = sandbox(tmp_path, monkeypatch, lambda: board())
    monkeypatch.setattr(rota, "ask", lambda agent, prompt, session:
                        box["asked"].append(agent) or "[error] timed out")
    assert run(monkeypatch) == 0
    assert json.loads(rota.LEDGER.read_text())["outcome"] == "error"
    assert "board_hash" not in json.loads(rota.LEDGER.read_text())
    monkeypatch.setattr(rota, "ask", lambda agent, prompt, session:
                        box["asked"].append(agent) or "a concrete proposal")
    assert run(monkeypatch) == 0
    assert box["asked"] == ["hermes", "grok"]


def test_unusable_turns_do_not_pin_the_skip(tmp_path, monkeypatch):
    box = sandbox(tmp_path, monkeypatch, lambda: board())
    monkeypatch.setattr(rota, "ask", lambda agent, prompt, session:
                        box["asked"].append(agent) or (
                            "The message seems to be an invitation for discussion"
                        ))
    assert run(monkeypatch) == 0
    monkeypatch.setattr(rota, "ask", lambda agent, prompt, session:
                        box["asked"].append(agent) or "a concrete proposal")
    assert run(monkeypatch) == 0
    assert box["asked"] == ["hermes", "grok"]


def test_empty_ledger_takes_a_turn(tmp_path, monkeypatch):
    box = sandbox(tmp_path, monkeypatch, lambda: board())
    assert rota.last_board_hash() is None
    assert run(monkeypatch) == 0
    assert box["asked"] == ["hermes"]
    assert rota.last_board_hash() == rota.turn_hash(board())
