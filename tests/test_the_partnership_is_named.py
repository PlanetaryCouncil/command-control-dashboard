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
