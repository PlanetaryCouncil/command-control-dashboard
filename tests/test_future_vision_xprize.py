"""YAML url, page, and fleet route for /future-vision-xprize."""
import re
from pathlib import Path

R = Path(__file__).resolve().parent.parent
PAGE = R / "fleet/static/future-vision-xprize/index.html"
YAML = R / "fleet/data/projects.yaml"
SRC = R / "fleet/bin/fleet.py"

SECTIONS = (
    "What it is",
    "Where it lives",
    "What it has published",
    "How to take part",
)

LIVE = (
    "https://futurevisionxprize.com",
    "https://vote.futurevisionxprize.com/",
    "https://moonshots.com",
)


def _block():
    return YAML.read_text().split("- name: Future Vision XPRIZE", 1)[1].split(
        "- name:", 1)[0]


def _sections(html):
    parts = re.split(r"<h2>([^<]+)</h2>", html)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_the_project_list_names_the_page():
    b = _block()
    assert "url: /future-vision-xprize" in b and "url: TODO" not in b
    assert "tags: [futures, prize]" in b


def test_the_tagline_is_the_first_sentence_of_what_it_is():
    b = _block()
    html = PAGE.read_text()
    what = re.sub(r"<[^>]+>", " ", _sections(html)["What it is"]).strip()
    first = what.split(".", 1)[0].strip()
    assert f"tagline: {first}" in b


def test_the_page_points_at_the_live_vote_not_a_future_announcement():
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
    assert "2,500" in published
    assert "September 2026" in published
    assert "Until those sources change, they are the source, not this page." in published
    how = sections["How to take part"]
    assert LIVE[1] in how
    assert LIVE[2] in how
    assert "There is no form on this page." in how
    assert "First challenge announced soon" not in h
    assert "propose a challenge" not in low
    assert "nothing to submit against" not in low
    for url in LIVE:
        assert url in h
    assert "imagination athlete" in low and "not a grant for a device" in low
    assert "lorem" not in low and "TODO" not in h
    assert "127.0.0.1" not in h and "localhost" not in h


def test_fleet_answers_the_project_url():
    src = SRC.read_text()
    assert 'if path == "/future-vision-xprize"' in src
    assert "future-vision-xprize" in src and "index.html" in src


def test_the_project_list_names_the_film():
    b = _block()
    assert "film: New Hope, Permission Not Required?" in b
    assert "watch: https://www.youtube.com/watch?v=mjeihsU0M-8" in b


def test_the_page_names_the_film():
    h = PAGE.read_text()
    assert "New Hope, Permission Not Required?" in h
    assert "https://www.youtube.com/watch?v=mjeihsU0M-8" in h
    sections = _sections(h)
    published = sections["What it has published"]
    assert "New Hope, Permission Not Required?" in published
    assert 'href="https://www.youtube.com/watch?v=mjeihsU0M-8"' in published
    how = sections["How to take part"]
    assert "New Hope, Permission Not Required?" in how
