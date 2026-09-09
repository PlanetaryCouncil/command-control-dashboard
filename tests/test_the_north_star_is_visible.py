"""The fleet's name and its goal, at the top of the page, for the operator.

Marsita, 2026-09-09: "at the very top, Singularity Engineering with the goals,
so I always see it. It always reminds you of the goals, so I'm a little bit
surprised. Please restore it."

Deliberately NOT the welcome row, which she restored on 2026-09-02 and cut the
same evening -- "upon some reflection ---> skip" -- because a row explaining
the fleet, with links to /about and the guestbook, is an advert aimed at a
stranger. Those tests still hold that row shut and they still pass.

This is the opposite of an advert: no links, nothing explained, one sentence
she wrote herself, kept in front of her.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import oneview            # noqa: E402

ARGS = ("[]", "[]", "tok")


def test_it_is_at_the_top_of_the_page_for_everyone():
    """"so I always see it" -- not gated on being a stranger, which is how the
    only reader who needed it became the only one who could not see it."""
    for remote in (True, False):
        assert 'id="northstar"' in oneview.page(*ARGS, remote=remote)


def test_the_name_is_there():
    assert "<b>Singularity Engineering</b>" in oneview.NORTH_STAR


def test_it_is_not_the_advert_row_she_already_cut():
    """A reminder with a call to action on it is a poster, not a reminder."""
    assert "<a " not in oneview.NORTH_STAR
    assert "/about" not in oneview.NORTH_STAR
    assert "sign" not in oneview.NORTH_STAR.lower()


def test_the_goal_comes_from_the_chain_not_from_the_chrome():
    """A mission copied into the banner goes stale the day the chain is
    edited, and a stale north star is worse than none."""
    src = (BIN / "oneview.py").read_text()
    assert 'id="nsgoal"' in src
    assert 'levels.find(l => l.scale === "1y")' in src
    assert "supercomputer" not in src, "the goal text is hard-coded"


def test_the_decade_is_the_hover_behind_the_year():
    src = (BIN / "oneview.py").read_text()
    body = src[src.index('const star = $("#nsgoal");'):][:700]
    assert 'l.scale === "10y"' in body
    assert "star.title = decade" in body


def test_a_broken_chain_leaves_it_blank_not_broken():
    src = (BIN / "oneview.py").read_text()
    body = src[src.index('const star = $("#nsgoal");'):][:700]
    assert "if (star){" in body
    assert "if (y){" in body
