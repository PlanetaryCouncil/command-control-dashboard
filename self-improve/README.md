# self-improve

A scheduled multi-agent loop that improves this machine's Claude Code tooling
using evidence from real past sessions.

The premise: your session transcripts already record every place the agent
stumbled — tool calls that errored, permissions that got denied, corrections you
had to type. That's a training signal sitting on disk doing nothing. This loop
mines it, turns the strongest patterns into skills / subagents / CLAUDE.md
rules, and commits them. Next session starts smarter than the last.

## How it works

```
observe.py            mine ~/.claude/projects/**/*.jsonl → clustered friction
    ↓                 (verbatim excerpts, deduped by normalized signature)
orchestrator          reads evidence, checks ledger for already-tried ideas
    ↓ fan out
proposer agents       one per evidence cluster → exactly one proposal each
    ↓ fan out
skeptic agents        adversarially refute; default to refuting when unsure
    ↓ survivors only
apply                 write under claude/, append ledger, one commit each
```

The symlinks are what close the loop:

```
~/.claude/skills     → claude/skills
~/.claude/agents     → claude/agents
~/.claude/CLAUDE.md  → claude/CLAUDE.md
```

Editing `claude/skills/foo/SKILL.md` *is* editing the live skill. Every change
is a git commit, so anything the loop does is revertible with `git revert`.

## Guardrails

An unattended agent editing the config that governs agents needs bounds that
don't rely on the agent's cooperation. Three layers:

| Layer | Mechanism | Depends on model behaving? |
|---|---|---|
| Instruction | `loop/prompt.md` hard limits | yes |
| Permission | `loop/deny.json` deny-list | no |
| Verification | checksum guard in `run-cycle.sh` | **no** |

Specifics:

- **Hooks are proposal-only.** Hooks run arbitrary shell on every tool call, so
  an unattended agent must not write them. If evidence calls for one, the agent
  writes `proposals/<date>-<slug>.md` and leaves it for you. `settings.json` is
  checksummed before and after every run and **restored from snapshot** if it
  changed — see `state/violations.log`.
- **Max 3 changes per cycle.** Bounds how far one bad run can drift.
- **No-evidence runs make no changes.** If the observer finds nothing, the cycle
  exits before the agent starts. Nothing invites invention like an empty file
  and a mandate to improve something.
- **Rejected ideas stay rejected.** `state/rejected.jsonl` stops the loop
  rediscovering the same refuted proposal every night.
- **No network.** WebFetch/WebSearch/curl/git push are denied. Local files and
  local commits only.

## Usage

```bash
# run a cycle by hand
bash loop/run-cycle.sh

# just look at the evidence, change nothing
python3 loop/observe.py 14 | less

# what has it changed, and why
cat CHANGELOG.md
cat state/applied.jsonl | python3 -m json.tool --json-lines

# what it tried and rejected
cat state/rejected.jsonl

# undo one change
git revert <sha>

# undo everything, back to bootstrap
git revert --no-commit cb5775d..HEAD && git commit -m "reset"
```

## Scheduling

```bash
cp loop/re.genesis.self-improve.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/re.genesis.self-improve.plist

launchctl list | grep self-improve      # confirm loaded
launchctl start re.genesis.self-improve # fire one now
launchctl unload ~/Library/LaunchAgents/re.genesis.self-improve.plist  # stop
```

Runs daily at 03:00. If the Mac is asleep, launchd fires it at next wake.

## Watching it

The failure mode to watch for is **drift**: the loop adding plausible rules
nobody needed, each one taxing every future session's context. Guard against it
by reading `CHANGELOG.md` weekly and asking of each entry — *would I have
written this rule myself?* If a run commits three changes on thin evidence,
that's the signal to tighten `loop/prompt.md`, not to let it keep running.

`state/cycles.log` is one line per run. A healthy loop mostly does nothing.
