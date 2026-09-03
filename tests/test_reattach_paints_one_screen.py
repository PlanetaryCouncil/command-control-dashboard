"""A reattaching page gets one screen, not the whole history repainted.

`Session.buf` is a byte LOG — every redraw the session ever emitted. Replaying
it on reattach does not restore the screen, it re-renders everything that was
ever drawn: the same conversation stacked several times down the page, two tmux
status bars, and the cursor left wherever the last replayed frame put it. Live
output then landed off-screen and the board looked frozen. Marsita, 2026-09-03:
"Currently I need to reload the browser tab with every message. Not practical."

tmux holds the one true screen. Ask it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fleet" / "bin"))

import terminal


class _FakeSession:
    """Just the surface `serve_socket` touches when a page attaches."""

    def __init__(self, tmux_name):
        self.tmux_name = tmux_name
        self.repainted = 0
        self.alive = True
        self.why = ""

    def repaint(self):
        if not self.tmux_name:
            return False
        self.repainted += 1
        return True


def test_repaint_is_a_no_op_without_tmux():
    """No tmux means nothing to ask, so the byte log is all there is."""
    assert _FakeSession("").repaint() is False


def test_repaint_asks_tmux_for_the_current_screen(monkeypatch, tmp_path):
    """The real repaint shells out to `tmux refresh-client -t <name>`."""
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(terminal.subprocess, "run", fake_run)
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")

    s = terminal.Session.__new__(terminal.Session)   # no fork
    s.tmux_name = "board"
    assert s.repaint() is True
    assert calls == [["/usr/bin/tmux", "refresh-client", "-t", "board"]]


def test_a_tmux_failure_is_not_a_dead_pane(monkeypatch):
    """tmux missing or refusing must never take the terminal down."""
    def boom(*a, **k):
        raise OSError("no tmux here")

    monkeypatch.setattr(terminal.subprocess, "run", boom)
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")
    s = terminal.Session.__new__(terminal.Session)
    s.tmux_name = "board"
    assert s.repaint() is False


def test_the_attach_path_clears_before_it_repaints():
    """The repaint must land on a blank screen, not on top of the old frame.

    Checked in the source rather than over a socket: the ordering is the whole
    fix, and a test that only asserted "a clear is sent somewhere" would pass
    on the broken version too.
    """
    src = (Path(terminal.__file__)).read_text()
    attach = src[src.index("backlog, queue = session.subscribe()"):
                 src.index("def pump_out()")]
    # The clear goes out on the tmux path, and the byte log is the fallback
    # for a machine with no tmux — never both, which is what stacked screens.
    assert "if session.tmux_name:" in attach
    assert "elif backlog:" in attach
    assert attach.index("\\x1b[2J") < attach.index("elif backlog:")


def test_the_repaint_waits_for_the_browsers_first_resize():
    """Repainting before the resize draws at the previous viewer's size."""
    src = (Path(terminal.__file__)).read_text()
    assert "first_resize = True" in src
    loop = src[src.index("first_resize = True"):]
    assert "if first_resize and session.tmux_name:" in loop
    assert "first_resize = False" in loop
