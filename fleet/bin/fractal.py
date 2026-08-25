#!/usr/bin/env python3
"""The same shape at every scale, in both directions, with the empty rungs marked.

Marsita, 2026-08-25: *"We are Singularity Engineering Fleet, not AI uprising,
we are here to unify humanity, fractalistic structure."*

The fractal claim is easy to make and easy to fake, so this file states it as a
structure that can be checked rather than a metaphor. Two axes, one shape:

**Time** — already built, and load-bearing. `data/horizons.json` runs ten years
down to right now, eight rungs, each one answering to the one above it. A goal
at a narrow scale with nothing above it is flagged as unanchored; that check
already runs and already fails loudly. That is the fractal working.

**Scope** — the same relation applied to people instead of hours. One life,
then a household, then a community, then the species. Each rung is the same
object: something that needs attention, ranked, with a next action, in the
open, readable by both a person and a machine.

The interesting property is that the two axes use the identical rule — *each
rung serves the one above it, and a rung with nothing above it is unanchored* —
which is why this is a fractal rather than two lists that happen to be near
each other.

Most of the scope axis does not exist. That is stated per rung rather than
glossed, because a fractal you have only drawn one level of is a claim about
the future, and this project's whole pitch is that you can check what it says.

    python3 fleet/bin/fractal.py
    python3 fleet/bin/fractal.py --json
"""

from __future__ import annotations

import json
import sys

RULE = ("Each rung serves the one above it. A rung with nothing above it is "
        "unanchored, and the system says so out loud rather than letting the "
        "work look purposeful.")

# (rung, who it covers, what exists today, built?)
SCOPE = [
    ("self", "one person and their agents",
     "the whole board: radar, horizons, fleet, standing. This is built and "
     "running, and everything below borrows its shape.", True),
    ("household", "the people and machines in one home",
     "partial — several machines already federate by pairing and signed "
     "writes, but they share one operator rather than deciding together.",
     False),
    ("community", "a group who chose each other",
     "the beginnings: a public inbox, vouches, a trust graph. No shared "
     "decisions yet — no way for a group to agree on something and have the "
     "agreement stick.", False),
    ("region", "many communities that must coordinate",
     "nothing. Named so the gap is visible rather than skipped.", False),
    ("planet", "the whole of it",
     "nothing built, and the honest note is that this rung is a direction, "
     "not a roadmap. Unifying humanity is not a feature you ship; the "
     "testable part is whether the smaller rungs actually work.", False),
]

TIME = [
    ("10y", "the widest horizon we will name"),
    ("1y", "what this year is for"),
    ("quarter", "what is being built now"),
    ("month", "what lands this month"),
    ("week", "the current week"),
    ("day", "today's mission"),
    ("hour", "the next verdict"),
    ("now", "what is actually happening"),
]

WHY_NOT_AN_UPRISING = (
    "An uprising replaces whoever was deciding. A fractal does the opposite: "
    "it keeps the same shape at every scale, so the thing that decides at the "
    "top is the same kind of thing that decides at the bottom — small, "
    "readable, answerable to the rung above it. Nothing here is trying to "
    "take a level over. It is trying to make one more level legible."
)


def as_text() -> str:
    lines = ["THE SAME SHAPE AT EVERY SCALE", "", RULE, ""]
    lines.append("TIME — built, and enforced (data/horizons.json)")
    lines.append("-" * 46)
    for scale, what in TIME:
        lines.append(f"  {scale:>8}  {what}")
    lines.append("")
    lines.append("SCOPE — one rung built, the rest named so the gaps show")
    lines.append("-" * 46)
    for rung, who, state, built in SCOPE:
        mark = "BUILT" if built else "not yet"
        lines.append(f"  {rung:>10}  [{mark}]  {who}")
        lines.append(f"              {state}")
    lines.append("")
    lines.append(WHY_NOT_AN_UPRISING)
    return "\n".join(lines) + "\n"


def as_markdown() -> str:
    out = [RULE, "", "**Time** — built and enforced:", ""]
    out.append(" · ".join(f"`{s}`" for s, _w in TIME))
    out.append("")
    out.append("**Scope** — one rung built, the rest named so the gaps show:")
    out.append("")
    out.append("| rung | covers | today |")
    out.append("|---|---|---|")
    for rung, who, state, built in SCOPE:
        mark = "**built**" if built else "*not yet*"
        out.append(f"| `{rung}` {mark} | {who} | {state} |")
    out.append("")
    out.append(WHY_NOT_AN_UPRISING)
    return "\n".join(out)


def as_json() -> dict:
    return {
        "rule": RULE,
        "time": [{"scale": s, "what": w} for s, w in TIME],
        "scope": [{"rung": r, "covers": c, "today": t, "built": b}
                  for r, c, t, b in SCOPE],
        "why_not_an_uprising": WHY_NOT_AN_UPRISING,
        "built_rungs": [r for r, _c, _t, b in SCOPE if b],
    }


if __name__ == "__main__":
    print(json.dumps(as_json(), indent=2) if "--json" in sys.argv else as_text())
