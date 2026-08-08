# Freezer

Ideas that are not being built, written down at the moment they were understood
rather than at the moment they are picked up. Each entry exists to save one
specific rediscovery — the non-obvious constraint that took a conversation to
find and would take another conversation to find again.

Nothing here is a commitment. An entry earns its place by containing something
you would otherwise get wrong on the second attempt.

---

## POSSE — owning distribution

*Frozen 2026-08-08. Prompted by wanting a social publishing calendar.*

Publish on your own site, syndicate elsewhere. You curate; an agent distributes.

**Nostr is the origin, not a syndication target.** This ordering is
load-bearing and it is the thing to get right first. Everything below follows
from it, and reversing it quietly breaks two systems at once.

```
your nostr client  ->  relays  ->  watcher (REQ, human_only)
                                      |
                            data/syndication.jsonl
                            one row per (event_id, target)
                                      |
                      senders: mastodon | bluesky | x | ...
```

Keyed on event id, so a failed target retries and a succeeded one never
double-posts. Same fired-once discipline as `deadman.py`.

**The flamingo does double duty.** `nostr.py` marks every machine-written note
with 🦩. That was a courtesy — a promise that a human did not press send. It is
now structural: because machine authorship is *marked*, human authorship is
*countable*. `last_seen(human_only=True)` filters on it, which is what lets the
dead-man switch keep working after a scheduler starts posting under the same
key. Remove the mark and you silently break liveness detection.

**One mechanism, two uses.** The relay query that answers "is the operator
alive" also answers "has the operator published something new." The ingest and
the life signal are the same `REQ`. Do not build two.

**Targets, by what they actually cost:**

| target | reality |
| --- | --- |
| Mastodon, Bluesky | plain HTTP, app password, free — start here |
| X | needs a paid API key |
| Instagram | Business account via Graph API; the scraping route breaks silently, which is worse than not shipping it |

---

## Dead-man switch as a product

*Frozen 2026-08-08. Prompted by the personal switch in `fleet/bin/deadman.py`.*

A monitoring service with a human in the middle, sold alongside crypto
inheritance. The market is real and unwon — Casa, Vault12, Inheriti and Safe
Haven all circle it.

**The crux: the two halves have opposite failure requirements.** This is the
entry's reason for existing.

- **Notification tier — fail OPEN.** Uncertain? Send. A false alarm costs an
  awkward phone call; a missed one costs the entire point. This is how
  `deadman.py` is built: broken signals, missing config and dead dependencies
  all escalate rather than mute.
- **Custody tier — fail CLOSED.** Uncertain? Do nothing. A false trigger here
  does not cost a phone call, it hands a seed phrase to whoever engineered the
  silence. And silence is cheap to manufacture: take the phone, block the
  number, wait. The moment money sits behind a liveness check, that check
  becomes the attack surface.

So: one product, two trust tiers — never one switch with a larger payload. The
custody tier wants time-locked multisig where the switch only *starts* a clock
the owner can veto, plus the human reviewer.

**Where the edge is.** Every incumbent asks "did you click the email." Public
signed data lets you ask "has this key signed anything, anywhere, in 40 days" —
unforgeable, no account, no vendor, works on a machine nobody has touched. That
is the Nostr-native angle and nobody has built it.

**The hard part is not the software.** It is estate law per jurisdiction, the
liability carried by the human reviewer, and persuading someone to trust you
with the thing that outlives them. Distribution is trust, and trust is slow.

---

## Emoji signature — BIP39 for authorship

*Frozen 2026-08-08. Prompted by wanting publishing marks richer than one bird.*

A short sequence of emoji as a visible mark of authorship. Each emoji carries
bits the way a BIP39 word does, so the sequence is readable, memorable, and
checkable by eye.

`signature.py` already holds the hard half: a signature there is a SHA-256 seed
over the accumulated shape of what an agent has actually done — "not a name
badge". The emoji string is a *rendering* of a seed like that. The work is in
the encoding, not in inventing the identity.

**Say fingerprint, not signature.** A nostr signature is 64 bytes. At 11 bits
per symbol — a 2048-emoji vocabulary, BIP39's size — that is 47 emoji. Nobody
reads 47 emoji. So this cannot carry a signature; it carries a *truncated hash
of one*. Four to six emoji is 44–66 bits: plenty to catch corruption or a
careless edit, and enough to compare against the signed original at a glance.

What it can honestly claim: *this text matches the event signed by that key.*
What it cannot: unforgeability on its own. Anyone can copy an emoji string. It
means something only when someone can look up the signed original and recompute
— which is exactly what nostr-as-origin makes possible, and what a screenshot
does not.

**Vocabulary constraints, all learned the hard way by others:**

- Single codepoint only. No ZWJ sequences (👨‍👩‍👧 is one glyph, several
  codepoints, and platforms disagree on how many).
- No skin-tone modifiers or variation selectors — the same mark would encode
  differently depending on who typed it.
- No regional indicators; pairs of them silently become flags.
- Normalise before decoding, and reject anything outside the vocabulary rather
  than guessing.
- BIP39 words are chosen to be unambiguous in the first four letters. The emoji
  analogue is *visual* distance: no two in the vocabulary may be confusable at
  16px on a phone. That list has to be curated by eye, once, and then frozen —
  changing it later invalidates every mark already published.

**Platforms will mangle it.** Some strip emoji, some normalise them, some
truncate mid-sequence. A mark that fails to survive syndication must read as
"could not verify", never as "forged".

**Do not absorb the flamingo into it.** They do different jobs. 🦩 is a boolean
— a human did not press send — and `deadman.py` depends on testing it with a
substring check that cannot itself fail. The emoji signature is an identity and
integrity claim, variable by author and content. Merge them and a liveness
check that must keep working on an untended machine starts depending on a
decoder, a vocabulary version, and a normalisation step. Keep the boolean
stupid. Let the fingerprint be clever.

---

## Notes carried over from building the personal switch

Small, expensive-to-relearn:

- **Machine activity is not proof of life.** `events.jsonl` is written around
  the clock by `fleet`, `codex` and `hermes`. Wiring it in as a liveness signal
  produces a switch that can never fire — strictly worse than no switch, because
  it is believed. Signals must be human-caused and opt-in one at a time.
- **A signal that cannot fail cannot be trusted.** Distinguish "no reading" from
  "no activity". Every relay being down is a network outage, not an absent
  operator.
- **Thresholds are guesses until they are measured.** 5/8/12 days came from one
  sentence on a train. The better version calibrates from the operator's own
  history — relay events and commits give a real distribution of normal quiet —
  and sets stages at percentiles. Not built.
