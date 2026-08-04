"""2n+1 or nothing: the escalating-quorum override.

The design goal is a single property: every flip doubles the price of
flipping back. One operator decision (n=1) takes 3 signed nodes to
overturn; overturning THAT takes 7; then 15. Ping-pong is exponentially
expensive, and the hard-block categories are not votable at any price.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app import identity, main
from app.main import app

client = TestClient(app)

NODES = {f"node-{i}": f"secret-{i}" for i in range(1, 8)}


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


def test_one_vote_does_not_flip(paired):
    sid = make_signal()
    r = vote(sid, "node-1", "declined")
    assert r.status_code == 202
    assert r.json()["votes"] == 1 and r.json()["needed"] == 3


def test_three_votes_flip_an_operator_decision(paired):
    sid = make_signal()
    vote(sid, "node-1", "declined")
    vote(sid, "node-2", "declined")
    r = vote(sid, "node-3", "declined")
    assert r.json()["status"] == "declined"
    assert len(r.json()["decision"]["backers"]) == 3


def test_flipping_back_now_costs_seven(paired):
    sid = make_signal()
    for n in ("node-1", "node-2", "node-3"):
        vote(sid, n, "declined")
    r = vote(sid, "node-4", "accepted")
    assert r.json()["needed"] == 7


def test_double_voting_counts_once(paired):
    sid = make_signal()
    vote(sid, "node-1", "declined")
    r = vote(sid, "node-1", "declined")
    assert r.json()["votes"] == 1


def test_quarantine_is_not_a_votable_target(paired):
    sid = make_signal()
    r = vote(sid, "node-1", "quarantined")
    assert r.status_code == 422
