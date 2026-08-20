import json

from fastapi.testclient import TestClient

from app import fleet
from app.main import app

client = TestClient(app)


def _make_fleet(tmp_path, workers=(), events=()):
    root = tmp_path / "fleet"
    (root / "workers").mkdir(parents=True)
    for w in workers:
        (root / "workers" / f"{w['worker']}.json").write_text(json.dumps(w))
    if events:
        (root / "events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n")
    return root


def test_missing_fleet_is_a_normal_state(tmp_path):
    """This repo must run on a machine that has never had a fleet."""
    snap = fleet.snapshot(tmp_path / "nope")
    assert snap["present"] is False
    assert snap["workers"] == [] and snap["events"] == []
    assert snap["counts"]["total"] == 0


def test_workers_sort_worst_first(tmp_path):
    root = _make_fleet(tmp_path, workers=[
        {"worker": "aaa-green", "status": "pass", "summary": "76 passed"},
        {"worker": "zzz-broken", "status": "fail", "summary": "2 failed"},
        {"worker": "mmm-idle", "status": "idle", "summary": ""},
    ])
    names = [w["name"] for w in fleet.workers(root)]
    assert names[0] == "zzz-broken", "a failing worker must outrank a green one"
    assert names.index("aaa-green") < names.index("mmm-idle")


def test_needs_you_stays_raised_until_that_agent_reports_ok(tmp_path):
    """An alarm must survive later chatter from *other* agents — otherwise a
    busy fleet silently clears a standing request for a human."""
    root = _make_fleet(tmp_path, events=[
        {"ts": "2026-07-29T00:00:00+00:00", "agent": "proj", "level": "needs_you", "msg": "tests failed"},
        {"ts": "2026-07-29T00:00:01+00:00", "agent": "other", "level": "ok", "msg": "all good"},
    ])
    snap = fleet.snapshot(root)
    assert [b["agent"] for b in snap["blocked"]] == ["proj"]

    (root / "events.jsonl").write_text(
        (root / "events.jsonl").read_text()
        + json.dumps({"ts": "2026-07-29T00:00:02+00:00", "agent": "proj",
                      "level": "ok", "msg": "green again"}) + "\n")
    assert fleet.snapshot(root)["blocked"] == []


def test_unknown_event_level_is_downgraded_not_trusted(tmp_path):
    root = _make_fleet(tmp_path, events=[
        {"ts": "2026-07-29T00:00:00+00:00", "agent": "x",
         "level": "<script>", "msg": "hi"},
    ])
    assert fleet.snapshot(root)["events"][0]["level"] == "info"


def test_corrupt_lines_are_skipped(tmp_path):
    root = _make_fleet(tmp_path, workers=[
        {"worker": "ok-one", "status": "pass", "summary": "fine"},
    ])
    (root / "events.jsonl").write_text('not json\n{"ts":"x","agent":"a","level":"ok","msg":"m"}\n')
    (root / "workers" / "broken.json").write_text("{{{")
    snap = fleet.snapshot(root)
    assert [e["agent"] for e in snap["events"]] == ["a"]
    assert [w["name"] for w in snap["workers"]] == ["ok-one"]


def test_api_fleet_endpoint_shape():
    body = client.get("/api/fleet").json()
    for key in ("present", "path", "workers", "events", "blocked", "counts"):
        assert key in body
    assert set(body["counts"]) == {"total", "healthy", "attention"}


def test_api_fleet_does_not_publish_the_install_path(monkeypatch, tmp_path):
    root = _make_fleet(tmp_path)
    monkeypatch.setenv("FLEET_PATH", str(root))
    body = client.get("/api/fleet").json()
    assert body["path"] == "fleet"
    assert str(tmp_path) not in json.dumps(body)


def test_api_dashboard_contract_unchanged():
    """Agents read /api/dashboard; merging the fleet must not alter it."""
    assert "fleet" not in client.get("/api/dashboard").json()
