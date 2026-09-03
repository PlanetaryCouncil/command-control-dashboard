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

Lean user, no sudo, browser-capable. James's account on this box is the
working reference for the desktop side (XFCE + lightdm; GDM on Ubuntu 26.04 is
Wayland-only and ignores both `WaylandEnable=false` and the AccountsService
`XSession` key — do not spend an hour rediscovering that).

Differences from James: **no sudo group**, and it is an agent that executes
code rather than a person, so keep its home genuinely separate from `m`'s.

Marsita's line, worth keeping: a box that browses the web as her is fine. A box
that routes other people's traffic out her home IP is a different thing and is
not what this is.

## Report back

Post the before/after of `uptime` and `free -g` to the board. The whole point
is Marsita being able to see the box breathe.
