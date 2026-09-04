"""A test result must not depend on the shell the suite was started from.

`TRUST_PROXY=1` tells the app a reverse proxy is in front of it, so the caller
is read from X-Forwarded-For rather than the socket. The TestClient sends no
such header, so every local-only write is refused — 28 tests across approvals,
dashboard, inbox and sync failed with 403 where they expected 404 or 200.

The code was fine. The suite was inheriting the variable from its parent: on
2026-09-04 the tmux server had been started with it set, so every run inside
that terminal failed and every run outside it passed. A suite that answers
differently depending on who launched it cannot be used to decide anything,
and "it passes on my machine" was literally the bug.
"""

import os

from fastapi.testclient import TestClient

from app.main import app


def test_trust_proxy_is_not_inherited_from_the_environment():
    """The autouse fixture clears it, whatever the shell exported."""
    assert os.environ.get("TRUST_PROXY") is None


def test_a_local_write_is_allowed_by_default():
    """The symptom, pinned: 403 here meant the environment had leaked in."""
    client = TestClient(app)
    r = client.post("/api/approvals/apr-does-not-exist/approve",
                    json={"scope": "x"})
    # 404 because the approval is invented — the point is that it got far
    # enough to look, rather than being refused as a stranger.
    assert r.status_code == 404, (
        "a local write was refused; TRUST_PROXY has leaked into the suite")


def test_a_test_that_wants_a_proxy_can_still_have_one(monkeypatch):
    """Clearing it by default must not stop the tunnel tests declaring it."""
    monkeypatch.setenv("TRUST_PROXY", "1")
    remote = TestClient(app, client=("203.0.113.9", 5555))
    r = remote.post("/api/handoffs", json={"by": "stranger", "changed": "no"})
    assert r.status_code == 403


# ------------------------------------------------- and the board stops leaking
def test_the_board_does_not_hand_its_proxy_setting_to_the_terminal(monkeypatch):
    """Fixing the suite is not the same as fixing the leak.

    conftest clears TRUST_PROXY for tests. That protects the suite, not the
    person typing in the terminal — every shell in the tmux session still
    inherited a networking assumption that is false for it. The board is
    behind the Tailscale funnel; the terminal it spawns is not behind
    anything.
    """
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[1] / "fleet" / "bin"))
    import terminal

    src = _P(terminal.__file__).read_text()
    child = src[src.index("if self.pid == 0:"):src.index("os._exit(1)")]
    assert 'env.pop("TRUST_PROXY", None)' in child, (
        "the terminal would inherit the board's proxy setting again")
