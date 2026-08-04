"""The doorbell: arrivals ring the fleet board, and only arrivals.

Written after the first suite run rang the *live* board 11 times with fake
visitors — the tests exercised /api/pair and signed signals, ring() wrote to
the real events.jsonl, and the watchdog runs this suite hourly. The isolation
now lives in conftest (FLEET_PATH → tmp); these tests pin the behaviour.
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import fleet, identity, main, pairing
from app.main import app

client = TestClient(app)

NODE = "doorbell-node"
SECRET = "d00rb3ll-secret-never-committed"


def rings() -> list[dict]:
    log = Path(os.environ["FLEET_PATH"]) / "events.jsonl"
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines()]


@pytest.fixture
def paired(tmp_path, monkeypatch):
    registry = tmp_path / "trusted_nodes.json"
    registry.write_text(json.dumps({"nodes": [{"node_id": NODE}]}))
    monkeypatch.setattr(main, "TRUSTED_NODES_PATH", registry)
    monkeypatch.setenv("NODE_SECRETS", f"{NODE}:{SECRET}")
    return registry


def send(body, *, sign=False):
    payload = {"kind": "ask", "sender": "someone", "body": body,
               "lawful": True}
    raw = json.dumps(payload).encode()
    headers = {"content-type": "application/json"}
    if sign:
        headers["x-node-id"] = NODE
        headers["x-node-signature"] = identity.sign(raw, SECRET)
    return client.post("/api/signals", content=raw, headers=headers)


def test_ring_writes_the_events_shape():
    fleet.ring("visitors", "ok", "[visitors] hello")
    (rec,) = rings()
    assert set(rec) == {"ts", "agent", "level", "msg"}
    assert rec["agent"] == "visitors"
    assert rec["level"] == "ok"


def test_ring_is_isolated_from_the_live_board(tmp_path):
    # The property whose absence rang the real board 11 times.
    assert str(tmp_path) in os.environ["FLEET_PATH"]


def test_ring_downgrades_unknown_levels():
    fleet.ring("visitors", "shouting", "[visitors] hello")
    (rec,) = rings()
    assert rec["level"] == "info"


def test_redeeming_a_code_rings_the_board():
    minted = pairing.invite(main.PAIRING_PATH, "test-node", ttl_hours=1)
    r = client.post("/api/pair", json={"code": minted["code"]})
    assert r.status_code == 201
    msgs = [e["msg"] for e in rings()]
    assert any("node 'test-node' paired" in m for m in msgs)


def test_anonymous_signal_does_not_ring():
    r = send("hello from a stranger")
    assert r.status_code == 201
    assert rings() == []


def test_signed_signal_rings_with_sender_and_kind_never_body(paired):
    r = send("SECRET-PAYLOAD-TEXT", sign=True)
    assert r.status_code == 201
    msgs = [e["msg"] for e in rings() if "signal from node" in e["msg"]]
    assert msgs, "signed signal should ring"
    assert NODE in msgs[0]
    assert "(ask)" in msgs[0]
    assert "SECRET-PAYLOAD-TEXT" not in msgs[0]
