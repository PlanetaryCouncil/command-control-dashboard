"""The wheel has to have somewhere to go.

xterm.js keeps its own 8000-line scrollback, so a terminal that prints and
scrolls off the top is scrollable for free. tmux is not that: it is a
full-screen program that repaints in place, so nothing ever leaves the
viewport and there is nothing above to scroll back to. The wheel did nothing
at all (2026-09-04: "wish I could scroll up on Claude output... currently
scrolling does nothing"), and no error said why.

`mouse on` is what makes tmux ask the terminal for wheel events. Then the
wheel enters tmux's own history instead of falling on the floor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fleet" / "bin"))

import terminal


def test_the_session_is_told_to_take_the_mouse(monkeypatch):
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")
    monkeypatch.setattr(terminal, "tmux_has", lambda n: True)
    monkeypatch.setattr(terminal.subprocess, "run", fake_run)

    assert terminal.configure_tmux("board") is True
    opts = {a[4]: a[5] for a in calls}
    assert opts["mouse"] == "on"


def test_history_is_deeper_than_the_tmux_default():
    """2000 lines is a few screens of talk and none of a test run."""
    assert terminal.HISTORY_LIMIT >= 20000


def test_it_waits_for_the_session_instead_of_racing_it(monkeypatch):
    """The session is created by an exec in a forked child, so it is not there
    the instant attach() returns. Configuring too early silently did nothing."""
    seen = {"n": 0}

    def not_yet(name):
        seen["n"] += 1
        return seen["n"] > 3          # exists on the fourth look

    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")
    monkeypatch.setattr(terminal, "tmux_has", not_yet)
    monkeypatch.setattr(terminal.time, "sleep", lambda s: None)
    monkeypatch.setattr(terminal.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 0})())
    assert terminal.configure_tmux("board") is True
    assert seen["n"] == 4


def test_a_session_that_never_appears_is_given_up_on(monkeypatch):
    """A missing session must not hang a thread forever."""
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")
    monkeypatch.setattr(terminal, "tmux_has", lambda n: False)
    monkeypatch.setattr(terminal.time, "sleep", lambda s: None)
    assert terminal.configure_tmux("board", tries=3) is False


def test_no_tmux_means_nothing_to_configure(monkeypatch):
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "")
    assert terminal.configure_tmux("board") is False
