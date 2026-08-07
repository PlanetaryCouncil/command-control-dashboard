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
