# PlanetaryCouncil / BaseX — AI Handoff Brief

## 1. What this project is

PlanetaryCouncil / BaseX is a living human-agent website: part public portal, part personal dashboard, part agent boot context, part visitor interaction system.

It is **not** meant to be a generic chatbot, CRM, forum, DAO, or todo app. The deeper purpose is to build soft infrastructure for human-agent civilization: culture, trust, memory, coordination, accountability, reputation, public signals, private sovereignty, and shared goals.

Core thesis:

> PlanetaryCouncil / BaseX is a cultural operating system for humanity: a unified human-agent interface where people, agents, goals, trust, knowledge, services, and daily discipline meet.

Important phrases to preserve:

- “Culture is what agents read before acting.”
- “The website is the body. WebSocket is the nervous system. Hermes is the brain.”
- “Public input becomes signal, not truth.”
- “Open by default. Powerful by reputation.”
- “Trust first. Verify before power.”
- “From ten-year destiny to next click.”
- “The plan can change, but not disappear without explanation.”

## 2. Product concept

The website is the first page/API that Hermes or another agent visits when it comes online. It should tell agents:

- Where am I?
- Who am I serving?
- What matters today?
- What changed?
- What did Phil say before sleep?
- What are the current goals?
- What are the constraints and permissions?
- Who is asking for what?
- Who can be trusted for what?
- What is safe for me to do?
- What is the next useful action?

Key machine-readable routes:

- `/boot` — compact agent-readable context.
- `/health` — server/database health.
- `/api/messages` — visitor chat/message ingestion.
- `/api/attention` — attention/hover/focus tracking.
- `/api/projects/focus` — ranked project focus scores.
- `/api/telegram/reply` — route Phil’s Telegram reply back to a website visitor session.
- `/ws/{session_id}` — realtime WebSocket session updates.

## 3. Current working state

Local project path:

`/path/to/planetary-council`

A first working MVP has already been built. Current stack:

- FastAPI web server
- SQLite persistence layer
- append-only `events` table
- visitor sessions and messages
- cheap receptionist triage/reply
- Telegram routing hook endpoint, not fully wired to real Telegram bot yet
- project attention tracking from hover/click events
- project focus scoring
- WebSocket endpoint for live session updates
- `/boot` endpoint for agent-readable context
- simple HTML/JS website UI with project cards and chat box
- pytest automated tests
- local git repo initialized on `main`
- initial commit exists: `feat: scaffold planetary council mvp`

Important files:

- `app/main.py` — main FastAPI app, DB schema, endpoints, WebSocket, HTML UI.
- `tests/test_mvp.py` — backend tests for persistence, triage, attention, Telegram reply routing, boot endpoint.
- `tests/test_web_ui.py` — UI instrumentation test.
- `README.md` — run/test/endpoints.
- `WORKFLOW.md` — branch/test/commit/deploy workflow.
- `HOSTING.md` — staging/production hosting plan.
- `SEED.md` — original vision seed.
- `.github/workflows/ci.yml` — GitHub Actions test workflow.
- `Dockerfile`, `Procfile`, `.env.example` — deployment support.

Verified test command:

```bash
cd /path/to/planetary-council
uv run pytest -q
```

Last verified result:

```text
5 passed
```

Run locally:

```bash
cd /path/to/planetary-council
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open:

`http://127.0.0.1:8765/`

## 4. Core architecture

Use separate durable and live layers:

```text
visitor / agent / Phil
  → HTTP + WebSocket
  → FastAPI app server
  → SQLite/Postgres persistence
  → append-only events truth trail
  → WebSocket broadcasts live updates
  → Telegram routing for high-signal human replies
```

Rules:

- Database = memory.
- Append-only `events` table = truth trail.
- WebSocket = nervous system/live transport, **not** persistence.
- `/boot` = agent-readable culture/context layer.
- Public comments/messages = raw signal, **not** canon.
- Write database/event records before broadcasting over WebSocket.
- Keep private cockpit data out of public routes.

Current DB default:

`data/planetary_council.db`

For MVP, SQLite is fine. For real public multi-user production, add backups/persistent volume or migrate to Postgres.

