"""The board pane answers one question -- is it done yet? -- and takes no keys.

Marsita drives from the laptop terminal; the browser watches and has a box to
send into it. These tests hold the two halves of that: the state the pane shows
comes from the session's own screen, and nothing on the page can put a
keystroke into the pseudo-terminal except a deliberate send.
"""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import terminal            # noqa: E402
import termview            # noqa: E402


# ------------------------------------------------------------------- the state
def test_a_spinner_means_working():
    assert terminal.classify("some output\n· Thinking… (12s · esc to interrupt)") == "working"


def test_a_permission_prompt_means_waiting_for_you():
    pane = "Bash(rm -rf x)\nDo you want to proceed?\n❯ 1. Yes\n  2. No"
    assert terminal.classify(pane) == "waiting"


def test_a_quiet_prompt_is_idle():
    assert terminal.classify("> \n\n  ? for shortcuts") == "idle"


def test_the_state_is_read_from_the_tail_not_the_history():
    """A spinner from an hour ago is not what is happening now."""
    old = "· Working… (esc to interrupt)\n" + "\n".join(str(i) for i in range(40))
    assert terminal.classify(old) == "idle"


def test_an_empty_screen_is_idle_not_a_crash():
    assert terminal.classify("") == "idle"


# ---------------------------------------------------------------- the estimate
def test_no_history_means_no_guess(tmp_path):
    assert terminal.estimate(tmp_path / "nothing.jsonl") is None


def test_the_guess_is_a_median_so_one_long_turn_cannot_move_it(tmp_path):
    log = tmp_path / "turns.jsonl"
    for s in (30, 32, 34, 36, 9999):
        terminal.record_turn(s, log)
    assert terminal.estimate(log) == 34


def test_a_blip_is_not_a_turn(tmp_path):
    """Half a second of spinner is noise; recording it would drag the guess down."""
    log = tmp_path / "turns.jsonl"
    terminal.record_turn(0.4, log)
    assert not log.exists()


def test_a_corrupt_line_does_not_take_the_history_with_it(tmp_path):
    log = tmp_path / "turns.jsonl"
    terminal.record_turn(10, log)
    with log.open("a") as fh:
        fh.write("not json\n")
    terminal.record_turn(20, log)
    assert terminal.estimate(log) == 15


# ------------------------------------------------------------------ one poller
def test_one_watch_per_session_however_many_tabs():
    """Two browsers must not write one turn into the history twice."""
    assert terminal.watch("board") is terminal.watch("board")
    assert terminal.watch("board") is not terminal.watch("other")


def test_the_frame_carries_what_the_pane_draws():
    frame = terminal.watch("test-shape").poll()
    assert frame["t"] == "state"
    assert set(frame) == {"t", "state", "since", "estimate"}


# -------------------------------------------------------------- no keys, ever
def test_the_screen_takes_no_keystrokes():
    """`term.onData(...)` is the line that piped every key into the pty. Gone.

    Matched as a CALL, not a mention: the comment explaining why it is absent
    contains the name, and a test that forbids the name forbids the comment.
    """
    assert "term.onData(" not in termview.JS
    assert "disableStdin = true" in termview.JS


def test_the_box_is_still_the_way_in():
    assert "function submit()" in termview.JS
    assert "sendRaw(v.includes" in termview.JS


def test_a_pasted_image_lands_in_the_box_not_the_session():
    """There is no other way in, so an upload has exactly one destination."""
    assert "ws.send(JSON.stringify({t:'input', d: d.path" not in termview.JS
    assert "box.value +=" in termview.JS


def test_the_page_says_where_the_real_terminal_is():
    page = termview.page("tok", "", "")
    assert "tmux attach -t board" in page
    assert 'id="state"' in page and 'id="clock"' in page


# --------------------------------------------------------------- scroll back
def test_history_asks_tmux_for_the_region_above_the_screen(monkeypatch):
    """Ending at -1 is the whole point: the repaint draws line 0 onwards, so
    history must stop just short of it or every screen appears twice."""
    seen = []
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")

    class R:
        returncode, stdout = 0, "older\n"

    monkeypatch.setattr(terminal.subprocess, "run",
                        lambda argv, **kw: (seen.append(argv), R)[1])
    assert terminal.history("board", 3000) == "older\n"
    assert seen[0][-4:] == ["-S", "-3000", "-E", "-1"]


def test_the_visible_screen_is_captured_without_the_history_flags(monkeypatch):
    seen = []
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")

    class R:
        returncode, stdout = 0, "now\n"

    monkeypatch.setattr(terminal.subprocess, "run",
                        lambda argv, **kw: (seen.append(argv), R)[1])
    terminal.capture("board")
    assert "-S" not in seen[0]


def test_no_tmux_means_no_history_not_a_crash(monkeypatch):
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "")
    assert terminal.history("board") == ""


def test_the_browsers_scrollback_is_no_longer_wiped_on_attach():
    """\x1b[3J clears the saved lines, which is exactly what the wheel needs."""
    src = (BIN / "terminal.py").read_text()
    assert "\\x1b[H\\x1b[2J\\x1b[3J" not in src


