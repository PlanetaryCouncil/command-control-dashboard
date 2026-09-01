"""The line must never go quiet just because a vendor stopped paying.

2026-09-01: grok answered every request with 402 Payment Required for four
days. dispatch() asked grok, got the refusal back as text, and handed the
operator "(no output) Internal error..." -- which reads exactly like a dead
fleet. It was a dead wallet.
"""
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "fleet" / "bin"
sys.path.insert(0, str(BIN))
import telegram  # noqa: E402


def test_a_vendor_out_of_credit_falls_through_to_a_free_one(monkeypatch):
    monkeypatch.setattr(telegram, "telegram_agent", lambda: "grok")
    monkeypatch.setattr(telegram, "_answer_chain", lambda: ["grok", "hermes"])
    monkeypatch.setitem(
        telegram.DISPATCH, "grok",
        lambda t, to: "(no output)\nAPI error (status 402 Payment Required)")
    monkeypatch.setitem(telegram.DISPATCH, "hermes", lambda t, to: "the pile is empty")

    out = telegram.dispatch("what is waiting?")
    assert "the pile is empty" in out
    # and it says who could not answer, so the operator knows to top up
    assert "grok" in out


def test_the_operator_is_told_when_nobody_can_answer(monkeypatch):
    monkeypatch.setattr(telegram, "_answer_chain", lambda: ["grok", "hermes"])
    for a in ("grok", "hermes"):
        monkeypatch.setitem(telegram.DISPATCH, a, lambda t, to: "(no output)")
    out = telegram.dispatch("anyone home?")
    assert "every agent refused" in out
    assert "grok" in out and "hermes" in out


def test_a_working_vendor_answers_plainly(monkeypatch):
    """No fallback happened, so no apology is prepended."""
    monkeypatch.setattr(telegram, "_answer_chain", lambda: ["grok", "hermes"])
    monkeypatch.setitem(telegram.DISPATCH, "grok", lambda t, to: "467 passed")
    assert telegram.dispatch("tests?") == "467 passed"


def test_hermes_always_closes_the_chain(monkeypatch):
    """Local and free: it cannot be the reason the line goes quiet."""
    monkeypatch.setattr(telegram, "telegram_agent", lambda: "claude")
    monkeypatch.setattr(telegram.sys, "path", telegram.sys.path)
    assert telegram._answer_chain()[-1] == "hermes"


def test_a_quota_refusal_is_not_mistaken_for_an_answer():
    assert telegram._is_silence("(no output)\nquota exceeded")
    assert telegram._is_silence("API error (status 402 Payment Required)")
    assert telegram._is_silence("")
    assert not telegram._is_silence("the pile is empty")
