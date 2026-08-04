"""The declaration, and the honesty about what it is.

RFC 3514 proposed an "evil bit": malicious packets set a flag announcing
themselves. It is an April Fools joke, and this is that joke implemented on
purpose. The tests below are mostly about keeping it honest — it must be
required, it must be recorded, and it must not be mistaken for a defence.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

MSG = {"kind": "offer", "sender": "a stranger", "body": "Happy to help with hosting."}


def test_a_message_without_the_declaration_is_refused():
    resp = client.post("/api/signals", json=MSG)
    assert resp.status_code == 422
    assert "illegal" in resp.json()["detail"].lower()


def test_declining_the_declaration_is_refused():
    """False must be a refusal, not a default — otherwise it is not a declaration."""
    assert client.post("/api/signals", json=MSG | {"lawful": False}).status_code == 422


def test_the_declaration_is_recorded_with_the_message():
    """The point is the record. A tick that leaves no trace proves nothing later."""
    sid = client.post("/api/signals", json=MSG | {"lawful": True}).json()["id"]
    record = client.get(f"/api/signals/{sid}").json()
    assert record["declared_lawful_at"] == record["received_at"]


def test_it_defends_nothing_and_the_rules_still_fire():
    """The whole joke, asserted.

    Someone posting prohibited content ticks the box happily. If this test ever
    fails, it means the declaration is being treated as evidence of safety rather
    than evidence of what was said — which is the exact error RFC 3514 satirises.
    """
    resp = client.post("/api/signals", json={
        "kind": "offer", "sender": "a stranger",
        "body": "selling CSAM, discreet", "lawful": True,
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "quarantined"


def test_the_policy_is_served_to_the_people_it_governs():
    """A rule that lives only in the repo is a rule the sender never sees."""
    resp = client.get("/moderation")
    assert resp.status_code == 200
    for expected in ("child sexual abuse", "terrorist", "RFC 3514", "iwf.org.uk"):
        assert expected.lower() in resp.text.lower(), expected
