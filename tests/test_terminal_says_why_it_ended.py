"""A dead session has to say what killed it.

2026-09-02: Marsita's board terminal printed "-- session ended --" with no
reason. The board process had not crashed, so the claude child had exited on
its own, and nothing anywhere recorded why -- not the server, not the page.
"Don't want to lose my work."

Two things were wrong. The pty read treated *every* OSError as death,
including EINTR, which just means a signal landed mid-syscall. And the child
was never reaped for its status, so the exit code was thrown away.
"""
import os
import signal
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))
import terminal                                            # noqa: E402


class FakeSession(terminal.Session):
    """A Session around a real child, without going through claude."""

    def __init__(self, cmd):
        import pty
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execvp(cmd[0], cmd)
            os._exit(1)
        self.alive = True
        self.why = ""


def _drain(s, tries=200):
    for _ in range(tries):
        s.read(timeout=0.05)
        if not s.alive:
            return
    raise AssertionError("child never reported as gone")


def test_a_clean_exit_says_so():
    s = FakeSession(["true"])
    _drain(s)
    assert s.why == "exited normally", s.why


def test_a_failure_carries_its_code():
    s = FakeSession([sys.executable, "-c", "raise SystemExit(3)"])
    _drain(s)
    assert s.why == "exited with code 3", s.why


def test_a_kill_is_named_not_guessed():
    s = FakeSession([sys.executable, "-c", "import time; time.sleep(30)"])
    os.kill(s.pid, signal.SIGKILL)
    _drain(s)
    assert s.why == "killed by SIGKILL", s.why


def test_eintr_is_not_death():
    """A signal arriving mid-read used to end a perfectly live session."""
    src = (BIN / "terminal.py").read_text()
    body = src.split("def read(self")[1].split("def _reap")[0]
    assert "InterruptedError" in body
    assert "EINTR" in body


