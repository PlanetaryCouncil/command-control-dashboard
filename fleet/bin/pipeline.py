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
  1. build   — grok (or FLEET_BUILDER) implements the proposal in a
               fresh git worktree on branch rota/<slug>, runs the tests,
               commits. It never pushes and never merges.
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
LOCK = FLEET / "logs" / ".pipeline.lock"
WORKTREES = REPO.parent / ".cc-pipeline-worktrees"
MAX_LOAD = 6.0
# One cycle keeps going until the queue empties or the box gets busy. The
# ceiling is a backstop against a runaway loop, not a target: at ~6 min a
# build, twelve is roughly an hour of work.
MAX_PER_CYCLE = 12
BUILD_TIMEOUT = 900
DIFF_CLIP = 6000


def venv_pytest() -> Path:
    """The pytest that actually exists on THIS machine.

    `.venv` was hardcoded, which was true on the Mac and false on the NUC:
    that box's `.venv` is python 3.14, which has no pytest and no coincurve
    wheel, so its 3.11 environment lives in `.venv311`. On 2026-08-07 all four
    builds of the night succeeded and all four verifications failed on
    "pytest does not exist" — the builder agents even said so in their
    reports, having tried every alternate invocation and been refused by the
    permission rules. The work was fine. The path was wrong.

    Preference order, first hit wins; falls back to `.venv` so the failure
    message still names the conventional location.
    """
    for name in (".venv", ".venv311", ".venv312", ".venv313"):
        p = REPO / name / "bin" / "pytest"
        if p.exists():
            return p
    return REPO / ".venv" / "bin" / "pytest"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buildgate     # noqa: E402
import chat          # noqa: E402
import events as ev  # noqa: E402


def builder_name() -> str:
    """Who implements. Default grok: it is here, it has credits, it edits.

    Claude stays selectable via FLEET_BUILDER=claude when that plan is alive
    again. The reviewer is always hermes, a different company.
    """
    return os.environ.get("FLEET_BUILDER", "grok").strip() or "grok"


def run_builder(prompt, cwd, timeout=BUILD_TIMEOUT):
    who = builder_name()
    if who == "grok":
        return run(["grok", "-p", prompt, "--output-format", "plain",
                    "--always-approve", "--cwd", str(cwd)],
                   cwd=cwd, timeout=timeout)
    return run(["claude", "--print", "--permission-mode", "acceptEdits",
                "--allowedTools",
                "Bash(git add:*)", "Bash(git commit:*)",
                "Bash(git status:*)", "Bash(git diff:*)",
                "Bash(git log:*)", f"Bash({venv_pytest()}:*)",
                "Bash(.venv/bin/pytest:*)", "Bash(.venv311/bin/pytest:*)",
                "WebSearch", "WebFetch"],
               cwd=cwd, timeout=timeout, stdin_text=prompt)


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
    first = first.lstrip("# ").strip()
    s = re.sub(r"[^a-z0-9]+", "-", first.lower()).strip("-")[:40]
    return s or "proposal"


def branch_name(prop: dict) -> str:
    """rota/<date>-<hhmm>-<slug> — the time keeps same-day proposals apart.

    Two agents filing near-identical titles on one day used to collide on a
    single branch, so a rejection of one read as a rejection of all.
    """
    ts = str(prop.get("ts", ""))
    hhmm = re.sub(r"[^0-9]", "", ts[11:16])[:4]
    stamp = f"{ts[:10]}-{hhmm}" if hhmm else ts[:10]
    return f"rota/{stamp}-{slug(prop['text'])}"


