"""YAML url, page, and fleet route for /ministry-of-memes."""
import re
from pathlib import Path

R = Path(__file__).resolve().parent.parent
PAGE = R / "fleet/static/ministry-of-memes/index.html"
YAML = R / "fleet/data/projects.yaml"
SRC = R / "fleet/bin/fleet.py"

SECTIONS = (
    "What it is",
    "Where it lives",
    "What it has published",
    "How to take part",
)

LIVE = (
    "https://planetarycouncil.github.io/ministry-of-memes-and-better-propaganda/",
    "https://github.com/PlanetaryCouncil/ministry-of-memes-and-better-propaganda",
    "https://github.com/PlanetaryCouncil/ministry-of-memes-and-better-propaganda/issues/3",
    "https://planetarycouncil.org/payload/",
    "https://planetarycouncil.org",
    "https://www.instagram.com/ministryofmemespropaganda",
)


def _block():
    return YAML.read_text().split(
        "- name: Ministry of Memes and Better Propaganda", 1)[1].split(
        "- name:", 1)[0]


def _sections(html):
    parts = re.split(r"<h2>([^<]+)</h2>", html)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_the_project_list_names_the_page():
    b = _block()
    assert "url: /ministry-of-memes" in b and "url: TODO" not in b
    assert "url: https://planetarycouncil.github.io" not in b
    assert "part_of: Planetary Council" in b
    assert "tags: [memes, art, propaganda]" in b


def test_the_tagline_is_the_first_sentence_of_what_it_is():
    b = _block()
    html = PAGE.read_text()
    what = re.sub(r"<[^>]+>", " ", _sections(html)["What it is"]).strip()
    first = what.split(".", 1)[0].strip()
    assert f"tagline: {first}" in b


def test_the_page_points_at_the_live_sources_without_duplicating_them():
    h = PAGE.read_text()
    low = h.lower()
    sections = _sections(h)
    assert list(sections) == list(SECTIONS)
    lives = sections["Where it lives"]
    assert LIVE[0] in lives
    assert "This page exists so the project list has somewhere to send a reader." in lives
    assert "not duplicated here" in lives.lower()
    published = sections["What it has published"]
    assert LIVE[1] in published
    assert LIVE[3] in published
    assert "https://planetarycouncil.org" in published
    assert "Until those sources change, they are the source, not this page." in published
    how = sections["How to take part"]
    assert LIVE[0] in how
    assert LIVE[2] in how
    assert LIVE[5] in how
    assert "@ministryofmemespropaganda" in how
    assert "There is no form on this page." in how
    for url in LIVE:
        assert url in h
    assert "lorem" not in low and "TODO" not in h
    assert "127.0.0.1" not in h and "localhost" not in h


def test_fleet_answers_the_project_url():
    src = SRC.read_text()
    assert 'if path == "/ministry-of-memes"' in src
    assert "ministry-of-memes" in src and "index.html" in src
