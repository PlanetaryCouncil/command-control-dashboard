"""Single-node moderation: any paired node has full authority.

Low traffic and a small circle of trusted nodes made an escalating quorum more
ceremony than protection. So one signed vote moves a signal — that is how a node
"removes" one: it declines it, and the operator can always restore it. The two
things that stay true regardless: an unsigned vote is refused, and the hard
categories (quarantine) are never a node's to set.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app import identity, main
from app.main import app

client = TestClient(app)

NODES = {f"node-{i}": f"secret-{i}" for i in range(1, 4)}


@pytest.fixture
def paired(tmp_path, monkeypatch):
    registry = tmp_path / "trusted_nodes.json"
    registry.write_text(json.dumps(
        {"nodes": [{"node_id": n} for n in NODES]}))
    monkeypatch.setattr(main, "TRUSTED_NODES_PATH", registry)
    monkeypatch.setenv("NODE_SECRETS",
                       ",".join(f"{n}:{s}" for n, s in NODES.items()))


def make_signal(body="a perfectly clean question"):
    r = client.post("/api/signals",
                    json={"kind": "ask", "sender": "someone", "body": body,
                          "lawful": True})
    assert r.status_code == 201
    return r.json()["id"]


def vote(signal_id, node, status):
    raw = json.dumps({"status": status}).encode()
    return client.post(f"/api/signals/{signal_id}/override", content=raw,
                       headers={"content-type": "application/json",
                                "x-node-id": node,
                                "x-node-signature": identity.sign(raw, NODES[node])})


def test_unsigned_votes_are_refused(paired):
    sid = make_signal()
    r = client.post(f"/api/signals/{sid}/override", json={"status": "declined"})
    assert r.status_code == 403


def test_one_signed_node_removes_in_one_move(paired):
    """Removal = decline, and a single node has full authority to do it."""
    sid = make_signal()
    r = vote(sid, "node-1", "declined")
    assert r.status_code == 202
    assert r.json()["status"] == "declined"


def test_any_node_can_move_it_again_no_quorum(paired):
    sid = make_signal()
    assert vote(sid, "node-1", "declined").json()["status"] == "declined"
    # a different single node moves it back, no accumulating quorum
    assert vote(sid, "node-2", "accepted").json()["status"] == "accepted"


def test_repeating_the_current_status_is_a_noop(paired):
    sid = make_signal()
    vote(sid, "node-1", "declined")
    r = vote(sid, "node-2", "declined")
    assert r.status_code == 202 and r.json().get("note") == "already there"


def test_quarantine_is_not_a_settable_target(paired):
    sid = make_signal()
    assert vote(sid, "node-1", "quarantined").status_code == 422


def test_unknown_status_is_refused(paired):
    sid = make_signal()
    assert vote(sid, "node-1", "banished").status_code == 422
