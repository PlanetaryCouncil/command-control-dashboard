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
    """The #tellBox closure."""
    i = SRC.index('const box = $("#tellBox")')
    return SRC[i:SRC.index("})();", i)]


def test_the_endpoint_is_still_there():
    assert '"/api/paste-image"' in SERVER


def test_a_pasted_image_is_uploaded():
    t = _tell()
    assert 'box.addEventListener("paste"' in t
    assert 'fetch("api/paste-image"' in t


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
    assert "box.value = box.value.slice(0, at)" in t
    assert "form.requestSubmit()" not in t.split("async function upload")[1].split("}")[0]


def test_the_cursor_ends_after_the_path():
    t = _tell()
    assert "box.selectionStart = box.selectionEnd = at" in t


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
    assert 'pnote("upload failed")' in t
