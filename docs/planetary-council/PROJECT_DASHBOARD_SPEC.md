# Project Dashboard Spec

Purpose: give Phil and Hermes an always-on cockpit for all active projects, with enough structure that agents can read it before acting and humans can glance at it on the monitor.

## Core thesis

The project dashboard is not a generic todo list. It is the map of Phil's current operating system: projects, goals, attention, risks, next actions, approvals, artifacts, browser tasks, and agent handoffs.

It should answer in under 10 seconds:

- What am I working on?
- What matters today?
- Which project needs the next click?
- What is blocked?
- What needs approval?
- What did agents produce?
- Where are the files/links?
- What is being ignored for too long?

## Dashboard sections

### 1. Today / cockpit top bar

Fields:

- date
- current anchor
- current mission
- energy/context note
- top 1-3 priorities
- pending approvals count
- active browser automation task
- last agent handoff
- high-signal alerts only

### 2. Project radar

A card per project, sorted by `focus_score`.

Each card shows:

- project name
- status: active | warming | paused | blocked | archived
- horizon: 10y | year | season | month | week | day
- why it matters
- current outcome
- next action
- owner / agents
- blockers
- last touched
- stale age
- artifact links
- GitHub link
- Drive folder link
- Discord channel
- browser automation needed: yes/no
- approval needed: yes/no

### 3. Focus score

Focus score should combine strategy, urgency, momentum, and public/world signal. It should not blindly follow clicks.

Suggested weights:

- strategic priority: 0-5
- deadline urgency: 0-5
- momentum: 0-5
- blocker severity: 0-5
- opportunity value: 0-5
- attention signal: 0-5
- agent readiness: 0-5
- energy fit: 0-5

Formula v0:

```text
focus_score =
  strategic_priority * 3
+ deadline_urgency * 2
+ opportunity_value * 2
+ blocker_severity * 2
+ momentum
+ attention_signal
+ agent_readiness
+ energy_fit
- stale_penalty_if_paused
```

Principle: Public attention shows where the world is leaning in. Strategic priority decides whether we lean back.

### 4. Approvals queue

Anything risky waits here:

- sending email/message
- posting publicly
- spending money
- deleting files/infrastructure
- changing production config
- sharing private data
- granting permissions
- merging/deploying

Each approval item:

- action
- project
- risk level
- exact target
- proposed content/diff
- rollback path
- approve/deny/defer

### 5. Browser automation queue

Because legitimate browser automation is high-value for Phil.

Each item:

- website/app
- account/session expected
- goal
- required evidence
- safe boundaries
- whether user presence is needed
- result link/screenshot

Rules:

- Use local browser/saved login when possible.
- Never ask for secrets directly.
- Verify by screenshot/page state/tool output.
- Do not submit/send/purchase/delete without approval.

### 6. Artifacts and outputs

GitHub is the source of truth. Drive is the warehouse.

Each artifact record:

- title
- project
- type: screenshot | report | PDF | image | video | export | code | doc
- location: GitHub path or Drive link
- created_at
- created_by
- status: draft | reviewed | final | archived
- summary

### 7. Agent handoffs

Each handoff should be short and operational:

- what changed
- what was verified
- what failed
- current blockers
- recommended next action
- links to artifacts
- confidence

### 8. Discord channel mapping

Discord should be the live cockpit. GitHub/Drive remain durable storage.

Suggested mapping:

- #hermes-home: general control
- #inbox: raw dumps, screenshots, links
- #daily-anchor: before-sleep and daily plan
- #approvals: gated decisions
- #alerts-high-signal: important only
- #planetary-council: core website/BaseX
- #browser-automation: web tasks and evidence
- #outputs: finished artifacts
- #agent-handoffs: summaries between sessions/machines
- #debug: logs/errors/noise

## Data shape

Suggested file: `data/projects.json`

```json
{
  "updated_at": "2026-07-18T00:00:00Z",
  "projects": [
    {
      "id": "planetary-council-basex",
      "name": "PlanetaryCouncil / BaseX",
      "status": "active",
      "horizon": "season",
      "why": "Build the first personal/public dashboard that agents read before acting.",
      "current_outcome": "Small living dashboard with /boot and project radar.",
      "next_action": "Scaffold projects.json and render Project Radar cards.",
      "strategic_priority": 5,
      "deadline_urgency": 3,
      "momentum": 4,
      "blocker_severity": 1,
      "opportunity_value": 5,
      "attention_signal": 4,
      "agent_readiness": 5,
      "energy_fit": 4,
      "focus_score": 0,
      "blockers": [],
      "approvals": [],
      "browser_tasks": [],
      "github": "",
      "drive": "",
      "discord_channel": "#planetary-council",
      "last_touched": "",
      "artifacts": []
    }
  ]
}
```

## MVP build path

1. Create `data/projects.json` with known projects.
2. Add a `/projects` or `/api/projects` endpoint.
3. Add dashboard Project Radar cards.
4. Add Approvals card.
5. Add Browser Automation Queue card.
6. Add Artifacts card with GitHub/Drive links.
7. Add Agent Handoff card.
8. Add stale-project highlighting.
9. Add Discord channel links when available.
10. Later: sync from GitHub issues, Discord messages, Drive folder indexes, browser task outputs.

## Initial project candidates

- PlanetaryCouncil / BaseX
- personal website / public presence
- browser automation cockpit
- Discord agent cockpit
- Google Drive artifact warehouse
- GitHub private coordination repo
- email autopilot
- art/music online presence
- Hermes always-on monitor setup

## Design principle

This dashboard should not become a chore. It should reduce mental RAM.

The screen should say: here is the map, here is the next click, here is what needs your human approval.
