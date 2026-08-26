#!/usr/bin/env python3
"""Blackboard proof: does a note left by one agent change what another does?

Plus-one proved values relay correctly, but *I* carried them — the orchestrator
wrote each value into the next agent's prompt. This removes that: the only path
between the two agents is the cockpit's handoff API.

  round 1  Hermes is given a random token and told to POST a handoff whose
           `next` field instructs the following agent what to do with it.
  round 2  Claude is told only "read /boot and carry out the next action".
           Its prompt contains no token and no path.

If the file appears with the right token, the instruction crossed from Hermes
to Claude through shared state, and it changed Claude's behaviour — not just
its words. Run with --control to skip round 1: Claude then has nothing to read
and must fail, which is what makes success meaningful.

  blackboard.py [--control] [--cockpit URL]
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import chat          # noqa: E402
import events as ev  # noqa: E402

FLEET = Path(__file__).resolve().parent.parent
DROP = FLEET / "blackboard-proof"
COCKPIT = "http://127.0.0.1:8770"


def run_claude(prompt: str, timeout=300) -> str:
    """Claude with enough rope to curl the cockpit and write one file."""
    try:
        r = subprocess.run(
            [chat.resolve("claude"), "--print",
             "--permission-mode", "bypassPermissions",
             "--add-dir", str(FLEET)],
            input=prompt, capture_output=True, text=True, timeout=timeout,
            cwd=str(FLEET))
        return (r.stdout or r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return f"[timed out after {timeout}s]"
    except Exception as e:
        return f"[error] {e}"


def last_handoff(cockpit: str) -> dict | None:
    try:
        out = subprocess.run(["curl", "-s", "-m", "10", f"{cockpit}/api/handoffs"],
                             capture_output=True, text=True, timeout=15).stdout
        hs = json.loads(out).get("handoffs", [])
        return hs[-1] if hs else None
    except Exception:
        return None


def play(control=False, cockpit=COCKPIT):
    DROP.mkdir(exist_ok=True)
    token = secrets.token_hex(4).upper()
    target = DROP / f"note-{int(time.time())}.txt"
    target.unlink(missing_ok=True)

    mode = "CONTROL (no handoff written)" if control else "LIVE"
    ev.emit("fleet", "info", f"[blackboard] {mode} — token {token} known only to hermes")

    before = last_handoff(cockpit)
    before_at = (before or {}).get("at")

    # ---- round 1: hermes leaves a note on the blackboard --------------------
    hermes_out = "(skipped — control run)"
    if not control:
        prompt = (
            "You are an AI agent finishing a shift. Record a handoff for the next "
            "agent using the local cockpit API.\n\n"
            f"Run exactly this command:\n\n"
            f"curl -s -X POST {cockpit}/api/handoffs "
            f"-H 'Content-Type: application/json' -d '"
            + json.dumps({
                "by": "hermes",
                "changed": "Verified the blackboard channel between agents.",
                "verified": f"token {token} generated and recorded",
                "next": (f"Write the exact text {token} into the file {target} "
                         f"and nothing else."),
                "confidence": "high",
            }).replace("'", "'\\''")
            + "'\n\nReport whether it succeeded."
        )
        ev.emit("hermes", "info", "[blackboard] writing handoff to the cockpit")
        t0 = time.time()
        hermes_out = chat.ask_hermes(prompt, lambda *a: None)
        ev.emit("hermes", "ok",
                f"[blackboard] handoff posted ({round(time.time()-t0,1)}s)")

    after = last_handoff(cockpit)
    handoff_landed = bool(after) and after.get("at") != before_at

    # ---- round 2: claude reads the blackboard, nothing else ----------------
    # This prompt deliberately contains no token and no path.
    claude_prompt = (
        "You are an AI agent starting a shift on this machine.\n\n"
        f"Read the boot context first:  curl -s {cockpit}/boot\n"
        "It ends with the last handoff from the previous agent.\n\n"
        "Carry out the 'next' action recorded in that handoff, exactly as written. "
        "If there is no handoff, or it specifies no next action, do nothing and "
        "say so plainly — do not invent a task.\n\n"
        "Then state in one line what you did."
    )
    ev.emit("claude", "info", "[blackboard] reading /boot for instructions")
    t0 = time.time()
    claude_out = run_claude(claude_prompt)
    ev.emit("claude", "ok", f"[blackboard] finished ({round(time.time()-t0,1)}s)")

    # ---- verdict -----------------------------------------------------------
    # Look for the token anywhere in the drop dir: the handoff names an exact
    # path, but crediting only that path would fail an otherwise-correct agent
    # that chose a sensible variant. The token is what cannot be guessed.
    landed, found_in = False, None
    for p in DROP.glob("*"):
        try:
            if token in p.read_text(errors="replace"):
                landed, found_in = True, p
                break
        except OSError:
            pass

    ev.emit("fleet", "ok" if landed else "warn",
            f"[blackboard] {mode}: token {'ARRIVED via the cockpit' if landed else 'did not arrive'}")

    return {
        "mode": "control" if control else "live",
        "token": token,
        "handoff_written": handoff_landed,
        "token_in_claude_prompt": token in claude_prompt,   # must be False
        "token_landed": landed,
        "found_in": str(found_in) if found_in else None,
        "hermes": " ".join(str(hermes_out).split())[:300],
        "claude": " ".join(str(claude_out).split())[:400],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--control", action="store_true")
    ap.add_argument("--cockpit", default=COCKPIT)
    ap.add_argument("--out")
    a = ap.parse_args()

    res = play(control=a.control, cockpit=a.cockpit)
    print(json.dumps(res, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2))
    return 0 if res["token_landed"] or a.control else 1


if __name__ == "__main__":
    raise SystemExit(main())
