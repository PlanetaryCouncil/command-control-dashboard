# Security Policy

## Reporting a vulnerability

Please report security issues **privately**, not in a public issue.

Use GitHub's private vulnerability reporting: the repository's **Security** tab
→ **Report a vulnerability**. That opens a private advisory visible only to the
maintainers.

Please include: what you found, where (file and line if you can), how to
reproduce it, and the impact you think it has. A working proof-of-concept helps
but is not required.

You can expect an acknowledgement within a few days. Fixes for confirmed issues
are prioritised over feature work.

## Scope

This project is a transparent, self-hostable operations dashboard. Its design
splits **public reads** from **local-only writes/control**. The security model
that matters most:

- The public surface is intended to be read-only plus a small set of clearly
  public write endpoints (`POST /api/signals`, `POST /api/signatures/sign`).
  Everything else — terminal, chat dispatch, kill switch,
  approvals, handoffs — must be reachable **only** by a local caller.
- The trust boundary is the fleet front door (`fleet/bin/fleet.py`): it decides
  local vs remote and sanitises `X-Forwarded-For` before forwarding to the
  cockpit. A remote caller must never reach a control or local-only action.

Findings that cross that boundary — a remote caller reaching a control path,
spoofing local identity, or reading private data from a public endpoint — are
the highest priority.

## Supported versions

This project is pre-1.0 and moves fast. Security fixes are applied to the
`main` branch and the latest tagged release. There is no long-term support
branch yet.

## Operating it safely

If you self-host and expose it to the internet (e.g. via a tunnel), keep the
host patched, do not run it on a machine whose compromise you cannot afford,
and treat the "writes are local-only" boundary as load-bearing — it is the only
thing between the public and your terminal.
