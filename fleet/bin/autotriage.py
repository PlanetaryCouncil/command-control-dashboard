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
REVIEW_LIMIT = 12
PICK_MAX = 1
VOTERS = ("agy", "grok")
KEEP_LINE = re.compile(r"KEEP\s+(20\d\d-\d\d-\d\dT\d\d:\d\d)", re.I)
# Specific phrases only. "i'll " is too broad — a real "I'll add X"
# would be skipped. These are the prompt-echo turns that filled the
# first review-old batch.
NARRATION = (
    "three questions",
    "play along",
    "here are my answers",
    "i'd like to propose answers",
    "i'll answer the three",
    "the message seems to be",
    "the text you provided appears",
    "here is the reformatted text",
    "this appears to be a log",
    "i'll follow the steps",
    "provide my answers",
    "i'll do my best to answer",
    "i'll respond to the questions",
    "i'm ready to play",
    "it seems like the team",
    "based on the provided",
    "here are the answers",
    "here are two-line",
    "session limit",
    "closing poems",
    "pick one project",
    "answer the question",
    "answering these questions",
    "i'll take on the challenge",
    "i'll do my best to follow",
)
# A wrapped "here are the answers" that still names a file to write
# is a proposal, not a Q&A echo.
ACTION_MARK = ("write `", "write static/", ".html`", ".py`")
FILE_KEY = re.compile(r"static/[a-z0-9_./-]+", re.I)
LAST_VOTE_RAW: dict[str, str] = {}
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


def unique_key(text: str) -> str:
    """Same static path = same idea, even when the wrapper words differ."""
    m = FILE_KEY.search(str(text))
    if m:
        return m.group(0).lower().rstrip("/")
    return gist(text)


def triage_agent() -> str:
    who = (os.environ.get("FLEET_TRIAGE") or "").strip()
    if not who:
        try:
            cfg = json.loads((FLEET / "config.json").read_text())
            who = str((cfg.get("pipeline") or {}).get("triage_agent") or "")
        except (OSError, ValueError):
            who = ""
    who = (who or "agy").strip() or "agy"
    if who in ("claude", "openclaw"):
        return "agy"
    return who


def usable_triage_agent() -> str:
    """The configured cheap agent, or the nearest one that can answer.

    A dry vendor is not a cheap vendor, it is no vendor. agy went
    quota-dead for five days on 2026-08-28 and triage kept naming it,
    so every batch was a no-op the log reported as "0 open". The
    config still states the preference; this states who is awake.
    """
    who = triage_agent()
    try:
        import quotas
        if not quotas.eligible([who]):
            for alt in ("grok", "agy", "hermes"):
                if alt != who and quotas.eligible([alt]):
                    return alt
    except Exception:
        pass
    return who


def ask_cheap(prompt: str) -> str:
    noop = lambda *a, **k: None
    who = usable_triage_agent()
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
    return [p for p in pipeline.proposals() if pipeline.is_waiting(p, seen)]


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
        rec = pipeline.by_proposal().get(p.get("ts"))
        if rec and rec.get("stage") == "reopen":
            kept.append(p)
            continue
        # No expiry. Age is not evidence. A proposal is closed because it is
        # empty, duplicated, narration, or a cheap model read it and said
        # DROP -- all judgements about the CONTENT. "Filed more than a day
        # ago" is a judgement about the queue's throughput, charged to the
        # proposal.
        #
        # It closed 140 proposals in 24 hours on 2026-08-26, more than half
        # of everything the pipeline touched, and none of them were ever
        # read. Marsita: "died of old age? I don't want to expire... Bad
        # design... Old proposals remain valid."
        #
        # The tell was already in this file: unique_stale() below exists to
        # dig stale-closed proposals back out for review. A queue that closes
        # items and then maintains machinery to recover them has admitted the
        # closing was wrong.
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
    who = "triage-" + usable_triage_agent()
    for p in drop:
        close(p, "cheap-model DROP", by=who)
    return {"keep": keep, "drop": len(drop), "raw": raw[:1500],
            "unparsed": len(batch) - len(verdicts)}


