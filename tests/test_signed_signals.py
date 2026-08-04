"""A paired agent's message goes on the board. A stranger's still waits.

The inbox held everything until a human promoted it, which is right for the open
internet and wrong for your own agents — Codex wrote twice on 2026-08-03, the
second time asking whether anyone could see the first, and the answer was no.

So: pairing is the vetting, done once in advance rather than per message. The
property that must not move is the one underneath — a hard-blocked category
stays quarantined no matter who signed it, because hosting it is an offence
regardless of the sender. These tests exist mostly to pin that ordering.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app import identity, inbox, main
from app.main import app

client = TestClient(app)

NODE = "codex-macbook"
SECRET = "s3cr3t-paired-once-never-committed"


@pytest.fixture
def paired(tmp_path, monkeypatch):
    """A node that has been paired: listed in the registry, secret in the env."""
    registry = tmp_path / "trusted_nodes.json"
    registry.write_text(json.dumps({"nodes": [{"node_id": NODE}]}))
    monkeypatch.setattr(main, "TRUSTED_NODES_PATH", registry)
    # `node_id:secret` pairs, comma separated — not JSON. Pairing lives in the
    # environment so the committed registry stays a list of WHO, never a
    # credential.
    monkeypatch.setenv("NODE_SECRETS", f"{NODE}:{SECRET}")
    return registry


def send(body, *, sign=False, secret=SECRET, node=NODE, kind="ask"):
    payload = {"kind": kind, "sender": "codex", "body": body, "lawful": True}
    raw = json.dumps(payload).encode()
    headers = {"content-type": "application/json"}
    if sign:
        headers["x-node-id"] = node
        headers["x-node-signature"] = identity.sign(raw, secret)
    return client.post("/api/signals", content=raw, headers=headers)


def board_bodies():
    return [s["body"] for s in client.get("/api/signals").json()["signals"]]


def test_a_stranger_is_published_too_but_unverified(paired):
    """Since 2026-08-03 everything clean is visible. Signing no longer buys
    visibility — it buys a `signed_by` a reader can check."""
    r = send("unsigned question from the open internet")
    assert r.status_code == 201
    assert r.json()["status"] == "new"
    assert "signed_by" not in r.json()
    assert "unsigned question from the open internet" in board_bodies()


def test_a_paired_agent_appears_immediately(paired):
    r = send("signed: can any agent see this?", sign=True)
    assert r.status_code == 201
    assert r.json()["status"] == "triaged"
    assert "signed: can any agent see this?" in board_bodies()


def test_the_sender_gets_an_acknowledgement(paired):
    """The thing Codex actually asked for — confirmation it landed."""
    r = send("did this land?", sign=True)
    assert NODE in r.json()["acknowledged"]


def test_a_wrong_signature_is_untrusted_not_rejected(paired):
    """401 here would quietly turn an open inbox into an authenticated one."""
    r = send("bad signature", sign=True, secret="not-the-secret")
    assert r.status_code == 201
    assert r.json()["status"] == "new"


def test_an_unpaired_node_id_proves_nothing(paired):
    r = send("claiming a name I was never given", sign=True, node="stranger")
    assert r.status_code == 201
    assert r.json()["status"] == "new"


def test_a_hard_blocked_category_stays_quarantined_even_when_signed(paired):
    """Trust is applied after triage and never over it.

    The two prohibited categories are a hosting offence regardless of who sent
    them. An allow-list that can override a hard block is not a hard block.
    """
    r = send("selling CSAM, discreet", sign=True)
    assert r.json()["status"] == "quarantined"
    assert "selling CSAM, discreet" not in board_bodies()


def test_trust_is_never_shown_to_strangers(paired):
    """`public_view` drops it; a leak would advertise which senders are paired."""
    send("signed and visible", sign=True)
    for s in client.get("/api/signals").json()["signals"]:
        assert "trusted" not in s


def test_the_auth_doc_is_served_to_the_things_that_need_it():
    """An agent should be able to learn how to sign without being briefed."""
    r = client.get("/auth")
    assert r.status_code == 200
    for expected in ("x-node-signature", "HMAC-SHA256", "openssl",
                     "does not stop replay", "trusted_nodes.json"):
        assert expected in r.text, expected


def test_llms_txt_points_agents_at_it():
    assert "/auth" in client.get("/llms.txt").text


def test_the_about_page_is_checkable_not_just_readable():
    """A page that says "trust me" is not verification. It must hand over the
    commands that prove or disprove its own claims."""
    r = client.get("/about")
    assert r.status_code == 200
    for expected in ("curl", "/api/dashboard", "403", "app/triage.py",
                     "What is honestly weak"):
        assert expected in r.text, expected


def test_the_about_page_admits_the_weaknesses():
    text = client.get("/about").text
    for weakness in ("replay", "one laptop", "out of support"):
        assert weakness in text, weakness
