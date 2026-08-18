"""Grok joins the fleet.

Onboarding an agent means four separate registrations, and forgetting any one
of them fails quietly rather than loudly: claude ran unregistered in agentsview
for weeks and simply rendered as the fleet's own gear. These tests pin all of
them together so the next agent cannot be half-added.
"""

import importlib.util
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, BIN / file)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


chat = _load("fleetchat", "chat.py")
plusone = _load("fleetplusone", "plusone.py")
agentsview = _load("fleetagentsview", "agentsview.py")


def test_grok_is_offered_in_chat():
    assert "grok" in chat.AGENTS


def test_grok_is_not_treated_as_local_work():
    """It is somebody else's GPU. Queueing it behind a local model throttles
    the wrong thing - the same reasoning that exempted hermes and openclaw."""
    assert "grok" not in chat.LOCAL_AGENTS


def test_grok_has_a_face_on_the_board():
    assert "grok" in agentsview.AGENTS
    glyph, light, dark, blurb = agentsview.AGENTS["grok"]
    assert glyph and blurb
    assert light.startswith("#") and dark.startswith("#")


def test_grok_gets_its_own_colour():
    """Two agents sharing a colour is two agents nobody can tell apart."""
    colours = [v[1] for v in agentsview.AGENTS.values()]
    assert colours.count(agentsview.AGENTS["grok"][1]) == 1


def test_the_relay_knows_how_to_ask_grok(monkeypatch):
    seen = {}

    def fake(prompt, files, emit, timeout=600):
        seen["timeout"] = timeout
        return "43"

    monkeypatch.setattr(chat, "ask_grok", fake)
    monkeypatch.setattr(plusone, "chat", chat)
    assert plusone.ask("grok", "add one to 42", "s") == "43"
    assert seen["timeout"] == plusone.TURN_TIMEOUT


def test_an_unregistered_agent_is_still_refused():
    """The relay must not silently treat a typo as a silent agent."""
    assert plusone.ask("grokk", "hi", "s").startswith("[unknown agent")


def test_a_grok_harness_failure_is_not_read_as_an_answer():
    """`[timed out after 600s]` contains digits. A silent agent must never
    look like a wrong one."""
    assert plusone.HARNESS_FAILURE.match("[timed out after 600s]")
    assert plusone.HARNESS_FAILURE.match("[unknown agent grokk]")


def test_grok_is_invoked_headless_and_plain(monkeypatch):
    """-p is single-turn; plain is stated rather than assumed, because every
    other output format is NDJSON."""
    seen = {}
    monkeypatch.setattr(chat, "run_cmd",
                        lambda cmd, timeout=None, stdin_text=None:
                        seen.setdefault("cmd", cmd) or "ok")
    chat.ask_grok("say ok", [], lambda *a: None)
    assert seen["cmd"][:2] == ["grok", "-p"]
    assert "--output-format" in seen["cmd"]
    assert "plain" in seen["cmd"]