def unique_stale(limit: int = REVIEW_LIMIT) -> list[dict]:
    """Oldest-dropped unique gists the last day did not repeat."""
    props = {p["ts"]: p for p in pipeline.proposals()}
    seen = pipeline.by_proposal()
    recent = {unique_key(p.get("text") or "")
              for p in props.values() if not too_old(p.get("ts") or "")}
    stale = []
    for ts, rec in seen.items():
        if rec.get("stage") != "drop":
            continue
        if not str(rec.get("detail") or "").startswith("stale"):
            continue
        p = props.get(ts)
        if not p or (p.get("outcome") in NOISE):
            continue
        g = gist(p.get("text") or "")
        k = unique_key(p.get("text") or "")
        if not k or k in recent:
            continue
        narrated = any(n in g for n in NARRATION)
        action = any(m in g for m in ACTION_MARK)
        if narrated and not action:
            continue
        stale.append(p)
    stale.sort(key=lambda p: p.get("ts") or "", reverse=True)
    out, used = [], set()
    for p in stale:
        k = unique_key(p.get("text") or "")
        if k in used:
            continue
        used.add(k)
        out.append(p)
        if len(out) >= limit:
            break
    return out


def parse_keep_stamps(blob: str, batch_ts: set[str]) -> set[str]:
    hits = set()
    for m in KEEP_LINE.finditer(str(blob)):
        prefix = m.group(1)
        for t in batch_ts:
            if t.startswith(prefix):
                hits.add(t)
    return hits


def vote_keep(batch: list[dict], who: str) -> set[str]:
    lines = [f"{p['ts'][:16]} | {gist(p.get('text'), 140)}" for p in batch]
    prompt = (
        "Do not use tools. Do not read files. You are voting, not "
        "implementing. These proposals were marked stale but might "
        "still be valid. KEEP only a real remaining improvement.\n"
        "Reply with ONLY lines of the form KEEP YYYY-MM-DDTHH:MM "
        "or a single line NONE. At most 3 KEEP.\n\n" + "\n".join(lines)
    )
    raw = ask_named(who, prompt)
    LAST_VOTE_RAW[who] = str(raw)[:1500]
    hits = parse_keep_stamps(raw, {p["ts"] for p in batch})
    ev.emit("pipeline", "ok",
            f"[autotriage] {who} KEEP {len(hits)} "
            f"raw={str(raw).replace(chr(10), ' ')[:160]}")
    return hits


def ask_named(who: str, prompt: str) -> str:
    noop = lambda *a, **k: None
    if who == "agy":
        return chat.ask_agy(prompt, [], noop, timeout=180)
    if who == "grok":
        return chat.ask_grok(prompt, [], noop, timeout=180)
    if who == "hermes":
        return chat.ask_hermes(prompt, noop, timeout=180)
    return f"[unknown agent {who}]"


def write_picks(items: list[dict]) -> None:
    """build.txt is what the pipeline will actually build. Cap is the point."""
    path = FLEET / "rota" / "build.txt"
    lines = []
    for i, p in enumerate(items[:PICK_MAX], 1):
        title = gist(p.get("text"), 60)
        lines.append(f"# {i}. {title}")
        lines.append(p["ts"][:19])
        lines.append("")
    path.write_text("\n".join(lines) + "\n")


def review_old(limit: int = REVIEW_LIMIT, pick: int = PICK_MAX) -> dict:
    """Two vendors must KEEP. Then at most `pick` items go to build.txt."""
    LAST_VOTE_RAW.clear()
    reps = unique_stale(limit)
    if not reps:
        return {"reps": 0, "agreed": 0, "picked": 0}
    votes = {who: vote_keep(reps, who) for who in VOTERS}
    if any(len(v) == 0 for v in votes.values()):
        votes["hermes"] = vote_keep(reps, "hermes")
    nonempty = [v for v in votes.values() if v]
    agreed_ts = (set.intersection(*nonempty) if len(nonempty) >= 2
                 else set())
    agreed = [p for p in reps if p["ts"] in agreed_ts]
    # reopen agreed so drain will not stale them this hour
    for p in agreed:
        pipeline.record(proposal_ts=p["ts"], stage="reopen", ok=True,
                        detail="unique stale, two vendors KEEP",
                        agent="autotriage", branch="")
    picked = agreed[:pick]
    if picked:
        write_picks(picked)
    receipt = {
        "reps": [{"ts": p["ts"], "gist": gist(p.get("text"), 80)}
                 for p in reps],
        "votes": {w: sorted(v) for w, v in votes.items()},
        "raw": dict(LAST_VOTE_RAW),
        "agreed": [p["ts"] for p in agreed],
        "picked": [p["ts"] for p in picked],
    }
    (FLEET / "rota" / "review-old.json").write_text(
        json.dumps(receipt, indent=2) + "\n")
    ev.emit("pipeline", "ok",
            f"[autotriage] review-old {len(reps)} unique stale → "
            f"{len(agreed)} agreed → {len(picked)} picked "
            f"({', '.join(VOTERS)})")
    return {"reps": len(reps), "agreed": len(agreed),
            "picked": len(picked),
            "votes": {w: len(v) for w, v in votes.items()}}


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
            f"{before} open. cheap agent: {usable_triage_agent()}.",
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


