"""Per-agent turn caps, and "too slow" told apart from "no answer".

Three agents raised this independently on the rota. The board showed hermes
timing out at 300.7s, 300.6s and 300.4s — always at its own chat-pane ceiling,
because the TURN_TIMEOUT constants in council.py and plusone.py were declared
but never handed to the adapters. And when the clock did run out, run_cmd threw
away the killed process's partial stdout, so "hermes is alive but slow" and
"hermes dropped the baton" produced the same string.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fleet" / "bin"))
import chat     # noqa: E402
import council  # noqa: E402
import plusone  # noqa: E402


# ------------------------------------------------------------- slow vs silent
def test_timeout_with_output_reports_partial():
    """An agent killed mid-answer was saying something; keep the evidence."""
    out = chat.run_cmd(["sh", "-c", "echo almost there; sleep 5"], timeout=1)
    assert out == "[timed out after 1s; partial: almost there]"


def test_timeout_with_no_output_says_so():
    out = chat.run_cmd(["sleep", "5"], timeout=1)
    assert out == "[timed out after 1s; no output]"


def test_outcomes_split_slow_from_dropped():
    """One word covered two faults. A slow agent and a gone agent need
    different responses, starting with whether to raise the cap."""
    assert plusone.outcome_of(
        "[timed out after 150s; partial: the answer is]", None, False) == "slow"
    assert plusone.outcome_of(
        "[timed out after 150s; no output]", None, False) == "timeout"
    # The old bare string still reads as a plain timeout.
    assert plusone.outcome_of("[timed out after 300s]", None, False) == "timeout"


def test_partial_output_is_still_not_an_answer():
    """The nastiest case again: digits inside the salvaged partial must not
    score as the agent's reply — same law as test_relay_honesty."""
    raw = "[timed out after 150s; partial: 48924]"
    assert plusone.extract_number(raw, 48924) is None
    assert plusone.outcome_of(raw, None, False) == "slow"


# ----------------------------------------------------------- the cap is wired
def _capture_timeout(monkeypatch):
    seen = {}

    # Not JSON and not a number: ask_openclaw json-parses what it gets back,
    # and a bare digit string would decode to an int and crash the unwrap.
    def fake_run_cmd(cmd, timeout, stdin_text=None):
        seen["timeout"] = timeout
        return "the next number"

    monkeypatch.setattr(chat, "run_cmd", fake_run_cmd)
    return seen


def test_relay_caps_every_agent_turn(monkeypatch):
    """plusone.TURN_TIMEOUT existed since the file was written and capped
    nothing; hermes ran its hops on the 300s chat default."""
    seen = _capture_timeout(monkeypatch)
    for agent in ("claude", "hermes", "openclaw", "grok"):
        seen.clear()
        plusone.ask(agent, "n+1?", session="t")
        assert seen["timeout"] == plusone.TURN_TIMEOUT, agent


def test_council_caps_every_agent_turn(monkeypatch):
    seen = _capture_timeout(monkeypatch)
    for agent in ("claude", "hermes", "openclaw", "grok"):
        seen.clear()
        council.ask(agent, "one thing?", session="t")
        assert seen["timeout"] == council.TURN_TIMEOUT, agent


def test_ollama_stays_off_the_council_roster():
    """Measured 2026-08-03: load 166 on 4 cores, and the turn still timed out.
    Demoted; revisit on hardware with a GPU or spare RAM."""
    assert "ollama" not in council.DEFAULT_AGENTS
