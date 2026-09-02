"""Five small things that made the board tiring to sit in all day.

Marsita, 2026-09-02, after a session of real use:
  1) allow to close the red notice -- just X in the upper right corner
  2) restore essential info about our purpose... always visible, always
     available, first thing that you see
  3) council rota message board is missing header (all other panes have one)
  4) as you collapse that pane to the bottom please hide the filtering pills
  5) the terminal please add a text area... I want to write a long message
     without fear that it will be override
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))
import oneview                                             # noqa: E402

LOCAL = oneview.page("[]", "{}", "tok", remote=False)
REMOTE = oneview.page("[]", "{}", "", remote=True)
SRC = (ROOT / "fleet" / "bin" / "oneview.py").read_text()


# 1 -- the red notice closes
def test_the_alarm_has_a_way_to_close_it():
    assert 'id="alarmx"' in LOCAL
    assert '$("#alarmx")' in SRC


def test_dismissing_one_alarm_does_not_silence_the_next():
    """Keyed on the message, not a flag: a red bar you can permanently kill
    is a red bar that stops being a channel."""
    assert "let alarmShut" in SRC
    assert "if (line === alarmShut)" in SRC
    fn = SRC.split("function renderAlarm(){")[1].split("\n}")[0]
    assert 'alarmShut = ""' in fn, "a cleared alarm must forget its dismissal"


# 2 -- the purpose line is permanent
def test_the_purpose_line_is_always_there():
    for page in (LOCAL, REMOTE):
        assert 'id="welcome"' in page
        assert "display:flex" in page.split('id="welcome"')[1][:120]


def test_the_purpose_line_cannot_be_dismissed_away():
    assert "welcomed" not in SRC, "dismissal was permanent and hid the point"
    assert 'localStorage.setItem(\'welcomed\'' not in SRC


# 3 -- the stream has a name
def test_the_stream_pane_is_named_like_every_other_pane():
    assert "council &amp; rota" in LOCAL
    body = LOCAL.split('id="stream"')[1][:400]
    assert '<span class="title">' in body


# 4 -- pills go away with the pane
def test_a_collapsed_pane_hides_its_filters():
    assert '.pane[data-open="0"] .filters{display:none;}' in LOCAL


def test_the_title_survives_the_collapse():
    """The heading is the way back in, so it must keep its name."""
    assert '.pane[data-open="0"] h2{cursor:pointer;}' in LOCAL
    assert '.pane[data-open="0"] .title' not in LOCAL


# 5 -- a composer the session cannot trample
def test_the_terminal_has_a_box_the_agent_cannot_write_into():
    assert '<form id="compose">' in LOCAL
    assert 'id="composeBox"' in LOCAL


def test_the_composer_is_local_only_like_the_terminal():
    assert '<form id="compose">' not in REMOTE
    assert 'id="composeBox"' not in REMOTE


def test_a_multiline_message_arrives_as_one_message():
    """Without bracketed paste each newline submits its own half-written
    turn."""
    assert "\\x1b[200~" in SRC and "\\x1b[201~" in SRC


def test_enter_sends_and_shift_enter_is_a_newline():
    assert 'e.key === "Enter" && !e.shiftKey' in SRC


def test_the_composer_goes_away_with_the_pane():
    assert '#termpane[data-open="0"] #compose{display:none;}' in LOCAL
