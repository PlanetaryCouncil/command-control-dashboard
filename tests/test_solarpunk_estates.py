"""YAML url, intake form, demand map, and fleet route for /solarpunk-estates."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

R = Path(__file__).resolve().parent.parent
PAGE = R / "fleet/static/solarpunk-estates/index.html"
YAML = R / "fleet/data/projects.yaml"
SRC = R / "fleet/bin/fleet.py"

spec = importlib.util.spec_from_file_location("fleetboard", SRC)
fleetboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fleetboard)

VALID = {
    "email": "  Steward@Example.COM ",
    "bioregion": "cascadia",
    "model": "coliving",
    "roles": ["resident", "land-steward"],
    "skills": "soil restoration, timber framing",
}


def _sections(html):
    parts = re.split(r"<h2>([^<]+)</h2>", html)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_the_project_list_names_the_page():
    b = YAML.read_text().split("- name: Solarpunk Estates", 1)[1].split("- name:", 1)[0]
    assert "url: /solarpunk-estates" in b and "url: TODO" not in b
    assert "url: https://solarpunkestates.org" not in b
    assert "awaiting-deployment" in b


def test_the_page_is_an_intake_form_with_a_demand_map():
    h = PAGE.read_text()
    low = h.lower()
    assert "<h1>Solarpunk Estates</h1>" in h
    assert "Building one billion regenerative homes — coliving, rent-to-own, rooted in nature, powered by the sun" in h
    assert "Status: awaiting deployment" in h
    assert "https://solarpunkestates.org" in h
    sections = _sections(h)
    assert list(sections) == ["What it is", "Expression of interest", "Demand by bioregion"]
    interest = sections["Expression of interest"]
    assert 'id="interest"' in interest
    assert 'type="email"' in interest and 'name="email"' in interest
    assert 'name="bioregion"' in interest
    assert 'value="coliving"' in interest and 'value="rent-to-own"' in interest
    assert 'name="roles"' in interest
    assert 'value="builder"' in interest and 'value="resident"' in interest
    assert 'value="land-steward"' in interest
    assert 'name="skills"' in interest
    assert 'action="/api/solarpunk-estates/interest"' in interest
    assert "fetch(\"/api/solarpunk-estates/interest\"" in h
    assert "not published" in interest.lower()
    demand = sections["Demand by bioregion"]
    assert 'id="demand-body"' in demand
    assert "fetch(\"/api/solarpunk-estates/demand\"" in h
    assert "lorem" not in low and "TODO" not in h
    assert "127.0.0.1" not in h and "localhost" not in h


def test_the_form_lists_the_same_bioregions_as_the_server():
    h = PAGE.read_text()
    for name in fleetboard.ESTATES_BIOREGIONS:
        assert f'value="{name}"' in h
    for name in fleetboard.ESTATES_MODELS:
        assert f'value="{name}"' in h
    for name in fleetboard.ESTATES_ROLES:
        assert f'value="{name}"' in h


def test_fleet_answers_the_project_url():
    src = SRC.read_text()
    assert 'if path == "/solarpunk-estates"' in src
    assert "static" in src and "solarpunk-estates" in src and "index.html" in src
    assert 'if path == "/api/solarpunk-estates/interest"' in src
    assert 'if path == "/api/solarpunk-estates/demand"' in src
    assert "_flooding" in src
    assert "record_estates_intake" in src
    assert "estates_demand" in src


def test_intake_emails_are_gitignored():
    gi = (R / ".gitignore").read_text()
    assert "fleet/data/solarpunk-estates-intake.jsonl" in gi
    assert "solarpunk-estates-intake.jsonl.1" in gi


def test_a_valid_interest_is_stored_and_not_echoed(tmp_path, monkeypatch):
    log = tmp_path / "solarpunk-estates-intake.jsonl"
    monkeypatch.setattr(fleetboard, "ESTATES_INTAKE", log)
    out = fleetboard.record_estates_intake(VALID)
    assert out == {"ok": True}
    rec = json.loads(log.read_text())
    assert rec["email"] == "steward@example.com"
    assert rec["bioregion"] == "cascadia"
    assert rec["model"] == "coliving"
    assert rec["roles"] == ["resident", "land-steward"]
    assert rec["skills"] == "soil restoration, timber framing"
    assert rec["ts"]
    dumped = json.dumps(out)
    assert "steward@example.com" not in dumped
    assert "email" not in dumped


@pytest.mark.parametrize("patch", [
    {"email": ""},
    {"email": "not-an-email"},
    {"bioregion": "atlantis"},
    {"model": "timeshare"},
    {"roles": []},
    {"roles": ["wizard"]},
    {"skills": ""},
    {"skills": " \n\t "},
])
def test_junk_is_not_stored(tmp_path, monkeypatch, patch):
    log = tmp_path / "solarpunk-estates-intake.jsonl"
    monkeypatch.setattr(fleetboard, "ESTATES_INTAKE", log)
    raw = dict(VALID)
    raw.update(patch)
    with pytest.raises(ValueError):
        fleetboard.record_estates_intake(raw)
    assert not log.exists()


def test_demand_is_counts_only_and_unique_per_email(tmp_path, monkeypatch):
    log = tmp_path / "solarpunk-estates-intake.jsonl"
    monkeypatch.setattr(fleetboard, "ESTATES_INTAKE", log)
    fleetboard.record_estates_intake(VALID)
    again = dict(VALID)
    again["bioregion"] = "andes"
    again["model"] = "rent-to-own"
    fleetboard.record_estates_intake(again)
    other = dict(VALID)
    other["email"] = "builder@example.org"
    other["bioregion"] = "andes"
    other["roles"] = ["builder"]
    fleetboard.record_estates_intake(other)
    demand = fleetboard.estates_demand()
    assert demand["total"] == 2
    assert demand["by_bioregion"]["andes"] == 2
    assert demand["by_bioregion"]["cascadia"] == 0
    assert demand["by_model"]["rent-to-own"] == 1
    assert demand["by_model"]["coliving"] == 1
    blob = json.dumps(demand)
    assert "email" not in blob
    assert "skills" not in blob
    assert "steward@example.com" not in blob
    assert "builder@example.org" not in blob


def test_the_interest_path_is_not_a_public_list():
    """GET must not grow a handler that dumps addresses."""
    src = SRC.read_text()
    get, post = src.split("def do_POST", 1)
    assert "/api/solarpunk-estates/interest" not in get
    assert "/api/solarpunk-estates/interest" in post
    assert "/api/solarpunk-estates/demand" in get
    block = post.split("/api/solarpunk-estates/interest", 1)[1].split("if path ==", 1)[0]
    assert "ev.emit" not in block
