# The NUC froze for nine days

**When:** 8 August 2026, 19:05 BST. Found and fixed 18 August 2026, 07:30.
**Impact:** The NUC was unreachable for nine days. Its Telegram bot took
messages and answered none of them. The operator was in Iceland and had no way
to tell the difference between "the bot is broken" and "the machine is gone".
**Detected by:** a human, asking why the bot had stopped talking.

---

## What actually happened

The machine did not crash and it did not shut down. It **stopped**.

A clean shutdown leaves a trail — `systemd-shutdown`, unmount lines, a
"powering down" message. A panic leaves a stack trace. This left nothing. The
journal ends mid-flight on a routine job finishing normally:

```
Aug 08 19:03:40.318814  Finished fleet-rota.service - Fleet rota (continuous).
Aug 08 19:05:23.373330  Starting fleet-board-medic.service - Fleet board medic...
Aug 08 19:05:23.407092  Finished fleet-board-medic.service - Fleet board medic.
```

Then silence for nine days. The next boot confirms it was violent:

```
Aug 18 07:30:55  EXT4-fs (dm-1): orphan cleanup on readonly fs
Aug 18 07:31:04  systemd-journald: File .../user-1000.journal corrupted or
                 uncleanly shut down, renaming and replacing.
```

That is a hard freeze. The kernel stopped executing. Nothing got written down
because the thing that writes things down was the thing that died.

## Why it stayed dead for nine days

This is the part worth remembering, and it is not obvious.

The NUC's BIOS is set to power on after a power outage. That setting did
nothing here, and could not have. **A frozen machine still draws power.** The
AC never dropped, so there was no power-restore event to react to. The box sat
there warm, plugged in, and completely inert.

What finally fixed it was the operator physically unplugging it and plugging it
back in — which manufactured the AC loss the BIOS had been waiting for.

> Restore-on-AC-loss protects you from the power going away.
> It does not protect you from the computer going away.

## What it was not

Ruled out from the logs, so nobody re-investigates these later:

- **Not out of memory.** There was one OOM kill — `llama-server`, on 7 August
  at 14:55, more than a day earlier. The box ran fine for another 28 hours.
- **Not heat.** Every "thermal" hit in the log is `thermald` starting up and
  complaining about a missing config file. No critical temperature, no MCE, no
  machine check exception, no hardware error.
- **Not the network.** The journal stops entirely. If it had merely dropped off
  the network, local services would have kept logging.

## What it probably was

Unknown, honestly. A silent hard hang with no kernel trace on a **NUC10i7FNH**
is usually firmware, a marginal PSU, or an i915 graphics hang — but the
evidence that would distinguish them is exactly the evidence a freeze destroys.

The one lead: `ollama` was working hard right up to the last second, on a box
with no GPU. Worth watching, not worth concluding.

**This post-mortem does not claim a root cause.** It claims a *recovery
failure*, which is the part we can actually fix.

---

## The real failure

The freeze is a hardware event and may well happen again. Nine days of silence
is a **design** failure, and that is ours.

Three things were missing:

1. Nothing watched the machine's liveness.
2. Nothing could reboot it without a human in the room.
3. Nothing told the operator it had gone quiet.

## The fix: two watchdogs, because there are two failures

### Layer 1 — hardware watchdog, for death

The NUC has an Intel TCO watchdog. The driver was never loaded.

```
iTCO_wdt: Found a Intel PCH TCO device (Version=6, TCOBASE=0x0400)
iTCO_wdt: initialized. heartbeat=30 sec (nowayout=0)
```

`/etc/modules-load.d/itco-watchdog.conf` loads it at boot;
`/etc/systemd/system.conf.d/watchdog.conf` sets `RuntimeWatchdogSec=30s`.
systemd pets `/dev/watchdog` continuously. If the kernel freezes, the petting
stops and the chip power-cycles the box in 30 seconds.

**This is the layer that would have caught the 8 August incident.** Nothing in
userspace could have.

### Layer 2 — stall watchdog, for coma

`fleet/bin/stall-watchdog.py`, a root systemd timer every two minutes.

There is a nastier failure between "healthy" and "frozen": the box answers ssh,
timers still fire, and yet nothing *finishes*, because every process is queued
behind swap or a wedged disk. The kernel is fine there, so the hardware
watchdog never fires. It is the work that is dead, not the machine.

---

