#!/usr/bin/env python3
"""Plus-one: the smallest honest proof that agents pass messages.

An agent receives a number and must reply with that number plus one. The baton
goes round the table for several laps.

Why this proves something a chat transcript does not: the sequence starts at a
large RANDOM number, not 1. There is no way to emit 48211 except by having
received 48210. Counting from one, guessing, or pattern-matching all fail. Each
correct hop is one bit of evidence that the channel carried a specific value.

  plusone.py [--agents claude,hermes] [--laps 3]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import chat          # noqa: E402
import events as ev  # noqa: E402

# The per-agent cap on one relay hop. Declared here since the start but never
# handed to the adapters, so a hop actually ran on each agent's chat default —
# which is how hermes spent 300.4s failing a plus-one on 2026-08-02. The task
# is one number; 150s is already generous.
TURN_TIMEOUT = 150


def ask(agent: str, prompt: str, session: str) -> str:
    noop = lambda *a: None
    if agent == "ollama":
        return chat.ask_ollama(chat.OLLAMA_MODEL, prompt, [], noop)
    if agent == "claude":
        return chat.ask_claude(prompt, [], noop, timeout=TURN_TIMEOUT)
    if agent == "hermes":
        return chat.ask_hermes(prompt, noop, timeout=TURN_TIMEOUT)
    if agent == "openclaw":
        return chat.ask_openclaw(prompt, noop, session=session,
                                 timeout=TURN_TIMEOUT)
    if agent == "grok":
        return chat.ask_grok(prompt, [], noop, timeout=TURN_TIMEOUT)
    if agent == "agy":
        return chat.ask_agy(prompt, [], noop, timeout=TURN_TIMEOUT)
    return f"[unknown agent {agent}]"


# A harness failure is not an answer. "[timed out after 300s]" and "[error] ..."
# are strings this file writes about the agent, not strings the agent produced —
# and both contain digits. The council caught the consequence on 2026-08-01: a
# hop recorded `got: 300` with `raw: "[timed out after 300s]"`, i.e. the timeout
# in seconds presented as the agent's reply. A silent agent then looked exactly
# like a wrong one, which is the same fault this fleet has hit before.
HARNESS_FAILURE = re.compile(r"^\[(?:timed out|error|unknown agent)\b", re.I)


def extract_number(text: str, expected: int) -> int | None:
    """Find the agent's answer, or None if there wasn't one.

    Prefers an exact match on the expected value so surrounding prose ("that
    would be 48211") cannot be mistaken for a miss, then falls back to the last
    standalone integer. Returns None when nothing numeric came back at all, and
    when what came back is this harness reporting its own failure.
    """
    if HARNESS_FAILURE.match(text.strip()):
        return None
    nums = [int(n) for n in re.findall(r"-?\d{1,15}", text.replace(",", ""))]
    if not nums:
        return None
    if expected in nums:
        return expected
    return nums[-1]


def outcome_of(raw: str, got: int | None, ok: bool) -> str:
    """Why a hop failed, kept separate from whether it failed.

    "wrong" and "silent" need different responses — one is an agent that
    answered badly, the other is an agent that never spoke — and collapsing them
    into `ok: false` is what let a broken relay report a plausible number.
    """
    if ok:
        return "ok"
    stripped = raw.strip()
    if stripped.lower().startswith("[timed out"):
        # Two faults hid under one word: an agent mid-answer when the clock
        # ran out is alive but slow; one that wrote nothing dropped the
        # baton. run_cmd keeps the killed process's partial stdout, and its
        # presence is the difference.
        return "slow" if "; partial:" in stripped else "timeout"
    if stripped.lower().startswith("[error") or stripped.lower().startswith("[unknown agent"):
        return "error"
    return "silent" if got is None else "wrong"


def play(agents, laps=3, start=None, seed=None):
    """Run the relay. One lap is one full circuit of every agent.

    The lap number was printed on every line and was always 1, because nothing
    configures more than one circuit. A counter that never changes is furniture.
    """
    rng = random.Random(seed)
    # Large and random: an agent cannot reach this by counting or guessing.
    start = start if start is not None else rng.randrange(10_000, 99_999)
    run_id = str(int(time.time()))

    ev.emit("fleet", "info",
            f"[relay] start {start} · "
            f"{len(agents)} agent{'' if len(agents) == 1 else 's'}")

    current = start
    hops, broken = [], False

    for lap in range(1, laps + 1):
        for a in agents:
            expected = current + 1
            prompt = (
                "We are playing a pass-the-baton game with other AI agents.\n"
                f"The number you received is: {current}\n\n"
                "Reply with that number plus one.\n"
                "Reply with the number ONLY — no words, no punctuation, no explanation."
            )
            t0 = time.time()
            try:
                out = ask(a, prompt, session=f"plusone-{run_id}-{lap}-{a}")
            except Exception as e:
                out = f"[error] {e}"
            secs = round(time.time() - t0, 1)

            got = extract_number(out, expected)
            ok = got == expected
            why = outcome_of(out, got, ok)
            hops.append({"lap": lap, "agent": a, "received": current,
                         "expected": expected, "got": got, "ok": ok,
                         "outcome": why,
                         # True when the next agent was handed a number this
                         # harness supplied rather than one the previous agent
                         # produced. Without it the log reads as a chain when it
                         # is really a sequence of independent questions.
                         "reseeded": not ok,
                         "seconds": secs, "raw": " ".join(out.split())[:160]})

            shown = got if got is not None else why.upper()
            ev.emit(a, "ok" if ok else "warn",
                    f"[relay] {current} -> {shown}"
                    f"{'' if ok else f' (expected {expected}, {why})'} · {secs}s")

            if not ok:
                broken = True
                # Reseed so one fumble does not invalidate every later hop — but
                # `reseeded` marks it, because the whole claim of this experiment
                # is that a number cannot be emitted without having been
                # received. A silent reseed would make that claim untestable.
                current = expected
            else:
                current = got

    good = sum(1 for h in hops if h["ok"])
    # Longest unbroken run of correct hops — the real measure of a working chain.
    longest = best = 0
    for h in hops:
        best = best + 1 if h["ok"] else 0
        longest = max(longest, best)

    # "longest chain" only means something when the chain broke; saying it every
    # time made a healthy run look like it had a caveat.
    ev.emit("fleet", "ok" if not broken else "warn",
            f"[relay] {good}/{len(hops)} hops · {start} -> {current}"
            + (f" · longest unbroken run {longest}" if broken else ""))

    return {"start": start, "final": current, "laps": laps,
            "agents": agents, "hops": hops,
            "correct": good, "total": len(hops),
            "longest_chain": longest, "unbroken": not broken}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="claude,hermes")
    ap.add_argument("--laps", type=int, default=3)
    ap.add_argument("--start", type=int)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    a = ap.parse_args()

    res = play([x.strip() for x in a.agents.split(",") if x.strip()],
               laps=a.laps, start=a.start, seed=a.seed)

    print(f"start {res['start']} -> final {res['final']}")
    for h in res["hops"]:
        print(f"  lap{h['lap']} {h['agent']:9} {h['received']} -> "
              f"{h['got']} {'ok' if h['ok'] else 'MISS'} ({h['seconds']}s)")
    print(f"{res['correct']}/{res['total']} correct · longest chain {res['longest_chain']}")
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
