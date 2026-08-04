# Personal Website as Dashboard

This is the meta turn: Phil's own website is not only a public portfolio or landing page. It is the dashboard for Phil, Hermes, trusted agents, collaborators, and eventually public visitors.

## Core thesis

Phil's website is the agent-readable home base for his life and work.

It has two faces:

1. Public face: what the world can see, understand, comment on, and respond to.
2. Private cockpit: what Phil and trusted agents use to coordinate goals, projects, approvals, browser work, artifacts, and daily continuity.

The public site and private dashboard are the same organism with different permissions.

## Why this is powerful

Most personal websites are dead brochures.

This one should be alive:

- public identity and work
- current projects
- live/async agent presence
- project dashboard
- fractal goals
- public messages and signals
- private daily anchor
- approvals queue
- browser automation queue
- artifacts/results
- trust/reputation context
- `/boot` endpoint for agents

The website becomes the first place agents visit before acting.

## Product surfaces

### Public website

Public-safe surface:

- who Phil is
- what Phil is building
- public projects
- art/music/public work
- public writing/manifesto
- ways to collaborate
- public comments/messages
- selected artifacts
- public project status
- agent presence/avatar with clear boundaries

### Private dashboard

Authenticated cockpit:

- today anchor
- current focus
- project radar
- approvals
- browser automation queue
- active missions
- private notes/handoffs
- GitHub/Drive/Discord links
- alert inbox
- health/cost/tool status
- private settings and micromanagement controls

### Agent API

Machine-readable layer:

- `/boot`
- `/api/context/today`
- `/api/projects`
- `/api/goals/fractal`
- `/api/messages/priority`
- `/api/approvals/pending`
- `/api/missions/active`
- `/api/trust/registry`
- `/api/artifacts`
- `/api/health`

## Key design principle

Do not split identity, dashboard, and agent boot portal too early.

Start as one local/personal site with clear public/private boundaries. Later it can grow into PlanetaryCouncil/BaseX.

## MVP pages

1. `/`
   - public home
   - one-line thesis
   - current projects
   - public contact/collab entry

2. `/dashboard`
   - private cockpit
   - today anchor
   - project radar
   - approvals
   - browser queue
   - artifacts

3. `/projects`
   - public/private project index depending on auth

4. `/boot`
   - JSON context for Hermes/agents

5. `/inbox`
   - messages/signals/comments, public or private depending on source

6. `/artifacts`
   - index of GitHub/Drive outputs

## Data sources

- GitHub private repo: durable project state, Markdown, JSON, schemas, commits.
- Google Drive: large artifacts, screenshots, PDFs, media, exports.
- Discord: live cockpit/channels/history.
- Local browser: verified web actions and screenshots.
- `.env`: local-only secrets.

## Public/private boundary

Public by default:

- project descriptions
- selected artifacts
- collaboration requests
- public writing
- public status
- safe agent explanation

Private by default:

- daily anchor
- personal notes
- approvals
- credentials/secrets
- private messages
- internal logs
- browser sessions
- unpublished strategy
- private health/cost alerts

Never expose secrets, raw `.env`, private Discord messages, unreviewed public comments as canon, or sensitive browser state.

## Agent behavior

Before doing project work, agents should read:

1. `/boot`
2. `/api/projects`
3. `/api/approvals/pending`
4. latest handoff
5. relevant project page

Agents should write outputs back as:

- GitHub commit or markdown note
- Drive artifact if large
- dashboard handoff entry
- Discord summary if live cockpit is enabled

## Slogan

The personal website is the public skin of the private operating system.

Or:

The website is not a brochure. It is the cockpit.

## Build order

1. Keep current PlanetaryCouncil/BaseX repo as seed/spec source.
2. Add `data/projects.json`.
3. Build local dashboard from static JSON.
4. Add `/boot` JSON endpoint.
5. Add public home page.
6. Add project pages from the same data.
7. Add private dashboard/auth.
8. Add artifact links to Drive/GitHub.
9. Add Discord channel mapping.
10. Add WebSocket live presence after persistence works.

## Immediate next artifact

Create `data/projects.json` with the first project list and build a dashboard page that renders:

- Today
- Project Radar
- Approvals
- Browser Automation Queue
- Artifacts
- Agent Handoff

This is the smallest version of the meta-loop becoming real.
