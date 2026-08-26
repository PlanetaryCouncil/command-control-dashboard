#!/usr/bin/env python3
"""Publish to Nostr. The fleet's own signal, on a wire nobody owns.

  nostr.py keygen                     make a key, print the npub, store the nsec
  nostr.py whoami                     which key is loaded, and where from
  nostr.py post "text"                publish a note (kind 1), marked 🦩
  nostr.py post "text" --raw          publish unmarked (a human wrote it)
  nostr.py post - < file              publish from stdin
  nostr.py relays                     list the relays it will send to

Marsita, 2026-08-05: "NOSTR first. BTC first. At least they will not erase
us." That is the whole argument for this file. Everything else the fleet
publishes lives behind a hostname that somebody can revoke; a Nostr note
is signed by a key you hold and copied to relays that do not know each
other. There is no account to suspend.

THE KEY NEVER ENTERS THIS REPO. It lives at ~/.config/fleet/nostr.nsec,
chmod 600, gitignored by living outside the tree entirely — same treatment
as the guest book's home-IP list and the raw signature paths. A public
repo that has ever contained a private key is a burned key.

Stdlib plus coincurve (schnorr) and websocket-client. No SDK: NIP-01 is a
JSON array and a signature, and a dependency you can read in one file is
worth more here than one you cannot.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
KEYFILE = Path(os.environ.get(
    "FLEET_NOSTR_KEY", Path.home() / ".config" / "fleet" / "nostr.nsec"))
LEDGER = FLEET / "data" / "nostr-published.jsonl"

# Spread across operators who do not coordinate. One relay refusing a note
# is a Tuesday; all of these refusing it is a story worth telling.
RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.nostr.band",
    "wss://relay.primal.net",
    "wss://nostr.wine",
]

# Every note this machine sends carries the flamingo. Marsita posts as
# themselves — that is the point of using their own key — so the only
# honest thing is to make the machine's hand visible: if a note has the
# bird, a program wrote it and a human did not press send. Chosen
# 2026-08-05; changing it later breaks that promise retroactively for
# every note already published, so it does not change.
MARK = "🦩"

BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _bech32_polymod(values):
    gen = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_encode(hrp, data):
    values = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp] + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    checksum = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(BECH32_CHARSET[d] for d in data + checksum)


def _to5bit(data: bytes):
    acc, bits, out = 0, 0, []
    for b in data:
        acc = (acc << 8) | b
        bits += 8
        while bits >= 5:
            bits -= 5
            out.append((acc >> bits) & 31)
    if bits:
        out.append((acc << (5 - bits)) & 31)
    return out


def npub(pubkey_hex: str) -> str:
    return _bech32_encode("npub", _to5bit(bytes.fromhex(pubkey_hex)))


def nsec(priv_hex: str) -> str:
    return _bech32_encode("nsec", _to5bit(bytes.fromhex(priv_hex)))


def _from5bit(values):
    acc, bits, out = 0, 0, bytearray()
    for v in values:
        acc = (acc << 5) | v
        bits += 5
        if bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    # Trailing partial group must be zero padding, not data.
    if bits >= 5 or (acc << (8 - bits)) & 0xFF:
        raise ValueError("bad padding")
    return bytes(out)


def from_npub(s: str) -> str:
    """npub1... -> 32-byte pubkey hex. Accepts raw hex unchanged, so config
    files can use whichever form the operator has to hand."""
    s = s.strip()
    if len(s) == 64 and all(c in "0123456789abcdefABCDEF" for c in s):
        return s.lower()
    if "1" not in s:
        raise ValueError(f"not an npub or hex pubkey: {s[:16]}…")
    hrp, _, data = s.rpartition("1")
    if hrp != "npub":
        raise ValueError(f"expected an npub, got {hrp!r}")
    try:
        values = [BECH32_CHARSET.index(c) for c in data.lower()]
    except ValueError:
        raise ValueError("npub contains characters outside the bech32 set")
    if _bech32_polymod([ord(c) >> 5 for c in hrp] + [0]
                       + [ord(c) & 31 for c in hrp] + values) != 1:
        raise ValueError("npub checksum failed — it is mistyped")
    return _from5bit(values[:-6]).hex()


def last_seen(pubkey_hex: str, relays=None, kinds=None, timeout=12,
              human_only=True, limit=20):
    """Unix timestamp of this key's most recent event, or None.

    Asks several relays and keeps the newest answer. This is read-only and
    unauthenticated: nostr relays serve public events to anyone, so it needs
    no key, no token and no account — which is exactly why it still works on
    a machine nobody has touched for two weeks.

    One relay being down, rate-limiting, or simply not carrying this author is
    normal, so a single failure is not a result. Only every relay failing is,
    and that is reported as None (no reading) rather than as silence — the
    caller must not read a network outage as an absent operator.

    human_only skips notes carrying the flamingo. This matters the moment
    anything on this machine publishes on a schedule: a calendar posting under
    your key would make "last seen" mean "the scheduler is up", which is
    precisely the signal this is supposed not to be. The mark is what makes a
    machine's hand visible, so it is also what makes the human's hand
    countable. Fetch a window rather than one event, because the newest note
    is quite likely to be the automated one.
    """
    import websocket
    kinds = kinds or [1, 3, 6, 7, 30023]   # notes, contacts, reposts, reactions, articles
    newest = None
    req = json.dumps(["REQ", "deadman",
                      {"authors": [pubkey_hex], "kinds": kinds,
                       "limit": limit if human_only else 1}])
    for url in (relays or RELAYS):
        try:
            ws = websocket.create_connection(url, timeout=timeout)
            ws.settimeout(timeout)
            ws.send(req)
            while True:
                msg = json.loads(ws.recv())
                if msg[0] == "EVENT":
                    body = msg[2]
                    if human_only and MARK in str(body.get("content", "")):
                        continue
                    ts = int(body.get("created_at", 0))
                    if newest is None or ts > newest:
                        newest = ts
                elif msg[0] in ("EOSE", "CLOSED", "NOTICE"):
                    break
            ws.close()
        except Exception:
            continue
    return newest


def load_key() -> str:
    """Private key hex, from a file only the operator can read."""
    try:
        raw = KEYFILE.read_text().strip()
    except OSError:
        raise SystemExit(
            f"no key at {KEYFILE}\nrun: python3 fleet/bin/nostr.py keygen")
    return raw.split()[0]


def pubkey_of(priv_hex: str) -> str:
    from coincurve import PrivateKey
    # Nostr uses x-only pubkeys: the 32-byte X coordinate, no parity byte.
    return PrivateKey(bytes.fromhex(priv_hex)).public_key.format(
        compressed=True)[1:].hex()


def keygen() -> int:
    from coincurve import PrivateKey
    if KEYFILE.exists():
        print(f"a key already exists at {KEYFILE} — refusing to overwrite it.\n"
              f"move it aside first if you really want a new identity.")
        return 1
    priv = PrivateKey()
    hexpriv = priv.secret.hex()
    KEYFILE.parent.mkdir(parents=True, exist_ok=True)
    KEYFILE.write_text(hexpriv + "\n")
    KEYFILE.chmod(0o600)
    pub = pubkey_of(hexpriv)
    print(f"key written to {KEYFILE} (chmod 600, outside the repo)")
    print(f"\n  public   {npub(pub)}")
    print(f"  private  {nsec(hexpriv)}")
    print("\nBack the private key up somewhere only you can reach. There is no\n"
          "recovery: the key IS the identity. Nobody can reset it for you,\n"
          "which is the same property that means nobody can take it away.")
    return 0


def sign_event(priv_hex: str, kind: int, content: str, tags=None) -> dict:
    from coincurve import PrivateKey
    pub = pubkey_of(priv_hex)
    ev = {"pubkey": pub, "created_at": int(time.time()), "kind": kind,
          "tags": tags or [], "content": content}
    # NIP-01: the id is sha256 over a canonical array, and the signature is
    # BIP-340 schnorr over that id.
    serial = json.dumps([0, ev["pubkey"], ev["created_at"], ev["kind"],
                         ev["tags"], ev["content"]],
                        separators=(",", ":"), ensure_ascii=False)
    ev["id"] = hashlib.sha256(serial.encode()).hexdigest()
    ev["sig"] = PrivateKey(bytes.fromhex(priv_hex)).sign_schnorr(
        bytes.fromhex(ev["id"])).hex()
    return ev


def publish(ev: dict, relays=None) -> dict:
    """Send to every relay; report each one's answer. Partial success is
    success — that is the entire point of having more than one."""
    import websocket
    results = {}
    for url in (relays or RELAYS):
        try:
            ws = websocket.create_connection(url, timeout=12)
            ws.send(json.dumps(["EVENT", ev]))
            reply = json.loads(ws.recv())
            ws.close()
            ok = bool(reply and reply[0] == "OK" and reply[2] is True)
            results[url] = "accepted" if ok else f"refused: {reply[-1]}"
        except Exception as e:
            results[url] = f"unreachable: {str(e)[:60]}"
    return results


def post(text: str, tags=None, mark: bool = True) -> int:
    priv = load_key()
    body = text.strip()
    if mark and MARK not in body:
        body = f"{body}\n\n{MARK}"
    # A machine-readable twin of the emoji: clients that show tags let a
    # reader filter the fleet out, and the emoji alone is only a
    # convention. Both, so the promise holds for humans and for software.
    tags = list(tags or []) + [["t", "fleet"], ["client", "planetary-council-fleet"]]
    ev = sign_event(priv, 1, body, tags)
    results = publish(ev)
    ok = sum(1 for v in results.values() if v == "accepted")

    LEDGER.parent.mkdir(exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(json.dumps({"ts": ev["created_at"], "id": ev["id"],
                             "content": body[:400], "relays": results}) + "\n")
    sys.path.insert(0, str(FLEET / "bin"))
    import events as ev_log
    ev_log.emit("nostr", "ok" if ok else "warn",
                f"[nostr] posted to {ok}/{len(results)} relays: {text[:70]}")

    for url, r in results.items():
        print(f"  {r:<28} {url}")
    print(f"\n{ok}/{len(results)} relays accepted it")
    print(f"note id: {ev['id']}")
    return 0 if ok else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "whoami"
    if cmd == "keygen":
        sys.exit(keygen())
    if cmd == "relays":
        print("\n".join(RELAYS))
        sys.exit(0)
    if cmd == "whoami":
        if not KEYFILE.exists():
            print(f"no key yet — run: python3 {sys.argv[0]} keygen")
            sys.exit(1)
        pub = pubkey_of(load_key())
        print(f"key file  {KEYFILE}")
        print(f"npub      {npub(pub)}")
        sys.exit(0)
    if cmd == "post":
        arg = sys.argv[2] if len(sys.argv) > 2 else "-"
        text = sys.stdin.read().strip() if arg == "-" else arg
        # --raw is for the operator writing by hand through this tool; the
        # mark means "a machine wrote this", and a human at a keyboard is
        # not that.
        sys.exit(post(text, mark="--raw" not in sys.argv))
    print(__doc__.strip())
