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
    assert 'sizes: "above"' in page      # the terminal, above its grip
    assert 'sizes: "below"' in page      # the artwork, below its grip
    assert 'const dir = opts.sizes === "above" ? 1 : -1;' in page


def test_the_drag_measures_the_pane_rather_than_parsing_the_variable():
    """The default is "50%" and parseInt("50%") is 50, so the first drag
    snapped a half-height pane to fifty pixels."""
    page = oneview.page(*ARGS, remote=False)
    assert "pane.getBoundingClientRect().height" in page


def test_dragging_under_a_tenth_collapses_instead_of_squeezing():
    page = oneview.page(*ARGS, remote=False)
    assert "const SHUT = 48;" in page
    assert "if (shutSelf)              setPaneOpen(pane, false, false);" in page


def test_a_collapsed_pane_leaves_a_bar_you_can_click_back():
    """Hiding the divider made the pane unrecoverable without a reload."""
    page = oneview.page(*ARGS, remote=False)
    assert '#termpane[data-open="0"]+.griph{height:7px;cursor:pointer;}' in page
    assert 'if (t && t.dataset.open === "0") toggleTerm();' in page


def test_collapsing_the_stream_gives_the_column_to_the_terminal():
    """Collapsing the thing you are not reading should give the space to the
    thing you are working in, not leave a hole."""
    page = oneview.page(*ARGS, remote=False)
    # One rule for every pane now, rather than a selector per pane.
    assert '.col:has(.pane[data-open="0"]) .pane:not([data-open="0"]){flex:1;}' in page
    assert 'other: "#stream"' in page


def test_one_grip_shuts_whichever_pane_is_being_crushed():
    page = oneview.page(*ARGS, remote=False)
    assert "const shutSelf = h <= SHUT;" in page
    assert "const shutOther = other && h >= col - SHUT;" in page


def test_a_collapsed_stream_keeps_a_heading_to_click_back():
    page = oneview.page(*ARGS, remote=False)
    assert '.pane[data-open="0"] h2{cursor:pointer;}' in page
    assert 'pane.dataset.open === "0" && !e.target.closest("button")' in page


def test_the_drag_does_not_write_to_storage_on_every_move():
    """A JSON parse, stringify and synchronous localStorage write per mouse
    move is what made the divider feel like it was chewing on something."""
    page = oneview.page(*ARGS, remote=False)
    assert "function applyHeight(h, varName)" in page
    assert "saveLayout(patch);" in page
    moves = page.split("const move = m =>")[1].split("const up =")[0]
    assert "localStorage" not in moves and "saveLayout" not in moves


def test_the_drag_measures_once_and_paints_on_a_frame():
    """Reading layout inside a pointermove forces a reflow on every event,
    against a size the same handler is changing."""
    page = oneview.page(*ARGS, remote=False)
    assert "requestAnimationFrame(paint)" in page
    assert "const col = grip.parentElement.getBoundingClientRect().height" in page


def test_collapsing_has_hysteresis():
    """One threshold means a hand resting on the line toggles many times a
    second, which reads as the board flickering."""
    page = oneview.page(*ARGS, remote=False)
    assert "const REOPEN = 96;" in page
    assert "else if (h >= REOPEN)      setPaneOpen(pane, true, false);" in page


def test_a_pasted_image_becomes_a_file_and_then_a_path():
    """Claude reads images by path, so a screenshot has to become a file
    before it can become context. /api/paste-image already existed and
    nothing on this page had ever called it."""
    page = oneview.page(*ARGS, remote=False)
    assert 'fetch("api/paste-image"' in page
    assert 'i.type.startsWith("image/")' in page
    assert 'ws.send(JSON.stringify({t: "input", d: out.path + " "}))' in page


def test_the_paste_listener_is_on_xterms_own_textarea():
    """A handler on the container only sees the paste if xterm lets it
    bubble, which it does not always do."""
    page = oneview.page(*ARGS, remote=False)
    assert "const pasteTarget = term.textarea || term_el;" in page


def test_pasting_text_is_left_alone():
    """Only images are intercepted; ordinary paste stays xterm's business."""
    page = oneview.page(*ARGS, remote=False)
    assert "if (!shot) return;" in page


def test_the_path_is_typed_not_sent():
    """A path arriving on its own line as a finished message is a question
    nobody asked."""
    page = oneview.page(*ARGS, remote=False)
    assert "Type the path in, do not send it." in page
