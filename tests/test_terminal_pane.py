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
    assert 'if ($("#termpane")){' in page
    assert "if (wanted !== 0) toggleTerm();" in page


def test_the_grip_is_wired_only_when_it_exists():
    """A remote render omits the grip; wiring a missing element throws and
    takes every pane below it down."""
    page = oneview.page(*ARGS, remote=False)
    assert 'if ($("#gripT")){' in page
    assert 'dragGripV($("#gripT")' in page


def test_the_grip_knows_which_side_its_pane_is_on():
    """--hArt sizes the pane below its grip; --hTerm sizes the pane above.
    One shared drag function assumed the first, so the terminal divider moved
    opposite to the mouse."""
    page = oneview.page(*ARGS, remote=False)
    assert "growsDown: true" in page
    assert "const dir = opts.growsDown ? 1 : -1;" in page


def test_the_drag_measures_the_pane_rather_than_parsing_the_variable():
    """The default is "50%" and parseInt("50%") is 50, so the first drag
    snapped a half-height pane to fifty pixels."""
    page = oneview.page(*ARGS, remote=False)
    assert "pane.getBoundingClientRect().height" in page


def test_dragging_under_a_tenth_collapses_instead_of_squeezing():
    page = oneview.page(*ARGS, remote=False)
    assert "collapseBelow: 0.10" in page
    assert "setPaneOpen(pane, false)" in page


def test_a_collapsed_pane_leaves_a_bar_you_can_click_back():
    """Hiding the divider made the pane unrecoverable without a reload."""
    page = oneview.page(*ARGS, remote=False)
    assert '#termpane[data-open="0"]+.griph{height:7px;cursor:pointer;}' in page
    assert 'if (t && t.dataset.open === "0") toggleTerm();' in page


def test_collapsing_the_stream_gives_the_column_to_the_terminal():
    """Collapsing the thing you are not reading should give the space to the
    thing you are working in, not leave a hole."""
    page = oneview.page(*ARGS, remote=False)
    assert '.col:has(#stream[data-open="0"]) #termpane{flex:1;}' in page
    assert 'other: "#stream"' in page


def test_one_grip_shuts_whichever_pane_is_being_crushed():
    page = oneview.page(*ARGS, remote=False)
    assert "if (h < col * opts.collapseBelow){ setPaneOpen(pane, false); return; }" in page
    assert "if (h > col * (1 - opts.collapseBelow)){" in page


def test_a_collapsed_stream_keeps_a_heading_to_click_back():
    page = oneview.page(*ARGS, remote=False)
    assert '#stream[data-open="0"] h2{cursor:pointer;}' in page
    assert 'st.dataset.open === "0" && !e.target.closest("button")' in page
