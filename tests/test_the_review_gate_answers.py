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


# --- a branch nobody reviewed comes back -------------------------------

def test_reopen_is_not_a_closed_stage():
    """`drop`, `land`, `verify` and friends close a proposal. A reopen must
    put it back in the queue -- on 2026-09-04 two branches sat closed and
    rejected with "991 passed" beside them, while every reviewer on the roster
    was failing on a denied tool. The code was finished. Nobody read it."""
    assert "reopen" not in pipeline.CLOSED_STAGES


def test_a_reopened_proposal_is_waiting_again():
    prop = {"ts": "2026-09-04T02:11:21Z", "text": "a real proposal"}
    closed = {prop["ts"]: {"stage": "verify", "ok": False}}
    reopened = {prop["ts"]: {"stage": "reopen", "ok": False}}
    assert pipeline.is_waiting(prop, closed) is False
    assert pipeline.is_waiting(prop, reopened) is True


def test_verify_reopens_rather_than_rejecting_when_nobody_answers():
    src = (BIN / "pipeline.py").read_text()
    block = src[src.index("def verify("):]
    assert 'record(stage="reopen"' in block
    assert "no reviewer answered" in block


def test_the_retry_is_bounded():
    """A retry that never stops is a loop. After two, a human hears about it
    instead of the queue churning quietly forever."""
    src = (BIN / "pipeline.py").read_text()
    block = src[src.index("def verify("):]
    assert "reopens >= 2" in block
    assert '"needs_you"' in block


def test_the_reviewer_is_asked_for_a_fact_check_not_a_design_review():
    """Marsita, 2026-09-04: "Fable proposes, rest signoffs? Basic
    fact-checking layer." The builder is a frontier model and the tests have
    already run; the second pair of eyes is there for things that are
    objectively wrong, not for taste."""
    src = (BIN / "pipeline.py").read_text()
    assert "This is a FACT CHECK, not a design review" in src
    assert "If nothing is factually wrong, APPROVE" in src
