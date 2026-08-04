"""The approval gate.

A grant here is standing — it lasts until revoked, with no clock. That was a
deliberate choice, and it puts all the weight on two properties: the scope must
be narrow, and the check must fail closed. Every test below is defending one of
those two, because if either gives way a standing grant becomes an open one.
"""

import json

from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)
remote = TestClient(app, client=("203.0.113.5", 5555))

PENDING = "apr-001"


def approvals():
    return client.get("/api/approvals").json()["approvals"]


def one(approval_id):
    return next(a for a in approvals() if a["id"] == approval_id)


def allowed(scope):
    return client.get("/api/approvals/check", params={"scope": scope}).json()["allowed"]


def test_a_grant_is_standing_until_revoked():
    assert allowed("discord:create-channels") is False
    resp = client.post(
        f"/api/approvals/{PENDING}/approve",
        json={"scope": "discord:create-channels", "note": "ten channels, named in the request"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "granted"
    assert allowed("discord:create-channels") is True

    # No clock ran out and nothing was consumed: it is still true on re-read.
    assert allowed("discord:create-channels") is True


def test_revoking_ends_it():
    client.post(f"/api/approvals/{PENDING}/approve", json={"scope": "discord:create-channels"})
    assert allowed("discord:create-channels") is True

    resp = client.post(
        f"/api/approvals/{PENDING}/revoke", json={"reason": "server never created"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"
    assert allowed("discord:create-channels") is False


def test_a_revoked_grant_is_not_revived_by_approving_again():
    """Revoking is a decision, not a pause. Reviving the same row would let a
    grant come back without anyone restating what it covers."""
    client.post(f"/api/approvals/{PENDING}/approve", json={"scope": "discord:create-channels"})
    client.post(f"/api/approvals/{PENDING}/revoke", json={})

    resp = client.post(
        f"/api/approvals/{PENDING}/approve", json={"scope": "discord:create-channels"}
    )
    assert resp.status_code == 409
    assert allowed("discord:create-channels") is False


def test_an_unscoped_grant_is_refused():
    """The scope is the only bound on a grant with no expiry. Absent, it would
    have to mean either 'nothing' or 'anything' — so it is rejected instead."""
    for blank in ("", "   "):
        resp = client.post(f"/api/approvals/{PENDING}/approve", json={"scope": blank})
        assert resp.status_code == 422
    assert one(PENDING)["status"] == "pending"


def test_scope_matching_is_exact_so_a_grant_never_covers_its_neighbours():
    client.post(f"/api/approvals/{PENDING}/approve", json={"scope": "discord:create-channels"})
    for adjacent in (
        "discord:delete-channels",
        "discord:create-channel",
        "discord",
        "discord:*",
        "*",
        "discord:create-channels:extra",
    ):
        assert allowed(adjacent) is False, f"{adjacent!r} must not ride on the grant"


def test_the_check_fails_closed_on_every_shape_of_nothing():
    assert allowed("") is False
    assert allowed("   ") is False
    assert allowed("never-requested") is False
    assert client.get("/api/approvals/check").json()["allowed"] is False
    # A pending approval is not a grant.
    assert one(PENDING)["status"] == "pending"
    assert allowed(one(PENDING).get("scope") or "unset") is False


def test_granting_and_revoking_are_local_only():
    assert remote.post(
        f"/api/approvals/{PENDING}/approve", json={"scope": "discord:create-channels"}
    ).status_code == 403
    assert remote.post(f"/api/approvals/{PENDING}/revoke", json={}).status_code == 403
    assert allowed("discord:create-channels") is False


def test_unknown_approval_is_a_404():
    assert client.post(
        "/api/approvals/apr-nope/approve", json={"scope": "x"}
    ).status_code == 404
    assert client.post("/api/approvals/apr-nope/revoke", json={}).status_code == 404


def test_boot_shows_standing_grants_and_stops_calling_them_pending():
    before = client.get("/boot").text
    assert "Standing grants" not in before

    client.post(f"/api/approvals/{PENDING}/approve", json={"scope": "discord:create-channels"})
    after = client.get("/boot").text
    assert "Standing grants" in after
    assert "discord:create-channels" in after

    action = one(PENDING)["action"]
    waiting = after.split("## Standing grants")[0]
    assert action not in waiting, "a granted item must leave the waiting-on-human list"


def test_both_decisions_are_written_to_the_event_log():
    client.post(f"/api/approvals/{PENDING}/approve", json={"scope": "discord:create-channels"})
    client.post(f"/api/approvals/{PENDING}/revoke", json={"reason": "changed my mind"})

    kinds = [
        json.loads(line)["kind"]
        for line in main.EVENTS_PATH.read_text().splitlines()
        if line.strip()
    ]
    assert "approval.granted" in kinds
    assert "approval.revoked" in kinds
