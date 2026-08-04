# PlanetaryCouncil / BaseX MVP

A first working local prototype for the living website/agent portal.

## What exists

- FastAPI web server
- SQLite persistence layer
- append-only `events` table
- visitor sessions and messages
- cheap receptionist triage/reply
- Telegram routing hook endpoint
- project attention tracking from hover/click events
- project focus scoring
- WebSocket endpoint for live session updates
- `/boot` endpoint for agent-readable context
- simple browser UI with project cards and chat box
- automated tests

## Run

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

Agent boot context:

```text
http://127.0.0.1:8765/boot
```

Health:

```text
http://127.0.0.1:8765/health
```

## Test

```bash
uv run pytest -q
```

Current verified result: `5 passed`.

## Important endpoints

- `GET /` — simple website UI.
- `GET /boot` — compact agent boot context.
- `POST /api/messages` — store visitor message, create event, triage, agent reply, optional Telegram-forward request.
- `GET /api/sessions/{session_id}/messages` — read session transcript.
- `POST /api/attention` — record hover/click/deep-read attention signal.
- `GET /api/projects/focus` — ranked project focus scores.
- `POST /api/telegram/reply` — route Phil's Telegram reply back to a website session.
- `GET /api/events` — inspect append-only event trail.
- `WS /ws/{session_id}` — realtime visitor/session updates.

## Current data file

Default SQLite database:

```text
data/planetary_council.db
```

## Next build steps

1. Wire real Telegram bot webhook/token.
2. Add public/private visibility filtering.
3. Add actual low-cost LLM receptionist backed by public canon.
4. Add dashboard admin page for sessions, attention scores, and pending escalations.
5. Add markdown holonic KB export.
6. Add auth/admin controls before exposing publicly.
