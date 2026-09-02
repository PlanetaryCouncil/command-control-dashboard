"""The three sites are one project; a stranger who finds one should see all.

Marsita, 2026-09-02: "mention planetary infrastructure PlanetaryCouncil.org
IndependentTribunal.org and BaseX.com ----> partnership for the goals".
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))
import firstcontact                                        # noqa: E402

SITES = ("PlanetaryCouncil.org", "IndependentTribunal.org", "BaseX.com")


def test_first_contact_names_all_three():
    text = " ".join(firstcontact.sentences())
    for site in SITES:
        assert site in text, site


def test_each_site_is_given_a_job():
    text = " ".join(firstcontact.sentences())
    for verb in ("decides", "contests", "deploys"):
        assert verb in text, verb


def test_the_quarter_goal_is_the_deployment():
    levels = json.loads((ROOT / "data" / "horizons.json").read_text())["levels"]
    q = next(l for l in levels if l["scale"] == "quarter")
    assert "BaseX.com" in q["goal"]
    assert q["why"], "a goal without a why is a slogan"


def test_the_intro_still_fits_its_budget():
    """Ten sentences, enforced here rather than by good intentions."""
    assert len(firstcontact.sentences()) <= firstcontact.SENTENCE_BUDGET


def test_the_demo_is_one_click_from_first_contact():
    """A demo needs testers more than readers. Marsita: "link to
    demo.basex.com to incentivize testing"."""
    paths = [path for _, path, _ in firstcontact.STEPS]
    assert "https://demo.basex.com" in paths


def test_the_ask_is_specific_not_polite():
    """"Take a look" gets nothing back. "Break it and say what broke" does."""
    note = next(n for _, p, n in firstcontact.STEPS
                if p == "https://demo.basex.com")
    assert "break it" in note.lower()


def test_the_board_footer_carries_all_three():
    src = (ROOT / "fleet" / "bin" / "oneview.py").read_text()
    foot = src.split("<h3>the partnership</h3>")[1].split("</section>")[0]
    for host in ("planetarycouncil.org", "independenttribunal.org",
                 "demo.basex.com"):
        assert host in foot.lower(), host
