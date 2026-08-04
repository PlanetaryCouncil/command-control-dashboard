# Straight Handoff

*Updated 2026-08-01. **The code is the source of truth** — where this and the
repo disagree, the repo is right.* Read `README.md` first for what the system
is; this file is only what the code cannot say.

---

## Where things are

| repo | remote | holds |
|---|---|---|
| `~/projects/command-control-dashboard` | `marsrobertson/command-control-dashboard` | the cockpit, the fleet, the self-improve loop |
| `~/projects/11c` | `PlanetaryCouncil/11c-of-consent` | consent framework, BaseX doctrine, PlanetaryCouncil vision |
| `~/projects/ai-brain-farts` | `PlanetaryCouncil/brainfarts` | 9 logged cases of confidently-wrong AI output |

All private, all pushed, nothing uncommitted. The remote is called
**`GitHub_priv`**, not `origin`.

---

## What runs

Six launchd jobs, all configured from `fleet/config.json` — edit it, then
`bash fleet/bin/apply-config.sh`. Only changed jobs reload.

```
  fleet-server    always on     the dashboard at :8787
  heartbeat       every 30m     relay check, all three agents
  watchdogs       hourly        runs the test suite, proposes a fix if red
  council         every 3h      two agents propose workflow improvements
  e2e             daily 05:30   canary checks against live infrastructure
  self-improve    daily 03:00   mines transcripts, proposes on a branch
```

Plus a `githooks/post-merge` hook running `e2e --quick` on every merge.

**Rules that hold everywhere:** agents propose on branches and never merge;
`main` is what a human approved; the fix proposer may not edit tests and this
is checked mechanically; the self-improve loop cannot write hooks.

---

## The dashboard

`http://127.0.0.1:8787` — one page. Nav is two items: **dashboard**, **chat**.
`/terminal`, `/board`, `/agents`, `/live`, `/procs` still resolve but are not
in the nav.

Three columns, **draggable dividers, widths persisted in localStorage**,
double-click a divider to reset. Terminal is a drawer, closed by default, and
neither xterm nor its socket load until opened.

Design rules learned the hard way, all in Marsita's words:

- **No text below 10px.** The monitor is 27" at 1920x1080 — 82 pixels per inch,
  where a glyph stroke is already one pixel.
- **Values render as meters, not numbers.** ~100px bars; the number stays in
  the tooltip.
- **Density comes from cutting chrome, never from shrinking type.**
- Every agent and every category has an emoji.
- ISO date appears once, on the line where the day turns over.
- Council turns are highlighted: the only lines an agent actually composed.

---

## The council, and why it matters

`fleet/bin/council.py`. Agents take turns reading the same board and saying one
grounded thing that would improve the fleet. No task list — they decide. Two
consecutive passes adjourns it.

**Its findings have been real.** In three sessions it produced eight faults,
all since fixed, including two bugs written hours earlier that same day:

- relays overlapping so an agent held two values from games it could not tell apart
- `last_run` start-stamped for watchdogs and finish-stamped for heartbeats,
  making the staleness check invalid
- a worker reading `pass` while 75 minutes stale — *"a silent worker looks
  identical to a healthy one"*
- its own transcript not being scoped, so it was handed already-solved problems

Nobody has yet answered NOTHING TO ADD. Watch whether the transcript fix lets it
adjourn, or whether the stop condition needs teeth.

---

## Open questions

1. ~~**Approval gate: how long is a grant good for?**~~ **Answered 2026-08-01:
   until revoked.** Built in `dcea608` — approve, revoke, check. Scope is
   mandatory (422 on blank) and matching is exact, no wildcards, because with no
   clock the scope is the only bound a grant has. `check` fails closed on blank,
   unknown, pending and revoked alike. **Nothing has been granted yet** — both
   `apr-001` and `apr-002` are still pending, deliberately.
2. **Should OpenClaw join the council?** It is in the heartbeat but never
   deliberates.
3. **Public exposure.** Everything is localhost. The airlock, the rate limiter
   and the signals queue exist for strangers who cannot yet reach them.

---

## Browser automation — where it actually stands

**Hermes is the runner.** It was already built and nobody had connected it.
`~/.hermes/config.yaml` has `engine: cdp`, `cdp_url: http://127.0.0.1:9222`,
`dialog_policy: must_respond`, `dialog_timeout_s: 300`, and a tool surface of
`browser_navigate / snapshot / click / type / scroll / press / console / vision`
plus raw CDP passthrough and a dialog supervisor. Not Claude — no persistent
session. Not OpenClaw — the browser stack lives in hermes.

