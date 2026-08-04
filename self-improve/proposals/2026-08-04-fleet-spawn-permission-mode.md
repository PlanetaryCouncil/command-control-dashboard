# Fleet agents are spawned in a mode that cannot run Python

**Date:** 2026-08-04
**Status:** for human decision — this loop does not change permission modes
**Signatures:** `13b47efe3c` (×10, 5 sessions), `15f51095a8`, `5a5c5eafd6`,
`f28546b9be`, `3ae1f0c881`
**Cycle verdict:** no `claude/` artifact written. The behavioural rule built on
this evidence was refuted (see `state/rejected.jsonl`, 2026-08-04). The
*mechanism* below survived — it is just not something a CLAUDE.md rule can fix.

## What the evidence actually shows

Partitioning every Bash call containing `python` across all of
`~/.claude/projects/` by permission mode:

```
mode                 | promptSource        | is_error | count
acceptEdits          | sdk                 | True     | 12
bypassPermissions    | sdk                 | False    | 31
auto                 | queued,typed        | False    | 222
auto,default         | queued,system,typed | False    | 277
```

Every denial is `permissionMode=acceptEdits` + `promptSource=sdk`. **No
`acceptEdits`+`sdk` Python call has ever succeeded on this machine.** Same
harness version (2.1.220) throughout, so the variable is the spawn mode, not
the version or the project.

Where the two modes come from:

```
fleet/bin/chat.py:181       "claude", "--print", "--permission-mode", "acceptEdits",
fleet/bin/blackboard.py:47  "--permission-mode", "bypassPermissions",
```

So rota/council turns spawned through `chat.py` get a mode in which
`python3 -c`, `python3 - <<EOF`, `python3 fleet/bin/pick.py --help`, `awk`, and
`Write` outside the cwd all come back *"This command requires approval"* — and
nobody is awake to approve. Turns spawned through `blackboard.py` do not.

Broader picture in the fleet project dir: **20 of 73 Bash results are errors**
— 10 `requires approval`, 7 `multiple operations`, 2 blocked greps (paths
outside the session cwd), 1 quoting rejection. `grep` is denied too when it
reaches outside the working directory or chains operations, so this is not
"Python bad, grep fine".

## What it actually cost

Small, and worth saying plainly before anyone changes anything:

- Data-inspection denials (6, across 4 sessions) recovered on the **immediately
  next** call with a working `grep`/`cat` substitute, 6 for 6. One wasted tool
  call each.
- Poem-box denials (8 calls, 2 sessions) cost nothing user-visible — both
  replies shipped correct hand-built boxes (every row 50 chars), and that whole
  class is gone anyway since commit `55ee42f3` exempted rota/council turns from
  the poem.

No task failed. No wrong output shipped. This is a papercut on ~1–2 unattended
sessions a day, not an outage.

## Options, if you want to close it

1. **Do nothing.** Defensible — recovery is one call and the agents cope.
2. **Move `chat.py:181` to `bypassPermissions`,** matching `blackboard.py`.
   Cheapest fix, and it makes the two spawn paths consistent. It also hands
   unattended agents arbitrary code execution in this project, which is
   presumably why they differ today. If the split was deliberate, keep it.
3. **Narrow allowlist instead** — e.g. `Bash(python3 -c:*)` and the fleet's own
   `bin/*.py` entry points in `.claude/settings.local.json` for the fleet
   project. Keeps the blast radius smaller than option 2.

Options 2 and 3 both touch permission configuration, which this loop is barred
from editing. Hence this file rather than a commit.

## Receipts

Sessions, all in `~/.claude/projects/-Users-phil-projects-command-control-dashboard-fleet/`:

- `8a49e6e2-aba5-40e6-b62b-fe77abf18876` — idx 62 heredoc denied, 64 `Write
  /tmp/box.py` denied, 69 `python3 -c` denied, 72 `awk` denied
- `8908291e-454c-49bc-9647-24208c0bd4f8` — idx 54 heredoc denied, 56 `Write
  /tmp/poembox.py` denied, 58 `python3 -c` denied, 61 `python3 bin/pick.py
  --help` denied
- `9abe35ce`, `964f86f1`, `1db51422` — data-inspection denials, each recovered
  next call
