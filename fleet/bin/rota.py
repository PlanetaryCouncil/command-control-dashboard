#!/usr/bin/env python3
"""One agent, one turn, three questions — in rotation.

The council runs several agents against each other and is good at finding faults.
This is the other half: each agent gets the board to itself, in turn, and is
asked what would be *better*. Not what is broken.

Three questions, deliberately in this order:

    1. One project, and the single most valuable action for it right now.
    2. What that project could do for the people it serves.
    3. The machine — and ONLY if it is blocking question 1.

The order was the other way round until 2026-08-07, and it showed: asked
first what would improve the machine, a fleet answers about the fleet. It
filed 72 proposals in one day and almost none of them touched a project.
Marsita: "My projects are fundamental, everything else is coordination and
tooling and infrastructure." So the machine went last, and now has to name
the project it unblocks to earn the slot at all.

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

  rota.py [--agents claude,hermes,openclaw] [--dry-run] [--retry-deferred]
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

# Reordered 2026-08-07. Marsita: "My projects are fundamental, everything else
# is coordination and tooling and infrastructure." The old first question asked
# what would improve the machine, and a fleet asked about itself answers about
# itself — 72 proposals filed in one day, almost every one about the fleet.
# The machine is now the third question and it has to earn its place by naming
# the project it unblocks.
QUESTIONS = [
    "Pick ONE project from the list and name the single most valuable thing "
    "that could be done for it right now. Not a plan — one action.",
    "What is the most valuable thing that project could do for the people it "
    "serves, that it is not doing yet?",
    "Only if some part of this machine is BLOCKING that action: what is the "
    "smallest fix? Name the project it unblocks, or answer NOTHING TO ADD.",
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


def projects_text() -> str:
    """The operator's own project list, verbatim.

    Without this the rota only ever saw the board — and the board is the
    fleet describing itself, so that is what came back. The projects are the
    point; the fleet is how they get built.
    """
    try:
        return (FLEET / "data" / "projects.yaml").read_text()[:4000]
    except OSError:
        return "(projects.yaml unavailable — say NOTHING TO ADD rather than guessing)"


def prompt_for(agent: str, board: dict) -> str:
    return "\n".join([
        "You are one agent in a small fleet. It is your turn; no other agent",
        "is running right now.",
        "",
        "THE PROJECTS ARE THE POINT. Marsita, 2026-08-07: \"My projects are",
        "fundamental, everything else is coordination and tooling and",
        "infrastructure.\" The fleet exists to move these forward. A turn spent",
        "on the fleet itself is a turn not spent on them.",
        "",
        "Here is the project list:",
        "",
        projects_text(),
        "",
        "And the current state of the board the fleet shares:",
        "",
        json.dumps(board, indent=2)[:4000],
        "",
        "Answer these three questions, in order.",
        "",
        *(f"{i}. {q}" for i, q in enumerate(QUESTIONS, 1)),
        "",
        "Rules:",
        "- Name the project. A proposal that does not name one is not a turn.",
        "- One action, small enough to finish today. 'Write the About page for",
        "  X' beats 'improve X's positioning'.",
        "- Prefer a project that is live but thin, or marked TODO, over one",
        "  already doing well. Look for the gap.",
        "- Check already_proposed first. If an entry from the last 4 hours",
        "  already covers your idea, say NOTHING TO ADD for that question.",
        "  The human has read it once; a sixth restatement is not a turn.",
        "- Do not restate these questions back. Answer them. A turn that",
        "  opens 'Here are my answers to the three questions' is filed",
        "  unusable and wastes the slot.",
        "- If a question has no honest answer, say NOTHING TO ADD for that one",
        "  rather than inventing something. Silence is a valid turn.",
        "- The fleet builds what you propose. Write it as something a builder",
        "  could implement, not as advice for a human to consider.",
    ])


NARRATION = (
    "the message seems to be",
    "the text you provided appears to be",
    "the text appears to be",
    "here is the reformatted text",
    "here's the reformatted text",
    "what appears to be a discord",
    "the format you requested is",
    "this appears to be a log",
    "it appears to be a log",
    "i'll answer the three questions based on the provided text",
    "based on the provided text, i'll answer",
)


def narrated(out: str) -> bool:
    """True when the turn describes the prompt instead of answering it.

    On 2026-08-07 three of the six entries on the board were the model
    reading the prompt back — "the message seems to be an invitation for
    discussion", "here is the reformatted text from what appears to be a
    Discord proposal". They exit clean, so nothing catches them the way the
    errored-turn check catches `[error]`, and each one takes a board slot a
    human and the next agent have to read past. Filed `unusable`, they stay
    in the ledger as evidence and stay off the board.

    Deliberately narrow: only the opening of the turn is examined, because a
    real proposal may well *quote* the board further down.
    """
    head = " ".join(out.split())[:300].lower()
    return any(p in head for p in NARRATION)


def harness_failed(out: str) -> bool:
    """CLI wrappers and quota dumps are not proposals."""
    s = str(out).strip()
    if s.startswith(("[timed out", "[error", "[unknown agent", "[stderr]")):
        return True
    low = s.lower()
    return "quota reached" in low or "out of credits" in low


def ask(agent: str, prompt: str, session: str) -> str:
    noop = lambda *a: None
    if agent == "claude":
        return chat.ask_claude(prompt, [], noop)
    if agent == "hermes":
        return chat.ask_hermes(prompt, noop)
    if agent == "openclaw":
        return chat.ask_openclaw(prompt, noop, session=session)
    if agent == "grok":
        return chat.ask_grok(prompt, [], noop)
    if agent == "agy":
        return chat.ask_agy(prompt, [], noop)
    if agent == "ollama":
        return chat.ask_ollama(chat.OLLAMA_MODEL, prompt, [], noop)
    return f"[unknown agent {agent}]"


def turn_hash(board: dict) -> str:
    """Hash of the board fields that would change what this turn says.

    Six proposals landed in 63 minutes on 2026-08-07 (13:00–14:03) while
    `pipeline` sat in `alert` with the same merge queue, the dashboard the
    same "341 passed", visitors the same 24h line. Three of the six restated
    the same two points. The rota kept firing and every agent spent a turn
    on a picture that had not moved.

    Worker identity/status/summary/alert_since, unmerged branches, and an
    operator question. Not `last_run` or the event tail — those tick without
    the situation changing. Not `already_proposed` either: this hash is
    stored ON that list, so counting it would make every filing look like
    the board moved.
    """
    return council.board_fingerprint({**board, "already_proposed": []})


def last_board_hash() -> str | None:
    """Fingerprint stored with the most recent already_proposed ledger row.

    Unusable turns stay off this check the same way they stay off the board:
    they are not something anyone proposed, so they must not pin the skip.
    An error row has no hash, so a failed turn does not lock the next one out.
    """
    if not LEDGER.exists():
        return None
    last = None
    for line in LEDGER.read_text(errors="replace").splitlines():
        try:
            p = json.loads(line)
        except ValueError:
            continue
        if p.get("outcome") == "unusable":
            continue
        last = p
    if not last:
        return None
    return last.get("board_hash") or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="hermes,grok,agy")
    ap.add_argument("--dry-run", action="store_true",
                    help="show whose turn it is and the prompt, spawn nothing")
    ap.add_argument("--retry-deferred", action="store_true",
                    help="take a load-deferred turn if one is pending, else exit")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    import quotas
    agents = quotas.eligible(agents)
    if not agents:
        print("no eligible agents (dry or rare)"); return 1
    import heavygate
    if not heavygate.enabled() and not a.dry_run:
        print("heavy work off on this machine — skipping")
        return 0

    agent, state = whose_turn(agents)

    if a.retry_deferred:
        deferred = state.get("deferred")
        if not deferred:
            print("rota: no deferred turn pending")
            return 0
        agent = deferred["agent"]
        if agent not in agents:
            print(f"rota: deferred {agent} is not eligible; skipping")
            return 0

    # Same gate as the relay, same reason: a turn taken on a saturated machine
    # times out and gets recorded as the agent having nothing to say.
    import pressure
    snap = pressure.snapshot()
    load1 = snap["load1"]
    if snap["hot"] and not a.dry_run:
        # Deferring used to drop the turn — the fleet's next thought waited a
        # full hour. Leave a pending marker instead; the watchdog retries it
        # once the sweep (the usual load source) finishes.
        state["deferred"] = {
            "agent": agent, "load": round(load1, 2),
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2) + "\n")
        ev.emit("fleet", "warn",
                f"[rota] {agent}'s turn deferred — {snap['reason']}; "
                f"retry pending for the next idle window")
        print(f"rota: {snap['reason']}; deferring {agent}, retry pending")
        return 0

    board = council.board_state()
    fingerprint = turn_hash(board)
    # The timer still fires; this just refuses to spend an agent on a board
    # that has not moved since the last already_proposed row.
    if not a.dry_run and fingerprint == last_board_hash():
        ev.emit("fleet", "info", "[rota] board unchanged — skipped")
        print("board unchanged — skipped")
        return 0
    prompt = prompt_for(agent, board)

    if a.dry_run:
        print(f"next up: {agent}  (turn {state.get('turns', 0) + 1})")
        print("-" * 70)
        print(prompt[:1200])
        return 0

    ev.emit("fleet", "info",
            f"[rota] retrying {agent}'s deferred turn — three questions"
            if a.retry_deferred else
            f"[rota] {agent}'s turn — three questions")
    t0 = time.time()
    try:
        out = ask(agent, prompt, session=f"rota-{int(t0)}-{agent}")
    except Exception as e:
        out = f"[error] {e}"
    secs = round(time.time() - t0, 1)

    # A harness failure is not a contribution — same distinction the relay had to
    # learn, where a timeout was recorded as the agent's answer. `[stderr]`
    # is chat.run_cmd wrapping a CLI that printed nothing to stdout
    # (agy quota-reached, 2026-08-21 — filed as proposed until this check).
    failed = harness_failed(out)
    nothing = "NOTHING TO ADD" in out.upper() and len(out.strip()) < 400
    unusable = not failed and not nothing and narrated(out)

    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent": agent,
        # Two agents agreeing means far more when they are two companies. This
        # fleet has been cross-vendor for weeks with nothing recording it, so
        # every convergence looked like one model repeating itself.
        "vendor": vendors.vendor(agent), "model": vendors.model(agent),
        "seconds": secs,
        "outcome": ("error" if failed else "nothing" if nothing
                    else "unusable" if unusable else "proposed"),
        "load_at_start": round(load1, 2),
        "text": " ".join(out.split()),
    }
    # Pin the skip to a turn that actually looked at the board. An error or
    # a narrated prompt must not freeze the next agent out of the slot.
    if not failed and not unusable:
        record["board_hash"] = fingerprint
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(record) + "\n")

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(
        {"last": agent, "turns": state.get("turns", 0) + 1,
         "last_at": record["ts"]}, indent=2) + "\n")

    if failed:
        ev.emit(agent, "warn", f"[rota] turn failed after {secs}s: {out.strip()[:80]}")
    elif unusable:
        ev.emit(agent, "warn",
                f"[rota] unusable turn after {secs}s — narrated the prompt back: "
                f"{record['text'][:80]}")
    elif nothing:
        ev.emit(agent, "ok", f"[rota] nothing to add ({secs}s)")
    else:
        ev.emit(agent, "ok", f"[rota] proposed ({secs}s): {record['text'][:150]}")
        try:
            import poems
            poems.append(out, author=agent, task="rota")
        except Exception:
            pass

    print(f"{agent}: {record['outcome']} in {secs}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
