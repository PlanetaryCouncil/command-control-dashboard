# Hosting Plan

## Recommendation

Use a staged hosting path:

1. **GitHub** for source control and CI.
2. **Render / Railway / Fly.io** for fast public staging.
3. **Fly.io with volume** or a small VPS once persistent SQLite matters.
4. **Postgres** later when multi-user/concurrent writes and backups become important.

## Why not static hosting only?

This app needs:

- WebSocket server
- database writes
- Telegram webhook endpoint
- live visitor sessions

So Netlify/Vercel static hosting alone is not enough. Vercel can host serverless HTTP, but long-lived WebSockets and SQLite persistence are awkward. Use a real app server.

## Best first deployment options

### Option A — Render

Good for easiest first public staging.

- Connect GitHub repo.
- Environment: Python.
- Start command:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Caveat: free/cheap filesystem may not be durable unless using a disk. Use Postgres or persistent disk for real data.

### Option B — Railway

Good for fast app + managed Postgres later.

- Connect GitHub repo.
- Deploy from Dockerfile or Python service.
- Add volume/Postgres when ready.

### Option C — Fly.io

Good for WebSockets + persistent volume + later serious deployment.

- Deploy Dockerfile.
- Attach volume mounted at `/app/data`.
- App keeps SQLite at `/app/data/planetary_council.db`.

This is probably the cleanest “small sovereign server” path.

## Environment variables

Future required env vars:

```text
PORT=8765
PLANETARY_DB_PATH=/app/data/planetary_council.db
PUBLIC_BASE_URL=https://your-domain.example
TELEGRAM_BOT_TOKEN=secret
TELEGRAM_OWNER_CHAT_ID=YOUR-TELEGRAM-CHAT-ID
```

Do not commit real values.

## Deployment readiness checklist

Before public production:

- [ ] GitHub remote exists.
- [ ] CI passes on GitHub Actions.
- [ ] Hosting provider deploys from `main`.
- [ ] Public URL works.
- [ ] `/health` works.
- [ ] `/boot` works.
- [ ] WebSocket connects.
- [ ] Visitor messages persist.
- [ ] Attention events persist.
- [ ] Telegram bot token stored as host secret, not repo file.
- [ ] Telegram reply routing tested.
- [ ] Privacy note added for attention analytics.
- [ ] Admin/private data blocked from public routes.
- [ ] Backup/restore story exists for database.

## Immediate path

1. Initialize local git and commit MVP.
2. Create private GitHub repo `planetary-council`.
3. Push `main`.
4. Connect Render/Railway/Fly.
5. Deploy staging.
6. Wire Telegram bot webhook.
7. Test website visitor → Telegram → website visitor roundtrip.
