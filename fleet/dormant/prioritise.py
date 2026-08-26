#!/usr/bin/env python3
"""Ask the council to score a shortlist, one agent at a time.

  prioritise.py [--agents claude,hermes,openclaw]

Four criteria, each 1-10, per item, per agent:

  simplicity        how simple is this to understand and do
  complexity        how many moving parts does it actually have
  practical         how much real use does it deliver
  importance        why this matters — and how much

Simplicity and complexity are asked SEPARATELY on purpose. Marsita,
2026-08-05: "are they synonymous? run questions on both, will see if
values diverge over time." The hypothesis is that they are not: a
one-line fix inside a tangled system is simple to grasp and complex to
land, and a rewrite can be conceptually simple and enormous. If the two
scores turn out to be perfect mirrors across many runs, one of the
questions is wasted and should go. That is an empirical question, and
this file is how it gets answered — every run appends to
rota/priorities.jsonl, so the correlation can be measured later.

Each agent scores alone, without seeing the others. Averaging independent
judgements is worth something; averaging agents who read each other's
numbers is worth much less.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FLEET / "bin"))

import chat          # noqa: E402
import events as ev  # noqa: E402

SHORTLIST = FLEET / "rota" / "triage.md"
LEDGER = FLEET / "rota" / "priorities.jsonl"

PROMPT = """You are scoring a shortlist of improvements to the machine you
run on. Score every item on four criteria, each 1 to 10.

  simplicity   how simple is it to understand and to do (10 = trivial)
  complexity   how many moving parts does it really have (10 = many)
  practical    how much real, daily use does it deliver (10 = enormous)
  importance   how much does it matter that this exists (10 = critical)

simplicity and complexity are asked separately deliberately. They are not
assumed to be opposites — a one-line change inside a tangled system can be
simple to grasp and complex to land. Score each on its own terms.

Reply with ONE line per item, nothing else, no preamble:

  <item number> | simplicity | complexity | practical | importance | six words on why

THE SHORTLIST
{items}"""


def items():
    try:
        text = SHORTLIST.read_text()
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        m = re.match(r"^(\d+)\s*\|\s*(.+?)\s*\|", line.strip())
        if m:
            out.append((int(m.group(1)), m.group(2)))
    return out


def ask(agent, prompt):
    noop = lambda *a, **k: None
    if agent == "claude":
        return chat.ask_claude(prompt, [], noop)
    if agent == "hermes":
        return chat.ask_hermes(prompt, noop)
    if agent == "openclaw":
        return chat.ask_openclaw(prompt, noop, session="prioritise")
    if agent == "grok":
        return chat.ask_grok(prompt, [], noop)
    if agent == "ollama":
        return chat.ask_ollama(chat.OLLAMA_MODEL, prompt, [], noop,
                               num_predict=600)
    return ""


def parse(text):
    """{item: {criterion: score}} from whatever shape came back."""
    rows = {}
    for line in str(text).splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) < 5 or not p[0].lstrip("#").strip().isdigit():
            continue
        try:
            n = int(p[0].lstrip("#").strip())
            rows[n] = {"simplicity": int(float(p[1])),
                       "complexity": int(float(p[2])),
                       "practical": int(float(p[3])),
                       "importance": int(float(p[4])),
                       "why": (p[5] if len(p) > 5 else "")[:80]}
        except ValueError:
            continue
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="claude,hermes,openclaw")
    a = ap.parse_args()
    shortlist = items()
    if not shortlist:
        print(f"no shortlist at {SHORTLIST} — run pipeline.py triage first")
        return 1

    listing = "\n".join(f"{n} | {t}" for n, t in shortlist)
    prompt = PROMPT.format(items=listing)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    scores = {}

    for agent in [x.strip() for x in a.agents.split(",") if x.strip()]:
        print(f"{agent} scoring…", flush=True)
        got = parse(ask(agent, prompt))
        if not got:
            print(f"  {agent}: no usable scores")
            continue
        scores[agent] = got
        with LEDGER.open("a") as fh:
            fh.write(json.dumps({"ts": stamp, "agent": agent,
                                 "scores": got}) + "\n")
        print(f"  {agent}: scored {len(got)} items")

    if not scores:
        return 1

    # The panel's view: mean per criterion, and the spread between agents,
    # because agreement and disagreement are different information.
    print(f"\n{'#':>2}  {'simp':>5}{'cplx':>5}{'prac':>5}{'impt':>5}"
          f"{'rank':>7}  item")
    ranked = []
    for n, title in shortlist:
        vals = [s[n] for s in scores.values() if n in s]
        if not vals:
            continue
        m = {c: sum(v[c] for v in vals) / len(vals)
             for c in ("simplicity", "complexity", "practical", "importance")}
        # Rank by what it delivers and matters, lifted by being simple.
        score = m["practical"] + m["importance"] + m["simplicity"] / 2
        ranked.append((score, n, title, m))
    for score, n, title, m in sorted(ranked, reverse=True):
        print(f"{n:>2}  {m['simplicity']:>5.1f}{m['complexity']:>5.1f}"
              f"{m['practical']:>5.1f}{m['importance']:>5.1f}{score:>7.1f}"
              f"  {title[:52]}")

    # The question Marsita asked: do simplicity and complexity say the
    # same thing? Correlation over every score collected so far.
    pairs = []
    try:
        for line in LEDGER.read_text().splitlines():
            for v in json.loads(line)["scores"].values():
                pairs.append((v["simplicity"], v["complexity"]))
    except (OSError, ValueError, KeyError):
        pass
    if len(pairs) > 3:
        n = len(pairs)
        sx = sum(p[0] for p in pairs); sy = sum(p[1] for p in pairs)
        sxx = sum(p[0] ** 2 for p in pairs); syy = sum(p[1] ** 2 for p in pairs)
        sxy = sum(p[0] * p[1] for p in pairs)
        den = ((n * sxx - sx ** 2) * (n * syy - sy ** 2)) ** 0.5
        r = (n * sxy - sx * sy) / den if den else 0
        print(f"\nsimplicity vs complexity: r = {r:+.2f} over {n} scores")
        print("  -1.0 would mean the two questions are one question."
              if r < -0.85 else
              "  they are measuring different things — keep both.")

    ev.emit("pipeline", "needs_you",
            f"[priorities] council scored {len(ranked)} items - "
            f"rota/priorities.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
