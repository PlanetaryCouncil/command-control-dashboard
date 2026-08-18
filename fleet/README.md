# fleet

An always-on board showing what this machine's agents are doing.

**http://127.0.0.1:8787** — starts at login, restarts if it dies, refreshes every 20s.

## Workers

| Worker | Kind | Runs | Does |
|---|---|---|---|
| `self-improve` | learner | daily 03:00 | Mines session transcripts, proposes tooling improvements, commits only what survives adversarial verification. Lives in `../self-improve`. |
| `planetary-council` | watchdog | hourly | Runs the project's own test suite; writes a digest when it breaks. |

## Adding a project

Copy `projects.example.txt` to `projects.txt` (gitignored) and append each
checkout's absolute path. It appears on the board on the next run — no code
change. The watchdog picks the project's own test command, in order:
`.venv/bin/pytest` → `uv run pytest` → `npm test` → `make test`. If none is found
the worker reports `skip` rather than inventing one.

Two of your projects are deliberately not listed:

- `~/projects/basexHQ` — only `DOCTRINE.md`; no code or tests to run.
- `~/projects/command-control-dashboard` — has real tests, but is not a git repo,
  so findings can't be anchored to a commit and no fix branch can be proposed.
  `git init` there and it becomes eligible.

## How workers report

Each writes one JSON file to `workers/<name>.json`. The dashboard renders whatever
it finds, so a new kind of worker needs no dashboard changes — just that file:

```json
{ "worker": "...", "kind": "...", "status": "pass|fail|skip|alert",
  "last_run": "ISO8601", "summary": "...", "digest": "digests/... .md" }
```

Anything `fail` or `alert` sorts to the top of the board.

## Deliberate boundary

The watchdog **observes and reports; it does not modify your projects.** Whatever
establishes ground truth shouldn't share a process with something that changes
the code being measured. Auto-proposing fix branches is a separate worker, and
worth adding only once you've seen the watchdog catch something real.

The optional NUC browser worker is `bin/nuc-bridge.py`. Set `FLEET_NUC`
(`user@host`) on the machine that SSHes in; the script refuses to run
without it and never writes SSH errors onto the public board.

## Control

```bash
bash bin/run-watchdogs.sh          # run all checks now
python3 bin/fleet.py render        # write a static index.html snapshot

launchctl list | grep genesis      # what's loaded
launchctl unload ~/Library/LaunchAgents/re.genesis.fleet-server.plist   # stop board
launchctl unload ~/Library/LaunchAgents/re.genesis.watchdogs.plist      # stop checks
```

Logs are in `logs/` (last 20 runs per project); failure digests in `digests/`.