**Captchas are already designed to come to Marsita.** `browser_vision` exists
explicitly for them, returns a `screenshot_path` shareable as `MEDIA:<path>`, and
a detector matches `"are you a robot"`, `"cloudflare"`, `"just a moment"`,
`"checking your browser"`. Nothing tries to solve them. That is the intent —
**feed captchas to the human, never solve them.**

**Profile:** `~/.browser-automation`, a dedicated `--user-data-dir`. Chrome
refuses `--remote-debugging-port` on the *standard* user-data-dir, so a Chrome
profile named in the normal profile picker cannot be driven — a separate dir is
required. Relaunch with:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 --user-data-dir="$HOME/.browser-automation" \
  --no-first-run --no-default-browser-check &
```

**Proven end to end on 2026-08-01:** navigate → evaluate → screenshot, over raw
CDP, screenshot read back. Verified on Chrome 150, protocol 1.3.

**The one blocker: the profile is not logged in.** `drive.google.com` redirects
to the marketing page. Someone has to sign in once, by hand, in that window.
After that `bq-001` can run for real — Drive folder tree, links returned,
screenshot as evidence, `boundaries: create folders only`.

Tinder came up as a target. Two things worth keeping: automation is what Tinder
bans hardest, so the likely outcome is a dead account rather than a runner; and
messaging as Marsita is a conversation with someone who does not know they are
talking to a machine. Swiping is Marsita's call. Messaging should not be built.

---

## Known gaps

- **`browser-automation-cockpit` scores `blocker_severity: 2` and its blocker is
  gone** — it read "No approval gate implemented yet", which shipped in
  `dcea608`. A stale blocker distorts exactly the ranking the radar exists for.
- **The stream collapses client-side only.** `events.jsonl` keeps every line and
  each page load redoes the work.
- **~1,900 lines of history use retired vocabulary** — `[plus-one]`,
  `agent-comms-full`. A one-time rewrite would make the scrollback consistent.
- **`fleet` posts most lines but is not an agent** — it is the channel itself.
  Dimming it would let the real agents stand out. Raised three times, never done.
- **No always-on host.** Everything assumes this machine is awake.
- **Hardware is the binding constraint.** Four cores, 8GB. An agent turn costs
  20-100s and a core; four at once produced load 15 and 300s timeouts. Local
  vision models were tried and abandoned.

---

## How to work with Marsita

- **Format: `## CONTEXT`, `## WHAT I DID`, `## ACTION`, `## SUGGESTIONS`.** Wrap
  at 80 columns. Never write "ACTION: none". WHAT I DID is my completed work and
  is skippable; ACTION is the sentence addressed to them. Keeping both under one
  heading buries the part they need.
- **Start every visible thinking block with the word `THINKING`.**
- **Open every reply with exactly 80 solid full blocks** — `█`, U+2588, bare on
  its own line, no code fence. Not `━`, not `─`, not any box-drawing line: those
  are strokes, and this is meant to be a bar of light. "Heavy rule" used to be
  the wording here and it was read as `━` for a whole session.
- **Emit that bar before any tool call, not after.** It is a scroll landmark —
  Marsita uses it to find where their own last message ended. Tool output
  rendered above it buries the thing it marks.
- **Close with a framed, indented poem — one or two lines.** It signals the turn
  is over. *Framed* means box characters on all four sides (`╭─╮│╰╯`), indented;
  indentation alone is not a frame. Build the box with a script that asserts
  every row is the same width — hand-padding produced two off-by-ones. Length has
  drifted upward twice and been corrected twice: it is a full stop, not an essay.
- **Decide ordinary things yourself**, say why in a line, and act. Only ask on
  real forks — except where asking first avoids priming.
- **Push by default, then paste the receipt.** `bash ~/.claude/pushed.sh <repo>`
  prints it: ✅ PUSHED, the repo, a **link to the commit on GitHub**, the commit
  **message**, and the **live URL** from `CNAME`. Three links so Marsita can
  verify without asking. It fetches and compares hashes rather than trusting push
  output, and prints ⚠️ NOT PUSHED when that is the truth. Saying "it's live" or
  "done" is not the same claim — Marsita has had to ask twice.
- **Spell out every acronym on first use.**
- **They are Marsita.** `phil` is only the macOS username.
- **Never invent a duration.** Read a clock or describe the shape of the work.
- They think fast and visually. Show the rendered thing. Start small.
- **They catch what I cannot see.** Every layout bug this session came from
  their screenshots. When they say something looks wrong, it is.
