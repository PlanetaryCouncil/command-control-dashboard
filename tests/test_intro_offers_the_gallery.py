"""The gallery is on the first thing a stranger reads.

It was in the nav and nowhere else, so a visitor met "say hi" and "sign the
pad" but had to find the faces themselves. The intro is the one line most
people read; a door that is not on it is a door most people do not use.
"""
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "fleet" / "bin"
sys.path.insert(0, str(BIN))
import oneview, nav  # noqa: E402

GALLERY = "https://planetarycouncil.github.io/selfie-gallery/"
ARGS = ("[]", "[]", "tok")


def test_the_intro_offers_the_gallery():
    page = oneview.page(*ARGS, remote=True)
    assert GALLERY in page, "the gallery is missing from the welcome line"


def _welcome(page):
    """Just the welcome line. The same hrefs appear in the nav, so an
    unscoped index() measures the wrong element and passes or fails for
    reasons that have nothing to do with the intro."""
    start = page.index('id="welcome"')
    return page[start:page.index("</div>", start)]


def test_it_sits_beside_say_hi():
    """Next to the other two invitations, not stranded at the end."""
    w = _welcome(oneview.page(*ARGS, remote=True))
    hi, gal, pad = w.index("/hi'"), w.index(GALLERY), w.index("/signatures'")
    assert hi < gal < pad, "the gallery belongs between 'say hi' and the pad"


def test_the_nav_and_the_intro_point_at_the_same_gallery():
    """Two hardcoded copies of one URL is one copy too many to trust; if they
    ever disagree, this says so before a visitor finds out."""
    assert any(href == GALLERY for href, _ in nav.PAGES), \
        "nav no longer points where the intro does"


def test_the_intro_asks_rather_than_merely_offers():
    """"see what you can do to advance humanity" is a slogan; "please sign" is
    a request. Only one of them gets a stranger to leave a mark."""
    w = _welcome(oneview.page(*ARGS, remote=True))
    assert "please sign" in w
    assert "every hand is different" in w


def test_the_board_says_its_own_name():
    """"Missing top level Singularity Engineering intro notice" -- the name
    was only on /intro, a page you have to navigate to."""
    w = _welcome(oneview.page(*ARGS, remote=False))
    assert "The Singularity Engineering Fleet." in w
    assert "Not an AI uprising" in w


def test_the_name_is_not_printed_twice():
    """Remote gets the FIRST CONTACT banner directly above the welcome line.
    Leading the welcome with the same name printed it twice (2026-09-02)."""
    page = oneview.page(*ARGS, remote=True)
    assert "NOT AN AI UPRISING" in page.upper()          # the banner says it
    assert page.count("Not an AI uprising") == 0         # the welcome does not


def test_the_tab_says_which_door():
    """Two tabs both reading GAIA cannot be told apart."""
    assert "(local)" in oneview.page(*ARGS, remote=False)
    assert "(public)" in oneview.page(*ARGS, remote=True)


def test_the_operator_sees_it_too():
    """It was gated on `remote`, so the person who looks at this board all
    day was the one person the fleet never introduced itself to."""
    assert 'id="welcome"' in oneview.page(*ARGS, remote=False)
