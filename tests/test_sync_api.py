import json

import pytest
from fastapi.testclient import TestClient

from app import identity, main
from app.main import app
from app.sync import Clock, make_ops

client = TestClient(app)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    life = tmp_path / "life.json"
    life.write_text(main.DATA_PATH.read_text())
    monkeypatch.setattr(main, "DATA_PATH", life)
    hz = tmp_path / "horizons.json"
    hz.write_text(main.HORIZONS_PATH.read_text())
    monkeypatch.setattr(main, "HORIZONS_PATH", hz)
    monkeypatch.setattr(main, "OPLOG_DIR", tmp_path / "oplog")
    monkeypatch.setattr(main, "CONFLICTS_PATH", tmp_path / "sync_conflicts.json")
    monkeypatch.setattr(main, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(main, "INBOX_DIR", tmp_path / "inbox")

    tn = tmp_path / "trusted_nodes.json"
    tn.write_text(json.dumps({"nodes": [{"node_id": "phone", "device": "test"}]}))
    monkeypatch.setattr(main, "TRUSTED_NODES_PATH", tn)
    monkeypatch.setenv("NODE_SECRETS", "phone:test-secret-do-not-use-in-prod")
    return life


def _signed_push(ops: list[dict], node_id="phone", secret="test-secret-do-not-use-in-prod"):
    body = json.dumps({"node_id": node_id, "ops": ops}).encode()
    sig = identity.sign(body, secret)
    return client.post(
        "/api/sync/push",
        content=body,
        headers={"content-type": "application/json", "x-node-id": node_id, "x-node-signature": sig},
    )


def test_pull_returns_this_nodes_op_log(sandbox):
    client.post("/api/projects/command-control-dashboard/touch", json={"status": "active"})
    resp = client.get("/api/sync/pull", params={"resource": "project"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ops"], "the local touch should have produced at least one op"
    assert body["node_id"] == identity.NODE_ID


def test_pull_unknown_resource_404s(sandbox):
    assert client.get("/api/sync/pull", params={"resource": "nonsense"}).status_code == 404


def test_push_without_signature_is_rejected(sandbox):
    resp = client.post(
        "/api/sync/push",
        json={"node_id": "phone", "ops": []},
    )
    assert resp.status_code == 401


def test_push_with_wrong_secret_is_rejected(sandbox):
    body = json.dumps({"node_id": "phone", "ops": []}).encode()
    bad_sig = identity.sign(body, "wrong-secret")
    resp = client.post(
        "/api/sync/push", content=body,
        headers={"content-type": "application/json", "x-node-id": "phone", "x-node-signature": bad_sig},
    )
    assert resp.status_code == 401


def test_push_from_untrusted_node_id_is_rejected(sandbox):
    body = json.dumps({"node_id": "stranger", "ops": []}).encode()
    sig = identity.sign(body, "anything")
    resp = client.post(
        "/api/sync/push", content=body,
        headers={"content-type": "application/json", "x-node-id": "stranger", "x-node-signature": sig},
    )
    assert resp.status_code == 401


def test_a_secret_not_listed_in_trusted_nodes_json_is_rejected(sandbox, monkeypatch):
    """Revocation must work by editing trusted_nodes.json alone — a node's
    old secret floating around in an env var must not be enough on its own."""
    monkeypatch.setenv("NODE_SECRETS", "phone:test-secret-do-not-use-in-prod,ex-node:leaked-secret")
    body = json.dumps({"node_id": "ex-node", "ops": []}).encode()
    sig = identity.sign(body, "leaked-secret")
    resp = client.post(
        "/api/sync/push", content=body,
        headers={"content-type": "application/json", "x-node-id": "ex-node", "x-node-signature": sig},
    )
    assert resp.status_code == 401, "a node absent from trusted_nodes.json must be rejected regardless of NODE_SECRETS"


def test_valid_push_reconciles_into_life_json(sandbox):
    clock = Clock("phone")
    ops = make_ops(clock, "project", "email-autopilot", {"status": "active", "next_action": "phone edit"})
    resp = _signed_push([o.to_dict() for o in ops])
    assert resp.status_code == 200
    assert resp.json()["merged"] == 2

    project = client.get("/api/projects/email-autopilot").json()
    assert project["status"] == "active"
    assert project["next_action"] == "phone edit"


def test_conflicting_push_is_recorded_and_newer_write_wins(sandbox):
    # local node writes first
    client.post("/api/projects/email-autopilot/touch", json={"status": "warming"})

    # remote node pushes a LATER write to the same field
    clock = Clock("phone")
    later_op = make_ops(clock, "project", "email-autopilot", {"status": "blocked"})[0]
    later_op = later_op.__class__(  # bump the wall clock so it's unambiguously later
        later_op.node_id, later_op.seq,
        later_op.hlc.__class__(later_op.hlc.wall_ms + 10_000_000, later_op.hlc.counter, later_op.node_id),
        later_op.resource, later_op.target_id, later_op.field, later_op.value,
    )
    resp = _signed_push([later_op.to_dict()])
    assert resp.status_code == 200
    assert resp.json()["conflicts"] == 1

    project = client.get("/api/projects/email-autopilot").json()
    assert project["status"] == "blocked", "the later write must win regardless of which node made it"

    conflicts = client.get("/api/sync/conflicts").json()["conflicts"]
    assert conflicts, "an overwritten edit must be disclosed, not silently dropped"
    assert conflicts[-1]["resource"] == "project"
    assert conflicts[-1]["field"] == "status"


def test_pushed_ops_are_idempotent_on_retry(sandbox):
    clock = Clock("phone")
    ops = [o.to_dict() for o in make_ops(clock, "project", "email-autopilot", {"status": "active"})]
    first = _signed_push(ops)
    second = _signed_push(ops)  # simulate a retried request after a dropped response
    assert first.status_code == second.status_code == 200
    resp = client.get("/api/sync/pull", params={"resource": "project"}).json()
    ids = [op["node_id"] + ":" + str(op["seq"]) for op in resp["ops"]]
    assert len(ids) == len(set(ids)), "no op should be duplicated by a retried push"


def test_horizon_push_reconciles_into_horizons_json(sandbox):
    clock = Clock("phone")
    ops = [o.to_dict() for o in make_ops(clock, "horizon", "week", {"goal": "set from phone"})]
    resp = _signed_push(ops)
    assert resp.status_code == 200
    chain = client.get("/api/horizons").json()["chain"]
    week = next(lv for lv in chain if lv["scale"] == "week")
    assert week["goal"] == "set from phone"


def test_boot_reports_this_node_and_conflict_count(sandbox):
    body = client.get("/boot").text
    assert f"node `{identity.NODE_ID}`" in body
    assert "resolved conflicts on record" in body
