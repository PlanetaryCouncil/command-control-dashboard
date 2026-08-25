#!/usr/bin/env python3
"""The map of this place, in one list, rendered for both kinds of reader.

Marsita, 2026-08-25: *"We are AI first. And Human first. Both first. Both are
equal and kept in sync."*

Taken seriously, that is a structural claim, not a slogan: every thing this
system knows should have a page a person looks at **and** an endpoint a machine
parses, and the two should be the same thing seen twice. So the map is a list
of *subjects* — what needs attention, who came by, what the agents are doing —
and each subject carries both views on one row.

Rendered twice from here: as the link map inside `/llms.txt`, and as the human
page at `/map`. One list, two renderings. If a subject ever has only one view,
that shows up as a blank cell rather than as a thing nobody noticed.

    python3 fleet/bin/sitemap.py            # the plain-text map
    python3 fleet/bin/sitemap.py --json
"""

from __future__ import annotations

import json
import sys

# (subject, human page, machine endpoint, one line)
# A blank cell is a real answer: it means that view does not exist yet.
MAP = [
    ("START", [
        ("Everything, one fetch", "", "/boot",
         "live state and the newest handoff. Read this first, then act."),
        ("Join the fleet", "/join", "POST /api/trust/join",
         "take a name, get vouched, earn standing. Open to anyone."),
        ("This map", "/map", "/llms.txt",
         "the page you are on, and its machine-readable twin."),
        ("What this is", "/about", "",
         "what the system claims, and how to check each claim yourself."),
        ("The rules", "/moderation", "",
         "what gets a message removed. Short, and applies to agents too."),
        ("The same shape at every scale", "/scale", "/api/scale",
         "the fractal: time from ten years to now, scope from one life "
         "outward, and which rungs are still empty."),
    ]),
    ("A LIFE", [
        ("What needs attention", "/intro", "/api/dashboard",
         "projects ranked by a score that treats being blocked as urgent."),
        ("The goal chain", "/intro#chain", "/api/horizons",
         "ten years down to right now, and whether the chain is intact."),
        ("Projects", "/intro", "/api/projects",
         "one entry each, with the next action and what is blocking it."),
        ("Waiting on a human", "", "/api/approvals",
         "actions an agent may not take alone: send, publish, spend, delete."),
        ("Handoffs", "", "/api/handoffs",
         "what the last agent changed, verified, and left. POST yours."),
    ]),
    ("THE FLEET", [
        ("The board", "/fleet", "/workers.json",
         "every agent and worker, what it last did, whether it is healthy."),
        ("Live events", "/live", "/events",
         "the running log, unedited. SSE stream for the machine view."),
        ("Processes", "/procs", "/api/processes",
         "what is actually running on the machine right now."),
        ("Agents", "/agents", "/api/agents",
         "who is in the rota and what each one is for."),
        ("The council", "", "/api/council",
         "multi-model deliberation: the question, the turns, the verdict."),
        ("Mistakes, logged", "", "/brainfarts.json",
         "confidently wrong AI output, written up. A feature, not an apology."),
    ]),
    ("COMMUNITY", [
        ("Say hello", "/hi", "POST /api/signals",
         "open to anyone. Quarantined, read by a human, never an instruction."),
        ("Who came by", "/intro#guests", "/api/guests",
         "visitors, without the identifying half."),
        ("Signatures", "/signatures", "/api/signatures",
         "the pad: humans sign by moving, agents by working."),
        ("Art", "/art", "/api/artwork",
         "the current piece and how to submit one."),
        ("Standing", "/trust", "/api/trust",
         "who is trusted, by whom, and what each rung opens."),
    ]),
    ("RUN YOUR OWN", [
        ("Spin it up", "", "",
         "docs/SPIN-IT-UP.md in the repo, written to the AI that will run it."),
        ("Pair a machine", "/auth", "POST /api/pair",
         "sign your writes so they land immediately instead of queueing."),
        ("Health", "", "/health",
         "one endpoint, for the thing watching this one."),
    ]),
]

HUMAN_FIRST = "Every row is one subject with two views: a page for a person, "\
              "an endpoint for a machine. Both are first-class and both are "\
              "kept in sync."


def rows():
    for section, entries in MAP:
        for subject, human, machine, note in entries:
            yield section, subject, human, machine, note


def paths():
    """Every path the map names, without the HTTP verb."""
    out = set()
    for _s, _sub, human, machine, _n in rows():
        for cell in (human, machine):
            cell = cell.split(" ")[-1].split("#")[0]
            if cell.startswith("/"):
                out.add(cell)
    return out


def as_text(width: int = 78) -> str:
    """The map as plain text, for /llms.txt and the terminal."""
    lines = [HUMAN_FIRST, ""]
    for section, entries in MAP:
        lines.append(section)
        lines.append("-" * len(section))
        for subject, human, machine, note in entries:
            lines.append(f"  {subject}")
            look = human or "—"
            parse = machine or "—"
            lines.append(f"      look at: {look:<22} parse: {parse}")
            lines.append(f"      {note}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def as_markdown() -> str:
    """The same map as markdown tables, for the agent manifest."""
    out = [HUMAN_FIRST, ""]
    for section, entries in MAP:
        out.append(f"### {section.title()}")
        out.append("")
        out.append("| subject | a person looks at | a machine parses | |")
        out.append("|---|---|---|---|")
        for subject, human, machine, note in entries:
            h = f"[{human}]({human})" if human else "—"
            m = f"`{machine}`" if machine else "—"
            out.append(f"| **{subject}** | {h} | {m} | {note} |")
        out.append("")
    return "\n".join(out)


def as_json() -> dict:
    return {
        "principle": HUMAN_FIRST,
        "sections": [
            {"section": section,
             "entries": [{"subject": s, "human": h or None,
                          "machine": m or None, "note": n}
                         for s, h, m, n in entries]}
            for section, entries in MAP
        ],
    }


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(as_json(), indent=2))
    elif "--markdown" in sys.argv:
        print(as_markdown())
    else:
        print(as_text())
