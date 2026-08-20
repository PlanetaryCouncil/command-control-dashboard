"""The NUC bridge must not put a LAN login on the public board."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
spec = importlib.util.spec_from_file_location("nuc_bridge", BIN / "nuc-bridge.py")
nuc_bridge = importlib.util.module_from_spec(spec)
sys.modules["nuc_bridge"] = nuc_bridge
spec.loader.exec_module(nuc_bridge)


def test_refuses_to_run_without_FLEET_NUC(monkeypatch, capsys):
    monkeypatch.delenv("FLEET_NUC", raising=False)
    assert nuc_bridge.main() == 2
    assert "FLEET_NUC" in capsys.readouterr().err


def test_source_does_not_name_a_lan_login():
    src = Path(nuc_bridge.__file__).read_text()
    assert "nuc.local" not in src
    assert "m@" not in src


def test_ssh_failure_does_not_echo_stderr(monkeypatch):
    class R:
        returncode = 1
        stdout = ""
        stderr = "you@nuc.local: Permission denied (publickey)\n"

    monkeypatch.setattr(nuc_bridge.subprocess, "run", lambda *a, **k: R())
    rep = nuc_bridge.fetch_report("anyone@anywhere")
    blob = json.dumps(rep)
    assert "Permission denied" not in blob
    assert "nuc.local" not in blob
    assert rep["unreachable"] == "ssh failed"


def test_raw_last_json_paths_do_not_reach_the_worker_card():
    raw_results = [{
        "profile": "desktop",
        "status": "200",
        "load_s": 1.2,
        "ok": True,
        "shot": "/home/YOU/monitor/shots/desktop.png",
    }]
    rep = nuc_bridge.public_report(True, results=raw_results)
    worker = nuc_bridge.worker_record(rep)
    blob = json.dumps(worker)
    assert "/home/YOU" not in blob
    assert "shot" not in blob
    assert "desktop" in worker["summary"]


def test_stale_on_disk_card_is_stripped_at_load():
    """A writer from last week must not keep leaking through /workers.json."""
    spec = importlib.util.spec_from_file_location(
        "fleetboard_sanitize", BIN / "fleet.py")
    fleetboard = importlib.util.module_from_spec(spec)
    sys.modules["fleetboard_sanitize"] = fleetboard
    spec.loader.exec_module(fleetboard)
    dirty = {
        "worker": "nuc",
        "detail": json.dumps({
            "ok": True,
            "results": [{"profile": "desktop", "ok": True,
                         "shot": "/home/YOU/monitor/shots/desktop.png"}],
        }),
    }
    blob = json.dumps(fleetboard.sanitize_worker(dirty))
    assert "/home/YOU" not in blob
    assert "shot" not in blob
    assert "desktop" in blob


def test_every_worker_field_is_sanitized_before_publication():
    spec = importlib.util.spec_from_file_location(
        "fleetboard_public_fields", BIN / "fleet.py")
    fleetboard = importlib.util.module_from_spec(spec)
    sys.modules["fleetboard_public_fields"] = fleetboard
    spec.loader.exec_module(fleetboard)
    dirty = {
        "worker": "old-writer",
        "target": "/Users/operator/private/repo",
        "summary": "reachable at 192.168.1.23",
        "detail": json.dumps({"nested": "/home/operator/secret"}),
    }
    blob = json.dumps(fleetboard.sanitize_worker(dirty))
    assert "/Users/" not in blob
    assert "/home/" not in blob
    assert "192.168.1.23" not in blob


def test_publish_creates_the_workers_dir(tmp_path):
    rep = nuc_bridge.public_report(False, unreachable="ssh failed")
    worker = nuc_bridge.publish(rep, fleet=tmp_path)
    written = json.loads((tmp_path / "workers" / "nuc.json").read_text())
    assert written["worker"] == "nuc"
    assert written["status"] == "fail"
    assert worker["summary"].endswith("ssh failed")
