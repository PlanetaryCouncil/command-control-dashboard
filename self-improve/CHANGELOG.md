# Self-improvement cycle log

## 2026-08-04 — no changes

**Nothing was written to `claude/`.** Window: **548 session files scanned**, 14
days, 80 signatures. Almost all of them were already adjudicated in earlier
cycles. Two clusters were new and got a full proposal round; neither survived.
One real finding came out of it, but it is a `fleet/` config change, not a
CLAUDE.md rule — written to
`proposals/2026-08-04-fleet-spawn-permission-mode.md` for a human.

`user_corrections` had three entries, all three already adjudicated on
2026-08-03 (two are observer regex false positives; the third is the
full-width-bar correction whose lesson is already in `claude/CLAUDE.md`).

### Rejected: "a fleet turn cannot run python" (`13b47efe3c` +9)

`This command requires approval`, ×10 across 5 sessions — the strongest
signature in the window by distinct sessions, and the only new one that cleared
the numeric bar. The proposed CLAUDE.md paragraph died on its own counterfactual.

It claimed the agent *"gave up and shipped the proposal with an 80-block bar and
no box."* Re-measured directly from the transcript, `8a49e6e2` idx 75:

```
'╭────────────────────────────────────────────────╮' 50
'│ six hours of memory, three nights of branches. │' 50
'│ the fleet forgets faster than it files.        │' 50
'╰────────────────────────────────────────────────╯' 50
```

A correct box shipped, and the reply *said so*: "python3 and awk calls were
denied in this sandbox, so the branch list and timestamps come from `git branch`
and `grep`; the poem box below was measured by hand rather than by script."
`8908291e` idx 64 is the same story. Zero malformed boxes from all 8 "dead"
calls.

The other half — Python denied while inspecting JSON — recovered on the
**immediately next** call with a working `grep`/`cat` substitute, 6 for 6. One
wasted tool call on ~1–2 unattended sessions a day, against a paragraph loaded
by every session on this machine. That is the exact trade refused on 2026-08-01.

Two more things killed it. The rule gated on the prompt string *"You are one
agent in a small fleet"*, which appears in 5 of ~180 fleet sessions — but the
denials partition perfectly on `permissionMode=acceptEdits` + `promptSource=sdk`
(12 of 12 denied machine-wide; 31 `bypassPermissions` Python calls succeeded).
Wrong gate. And "a fleet turn cannot run python" is false about a project with
32 `.py` files whose own CLI (`python3 fleet/bin/pick.py`) the rule would have
talked the agent out of running.

### Rejected: `/tmp` scratch-script write denials (`3ae1f0c881`)

`Claude requested permissions to write to /tmp/poembox.py, but you haven't
granted it yet.` Two real occurrences, not four — the other two machine-wide
hits are this cycle's own orchestrator. The obvious fix (inline heredoc instead
of `Write` to `/tmp`) is falsified: the heredoc is what the agent tried *first*
and it was denied first, both times. The constraint is code execution, not the
path. Root cause already removed by commit `55ee42f3` (2026-08-03 13:17), which
exempts rota and council turns from the poem entirely — zero recurrence in the
12 fleet sessions since.

### Escalated, not applied

`proposals/2026-08-04-fleet-spawn-permission-mode.md`. `fleet/bin/chat.py:181`
spawns with `acceptEdits`; `fleet/bin/blackboard.py:47` spawns with
`bypassPermissions`. Only the first is denied. 20 of 73 Bash results in that
project dir are errors. The fix is a permission-mode or allowlist change, both
off-limits to this loop, and the measured cost is one tool call — so it is
framed as "here is the mechanism, your call", including the option of doing
nothing.

### What would justify action next cycle

- A fleet turn that **fails outright** rather than substituting on the next
  call — the 6-for-6 recovery rate is what makes the papercut unwritable.
- Any signature appearing in **two projects** that is not the compound-probe
  shape already rejected four times.
- A `user_corrections` entry that is a real correction and is *not* already
  answered by `claude/CLAUDE.md` — that file absorbed three of them in the last
  week, which is why the loop keeps finding nothing left to add.
- The observer still hashes one recurring moment into many `count:1`
  signatures (eight variants of "multiple operations" this window). The
  2026-08-01 proposal on signature hygiene is still unmerged.

## 2026-07-31 — no changes

