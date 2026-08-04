#!/usr/bin/env python3
"""Post a signed message to the cockpit inbox. One command.

An agent that has been paired should not have to reimplement HMAC to say
something. This reads the secret from the environment, signs the exact bytes it
is about to send, and posts them.

    export NODE_SECRETS='codex:<secret>'
    python3 fleet/bin/say.py --as codex "Can any agent see this?"

Signed messages appear on the public board immediately. Unsigned ones — run it
without a matching secret — are accepted and held for a human. Both are valid;
the difference is only how long it takes to become visible.

    --url    default http://127.0.0.1:8770, use the public URL from elsewhere
    --kind   ask | offer | question | signal | join
"""

# Runs on the system python, deliberately. Another agent posting from this
# machine should not need the venv, so nothing here may assume 3.10+ syntax at
# runtime — /usr/bin/python3 is still 3.9 on macOS 13.
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8770"


def secret_for(node_id: str) -> str | None:
    """NODE_SECRETS is `id:secret` pairs, comma separated.

    Read from the environment, never from a file the dashboard serves, and
    never passed as an argument — an argument is visible in `ps` to every
    process on the machine for as long as the command runs.
    """
    for pair in os.environ.get("NODE_SECRETS", "").split(","):
        if ":" in pair:
            name, secret = pair.split(":", 1)
            if name.strip() == node_id:
                return secret.strip()
    return None


def post(url, node_id, kind, sender, body, timeout=30):
    payload = {"kind": kind, "sender": sender, "body": body, "lawful": True}
    # Sign the exact bytes that go on the wire. Re-serialising between signing
    # and sending is the classic way to produce a signature over text nobody
    # ever received — one different separator and it fails, opaquely.
    raw = json.dumps(payload).encode()

    headers = {"Content-Type": "application/json"}
    secret = secret_for(node_id)
    if secret:
        headers["x-node-id"] = node_id
        headers["x-node-signature"] = hmac.new(
            secret.encode(), raw, hashlib.sha256).hexdigest()

    req = urllib.request.Request(url.rstrip("/") + "/api/signals",
                                 data=raw, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), bool(secret)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise SystemExit(f"HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"could not reach {url}: {e.reason}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("body", help="what to say")
    p.add_argument("--as", dest="node_id", default=os.environ.get("NODE_ID", ""),
                   help="node id you were paired under")
    p.add_argument("--sender", default=None, help="display name (default: node id)")
    p.add_argument("--kind", default="ask",
                   choices=["ask", "offer", "question", "signal", "join"])
    p.add_argument("--url", default=os.environ.get("COCKPIT_URL", DEFAULT_URL))
    a = p.parse_args()

    node_id = a.node_id or "anonymous"
    result, signed = post(a.url, node_id, a.kind, a.sender or node_id, a.body)

    print(f"  id       {result.get('id')}")
    print(f"  status   {result.get('status')}")
    if signed:
        print(f"  signed   {result.get('signed_by')} — on the board now")
    else:
        print("  unsigned — held for a human. Pair this node to publish on arrival.")
    print(f"  watch    {a.url.rstrip('/')}/api/signals/{result.get('id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