## Thresholds, and why they are what they are

This is the part to argue with. Read it sceptically.

### Why not load average

The obvious rule is "load too high for too long, reboot". It is wrong on this
box, and would have caused outages of its own.

This NUC runs `ollama` with **no GPU**. A legitimate inference run pins all
twelve cores for minutes at a stretch — that is the machine doing exactly what
it was bought to do. A load-based rule cannot tell that apart from a wedged
box, so it would shoot the machine mid-thought. Load measures *demand*. It says
nothing about whether work is *completing*.

### Why PSI instead

Pressure Stall Information (`/proc/pressure/{cpu,memory,io}`) measures
something load cannot: **what fraction of wall-clock time tasks spent unable to
progress.**

Two flavours, and the difference matters:

- `some` — at least one task was stalled. Normal under load.
- `full` — **every** runnable task was stalled. Nothing progressed at all.

`memory full avg60 = 30` means that for 30% of the last minute, the entire
machine achieved nothing. A busy machine has high `some` and near-zero `full`.
A dying one has high `full`. That is the signal, and it is the reason this
design works where a load rule does not.

### The numbers

| Signal | Threshold | Basis |
|---|---|---|
| `memory full avg60` | > 20% | **Reasoned.** Sustained `full` memory pressure is swap death. 20% for a full minute is far outside anything healthy. |
| `io full avg60` | > 60% | **Reasoned, and the weakest number here.** Higher than memory because heavy disk work legitimately produces real `full` io pressure in bursts. |
| `cpu some avg300` | > 90% | **Weakest of the three.** This is a `some`, not a `full` — the kernel does not report `cpu full`. A long ollama run could plausibly approach it. Prime suspect for the first false positive. |
| strikes | 3 x 2 min | **Reasoned.** ~6 minutes of sustained stall. Survives one ugly minute; well under the nine days it replaced. |
| boot grace | 15 min | **Reasoned.** Never shoot a machine that is still starting up. |

**Be honest about the provenance:** these are first-principles numbers, not
measured ones. Baseline PSI on this box is `0.00` across the board when idle,
which tells us the healthy floor and nothing about the healthy ceiling. **We
have never observed PSI during a real ollama run**, and that is the single
biggest gap in this design.

### How to calibrate them properly

Sample `/proc/pressure/*` every 10 seconds for a week, through real ollama
workloads. Then set each threshold above the observed maximum of normal
operation, with margin. Until that data exists, the numbers above are educated
guesses that have not yet been wrong.

### Which way to err

A false positive costs a reboot on a machine designed to survive reboots. A
false negative costs nine days of silence. When in doubt, **reboot too eagerly,
not too reluctantly** — but only after fixing `cpu some avg300`, which is the
one most likely to fire without cause.

---

## Lessons

1. **A frozen machine draws power.** Every recovery plan built on AC loss has
   this hole in it.
2. **Absence of evidence is the evidence.** No shutdown sequence in the log is
   itself the diagnosis. Learn to read the silence.
3. **Measure completion, not demand.** Load says the machine is busy. PSI says
   whether anything is getting done. Only one of those distinguishes work from
   death.
4. **Two failure modes need two watchdogs.** Software cannot catch a kernel
   freeze; hardware cannot catch a live-but-useless box.
5. **Unmonitored silence lasts exactly as long as it takes a human to notice.**
   Here, nine days, because the human was in another country.
6. **Say it before you do it.** The stall watchdog messages Telegram *before*
   rebooting. Waking to a mysteriously rebooted machine is its own failure.

## Still open

- ~~The hardware watchdog config has not been verified across a reboot.~~
  **Verified on 2026-08-18, and it was broken.** Two reboots came up with no
  `/dev/watchdog` at all: the kernel package deny-lists `iTCO_wdt`, and both
  `/etc/modules-load.d` and the initramfs skip a deny-listed module while
  reporting success. Fixed with an explicit `modprobe` in a systemd unit and
  confirmed on a third reboot. See
  [nuc-hardware-watchdog.md](../development-log-progress-report/nuc-hardware-watchdog.md).

  The lesson generalises: **the untested assumption was untested for a reason,
  and it was wrong.** Nine days of protection existed only on paper.
- The Mac has neither watchdog.
- Root cause of the freeze remains unknown. If it recurs, the hardware watchdog
  will now produce a *pattern* — which is the first real evidence we will ever
  have had.
