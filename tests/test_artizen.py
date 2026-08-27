"""YAML url, page, and fleet route for /artizen."""
import re
from pathlib import Path

R = Path(__file__).resolve().parent.parent
PAGE = R / "fleet/static/artizen/index.html"
YAML = R / "fleet/data/projects.yaml"
SRC = R / "fleet/bin/fleet.py"

SECTIONS = (
    "What it is",
    "How funding works",
    "What a donation does",
    "Who raises",
)

MEMBERS = (
    "Labour Union of Higherdimensional Shapeshifters",
    "Marsita the Ultra",
    "Planetary Council",
    "Money from the Future",
)


def _block():
    return YAML.read_text().split("- name: Artizen.fund projects", 1)[1].split(
        "- name:", 1)[0]


def _sections(html):
    parts = re.split(r"<h2>([^<]+)</h2>", html)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_the_project_list_names_the_page():
    b = _block()
    assert "url: /artizen" in b and "url: TODO" not in b
    assert "url: https://artizen.fund" not in b
    assert "tags: [art, funding]" in b
    for name in MEMBERS:
        assert name in b


def test_the_tagline_is_the_first_sentence_of_what_it_is():
    b = _block()
    html = PAGE.read_text()
    what = re.sub(r"<[^>]+>", " ", _sections(html)["What it is"]).strip()
    first = what.split(".", 1)[0].strip()
    assert f"tagline: {first}" in b


def test_the_page_explains_funding_and_impact_without_invented_tallies():
    h = PAGE.read_text()
    low = h.lower()
    sections = _sections(h)
    assert list(sections) == list(SECTIONS)
    how = sections["How funding works"].lower()
    assert "fund drive" in how
    assert "artifact" in how
    assert "match" in how
    assert "endowment" in how
    assert "impact report" in how
    impact = sections["What a donation does"].lower()
    assert "goes to that project" in impact
    assert "not invented here" in impact
    who = sections["Who raises"]
    for name in MEMBERS:
        assert name in who
    assert "https://artizen.fund" in h
    assert "https://artizen.fund/index/p/labour-union-of-higher-dimensional-shapeshifters" in h
    assert "lorem" not in low and "TODO" not in h
    assert "127.0.0.1" not in h and "localhost" not in h


def test_fleet_answers_the_project_url():
    src = SRC.read_text()
    assert 'if path == "/artizen"' in src
    assert "artizen" in src and "index.html" in src
