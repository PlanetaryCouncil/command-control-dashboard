"""A screenshot should reach the machine it is a screenshot of, directly.

Marsita, 2026-09-17: "I would like to paste images here in the console... Last
time I posted to twitter and shared link here." Posting to a social network to
get a file onto your own laptop is a detour nobody should have to take.

/api/paste-image never went away -- only the browser handler did, when the
in-page terminal was retired. This wires it to the compose box.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = (REPO / "fleet" / "bin" / "oneview.py").read_text()
SERVER = (REPO / "fleet" / "bin" / "fleet.py").read_text()


def _tell():
    """The paste wiring, plus the #tellBox closure that uses it.

    The handlers used to live inline in the #tellBox closure. Pane two
    needed the same behaviour, so they moved into wireImagePaste(box, grow)
    and both panes call it. Slicing forward from #tellBox alone stopped
    seeing them -- the code had moved ABOVE the thing this sliced from,
    which is why fifteen tests failed at once for a feature that works.
    """
    i = SRC.index("function wireImagePaste(")
    j = SRC.index('const box = $("#tellBox")')
    return SRC[i:SRC.index("})();", j)]


def test_the_endpoint_is_still_there():
    assert '"/api/paste-image"' in SERVER


def test_a_pasted_image_is_uploaded():
    t = _tell()
    assert 'box.addEventListener("paste"' in t
    # fetchT is fetch with a deadline; either spelling is the same endpoint.
    assert ('fetchT("api/paste-image"' in t
            or 'fetch("api/paste-image"' in t)


def test_a_dropped_image_is_uploaded_too():
    """The other way a screenshot arrives."""
    t = _tell()
    assert 'box.addEventListener("drop"' in t
    assert 'box.addEventListener("dragover"' in t


def test_a_plain_text_paste_is_left_alone():
    """Hijacking every paste would break pasting a path or a log line."""
    t = _tell()
    assert "if (!files.length) return;" in t
    # and the default is only prevented once there is an image to handle
    assert t.index("if (!files.length) return;") < t.index("e.preventDefault();")


def test_only_images_are_taken():
    t = _tell()
    assert 'f.type.startsWith("image/")' in t


def test_the_path_lands_in_the_box_and_is_not_sent():
    """It is usually part of a sentence you are still writing."""
    t = _tell()
    assert "function insertAtCursor(" in t
    assert "form.requestSubmit()" not in t.split("async function upload")[1].split("\n  }")[0]


def test_a_placeholder_goes_in_immediately():
    """Marsita, 2026-09-18: "massive delay on pasting images from clip...
    taking ages and then inserts as I type". Base64 of a few megabytes plus
    the round trip is a second or more, and writing the path at the cursor
    whenever it finished landed it in the middle of the next sentence."""
    t = _tell()
    i = t.index("async function upload(")
    fn = t[i:t.index("\n  }", i)]
    assert 'const token = "[### " + nextImgN() + "]"' in fn
    assert fn.index("insertAtCursor(token)") < fn.index("await file.arrayBuffer()")


def test_the_upload_rewrites_the_token_not_the_cursor():
    """By the time it lands the token has moved -- that is the whole point."""
    t = _tell()
    assert "function replaceToken(" in t
    i = t.index("function replaceToken(")
    fn = t[i:t.index("\n  }", i)]
    assert "box.value.indexOf(token)" in fn


def test_a_rewrite_behind_the_caret_does_not_move_you_forward():
    t = _tell()
    i = t.index("function replaceToken(")
    fn = t[i:t.index("\n  }", i)]
    assert "if (caret > at)" in fn


def test_a_token_you_deleted_is_left_alone():
    t = _tell()
    i = t.index("function replaceToken(")
    fn = t[i:t.index("\n  }", i)]
    assert "if (at === -1) return;" in fn


def test_the_count_survives_a_reload():
    """"keep count for posterity"."""
    t = _tell()
    assert 'IMG_N_KEY = "img.count"' in t
    assert "localStorage.setItem(IMG_N_KEY" in t


def test_a_broken_counter_still_pastes():
    """localStorage throws in a private window; a number is never worth the
    feature."""
    t = _tell()
    i = t.index("function nextImgN(")
    fn = t[i:t.index("\n  }", i)]
    assert fn.count("catch (e) {}") >= 2


def test_a_failed_upload_leaves_the_token_visible():
    """Silently removing something you watched yourself paste is worse than
    leaving a mark that says it failed."""
    t = _tell()
    assert "(upload failed)" in t
    i = t.index("async function upload(")
    fn = t[i:t.index("\n  }", i)]
    assert "replaceToken(token, token + \" (upload failed)\")" in fn


def test_a_huge_file_is_refused_with_a_reason():
    """Otherwise a video dropped by accident looks like a hang."""
    t = _tell()
    m = re.search(r"file\.size > (\d+) \* 1024 \* 1024", t)
    assert m and int(m.group(1)) <= 20
    assert "too big" in t


def test_base64_is_chunked():
    """btoa over one big string blows the argument limit on a real screenshot."""
    t = _tell()
    assert "i += 0x8000" in t
    assert "subarray(i, i + 0x8000)" in t


def test_a_failure_says_so_in_the_box():
    t = _tell()
    assert "(upload failed)" in t
