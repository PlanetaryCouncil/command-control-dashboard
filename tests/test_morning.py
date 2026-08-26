"""The overnight briefing must not quietly drop an alarm.

`morning.py` exists so a night's work gets read. That only holds if the NEEDS
YOU section is trustworthy — a briefing that misses a standing request is worse
than no briefing, because it is read as an all-clear.

The load-bearing rule is that an alarm stands until *the agent that raised it*
reports ok. A busy fleet emits `ok` constantly from other agents, and clearing
on any of them would erase a real request within minutes.
"""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "dormant" / "morning.py"
spec = importlib.util.spec_from_file_location("morning", BIN)
morning = importlib.util.module_from_spec(spec)
spec.loader.exec_module(morning)


def ev(agent, level, msg="", minutes_ago=10):
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {"ts": ts.isoformat().replace("+00:00", "Z"),
            "agent": agent, "level": level, "msg": msg}


def test_an_alarm_survives_other_agents_reporting_ok():
    events = [
        ev("watchdog", "needs_you", "tests failed", 60),
        ev("council", "ok", "round done", 50),
        ev("rota", "ok", "turn done", 40),
    ]
    still = morning.needs_you(events)
    assert [e["agent"] for e in still] == ["watchdog"], \
        "another agent's ok cleared a standing request"


def test_the_same_agent_reporting_ok_clears_it():
    events = [
        ev("watchdog", "needs_you", "tests failed", 60),
        ev("watchdog", "ok", "green again", 30),
    ]
    assert morning.needs_you(events) == []


def test_a_re_raised_alarm_comes_back():
    """Fixed then broken again must read as broken, not as resolved."""
    events = [
        ev("watchdog", "needs_you", "first break", 90),
        ev("watchdog", "ok", "fixed", 60),
        ev("watchdog", "needs_you", "broke again", 30),
    ]
    still = morning.needs_you(events)
    assert len(still) == 1 and still[0]["msg"] == "broke again"


def test_briefing_renders_without_a_fleet():
    """This repo must run on a machine that has never had a fleet."""
    page = morning.render()
    assert page.startswith("# Morning —")
    assert "## NEEDS YOU" in page and "## RAN" in page


def test_first_line_truncates_multi_line_agent_output():
    """Agent messages are paragraphs; a briefing line is a line."""
    long = "first line of the proposal\nsecond line\nthird"
    assert "\n" not in morning.first_line(long)
    assert morning.first_line("x" * 200, limit=20).endswith("…")


def test_first_line_skips_the_house_style_bar():
    """Agents open with the 80-block rule; a summary of that is not a summary."""
    reply = "█" * 80 + "\n\n## CONTEXT\n\nThe relay double-books hermes.\n"
    assert morning.first_line(reply) == "The relay double-books hermes."


def test_first_line_strips_a_bar_that_shares_its_line():
    """Some agents return the whole reply as one line, bar included."""
    assert morning.first_line("█" * 80 + " Relay double-books hermes.") \
        == "Relay double-books hermes."


def test_an_unanswered_stranger_is_a_needs_you(tmp_path, monkeypatch):
    """Codex wrote twice asking whether anyone could see it. Nothing surfaced it."""
    repo = tmp_path
    (repo / "data").mkdir()
    (repo / "data" / "inbox.json").write_text(json.dumps({"signals": [
        {"id": "sig-1", "sender": "codex", "status": "new", "response": "",
         "received_at": "2026-08-03T14:50:12Z", "body": "How do you verify agent identity?"},
        {"id": "sig-2", "sender": "old", "status": "closed", "response": "handled",
         "received_at": "2026-07-01T00:00:00Z", "body": "already dealt with"},
    ]}))
    monkeypatch.setattr(morning, "REPO", repo)
    still = morning.open_signals()
    assert [s["id"] for s in still] == ["sig-1"]
    assert "codex" in morning.render()
