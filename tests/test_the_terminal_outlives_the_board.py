"""The board is a viewer. Something else holds the session.

The board used to `pty.fork()` claude directly, making the board process its
parent -- so every restart of the board killed whatever was running in it.
Reloads survived, because the pty outlives one websocket. Restarts did not,
and the board gets restarted every time it is improved: twelve times on
2026-09-02 alone, each landing on whatever Marsita was mid-way through.

  "the board terminal needs to stay alive ---> that's the point ---> I'm not
   tmux dude, I'm practical solutions hacker dude"

So tmux owns the process and the board only draws it. `new-session -A` is the
whole mechanism -- attach if it exists, create if it does not -- which means
the first connection starts claude and every later one joins it, whether it
arrives after a reload, after a restart, or from a real terminal.
"""
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))
import terminal                                            # noqa: E402

SRC = (BIN / "terminal.py").read_text()


def test_the_session_is_started_under_tmux(monkeypatch):
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")
    monkeypatch.setattr(terminal, "has_prior_session", lambda cwd: False)
    argv = terminal.session_argv("/tmp", "claude", "board")
    assert argv[:1] == ["/usr/bin/tmux"]
    assert "new-session" in argv and "-A" in argv
    assert argv[-1] == "claude"


def test_attach_if_it_exists_is_the_whole_mechanism():
    """Without -A a second connection would fail on a duplicate name, and
    with `attach-session` the first would fail because nothing exists yet."""
    assert '"new-session", "-A"' in SRC


def test_the_resume_flag_still_travels_through(monkeypatch):
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")
    monkeypatch.setattr(terminal, "has_prior_session", lambda cwd: True)
    argv = terminal.session_argv("/tmp", "claude", "board")
    assert argv[-2:] == ["claude", "--continue"]


def test_a_claude_flag_can_never_be_read_as_a_tmux_flag(monkeypatch):
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "/usr/bin/tmux")
    monkeypatch.setattr(terminal, "has_prior_session", lambda cwd: True)
    argv = terminal.session_argv("/tmp", "claude", "board")
    assert argv[argv.index("--") + 1] == "claude"


def test_without_tmux_it_behaves_exactly_as_before(monkeypatch):
    """A board that refuses to open a terminal is worse than one whose
    terminal is fragile."""
    monkeypatch.setattr(terminal, "tmux_bin", lambda: "")
    monkeypatch.setattr(terminal, "has_prior_session", lambda cwd: False)
    assert terminal.session_argv("/tmp", "claude", "board") == ["claude"]


def test_a_surviving_tmux_session_counts_as_a_resume(monkeypatch):
    """After a board restart `_LIVE` is empty but tmux is still there, and
    calling that a fresh start would misreport the one thing this fixes."""
    monkeypatch.setattr(terminal, "tmux_has", lambda n: True)
    monkeypatch.setattr(terminal, "Session", lambda *a, **k: object())
    terminal._LIVE.pop("probe", None)
    try:
        _s, resumed = terminal.attach("probe", ".", claude_bin="cat")
        assert resumed is True
    finally:
        terminal._LIVE.pop("probe", None)


def test_closing_a_socket_still_only_detaches():
    tail = SRC.rsplit("finally:", 1)[1]
    assert "unsubscribe" in tail
    assert "session.close()" not in tail
    assert "kill-session" not in tail


def test_only_end_kills_the_session_behind_the_viewer():
    fn = SRC.split("def end(name: str)")[1].split("\ndef ")[0]
    assert "kill-session" in fn
