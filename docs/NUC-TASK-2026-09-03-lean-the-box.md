# NUC task: lean the box, then give GrokBot a login

**Written on Gaia 2026-09-03 for a Claude running *on the NUC*.** Gaia could
diagnose this over ssh but not change it — the auto-mode classifier blocks
remote systemd writes. Run these locally.

## What is wrong

`llama-server` burned **6d 05h of CPU in 25h wall clock** — about 6 of 12
cores pegged continuously, 8 GB RSS, box 3 GB into swap on a 14 GB machine.

It is not idle. It is being hammered by the fleet's own builders:

```
fleet-build@agy.timer      OnUnitInactiveSec=30s
fleet-build@claude.timer   OnUnitInactiveSec=30s
fleet-build@grok.timer     OnUnitInactiveSec=30s
```

Three builder instances, each running `backlog.sh`, which runs *both*
`autotriage.py` and `pipeline.py run` — six concurrent `hermes -z` calls into
ollama. Generation is `5.18 t/s` on CPU, so a slot never finishes inside its
30-second gap. It stacks, the box swaps, it gets slower, it stacks harder.

`backlog.sh` says `# One 15-minute builder slot`. It is getting 30 seconds.

**This is also why the pipeline has built nothing since 2026-09-01T10:36.** It
is not dead. It is queued behind itself.

## What Marsita decided

- No GPU on this box, so no always-on local inference. **Kill ollama as a
  service.**
- Keep it installed. Bring it up **once a day** so hermes can act as the
  on-device guardian — fact-checking, self-improvement. hermes is good at
  self-improving and llama is free; that pairing is worth one slot a day.
- Give **GrokBot** a lean login. Browsing the web as Marsita, from the home
  IP rather than a datacenter. **No sudo.** No VM needed — the VM plan was
  only ever about RAM, and killing ollama returns 8 GB.

## Step 1 — stop the loop

```
systemctl --user disable --now fleet-build@agy.timer fleet-build@claude.timer fleet-build@grok.timer
```

Then confirm no `hermes -z` survives, and that load falls below 1.

## Step 2 — ollama off always-on

```
sudo systemctl disable --now ollama
```

Keep the binary and the models. Only the always-on unit goes.

## Step 3 — the daily guardian slot

One unit + timer, once a day, that:

1. `systemctl start ollama`, waits for `127.0.0.1:11434` to answer
2. runs the hermes guardian pass (fact-check + self-improvement)
3. `systemctl stop ollama` in an `ExecStopPost`/`trap`, **unconditionally** —
   the whole point is that it does not stay up

Give it a hard `TimeoutStartSec` well under a day. The failure that caused all
this was an unbounded job on a re-firing timer; do not rebuild that shape.

`~/.hermes/config.yaml` already points at `http://127.0.0.1:11434/v1` with
`default: llama3.2:3b` and no cloud key, so hermes works inside the slot and
fails fast outside it. That fast failure is desirable — a job that dies in a
second cannot stack.

## Step 4 — fix the builder cadence before re-enabling it

Do **not** just re-enable the three timers. Whatever cadence is chosen, the
units need:

- a gap that matches the real duration of a slot, not 30 seconds
- a `TimeoutStartSec` that is smaller than the gap between fires
- ideally one builder at a time, not three instances racing

`TimeoutStartSec=14400` (4 hours) on a job re-fired every 30 seconds is the
bug in one line.

## Step 5 — GrokBot's login

**Decided 2026-09-04.** GrokBot is an agent living in a datacenter. It needs to
browse from Marsita's home IP rather than a datacenter range, driving a real
Chrome it can see and click. So: a real desktop login on this box.

Marsita weighed the residential-reputation cost and accepted it: *"I'm going to
use bots one way or another so may as well use it."* That decision is made; do
not re-litigate it.

### Shape

- user `grokbot`, **no sudo**, in no group that `m` is in
- home mode `0750` — `m`'s files are not readable from it and vice versa
- XFCE session, Chrome, reachable over RustDesk like James's account
- **GDM on Ubuntu 26.04 is Wayland-only** and ignores both
  `WaylandEnable=false` and the AccountsService `XSession` key. Use lightdm.
  James's account is the working reference; copy it, minus sudo.
- a **fresh Chrome profile**, no sync, never signed into any of Marsita's
  accounts. The IP is shared. Nothing else is.

### The line that holds

GrokBot browsing the web on Marsita's behalf, from her line, is fine. Turning
the box into an exit node for other people's traffic is not, and is not what
this is. Do not install a general proxy, do not open the SOCKS port beyond
localhost/Tailscale, do not add other users to it.

### Keep the IP boring

The cost of this is that a residential line starts looking automated —
CAPTCHAs land on Marsita's own browsing. Cheap mitigations, worth doing at
setup rather than after:

- rate-limit the agent's browsing; human-ish pacing, not a crawl loop
- no parallel tab storms, no scraping runs
- if it starts hammering something, that is a bug, not throughput

### Kill switch

`sudo pkill -u grokbot; sudo usermod -L grokbot` stops everything at once.
Marsita should know that command exists before the first session, not after.

## Report back


Post the before/after of `uptime` and `free -g` to the board. The whole point
is Marsita being able to see the box breathe.

## Appendix — hermes has no working cloud brain (2026-09-04)

Relevant because hermes is the thing that was hammering llama, and because he
is on the council rota and Marsita wants to keep talking to him.

- **Anthropic API is refused.** Not an auth failure — `invalid_request_error`:
  *"Third-party apps now draw from your extra usage, not your plan limits."*
  The Max plan does not cover a third-party agent. Needs pay-as-you-go credit.
- **GitHub Copilot is refused too.** `api.githubcopilot.com/models` answers
  with 30 model ids (`gpt-5.6-sol`, `claude-opus-5`, `kimi-k3`...), but every
  completion returns `model_not_supported`, and `gh api user/copilot_billing`
  is a 404. There is no Copilot subscription on the account. The model list is
  a public menu, not an entitlement.
- Verified by hand with curl, outside hermes. Not a hermes bug.

So hermes' options are: Copilot Pro at ~$10/mo (flat, unlocks that whole list),
an OpenAI platform key (metered — note a ChatGPT subscription is *not* API
access), or stay on llama at 5 t/s for the daily guardian slot only.

Marsita has not chosen yet. Do not spend money on her behalf.
