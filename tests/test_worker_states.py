"""States that say what is happening, rather than what the board does not know.

Marsita, 2026-08-18, on seeing `fail` for a check the fleet had deliberately
declined to run: "maybe use explicit names such as busy / thinking and last
signal date or last connection date".

`fail`, `stale` and `warn` are all the board describing its own ignorance.
`busy` and `thinking` are the machine describing itself, and they are different
claims: one means not now, the other means give me a minute.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))
spec = importlib.util.spec_from_file_location("fleetboard", BIN / "fleet.py")
fleetboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fleetboard)

FRESH = "2026-08-18T12:00:00Z"
OLD = "2026-08-01T12:00:00Z"


@pytest.fixture(autouse=True)
def no_real_branches(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "council",
                        types.SimpleNamespace(open_branches=lambda: []))
    monkeypatch.setattr(fleetboard, "CHARGES", tmp_path / "none.jsonl")


def test_busy_is_not_failed():
    ws = [{"worker": "agent-comms", "status": "busy", "last_run": FRESH,
           "summary": "deferred — load 8.4 over 6"},
          {"worker": "visitors", "status": "pass", "last_run": FRESH}]
    html = fleetboard.render_body([dict(w) for w in ws])
    assert "busy" in html
    assert "Needs attention" not in html      # nobody is being summoned


def test_thinking_is_not_failed():
    ws = [{"worker": "agent-comms", "status": "thinking", "last_run": FRESH,
           "summary": "relaying now"}]
    html = fleetboard.render_body([dict(w) for w in ws])
    assert "thinking" in html
    assert "Needs attention" not in html


def test_a_long_deferral_still_ages_into_red():
    """Not now is fine. Not now for a fortnight is a real problem, and the
    card has to end up saying so on its own."""
    ws = [{"worker": "agent-comms", "status": "pass", "last_run": OLD},
          {"worker": "visitors", "status": "pass", "last_run": FRESH}]
    fleetboard.render_body(ws)
    assert {w["worker"]: w["status"] for w in ws}["agent-comms"] == "stale"


def test_staleness_never_overwrites_a_live_state():
    """busy and thinking are claims about right now. Ageing them would replace
    a true statement with a guess."""
    ws = [{"worker": "agent-comms", "status": "busy", "last_run": OLD},
          {"worker": "visitors", "status": "pass", "last_run": FRESH}]
    fleetboard.render_body(ws)
    assert {w["worker"]: w["status"] for w in ws}["agent-comms"] == "busy"


def test_the_card_names_what_the_timestamp_means():
    html = fleetboard.render_body([{"worker": "visitors", "status": "pass",
                                    "last_run": FRESH}])
    assert "last signal" in html


def test_a_worker_that_never_reported_says_so():
    html = fleetboard.render_body([{"worker": "self-improve", "status": "idle",
                                    "last_run": None}])
    assert "no signal yet" in html


def test_working_sorts_above_quiet_and_below_trouble(tmp_path, monkeypatch):
    """A card that is mid-sentence belongs near the top - it answers the
    question "why is this not fresh" - but never above something asking for a
    human."""
    import json as _json
    monkeypatch.setattr(fleetboard, "WORKERS", tmp_path)
    monkeypatch.setattr(fleetboard, "SELF_IMPROVE", tmp_path / "nope")
    monkeypatch.setitem(sys.modules, "probe",
                        types.SimpleNamespace(probe_all_cached=lambda: []))
    for name, status in (("quiet", "pass"), ("broken", "fail"),
                         ("working", "thinking"), ("waiting", "busy")):
        (tmp_path / f"{name}.json").write_text(_json.dumps(
            {"worker": name, "status": status, "last_run": FRESH}))

    assert [w["worker"] for w in fleetboard.load_workers()] == \
        ["broken", "working", "waiting", "quiet"]