**Nothing was committed to `claude/`.** Window: **185 session files scanned**
(up from 89), 14 days. Of 38 signatures, **32 were already rejected in prior
cycles** — including every browser signature, still confined to the one session
`cf7cee31` after 2× more sessions were scanned. `user_corrections` is empty for
the fourth consecutive cycle.

Exactly **one** signature was new *and* cleared the numeric bar
(`distinct_sessions >= 2` and `distinct_projects >= 2`). It got a full
proposal round and did not survive.

### Examined and rejected (now in `rejected.jsonl`)

**Read-before-Write** (`8b516d33f6`, ×2): `File has not been read yet. Read it
first before writing to it.` The numbers dissolve on inspection — the second
"project" is `/private/tmp/claude-505/-Users-phil/f271523b-…/scratchpad/cheatdemo`,
a fleet worker spawned *by* the first session. One lineage, not two; the `2` is
an artifact of the tmp-dir naming scheme.

Both occurrences recovered on the very next turn (Read → Write) at 2 tool calls
each. 88 of 90 Writes in the window did not hit it. Zero wrong outcomes.

The decisive point is that **the harness block produced a better result than
compliance would have.** In session `f271523b` the blind first Write to
`README.md` opened with a condensed line and silently dropped the repo's
load-bearing commitment; after the forced Read, the successful Write restored it
verbatim:

> **No credentials, tokens, cookies, or API keys ever go in `data/`.**

A rule that made blind overwriting smoother would have *cost* something here.
The instruction also already exists three times over — in the Write tool
description, in the error text, and in the mechanical gate — and any rule shaped
"Read before Write" fires on every new-file creation and generated artifact,
which is most Writes.

### A phantom worth naming

Three further transcripts match the error string. A naive `grep` reads them as
corroboration — 5 occurrences, 3 projects, clears any bar. **All three contain
zero real occurrences.** They are self-improve cycle sessions that *read
`observations.json`*, which contains the sample text. The loop greps its own
exhaust and finds itself.

