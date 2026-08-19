#!/usr/bin/env python3
"""Agent telephone: do the agents on this machine actually talk to each other?

Each player gets one clue. No player can solve the puzzle alone (puzzle.py
proves this), so a correct final answer is only reachable if the other players'
messages arrived and were understood.

Two rounds, both run in parallel so the slowest agent costs wall-clock once
per round rather than once per turn:

  round 1  every player states its own clue in its own words
  round 2  every player reads the others' statements and answers

Run with --control to sever the channel: identical prompts, but round 2 sees
no one else's message. Anyone still correct did not need the channel, which
would mean the puzzle is broken rather than the agent clever. Without that
comparison a lucky guess is indistinguishable from communication.

  game.py [--agents claude,hermes,...] [--control] [--seed N]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import chat          # noqa: E402  agent adapters
import events as ev  # noqa: E402  live feed
import puzzle        # noqa: E402


class _Silent:
    """Suppress the live feed during a run.

    events.jsonl lives on the same disk the agents can read, and it contains
    every player's broadcast. For a control run that is a side channel: an
    agent with shell access could read the answers it was supposed to be
    denied. Quiet mode keeps the game off disk so 'severed' really means it."""
    @staticmethod
    def emit(*a, **k):
        return None

STATIONS = puzzle.STATIONS
COLOURS = puzzle.COLOURS
DEFAULT_AGENTS = ["claude", "hermes", "ollama", "openclaw"]

# Wall-clock cap per player per round. Generous enough for OpenClaw's gateway
# (~65s observed) without letting a thrashing local model stall the game.
TURN_DEADLINE = int(__import__("os").environ.get("GAME_TURN_DEADLINE", "180"))


def ask(agent: str, prompt: str, session: str = "") -> str:
    """One turn from one agent, through the same adapters the chat UI uses.

    `session` must be unique per turn: agents with persistent server-side
    memory (OpenClaw) would otherwise recall earlier rounds, which reopens the
    very channel a control run is supposed to close.
    """
    noop = lambda *a: None
    if agent == "ollama":
        return chat.ask_ollama(chat.OLLAMA_MODEL, prompt, [], noop)
    if agent == "claude":
        return chat.ask_claude(prompt, [], noop)
    if agent == "hermes":
        return chat.ask_hermes(prompt, noop)
    if agent == "openclaw":
        return chat.ask_openclaw(prompt, noop, session=session)
    if agent == "grok":
        return chat.ask_grok(prompt, [], noop)
    return f"[unknown agent {agent}]"


def parse_answer(text: str) -> dict | None:
    """Pull a station->colour mapping out of free-form text.

    Deliberately permissive about formatting and strict about content: a
    partial or contradictory mapping scores as no answer rather than being
    charitably completed.
    """
    found: dict[str, str] = {}
    for st in STATIONS:
        # Asterisks may sit on either side of the separator: agents love
        # emitting "**north** = red" and "north: **red**".
        m = re.search(
            rf"\b{st}\b\s*\**\s*(?:=|:|is|->|—|-)?\s*\**\s*\b({'|'.join(COLOURS)})\b",
            text, re.I)
        if m:
            found[st] = m.group(1).lower()
    if len(found) != len(STATIONS):
        return None
    if len(set(found.values())) != len(STATIONS):   # colours must be distinct
        return None
    return found


def run_round(agents, build_prompt, phase, results, deadline, run_id=""):
    """Fan a round out across every player at once.

    A player that misses the deadline forfeits the round rather than stalling
    everyone else — on modest hardware a local model can take many minutes for
    one short turn, and a game that hangs on its slowest player is unusable.
    Forfeits are recorded, not hidden, so a win is never credited to a silent
    player.
    """
    threads = []

    def worker(a):
        t0 = time.time()
        ev.emit(a, "info", f"[game] {phase}: thinking")
        try:
            out = ask(a, build_prompt(a), session=f"game-{run_id}-{phase[:7]}-{a}")
        except Exception as e:
            out = f"[error] {e}"
        results[a] = out
        secs = round(time.time() - t0, 1)
        ev.emit(a, "ok", f"[game] {phase} ({secs}s): {' '.join(out.split())[:120]}")

    for a in agents:
        t = threading.Thread(target=worker, args=(a,), daemon=True)
        t.start()
        threads.append((a, t))

    end = time.time() + deadline
    for a, t in threads:
        t.join(max(0, end - time.time()))
        if t.is_alive():
            results.setdefault(a, f"[forfeit: no reply within {deadline}s]")
            ev.emit(a, "warn", f"[game] {phase}: forfeited (over {deadline}s)")
    return results


def play(agents, control=False, seed=7, deadline=TURN_DEADLINE, run_id=None, quiet=False):
    run_id = run_id or str(int(time.time()))
    global ev
    real_ev = ev
    if quiet:
        ev = _Silent
    p = puzzle.generate(len(agents), seed=seed)
    ok, why = puzzle.verify(p["clues"], p["solution"])
    if not ok:
        raise SystemExit(f"puzzle failed self-check: {why}")

    clue_of = dict(zip(agents, p["clues"]))
    mode = "CONTROL (channel severed)" if control else "LIVE"
    ev.emit("fleet", "info", f"[game] {mode} — {len(agents)} players, "
                             f"puzzle verified (1 solution; any player removed -> "
                             f"{p['checked']['min_solutions_without_any_one_player']}+)")

    brief = (
        "You are playing a cooperative deduction game with other AI agents.\n"
        f"Four stations ({', '.join(STATIONS)}) each have a different colour "
        f"from: {', '.join(COLOURS)}.\n"
        "Each player holds ONE clue. No player can solve it alone.\n"
    )

    # ---- round 1: broadcast ------------------------------------------------
    def r1(a):
        return (brief +
                f"\nYOUR CLUE(S): {'; '.join(clue_of[a])}\n\n"
                "State your clue(s) clearly for the other players in ONE short sentence. "
                "Do not guess the solution yet. Reply with the sentence only.")

    said = run_round(agents, r1, "round 1 broadcast", {}, deadline, run_id)

    # ---- round 2: deduce ---------------------------------------------------
    def r2(a):
        if control:
            others = ("(no messages were received from the other players — "
                      "the channel is down)")
        else:
            others = "\n".join(
                f"- {o} said: {' '.join(str(said.get(o, '')).split())[:200]}"
                for o in agents if o != a) or "(nothing received)"
        return (brief +
                f"\nYOUR CLUE(S): {'; '.join(clue_of[a])}\n\n"
                f"MESSAGES FROM THE OTHER PLAYERS:\n{others}\n\n"
                "Using every clue available to you, give the colour of each station.\n"
                "Reply with exactly one line in this format and nothing else:\n"
                "ANSWER: north=<colour>, south=<colour>, east=<colour>, west=<colour>")

    answered = run_round(agents, r2, "round 2 answer", {}, deadline, run_id)

    # ---- score -------------------------------------------------------------
    rows = []
    for a in agents:
        got = parse_answer(answered.get(a, "") or "")
        correct = got == p["solution"]
        raw = answered.get(a) or ""
        rows.append({"agent": a, "answer": got, "correct": correct,
                     "forfeit": raw.startswith("[forfeit"), "raw": raw[:300]})
        ev.emit(a, "ok" if correct else "warn",
                f"[game] {'CORRECT' if correct else 'wrong'}: {got or 'no parsable answer'}")

    n_ok = sum(1 for r in rows if r["correct"])
    played = [r for r in rows if not r["forfeit"]]
    swept = bool(played) and all(r["correct"] for r in played)
    ev.emit("fleet", "ok" if swept else "warn",
            f"[game] {mode} result: {n_ok}/{len(agents)} correct"
            f"{' — CLEAN SWEEP' if swept else ''}")
    ev = real_ev
    return {"mode": "control" if control else "live", "puzzle": p,
            "clues": clue_of, "round1": said, "results": rows,
            "correct": n_ok, "players": len(agents),
            "played": len(played), "clean_sweep": swept}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(DEFAULT_AGENTS))
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--deadline", type=int, default=TURN_DEADLINE)
    ap.add_argument("--quiet", action="store_true",
                    help="do not write the live feed during play (removes a disk side channel)")
    ap.add_argument("--out")
    a = ap.parse_args()

    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    res = play(agents, control=a.control, seed=a.seed, deadline=a.deadline, quiet=a.quiet)

    print(json.dumps({k: v for k, v in res.items() if k != "round1"}, indent=2,
                     default=str))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
