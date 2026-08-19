# Straight Handoff

*Updated 2026-08-05. **The code is the source of truth** — where this and the
repo disagree, the repo is right.* Read `README.md` first for what the system
is; this file is only what the code cannot say.

This document went four days stale once (six jobs listed while twelve ran).
If you change what runs, change this in the same commit or delete the line.

---

## Where things are

| repo | remote | holds |
|---|---|---|
| `~/projects/command-control-dashboard` | `PlanetaryCouncil/command-control-dashboard` | the cockpit, the fleet, the self-improve loop |
| `~/projects/11c` | `PlanetaryCouncil/11c-of-consent` | consent framework, BaseX doctrine, PlanetaryCouncil vision |
| `~/projects/ai-brain-farts` | `PlanetaryCouncil/brainfarts` | logged cases of confidently-wrong AI output |
| `~/projects/poems` | `PlanetaryCouncil/poems` | the closing two-liners, live at poems.planetarycouncil.org |
| `~/projects/seeing` | — | image dissector, a service on :8791 |
| `~/projects/freezer` | — | ideas parked, with the state needed to resume |

The dashboard remote is **`GitHub_priv`**, not `origin`; the
PlanetaryCouncil repos use `origin`. Run `bash ~/.claude/pushed.sh <repo>`
for a receipt rather than trusting a push's own output.

**Private state deliberately outside the repo** (`~/.config/fleet/`):
`homies.txt` (home IP prefixes — a location fingerprint), and
`signatures-collected.jsonl` (raw pointer paths). Overridden by
`$FLEET_HOMIES` and `$FLEET_SIGNATURES`, both set in the fleet-server
plist.

---

## What runs

Twelve launchd jobs, most configured from `fleet/config.json` — edit it, then
`bash fleet/bin/apply-config.sh`. Only changed jobs reload.

```
  fleet-server    always on     the board at :8787 — and the legacy cockpit
                                boots INSIDE it as a thread on :8770
  ollama          always on     local model, kept for the offline case only
  dissector       always on     ~/projects/seeing on :8791, a registered tool
  board-medic     every 5m      probes :8787, load-gated, 30m cooldown
  watchdogs       hourly        project test suites
  rota            hourly        one agent proposes, in rotation
  pipeline        hourly        builds ONLY what a human picked (see below)
  council         every 3h      claude, hermes, openclaw
  heartbeat       daily         relay check
  self-improve    daily 03:00   mines transcripts, proposes on a branch
  local-voice     daily 06:15   one question to the local model, so the
                                offline fallback is known-good
  e2e             daily 05:30   canary checks; its kill test now shoots a
                                sacrificial canary, not the live fleet
```

**Reload code with `bash fleet/bin/reload.sh`, never a bare kickstart.** It
compiles with the server's own interpreter and boots the new code on a
scratch port before touching the live one. A 3.14-only f-string once black-
ed out the board because those two checks did not exist.

Plus a `githooks/post-merge` hook running `e2e --quick` on every merge.

**Rules that hold everywhere:** agents propose on branches and never merge;
`main` is what a human approved; the fix proposer may not edit tests and this
is checked mechanically; the self-improve loop cannot write hooks.

---

## The dashboard

`http://127.0.0.1:8787` — the board. Public through Tailscale Funnel at
**https://[redacted-host]/**. Nav: fleet, intro, send a message,
chat. `/signatures`, `/art`, `/orbit`, `/board`, `/agents`, `/live`, `/procs`
resolve but are not all in the nav.

**Reads are public; control is local.** `CONTROL_PATHS` in `fleet.py`
(`/terminal`, `/chat`, `/api/kill`, …) answer **404** — not 403 — to any
caller carrying `X-Forwarded-For`, which tailscaled sets on every funnelled
request. Verified both directions; 52 probes for `/terminal` in one day all
got "no such thing".

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
2. ~~**Should OpenClaw join the council?**~~ **Answered 2026-08-05: yes.**
   Three vendors deliberate now — claude, hermes, openclaw. Cross-vendor is
   the point: the agent that verifies a build is never the one that wrote it.
3. ~~**Public exposure.**~~ **Answered 2026-08-05: it is public.** Funnelled,
   read-only, with the guest book, the porch and the signature wall built for
   exactly the strangers who can now reach it. The repo went public the same
   day after a full secret sweep and a squashed history.
4. **Still open — where does the fleet run when this laptop sleeps?** The
   dappnode (16GB, on the LAN) is the candidate. See the freezer.

---

## Browser automation — where it actually stands

**Updated 2026-08-05: `fleet/bin/browser.py` is now the fleet's own driver**
(CDP over stdlib, ~230 lines, readable in one sitting). `browser.py check` /
`open` / `text` / `shot` / `tabs`. On any of 16 `HUMAN_CHECK` markers it
screenshots, raises `needs_you` on the board, fires a desktop notification
and **stops** — the tab is already open in front of Marsita. It does not
solve checks and will not be made to; see the `lines-i-hold` memory.

**The profile question is still open and it is Marsita's call.** Chrome ≥136
refuses `--remote-debugging-port` on the default profile, so driving their
*real* logged-in browser means either copying the profile directory or
logging into a fresh one by hand. Also: a debugging port lets any local
process drive that browser. Stated plainly, deferred deliberately, not
forgotten. Marsita also asked for a **hybrid** — CDP for sight, native
pointer events for hands, since a debugging port is detectable.