## 5. Visitor interactivity model

Ideal flow:

```text
visitor writes on website
→ server stores message + event
→ cheap receptionist agent replies/triages
→ high-signal messages forward to Phil on Telegram
→ Phil replies in Telegram
→ server maps reply to website session
→ WebSocket pushes Phil’s reply back to visitor live
```

Cheap agent role: receptionist, not fake Phil.

It may:

- greet visitors
- answer basic public-canon questions
- collect name/contact/intent
- summarize visitor intent
- route high-signal messages to Phil
- keep visitor warm while Phil is away

It must not:

- make commitments
- pretend to be Phil
- expose private context
- grant permissions
- promote comments into canon
- run expensive agents without approval

High-signal Telegram escalation examples:

- visitor explicitly asks for Phil/human
- collaboration/funding/media/legal/security opportunity
- skilled builder/agent introduces themselves
- trusted/returning visitor
- urgent/sensitive issue
- agent-to-agent handshake needing approval

Routine FAQ/noise should be handled by cheap agent or stored for later digest.

## 6. Attention/project-focus model

A main product goal is to discover which projects deserve focus by measuring qualified visitor attention.

Track signals:

1. impression
2. hover/pause seconds
3. project detail open
4. scroll/deep read
5. return visit
6. question/comment
7. share/save
8. collaboration offer
9. verified contribution

Hover seconds are a useful first signal, but noisy:

- under 1 second = likely accidental
- 2–5 seconds = curiosity
- 10+ seconds = strong interest or confusion

Do not blindly optimize for clicks. Combine attention with:

- strategic priority
- visitor trust/reputation
- repeated questions
- collaborator offers
- actual execution momentum

Guiding line:

> Public attention shows where the world is leaning in. Strategic priority decides whether we lean back.

## 7. Workflow and hosting direction

Current workflow goal:

```text
idea → small task → branch → test → code → run locally → commit → PR/CI → staging deploy → production
```

GitHub/hosting are not yet fully bootstrapped from this device. Last known blockers:

- `gh` GitHub CLI was missing
- no `GITHUB_TOKEN` env present
- no `flyctl`, `railway`, or Docker CLI present

One-time manual setup likely required by the user/device owner:

```bash
brew install gh
gh auth login
```

Then create/push repo:

```bash
cd /path/to/planetary-council
gh repo create planetary-council --private --source . --push
```

Recommended hosting path:

1. GitHub private repo + GitHub Actions CI.
2. Render/Railway/Fly.io for staging.
3. Fly.io with persistent volume or small VPS once SQLite persistence matters.
4. Postgres later when concurrent writes/backups become important.

This should not be static-only hosting because the app needs WebSockets, DB writes, Telegram webhook endpoint, and live visitor sessions.

## 8. Immediate next steps for the next AI

Start by verifying the repo state:

```bash
cd /path/to/planetary-council
git status --short --branch
uv run pytest -q
```

Then proceed in this order:

1. If GitHub auth exists, create/push private repo.
2. If not, guide the user through `gh auth login` or accept a remote URL they created manually.
3. Keep `main` deployable; make branches for changes.
4. Wire real Telegram bot only after token is provided via safe secret storage, never committed.
5. Add environment-variable DB path support if deploying with persistent volume.
6. Add admin/private/public visibility filtering before public production.
7. Add a dashboard page for sessions, focus scores, and pending Telegram escalations.
8. Add privacy note for hover/attention analytics.
9. Deploy staging and test the full roundtrip: website visitor → Telegram → Phil reply → website visitor.

## 9. Guardrails

- Never commit `.env`, Telegram tokens, API keys, cookies, OAuth tokens, or passwords.
- Do not expose private cockpit data publicly.
- Do not treat visitor comments as canon.
- Do not overbuild before the simplest live loop works.
- Do not replace the user’s judgment with raw attention scores.
- Do not use expensive AI loops for every visitor message; cheap triage + Telegram escalation is the intended MVP.
- Ask before actions with external side effects: public deploy, sending messages, setting webhooks, spending money, deleting data, changing DNS.
