"""One-time codes, so a credential never travels in an email.

The problem this solves: two machines that have no secure channel between them.
Reading twelve words down a phone works when the far side is a person. When it
is an agent, or when all you have is email, there is nothing to read to.

So the email carries an *invitation*, not a key:

    node id:  bright-otter
    code:     4417-bright-otter-9f2c   (expires 18:00)
    post to:  https://[redacted-host]/api/pair

The far side redeems the code over TLS and receives a freshly minted secret.
The code then burns. What was in the email is worthless the moment it is used,
and worthless anyway after the expiry.

Three properties, and each one is doing a job:

**Single use.** If someone intercepts the mail and redeems first, your friend's
attempt fails. You do not merely hope nobody read it — you find out that
somebody did. That is the only interception detector available on a channel you
do not control.

**Expiry.** Bounds the window in which a stolen mail is worth anything. An
invitation that never expires is a password with extra steps.

**Hashed at rest.** `data/pairing.json` stores SHA-256 of the code, never the
code. A file that can mint credentials is itself a credential; this one cannot
be replayed by whoever reads it.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Short, unambiguous, and readable down a phone if it comes to that. No l/1/0/O.
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
DEFAULT_TTL_HOURS = 6


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_code() -> str:
    """Three groups of five: ~74 bits. Guessing is not a threat model here —
    the code is short-lived and single-use — but it costs nothing to be past
    the point where a script could try."""
    raw = "".join(secrets.choice(ALPHABET) for _ in range(15))
    return f"{raw[:5]}-{raw[5:10]}-{raw[10:]}"


def fingerprint(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()


def load(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {"invites": []}


def save(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)
    path.chmod(0o600)


def invite(path: Path, node_id: str, ttl_hours: float = DEFAULT_TTL_HOURS) -> dict:
    """Mint a code for `node_id`. Returns the code — the only time it exists."""
    node_id = node_id.strip()
    if not node_id:
        raise ValueError("node id is required")

    code = new_code()
    data = load(path)
    # One live invite per node. Minting a second silently invalidates the first,
    # which is what you want when you have just emailed the wrong address.
    data["invites"] = [i for i in data.get("invites", [])
                       if i.get("node_id") != node_id]
    data["invites"].append({
        "node_id": node_id,
        "code_sha256": fingerprint(code),
        "created_at": now().isoformat(),
        "expires_at": (now() + timedelta(hours=ttl_hours)).isoformat(),
        "redeemed_at": None,
        "redeemed_from": None,
    })
    save(path, data)
    return {"node_id": node_id, "code": code,
            "expires_at": data["invites"][-1]["expires_at"]}


def redeem(path: Path, code: str, from_addr: str = "") -> dict:
    """Burn a code and mint a secret. Raises ValueError with a reason.

    The reasons are deliberately distinguishable — expired, already redeemed,
    unknown — because the operator needs to tell "my friend was slow" from
    "somebody else got there first", and those are different incidents.
    """
    fp = fingerprint(code)
    data = load(path)

    for entry in data.get("invites", []):
        if entry.get("code_sha256") != fp:
            continue
        if entry.get("redeemed_at"):
            raise ValueError(
                f"already redeemed at {entry['redeemed_at']} "
                f"from {entry.get('redeemed_from') or 'unknown'}")
        try:
            expires = datetime.fromisoformat(entry["expires_at"])
        except (KeyError, ValueError):
            raise ValueError("invite is malformed")
        if now() > expires:
            raise ValueError(f"expired at {entry['expires_at']}")

        secret = secrets.token_hex(32)
        entry["redeemed_at"] = now().isoformat()
        entry["redeemed_from"] = from_addr or "unknown"
        entry["secret_sha256"] = hashlib.sha256(secret.encode()).hexdigest()
        save(path, data)
        return {"node_id": entry["node_id"], "secret": secret}

    raise ValueError("unknown code")


def live(path: Path) -> list:
    """Invites that could still be redeemed. For showing the operator."""
    out = []
    for entry in load(path).get("invites", []):
        if entry.get("redeemed_at"):
            continue
        try:
            if now() > datetime.fromisoformat(entry["expires_at"]):
                continue
        except (KeyError, ValueError):
            continue
        out.append({"node_id": entry["node_id"],
                    "expires_at": entry["expires_at"]})
    return out
