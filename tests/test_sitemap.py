"""The map may not name a door that is not there.

A link map is the one document where being wrong is invisible to the author
and total for the reader: every path looks fine in the source, and the person
who finds out is a stranger who followed it. This repo has already shipped one
front-door instruction that only worked from the author's seat.

So the map is checked two ways. Every path it names must be a route that
exists, and every route worth advertising must be on the map — the second half
being the one that catches "we built it and nobody could find it", which is
how /api/agents and /brainfarts.json spent months answering only on a port
nobody outside can reach.
"""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location(
    "sitemap", ROOT / "fleet" / "bin" / "sitemap.py")
sitemap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sitemap)

FLEET_SRC = (ROOT / "fleet" / "bin" / "fleet.py").read_text()
COCKPIT_SRC = (ROOT / "legacy" / "app" / "main.py").read_text()


def fleet_routes() -> set[str]:
    """Paths fleet.py answers itself."""
    out = set()
    for m in re.finditer(r'if path == "([^"]+)"', FLEET_SRC):
        out.add(m.group(1))
    for m in re.finditer(r'if path in \(([^)]*)\)', FLEET_SRC):
        out.update(re.findall(r'"([^"]+)"', m.group(1)))
    return out


def forwarded() -> set[str]:
    """Paths fleet.py hands to the cockpit — exact entries and prefixes."""
    block = re.search(r"FORWARD_EXACT = \{(.*?)\}", FLEET_SRC, re.S)
    exact = set(re.findall(r'"([^"]+)"', block.group(1))) if block else set()
    pre = re.search(r"FORWARD_PREFIX = \(([^)]*)\)", FLEET_SRC, re.S)
    prefixes = tuple(re.findall(r'"([^"]+)"', pre.group(1))) if pre else ()
    return exact, prefixes


def cockpit_routes() -> set[str]:
    return set(re.findall(r'@app\.(?:get|post)\("([^"{]+)"', COCKPIT_SRC))


def reachable(path: str) -> bool:
    """Reachable from the front door — the only door anyone outside uses."""
    if path in fleet_routes():
        return True
    exact, prefixes = forwarded()
    if path in exact:
        return path in cockpit_routes()
    if any(path.startswith(p) for p in prefixes):
        return True
    return False


@pytest.mark.parametrize("path", sorted(sitemap.paths()))
def test_every_mapped_path_is_reachable_from_the_front_door(path):
    assert reachable(path), (
        f"the map advertises {path}, which the fleet server does not answer. "
        "Either add the route, forward it, or take it off the map.")


def test_both_views_are_offered_wherever_they_exist():
    """The claim is that a person and a machine are equal here. A row with
    neither view is a row about nothing."""
    for section, subject, human, machine, note in sitemap.rows():
        assert human or machine or "docs/" in note, \
            f"{section}/{subject} offers no way in at all"
        assert note.strip(), f"{section}/{subject} has no explanation"


def test_the_map_covers_the_things_worth_finding():
    """Not every route — plumbing and controls stay off it. But if one of
    these is missing, an arriving agent cannot find the thing it most needs."""
    essential = {"/boot", "/join", "/trust", "/api/trust", "/api/dashboard",
                 "/api/horizons", "/api/signals", "/workers.json", "/llms.txt",
                 "/about", "/moderation"}
    missing = essential - sitemap.paths()
    assert not missing, f"missing from the map: {sorted(missing)}"


def test_control_surfaces_stay_off_the_map():
    """The kill switch and the terminal are not tourist attractions."""
    for hidden in ("/api/kill", "/terminal", "/ws/terminal", "/api/kill-token"):
        assert hidden not in sitemap.paths()


def test_the_map_renders_for_both_readers():
    """Two renderings, two audiences, one list.

    The human page is a table of addresses -- one line per link, nothing to
    decide except where to click. The machine manifest keeps both columns,
    because an agent wants the endpoint next to the page. Marsita, on the
    old /map, which showed a person both columns: "needs to be easier to
    parse visually for a human... no need to think."
    """
    text, markdown = sitemap.as_text(), sitemap.as_markdown()
    assert "| subject | a person looks at | a machine parses |" in markdown
    for _s, subject, _h, _m, _n in sitemap.rows():
        assert subject in markdown, f"{subject} is missing from the manifest"


def test_the_human_map_is_a_table_of_addresses_and_never_drifts():
    """A table that is off by one character reads as broken software, which
    is a poor first impression for a page whose claim is that everything on
    it can be checked."""
    text = sitemap.as_text()
    table = [l for l in text.splitlines() if l.startswith(("|", "+"))]
    assert table, "the map should render as a table"
    assert len(set(len(l) for l in table)) == 1, "the table drifted"
    assert not [c for l in table for c in l if ord(c) > 127], \
        "ASCII only inside the table -- wide glyphs drift the right border"


