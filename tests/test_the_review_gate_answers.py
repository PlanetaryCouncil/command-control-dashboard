"""Silence is not a rejection.

Nothing merged between 2026-09-01 and 2026-09-04. The tests were passing the
whole time -- "991 passed" sits in the pipeline log next to every failure. What
failed was the reviewer, in three distinct ways, all visible in
fleet/rota/pipeline.jsonl:

    "no reviewer produced a verdict"
    "[stderr] jetski: no output produced -- a tool required the 'command'
     permission that headless mode cannot prompt for, so it was auto-denied"
    "I'll load the brief and inspect the merged change against the
     surrounding fleet-model wiring."

An empty answer, a tool the sandbox denied, and a preamble from an agent about
to start work. All three were scored as REJECT by
`.strip().upper().startswith("APPROVE")`, and the branch was blamed for the
roster.
"""

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import pipeline  # noqa: E402


def test_a_plain_verdict_is_read():
    assert pipeline.verdict_of("APPROVE tests pass and the scope is tight")
    assert pipeline.verdict_of("REJECT this touches three unrelated files") is False


def test_a_verdict_below_a_preamble_still_counts():
    """Agents narrate. The word is what matters, not the line it lands on."""
    assert pipeline.verdict_of("Verdict:\nAPPROVE\nbecause the tests pass")
    assert pipeline.verdict_of("**REJECT** - too broad") is False


def test_silence_is_not_a_rejection():
    assert pipeline.verdict_of("") is None
    assert pipeline.verdict_of(None) is None


def test_a_denied_tool_is_not_a_rejection():
    assert pipeline.verdict_of(
        '[stderr] jetski: no output produced - a tool required the "command" '
        "permission that headless mode cannot prompt for") is None


def test_an_agent_about_to_start_has_not_said_no():
    assert pipeline.verdict_of(
        "I'll load the brief and inspect the merged change against the "
        "surrounding fleet-model wiring.") is None


def test_the_brief_tells_the_reviewer_not_to_reach_for_tools():
    """It has the whole diff already, and a tool call in headless mode is
    auto-denied -- which is how a reviewer produced nothing at all."""
    src = (BIN / "pipeline.py").read_text()
    assert "Do NOT use any tool" in src
    assert "auto-denied" in src


def test_a_silent_reviewer_gets_replaced_not_obeyed():
    others = pipeline._other_reviewers("agy")
    assert others, "no fallback reviewer at all"
    assert "agy" not in others
    assert "ollama" not in others, "a local model is not a second opinion"


def test_the_fallback_stays_independent_of_the_builder(monkeypatch):
    monkeypatch.setenv("FLEET_BUILDER", "grok")
    assert "grok" not in pipeline._other_reviewers("agy")
