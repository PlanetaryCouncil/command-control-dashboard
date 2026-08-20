#!/usr/bin/env python3
"""Cheap autopilot for the rota pile.

The pipeline still will not BUILD what nobody picked (2026-08-05: 8
triage items became 20 branches). This file only closes the backlog
that telegram counts: errors, empties, duplicates, and a cheap model's
DROP. KEEP stays a shortlist in rota/triage.md.

Default model is agy (Google). Override with FLEET_TRIAGE=grok|agy.
Never claude — that plan is rare.

  autotriage.py              drain + one cheap batch
  autotriage.py --drain-only no model
  autotriage.py --batches 3  drain + up to 3 model batches
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FLEET / "bin"))

import chat          # noqa: E402
import events as ev  # noqa: E402
import pipeline      # noqa: E402

NOISE = {"error", "nothing", "unusable"}
BATCH = 40
KEEP_MAX = 8
STALE_HOURS = 24
BAR = re.compile(r"[█▉▊▋▌▍▎▏▐▓▒░]{3,}")
LINE = re.compile(
    r"(20\d\d-\d\d-\d\dT\d\d:\d\d)\S*.{0,80}?\b(KEEP|DROP)\b",
    re.I,
)


def too_old(ts: str) -> bool:
    try:
        when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when < datetime.now(timezone.utc) - timedelta(hours=STALE_HOURS)


def gist(text: str, n: int = 100) -> str:
    s = BAR.sub(" ", str(text))
    s = " ".join(s.split())
    return s[:n].lower()


def triage_agent() -> str:
    who = (os.environ.get("FLEET_TRIAGE") or "agy").strip() or "agy"
    if who in ("claude", "openclaw"):
        return "agy"
    return who


def ask_cheap(prompt: str) -> str:
    noop = lambda *a, **k: None
    who = triage_agent()
    if who == "agy":
        return chat.ask_agy(prompt, [], noop, timeout=180)
    if who == "grok":
        return chat.ask_grok(prompt, [], noop, timeout=180)
    if who == "hermes":
        return chat.ask_hermes(prompt, noop, timeout=180)
    if who == "ollama":
        return chat.ask_ollama(chat.OLLAMA_MODEL, prompt, [], noop,
                               num_predict=400, timeout=180)
    return f"[unknown agent {who}]"


def close(prop: dict, reason: str, by: str = "autotriage") -> None:
    pipeline.record(
        proposal_ts=prop["ts"],
        stage="drop",
        ok=True,
        detail=reason[:200],
        agent=by,
        branch="",
    )


def open_proposals() -> list[dict]:
    seen = pipeline.by_proposal()
    return [p for p in pipeline.proposals() if p.get("ts") not in seen]


def drain(todo: list[dict] | None = None) -> dict:
    """Close noise and duplicates. No model."""
    todo = open_proposals() if todo is None else todo
    dropped = {"error": 0, "nothing": 0, "unusable": 0,
               "duplicate": 0, "stale": 0}
    kept: list[dict] = []
    seen_gist: dict[str, str] = {}
    for p in todo:
        out = p.get("outcome") or ""
        if out in NOISE:
            close(p, f"outcome={out}")
            dropped[out] = dropped.get(out, 0) + 1
            continue
        if too_old(p.get("ts") or ""):
            close(p, f"stale>{STALE_HOURS}h")
            dropped["stale"] += 1
            continue
        g = gist(p.get("text") or "")
        if not g or g == "nothing to add":
            close(p, "empty")
            dropped["nothing"] = dropped.get("nothing", 0) + 1
            continue
        if g in seen_gist:
            close(p, f"duplicate of {seen_gist[g][:16]}")
            dropped["duplicate"] += 1
            continue
        seen_gist[g] = p["ts"]
        kept.append(p)
    return {"dropped": dropped, "kept": kept}


def parse_verdicts(blob: str, batch_ts: set[str]) -> dict[str, str]:
    """ts prefix -> KEEP|DROP. Unknown timestamps ignored."""
    out = {}
    for raw in str(blob).splitlines():
        m = LINE.search(raw.strip())
        if not m:
            continue
        prefix, verb = m.group(1), m.group(2).upper()
        hit = next((t for t in batch_ts if t.startswith(prefix)), None)
        if hit:
            out[hit] = verb
    return out


def model_batch(batch: list[dict]) -> dict:
    """One cheap turn over a small batch. Fail closed: unparsed = skip."""
    lines = []
    batch_ts = set()
    for p in batch:
        ts = p["ts"]
        batch_ts.add(ts)
        lines.append(f"{ts[:16]} | {p.get('agent','?')} | {gist(p.get('text'), 160)}")
    prompt = (
        "Triage these fleet-improvement proposals. Most are duplicates or "
        "already-fixed observations. For EACH line reply exactly:\n"
        "  TIMESTAMP | KEEP or DROP | six words why\n"
        f"KEEP at most {KEEP_MAX} in this batch. DROP the rest. "
        "No preamble.\n\n" + "\n".join(lines)
    )
    raw = ask_cheap(prompt)
    verdicts = parse_verdicts(raw, batch_ts)
    keep = [p for p in batch if verdicts.get(p["ts"]) == "KEEP"]
    drop = [p for p in batch if verdicts.get(p["ts"]) == "DROP"]
    if len(keep) > KEEP_MAX:
        extra, keep = keep[KEEP_MAX:], keep[:KEEP_MAX]
        drop.extend(extra)
    who = "triage-" + triage_agent()
    for p in drop:
        close(p, "cheap-model DROP", by=who)
    return {"keep": keep, "drop": len(drop), "raw": raw[:1500],
            "unparsed": len(batch) - len(verdicts)}


def run(batches: int = 1, drain_only: bool = False) -> dict:
    before = len(open_proposals())
    stats = drain()
    leftover = stats["kept"]
    model_kept: list[dict] = []
    model_drop = 0
    unparsed = 0
    if not drain_only and leftover and batches > 0:
        n = 0
        rest = leftover
        while rest and n < batches:
            chunk, rest = rest[:BATCH], rest[BATCH:]
            rec = model_batch(chunk)
            model_kept.extend(rec["keep"])
            model_drop += rec["drop"]
            unparsed += rec["unparsed"]
            n += 1
        leftover = model_kept + rest
    stamp = pipeline.now()
    short = leftover[:KEEP_MAX]
    body = [f"# Triage {stamp}", "",
            f"{before} open. cheap agent: {triage_agent()}.",
            f"drain: {stats['dropped']}",
            f"model DROP {model_drop}, unparsed {unparsed}, "
            f"still open {len(open_proposals())}.", ""]
    for i, p in enumerate(short, 1):
        body.append(f"{i} | {gist(p.get('text'), 70)} | {p['ts'][:16]}")
    if not short:
        body.append("(nothing kept)")
    (FLEET / "rota" / "triage.md").write_text("\n".join(body) + "\n")
    ev.emit("pipeline", "ok",
            f"[autotriage] {before} open → {len(open_proposals())} "
            f"(drain {sum(stats['dropped'].values())}, "
            f"model drop {model_drop})")
    pipeline.write_worker()
    return {"before": before, "open": len(open_proposals()),
            "dropped": stats["dropped"], "model_drop": model_drop,
            "kept": len(short)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drain-only", action="store_true")
    ap.add_argument("--batches", type=int, default=1)
    a = ap.parse_args()
    res = run(batches=a.batches, drain_only=a.drain_only)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
