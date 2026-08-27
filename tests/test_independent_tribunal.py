"""YAML url, page, and fleet route for /independent-tribunal."""
import re
from pathlib import Path

R = Path(__file__).resolve().parent.parent
PAGE = R / "fleet/static/independent-tribunal/index.html"
YAML = R / "fleet/data/projects.yaml"
SRC = R / "fleet/bin/fleet.py"

SECTIONS = (
    "What it is",
    "What it rules on",
    "Who sits on it",
    "How to bring something to it",
)


def _block():
    return YAML.read_text().split("- name: Independent Tribunal", 1)[1].split(
        "- name:", 1)[0]


def _sections(html):
    parts = re.split(r"<h2>([^<]+)</h2>", html)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_the_project_list_names_the_page():
    b = _block()
    assert "url: /independent-tribunal" in b and "url: TODO" not in b
    assert "tags: [governance, justice, disputes]" in b
    assert 'twitter: "@IndependentTrib"' in b
    assert 'telegram: "@IndependentTribunal"' in b


def test_the_tagline_is_the_first_sentence_of_what_it_is():
    b = _block()
    html = PAGE.read_text()
    what = re.sub(r"<[^>]+>", " ", _sections(html)["What it is"]).strip()
    first = what.split(".", 1)[0].strip()
    assert f"tagline: {first}" in b
    assert "An independent tribunal" not in b.split("tagline:", 1)[1].split("\n", 1)[0]


def test_the_page_has_four_sections_and_no_placeholders():
    h = PAGE.read_text()
    low = h.lower()
    sections = _sections(h)
    assert list(sections) == list(SECTIONS)
    what = re.sub(r"<[^>]+>", " ", sections["What it is"]).strip()
    assert what.count(".") >= 1
    rules = sections["What it rules on"].lower()
    assert "will hear" in rules and "will not hear" in rules
    who = sections["Who sits on it"].lower()
    assert "being convened" in who
    how = sections["How to bring something to it"]
    assert "@IndependentTrib" in how and "@IndependentTribunal" in how
    assert "https://x.com/IndependentTrib" in how
    assert "https://t.me/IndependentTribunal" in how
    assert "lorem" not in low and "TODO" not in h
    assert "127.0.0.1" not in h and "localhost" not in h


def test_fleet_answers_the_project_url():
    src = SRC.read_text()
    assert 'if path == "/independent-tribunal"' in src
    assert "independent-tribunal" in src and "index.html" in src