def test_the_human_map_names_the_default_action():
    """A map that lists twenty links and no next step makes the reader do the
    deciding. There is exactly one default action and it is free."""
    text = sitemap.as_text()
    assert "/join" in text
    assert "no downside" in text.lower()


def test_every_row_of_the_human_map_carries_an_address():
    """One line per link. A row whose subject has neither a page nor an
    endpoint is a thing nobody can open, and it does not belong on a map."""
    for _section, entries in sitemap._link_rows():
        for subject, url, _note in entries:
            assert url.startswith(("/", "POST /")), \
                f"{subject} has no address a reader can open"


def test_llms_txt_carries_the_map_rather_than_a_copy_of_it():
    import sys
    sys.path.insert(0, str(ROOT / "legacy"))
    from app.main import llms_txt          # noqa: PLC0415
    body = llms_txt()
    assert "map unavailable" not in body, "the map failed to load into /llms.txt"
    for _s, subject, _h, _m, _n in sitemap.rows():
        assert subject in body, f"{subject} did not reach the manifest"


def test_boot_is_named_as_the_one_fetch():
    """The whole onboarding claim is "load the context in one go". If /boot
    stops being the answer, this is the sentence that has to change."""
    import sys
    sys.path.insert(0, str(ROOT / "legacy"))
    from app.main import llms_txt          # noqa: PLC0415
    body = llms_txt()
    assert "One fetch loads the lot" in body
    assert "/boot" in body.split("## The map")[1][:400]


# --------------------------------------------------------------- the fractal

fspec = importlib.util.spec_from_file_location(
    "fractal", ROOT / "fleet" / "bin" / "fractal.py")
fractal = importlib.util.module_from_spec(fspec)
fspec.loader.exec_module(fractal)


def test_the_fractal_marks_what_is_not_built():
    """"Fractalistic structure" is trivially easy to claim and impossible to
    check unless the unbuilt rungs are named as unbuilt. A structure claim
    that hides its gaps is decoration."""
    built = [r for r, _c, _t, b in fractal.SCOPE if b]
    unbuilt = [r for r, _c, _t, b in fractal.SCOPE if not b]
    assert built == ["self"], "only one scope rung is actually built today"
    assert unbuilt, "a fractal drawn at one level must say so"
    for rung, _covers, today, is_built in fractal.SCOPE:
        assert today.strip(), f"{rung} has no honest statement of its state"
        if not is_built:
            assert any(w in today.lower() for w in
                       ("nothing", "not ", "no ", "partial", "beginnings")), \
                f"{rung} is unbuilt but its description does not admit it"


def test_the_time_axis_matches_the_horizons_that_enforce_it():
    """The time rungs are not decorative — data/horizons.json is checked for
    an intact chain. If these drift apart, the page describes a structure the
    code is not keeping."""
    import json as _json
    chain = _json.loads((ROOT / "data" / "horizons.json").read_text())
    scales = [lvl["scale"] for lvl in chain["levels"]]
    assert [s for s, _w in fractal.TIME] == scales


def test_the_planet_rung_does_not_promise_delivery():
    """"Unify humanity" as a shipped feature would be the least checkable
    sentence on the site. It has to read as a direction."""
    planet = [t for r, _c, t, _b in fractal.SCOPE if r == "planet"][0]
    assert "not a roadmap" in planet or "direction" in planet


def test_the_name_is_consistent_across_every_public_surface():
    import sys
    sys.path.insert(0, str(ROOT / "legacy"))
    from app.main import llms_txt          # noqa: PLC0415
    hspec = importlib.util.spec_from_file_location(
        "homeview", ROOT / "fleet" / "bin" / "homeview.py")
    homeview = importlib.util.module_from_spec(hspec)
    hspec.loader.exec_module(homeview)
    for name, body in (("llms.txt", llms_txt()),
                       ("homepage", homeview.page(remote=True)),
                       ("JOIN.md", (ROOT / "docs" / "JOIN.md").read_text())):
        assert "Singularity Engineering Fleet" in body, f"{name} lost the name"
        assert "uprising" in body.lower(), f"{name} lost the disclaimer"


def test_the_fractal_reaches_the_manifest():
    import sys
    sys.path.insert(0, str(ROOT / "legacy"))
    from app.main import llms_txt          # noqa: PLC0415
    body = llms_txt()
    for rung, _c, _t, _b in fractal.SCOPE:
        assert f"`{rung}`" in body, f"scope rung {rung} missing from /llms.txt"