def test_the_pane_keeps_enough_scrollback_to_hold_the_history():
    import re
    kept = int(re.search(r"scrollback:\s*(\d+)", termview.JS).group(1))
    assert kept >= 3000


# ------------------------------------------------------------- no instructions
def test_the_compose_box_says_nothing_but_dots():
    """Marsita, 2026-09-04: "please skip the placeholder... The only
    placeholder is '...' (I know how it works)".

    A placeholder is a hint for someone who has never seen the box. She owns
    it. Explaining Enter and Shift+Enter to her every time she looks at the
    page is text she has to skip, forever, to reach a box she was already
    going to type in.
    """
    import re
    for mod in (termview.page("tok", "", ""), (BIN / "oneview.py").read_text()):
        for hint in re.findall(r'placeholder="([^"]*)"', mod):
            assert hint in ("...", "you") or hint.startswith("{"), hint


# ------------------------------------------------------------- room to breathe
def test_the_window_follows_the_biggest_viewer_not_the_smallest():
    """tmux defaults to `smallest`, which let the laptop clamp the browser and
    left two-thirds of the pane black."""
    src = (BIN / "terminal.py").read_text()
    assert '"window-size", "largest"' in src


def test_the_size_options_never_block_the_session_starting():
    """Two subprocess calls inline in __init__ delayed the end of it by
    seconds, and a session created just after the last one was killed then
    attached to the DYING one. No tmux call belongs on that path."""
    src = (BIN / "terminal.py").read_text()
    i = src.index("def __init__")
    j = src.index("def tmux_opt")
    # The CALL, not the mention: the comment explaining why none belongs here
    # names it, and a test that bans the name bans its own explanation.
    assert "subprocess.run(" not in src[i:j], "a tmux call is back in __init__"


def test_one_owner_of_the_sessions_options():
    """mouse and history were set in `configure_tmux`, size in `__init__`.
    Two owners of one session's setup is two chances to race its startup."""
    src = (BIN / "terminal.py").read_text()
    assert "_tmux_setup" not in src, "the second owner is back"
    i = src.index("def configure_tmux")
    body = src[i:i + 2500]
    for opt in ('"mouse", "on"', '"history-limit"',
                '"window-size", "largest"', '"aggressive-resize", "on"'):
        assert opt in body, opt


def test_attach_does_not_assume_it_got_a_real_session():
    """The tests fake one. A page must not 500 because of an attribute."""
    src = (BIN / "terminal.py").read_text()
    assert 'getattr(s, "tmux_name", "")' in src


def test_setting_a_tmux_option_never_takes_the_session_down(monkeypatch):
    s = terminal.Session.__new__(terminal.Session)
    s.tmux_name = "board"
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")

    def boom(*a, **k):
        raise OSError("tmux went away")

    monkeypatch.setattr(terminal.subprocess, "run", boom)
    s.tmux_opt("window-size", "largest")        # must not raise


def test_the_footer_collapses_to_a_hairline_not_a_heading_bar():
    css = (BIN / "oneview.py").read_text()
    assert '#stream[data-open="0"]>h2{' in css
    assert '#stream[data-open="0"]>h2:hover{opacity:1;}' in css, "no way back"


# --------------------------------------------------------------- the footer
def test_the_footer_collapses_to_one_word():
    src = (BIN / "oneview.py").read_text()
    assert '<div class="foottoggle" id="foottoggle">footer</div>' in src
    assert '#foot[data-open="0"]>section{display:none;}' in src


def test_open_the_handle_is_a_bar_and_says_nothing():
    """A word saying "footer" above a footer is a label for the obvious."""
    src = (BIN / "oneview.py").read_text()
    i = src.index("#foot>.foottoggle{")
    assert "font-size:0;" in src[i:i + 220], "the word still shows when open"
    assert "#foot>.foottoggle:hover::after{background:var(--info);}" in src, \
        "no blue grab handle"


def test_shut_the_word_is_the_only_thing_left_and_the_way_back():
    src = (BIN / "oneview.py").read_text()
    i = src.index('#foot[data-open="0"]>.foottoggle{')
    assert "font-size:8px" in src[i:i + 220], "the word does not come back"
    assert '#foot[data-open="0"]>.foottoggle{display:none' not in src


def test_a_project_and_its_repo_share_one_line():
    """Marsita: "prefer less vertical". Six stacked rows became three."""
    src = (BIN / "oneview.py").read_text()
    assert src.count('<span class="pair">') == 3
    # Matched as link TEXT, not as a mention: two comments explain why the
    # arrow rows went, and a test that bans the glyph bans the explanation.
    assert '">&#8627; github.com/' not in src, "the stacked arrow rows are gone"


def test_the_partnership_column_is_wider_than_the_rest():
    """Full repo URLs were being ellipsed in a one-eighth column."""
    assert '#foot section.partners{grid-column:span 2;}' in (BIN / "oneview.py").read_text()
