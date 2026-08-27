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


def test_api_fleet_sanitizes_worker_and_event_host_details(monkeypatch, tmp_path):
    root = _make_fleet(
        tmp_path,
        workers=[{
            "worker": "private-worker",
            "status": "pass",
            "summary": "repo at /Users/operator/private/project",
        }],
        events=[{
            "ts": "2026-08-20T00:00:00+00:00",
            "agent": "private-worker",
            "level": "needs_you",
            "msg": "node 192.168.1.23 needs attention",
        }],
    )
    monkeypatch.setenv("FLEET_PATH", str(root))
    body = client.get("/api/fleet").json()
    blob = json.dumps(body)
    assert "/Users/" not in blob
    assert "192.168.1.23" not in blob
    assert body["workers"][0]["summary"] == ""
    assert body["events"][0]["msg"] == ""
    assert body["blocked"][0]["msg"] == ""


def test_api_dashboard_contract_unchanged():
    """Agents read /api/dashboard; merging the fleet must not alter it."""
    assert "fleet" not in client.get("/api/dashboard").json()


def test_a_green_laggard_is_not_still_passing(tmp_path):
    """command-control-dashboard sat at `pass` with last_run 2026-08-07T16:56:28Z
    while the rest of the fleet kept reporting. The cockpit painted that as
    healthy, so the public dashboard spread a ten-day-old result as current.
    """
    root = _make_fleet(tmp_path, workers=[
        {"worker": "command-control-dashboard", "kind": "watchdog",
         "status": "pass", "summary": "337 passed",
         "last_run": "2026-08-07T16:56:28Z"},
        {"worker": "visitors", "kind": "meter", "status": "pass",
         "summary": "841 hits/24h", "last_run": "2026-08-23T04:59:00Z"},
    ])
    by_name = {w["name"]: w for w in fleet.workers(root)}
    assert by_name["command-control-dashboard"]["status"] == "stale"
    assert by_name["command-control-dashboard"]["stale_hours"] >= 24
    assert by_name["visitors"]["status"] == "pass"
    snap = fleet.snapshot(root)
    assert snap["counts"]["healthy"] == 1
    assert snap["counts"]["attention"] == 1


def test_six_hours_behind_is_a_warning_not_a_dead_card(tmp_path):
    root = _make_fleet(tmp_path, workers=[
        {"worker": "agent-comms", "status": "pass", "summary": "3/3 hops",
         "last_run": "2026-08-03T19:18:38Z"},
        {"worker": "watchdog", "status": "pass", "summary": "244 passed",
         "last_run": "2026-08-04T12:40:15Z"},
    ])
    by_name = {w["name"]: w for w in fleet.workers(root)}
    assert by_name["agent-comms"]["status"] == "warn"
    assert by_name["agent-comms"]["stale_hours"] == 17
    assert by_name["watchdog"]["status"] == "pass"
    assert fleet.snapshot(root)["counts"]["attention"] == 0


def test_workers_running_in_step_are_never_stale(tmp_path):
    """A laptop asleep all weekend ages every check together; that is not one
    worker's fault and must not light the dashboard up."""
    root = _make_fleet(tmp_path, workers=[
        {"worker": "a", "status": "pass", "last_run": "2026-08-01T10:00:00Z"},
        {"worker": "b", "status": "pass", "last_run": "2026-08-01T10:30:00+00:00"},
    ])
    assert all("stale_hours" not in w for w in fleet.workers(root))
    assert all(w["status"] == "pass" for w in fleet.workers(root))


def test_a_loud_status_is_not_softened_by_staleness(tmp_path):
    root = _make_fleet(tmp_path, workers=[
        {"worker": "agent-comms", "status": "fail", "summary": "0/3 hops",
         "last_run": "2026-08-07T16:56:28Z"},
        {"worker": "visitors", "status": "pass",
         "last_run": "2026-08-23T04:59:00Z"},
    ])
    by_name = {w["name"]: w for w in fleet.workers(root)}
    assert by_name["agent-comms"]["status"] == "fail"
    assert by_name["agent-comms"]["stale_hours"] >= 24


def test_stale_sorts_with_the_failures(tmp_path):
    root = _make_fleet(tmp_path, workers=[
        {"worker": "quiet", "status": "pass",
         "last_run": "2026-08-23T04:59:00Z"},
        {"worker": "laggard", "status": "pass",
         "last_run": "2026-08-07T16:56:28Z"},
        {"worker": "broken", "status": "fail",
         "last_run": "2026-08-23T04:59:00Z"},
    ])
    assert [w["name"] for w in fleet.workers(root)] == [
        "broken", "laggard", "quiet"]


def test_the_cockpit_paints_stale_as_trouble():
    """The JSON downgrade is wasted if the template still paints stale green."""
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent
            / "legacy" / "app" / "templates" / "dashboard.html").read_text()
    assert 'w.status === "stale"' in html
    assert "stale ${w.stale_hours}h" in html