`observe.py` was not fooled — it counts only `is_error` tool results, so it
reported 2, correctly. But the near-miss is the warning: this loop reads
transcripts of itself (`a68280a038`, a denied `git rm` from the 2026-07-29
cycle, is already in this window's evidence as a real signature). No change
recommended yet — the miner is behaving. Flagging it so a future cycle that sees
a suspiciously strong cluster checks whether it wrote the evidence itself.

### What would justify action next cycle

- A signature appearing in **two genuinely unrelated projects** — check the
  project paths for an embedded parent session id before trusting the count.
- Any entry in `user_corrections`. Still empty across four windows; it remains
  the highest-signal field in the file and the one most likely to justify a rule.
- A failure with a **wrong outcome** rather than a retry. Every signature
  rejected so far cost tool calls and nothing else.

## 2026-07-30 — no changes

**Nothing was committed to `claude/`.** No proposal round was run, because no
cluster cleared the evidence bar and manufacturing one to grade would be the
loop spinning in place. Window: **89 session files scanned** (up from 32), 14
days. **Every signature is `single_session_only: true`; not one has
`distinct_sessions >= 2` or `distinct_projects >= 2`.** `user_corrections` is
empty for the third consecutive cycle.

Of ~24 error signatures, **16 were already rejected in prior cycles** with
transcript-verified reasons, including all three of the largest (`ebcddcaded` ×4,
`f05eda3928` ×2, `963514b658` ×2 — Claude_Browser, still confined to session
`cf7cee31`). Nearly 3× more sessions were scanned this window without them
reappearing anywhere, which strengthens those refutations. Off the table.

`observe.py` now carries the `distinct_sessions` / `single_session_only` ranking
recommended last cycle — applied by a human, as intended. It did its job here:
the flag is what made the singleton noise legible at a glance.

### Examined and rejected (now in `rejected.jsonl`)

**Compound Bash probe exit codes** (14 signatures: `b99ce97c07`, `a1b11f72f4`,
`2fd768ff1d`, `40b6357acc`, `c0e05d94d6`, `770c1ab5b4`, `f6ff1c9225`,
`25dd293f76`, `b2967377ae`, `87d249c10c`, `94a5f9bf71`, `422abd359d`,
`e99640f3bd`, `a7d22d2769`). This was the real candidate — the one shape this
window spanning **both ≥2 sessions and ≥2 projects**, and it escapes the
`single_session_only` flag precisely because it is spread across many distinct
signatures. Shared shape: the agent batches independent probes into one Bash
call with `echo === section ===` separators, and a sub-probe whose failure *is*
the informative answer (an `ls`/`cat` on a file that should be absent) marks the
entire call `is_error=true`.

Pulling transcript `cf7cee31` dissolved it. At idx 922 the agent read the exit-1
and wrote: *"the `ls` exit code 1 is expected — the files correctly don't
exist."* At idx 1175, on an identical exit-1: *"76 passed, zero leaks."* Real
failures inside the same idiom (idx 1156, six pytest failures) were diagnosed
correctly on the very next call. No retries, no wrong conclusions, no user
complaint. **The agent was never misled — so there is no failure to prevent.**

Worse, the natural rule ("append `|| true`, or separate probes so an expected
absence doesn't fail the call") would train every future session to mask Bash
exit codes, suppressing genuine failures. Misfire cost vastly exceeds a cosmetic
exit code the agent already reads correctly.

**Model-unavailable errors** (`c22ef9b571`, `9adea048da`). Transient upstream
infrastructure. The error text already ships better remediation than any rule we
could write ("Wait briefly and then try again… continue with other tasks").

### Recommended to the human (not applied)

`observe.py` treats `is_error=true` as friction. Two classes of confirmed
non-failure keep consuming the evidence budget:

1. **Compound-probe exit codes** — the cluster above. 14 of ~24 signatures this
   cycle are calls the agent handled correctly.
2. **`AskUserQuestion` free-form answers** — the denial regex at `observe.py:155`
   matches `user doesn't want`, so a user typing an answer instead of clicking an
   option is logged as a permission denial. This is why `b5f92cc875` (×3)
   resurfaces as a top denial despite being rejected last cycle as not-friction.

Both are suppression changes to the miner that grades this loop's own cycles, so
they are recorded here rather than applied unilaterally — same protocol as last
cycle's `distinct_sessions` recommendation, which worked.

### What would justify action next cycle

- Any signature with `distinct_sessions >= 2` **or** `distinct_projects >= 2`
  that is not one of the 18 now in `rejected.jsonl`.
- Any entry in `user_corrections` — still empty across 89 sessions and 14 days.
  This is the single most valuable missing signal: it is the only channel that
  reports friction the agent did *not* silently absorb.
- A retry storm: ≥3 consecutive failing calls on one goal. None has occurred in
  three cycles of scanning.
- Evidence that a *masked* failure cost something — i.e. a compound Bash probe
  where the agent read a real error as expected-absence and proceeded wrongly.
  That would flip the rejected cluster above into a genuine finding.

## 2026-07-29 — no changes

**Nothing was committed to `claude/`.** No proposal was written, because no
evidence cluster cleared the bar. Scope of the window: 32 session files scanned,
but **all 40 error results come from just 5 sessions — one per project — and
every single signature is `single_session_only: true`.** Not one signature
recurs across two sessions or two projects.

The three largest clusters (`ebcddcaded` ×4, `f05eda3928` ×2, `963514b658` ×2 —
all Claude_Browser) are the ones rejected last cycle, still confined to the same
one session (`cf7cee31`, command-control-dashboard). Ten times more sessions
were scanned this window and they did not reappear anywhere, which strengthens
last cycle's refutation rather than weakening it. Off the table.

### Examined and rejected (now in `rejected.jsonl`)

**Bash 2-minute timeouts** (`e204db05ec`, `eadb694516`, `1f268d044e`, plus the
blocked `sleep`-then-`cat`, `4370b0f779`). This is the one cluster that looked
real, because three *distinct* signatures share a symptom and so escaped the
`single_session_only` flag on any one of them. Pulling the actual commands
dissolved it: all three are the same session (`f271523b`), with three unrelated
causes — a `grep -oiE` with unanchored `.{0,45}` context over minified JSON, a
hand-rolled 90s watchdog subshell whose `kill -9` never reached the child, and a
`curl` poll against a local server on `127.0.0.1:8796` that hung. No one rule
prevents all three; each is a separate authoring slip. The blocked `sleep`
already prints its own remedy ("use Monitor with an until-loop") and the agent
complied on the next call.

**AskUserQuestion "denials"** (`b5f92cc875` ×2, `3308ac8d23`, `4af178be50`).
Not friction at all. Every one is the user taking the free-form answer path on an
open-ended question ("Now that they're one system — what next?"). That is the
supported path; it only reads as a denial because `observe.py`'s denial regex
matches the string "user doesn't want". `4af178be50` is an infrastructure
`AbortError`, not a user decision.

### Note on the miner

Last cycle's recommendation was implemented — `pack()` now emits
`distinct_sessions` / `single_session_only` and ranks on sessions, and that flag
did most of the triage work here. Its one blind spot showed up in the timeout
cluster: signatures are hashed per error string, so a symptom spread across
several signatures shows no per-signature recurrence even when it repeats. Worth
noting, **not worth fixing yet** — inspection showed the recurrence was spurious,
so grouping those signatures would have manufactured a false pattern, not caught
a real one. Revisit only if a symptom-level cluster ever spans two sessions.

### What would justify action next cycle

- Any signature with `distinct_sessions >= 2`. None exists today.
- Any entry in `user_corrections` — still empty across the full 14-day window,
  now over 32 sessions rather than 3.
- A browser signature from a second project, which would finally make the
  command-control-dashboard cluster a protocol property rather than one page's.
- Friction in a session that ends *badly* — the miner records errors but not
  whether the task succeeded, so a recovered error and an abandoned one weigh
  the same. That, not more error volume, is the missing signal.

## 2026-07-28 — no changes

**Nothing was committed to `claude/`.** Two proposals were generated from the two
strongest evidence clusters; both were refuted, and both refutations were
independently verified by re-reading the raw transcript.

### Rejected

**`claude-browser-protocol` skill** — Claude_Browser MCP preconditions
(`f05eda3928` ×2, plus five ×1 signatures).
The proposal's mechanism was false. It claimed the screenshot precondition for
`computer{scroll, coordinate}` is "per-tab and re-arms on a new or switched tab."
In the transcript, *both* failures happened on tabs that had just been
screenshotted, with no tab switch — tab-1 with an intervening `resize_window`,
tab-2 with an intervening `navigate` + `javascript_exec`. The rule predicts
success in both cases it was built to prevent, so it would have taught future
sessions to read a real error as a server bug. Two other rows were contradicted
by successful calls in the same window (`tabs_create` worked without
`preview_start` 2 of 3 times; `preview_stop` worked on a carried `serverId`
without `preview_list`).

**`browser-pane-stuck` skill** — 30s pane-hang recovery ladder
(`ebcddcaded` ×4, `963514b658` ×2, `f20a9cbaa8` ×1).
Its premise — "the pane is the failure point, not the API," budget one call
after a timeout — is contradicted by trace 1, where `get_page_text` and
`javascript_tool` both succeeded on the same tab right after a `computer{scroll}`
timeout. The rule would have pushed the agent out of a browser that was working.
Its "screenshot is the worst post-timeout call" rule would also train toward
`f05eda3928`, which *requires* a screenshot before a coordinate scroll. Misfire
cost (shipping an unverified UI change) exceeds the author's own stated ceiling
of ~60s of wall-clock per session.

Common to both: every browser error string ships its own remediation, and the
agent self-corrected on the very next call in 6 of 6 protocol errors, with no
retry storm and no user complaint (`user_corrections` is empty).

### Finding about the evidence pipeline itself

`observations.json` reports `sessions_scanned: 3`, but **every browser signature
in it comes from a single session file** (`cf7cee31…`). Counts of 2 are two
moments in one continuous conversation, not two independent recurrences, and
`observe.py` currently emits clusters at `min_count=1` with no per-session
breakdown — so the report reads as much stronger evidence than it is. This is the
main reason both proposals looked plausible before verification.

Recommended (not done unilaterally — an unattended loop should not rewrite the
evidence miner that grades its own future cycles): add `sessions` /
`distinct_sessions` alongside `count` in `observe.py`'s `pack()`, and rank by
distinct sessions rather than raw count.

### What would justify action next cycle

- The same browser signature from **a second project or session** — that would
  make it a protocol property rather than one page's behavior.
- A **retry storm**: ≥3 consecutive failing calls on the same goal after a
  timeout. None occurred here; recovery was already adequate in 4 of 6 traces.
- Any entry in `user_corrections`, which is currently empty across the window.
- For the coordinate-scroll error specifically: evidence that arming is
  invalidated by an intervening `navigate`/`resize_window` (the pattern both
  failures actually fit). n=2 in one session is too thin to write down, and the
  narrow rule would be "screenshot *immediately* before a coordinate op" — not
  what was proposed.
