"""YAML url, page, waitlist, score, and fleet route for /basex."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

R = Path(__file__).resolve().parent.parent
PAGE = R / "fleet/static/basex/index.html"
YAML = R / "fleet/data/projects.yaml"
SRC = R / "fleet/bin/fleet.py"

spec = importlib.util.spec_from_file_location("fleetboard", SRC)
fleetboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fleetboard)


def _sections(html):
    parts = re.split(r"<h2>([^<]+)</h2>", html)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_the_project_list_names_the_page():
    b = YAML.read_text().split("- name: BaseX", 1)[1].split("- name:", 1)[0]
    assert "url: /basex" in b and "url: TODO" not in b
    assert "awaiting-deployment" in b


def test_the_page_defines_the_three_bottom_lines():
    h = PAGE.read_text(); low = h.lower()
    assert "<h1>BaseX</h1>" in h
    assert "a new definition of value — triple bottom line (people, planet, prosperity)" in h
    assert "Status: awaiting deployment" in h
    assert "https://calendly.com/marsxr/basex" in h
    assert h.count("http") == 1
    sections = _sections(h)
    for name in ("People", "Planet", "Prosperity"):
        words = re.sub(r"<[^>]+>", " ", sections[name]).split()
        assert 90 <= len(words) <= 160, (name, len(words))
    assert "lorem" not in low and "TODO" not in h
    assert "127.0.0.1" not in h and "localhost" not in h


def test_the_page_has_an_architecture_diagram():
    h = PAGE.read_text()
    sections = _sections(h)
    assert "Architecture" in sections
    arch = sections["Architecture"]
    assert "<svg" in arch
    assert 'id="arch-title"' in arch
    for name in ("People", "Planet", "Prosperity", "impact score"):
        assert name in arch
    assert "geometric mean" in arch.lower()


def test_the_page_has_a_three_capital_calculator():
    h = PAGE.read_text()
    sections = _sections(h)
    assert "Impact score" in sections
    score = sections["Impact score"]
    assert 'name="people"' in score
    assert 'name="planet"' in score
    assert 'name="prosperity"' in score
    assert "Community" in score and "Ecological" in score and "Financial" in score
    assert "8, 27, 64 → 24" in score
    assert "0, 100, 100 → 0" in score
    assert "function impactScore" in h
    assert "Math.cbrt(people * planet * prosperity)" in h
    assert 'id="impact"' in score


def test_the_page_has_an_email_waitlist_form():
    h = PAGE.read_text()
    sections = _sections(h)
    assert "Waitlist" in sections
    wait = sections["Waitlist"]
    assert 'id="waitlist"' in wait
    assert 'type="email"' in wait
    assert 'name="email"' in wait
    assert 'action="/api/basex/waitlist"' in wait
    assert "fetch(\"/api/basex/waitlist\"" in h
    assert "not published" in wait.lower()


def test_fleet_answers_the_project_url():
    src = SRC.read_text()
    assert 'if path == "/basex"' in src
    assert "static" in src and "basex" in src and "index.html" in src
    assert 'if path == "/api/basex/waitlist"' in src
    assert "_flooding" in src
    assert "record_waitlist" in src


def test_waitlist_emails_are_gitignored():
    gi = (R / ".gitignore").read_text()
    assert "fleet/data/basex-waitlist.jsonl" in gi
    assert "basex-waitlist.jsonl.1" in gi


def test_a_valid_email_is_stored_and_not_echoed(tmp_path, monkeypatch):
    log = tmp_path / "basex-waitlist.jsonl"
    monkeypatch.setattr(fleetboard, "WAITLIST", log)
    out = fleetboard.record_waitlist("  Founder@Example.COM ")
    assert out == {"ok": True}
    rec = json.loads(log.read_text())
    assert rec["email"] == "founder@example.com"
    assert rec["ts"]
    assert "founder@example.com" not in json.dumps(out)


@pytest.mark.parametrize("raw", [
    "", "not-an-email", "a@b", "@x.com", "x@", "a@b.c\ncc:evil@x.com",
])
def test_junk_is_not_stored(tmp_path, monkeypatch, raw):
    log = tmp_path / "basex-waitlist.jsonl"
    monkeypatch.setattr(fleetboard, "WAITLIST", log)
    with pytest.raises(ValueError):
        fleetboard.record_waitlist(raw)
    assert not log.exists()


def test_the_waitlist_path_is_not_a_public_list():
    """GET must not grow a handler that dumps addresses."""
    src = SRC.read_text()
    get, post = src.split("def do_POST", 1)
    assert "/api/basex/waitlist" not in get
    assert "/api/basex/waitlist" in post
    block = post.split("/api/basex/waitlist", 1)[1].split("if path ==", 1)[0]
    assert "ev.emit" not in block
