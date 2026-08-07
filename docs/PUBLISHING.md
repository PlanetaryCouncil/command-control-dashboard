# Publishing the cockpit from this laptop

No server, no DNS, no cloud. The laptop is the host, and when it sleeps the site
is gone. That is the intended trade, not a limitation to work around.

---

## The rule that makes it safe

A tunnel terminates **on this machine**, so every visitor reaches the app from
`127.0.0.1` — the exact address `require_local` is built to trust. Published
without a change, the cockpit would hand every stranger the operator's own
permissions, and nothing on the page would look different.

`TRUST_PROXY=1` is the switch that fixes it. Set it, and `steering_caller`
discards the socket address entirely and judges the caller by `X-Forwarded-For`
instead — the address the tunnel reports, which a visitor cannot forge past the
tunnel.

It fails closed in both directions:

| Situation | Result |
|---|---|
| `TRUST_PROXY=1`, header says a public IP | write refused |
| `TRUST_PROXY=1`, header missing | write refused — unknown is not local |
| `TRUST_PROXY` unset, visitor sends `X-Forwarded-For: 127.0.0.1` | header ignored, write refused |

Covered by `tests/test_public_tunnel.py`. **If that file is failing, do not
publish.**

---

## One port: 8787. The control paths gate themselves.

The fleet board on **8787** is the public front door; the funnel points at it.
It serves `/ws/terminal` — a real shell over a WebSocket — plus `/api/kill`,
so it splits callers instead of hiding: tailscaled stamps `X-Forwarded-For`
on every funnelled request, and any control path (`/terminal`, `/ws/terminal`,
`/chat`, `/api/kill`, ...) answers 404 to callers carrying that header. See
`CONTROL_PATHS` in `fleet/bin/fleet.py`. A stranger gets the readouts, never
the prompt.

The legacy cockpit no longer has its own process — the fleet server boots it
in-process on loopback **8770** and forwards its public routes.

---

## Running it

Tailscale is already installed. It needs no port forwarding, no router config and
no DNS, and it issues the HTTPS certificate itself.

```bash
# 1. Start the fleet server — it boots the legacy cockpit in-process and
#    sets TRUST_PROXY itself.
cd ~/projects/command-control-dashboard
.venv/bin/python3 fleet/bin/fleet.py serve 8787

# 2. Log in once, in a browser window it opens.
tailscale up

# 3. Publish the board.
tailscale funnel 8787
```

Step 3 prints the public URL — `https://<machine>.<tailnet>.ts.net`. WebSockets
work through it, so the chat stream and any live updates survive the trip.

To take it down:

```bash
tailscale funnel reset
```

---

## Checking it actually closed

From another machine, or any network that is not this laptop:

```bash
curl https://<your-url>/boot                       # 200 — reading is the point
curl -X POST https://<your-url>/api/handoffs \
     -H 'content-type: application/json' \
     -d '{"by":"stranger","changed":"nothing"}'    # must be 403
```

A `201` on the second command means `TRUST_PROXY` is not set on the process that
is actually serving. Take the funnel down before doing anything else.

---

## What a visitor can still do

Deliberately, and unchanged by any of the above:

- **Read everything.** `/`, `/boot`, `/llms.txt`, every `/api/…` GET. There is no
  private half.
- **The public writes.** Three, and none of them carries authority or reaches
  an agent's context:
  - **`POST /api/signals`** — rate limited, and quarantined behind the airlock:
    a signal never reaches an agent's context until a human writes their own
    summary of it.
  - **`POST /api/signatures/sign`** — a pointer-path signature for the wall. A
    too-regular path waits in moderation; a living hand is shown.

Everything that steers the system — handoffs, project touches, horizons,
approvals — needs the operator.

---

## Before the first publish

- `data/` holds no credentials. It never should, but check.
- `uv run pytest -q` is green, `tests/test_public_tunnel.py` included.
- The URL is public. Anything readable becomes readable by anyone, including
  crawlers, and stays cached after the laptop closes.
