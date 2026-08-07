"""The terminal socket must fail closed.

`/ws/terminal` ends in os.execvpe of `claude` on a PTY with cwd at the repo
root. Three things stand in front of it: CONTROL_PATHS hides it from funnelled
callers, a per-boot token guards it, and Origin pins it to a local browser.

The Origin check used to read `if origin and not origin.startswith(...)` —
which enforced nothing against a client that omitted the header, and omitting a
header is easier than forging one. A guard that only inconveniences browsers is
backwards, since a browser is the one caller that cannot lie about Origin.
"""

import sys
from pathlib import Path

FLEET_BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(FLEET_BIN))

import terminal  # noqa: E402

TOKEN = "correct-horse"


class FakeHandler:
    """A BaseHTTPRequestHandler mid-request, as serve_socket expects one."""

    def __init__(self, headers):
        self.path = f"/ws/terminal?token={TOKEN}"
        self.headers = headers
        self.errors = []

    def send_error(self, code, message=None):
        self.errors.append((code, message))


def _attempt(headers):
    h = FakeHandler(headers)
    terminal.serve_socket(h, cwd=".", token=TOKEN)
    return h.errors


def test_a_missing_origin_is_refused():
    """The regression. Absent must not read as permitted."""
    assert _attempt({}) == [(403, "bad origin")]


def test_a_foreign_origin_is_refused():
    assert _attempt({"Origin": "https://evil.example"}) == [(403, "bad origin")]


def test_a_local_origin_gets_past_the_origin_check():
    """It must still stop at the upgrade check, not at Origin.

    Pinning this stops a future 'fix' from failing closed on everything and
    quietly breaking the operator's own terminal — the failure mode that gets
    a guard deleted rather than repaired.
    """
    for origin in ("http://127.0.0.1:8787", "http://localhost:8787"):
        errors = _attempt({"Origin": origin})
        assert errors == [(400, "expected a websocket upgrade")]


def test_a_bad_token_is_refused_before_origin_is_considered():
    h = FakeHandler({"Origin": "http://127.0.0.1:8787"})
    h.path = "/ws/terminal?token=wrong"
    terminal.serve_socket(h, cwd=".", token=TOKEN)
    assert h.errors == [(403, "bad token")]