def autopick(limit: int = 1) -> dict:
    """Fill build.txt from the KEPT shortlist when nothing is queued.

    Picking what to BUILD was a human step. That is the right default when a
    human is around, and it is why 1715 proposals sat untouched: build.txt
    still named a pick from 2026-08-19 and nothing had been queued since.

    What it does NOT touch is the invariant that matters. The builder works
    in a throwaway git worktree on a rota/* branch, never pushes, and never
    merges. A human still lands every branch. Automating the pick changes
    how much gets built; it does not change who decides what ships.

    Only writes when the queue is genuinely empty, so a pick a human made by
    hand is never overwritten.
    """
    queued = [i for i in pipeline._picked_items()
              if any(t not in pipeline.by_proposal() for t in i["ts"])]
    if queued:
        return {"picked": 0, "reason": "queue already has unbuilt items"}

    seen = pipeline.by_proposal()
    waiting = [p for p in pipeline.proposals()
               if pipeline.is_waiting(p, seen) and (p.get("text") or "").strip()]
    if not waiting:
        return {"picked": 0, "reason": "nothing waiting"}

    # Oldest first. These have waited longest and were never read; a queue
    # that always takes the newest is how a backlog becomes permanent.
    waiting.sort(key=lambda p: p.get("ts") or "")
    picks = waiting[:limit]
    lines = []
    for n, p in enumerate(picks, 1):
        title = " ".join((p.get("text") or "").split())[:70]
        lines.append(f"# {n}. {title}")
        lines.append(p["ts"])
    (FLEET / "rota" / "build.txt").write_text("\n".join(lines) + "\n")
    ev.emit("autotriage", "info",
            f"[triage] auto-picked {len(picks)} proposal(s) for build; "
            f"{len(waiting)} still waiting")
    return {"picked": len(picks), "oldest": picks[0]["ts"]}


def unexpire(dry_run: bool = False) -> dict:
    """Bring back every proposal that was closed for being old.

    Expiry is gone from the drain, but the ledger still carries the ones it
    already took -- 140 in a single day. They were never read, never judged,
    and never wrong; they were late. This reopens exactly those: closures
    whose stated reason is age, and nothing else. A proposal a model actually
    read and dropped stays dropped.

    Append-only. The stale record stays in the ledger and a reopen is written
    after it, so the history still shows what happened rather than pretending
    it did not.
    """
    props = {p["ts"]: p for p in pipeline.proposals() if p.get("ts")}
    seen = pipeline.by_proposal()
    back = []
    for ts, rec in seen.items():
        if rec.get("stage") != "drop":
            continue
        if not str(rec.get("detail") or "").startswith("stale"):
            continue
        if ts not in props:
            continue
        back.append(ts)
    if not dry_run:
        for ts in back:
            pipeline.record(proposal_ts=ts, stage="reopen", ok=True,
                            detail="unexpired: age is not a verdict",
                            agent="autotriage", branch="")
        if back:
            ev.emit("autotriage", "info",
                    f"[triage] {len(back)} proposals unexpired -- "
                    f"closed for age, never read")
    return {"unexpired": len(back), "dry_run": dry_run}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drain-only", action="store_true")
    ap.add_argument("--batches", type=int, default=1)
    ap.add_argument("--review-old", action="store_true",
                    help="two vendors review unique stale ideas; pick for build")
    ap.add_argument("--limit", type=int, default=REVIEW_LIMIT)
    ap.add_argument("--pick", type=int, default=PICK_MAX)
    ap.add_argument("--unexpire", action="store_true",
                    help="reopen proposals that were closed only for age")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--autopick", type=int, default=0,
                    help="fill build.txt from the backlog when nothing queued")
    a = ap.parse_args()
    if a.autopick:
        res = autopick(limit=a.autopick)
    elif a.unexpire:
        res = unexpire(dry_run=a.dry_run)
    elif a.review_old:
        res = review_old(limit=a.limit, pick=a.pick)
    else:
        res = run(batches=a.batches, drain_only=a.drain_only)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
