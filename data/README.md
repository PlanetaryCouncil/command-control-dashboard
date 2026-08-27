# What lives in `data/` — and what is public

This project is a transparent dashboard, so some operational data is
**intentionally public**. But "transparent" is not "publish everything": Git
makes anything committed durable in history and forks, so runtime state that
carries private detail is kept out of the tree entirely.

## Intentionally public (tracked)

These are the dashboard's content — the "life OS" that the board renders. They
are meant to be read by anyone (and by agents).

| file | what it is |
|---|---|
| `life.json` | the mission, projects and "life operating system" shown on the board. Home paths are sanitised to `~`. |
| `horizons.json` | long-range goals and their review dates. |

## Runtime, kept tracked but redacted

Kept for now because live readers depend on them; scrubbed of third-party PII.
Caller addresses are coarsened at capture (IPv6→/48, IPv4→/24), so these stop
accumulating home addresses. Untracking them fully is a follow-up.

| file | note |
|---|---|
| `events.jsonl` | the mutation/event log the board streams. Specific third-party IPs were redacted across history; new entries are coarsened. |
| `trusted_nodes.json` | paired-node registry. IPs redacted; device strings retained. |

## Runtime-only (NOT tracked — see `.gitignore`)

Written constantly by the running fleet and its jobs. They carry queue state,
agent transcripts, local worktree paths and timestamps — none of it release
source. A fresh clone boots without them: the loaders default to empty.

- `data/inbox.json`, `data/pairing.json`, `data/sync_conflicts.json`
- `data/oplog/`, `data/inbox/`
- `data/poems.jsonl` (closing couplets; served live at `/poems.json`)
- `fleet/rota/*`, `fleet/state/*`
- `self-improve/state/*`
- `fleet/data/selfies.jsonl`, `fleet/data/localvoice.jsonl`
- `fleet/projects.txt`

## Rule

Runtime state is not release source. Before tagging or publishing, discard
churn with `git checkout -- .` (see `docs/RELEASE.md`). PII is coarsened at the
point of capture, never cleaned up after.
