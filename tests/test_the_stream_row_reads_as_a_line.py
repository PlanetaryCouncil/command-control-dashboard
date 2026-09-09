"""When, what kind, who, what they said -- in that order, on one row.

Marsita, 2026-09-09: "include YYYY-MM-DD HH:MM (no SS) timestamp. Timestamp \\t
who \\t message. Category of the message to be represented with emoji."
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

SRC = (BIN / "oneview.py").read_text()


def test_the_stamp_is_a_date_and_a_clock_to_the_minute():
    i = SRC.index("const hhmm  = iso =>")
    body = SRC[i:i + 400]
    assert "d.getFullYear()" in body
    assert "getSeconds" not in body, "seconds are back"


def test_the_row_is_four_columns_in_order():
    assert "row.append(t, icon, w, m);" in SRC


def test_the_message_flexes_and_the_chrome_does_not():
    """Fixed chrome is what makes a run of rows read as a column when the
    messages are ragged."""
    i = SRC.index(".ev{display:flex;")
    body = SRC[i:i + 900]
    assert ".ev .t{flex:none" in body
    assert ".ev .who{flex:none" in body
    assert ".ev .m{flex:1" in body


def test_one_emoji_per_row_and_it_means_the_category():
    """The name used to carry the agent's emoji as well, which put two on a
    row next to the tag icon."""
    i = SRC.index('const w = document.createElement("span"); w.className="who";')
    body = SRC[i:i + 800]
    assert "w.textContent = e.agent;" in body
    assert "emoji(e.agent) + " not in body
    assert 'icon.textContent = TAG_ICON[tag]' in body


def test_a_row_with_no_known_tag_still_gets_a_mark():
    """An empty column is a hole in the run; a dot is not."""
    i = SRC.index("icon.textContent = TAG_ICON[tag]")
    assert '|| "·"' in SRC[i:i + 120]


def test_the_day_divider_is_gone_because_every_row_says_the_date():
    i = SRC.index("function dayDivider(iso){")
    assert "return null;" in SRC[i:i + 400]
    assert "el.className = \"daybar\"" not in SRC


def test_collapsing_the_stream_takes_the_post_box_with_it():
    """It was briefly kept alive in a collapsed pane, on the theory that the
    box was the reason the pane existed. The box she could not find was
    Claude's, which has its own pane now. Marsita, looking at the leftover
    row: "collapse, it looks ugly"."""
    assert '.pane[data-open="0"] .body,.pane[data-open="0"] form,' in SRC
    assert '#stream[data-open="0"] #say{display:flex !important;}' not in SRC


def test_the_chrome_leaves_room_for_the_message():
    """It was 219px of a 528px pane -- 41% of every row spent saying when and
    who before a word of what, and a message starting that far right wraps
    into a deep empty gutter that reads as a gap in the log rather than a long
    line. Marsita, 2026-09-09: "seems like a gap"."""
    i = SRC.index(".ev{display:flex;")
    body = SRC[i:i + 800]
    assert ".ev .who{flex:none;width:58px" in body
    assert "font-size:8.5px" in body
