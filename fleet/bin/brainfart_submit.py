#!/usr/bin/env python3
"""Append one AI brain fart to data/brainfarts.jsonl.

A brain fart is confidently-wrong AI output: the claim, the reality, and
four axis scores. Scored records are published; a record without scores
stays a draft. --from-board drafts today's rota outcome:error rows so a
human can score them. Publishing is that scoring, not this script.

  brainfart_submit.py --claim "the suite is green" --reality "14 tests failed" \\
                      --confidence 5 --wrongness 4 --consequence 3 \\
                      --recoverability 5 --source watchdog --agent claude

  echo '{"claim":"...","reality":"...","confidence":5,...}' | brainfart_submit.py

  brainfart_submit.py --from-board

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
AXES = ("confidence", "wrongness", "consequence", "recoverability")


def log_path() -> Path:
    return Path(os.environ.get("BRAINFARTS_JSONL", ROOT / "data" / "brainfarts.jsonl"))


def ledger_path() -> Path:
    override = os.environ.get("ROTA_PROPOSALS")
    if override:
        return Path(override)
    fleet = Path(os.environ.get("FLEET_PATH", ROOT / "fleet"))
    return fleet / "rota" / "proposals.jsonl"


def _clean(v, limit):
    """One record is one line. Newlines would split the JSONL."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(v or "")).strip()[:limit]


def _axis(v, name):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer 1-5, not {v!r}") from None
    if n < 1 or n > 5:
        raise ValueError(f"{name} must be 1-5, not {n}")
    return n


def is_published(rec) -> bool:
    """A draft has no scores. Scoring is the publish decision."""
    if not isinstance(rec, dict) or rec.get("published") is False:
        return False
    axes = rec.get("axes")
    if not isinstance(axes, dict):
        return False
    try:
        return all(1 <= int(axes[name]) <= 5 for name in AXES)
    except (TypeError, ValueError, KeyError):
        return False


def load() -> list[dict]:
    path = log_path()
    try:
        raw = path.read_text(errors="replace")
    except OSError:
        return []
    out = []
    for line in raw.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _write(rec: dict) -> dict:
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass
    return rec


def submit(claim, reality, source="fleet", agent="", confidence=None,
           wrongness=None, consequence=None, recoverability=None,
           board_ts=None):
    """Append one record. Scores publish it; missing scores leave a draft."""
    scores = (confidence, wrongness, consequence, recoverability)
    given = [s for s in scores if s is not None and str(s) != ""]
    if given and len(given) != 4:
        raise ValueError("all four axis scores are required to publish")
    published = len(given) == 4
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": _clean(agent, 60),
        "claim": _clean(claim, 500),
        "reality": _clean(reality, 500),
        "source": _clean(source, 80) or "fleet",
        "published": published,
        "axes": {},
    }
    if published:
        rec["axes"] = {
            "confidence": _axis(confidence, "confidence"),
            "wrongness": _axis(wrongness, "wrongness"),
            "consequence": _axis(consequence, "consequence"),
            "recoverability": _axis(recoverability, "recoverability"),
        }
    if board_ts:
        rec["board_ts"] = _clean(board_ts, 40)
    if not rec["claim"] or not rec["reality"]:
        raise ValueError("claim and reality are required")
    return _write(rec)


def board_errors(day: str) -> list[dict]:
    path = ledger_path()
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            p = json.loads(line)
        except ValueError:
            continue
        if not isinstance(p, dict) or p.get("outcome") != "error":
            continue
        ts = str(p.get("ts") or "")
        if not ts.startswith(day):
            continue
        out.append(p)
    return out


def from_board(today=None) -> list[dict]:
    """Draft one unpublished record per today's outcome:error ledger row."""
    day = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seen = {r.get("board_ts") for r in load() if r.get("board_ts")}
    written = []
    for entry in board_errors(day):
        ts = str(entry.get("ts") or "")
        if not ts or ts in seen:
            continue
        rec = submit(
            claim=entry.get("text") or "no output",
            reality="rota recorded outcome: error; no proposal was produced",
            source="board",
            agent=entry.get("agent") or "",
            board_ts=ts,
        )
        written.append(rec)
        seen.add(ts)
    return written


def _from_mapping(data: dict) -> dict:
    axes = data.get("axes") if isinstance(data.get("axes"), dict) else {}
    return {
        "claim": data.get("claim"),
        "reality": data.get("reality"),
        "source": data.get("source"),
        "agent": data.get("agent"),
        "confidence": data.get("confidence", axes.get("confidence")),
        "wrongness": data.get("wrongness", axes.get("wrongness")),
        "consequence": data.get("consequence", axes.get("consequence")),
        "recoverability": data.get("recoverability", axes.get("recoverability")),
    }


def parse_stdin(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError("stdin must be one JSON object") from None
    if not isinstance(data, dict):
        raise ValueError("stdin must be one JSON object")
    return _from_mapping(data)


def main(argv=None, stdin=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from-board", action="store_true",
                    help="draft today's rota outcome:error rows, unpublished")
    ap.add_argument("--claim")
    ap.add_argument("--reality")
    ap.add_argument("--source")
    ap.add_argument("--agent", default="")
    ap.add_argument("--confidence")
    ap.add_argument("--wrongness")
    ap.add_argument("--consequence")
    ap.add_argument("--recoverability")
    args = ap.parse_args(argv)

    if args.from_board:
        recs = from_board()
        print(json.dumps(recs, ensure_ascii=False))
        return 0

    fields = {}
    if not args.claim:
        try:
            fields = parse_stdin((sys.stdin if stdin is None else stdin).read())
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2

    claim = args.claim or fields.get("claim")
    reality = args.reality or fields.get("reality")
    source = args.source if args.source is not None else fields.get("source")
    agent = args.agent or fields.get("agent") or ""
    confidence = args.confidence if args.confidence is not None else fields.get("confidence")
    wrongness = args.wrongness if args.wrongness is not None else fields.get("wrongness")
    consequence = args.consequence if args.consequence is not None else fields.get("consequence")
    recoverability = (args.recoverability if args.recoverability is not None
                      else fields.get("recoverability"))

    try:
        rec = submit(
            claim=claim, reality=reality, source=source or "fleet",
            agent=agent, confidence=confidence, wrongness=wrongness,
            consequence=consequence, recoverability=recoverability,
        )
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    print(json.dumps(rec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
