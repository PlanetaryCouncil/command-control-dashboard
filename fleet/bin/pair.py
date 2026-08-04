#!/usr/bin/env python3
"""Pair a node by reading twelve words out loud.

A shared secret has to get from one machine to another, and the honest channels
for that are bad ones: a 43-character base64 string is hostile to a human hand —
case sensitive, `l` beside `I`, `0` beside `O`, and no way to know you mistyped
until the signature silently fails and you are debugging the wrong layer.

BIP39 exists for exactly this. Twelve words from a fixed 2048-word list carry
128 bits, which is plenty for an HMAC secret. The list is chosen so the first
four letters of every word are unique, and four bits of checksum mean a wrong
word is caught *here*, at the moment you type it, rather than surfacing later as
"the other machine won't talk to me".

    python3 fleet/bin/pair.py new codex        # this side: mint and read out
    python3 fleet/bin/pair.py accept codex     # other side: type them back

Both sides end up printing the identical NODE_SECRETS line. If they differ, one
of you misheard a word, and you will know because the checksum will usually have
caught it first.

The secret is derived from the entropy, not from the words — so a mnemonic that
round-trips wrong cannot silently produce a working-but-different key.
"""

import hashlib
import hmac
import secrets
import sys
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
WORDLIST_PATH = FLEET / "data" / "bip39-english.txt"

# The canonical BIP39 English list, pinned. A wordlist that quietly changed
# would produce mnemonics that decode differently on the two machines, which is
# the one failure this whole file exists to prevent — so it fails closed rather
# than trusting whatever is on disk.
WORDLIST_SHA256 = "2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda"

ENTROPY_BITS = 128          # -> 12 words
DERIVATION_LABEL = b"genesis-pair-v1"


def load_wordlist(path=WORDLIST_PATH):
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != WORDLIST_SHA256:
        raise SystemExit(
            f"wordlist checksum mismatch\n  expected {WORDLIST_SHA256}\n"
            f"  found    {digest}\nRefusing to pair with an unverified list.")
    words = raw.decode().split()
    if len(words) != 2048:
        raise SystemExit(f"wordlist has {len(words)} words, expected 2048")
    return words


def encode(entropy: bytes, words=None) -> list:
    """Entropy -> mnemonic. BIP39: append the first ENT/32 bits of its SHA-256,
    then read the result 11 bits at a time."""
    words = words or load_wordlist()
    if len(entropy) * 8 != ENTROPY_BITS:
        raise ValueError(f"expected {ENTROPY_BITS // 8} bytes of entropy")
    bits = "".join(f"{b:08b}" for b in entropy)
    checksum = f"{hashlib.sha256(entropy).digest()[0]:08b}"[:ENTROPY_BITS // 32]
    bits += checksum
    return [words[int(bits[i:i + 11], 2)] for i in range(0, len(bits), 11)]


def decode(mnemonic, words=None) -> bytes:
    """Mnemonic -> entropy, or a clear refusal.

    Every failure here names the specific word, because "invalid mnemonic" sends
    someone back to re-read all twelve.
    """
    words = words or load_wordlist()
    index = {w: i for i, w in enumerate(words)}
    given = mnemonic.split() if isinstance(mnemonic, str) else list(mnemonic)

    if len(given) != 12:
        raise ValueError(f"expected 12 words, got {len(given)}")
    for w in given:
        if w not in index:
            near = [c for c in words if c.startswith(w[:4])][:3]
            hint = f" — did you mean {', '.join(near)}?" if near else ""
            raise ValueError(f"{w!r} is not in the wordlist{hint}")

    bits = "".join(f"{index[w]:011b}" for w in given)
    entropy = bytes(int(bits[i:i + 8], 2) for i in range(0, ENTROPY_BITS, 8))
    expected = f"{hashlib.sha256(entropy).digest()[0]:08b}"[:ENTROPY_BITS // 32]
    if bits[ENTROPY_BITS:] != expected:
        raise ValueError("checksum failed — one of the words is wrong. "
                         "Read them back in order.")
    return entropy


def secret_from(entropy: bytes) -> str:
    """The shared secret both sides end up with.

    Derived from the entropy rather than the word string, so spacing, case, or
    a trailing newline cannot produce two different keys from the same twelve
    words. Not a BIP32 seed and not pretending to be one — this is an HMAC
    secret for signing requests between two machines you own.
    """
    return hmac.new(DERIVATION_LABEL, entropy, hashlib.sha256).hexdigest()


def new_pairing():
    entropy = secrets.token_bytes(ENTROPY_BITS // 8)
    return encode(entropy), secret_from(entropy)


def _print_pairing(node_id, mnemonic, secret):
    print()
    for row in range(4):
        line = "   ".join(f"{i + 1:>2}. {mnemonic[i]:<9}"
                          for i in (row, row + 4, row + 8))
        print("  " + line)
    print()
    print(f"  NODE_SECRETS={node_id}:{secret}")
    print()
    print("  Add the node id to data/trusted_nodes.json on both machines.")
    print("  The words are the transport. The line above is what gets stored.")


def invite_by_code(node_id, hours=6):
    """Mint a one-time code to email. The key itself never travels.

    For a far side that cannot be phoned — an agent, or a friend you only have
    an email address for. The mail carries something that expires, works once,
    and is worthless afterwards.
    """
    sys.path.insert(0, str(FLEET.parent))
    from app import pairing
    inv = pairing.invite(FLEET.parent / "data" / "pairing.json", node_id,
                         ttl_hours=hours)
    print(f"""
  Email this. It contains no secret.

    node id:  {inv['node_id']}
    code:     {inv['code']}
    expires:  {inv['expires_at'][:16].replace('T', ' ')} UTC

    Redeem once, over TLS:

      curl -X POST https://cockpit-1.tail151af.ts.net/api/pair \\
        -H "content-type: application/json" \\
        -d '{{"code": "{inv['code']}"}}'

    That returns the secret, one time only. Then read /auth to sign with it.

  If their attempt says "already redeemed", somebody else used it first.
  That is the interception detector — treat it as one.
""")


USAGE = """
  Give an agent a password. Three ways, depending on what channel you have.

    pair.py invite  <name> [hours]   no channel — email a one-time code
    pair.py new     <name>           a voice    — read twelve words out
    pair.py accept  <name>           the far side of `new` — type them back

  All three end with the same thing: one line of NODE_SECRETS on each machine.
  The auth itself is the same either way; only the handover differs.
"""


def main(argv):
    if len(argv) < 3 or argv[1] not in ("new", "accept", "invite"):
        # Printed a slice of the module docstring before, which silently stopped
        # matching the commands the moment `invite` was added — so the one
        # message a confused user sees was the one thing nobody was testing.
        print(USAGE)
        return 2

    mode, node_id = argv[1], argv[2]

    if mode == "invite":
        hours = float(argv[3]) if len(argv) > 3 else 6
        invite_by_code(node_id, hours)
        return 0

    if mode == "new":
        mnemonic, secret = new_pairing()
        print(f"\n  Pairing '{node_id}'. Read these twelve words to the other side:")
        _print_pairing(node_id, mnemonic, secret)
        return 0

    print(f"\n  Pairing '{node_id}'. Type the twelve words, separated by spaces:")
    try:
        given = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  cancelled")
        return 1
    try:
        entropy = decode(given)
    except ValueError as exc:
        print(f"\n  ✗ {exc}")
        return 1
    print("\n  ✓ checksum good")
    _print_pairing(node_id, given.split(), secret_from(entropy))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
