#!/usr/bin/env python3
"""Proposals become branches; branches get tested; you get a yes/no.

  pipeline.py run       one cycle: build the newest untried proposal, then
                        verify any built branch that lacks a verdict
  pipeline.py status    print the pipeline state

The council's own finding, three sittings in a row: the rota is write-only —
agents propose and nothing ever reads the proposals. Marsita, 2026-08-04:
"they are supposed to suggest improvements -> work on branch -> other agent
is testing -> obviously". This is that pipe.

Stages, each a different pair of hands:
  1. build   — claude (the only agent here that can edit files) implements
               the proposal in a fresh git worktree on branch rota/<slug>,
               runs the tests, commits. It never pushes and never merges.
  2. verify  — pytest runs mechanically in the worktree, then hermes (a
               different vendor) reads the diff and answers APPROVE or
               REJECT with a reason. Builder never grades its own work.
  3. decide  — a human. The board's `pipeline` card lists what awaits a
               yes; merging stays a human action, always.

State is one JSONL (rota/pipeline.jsonl); each proposal is keyed by its
timestamp. The load gate mirrors the rota's: this is a 4-core/8GB box and a
build that starts during a swap storm helps nobody.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
REPO = FLEET.parent
PROPOSALS = FLEET / "rota" / "proposals.jsonl"
STATE = FLEET / "rota" / "pipeline.jsonl"
WORKER = FLEET / "workers" / "pipeline.json"
WORKTREES = REPO.parent / ".cc-pipeline-worktrees"
MAX_LOAD = 6.0
# One cycle keeps going until the queue empties or the box gets busy. The
# ceiling is a backstop against a runaway loop, not a target: at ~6 min a
# build, twelve is roughly an hour of work.
MAX_PER_CYCLE = 12
BUILD_TIMEOUT = 900
DIFF_CLIP = 6000

sys.path.insert(0, str(Path(__file__).resolve().parent))
import events as ev  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state() -> list[dict]:
    try:
        return [json.loads(l) for l in STATE.read_text().splitlines() if l.strip()]
    except OSError:
        return []


def record(**rec) -> dict:
    rec["ts"] = now()
    with STATE.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def by_proposal() -> dict:
    """proposal_ts -> latest pipeline record for it."""
    out = {}
    for r in state():
        out[r.get("proposal_ts", "?")] = r
    return out


def proposals() -> list[dict]:
    try:
        rows = [json.loads(l) for l in PROPOSALS.read_text().splitlines() if l.strip()]
    except OSError:
        return []
    return [r for r in rows if r.get("text")]


def slug(text: str) -> str:
    first = next((l for l in str(text).splitlines() if l.strip("# ").strip()), "")
    s = re.sub(r"[^a-z0-9]+", "-", first.lower()).strip("-")[:40]
    return s or "proposal"


def run(cmd, cwd=None, timeout=300, stdin_text=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, input=stdin_text)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"[timed out after {timeout}s]"
    except Exception as e:  # noqa: BLE001 — a broken tool is a verdict, not a crash
        return 1, f"[error] {e}"


def build(prop: dict) -> dict:
    branch = f"rota/{prop['ts'][:10]}-{slug(prop['text'])}"
    wt = WORKTREES / branch.replace("/", "-")
    WORKTREES.mkdir(exist_ok=True)
    code, out = run(["git", "worktree", "add", "-b", branch, str(wt), "main"],
                    cwd=REPO)
    if code != 0 and "already exists" not in out:
        return record(stage="build", proposal_ts=prop["ts"], branch=branch,
                      ok=False, detail=out[-300:])

    prompt = f"""You are the build stage of an agent pipeline. Working copy: {wt}
(a git worktree on branch {branch} — you are already on it).

Implement the smallest working version of this proposal from the fleet's rota:

--- PROPOSAL (by {prop.get('agent', '?')}) ---
{str(prop['text'])[:1500]}
--- END ---

