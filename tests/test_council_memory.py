"""A council that cannot remember re-derives the same finding forever.

On 2026-08-03 `claude` and `openclaw` independently reported the same root
cause, which is itself the evidence for it: `board_state()` showed workers,
event counts and 60 recent events, and nothing about work already filed. So
every council saw a fresh-looking gap and filed it again.

claude priced it: 257 seconds of agent time re-reaching a conclusion the
previous council had already reached 25 hours earlier — on a laptop that was
deferring its own jobs for load twenty minutes later. openclaw counted the loop
at 30 of 60 events in a day.

The 6-hour transcript window is not the bug and is not touched. It exists to
keep stale context out of a live conversation. This is the separate, durable
memory it was never meant to be.
"""

import importlib.util
import json
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "council.py"
spec = importlib.util.spec_from_file_location("council", BIN)
council = importlib.util.module_from_spec(spec)
spec.loader.exec_module(council)


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    (tmp_path / "rota").mkdir()
    (tmp_path / "workers").mkdir()
    monkeypatch.setattr(council, "FLEET", tmp_path)
    return tmp_path


def write_proposals(root, rows):
    (root / "rota" / "proposals.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")


def test_a_council_can_see_what_was_already_proposed(fleet):
    write_proposals(fleet, [
        {"ts": "2026-08-03T15:55:00Z", "agent": "hermes", "outcome": "proposed",
         "text": "████\n\n1. Add a rota load gate row to the board"},
    ])
    gists = [p["gist"] for p in council.already_asked()]
    assert any("rota load gate" in g for g in gists)


def test_the_house_style_bar_is_stripped_from_the_gist(fleet):
    """Every agent opens with the 80-block rule; a wall of █ summarises nothing."""
    write_proposals(fleet, [
        {"ts": "2026-08-03T16:00:00Z", "agent": "openclaw", "outcome": "proposed",
         "text": "█" * 80 + "\n\n## CONTEXT\n\nThe relay double-books hermes."},
    ])
    gist = council.already_asked()[0]["gist"]
    assert "█" not in gist
    assert gist.startswith("The relay double-books")


def test_only_the_recent_ones_are_carried(fleet):
    """Memory, not an archive — a council reads this before every round."""
    write_proposals(fleet, [
        {"ts": f"2026-08-0{i % 9 + 1}T00:00:00Z", "agent": "a",
         "outcome": "proposed", "text": f"proposal {i}"} for i in range(20)])
    assert len(council.already_asked()) == 6
    assert council.already_asked()[-1]["gist"] == "proposal 19"


def test_no_proposals_file_is_a_normal_state(fleet):
    assert council.already_asked() == []


def test_an_alert_carries_how_long_it_has_been_ringing(fleet):
    """agent-comms sat in alert for 23 hours while two councils noted it.

    From the board alone nobody could tell whether that was three minutes old
    or a day stale, which is the difference between "someone is on it" and
    "everyone has walked past it".
    """
    (fleet / "workers" / "agent-comms.json").write_text(json.dumps({
        "worker": "agent-comms", "kind": "heartbeat", "status": "alert",
        "summary": "2/3 hops", "last_run": "2026-08-02T18:59:37Z"}))
    row = next(w for w in council.board_state()["workers"]
               if w["worker"] == "agent-comms")
    assert row["alert_since"] == "2026-08-02T18:59:37Z"


def test_a_healthy_worker_gets_no_alert_stamp(fleet):
    (fleet / "workers" / "ok.json").write_text(json.dumps({
        "worker": "ok", "kind": "watchdog", "status": "pass",
        "summary": "187 passed", "last_run": "2026-08-03T14:00:00Z"}))
    row = next(w for w in council.board_state()["workers"] if w["worker"] == "ok")
    assert "alert_since" not in row


def test_a_green_worker_far_behind_the_others_is_flagged_stale(fleet):
    """agent-comms was "pass" with a last_run 17 hours behind the live checks —
    green but old, hiding in plain sight."""
    (fleet / "workers" / "agent-comms.json").write_text(json.dumps({
        "worker": "agent-comms", "kind": "heartbeat", "status": "pass",
        "summary": "3/3 hops", "last_run": "2026-08-03T19:18:38Z"}))
    (fleet / "workers" / "watchdog.json").write_text(json.dumps({
        "worker": "watchdog", "kind": "watchdog", "status": "pass",
        "summary": "244 passed", "last_run": "2026-08-04T12:40:15Z"}))
    rows = {w["worker"]: w for w in council.board_state()["workers"]}
    assert rows["agent-comms"]["stale"].startswith("17h")
    assert "stale" not in rows["watchdog"]


def test_workers_running_in_step_are_never_stale(fleet):
    """Staleness is relative to the freshest worker, not the clock, so a
    machine that slept all weekend does not flag its whole fleet."""
    (fleet / "workers" / "a.json").write_text(json.dumps({
        "worker": "a", "status": "pass", "last_run": "2026-08-01T10:00:00Z"}))
    (fleet / "workers" / "b.json").write_text(json.dumps({
        "worker": "b", "status": "pass", "last_run": "2026-08-01T10:30:00+00:00"}))
    assert all("stale" not in w for w in council.board_state()["workers"])


def test_the_board_opens_with_a_needs_attention_line(fleet, monkeypatch):
    monkeypatch.setattr(council.ev, "tail", lambda n=200: [])
    (fleet / "workers" / "agent-comms.json").write_text(json.dumps({
        "worker": "agent-comms", "status": "pass",
        "last_run": "2026-08-03T19:18:38Z"}))
    (fleet / "workers" / "watchdog.json").write_text(json.dumps({
        "worker": "watchdog", "status": "pass",
        "last_run": "2026-08-04T12:40:15Z"}))
    line = council.board_state()["needs_attention"]
    assert "agent-comms stale since 2026-08-03T19:18:38Z" in line


def test_a_quiet_board_needs_nothing(fleet, monkeypatch):
    monkeypatch.setattr(council.ev, "tail", lambda n=200: [])
    (fleet / "workers" / "ok.json").write_text(json.dumps({
        "worker": "ok", "status": "pass", "last_run": "2026-08-04T12:00:00Z"}))
    assert council.board_state()["needs_attention"] == "nothing"


def test_the_board_hands_both_memories_to_the_agent(fleet):
    """If these two keys are missing the council is blind again."""
    write_proposals(fleet, [{"ts": "2026-08-03T00:00:00Z", "agent": "a",
                             "outcome": "proposed", "text": "something"}])
    state = council.board_state()
    assert "already_proposed" in state
    assert "unmerged_branches" in state