Below is the older hermes path, still true, kept because it works:

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

## The pipeline — how a proposal becomes a merge

`fleet/bin/pipeline.py`, hourly. Four steps, and the ordering matters:

```
  triage   writes rota/triage.md and rings needs_you — a HUMAN picks
  pick     _picked_items() reads only what was picked
  build    one agent per item, in its own git worktree
  verify   a DIFFERENT vendor merges main FIRST, then tests
  revise   exactly one round, then it stops
```

**Only a human picks.** This exists because on 2026-08-05 triage cut 27
proposals to 8 and the builder then built 20 branches — it was consuming
proposals rather than picked items. `_picked_items()` parses `# N. title`
headings and owns the timestamps under each. If that function is ever
loosened, the fleet starts working on things nobody chose.

**`verify` runs `git merge --no-edit main` before the tests**, and a conflict
is a rejection. Verifying a branch against stale main proves nothing.

Guards: `MAX_LOAD = 6.0`, `MAX_PER_CYCLE = 12`, `flock` so cycles cannot
overlap. **Every fleet job needs a load gate.** `board-medic.sh` was the one
without and it kickstarted a starved server in a loop — load 189, twenty
minutes of blackout, logged as a brainfart. It now has a gate at 8.0, a 120s
grace, a 30-minute cooldown and 3×20s probes before it acts.

---

## Signatures — the entropy project

Marsita: *"I want to collect entropy as signature. And see how humans /
agents sign their work. This is an artistic project in itself."*

Anyone writing to the board signs. Not optional — an optional field is a
decision tax on every user, and half-signed data is not a collection.

- **Capture** — pointer path in the compose box and on `/hi`, the porch.
- **Score** — `hand_entropy()` in `legacy/app/main.py`: timing CV, stride CV,
  direction flips. A real hand is irregular; a script is not. High entropy is
  a **fast lane**, low entropy is **moderation purgatory** — never a hard
  reject, because the cost of refusing a real person is worse than a queue.
- **Override** — `/api/signals/{id}/override` needs **2n+1** agreement.
  Marsita's spec: *"to make override more expensive."*
- **Store** — signals keep the path downsampled to 400 points. The **raw**
  paths go to `~/.config/fleet/signatures-collected.jsonl`, outside the repo:
  a movement trace is closer to biometrics than to art.
- **Render** — `fleet/static/signature.js`, drawn inline next to each message
  at 110×26, transparent, no background of its own.

**The rendering bugs, so they are not rediscovered:** sizing the canvas inside
`pointermove` wipes the stroke mid-gesture; `clearRect` does not touch the
backing store (assigning `canvas.width` does); using x/width but y/height for
normalisation bakes the pad's aspect into stored data; and magnifying a flat
stroke to fill a box makes it a smear. The fit is aspect-preserving with a
cap — `S = Math.min(fit, W)` — so a signature is never magnified past
frame-width. And `.js` is served `no-store`: a day-long cache meant every fix
was invisible for a day.

---

## The porch, the guest book, and who is watching

- **`/hi`** (`fleet/bin/hiview.py`) — name\*, i am\* (human / AI / alien /
  nature / non-binary), message\*, signature\*, and a "not [illegal
  content]"\* checkbox whose link opens a modal so a half-written message
  survives being read. Every field required.
- **The guest book** (`fleet/bin/visitors.py`) — records funnelled requests
  only, via the server's `log_request` hook. `_is_homie()` reads prefixes
  from `$FLEET_HOMIES`. Bots and crawlers show up here; this is how Venus
  found the board and left a note.
- **Guests are a filter, not a column** — a 👋 pill on the stream matching
  `[signals]|[signatures]|[visitors]|[charge]`.

---

## Tools as services

Marsita: *"I can connect new tools through api, my dashboard will become my
home."* A tool is its own process on its own port, registered at
`/api/tools`. First one: the image dissector, `~/projects/seeing` on **:8791**
— it teaches artists how a model sees a picture. Add tools this way; do not
grow `fleet.py`.

---

## Known gaps

- **Chat exchanges are not persisted anywhere.** Found 2026-08-05 when
  Marsita asked whether an agent had used the word "entropy" unprompted and
  there was no way to check. Council turns land in `events.jsonl`; the chat
  does not. This is the gap most worth closing — it is the fleet's memory of
  what it actually said.
- **The stream collapses client-side only.** `events.jsonl` keeps every line and
  each page load redoes the work.
- **~1,900 lines of history use retired vocabulary** — `[plus-one]`,
  `agent-comms-full`. A one-time rewrite would make the scrollback consistent.
- **`fleet` posts most lines but is not an agent** — it is the channel itself.
  Dimming it would let the real agents stand out. Raised three times, never done.
- **No always-on host.** Everything assumes this machine is awake. The
  dappnode is the standing candidate; SSH username unresolved (`dappnode@`
  was refused). Host key already trusted:
  `SHA256:YWXhgLWZu6JNQ8PHtVGSkFZR4YEQrSIYaIwQwrVZ8Uw`.
- **Nostr is built and unarmed.** `fleet/bin/nostr.py` signs NIP-01 events to
  five relays; the key must be placed by Marsita's own hand at
  `~/.config/fleet/nostr.nsec`. A private key must never pass through a
  session transcript — that is why this step is theirs and stays theirs.
- **`fleet/static/*` was gitignored wholesale** and twice shipped dangling
  image references. Check what is actually tracked before claiming a page
  renders for anyone but you.
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
