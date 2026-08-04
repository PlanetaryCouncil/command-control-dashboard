"""The relay must not report a harness failure as an agent's answer.

Found by the council on 2026-08-01, restated by it on 2026-08-02, and still live
when this was written: hops recorded `got: 300` alongside
`raw: "[timed out after 300s]"`. The 300 is the timeout in seconds — a string
this harness writes about the agent — presented as the number the agent replied
with.

That matters more than a cosmetic mislabel. The whole claim of the plus-one
experiment is that a value cannot be emitted without having been received, which
is what makes it self-verifying with no control arm. A silent agent that scores
as a wrong answer, and a reseed that is not recorded, both make that claim
untestable while leaving the board looking merely imperfect.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fleet" / "bin"))
import plusone  # noqa: E402


EXPECTED = 48923


@pytest.mark.parametrize("raw", [
    "[timed out after 300s]",
    "[timed out after 420s]",
    "[error] connection refused on port 8080",
    "[unknown agent nobody]",
])
def test_harness_failures_are_not_answers(raw):
    """Every one of these contains digits. None of them is a reply."""
    assert plusone.extract_number(raw, EXPECTED) is None


def test_the_exact_bug_the_council_found():
    """A 300-second timeout must not be recorded as the agent saying 300."""
    raw = "[timed out after 300s]"
    got = plusone.extract_number(raw, EXPECTED)
    assert got != 300
    assert got is None
    assert plusone.outcome_of(raw, got, ok=False) == "timeout"


def test_silence_and_wrongness_are_told_apart():
    """Different faults need different responses — one agent is broken, the
    other is confused, and `ok: false` alone cannot say which."""
    assert plusone.outcome_of("[timed out after 300s]", None, False) == "timeout"
    assert plusone.outcome_of("I think it is 77", 77, False) == "wrong"
    assert plusone.outcome_of("no idea, sorry", None, False) == "silent"
    assert plusone.outcome_of("48923", EXPECTED, True) == "ok"


def test_a_real_answer_still_reads_correctly():
    """The fix must not make the relay blind to working agents."""
    assert plusone.extract_number("that would be 48923", EXPECTED) == EXPECTED
    assert plusone.extract_number("48,923", EXPECTED) == EXPECTED
    assert plusone.outcome_of("that would be 48923", EXPECTED, True) == "ok"


def test_a_failure_message_containing_the_right_number_is_still_a_failure():
    """The nastiest case: a timeout string that happens to contain the expected
    value would otherwise score as a pass, which is a false green."""
    raw = f"[timed out after {EXPECTED}s]"
    assert plusone.extract_number(raw, EXPECTED) is None
