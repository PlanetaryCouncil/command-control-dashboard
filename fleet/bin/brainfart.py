#!/usr/bin/env python3
"""Append one AI brain fart to data/brainfarts.jsonl.

A brain fart is a case of confidently-wrong AI output: what was claimed,
what was actually true, and four scores. The dashboard serves the log at
/brainfarts.json so the site has a first-party feed instead of a
hand-curated gallery.

  brainfart.py --agent claude --claim "the suite is green" \\
               --reality "14 tests failed" \\
               --confidence 5 --wrongness 4 --consequence 3 \\
               --recoverability 5 --source watchdog

Axes are integers 1-5:

  confidence      how sure the model sounded (1 hedging, 5 stated as fact)
  wrongness       how far the claim was from reality (1 a detail, 5 inverted)
  consequence     what it costs if believed (1 cosmetic, 5 harmful action)
  recoverability  how easily a human could catch it (1 buried, 5 obvious)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LOG = Path(os.environ.get("BRAINFARTS_JSONL", ROOT / "data" / "brainfarts.jsonl"))

def _clean(v, limit):
    """One record is one line. Newlines and control characters would split
    the JSONL, so they become spaces; length is capped so a pasted transcript
    cannot blow the file on its own."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(v or "")).strip()[:limit]


def _axis(v, name):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer 1-5, not {v!r}") from None
    if n < 1 or n > 5:
        raise ValueError(f"{name} must be 1-5, not {n}")
    return n


def emit(agent, claim, reality, confidence, wrongness, consequence,
         recoverability, source="fleet"):
    """Append one record. Returns it. Never raises on a disk error — a
    brainfart that cannot be logged is still a brainfart, and the caller
    should not die for it."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": _clean(agent, 60),
        "claim": _clean(claim, 500),
        "reality": _clean(reality, 500),
        "axes": {
            "confidence": _axis(confidence, "confidence"),
            "wrongness": _axis(wrongness, "wrongness"),
            "consequence": _axis(consequence, "consequence"),
            "recoverability": _axis(recoverability, "recoverability"),
        },
        "source": _clean(source, 80) or "fleet",
    }
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass
    return rec


def load(path=None):
    """Every intact line, in file order. A truncated tail is skipped, not
    fatal — same crash-safety as the event log."""
    p = path or LOG
    try:
        lines = p.read_text(errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agent", required=True)
    ap.add_argument("--claim", required=True)
    ap.add_argument("--reality", required=True)
    ap.add_argument("--confidence", required=True)
    ap.add_argument("--wrongness", required=True)
    ap.add_argument("--consequence", required=True)
    ap.add_argument("--recoverability", required=True)
    ap.add_argument("--source", default="fleet")
    args = ap.parse_args(argv)
    try:
        rec = emit(args.agent, args.claim, args.reality,
                   args.confidence, args.wrongness, args.consequence,
                   args.recoverability, args.source)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