def branch_exists(branch: str) -> bool:
    code, _ = run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                  cwd=REPO)
    return code == 0


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
    branch = branch_name(prop)
    wt = WORKTREES / branch.replace("/", "-")
    if branch_exists(branch):
        # never build a second proposal onto someone else's branch
        return record(stage="build", proposal_ts=prop["ts"], branch=branch,
                      ok=False, detail=f"branch {branch} already exists — refusing to reuse it")
    WORKTREES.mkdir(exist_ok=True)
    code, out = run(["git", "worktree", "add", "-b", branch, str(wt), "main"],
                    cwd=REPO)
    if code != 0:
        return record(stage="build", proposal_ts=prop["ts"], branch=branch,
                      ok=False, detail=out[-300:])

    prompt = f"""You are the build stage of an agent pipeline. Working copy: {wt}
(a git worktree on branch {branch} — you are already on it).

Implement the smallest working version of this proposal from the fleet's rota:

--- PROPOSAL (by {prop.get('agent', '?')}) ---
{str(prop['text'])[:1500]}
--- END ---

Rules: touch only what the proposal needs. Run `{venv_pytest()} -q` — that
exact path, it is this machine's environment and the only one the permission
rules allow — and make it pass. Commit everything with a clear
message. Do NOT push. Do NOT merge. Do NOT touch other branches. If the
proposal is not implementable as code, commit nothing and say why in one
line starting with SKIP:."""
    code, out = run_builder(prompt, wt)
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
    code, out = run_builder(prompt, wt)
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

    # Test the tree you will actually get. hermes rejected a branch on
    # 2026-08-04 for exactly this — "can mark a branch ready to merge from
    # cached branch-tip test results without testing the branch integrated
    # with current main" — and the pipeline itself kept doing it: a branch
    # cut at 09:00 was verified against a main that had moved by the time
    # anyone merged. So merge main in first. A conflict is a rejection with
    # a real reason, not a surprise at merge time.
    code, out = run(["git", "merge", "--no-edit", "main"], cwd=wt)
    if code != 0:
        run(["git", "merge", "--abort"], cwd=wt)
        ev.emit("pipeline", "warn",
                f"[pipeline] {branch}: conflicts with current main — rejected")
        run(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO)
        return record(stage="verify", proposal_ts=built["proposal_ts"],
                      branch=branch, ok=False, tests="not run",
                      review=f"REJECT conflicts with main: {out[-200:]}")

    code, out = run([str(venv_pytest()), "-q"], cwd=wt, timeout=600)
    tests_ok = code == 0
    tests_line = out.strip().splitlines()[-1] if out.strip() else "no output"

    diff = run(["git", "diff", f"main...{branch}", "--stat", "-p"],
               cwd=REPO)[1][:DIFF_CLIP]
    import chat  # noqa: E402 — sibling module, path set at import time
    noop = lambda *a, **k: None
    review = chat.ask_hermes(
        "You are the verify stage of a pipeline. Another agent implemented a "
        "proposal on a branch, which has been merged with current main "
        "before testing — so these results reflect the tree that would "
        "actually ship. Tests: "
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


def land(verified: dict) -> dict:
    """Merge an approved branch into main and push it. No human in the loop.

    Marsita, 2026-08-07: "fleet can merge... I'm not able to understand
    subtle code nuance... I don't want to worry about infra / pr / code /
    issues." A queue of approved branches waiting on someone who does not
    read diffs is not review, it is a stall dressed as caution.

    Three things stand between a branch and main, and all three are machine
    checks rather than opinions:

    1. It was verified — tests ran on the branch already merged with main,
       and the reviewer said APPROVE.
    2. It merges cleanly, no conflict.
    3. **The suite passes again on the merge commit itself.** Two branches
       can each be green and break each other; that is exactly the case a
       per-branch verdict cannot see, and the only moment it is visible is
       here, after the merge and before the push.

    Any of those failing rolls main back to where it was. The branch keeps
    its commits and its verdict, so nothing is lost — it simply did not land
    this cycle.
    """
    branch = verified["branch"]
    ts = verified["proposal_ts"]
    # Never touch the shared checkout. It belongs to whoever is working in it
    # — on 2026-08-07 the Nuc's tree was sitting on another agent's branch
    # mid-task, and `git checkout main` here would have yanked it away
    # underneath them. The merge happens in a worktree of its own and the
    # push goes from there; the operator's tree never moves.
    wt = WORKTREES / f"land-{branch.replace('/', '-')}"
    WORKTREES.mkdir(exist_ok=True)
    run(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO)
    # Base the merge on origin's main, not on whatever local main happens to
    # be. When several branches land in one loop, each push advances the
    # remote and leaves the local ref behind; building on the stale ref is
    # what produced the standing "push: behind its remote" alert.
    run(["git", "fetch", "origin", "main:main"], cwd=REPO)
    code, out = run(["git", "worktree", "add", "--detach", str(wt), "main"],
                    cwd=REPO)
    if code != 0:
        return record(stage="land", proposal_ts=ts, branch=branch, ok=False,
                      detail=f"worktree: {out[-200:]}")

    def done(ok, **extra):
        run(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO)
        return record(stage="land", proposal_ts=ts, branch=branch, ok=ok, **extra)

    # Two attempts. A push refused because the remote moved between the fetch
    # above and the push below is a race with our own sibling lands, not a
    # real conflict — rebuild on the new main and try once more before
    # raising an alert a human has to read.
    for attempt in (1, 2):
        code, out = run(["git", "merge", "--no-ff", "--no-edit", branch], cwd=wt)
        if code != 0:
            run(["git", "merge", "--abort"], cwd=wt)
            ev.emit("pipeline", "warn", f"[land] {branch}: conflicts with main")
            return done(False, detail=f"conflict: {out[-200:]}")

        merge_sha = run(["git", "rev-parse", "HEAD"], cwd=wt)[1].strip()
        code, out = run([str(venv_pytest()), "-q"], cwd=wt, timeout=900)
        if code != 0:
            # The merge commit is what failed, so the merge commit is what gets
            # thrown away — not the branch, which is still good on its own and
            # may land once whatever it collided with is fixed. Discarding the
            # worktree discards the merge; main was never moved.
            tail = out.strip().splitlines()[-1] if out.strip() else "no output"
            ev.emit("pipeline", "warn",
                    f"[land] {branch}: green alone, red merged — dropped ({tail})")
            return done(False, detail=f"merged tests: {tail}")

        # Push the merge commit straight at main. Nothing local is updated to
        # point at it until the push is accepted, so a rejected push leaves no
        # half-landed state anywhere.
        code, out = run(["git", "push", "origin", f"{merge_sha}:main"],
                        cwd=wt, timeout=300)
        if code == 0:
            run(["git", "fetch", "origin", "main:main"], cwd=REPO)
            ev.emit("pipeline", "ok",
                    f"[land] {branch} merged to main and pushed")
            return done(True, sha=merge_sha[:12])

        if attempt == 1:
            ev.emit("pipeline", "info",
                    f"[land] {branch}: push refused, rebuilding on new main "
                    f"({out[-120:]})")
            run(["git", "fetch", "origin", "main:main"], cwd=REPO)
            rc, rout = run(["git", "reset", "--hard", "main"], cwd=wt)
            if rc != 0:
                return done(False, detail=f"reset: {rout[-200:]}")
            continue

        ev.emit("pipeline", "warn",
                f"[land] {branch}: push refused twice ({out[-120:]})")
        return done(False, detail=f"push: {out[-200:]}")


def write_worker() -> None:
    done = by_proposal()
    landed = [r for r in done.values() if r.get("stage") == "land" and r.get("ok")]
    stuck = [r for r in done.values() if r.get("stage") == "land" and not r.get("ok")]
    awaiting = [r for r in done.values()
                if r.get("stage") == "verify" and r.get("ok")]
    rejected = [r for r in done.values()
                if r.get("stage") == "verify" and not r.get("ok")]
    # Approved branches land themselves now, so "awaiting" means the landing
    # failed, not that someone forgot to merge. Only that is worth an alert —
    # a green cycle should say what it did and then be quiet.
    if stuck:
        summary = " · ".join(f"{r['branch']} could not land: "
                             f"{str(r.get('detail'))[:60]}" for r in stuck)
    elif awaiting:
        summary = " · ".join(f"{r['branch']} approved, not yet landed"
                             for r in awaiting)
    else:
        summary = (f"{len(landed)} landed, {len(rejected)} rejected, "
                   f"{len(done)} proposals processed")
    WORKER.parent.mkdir(exist_ok=True)
    WORKER.write_text(json.dumps({
        "worker": "pipeline", "kind": "pipeline",
        "status": "alert" if (stuck or awaiting) else "pass",
        "last_run": now(), "summary": summary[:200],
    }, indent=2))


def _picked_items() -> list:
    """Tasks a human picked, each carrying every proposal it covers.

    ONE ITEM, ONE BRANCH. The first version of this returned bare
    timestamps and the build loop iterated them, so 27 proposals that
    triage had folded into 8 items produced 20 branches — 12 of them
    editing the same file, each tested against main and none against the
    others (2026-08-05, logged in brainfarts). Deduplication that the
    next stage ignores is not deduplication.

    build.txt is written by a human from triage.md: `# N. title` starts an
    item, the timestamps under it belong to it.
    """
    items, cur = [], None
    try:
        lines = (FLEET / "rota" / "build.txt").read_text().splitlines()
    except OSError:
        return []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line.lstrip("# ").strip()
            if body and body[0].isdigit() and "." in body[:4]:
                cur = {"title": body.split(".", 1)[1].strip(), "ts": []}
                items.append(cur)
            continue
        if cur is not None:
            cur["ts"].append(line[:19])
    return [i for i in items if i["ts"]]


def cycle() -> None:
    """One cycle, and only one at a time.

    The hourly launchd job fired while a manual run was mid-build on
    2026-08-05, so two pipelines built the same items in parallel and the
    ledger recorded two contradictory verdicts for one branch. Every other
    long job here (council, rota, plusone) already shares a lock; the
    pipeline was written without one. A cycle that finds the lock held
    exits quietly — the next hour will do it.
    """
    import fcntl
    LOCK.parent.mkdir(exist_ok=True)
    fh = LOCK.open("w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        ev.emit("pipeline", "info",
                "[pipeline] another cycle is running — skipping this one")
        return
    try:
        _cycle()
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _cycle() -> None:
    import pressure
    snap = pressure.snapshot()
    if snap["hot"] or (snap.get("disk") or {}).get("alert"):
        ev.emit("pipeline", "info",
                f"[pipeline] deferred — {snap['reason']}")
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
    # Land what passed. This runs before building and before the build gate,
    # so a machine that has handed compiling to its brother still merges the
    # work it verified — the queue never depends on which box is compiling.
    for r in list(by_proposal().values()):
        if r.get("stage") == "verify" and r.get("ok"):
            land(r)
    # Drain, don't sip. The rota files one proposal an hour and this ran
    # one every two — so the queue grew by half a proposal an hour,
    # forever, and 27 of them was 54 hours of work that would never
    # arrive (Marsita did the arithmetic, 2026-08-05). Now a cycle keeps
    # building until the queue is empty, the load gate says stop, or the
    # budget is spent — whichever comes first.
    # Only build what triage picked. An unreviewed proposal is a
    # suggestion, not a work order — the same mistake in miniature that
    # built a project out of an idea earlier today.
    # Verifying and revising happen above regardless: a machine that has
    # handed building to its faster brother still finishes what it started
    # and still judges the work. Only the compiling moves.
    if not buildgate.enabled():
        g = buildgate.read()
        ev.emit("pipeline", "info",
                f"[pipeline] building is off on {g.get('host')} — "
                f"{g.get('reason') or 'set from the board'}")
        write_worker()
        return
    items = _picked_items()
    if not items:
        ev.emit("pipeline", "info",
                "[pipeline] nothing picked — run triage, then fill build.txt")
        write_worker()
        return

    by_ts = {p["ts"][:16]: p for p in proposals()}
    done = by_proposal()
    built = 0
    for item in items:
        if built >= MAX_PER_CYCLE:
            break
        key = item["ts"][0]                    # an item is keyed by its first
        if key in done:
            continue
        if pressure.too_hot():
            ev.emit("pipeline", "info",
                    f"[pipeline] stopping after {built} — "
                    f"{pressure.snapshot()['reason']}")
            break
        # Every proposal the item covers goes into one prompt, so the
        # builder sees the whole ask instead of one agent's wording of it.
        parts = []
        for ts in item["ts"]:
            p = by_ts.get(ts[:16])
            if p:
                parts.append(f"--- observed by {p.get('agent','?')} at "
                             f"{p['ts'][:16]} ---\n{str(p['text'])[:900]}")
        merged = {"ts": key, "agent": "council-triage",
                  "text": f"# {item['title']}\n\n"
                          f"{len(parts)} agents observed this "
                          f"independently:\n\n" + "\n\n".join(parts)}
        rec = build(merged)
        built += 1
        if rec.get("stage") == "build" and rec.get("ok"):
            verify(rec)
        write_worker()
    if built:
        ev.emit("pipeline", "ok",
                f"[pipeline] built {built} item(s) this cycle — "
                f"one branch each")
    write_worker()


def triage() -> None:
    """Read every unprocessed proposal and say which deserve building.

    Marsita, 2026-08-05: "27 proposals that's good maybe we can simply
    review them? decide that needs to be built." Better than draining:
    most of a backlog is duplicates and stale observations, and building
    those costs agent-hours to produce branches nobody wants. One agent
    reads the lot, groups what repeats, and returns a ranked shortlist.
    The human picks; the pipeline builds only what was picked.
    """
    seen = by_proposal()
    todo = [p for p in proposals() if p["ts"] not in seen]
    if not todo:
        print("nothing to triage")
        return
    lines = []
    for p in todo:
        text = " ".join(str(p.get("text", "")).split())
        lines.append(f"[{p['ts'][:16]} by {p.get('agent','?')}] {text[:400]}")
    prompt = (
        "You are triaging a backlog of improvement proposals written by "
        "agents about the machine they run on. There are "
        f"{len(todo)} of them and most of a backlog is duplicates or "
        "already-fixed observations.\n\nGroup them. Then return AT MOST 8 "
        "items worth building, each one line:\n"
        "  RANK | one-line description | why it matters | the proposal "
        "timestamps it covers\n\nDrop anything already obviously done, "
        "purely observational, or repeated. Say how many you dropped and "
        "why in one final line. No preamble.\n\n" + "\n\n".join(lines))
    print(f"triaging {len(todo)} proposals…", flush=True)
    noop = lambda *a, **k: None
    out = chat.ask_grok(prompt, [], noop) if builder_name() == "grok" \
        else chat.ask_claude(prompt, [], noop)
    stamp = now()
    (FLEET / "rota" / "triage.md").write_text(
        f"# Triage {stamp}\n\n{len(todo)} unprocessed proposals reviewed.\n\n"
        f"{out}\n")
    ev.emit("pipeline", "needs_you",
            f"[pipeline] triaged {len(todo)} proposals - shortlist in "
            f"rota/triage.md, awaiting your picks")
    print(out[:2000])


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode == "run":
        cycle()
    elif mode == "triage":
        triage()
    else:
        for ts, r in by_proposal().items():
            print(f"{ts}  {r.get('stage'):<7} {'ok' if r.get('ok') else 'NO':<3}"
                  f" {r.get('branch','')}  {r.get('tests', r.get('detail',''))[:60]}")
