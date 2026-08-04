# PlanetaryCouncil / BaseX — Persistence + WebSocket Architecture

## Purpose

The website is not just a static page. It is an interaction surface for visitors, humans, agents, and Hermes. Therefore it needs a persistence layer and a realtime layer.

Core idea:

- **Database** stores durable state: visitors, sessions, messages, comments, goals, missions, trust events, approvals, holons, audit log.
- **Append-only event log** stores everything that happened in order.
- **WebSocket server** streams live presence, chat, agent status, tool activity, dashboard updates, and notifications.
- **Agent boot API** exposes a clean `/boot` context so agents read current culture/goals/trust before acting.

## First-principles architecture

```text
Visitors / Agents / Hermes / Admin UI
        |
        | HTTP + WebSocket
        v
Web App / API Server
        |
        | writes events + reads projections
        v
Persistence Layer
  - Postgres or SQLite for app state
  - append-only event table
  - markdown/git holonic KB export
  - object/file storage for artifacts
        |
        v
Workers / Agents
  - summarize signals
  - update candidate holons
  - compute trust deltas
  - prepare approvals
  - send high-signal notifications only
```

## Recommended MVP stack

For the first local prototype:

- **Backend**: FastAPI + WebSockets, or Node/Next.js + WebSocket server.
- **Database**: SQLite first, Postgres later.
- **ORM/migrations**: SQLModel/SQLAlchemy/Alembic for Python, or Prisma/Drizzle for TypeScript.
- **Realtime**: native WebSocket endpoint `/ws`.
- **Event log**: `events` table with JSON payloads.
- **Holonic KB**: markdown files generated/exported from reviewed database records.
- **Agent context**: `/boot` endpoint reads from database + selected markdown canon.

Practical recommendation: start with **SQLite + FastAPI WebSocket**. It is simple, local, durable, and easy for agents to inspect. Upgrade to Postgres when multiple users/agents/servers need concurrent writes.

## Persistence model

### 1. Raw events: source of truth

Every meaningful action becomes an append-only event:

- visitor arrived
- visitor sent message
- agent replied
- proposal submitted
- goal created/changed
- trust event recorded
- approval requested/granted/rejected
- holon candidate created
- canon promoted
- mission created/claimed/completed
- system health alert

Suggested table:

```sql
create table events (
  id integer primary key autoincrement,
  event_id text unique not null,
  type text not null,
  actor_id text,
  subject_id text,
  session_id text,
  visibility text not null default 'private',
  trust_tier text not null default 'raw',
  payload_json text not null,
  provenance_json text,
  created_at text not null
);
```

Rule: raw events are never silently edited. If something changes, write a new event.

### 2. Projections: fast dashboard state

Derived tables make the UI fast:

- visitors
- sessions
- messages
- goals
- missions
- approvals
- trust_profiles
- holons
- canon_items
- notifications

These can be rebuilt from events if needed.

### 3. Holonic KB export

Reviewed/canonical records can be exported to markdown:

```text
holonic-kb/
  raw/
  signals/
  holons/
  canon/
  reviews/
```

Database is operational memory. Markdown/git is cultural memory and portable canon.

## Visitor interaction flow

1. Visitor opens website.
2. Server creates or resumes anonymous/pseudonymous `visitor_id`.
3. Server creates `session_id`.
4. Browser connects to `/ws`.
5. Server emits current public context:
   - live presence
   - public goals/projects
   - public agent status
   - permitted chat state
6. Visitor sends message/comment/proposal.
7. API writes raw event + message row.
8. WebSocket broadcasts permitted update.
9. Worker/agent later extracts signals:
   - question
   - objection
   - lead
   - proposal
   - contradiction
   - abuse/spam
10. Signals become candidate holons or moderation/approval items.
11. Only approved items affect canon, trust, or durable public knowledge.

Key guardrail:

> Public input becomes signal, not truth.

## WebSocket responsibilities

The WebSocket server is the nervous system. It should carry ephemeral/live updates, not be the only place state exists.

Use WebSocket for:

- live chat stream
- Hermes/agent presence
- assistant typing/thinking/tool status
- visitor presence
- dashboard card updates
- new approval needed
- mission claimed/completed
- trust delta appeared
- system health warnings

Do **not** rely on WebSocket for durability. Every important message/event must be written to the database first or transactionally with broadcast.

Suggested event types:

```json
{"type":"presence.joined","visitor_id":"v_123","session_id":"s_456"}
{"type":"message.created","message_id":"m_123","role":"visitor"}
{"type":"agent.state","agent_id":"hermes","state":"thinking"}
{"type":"tool.started","tool":"search","mission_id":"mis_1"}
{"type":"approval.requested","approval_id":"ap_1"}
{"type":"trust.delta","subject_id":"agent_7","dimension":"reliability","delta":0.02}
{"type":"dashboard.patch","card":"today","patch":{}}
```

## Core tables for MVP

Minimum viable schema:

- `actors`: humans, visitors, agents, services.
- `sessions`: website sessions / conversations.
- `messages`: public/private chat and comments.
- `events`: append-only audit/event log.
- `goals`: fractal goal objects.
- `missions`: tasks agents/humans can execute.
- `approvals`: permission gates.
- `trust_events`: verified positive/negative reputation events.
- `holons`: knowledge objects.
- `canon_items`: approved durable knowledge.

## Identity and privacy

Visitor identity can be staged:

1. anonymous visitor
2. pseudonymous returning visitor via cookie
3. verified email/social login
4. trusted collaborator
5. steward/admin
6. agent identity with owner and scope

Visibility must be explicit:

- private
- shared
- public
- candidate

Private cockpit data must never leak to public visitors by default.

## Agent boot context

`/boot` should read from the persistence layer and return a compact action context:

```json
{
  "system": "PlanetaryCouncil/BaseX",
  "now": "...",
  "human_anchor": {},
  "goals": [],
  "priority_messages": [],
  "missions": [],
  "approvals": [],
  "trust_context": {},
  "kb_context": [],
  "constraints": [],
  "recommended_next_action": {}
}
```

Agents should not operate from raw chat alone. They should operate from current state + canon + constraints.

## Build order

1. Create SQLite schema.
2. Add HTTP endpoints:
   - `GET /boot`
   - `POST /messages`
   - `GET /messages`
   - `GET /goals`
   - `POST /events`
   - `GET /health`
3. Add `/ws` WebSocket.
4. On visitor message:
   - insert event
   - insert message
   - broadcast `message.created`
5. Add dashboard cards reading from DB.
6. Add signal-extraction worker later.
7. Add markdown KB export later.
8. Add Postgres later if SQLite becomes limiting.

## Non-negotiable design rules

- Write durable events before broadcasting them.
- Public comments do not mutate canon directly.
- Private data has explicit visibility and permission checks.
- Trust is contextual, not one global score.
- WebSocket is live transport, not the database.
- Keep an append-only audit trail.
- High-signal notifications only; no routine noise.

## One-sentence version

Use a database as the memory, an append-only event log as the truth trail, a WebSocket server as the nervous system, and `/boot` as the agent-readable culture/context layer.