Rules: touch only what the proposal needs. Run `.venv/bin/pytest -q` (the
venv is at {REPO}/.venv) and make it pass. Commit everything with a clear
message. Do NOT push. Do NOT merge. Do NOT touch other branches. If the
proposal is not implementable as code, commit nothing and say why in one
line starting with SKIP:."""
    # acceptEdits covers file edits only — the first live cycle implemented
    # its proposal and then couldn't run `git commit`. Grant the exact
    # commands the job needs, nothing broader.
    code, out = run(["claude", "--print", "--permission-mode", "acceptEdits",
                     "--allowedTools",
                     "Bash(git add:*)", "Bash(git commit:*)",
                     "Bash(git status:*)", "Bash(git diff:*)",
                     "Bash(git log:*)", f"Bash({REPO}/.venv/bin/pytest:*)",
                     "Bash(.venv/bin/pytest:*)",
                     "WebSearch", "WebFetch"],
                    cwd=wt, timeout=BUILD_TIMEOUT, stdin_text=prompt)
    committed = run(["git", "log", "--oneline", "main..HEAD"], cwd=wt)[1].strip()
    ok = code == 0 and bool(committed)
    ev.emit("pipeline", "ok" if ok else "warn",
            f"[pipeline] build {branch}: "
            + (f"committed: {committed.splitlines()[0]}" if ok
               else f"nothing committed ({out.strip()[-120:]})"))
    return record(stage="build", proposal_ts=prop["ts"], branch=branch,
                  ok=ok, worktree=str(wt), detail=out.strip()[-300:])


def revise(rejected: dict) -> dict:
    """One round, no more: the builder answers the reviewer's objection.

    Marsita, 2026-08-04: "one round of revise is good". The branch gets
    exactly one chance to fix what the verifier named; then the verdict —
    whichever way it lands — is final. Rebuttal loops are how pipelines
    stop terminating.
    """
    branch, wt = rejected["branch"], WORKTREES / rejected["branch"].replace("/", "-")
    WORKTREES.mkdir(exist_ok=True)
    code, out = run(["git", "worktree", "add", str(wt), branch], cwd=REPO)
    if code != 0:
        return record(stage="revise", proposal_ts=rejected["proposal_ts"],
                      branch=branch, ok=False, detail=out[-300:])
    before = run(["git", "rev-parse", "HEAD"], cwd=wt)[1].strip()
    prompt = f"""You are the revise stage of an agent pipeline. Working copy: {wt}
(branch {branch}, already checked out). Your earlier change on this branch
was REJECTED by an independent reviewer. This is your one revision round.

REVIEWER'S OBJECTION:
{rejected.get('review', '(none recorded)')}

TESTS AT REVIEW TIME: {rejected.get('tests', '?')}

