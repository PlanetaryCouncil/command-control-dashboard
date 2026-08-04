"""Node identity for multi-writer sync: replaces "is this 127.0.0.1" with
"is this request signed by a key I trust."

Public keys are not secrets — they are, definitionally, the part meant to be
shared, so `data/trusted_nodes.json` lives alongside the other public data
files. The private key never does: it stays in an environment variable or a
local keyfile outside the repo, generated per node, never copied.

Signing is deliberately simple (HMAC over the request body with a shared
secret) rather than asymmetric crypto — see the note on SIGNING below.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

# HMAC, not Ed25519/RSA: every trusted node here is one YOU control, so a
# shared secret per node distributed once (at pairing time) is sufficient —
# the threat model is "reject requests from nodes I never approved," not
# "prove identity to a stranger who might be lying." A real federation of
# untrusted third parties would need asymmetric signatures instead; a handful
# of your own devices does not.

NODE_ID = os.environ.get("NODE_ID", "local")


def load_trusted_nodes(path) -> dict:
    """{node_id: secret}, restricted to node ids listed in trusted_nodes.json.

    Secret material always comes from NODE_SECRETS in the environment, never
    from the committed JSON file (metadata only, no secrets) — but the JSON
    file is what makes a node's entry in NODE_SECRETS actually count. This
    means revoking a node is "delete it from trusted_nodes.json," full stop,
    even if its old secret is still sitting in some environment somewhere.
    Without this check the JSON registry would be pure decoration.
    """
    import json

    try:
        registry = json.loads(Path(path).read_text())
        allowed = {n["node_id"] for n in registry.get("nodes", [])}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        allowed = set()

    secrets_env = os.environ.get("NODE_SECRETS", "")
    out = {}
    for pair in secrets_env.split(","):
        if ":" in pair:
            node_id, secret = pair.split(":", 1)
            node_id = node_id.strip()
            if node_id in allowed:
                out[node_id] = secret.strip()

    # Secrets minted at runtime by a redeemed pairing code (see app/pairing.py)
    # cannot live in the environment — nothing can edit a running process's env
    # — so they land in a file instead. Same gate applies: still worthless
    # unless the node id is in the registry, so revocation is still one line of
    # JSON. The file is 0600, gitignored, and no route serves it; `/api/files`
    # only ever reads INBOX_DIR.
    minted_path = os.environ.get("NODE_SECRETS_FILE",
                                 str(Path(path).parent / "node_secrets.json"))
    try:
        minted = json.loads(Path(minted_path).read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        minted = {}
    for node_id, secret in minted.items():
        if node_id in allowed:
            # The environment wins. A key you set by hand should never be
            # silently replaced by one an endpoint issued.
            out.setdefault(node_id, secret)
    return out


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(body: bytes, secret: str, signature: str) -> bool:
    expected = sign(body, secret)
    return hmac.compare_digest(expected, signature)


def new_node_secret() -> str:
    """For pairing a new node: run once, put the result in both nodes'
    NODE_SECRETS env var under the new node's id. Never stored in a file the
    dashboard serves."""
    return secrets.token_urlsafe(32)
