"""A code you can email, that is worthless the moment it is used.

Reading twelve words down a phone works when the far side is a person. When it
is an agent, or when all you have is email, there is nothing to read to — so the
mail carries an invitation instead of a key.

The three properties below are the entire security argument, and each has a test
because each one alone is not enough:

  single use   an interceptor who redeems first makes your friend's attempt
               fail. You do not hope nobody read the mail; you find out.
  expiry       bounds how long a stolen mail is worth anything.
  hashed       the file that mints credentials must not itself be one.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import identity, main, pairing
from app.main import app

client = TestClient(app)


@pytest.fixture
def store(tmp_path, monkeypatch):
    registry = tmp_path / "trusted_nodes.json"
    registry.write_text(json.dumps({"nodes": []}))
    monkeypatch.setattr(main, "TRUSTED_NODES_PATH", registry)
    monkeypatch.setattr(main, "PAIRING_PATH", tmp_path / "pairing.json")
    monkeypatch.setattr(main, "NODE_SECRETS_FILE", tmp_path / "node_secrets.json")
    monkeypatch.setattr(main, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setenv("NODE_SECRETS", "")
    monkeypatch.setenv("NODE_SECRETS_FILE", str(tmp_path / "node_secrets.json"))
    return tmp_path


def mint(store, node="friend", hours=6):
    return pairing.invite(store / "pairing.json", node, ttl_hours=hours)["code"]


def test_a_code_becomes_a_working_key(store):
    r = client.post("/api/pair", json={"code": mint(store)})
    assert r.status_code == 201
    body = r.json()
    assert body["node_id"] == "friend"
    assert len(body["secret"]) == 64

    # The point of the whole exercise: that secret must now authenticate.
    secrets_map = identity.load_trusted_nodes(main.TRUSTED_NODES_PATH)
    assert secrets_map.get("friend") == body["secret"]


def test_a_code_works_exactly_once(store):
    code = mint(store)
    assert client.post("/api/pair", json={"code": code}).status_code == 201
    second = client.post("/api/pair", json={"code": code})
    assert second.status_code == 400
    assert "already redeemed" in second.json()["detail"]


def test_the_second_attempt_says_when_and_from_where(store):
    """An interception detector is only useful if it says what happened."""
    code = mint(store)
    client.post("/api/pair", json={"code": code})
    detail = client.post("/api/pair", json={"code": code}).json()["detail"]
    assert "already redeemed at" in detail
    assert "from" in detail


def test_an_expired_code_is_refused(store):
    path = store / "pairing.json"
    pairing.invite(path, "late", ttl_hours=6)
    data = json.loads(path.read_text())
    data["invites"][0]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    path.write_text(json.dumps(data))
    # Reconstruct a code that hashes to the stored one? You cannot — which is
    # the point. Redeem through the module with a known code instead.
    fresh = pairing.invite(path, "late2", ttl_hours=-1)
    with pytest.raises(ValueError, match="expired"):
        pairing.redeem(path, fresh["code"])


def test_an_unknown_code_is_refused(store):
    r = client.post("/api/pair", json={"code": "aaaaa-bbbbb-ccccc"})
    assert r.status_code == 400
    assert "unknown code" in r.json()["detail"]


def test_the_code_is_never_stored(store):
    """A file that can mint credentials must not be replayable by its reader."""
    code = mint(store)
    on_disk = (store / "pairing.json").read_text()
    assert code not in on_disk
    assert code.replace("-", "") not in on_disk
    assert "code_sha256" in on_disk


def test_the_minted_secret_is_never_stored_in_the_invite(store):
    code = mint(store)
    secret = client.post("/api/pair", json={"code": code}).json()["secret"]
    assert secret not in (store / "pairing.json").read_text()


def test_minting_a_second_invite_kills_the_first(store):
    """For when you have just emailed the wrong address."""
    path = store / "pairing.json"
    first = pairing.invite(path, "friend")["code"]
    pairing.invite(path, "friend")
    with pytest.raises(ValueError, match="unknown code"):
        pairing.redeem(path, first)


def test_a_secret_is_inert_until_the_node_is_registered(store):
    """Revocation stays one line of JSON, even for keys minted by an endpoint."""
    secret = client.post("/api/pair", json={"code": mint(store)}).json()["secret"]
    assert identity.load_trusted_nodes(main.TRUSTED_NODES_PATH)["friend"] == secret

    registry = json.loads(main.TRUSTED_NODES_PATH.read_text())
    registry["nodes"] = [n for n in registry["nodes"] if n["node_id"] != "friend"]
    main.TRUSTED_NODES_PATH.write_text(json.dumps(registry))
    assert "friend" not in identity.load_trusted_nodes(main.TRUSTED_NODES_PATH)


def test_a_hand_set_environment_key_is_never_overwritten(store, monkeypatch):
    """A key you set yourself must not be silently replaced by an issued one."""
    secret = client.post("/api/pair", json={"code": mint(store)}).json()["secret"]
    monkeypatch.setenv("NODE_SECRETS", "friend:mine-not-yours")
    assert identity.load_trusted_nodes(main.TRUSTED_NODES_PATH)["friend"] == "mine-not-yours"
    assert secret != "mine-not-yours"


def test_refusals_are_logged_so_interception_is_visible(store):
    code = mint(store)
    client.post("/api/pair", json={"code": code})
    client.post("/api/pair", json={"code": code})
    log = (store / "events.jsonl").read_text()
    assert "pair.redeemed" in log
    assert "pair.refused" in log


def test_live_invites_exclude_spent_and_expired(store):
    path = store / "pairing.json"
    code = pairing.invite(path, "alive")["code"]
    pairing.invite(path, "dead", ttl_hours=-1)
    spent = pairing.invite(path, "used")["code"]
    pairing.redeem(path, spent)
    assert [i["node_id"] for i in pairing.live(path)] == ["alive"]
    assert code  # minted, unspent, still live
