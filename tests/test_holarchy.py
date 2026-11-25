"""The holarchy is Marsita's map of how projects lead to one another
(fleet/data/holarchy.yaml). It must never drift from the projects list, and
it must never point at a project that does not exist."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
H = yaml.safe_load((ROOT / "fleet/data/holarchy.yaml").read_text())
NAMES = {p["name"] for p in
         yaml.safe_load((ROOT / "fleet/data/projects.yaml").read_text())["projects"]}


def test_every_project_is_on_the_map_and_nothing_else_is():
    assert {p["name"] for p in H["projects"]} == NAMES


def test_the_hq_is_a_project():
    assert H["hq"] in NAMES


def test_every_link_points_at_a_real_project():
    for p in H["projects"]:
        for other in p["next_to"]:
            assert other in NAMES, f"{p['name']} -> {other}"


def test_marsitas_words_are_kept():
    assert all(p["said"].strip() for p in H["projects"])
