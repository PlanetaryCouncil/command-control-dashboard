"""The terminal is a pane in the middle column, above the stream.

It used to slide up over the board as a drawer, so using it meant losing
sight of the stream -- the two things you most want together, because the
terminal is where you act and the stream is where the fleet answers.
"""
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "fleet" / "bin"
sys.path.insert(0, str(BIN))
import oneview  # noqa: E402

ARGS = ("[]", "[]", "tok")


def test_the_terminal_sits_above_the_stream():
    page = oneview.page(*ARGS, remote=False)
    for el in ('id="termpane"', 'id="gripT"', 'id="stream"'):
        assert el in page, f"missing {el}"
    assert page.index('id="termpane"') < page.index('id="stream"'), \
        "the terminal must render above the stream, not below it"


def test_a_remote_visitor_gets_no_terminal_pane():
    page = oneview.page(*ARGS, remote=True)
    for el in ('id="termpane"', 'id="gripT"', 'id="term"'):
        assert el not in page, f"{el} rendered for a remote visitor"


def test_the_pane_starts_closed_and_is_opened_by_the_boot_call():
    """Rendering it open and then calling the opener would toggle it shut --
    two states pretending to be one."""
    page = oneview.page(*ARGS, remote=False)
    assert 'id="termpane" data-open="0"' in page
    assert 'if ($("#termpane")) toggleTerm();' in page


def test_the_grip_is_wired_only_when_it_exists():
    """A remote render omits the grip; wiring a missing element throws and
    takes every pane below it down."""
    assert 'if ($("#gripT")) dragGripV(' in oneview.page(*ARGS, remote=False)
