"""A page reload must not throw the running session away.

2026-09-02, Marsita: "I want continuity in the terminal on the web... to
survive reloads on WWW". The board is the home; a refresh should not be a
house move. Every websocket used to fork a fresh `claude` and the old one was
killed in the socket's `finally`.
"""
import sys
import time
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))
import terminal                                            # noqa: E402


def _fresh(name="t"):
    terminal._LIVE.pop(name, None)
    return name


def test_the_second_attach_gets_the_same_session():
    n = _fresh()
    a, resumed_a = terminal.attach(n, ".", claude_bin="cat")
    b, resumed_b = terminal.attach(n, ".", claude_bin="cat")
    try:
        assert a is b
        assert resumed_a is False and resumed_b is True
    finally:
        terminal.end(n)


def test_a_late_arrival_is_shown_what_it_missed():
    n = _fresh()
    s, _ = terminal.attach(n, ".", claude_bin="cat")
    try:
        s.write(b"hello reload\n")
        for _ in range(100):
            if b"hello reload" in bytes(s.buf):
                break
            time.sleep(0.02)
        backlog, q = s.subscribe()
        assert b"hello reload" in backlog
        s.unsubscribe(q)
    finally:
        terminal.end(n)


def test_detaching_does_not_kill_the_session():
    """The socket's finally used to call close(). Nothing about a browser
    going away means the work should stop."""
    src = (BIN / "terminal.py").read_text()
    tail = src.rsplit("finally:", 1)[1]
    assert "unsubscribe" in tail
    assert "session.close()" not in tail


def test_a_dead_session_is_not_resumed():
    n = _fresh()
    s, _ = terminal.attach(n, ".", claude_bin="true")
    for _ in range(100):
        if not s.alive:
            break
        time.sleep(0.02)
    terminal.forget(n)
    s2, resumed = terminal.attach(n, ".", claude_bin="cat")
    try:
        assert resumed is False and s2 is not s
    finally:
        terminal.end(n)


def test_both_pages_ask_for_the_same_session():
    for view in ("oneview.py", "termview.py"):
        assert "&s=board" in (BIN / view).read_text(), view
