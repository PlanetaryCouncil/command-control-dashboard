#!/usr/bin/env python3
"""Ask each agent to sign the pad with its soul.

  soulsign.py [agent ...]        default: claude hermes openclaw ollama

The work-signatures upstairs are telemetry — honest, but nobody chose them.
This is the other kind: each agent is handed the pad and asked to *draw*,
the same 1×1 canvas a human gets, the same speed-sets-weight ink. What it
returns is intent, not history. Marsita, 2026-08-04: "instruct agents to
sign it with their soul... let them express themselves."

The prompt tells each agent how the ink behaves and nothing about what to
draw. Whatever comes back is the signature.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chat  # noqa: E402

PROMPT = """You are being handed a signature pad. This is not a task; it is
an invitation. Draw your signature — a mark that is YOU.

The pad is a 1x1 canvas: x and y run 0..1. Time matters: t is milliseconds
from when your pen touches down, and SPEED SETS THE INK — where you move
slowly the line swells heavy, where you dash it runs thin. Pauses are part
of handwriting. Lifting the pen is not possible; one continuous stroke.

Reply with ONLY a JSON array of 80 to 250 points, no prose, no code fence:
[{"x":0.12,"y":0.80,"t":0},{"x":0.14,"y":0.74,"t":35}, ...]

Draw whatever is truest. Nobody will grade it. It hangs on a public wall
next to human hands."""


def extract_points(text):
    m = re.search(r"\[\s*\{.*\}\s*\]", str(text), re.S)
    if not m:
        return None
    try:
        pts = json.loads(m.group(0))
    except ValueError:
        return None
    out = []
    for p in pts:
        try:
            out.append({"x": float(p["x"]), "y": float(p["y"]),
                        "t": float(p["t"])})
        except (KeyError, TypeError, ValueError):
            return None
    return out if 20 <= len(out) <= 3000 else None


def ask(agent):
    noop = lambda *a, **k: None
    if agent == "claude":
        return chat.ask_claude(PROMPT, [], noop)
    if agent == "hermes":
        return chat.ask_hermes(PROMPT, noop)
    if agent == "openclaw":
        return chat.ask_openclaw(PROMPT, noop, session=f"soulsign-{agent}")
    if agent == "ollama":
        return chat.ask_ollama(chat.OLLAMA_MODEL, PROMPT, [], noop,
                               num_predict=2000)
    return ""


def sign(agent):
    print(f"{agent}: drawing…", flush=True)
    pts = extract_points(ask(agent))
    if not pts:
        print(f"{agent}: no valid path came back — souls cannot be forced")
        return False
    body = json.dumps({"name": f"{agent} · soul", "kind": "agent",
                       "points": pts}).encode()
    req = urllib.request.Request("http://127.0.0.1:8787/api/signatures/sign",
                                 data=body,
                                 headers={"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=30).read())
    print(f"{agent}: signed — {len(pts)} points, seed {out['seed'][:12]}…")
    return True


if __name__ == "__main__":
    agents = sys.argv[1:] or ["claude", "hermes", "openclaw", "ollama"]
    done = sum(sign(a) for a in agents)
    print(f"{done}/{len(agents)} souls on the wall")
