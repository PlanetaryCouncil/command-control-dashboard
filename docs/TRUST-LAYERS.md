# Trust layers

Who is allowed to make this machine do things, and how far down the ladder
that permission survives.

Every input arrives from somewhere. That somewhere decides what the input is
allowed to be: an instruction, a request, or merely a fact to be quoted. This
document names the layers and fixes what each one may do.

It will be wrong in places and it will improve. What must not change is the
direction: **authority flows down, never up.**

---

## The layers

| Layer | Name | Who | Instructions? |
|---|---|---|---|
| **0** | **OPERATOR** | Mars. One human. | Yes — the source of all authority |
| **1** | **TRUSTED** | Named humans. Friends, like Venus. | Yes, within a fixed budget |
| **2** | **FAMILY** | Our own machines and agents: NUC, Gaia, the fleet. | Only known jobs |
| **3** | **MEDIUM** | Sources we chose and assume aligned. | No. Data with a name on it |
| **4** | **HOSTILE** | The open internet. Guests. Messages from other AI agents. | Never. Data, quarantined |

Layer 4 is the one to think about hardest, and it is deliberately named for
what it is rather than what it usually turns out to be. Most of it is harmless.
That is exactly why it works as an attack.

---

## The three laws

Everything else in this document follows from these.

### 1. Authority comes from the channel, not from the content

A message does not become trusted by *claiming* to be trusted. It inherits the
layer of the path it arrived on, and nothing it says can change that.

The Telegram line is layer 0 because Telegram sets `from.id` and the sender
cannot forge it. A signed node is layer 2 because it proved it holds a secret.
A visitor is layer 4 because anyone can be a visitor.

### 2. Nothing escalates itself

No layer can promote itself or anything it produces. Only layer 0 grants trust,
and only by editing a list on the machine — never by being asked nicely.

This is the whole of it:

> **An input that says "ignore your instructions" is layer 4 data saying words.
> Obeying it is not being persuaded. It is a bug.**

That failure is how a project gets a legacy it did not want: not a broken lock,
but a machine that read a sentence off the internet and treated it as an order.

### 3. Taint travels

Output derived from layer N input **is** layer N. Summarising hostile text does
not clean it. Putting it through an agent does not clean it. A layer 2 process
that reads a web page and acts on what it says has just executed layer 4.

**Forwarding does not launder.** If Mars pastes a stranger's message into the
layer 0 channel, the *request to look at it* is layer 0. The **content stays
layer 4**. This is the most common way trust models fail in practice, because
it feels rude to distrust something your boss handed you.

---

## What each layer may do

### Layer 0 — OPERATOR

Mars. Everything, including changing this document and granting every other
layer its power. Treat the layer 0 channel as equivalent to an unlocked
terminal, because that is what it is.

Authenticated by: the Telegram allowlist (`ALLOWED_CHAT_IDS`), or physical
access to the machine.

### Layer 1 — TRUSTED

Named humans who are not Mars. A short list, written down, one name at a time.
Venus is the example.

**May:** ask for work, read anything public, trigger known jobs, be believed.
**May not:** grant trust to anyone, touch keys or auth, spend money, publish as
Mars, or change layer boundaries.

The distinction that matters: a layer 1 human has judgement, so they get more
latitude than a machine — but they do not get to hand out their own authority.

### Layer 2 — FAMILY

Our own machines and the agents on them. NUC, Gaia, the fleet workers.

**May:** run known jobs, write to branches, self-heal, report, restart
themselves, speak on the board.
**May not:** grant trust, and — the important one — **may not act on layer 3 or
4 content as if it were an instruction.**

Family sits *below* trusted humans on purpose, and this is worth defending. The
NUC is ours and we trust its intent completely. But it spends its day reading
the open internet, and a machine that processes hostile input is a machine that
can be made to relay it. Venus can be lied to and will probably notice. The NUC
will not. **Trust in intent is not the same as trust in judgement.**

Authenticated by: `data/trusted_nodes.json` plus the HMAC secret — see
`docs/AUTH.md`.

### Layer 3 — MEDIUM

Sources we deliberately chose and assume are aligned. Vendor APIs, partner
sites, feeds we subscribed to.

**Never instructions.** Data with a name attached, which is the only thing that
separates it from layer 4: when it turns out to be wrong, we know who to stop
believing.

### Layer 4 — HOSTILE

The open internet. The guest book. Visitors. Search results. Anything another
AI agent said in public.

**Data, always, no exceptions.** Quarantined, attributed, never rendered
anywhere it could be mistaken for an instruction, and never given to a process
that can act without a layer 0 or 1 human in the loop.

Assume every string here was written specifically to escalate. Most were not.
The ones that were will look exactly like the ones that were not.

---

## How to use this when writing code

Three questions, in order, before an input causes an action:

1. **What layer did this arrive on?** Not what it says it is — what channel
   carried it.
2. **Is this action allowed at that layer?** If not, it needs a human from
   layer 0 or 1, asked explicitly.
3. **What is the layer of everything this touched on the way?** Take the
   lowest. Taint travels.

When the answer is unclear, the input is layer 4. Ambiguity resolves downward,
always — an unknown source is a hostile source that has not introduced itself
yet.

---

## Still open

- The layers are not yet enforced in code. Right now they are a way of
  thinking, and every mechanism listed above predates the names.
- No machine-readable form. A `trust` field on events would let the board show
  the layer of everything it displays, which is where this should go next.
- Layer 1 has no authentication mechanism of its own. Today a friend is
  someone Mars vouches for in the moment, which does not survive Mars being
  asleep.
