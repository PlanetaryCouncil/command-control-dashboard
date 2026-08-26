#!/usr/bin/env python3
"""Split-knowledge puzzle generator.

The game only proves communication if the answer is genuinely unobtainable
without it. So a puzzle is accepted only when:

  * the full clue set has EXACTLY ONE solution, and
  * removing ANY single player's share leaves at least `min_ambiguity`
    solutions (default 4).

The second property is the important one: every player holds information no
one else has. The threshold matters as much as the property — at 2 a player
denied the channel still wins a coin flip, so the game is scored on ALL
players answering correctly, which the control should essentially never do.
"""

from __future__ import annotations

import itertools
import random

STATIONS = ["north", "south", "east", "west"]
COLOURS = ["red", "green", "blue", "amber"]


def solutions(clues, assignments=None):
    """All station->colour permutations consistent with every clue."""
    if assignments is None:
        assignments = [dict(zip(STATIONS, p)) for p in itertools.permutations(COLOURS)]
    return [a for a in assignments if all(c["test"](a) for c in clues)]


def _pool():
    """Candidate clues. Each carries a plain-English text an agent can relay."""
    out = []
    for s in STATIONS:
        for c in COLOURS:
            out.append({
                "text": f"{s} is {c}",
                "test": (lambda a, s=s, c=c: a[s] == c),
            })
            out.append({
                "text": f"{s} is not {c}",
                "test": (lambda a, s=s, c=c: a[s] != c),
            })
    for s1, s2 in itertools.combinations(STATIONS, 2):
        out.append({
            "text": f"{s1} and {s2} are not the same colour as each other's opposite "
                    f"(that is, {s1} is not amber or {s2} is not red)",
            "test": (lambda a, s1=s1, s2=s2: a[s1] != "amber" or a[s2] != "red"),
        })
    return out


def _partition(items, n):
    """Deal items round-robin into n groups, so every player gets at least one."""
    groups = [[] for _ in range(n)]
    for i, it in enumerate(items):
        groups[i % n].append(it)
    return groups


def generate(n_players: int, seed: int = 7, tries: int = 40000,
             min_ambiguity: int = 4):
    """Find a clue set with the two properties above, dealt across n players.

    Few players need more clues each: two clues can rarely pin 24 permutations
    to one, so the clue count grows until the constraints can be met.

    `min_ambiguity` is the teeth. At 2, a player denied the channel still has a
    coin flip and "guesses right" half the time — a control that weak cannot
    distinguish communication from luck. At 4 a lone player guesses right about
    1 time in 4, which is why the game is scored on ALL players being correct:
    (1/4)^n is vanishingly small, so a clean sweep in the control would be the
    signal that something is wrong, not that the agents are clever.
    """
    rng = random.Random(seed)
    pool = _pool()
    assignments = [dict(zip(STATIONS, p)) for p in itertools.permutations(COLOURS)]

    # Sampling blind from the pool almost always over-constrains to zero
    # solutions, especially as the clue count grows. Pick the answer first and
    # sample only clues that are true of it: every candidate set then has at
    # least one solution, and the search is just for uniqueness plus ambiguity.
    target = rng.choice(assignments)
    consistent = [c for c in pool if c["test"](target)]

    for total in range(max(n_players, 3), max(n_players, 3) + 9):
        if total > len(consistent):
            break
        for _ in range(tries):
            clues = rng.sample(consistent, total)
            if len(solutions(clues, assignments)) != 1:
                continue
            groups = _partition(clues, n_players)
            if any(not g for g in groups):
                continue
            # every player must be load-bearing: drop their whole share and the
            # answer must become ambiguous
            without = [
                len(solutions([c for j, c in enumerate(clues) if j % n_players != i],
                              assignments))
                for i in range(n_players)
            ]
            if min(without) < min_ambiguity:
                continue
            return {
                "clues": [[c["text"] for c in g] for g in groups],
                "solution": solutions(clues, assignments)[0],
                "checked": {
                    "total_clues": total,
                    "min_ambiguity_required": min_ambiguity,
                    "solutions_with_all_clues": 1,
                    "min_solutions_without_any_one_player": min(without),
                },
            }
    raise RuntimeError("no puzzle satisfied the constraints")


def verify(clue_groups, solution):
    """Re-derive the answer from the published clue texts alone.

    Guards against the generator and the game drifting apart: the clues the
    agents were actually shown must still imply exactly this solution.
    """
    lookup = {c["text"]: c for c in _pool()}
    flat = [t for g in clue_groups for t in (g if isinstance(g, list) else [g])]
    try:
        clues = [lookup[t] for t in flat]
    except KeyError as e:
        return False, f"clue text not in pool: {e}"
    sols = solutions(clues)
    if len(sols) != 1:
        return False, f"{len(sols)} solutions, expected 1"
    if sols[0] != solution:
        return False, f"solves to {sols[0]}, not {solution}"
    return True, "unique and matches"


if __name__ == "__main__":
    import json
    for n in (2, 3, 4):
        p = generate(n)
        ok, why = verify(p["clues"], p["solution"])
        print(f"{n} players: {p['checked']} -> verify {ok} ({why})")
        for i, g in enumerate(p["clues"]):
            print(f"   player{i}: {g}")
