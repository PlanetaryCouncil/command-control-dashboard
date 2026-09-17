# The fleet: two machines, six roles

**Single source of truth for where work runs.** If something here disagrees
with a plist, a timer, a README or a memory, this file is right and the other
thing is stale. Written 2026-09-17 because this argument has now been had more
than once — most recently by an agent that spent a session trying to "fix"
eight launch agents that were switched off on purpose.

## Two machines

| | Gaia | NUC |
|---|---|---|
| what | MacBook, 4 cores, 8 GB | 12 cores, 14 GB, in a cupboard |
| role | the board, the terminal, the operator | **the work** |
| runs | `fleet.py serve 8787`, the tmux `board` session | every scheduled job |

`1a7b89e` (2026-08-20) named it: **"cupboard sits, desk stays light."** Both
boxes are always on; the split is capacity, not uptime. Gaia sits at load ~6
on 4 cores with a browser and several Claude sessions; the NUC idles at 0.2.

**Consequence: the eight `re.genesis.*` launch agents on Gaia are dead.** They
are installed, `launchctl disable`d, and must stay that way. A disabled service
refuses `bootstrap` with `Input/output error`, which looks exactly like a bug
and is not one. Do not load them. Do not "repair" them.

## Six roles, not thirteen jobs

`fleet/config.json` lists thirteen **cadences**. It is a schedule file read by
a handful of runners — not thirteen processes. Reading it as a process list is
the specific mistake that starts this conversation.

| role | systemd unit | what it is | absorbed |
|---|---|---|---|
| **ROTA** — the conductor | `fleet-rota` | one agent at a time, in turn, forever. Reads the board, proposes one action. Proposes only. | |
| **BUILD** — the builder | `fleet-build` → `backlog.sh` | one 15-minute slot. Picks the next builder, triages the backlog, implements in a worktree. | `pipeline`, `builders` |
| **HEALTH** — the guardian | `fleet-health` → `health.sh` | is everything up? Board every 5 min, project suites hourly, comms relay daily. Fixes what it finds. | `watchdogs`, `board_medic`, `comms-heartbeat`, `trim`, `quotas` |
| **COUNCIL** — the deliberators | `fleet-council` → `council-cycle.sh` | all agents together. Mines transcripts, proposes changes to its own code. | `self_improve` (once per calendar day) |
| **REPORT** — the storyteller | `fleet-report` → `report-cycle.sh` | one page a day, published to GitHub Pages. Pulse check, model check. | `local_voice` |
| **E2E** — the verifier | `fleet-e2e` | daily, against live infrastructure. The only one that can say the whole fleet works. | |
| **DAILY** | `fleet-daily` | the one message the operator actually reads. | |

The consolidations are recorded in the code, in Marsita's own words:

- `health.sh` — *"watchdog = medic = heartbeat = same same, we don't want to"*
- `council-cycle.sh` — *"council and self-improve should be same as well"*

`quotas` is one level deeper again: `health.sh` runs `board-medic.sh`, and
`board-medic.sh:36` runs `quotas.py`. Nesting like that is exactly why you
cannot tell what runs by reading names.

## Changing a schedule

Edit `fleet/config.json`, then on the NUC:

```
bash fleet/bin/apply-config-systemd.sh
```

`apply-config.sh` is the macOS sibling. It writes launchd plists and is **not**
how the fleet runs any more; it stays for the board's own units.

## Before you "fix" the fleet

1. A job missing from Gaia is not missing. Check the table above.
2. A disabled launch agent on Gaia is deliberate.
3. Compare behaviour, not lists of names. Two names that differ can be the
   same job; `grep` the runner before concluding anything.
