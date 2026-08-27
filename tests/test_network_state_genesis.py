"""YAML url, page, and fleet route for /network-state-genesis."""
import re
from pathlib import Path

R = Path(__file__).resolve().parent.parent
PAGE = R / "fleet/static/network-state-genesis/index.html"
YAML = R / "fleet/data/projects.yaml"
SRC = R / "fleet/bin/fleet.py"

SECTIONS = (
    "What it is",
    "Where it lives",
    "What it has published",
    "How to take part",
)


def _block():
    return YAML.read_text().split("- name: Network State Genesis", 1)[1].split(
        "- name:", 1)[0]


def _sections(html):
    parts = re.split(r"<h2>([^<]+)</h2>", html)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_the_project_list_names_the_page():
    b = _block()
    assert "url: /network-state-genesis" in b and "url: TODO" not in b
    assert "url: https://genesis.re" not in b
    assert "tags: [governance, network-state]" in b
    assert 'twitter: "@genesisdotre"' in b


def test_the_tagline_is_the_first_sentence_of_what_it_is():
    b = _block()
    html = PAGE.read_text()
    what = re.sub(r"<[^>]+>", " ", _sections(html)["What it is"]).strip()
    first = what.split(".", 1)[0].strip()
    assert f"tagline: {first}" in b


def test_the_page_points_at_the_live_site_without_taking_payment():
    h = PAGE.read_text()
    low = h.lower()
    sections = _sections(h)
    assert list(sections) == list(SECTIONS)
    lives = sections["Where it lives"]
    assert "https://genesis.re" in lives
    assert "not duplicated here" in lives.lower()
    published = sections["What it has published"]
    assert "Network-State-Genesis-WHITEPAPER-compressed.pdf" in published
    assert "Network-State-Genesis-WHITEPAPER-V2.pdf" in published
    assert "2021" in published and "2024" in published
    how = sections["How to take part"]
    assert "https://genesis.re" in how
    assert "@genesisdotre" in how
    assert "https://x.com/genesisdotre" in how
    assert "https://calendly.com/marsxr/basex" in how
    assert "0x" not in h
    assert "lorem" not in low and "TODO" not in h
    assert "127.0.0.1" not in h and "localhost" not in h


def test_fleet_answers_the_project_url():
    src = SRC.read_text()
    assert 'if path == "/network-state-genesis"' in src
    assert "network-state-genesis" in src and "index.html" in src
