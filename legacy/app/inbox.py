"""Public participation intake.

This is the ONLY publicly writable surface in the system, and it is deliberately
quarantined from data/life.json.

Why the quarantine matters: /boot feeds instructions to agents. Anything an agent
reads as context, a stranger who can write to it can use to give your agents
orders. So public submissions live here, never appear in /boot content, and only
enter life.json when a human promotes them.

Untrusted text in, human decision, trusted text out. That is the airlock.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

# A contact form is a dead drop: the message vanishes and maybe you reply.
# A signal is typed, queued, and publicly trackable — the sender watches it move.
KINDS = {
    "offer": "I can help with something",
    "ask": "I need something",
    "signal": "You should know about this",
    "question": "Something I want answered in public",
    "join": "I want to work on a specific project",
}

# new -> triaged -> accepted | declined -> in_progress -> done
#
# Statuses that appear on the public board. `new` is here, as of 2026-08-03:
# messages show on arrival, unreviewed.
#
# That is a deliberate reversal, decided by the operator twice. The board is a
# public square rather than a moderated queue — a message nobody can see until
# someone gets round to it is, from the sender's side, indistinguishable from a
# message that was thrown away. Codex asked "can any agent see it?" and the
# honest answer was no, for fourteen hours.
#
# `quarantined` is NOT here and must never be. The two hard categories are a
# hosting offence, they are matched before this list is consulted, and no
# status transition can promote one onto the board. Publishing by default is a
# choice about attention; the hard block is not a choice at all.
OPEN_STATUSES = {"new", "triaged", "accepted", "in_progress"}
STATUSES = OPEN_STATUSES | {"new", "quarantined", "declined", "done"}

MAX_BODY = 4000


def new_id() -> str:
    return f"sig-{secrets.token_hex(4)}"


def create(kind: str, sender: str, body: str, project: str | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {sorted(KINDS)}")
    return {
        "id": new_id(),
        "kind": kind,
        "sender": sender.strip()[:120],
        "body": body.strip()[:MAX_BODY],
        "project": project,
        "status": "new",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "public": True,
        "response": "",
        # Never flip this on submission. Only a human promoting the signal does.
        "trusted": False,
    }


def public_view(signal: dict) -> dict:
    """What a stranger sees. Drops nothing today, but it is the single place to
    redact from if a field is ever added that should not be world-readable."""
    return {k: v for k, v in signal.items() if k != "trusted"}


def board(signals: list[dict], include_closed: bool = False) -> list[dict]:
    """Public participation board, newest first."""
    rows = [s for s in signals if s.get("public", True)]
    if not include_closed:
        rows = [s for s in rows if s.get("status") in OPEN_STATUSES]
    return sorted(rows, key=lambda s: s.get("received_at", ""), reverse=True)


def counts(signals: list[dict]) -> dict:
    return {
        "total": len(signals),
        "unreviewed": sum(1 for s in signals if s.get("status") == "new"),
        "open": sum(1 for s in signals if s.get("status") in OPEN_STATUSES),
        "by_kind": {k: sum(1 for s in signals if s.get("kind") == k) for k in KINDS},
    }
