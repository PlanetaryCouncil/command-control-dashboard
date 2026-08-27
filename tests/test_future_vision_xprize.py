"""YAML url, page, and fleet route for /future-vision-xprize."""
from pathlib import Path

R = Path(__file__).resolve().parent.parent
PAGE = R / "fleet/static/future-vision-xprize/index.html"
YAML = R / "fleet/data/projects.yaml"
SRC = R / "fleet/bin/fleet.py"


def test_the_project_list_names_the_page():
    b = YAML.read_text().split("- name: Future Vision XPRIZE", 1)[1].split("- name:", 1)[0]
    assert "url: /future-vision-xprize" in b and "url: TODO" not in b


def test_the_page_has_four_sections_and_no_placeholders():
    h = PAGE.read_text(); low = h.lower()
    for s in ("Future Vision XPRIZE", "First challenge announced soon",
              "mailto:marsXrobertson@gmail.com", "https://calendly.com/marsxr/basex"):
        assert s in h
    assert "imagination athlete" in low and "not a grant for a device" in low
    assert "propose a challenge" in low
    assert "lorem" not in low and "TODO" not in h
    assert "127.0.0.1" not in h and "localhost" not in h


def test_fleet_answers_the_project_url():
    src = SRC.read_text()
    assert 'if path == "/future-vision-xprize"' in src
    assert "future-vision-xprize" in src and "index.html" in src
