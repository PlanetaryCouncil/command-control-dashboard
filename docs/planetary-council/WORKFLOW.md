# PlanetaryCouncil / BaseX Development Workflow

## Workflow principle

Move fast, but keep the loop clean:

```text
idea → small issue/task → branch → test → code → run locally → commit → PR/CI → deploy preview → production
```

Do not let the repo become a pile of experiments. Every change should either improve the live portal or be parked in docs/plans.

## Branches

- `main` — always deployable.
- `feat/<short-name>` — new features.
- `fix/<short-name>` — bug fixes.
- `docs/<short-name>` — docs/plans.
- `spike/<short-name>` — throwaway experiments; merge only if cleaned up.

## Commit style

Use conventional commits:

```text
feat: add Telegram routing webhook
fix: persist attention score updates atomically
docs: add deployment workflow
test: cover WebSocket session messages
chore: add Dockerfile
```

## Quality gate before commit

Run:

```bash
uv run pytest -q
```

For server smoke test:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/boot
```

## PR template mentally

Each PR should answer:

- What changed?
- Why now?
- How was it tested?
- Any secrets/migrations/deployment changes?
- Any privacy/trust implications?

## Deployment environments

### Local

SQLite file in `data/planetary_council.db`.

### Staging

Public-but-low-risk host. Used for testing website chat, WebSocket, Telegram routing, and attention analytics.

### Production

Only after:

- auth/admin boundaries exist
- public/private visibility filtering works
- Telegram secret storage is configured
- backups are understood
- privacy disclosure exists for attention analytics

## High-signal product loop

1. Ship smallest real surface.
2. Watch attention/project focus data.
3. Route only high-signal visitor messages to Telegram.
4. Convert repeated questions into public FAQ/canon candidates.
5. Convert collaboration offers into missions.
6. Add trust/reputation only after there are real interactions to score.

## Guardrails

- Never commit `.env` or tokens.
- Never expose private cockpit data publicly.
- Visitor comments are raw signals, not canon.
- SQLite is fine for MVP, but production needs backups/persistence volume.
- WebSocket is live transport, not the source of truth.
- `main` should always pass tests.
