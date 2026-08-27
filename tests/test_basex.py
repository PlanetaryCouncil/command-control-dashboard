"""YAML url, page, and fleet route for /basex."""
import re
from pathlib import Path

R = Path(__file__).resolve().parent.parent
PAGE = R / "fleet/static/basex/index.html"
YAML = R / "fleet/data/projects.yaml"
SRC = R / "fleet/bin/fleet.py"


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
    parts = re.split(r"<h2>([^<]+)</h2>", h)
    sections = {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}
    for name in ("People", "Planet", "Prosperity"):
        words = re.sub(r"<[^>]+>", " ", sections[name]).split()
        assert 90 <= len(words) <= 160, (name, len(words))
    assert "lorem" not in low and "TODO" not in h
    assert "127.0.0.1" not in h and "localhost" not in h


def test_fleet_answers_the_project_url():
    src = SRC.read_text()
    assert 'if path == "/basex"' in src
    assert "static" in src and "basex" in src and "index.html" in src
