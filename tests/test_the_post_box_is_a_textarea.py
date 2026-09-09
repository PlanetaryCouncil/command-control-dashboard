"""The box you post to the board with is a textarea you can see into.

Marsita, 2026-09-09: "Lost the bottom text area for the blog. I thought I had a
text area where I can type directly in the native field."

Two separate things had gone wrong.

The one she noticed: the compose box under the terminal pane, removed on
2026-09-05 with the terminal itself, because it typed into a pty and the pty
round trip was the thing she called unworkable. That is not coming back --
there is nothing left for it to type into.

The one she was actually reaching for: `#sayBody`, which posts to the board,
had always been a one-line `<input maxlength="3900"`. It accepted a blog post
and showed about sixty characters of it, so anything longer than a sentence
was written blind.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import oneview            # noqa: E402

ARGS = ("[]", "[]", "tok")


def test_it_is_a_textarea_not_a_one_line_input():
    page = oneview.page(*ARGS, remote=False)
    assert '<textarea id="sayBody"' in page
    assert '<input id="sayBody"' not in page


def test_it_still_takes_a_whole_post():
    assert 'maxlength="3900"' in oneview.page(*ARGS, remote=False)


def test_it_grows_with_what_is_typed_and_then_stops():
    """Unbounded, a long post pushes the stream off the screen; fixed, it is
    the input again with extra steps."""
    src = (BIN / "oneview.py").read_text()
    assert "box.addEventListener(\"input\", grow);" in src
    assert "Math.min(box.scrollHeight, innerHeight * 0.33)" in src


def test_enter_posts_and_shift_enter_is_a_newline():
    """A textarea swallows Enter by default. Without this the post button is
    the only way out, which is worse than the input it replaced."""
    src = (BIN / "oneview.py").read_text()
    i = src.index('box.addEventListener("keydown"')
    body = src[i:i + 300]
    assert 'e.key === "Enter" && !e.shiftKey' in body
    assert "form.requestSubmit();" in body


def test_posting_resets_the_height():
    """Cleared but still four lines tall is a box that lies about its state."""
    src = (BIN / "oneview.py").read_text()
    assert src.count("window.__sayGrow?.();") == 2, "one per send path"


def test_the_retired_compose_box_stays_retired():
    """It typed into a pty. There is no pty."""
    page = oneview.page(*ARGS, remote=False)
    assert 'id="composeBox"' not in page


def test_collapsing_the_stream_does_not_take_the_box_with_it():
    """The pane you collapse to get the LIST out of the way was also hiding
    the box you write in. Marsita, 2026-09-09: "It used to be there (I saw in
    tab you control) but not anymore after reload" -- her stream was collapsed
    from an earlier session and mine was not, so the box existed for exactly
    one of us."""
    src = (BIN / "oneview.py").read_text()
    assert '.pane[data-open="0"] form:not(#say),' in src
    assert '#stream[data-open="0"] #say{display:flex !important;}' in src


def test_collapsing_does_not_unfold_the_signature_pad():
    """Collapsing a pane should never expand something inside it."""
    src = (BIN / "oneview.py").read_text()
    assert '#stream[data-open="0"] #say #sayMore{display:none;}' in src


def test_the_stream_has_a_floor_the_terminal_pane_must_respect():
    """A saved --hTerm of 537px in a shorter column crushed the stream to TWO
    pixels. The box still laid out, at full height, entirely outside the
    pane -- so it measured fine and could not be seen. Marsita: "Still no text
    area... strange". Nothing was hidden; it was squeezed out."""
    src = (BIN / "oneview.py").read_text()
    assert "#termpane{flex:0 1 var(--hTerm,50%);min-height:80px;}" in src, \
        "termpane cannot shrink, so nothing can give way"
    assert "#stream{min-height:74px;}" in src, "no floor"


def test_a_collapsed_stream_gives_its_floor_back():
    """Shut on purpose is not the same as squeezed by accident."""
    assert '#stream[data-open="0"]{min-height:0;}' in (BIN / "oneview.py").read_text()
