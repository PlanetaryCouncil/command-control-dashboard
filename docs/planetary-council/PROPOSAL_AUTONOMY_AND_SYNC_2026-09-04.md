# Proposal: autonomous merge, default orchestrator, live board sync

Written 2026-09-04, from a late-night NUC session, at Mars's request after he
said the pipeline's "nothing merges itself" gate no longer matches how much he
trusts the fleet, and asked for board-to-board sync and a trust-tier refresher.
Nothing here is applied. It's three separable decisions for a fresh read, not
one bundle to accept or reject together.

## 1. Autonomous merge

**Current state.** `fleet/config.json`'s `pipeline._what`: *"grok (or
FLEET_BUILDER) builds on rota/\* branches in worktrees, pytest runs, hermes (a
different vendor) reviews each diff, and the board lists what awaits a human
merge. Nothing merges itself."* This is deliberate, documented, and dates to
the same airlock philosophy as issue #18.

**What changed tonight.** Mars, in conversation: *"I'm not even reviewing
diffs — I trust you."* That's a real statement of intent, not a slip, and
`docs/TRUST-LAYERS.md` already has the vocabulary for it — this is a **layer 1
→ layer 0 authority question**, not a security question the fleet needs to
solve from scratch:

> "the score is published, not enforced. That is the next step, and it should
> land as 'layer 1 requires standing ≥ threshold,' never as 'the score says
> so, therefore obey.'"

**Proposed shape**, following that framework rather than inventing a new one:

- Gate merge eligibility on `fleet/bin/reputation.py`'s standing score
  (already computed, currently only published) crossing an explicit
  threshold — not on "an agent decided to."
- Scope it first: e.g. docs-only or test-only diffs auto-merge; anything
  touching `legacy/app/`, auth, or public endpoints still waits for a human,
  at least for the first month of operation. Widen once the gate has a track
  record.
- Keep every other guardrail pipeline already has: pytest must pass, hermes's
  cross-vendor review still runs and its verdict becomes a merge precondition
  rather than a display, `git diff --check` clean.
- Log every auto-merge to the event log at the layer that authorized it (this
  itself is new: nothing today distinguishes "a human merged this" from "the
  standing gate merged this" in the record).
- Keep a cheap kill switch: one config bool that drops back to
  human-required, independent of standing scores, for when something looks
  wrong.

**Explicitly not resolved here**: what threshold, which paths are excluded,
who's allowed to lower the threshold later (should probably itself require
layer 0). Those are Mars's calls, made awake, not mine at 2am.

## 2. Default orchestrator: Fable 5.1

Mars asked for Fable 5.1 as "the orchestrator" by default. There is currently
no single orchestrator role in the running code — the closest existing
concepts are council's participant list (`claude, hermes, grok, agy` per
`fleet/config.json`) and `FLEET_BUILDER` in pipeline. Before this can be
implemented as anything other than "add a name to a list," it needs one
decision: is "orchestrator" a new role (something that sequences/directs the
others, which doesn't exist yet — build it) or is it shorthand for "put Fable
5.1 in the seat that currently leads council/pipeline"? Flagging rather than
guessing, since the two are very different amounts of work and one invents an
architecture the fleet doesn't have yet.

## 3. Board-to-board direct sync

**Already built, currently wired to nothing.** `legacy/app/main.py` has a
complete multi-writer sync protocol: `/api/sync/pull`, `/api/sync/push`
(HMAC-signed per node, secret in `NODE_SECRETS` env, never on disk),
`/api/sync/conflicts` (conflicts are recorded and disclosed, never silently
dropped), `/api/sync/nodes`. `data/trusted_nodes.json` lists paired node ids
already. Nothing in `fleet/bin/*.py` calls `sync_push`/`sync_pull` on a
schedule — no cron/timer drives it — and per the 2026-08-06 security review
it isn't forwarded through the public funnel either.

**To activate:**
- Confirm which `trusted_nodes.json` entries actually correspond to nuc and
  Gaia (the current entries — `codex`, `codex-remote`, `mac-two`,
  `friendly-agent` — don't self-evidently map to either board; worth
  auditing regardless of this proposal, some may be stale).
- Add a scheduled job (new `fleet-sync` timer, same `pressure.py` load-gate
  the other timers use) that calls `sync_push` after writing local ops and
  `sync_pull` before reading board state, on both machines.
- Decide whether `/api/sync/*` should be forwarded through the funnel for
  this, or should only run over the tailnet (100.x addresses) — the latter
  is safer and doesn't need any funnel/Cloudflare decision at all, since both
  boards are already on the same tailnet.
- Because sync ops flow through the same event/board data council reads,
  every op arriving from another node is **layer 2 (DERIVED)** per
  `TRUST-LAYERS.md` law 3 — it doesn't get upgraded to layer 1 just because
  the node that sent it is FAMILY. Worth stating explicitly in the sync code
  itself, not just in this doc, so it doesn't quietly drift the way the
  hermes vendor table did.

## Housekeeping this proposal depends on

- `docs/TRUST-LAYERS.md` is the right foundation for §1 and §3 — no need to
  re-derive trust tiers, they already exist and are more thought-through than
  a first draft would be tonight.
- None of this is applied. No config changed, no code changed, no merge gate
  touched. This is the artifact from "write it up, don't decide at 2am."
