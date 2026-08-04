#!/usr/bin/env python3
"""One agent, one turn, three questions — in rotation.

The council runs several agents against each other and is good at finding faults.
This is the other half: each agent gets the board to itself, in turn, and is
asked what would be *better*. Not what is broken.

Three questions, deliberately in this order:

    1. This machine — the workflow, the setup, the fleet it runs inside.
    2. Marsita the Ultra — the person the machine exists to serve.
    3. The planet — who this serves besides her.

The ladder is the point, and the third rung is not decoration: `data/life.json`
already asks of every project "who does this serve besides me?", so an agent that
only ever optimises the machine is answering a smaller question than the operator
set. Ordering matters too — an agent asked about the planet first produces
sermons, and asked about it last produces the version grounded in what it just
read on the board.

**One agent per firing.** Four cores. A turn costs 20-100s and a core, and four
at once has already put this machine at load 15 with two agents killed on a 300s
timeout. The rota is what makes "everyone contributes" survive the hardware: the
turn moves, the load does not stack.

**Proposes, never applies.** Same rule as everything else here. The turn is
appended to a ledger a human reads.

  rota.py [--agents claude,hermes,openclaw] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FLEET / "bin"))

import chat            # noqa: E402
import council         # noqa: E402  — reuse board_state, one reader of the board
import vendors         # noqa: E402
import events as ev    # noqa: E402

STATE = FLEET / "state" / "rota.json"
LEDGER = FLEET / "rota" / "proposals.jsonl"
MAX_LOAD = float(os.environ.get("MAX_LOAD", "6"))

QUESTIONS = [
    "What would most improve this machine — the workflow, the setup, the fleet "
    "you run inside?",
    "What would most help Marsita the Ultra, the person this exists to serve?",
    "What would this let her do for the planet — who does it serve besides her?",
]


def whose_turn(agents: list[str]) -> tuple[str, dict]:
    """Next agent in rotation, persisted so a restart does not reset the cycle."""
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {"last": None, "turns": 0}
    if state.get("last") in agents:
        nxt = agents[(agents.index(state["last"]) + 1) % len(agents)]
    else:
        nxt = agents[0]
    return nxt, state


def prompt_for(agent: str, board: dict) -> str:
    return "\n".join([
        "You are one agent in a small fleet running on a four-core laptop.",
        "It is your turn. No other agent is running right now.",
        "",
        "Here is the current state of the board you all share:",
        "",
        json.dumps(board, indent=2)[:6000],
        "",
        "Answer these three questions, in order, grounded in what you just read.",
        "Cite actual numbers, workers or events from the board — a proposal that",
        "would read the same without the board is not worth a turn.",
        "",
        *(f"{i}. {q}" for i, q in enumerate(QUESTIONS, 1)),
        "",
        "Rules:",
        "- Check already_proposed first. If an entry from the last 4 hours",
        "  (its ts is on the board) already covers your idea — branch backlog,",
        "  merge debt, a stale worker — say NOTHING TO ADD for that question.",
        "  The human has read it once; a sixth restatement is not a turn.",
        "- Be specific and small. The smallest change that would actually help.",
        "- One concrete proposal per question. Say what you would change, where.",
        "- If a question has no honest answer from this board, say NOTHING TO ADD",
        "  for that one rather than inventing something. Silence is a valid turn.",
        "- You are proposing, not doing. A human reads this and decides.",
        "- Four cores, 8GB. A proposal that needs more machine than exists is not",
        "  a proposal.",
    ])


def ask(agent: str, prompt: str, session: str) -> str:
    noop = lambda *a: None
    if agent == "claude":
        return chat.ask_claude(prompt, [], noop)
    if agent == "hermes":
        return chat.ask_hermes(prompt, noop)
    if agent == "openclaw":
        return chat.ask_openclaw(prompt, noop, session=session)
    if agent == "ollama":
        return chat.ask_ollama(chat.OLLAMA_MODEL, prompt, [], noop)
    return f"[unknown agent {agent}]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="claude,hermes,openclaw")
    ap.add_argument("--dry-run", action="store_true",
                    help="show whose turn it is and the prompt, spawn nothing")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    if not agents:
        print("no agents"); return 1

    agent, state = whose_turn(agents)

    # Same gate as the relay, same reason: a turn taken on a saturated machine
    # times out and gets recorded as the agent having nothing to say.
    load1 = os.getloadavg()[0]
    if load1 > MAX_LOAD and not a.dry_run:
        ev.emit("fleet", "warn",
                f"[rota] {agent}'s turn deferred — load {load1:.1f} over {MAX_LOAD:.0f}")
        print(f"rota: load {load1:.1f} > {MAX_LOAD}; deferring {agent}")
        return 0

    board = council.board_state()
    prompt = prompt_for(agent, board)

    if a.dry_run:
        print(f"next up: {agent}  (turn {state.get('turns', 0) + 1})")
        print("-" * 70)
        print(prompt[:1200])
        return 0

    ev.emit("fleet", "info", f"[rota] {agent}'s turn — three questions")
    t0 = time.time()
    try:
        out = ask(agent, prompt, session=f"rota-{int(t0)}-{agent}")
    except Exception as e:
        out = f"[error] {e}"
    secs = round(time.time() - t0, 1)

    # A harness failure is not a contribution — same distinction the relay had to
    # learn, where a timeout was recorded as the agent's answer.
    failed = out.strip().startswith(("[timed out", "[error", "[unknown agent"))
    nothing = "NOTHING TO ADD" in out.upper() and len(out.strip()) < 400

    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent": agent,
        # Two agents agreeing means far more when they are two companies. This
        # fleet has been cross-vendor for weeks with nothing recording it, so
        # every convergence looked like one model repeating itself.
        "vendor": vendors.vendor(agent), "model": vendors.model(agent),
        "seconds": secs,
        "outcome": "error" if failed else ("nothing" if nothing else "proposed"),
        "load_at_start": round(load1, 2),
        "text": " ".join(out.split()),
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(record) + "\n")

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(
        {"last": agent, "turns": state.get("turns", 0) + 1,
         "last_at": record["ts"]}, indent=2) + "\n")

    if failed:
        ev.emit(agent, "warn", f"[rota] turn failed after {secs}s: {out.strip()[:80]}")
    elif nothing:
        ev.emit(agent, "ok", f"[rota] nothing to add ({secs}s)")
    else:
        ev.emit(agent, "ok", f"[rota] proposed ({secs}s): {record['text'][:150]}")

    print(f"{agent}: {record['outcome']} in {secs}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
