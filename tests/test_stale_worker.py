"""Green but old must not hide in plain sight.

On 2026-08-04 the board showed agent-comms as "pass" with a last_run of
2026-08-03T19:18:38Z while the other live checks had run within the hour — a
17-hour-old heartbeat wearing a green pill. These tests pin the human board:
the laggard's card says stale, and one line above the cards says what needs
a person.
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

WORKERS = [
    {"worker": "agent-comms", "kind": "heartbeat", "status": "pass",
     "summary": "3/3 hops", "last_run": "2026-08-03T19:18:38Z"},
    {"worker": "command-control-dashboard", "kind": "watchdog", "status": "pass",
     "summary": "244 passed", "last_run": "2026-08-04T12:40:15Z"},
    {"worker": "visitors", "kind": "meter", "status": "pass",
     "summary": "841 hits/24h", "last_run": "2026-08-04T12:52:35+00:00"},
]


@pytest.fixture(autouse=True)
def no_real_branches(monkeypatch):
    """The attention line counts unmerged branches from the live .git; tests
    must not depend on what happens to be unmerged when they run."""
    monkeypatch.setitem(sys.modules, "council",
                        types.SimpleNamespace(open_branches=lambda: []))


def test_the_laggard_is_marked_stale_on_its_card():
    html = fleetboard.render_body([dict(w) for w in WORKERS])
    assert "stale 17h" in html


def test_the_board_opens_with_a_needs_attention_line():
    html = fleetboard.render_body([dict(w) for w in WORKERS])
    assert "Needs attention:" in html
    assert "agent-comms stale 17h" in html


def test_a_fleet_in_step_shows_no_attention_line():
    fresh = [dict(w, last_run="2026-08-04T12:00:00Z") for w in WORKERS]
    html = fleetboard.render_body(fresh)
    assert "Needs attention" not in html
    assert "stalemark" not in html


def test_a_stale_worker_stops_claiming_pass():
    """The green pill was the whole problem: a worker that has not run in half a
    day is not passing, whatever its last run said."""
    ws = [dict(w) for w in WORKERS]
    fleetboard.render_body(ws)
    by_name = {w["worker"]: w["status"] for w in ws}
    assert by_name["agent-comms"] == "warn"
    assert by_name["visitors"] == "pass"


def test_a_loud_status_is_not_softened_by_staleness():
    ws = [dict(w, status="fail") if w["worker"] == "agent-comms" else dict(w)
          for w in WORKERS]
    fleetboard.render_body(ws)
    assert {w["worker"]: w["status"] for w in ws}["agent-comms"] == "fail"


def test_the_stale_worker_is_not_counted_healthy():
    html = fleetboard.render_body([dict(w) for w in WORKERS])
    assert '<div class="v">2</div><div class="label">Healthy' in html


def test_staleness_is_relative_to_the_fleet_not_the_clock():
    """A laptop asleep all weekend ages every check together; that is not one
    worker's fault and must not light the board up."""
    old_together = [dict(w, last_run="2026-07-30T09:00:00Z") for w in WORKERS]
    assert "stale" not in fleetboard.render_body(old_together)


def test_a_day_behind_is_red_not_merely_amber():
    """Twelve days green is what this is for.

    On 2026-08-18 the nuc card read `pass` with a last_run from the 6th. Six
    hours behind is a note; a full day behind is a different claim, and it gets
    the failure colour so the board cannot quietly carry a dead machine.
    """
    ws = [dict(w) for w in WORKERS]
    ws[0]["last_run"] = "2026-07-28T12:00:00Z"        # ~7 days behind the rest
    fleetboard.render_body(ws)
    assert {w["worker"]: w["status"] for w in ws}["agent-comms"] == "stale"


def test_the_json_the_agents_read_is_downgraded_too(tmp_path, monkeypatch):
    """The council believed /workers.json, and /workers.json believed the file.

    render_body downgraded a stale worker while load_workers did not, so the
    html page said `warn` and the json said `pass`. Everything that is not a
    human reads the json.
    """
    import json as _json
    monkeypatch.setattr(fleetboard, "WORKERS", tmp_path)
    monkeypatch.setattr(fleetboard, "SELF_IMPROVE", tmp_path / "nope")
    monkeypatch.setitem(sys.modules, "probe",
                        types.SimpleNamespace(probe_all_cached=lambda: []))
    for w in WORKERS:
        (tmp_path / f"{w['worker']}.json").write_text(_json.dumps(w))

    got = {w["worker"]: w["status"] for w in fleetboard.load_workers()}
    assert got["agent-comms"] == "warn"        # 17h behind, not a day
    assert got["visitors"] == "pass"


def test_a_stray_json_does_not_take_the_board_down(tmp_path, monkeypatch):
    """The workers directory is a drop box; not everything dropped is a worker."""
    import json as _json
    monkeypatch.setattr(fleetboard, "WORKERS", tmp_path)
    monkeypatch.setattr(fleetboard, "SELF_IMPROVE", tmp_path / "nope")
    monkeypatch.setitem(sys.modules, "probe",
                        types.SimpleNamespace(probe_all_cached=lambda: []))
    (tmp_path / "notes.json").write_text(_json.dumps({"levels": [1, 2]}))
    (tmp_path / "visitors.json").write_text(_json.dumps(WORKERS[2]))

    assert [w["worker"] for w in fleetboard.load_workers()] == ["visitors"]


def test_stale_sorts_with_the_failures():
    """A dead check must not sit below the healthy ones where nobody scrolls."""
    ranked = {"fail": 0, "stale": 1, "alert": 2, "warn": 3,
              "skip": 4, "pass": 5, "idle": 6}
    assert ranked["stale"] < ranked["warn"] < ranked["pass"]
