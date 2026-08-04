"""Fleet is published to the internet; its shell is not.

The fleet server was written for localhost and shows it — `/ws/terminal` spawns
a Claude session in the repo, `/api/kill` SIGKILLs the fleet, and
`/api/kill-token` hands the token guarding both to whoever asks. All of that is
correct on a laptop and indefensible on a funnel.

The split is by caller. tailscaled sets `X-Forwarded-For` on every funnelled
request; a browser on 127.0.0.1 never does; the server binds loopback only, so
the funnel is the only route in from outside. These tests pin both halves —
that control paths vanish for a remote caller, and that they still work locally,
because a guard that also breaks the operator's own terminal would just get
removed.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

FLEET = Path(__file__).resolve().parent.parent / "fleet"
PORT = 8913

CONTROL = ["/terminal", "/chat", "/api/kill-token"]
# `/events` is public too, but it is an open SSE stream that never closes —
# asserting on it here would hang the suite rather than test anything.
PUBLIC = ["/", "/board", "/workers.json", "/agents", "/procs"]


@pytest.fixture(scope="module")
def server():
    """Fails loudly if the server does not start. Never skips.

    This module used to `pytest.skip` here. On 2026-08-03 a council agent read
    three watchdog sweeps of the same command — `187 passed (51s)`,
    `174 passed + 13 skipped (175s)`, `192 passed (288s)` — and pointed out that
    all three reported `pass`. The 13 were exactly this file: the tests that
    prove the public URL does not expose a terminal or a kill switch.

    A slow laptop silently downgraded the safety check to nothing, and the
    watchdog said the same word either way. So: no skip. If the server will not
    start, that is a failure and it takes its stderr with it.
    """
    p = subprocess.Popen(
        [sys.executable, str(FLEET / "bin" / "fleet.py"), "serve", str(PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.monotonic() + 30          # generous: this box compiles Go
    last = None
    while time.monotonic() < deadline:
        time.sleep(0.25)
        if p.poll() is not None:
            pytest.fail(f"fleet server exited {p.returncode}:\n{p.communicate()[0]}")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/workers.json", timeout=2)
            break
        except Exception as exc:
            last = exc
    else:
        p.kill()
        pytest.fail(f"fleet server never answered on :{PORT} within 30s "
                    f"— last error: {last!r}")
    yield
    p.kill()
    p.wait(timeout=10)


def fetch(path, forwarded=None):
    """Returns (status, body). A forwarded address means 'through the funnel'."""
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}")
    if forwarded:
        req.add_header("X-Forwarded-For", forwarded)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


@pytest.mark.parametrize("path", CONTROL)
def test_control_paths_do_not_exist_for_a_remote_caller(server, path):
    status, _ = fetch(path, forwarded="203.0.113.7")
    assert status == 404, f"{path} answered {status} to the internet"


@pytest.mark.parametrize("path", CONTROL)
def test_control_paths_still_work_locally(server, path):
    status, _ = fetch(path)
    assert status == 200, f"{path} broke for the operator ({status})"


@pytest.mark.parametrize("path", PUBLIC)
def test_read_only_views_stay_public(server, path):
    """The point of publishing is that a stranger's agent can read this."""
    status, _ = fetch(path, forwarded="203.0.113.7")
    assert status == 200, f"{path} should be readable by anyone, got {status}"


def test_the_landing_page_does_not_leak_the_kill_token(server):
    """404ing /api/kill-token is theatre if the page embeds the token anyway."""
    _, local = fetch("/")
    _, remote = fetch("/", forwarded="203.0.113.7")

    status, body = fetch("/api/kill-token")
    assert status == 200
    token = json.loads(body)["token"]

    assert token in local, "the operator's own page needs its controls to work"
    assert token not in remote, "the kill token reached a remote viewer"


def test_kill_is_refused_through_the_funnel(server):
    """Belt and braces: even holding a token, the route is gone remotely."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/kill", method="POST",
        data=b'{"token":"whatever","dry_run":true}')
    req.add_header("X-Forwarded-For", "203.0.113.7")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            pytest.fail(f"kill answered {r.status} to the internet")
    except urllib.error.HTTPError as e:
        assert e.code == 404
