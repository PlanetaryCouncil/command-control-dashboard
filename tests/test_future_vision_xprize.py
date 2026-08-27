"""Future Vision XPRIZE was a named project with nowhere to send a person.

The dashboard rendered the tagline and url: TODO. This pins that the page
is on disk, the project list points at it, and the fleet serves that URL.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "fleet" / "static" / "future-vision-xprize" / "index.html"
PROJECTS = ROOT / "fleet" / "data" / "projects.yaml"
FLEET_SRC = ROOT / "fleet" / "bin" / "fleet.py"


def test_the_project_list_names_the_page():
    text = PROJECTS.read_text()
    block = text.split("- name: Future Vision XPRIZE", 1)[1].split("- name:", 1)[0]
    assert "url: /future-vision-xprize" in block
    assert "url: TODO" not in block


def test_the_page_has_four_sections_and_no_placeholders():
    html = PAGE.read_text()
    assert "Future Vision XPRIZE" in html
    assert "imagination athlete" in html.lower()
    assert "not a grant for a device" in html.lower()
    assert "First challenge announced soon" in html
    assert "mailto:marsXrobertson@gmail.com" in html
    assert "https://calendly.com/marsxr/basex" in html
    assert "propose a challenge" in html.lower()
    assert "lorem" not in html.lower()
    assert "TODO" not in html
    assert "127.0.0.1" not in html
    assert "localhost" not in html


def test_fleet_answers_the_project_url():
    src = FLEET_SRC.read_text()
    assert 'if path == "/future-vision-xprize"' in src
    assert "future-vision-xprize" in src and "index.html" in src
