"""The poems page asks for poems, at the top, before anyone has scrolled.

Marsita, 2026-09-09: "poetry... We have poems repo. Please at the top provide
link to the repo 'how to submit'. We want to collect poems."

A page that collects things has to say how, above the things it has already
collected -- an invitation under two hundred poems is an invitation nobody
reads.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import poems            # noqa: E402


def html():
    return poems.page("", "")


def test_the_invitation_exists():
    assert 'class="submit"' in html()


def test_it_is_at_the_top_above_the_poems():
    page = html()
    i = page.index('class="submit"')
    for after in ('<article class="poem"', 'class="empty"'):
        j = page.find(after)
        if j != -1:
            assert i < j, f"{after} comes first"


def test_it_is_in_the_header_not_the_footer():
    page = html()
    i = page.index('class="submit"')
    assert page.rindex("<header", 0, i) > page.rfind("</header>", 0, i)


def test_it_links_to_the_repo_and_to_the_new_issue_form():
    """"how to submit" has to land on the form, not on a README somebody has
    to read first."""
    page = html()
    block = page[page.index('class="submit"'):][:900]
    assert "https://github.com/PlanetaryCouncil/poems/issues/new" in block
    assert "https://github.com/PlanetaryCouncil/poems" in block
    assert "how to submit" in block


def test_it_says_an_issue_not_a_pull_request():
    """A poem should not need a fork."""
    block = html()[html().index('class="submit"'):][:900].lower()
    assert "issue" in block
    assert "no fork" in block


def test_it_invites_people_as_well_as_agents():
    """The page is otherwise entirely machine-generated couplets, which reads
    as closed unless it says otherwise."""
    block = html()[html().index('class="submit"'):][:900].lower()
    assert "human" in block


def test_the_links_open_safely():
    block = html()[html().index('class="submit"'):][:900]
    assert block.count('rel="noopener"') == 2
