"""Writes must stay closed when the cockpit is published from the laptop.

(Data isolation comes from conftest's autouse `isolate_written_data`, so these
never touch the real data/ files.)

Serving this through a tunnel is the intended way to put it online — no server,
no DNS, laptop is the host. But a tunnel terminates locally, so every visitor
reaches the app from 127.0.0.1, which is the exact address the write gate exists
to trust. Without the checks below, publishing the site would hand every stranger
the operator's own permissions, and nothing on the page would look different.

Every test here sets TRUST_PROXY=1, i.e. "a tunnel is in front of you now".
"""

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app

# A tunnel connects from the loopback address. That is the whole problem.
tunnel = TestClient(app, client=("127.0.0.1", 4111))

WRITES = [
    ("/api/handoffs", {"by": "stranger", "changed": "anything"}),
    ("/api/projects/command-control-dashboard/touch", {"status": "paused"}),
    ("/api/horizons/today", {"goal": "rewritten by a visitor"}),
    ("/api/approvals/apr-001/approve", {"scope": "discord:create-channels"}),
    ("/api/approvals/apr-001/revoke", {}),
]


@pytest.fixture
def behind_tunnel(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY", "1")


@pytest.mark.parametrize("path,body", WRITES)
def test_a_visitor_through_the_tunnel_cannot_steer(behind_tunnel, path, body):
    """The socket says 127.0.0.1; the forwarded header says who it really is."""
    resp = tunnel.post(path, json=body, headers={"x-forwarded-for": "203.0.113.9"})
    assert resp.status_code == 403, f"{path} accepted a write from a stranger"


@pytest.mark.parametrize("path,body", WRITES)
def test_a_missing_forwarded_header_fails_closed(behind_tunnel, path, body):
    """Absent header under a declared proxy means unknown, not local.

    This is the case that would bite hardest: if the tunnel stops sending the
    header — a version change, a misconfiguration — falling back to the socket
    address would silently re-open every write to the public.
    """
    resp = tunnel.post(path, json=body)
    assert resp.status_code == 403, f"{path} trusted a caller it could not identify"


def test_a_spoofed_local_header_is_still_refused_without_a_proxy():
    """With no TRUST_PROXY, the header is attacker-controlled and must be ignored.

    Otherwise anyone could send X-Forwarded-For: 127.0.0.1 and write at will —
    the mirror image of the tunnel bug, and the reason the header is only ever
    honoured when a proxy is explicitly declared.
    """
    remote = TestClient(app, client=("203.0.113.9", 5555))
    resp = remote.post("/api/handoffs",
                       json={"by": "stranger", "changed": "nope"},
                       headers={"x-forwarded-for": "127.0.0.1"})
    assert resp.status_code == 403


def test_reads_stay_open_through_the_tunnel(behind_tunnel):
    """Closing writes must not close the site. Public reading is the point."""
    for path in ("/", "/boot", "/llms.txt", "/api/dashboard", "/api/approvals", "/health"):
        resp = tunnel.get(path, headers={"x-forwarded-for": "203.0.113.9"})
        assert resp.status_code == 200, f"{path} stopped serving readers"


def test_the_public_write_still_works_through_the_tunnel(behind_tunnel):
    """POST /api/signals is the one thing strangers are invited to do."""
    resp = tunnel.post("/api/signals",
                       json={"kind": "offer", "body": "I can host this for you.",
                             "sender": "a stranger", "lawful": True},
                       headers={"x-forwarded-for": "203.0.113.9"})
    assert resp.status_code in (200, 201), resp.text


def test_the_operator_can_still_steer_from_the_laptop(behind_tunnel):
    """A tunnel in front must not lock the owner out of their own cockpit.

    Local traffic does not pass through it, so nothing forwards a header — but
    the fail-closed rule above would refuse that too. The operator keeps a route
    by hitting the app directly with a header naming themselves, which only
    something already on this machine can do.
    """
    resp = tunnel.post("/api/handoffs",
                       json={"by": "marsita", "changed": "still in charge"},
                       headers={"x-forwarded-for": "127.0.0.1"})
    assert resp.status_code == 201, resp.text


def test_a_spoofed_localhost_prefix_is_refused(behind_tunnel):
    """#10: a reverse proxy APPENDS the real client, so a remote caller sending
    '127.0.0.1' arrives as '127.0.0.1, <real-ip>'. Reading the LAST entry makes
    that resolve to the real remote address and be refused — while a bare
    '127.0.0.1' from the trusted front door still passes (test above)."""
    resp = tunnel.post("/api/handoffs",
                       json={"by": "attacker", "changed": "should be blocked"},
                       headers={"x-forwarded-for": "127.0.0.1, 203.0.113.9"})
    assert resp.status_code == 403, resp.text


def test_steering_caller_discards_the_socket_when_a_proxy_is_declared(monkeypatch):
    """The unit-level guarantee the endpoint tests rest on."""
    class Req:
        def __init__(self, host, fwd):
            self.client = type("C", (), {"host": host})()
            self.headers = {"x-forwarded-for": fwd} if fwd else {}

    monkeypatch.setenv("TRUST_PROXY", "1")
    assert main.steering_caller(Req("127.0.0.1", "203.0.113.9")) == "203.0.113.9"
    assert main.steering_caller(Req("127.0.0.1", "")) == ""

    monkeypatch.delenv("TRUST_PROXY", raising=False)
    assert main.steering_caller(Req("127.0.0.1", "203.0.113.9")) == "127.0.0.1"
