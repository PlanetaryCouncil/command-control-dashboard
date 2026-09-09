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


def test_it_looks_like_a_textarea_at_rest():
    """It already WAS one and looked exactly like the input it replaced --
    Marsita, looking straight at it: "where?". A box you cannot tell from a
    field is a box nobody knows they have."""
    src = (BIN / "oneview.py").read_text()
    i = src.index("#sayBody{flex:1;")
    assert "height:52px;min-height:52px" in src[i:i + 400]


def test_it_never_shrinks_below_three_lines():
    src = (BIN / "oneview.py").read_text()
    assert "Math.max(FLOOR, Math.min(box.scrollHeight" in src


def test_the_stream_is_no_longer_propped_open_for_this_box():
    """Both props -- keeping #say alive in a collapsed pane, and a min-height
    floor so the terminal pane could not squeeze it -- existed because this
    was mistaken for the box Marsita had lost. That box was Claude's, and it
    has its own pane now (test_two_boxes_two_things.py). The props go, and
    collapse means collapse."""
    src = (BIN / "oneview.py").read_text()
    assert "#stream{min-height:104px;}" not in src
    assert '#stream[data-open="0"] #say{display:flex !important;}' not in src
