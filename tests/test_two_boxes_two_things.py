"""Talking to Claude and posting to the board are two different things.

Marsita, 2026-09-09: "Talking to the board is a different thing than talking
to Claude. Talking to Claude is the dedicated function. I talk to Claude
directly, and I post to the text area. The bottom is if I want to talk with
the board and something else. They are two different functionalities."

They were never deliberately merged. The Claude box was removed on 2026-09-05
with the terminal it typed into, and when she said the text area was missing I
improved the only box still on the page -- the board's -- four times, without
once noticing it was not the one she had lost.

These tests make the two boxes structurally impossible to confuse.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import oneview            # noqa: E402
import terminal           # noqa: E402

ARGS = ("[]", "[]", "tok")


def test_there_are_two_boxes():
    page = oneview.page(*ARGS, remote=False)
    assert 'id="tellBox"' in page, "no box for Claude"
    assert 'id="sayBody"' in page, "no box for the board"


def test_they_live_in_different_panes():
    """Claude's belongs to the pane showing Claude; the board's to the pane
    showing the board. Neither is reachable by collapsing the other."""
    page = oneview.page(*ARGS, remote=False)
    claude_pane = page.index('id="termpane"')
    stream_pane = page.index('id="stream"')
    assert claude_pane < page.index('id="tellBox"') < stream_pane
    assert stream_pane < page.index('id="sayBody"')


def test_they_post_to_different_endpoints():
    src = (BIN / "oneview.py").read_text()
    assert 'fetch("api/tell"' in src           # Claude
    assert "/api/signals" in src               # the board


def test_talking_to_claude_never_reaches_the_public_board():
    """The board is public. A line meant for Claude landing there is not a
    layout bug, it is a disclosure."""
    src = (BIN / "oneview.py").read_text()
    i = src.index('const form = $("#tell");')
    body = src[i:i + 1600]
    assert "signals" not in body
    assert "sayBody" not in body


# --------------------------------------------------------------- the send
def test_the_text_is_typed_literally_not_pressed():
    """Without `-l`, tmux reads the text as key NAMES -- a message containing
    the word "Enter" or "C-c" would be pressed rather than typed."""
    src = (BIN / "terminal.py").read_text()
    i = src.index("def send(")
    assert '"send-keys", "-t", name, "-l", text' in src[i:i + 2000]


def test_enter_is_sent_separately_after_the_text():
    src = (BIN / "terminal.py").read_text()
    i = src.index("def send(")
    body = src[i:i + 2000]
    # The CALLS, not the docstring -- which says "press Enter" three lines in.
    assert (body.index('"send-keys", "-t", name, "-l", text')
            < body.index('"send-keys", "-t", name, "Enter"'))


def test_an_empty_send_is_refused_before_it_reaches_tmux(monkeypatch):
    monkeypatch.setattr(terminal, "tmux_bin",
                        lambda: (_ for _ in ()).throw(AssertionError("called")))
    assert terminal.send("board", "   ") == "nothing to send"


def test_no_tmux_is_a_reason_not_an_exception(monkeypatch):
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "")
    assert terminal.send("board", "hello") == "no tmux on this machine"


def test_a_missing_session_is_started_rather_than_refused(monkeypatch):
    """A box that says "no session" asks the operator to go and do sysadmin
    before they are allowed to talk."""
    src = (BIN / "terminal.py").read_text()
    i = src.index("def send(")
    body = src[i:i + 2000]
    assert "if not tmux_has(name):" in body
    assert "attach(name, cwd" in body


def test_the_endpoint_is_local_only():
    src = (BIN / "fleet.py").read_text()
    assert '"/api/tell",' in src, "not in CONTROL_PATHS"
    i = src.index('if path == "/api/tell":')
    assert "self._remote()" in src[i:i + 900]


def test_a_failed_send_keeps_your_words():
    """Losing a paragraph to a dropped request is the one thing a send-only
    box must never do."""
    src = (BIN / "oneview.py").read_text()
    i = src.index('const form = $("#tell");')
    body = src[i:i + 1600]
    assert "if (d.ok){ box.value = \"\"; grow(); }" in body
    assert body.index("await fetch") < body.index('box.value = ""')