Fix exactly what the objection names — smallest change that answers it.
Run `.venv/bin/pytest -q` (venv at {REPO}/.venv) and keep it green. Commit.
Do NOT push, do NOT merge. If the objection cannot be answered in code,
commit nothing and say why in one line starting with SKIP:."""
    code, out = run(["claude", "--print", "--permission-mode", "acceptEdits",
                     "--allowedTools",
                     "Bash(git add:*)", "Bash(git commit:*)",
                     "Bash(git status:*)", "Bash(git diff:*)",
                     "Bash(git log:*)", f"Bash({REPO}/.venv/bin/pytest:*)",
                     "Bash(.venv/bin/pytest:*)", "WebSearch", "WebFetch"],
                    cwd=wt, timeout=BUILD_TIMEOUT, stdin_text=prompt)
    after = run(["git", "rev-parse", "HEAD"], cwd=wt)[1].strip()
    ok = code == 0 and after != before
    ev.emit("pipeline", "ok" if ok else "warn",
            f"[pipeline] revise {branch}: "
            + ("new commit, re-verifying" if ok
               else f"no revision ({out.strip()[-120:]})"))
    rec = record(stage="revise", proposal_ts=rejected["proposal_ts"],
                 branch=branch, ok=ok, worktree=str(wt),
                 detail=out.strip()[-300:])
    if ok:
        verify(rec)
    else:
        run(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO)
    return rec


def verify(built: dict) -> dict:
    wt, branch = Path(built["worktree"]), built["branch"]
    code, out = run([str(REPO / ".venv" / "bin" / "pytest"), "-q"],
                    cwd=wt, timeout=600)
    tests_ok = code == 0
    tests_line = out.strip().splitlines()[-1] if out.strip() else "no output"

    diff = run(["git", "diff", f"main...{branch}", "--stat", "-p"],
               cwd=REPO)[1][:DIFF_CLIP]
    import chat  # noqa: E402 — sibling module, path set at import time
    noop = lambda *a, **k: None
    review = chat.ask_hermes(
        "You are the verify stage of a pipeline. Another agent implemented a "
        "proposal on a branch. Tests: "
        f"{'PASS' if tests_ok else 'FAIL'} ({tests_line}). Review this diff "
        "for correctness and scope creep. First line of your answer must be "
        f"exactly APPROVE or REJECT, then one sentence why.\n\n{diff}", noop)
    approved = str(review).strip().upper().startswith("APPROVE")
    verdict = "approved" if (tests_ok and approved) else "rejected"
    ev.emit("pipeline", "needs_you" if verdict == "approved" else "warn",
            f"[pipeline] {branch}: tests {'pass' if tests_ok else 'FAIL'}, "
            f"hermes {verdict} — {' '.join(str(review).split())[:140]}")
    run(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO)
    return record(stage="verify", proposal_ts=built["proposal_ts"],
                  branch=branch, ok=verdict == "approved",
                  tests=tests_line, review=" ".join(str(review).split())[:300])


def write_worker() -> None:
    done = by_proposal()
    awaiting = [r for r in done.values()
                if r.get("stage") == "verify" and r.get("ok")]
    rejected = [r for r in done.values()
                if r.get("stage") == "verify" and not r.get("ok")]
    # The alert carries its own remedy: naming a branch makes Marsita go
    # reconstruct the command; pasting one line clears the queue.
    summary = (" · ".join(f"{r['branch']} awaits your merge — "
                          f"git merge --no-ff {r['branch']}" for r in awaiting)
               or f"nothing awaiting ({len(rejected)} rejected, "
                  f"{len(done)} proposals processed)")
    WORKER.parent.mkdir(exist_ok=True)
    WORKER.write_text(json.dumps({
        "worker": "pipeline", "kind": "pipeline",
        "status": "alert" if awaiting else "pass",
        "last_run": now(), "summary": summary[:200],
    }, indent=2))


def cycle() -> None:
    if os.getloadavg()[0] > MAX_LOAD:
        ev.emit("pipeline", "info",
                f"[pipeline] deferred — load {os.getloadavg()[0]:.1f} over {MAX_LOAD}")
        return
    seen = by_proposal()
    # Verify first: a built branch without a verdict blocks nothing else.
    for r in list(seen.values()):
        if r.get("stage") == "build" and r.get("ok"):
            verify(r)
    # One revise round for fresh rejections, then the verdict is final.
    revised = {r["proposal_ts"] for r in state() if r.get("stage") == "revise"}
    for r in list(by_proposal().values()):
        if (r.get("stage") == "verify" and not r.get("ok")
                and r["proposal_ts"] not in revised):
            revise(r)
    # Drain, don't sip. The rota files one proposal an hour and this ran
    # one every two — so the queue grew by half a proposal an hour,
    # forever, and 27 of them was 54 hours of work that would never
    # arrive (Marsita did the arithmetic, 2026-08-05). Now a cycle keeps
    # building until the queue is empty, the load gate says stop, or the
    # budget is spent — whichever comes first.
    built = 0
    while built < MAX_PER_CYCLE:
        if os.getloadavg()[0] > MAX_LOAD:
            ev.emit("pipeline", "info",
                    f"[pipeline] stopping after {built} — load "
                    f"{os.getloadavg()[0]:.1f} over {MAX_LOAD}")
            break
        seen = by_proposal()
        todo = [p for p in reversed(proposals()) if p["ts"] not in seen]
        if not todo:
            if built:
                ev.emit("pipeline", "ok",
                        f"[pipeline] queue empty after {built} this cycle")
            break
        rec = build(todo[0])
        built += 1
        if rec.get("stage") == "build" and rec.get("ok"):
            verify(rec)
        write_worker()
    write_worker()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode == "run":
        cycle()
    else:
        for ts, r in by_proposal().items():
            print(f"{ts}  {r.get('stage'):<7} {'ok' if r.get('ok') else 'NO':<3}"
                  f" {r.get('branch','')}  {r.get('tests', r.get('detail',''))[:60]}")
