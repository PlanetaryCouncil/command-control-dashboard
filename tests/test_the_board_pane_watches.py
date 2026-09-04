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
