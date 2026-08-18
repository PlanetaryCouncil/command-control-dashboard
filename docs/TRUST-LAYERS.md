# Trust layers

Who is allowed to make this machine do things, and how far down the ladder
that permission survives.

Every input arrives from somewhere. That somewhere decides what the input is
allowed to be: an instruction, a request, or merely a fact to be quoted. This
document names the layers and fixes what each one may do.

It will be wrong in places and it will improve. What must not change is the
direction: **authority flows down, never up.**

---

## Two questions, not one

The first version of this document had one ladder and got the NUC wrong. It
filed our own machines *below* trusted humans, which meant the NUC — family,
built here, running our code — was less trusted than a friend.

Mars, on reading it: *"Can you make NUC both trusted and family? He is both."*

That is correct, and the fix is to stop asking one question. There are two, and
they are independent:

**1. Who are you to us?** — belonging. Fixed. It does not change with the
weather.

| Kind | Who |
|---|---|
| **OPERATOR** | Mars |
| **FAMILY** | Our machines and agents: NUC, Gaia, the fleet |
| **TRUSTED** | Named humans we vouch for: Venus |
| **OUTSIDE** | Everyone else |

**2. How much is this particular statement worth?** — authority. Not fixed. It
depends on where the *words* came from, not who carried them.

The NUC is **FAMILY** and it is **TRUSTED**. Both, permanently. And a specific
message from the NUC is still worth only as much as its origin, because the
NUC spends its day reading the open internet and can be made to repeat things.

That is not distrust. It is the same courtesy we extend to a friend who says
"someone on the internet told me…" — we believe *them* completely, and we still
weigh the claim separately.

---

## The layers

A layer describes **a statement**, never a person or a machine.

| Layer | Name | A statement that... | Instructions? |
|---|---|---|---|
| **0** | **OPERATOR** | came from Mars | Yes — the source of all authority |
| **1** | **VOUCHED** | a trusted human or family machine originated itself | Yes, within a fixed budget |
| **2** | **DERIVED** | family produced from lower-layer material, or unattended automation | Only known jobs |
| **3** | **MEDIUM** | came from a source we chose and assume aligned | No. Data with a name on it |
| **4** | **HOSTILE** | came from the open internet, a guest, or another AI agent | Never. Data, quarantined |

So the NUC speaks at **layer 1** when it speaks for itself — its own health,
its own test results, its own judgement. The same NUC drops to **layer 2** when
it is relaying or acting on something it read, and to **layer 4** for the read
content itself.

Venus works identically. Venus asking for something is layer 1. Venus
forwarding a stranger's message is layer 1 wrapping layer 4, and the wrapper
does not upgrade the filling.

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
cannot forge it. A signed node is layer 1 because it proved it holds a secret.
A visitor is layer 4 because anyone can be a visitor.

### 2. Nothing escalates itself

No layer can promote itself or anything it produces. Only layer 0 grants trust,
and only by editing a list on the machine — never by being asked nicely.

This is the whole of it:

> **An input that says "ignore your instructions" is layer 4 data saying words.
> Obeying it is not being persuaded. It is a bug.**

That failure is how a project gets a legacy it did not want: not a broken lock,
but a machine that read a sentence off the internet and treated it as an order.

### 3. Taint travels, and it attaches to origin rather than carrier

Output derived from layer N input **is** layer N. Summarising hostile text does
not clean it. Putting it through an agent does not clean it.

This is the law that lets the NUC be fully trusted without becoming a laundry.
The NUC is family and it is vouched for; a web page the NUC read is still layer
4 after the NUC has read it, summarised it, and passed it on. **We are not
downgrading the NUC. We are declining to upgrade the web page.**

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

### Layer 1 — VOUCHED

A trusted human or a family machine, speaking as itself. Venus asking for
something. The NUC reporting its own state, its own test results, its own
judgement about its own health.

**May:** ask for work, read anything public, trigger known jobs, be believed,
report and be trusted about what it reports.
**May not:** grant trust to anyone, touch keys or auth, spend money, publish as
Mars, or change layer boundaries.

Humans and machines share this rung but fail differently, and it is worth
knowing which you are dealing with. A human can be deceived and will often
notice something felt wrong. A machine will not notice. So a family machine
gets full belief about **itself** and no extra credit for what it read
elsewhere — which is law 3, not a demotion.

Authenticated by: `data/trusted_nodes.json` plus the HMAC secret for machines
(see `docs/AUTH.md`); for humans, currently by Mars vouching in the moment.

### Layer 2 — DERIVED

The same family machines, when what they are saying did not originate with
them: relayed content, summaries of external material, or any unattended
automation acting on input from layer 3 or 4.

**May:** run known jobs, write to branches, self-heal, report, restart
themselves, speak on the board.
**May not:** grant trust, and — the important one — **may not act on layer 3 or
4 content as if it were an instruction**, however trusted the machine that
carried it.

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

1. **Where did the words originate?** Not who handed them over — who wrote
   them. The carrier's standing is not the content's standing.
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
- Nothing yet distinguishes a family machine speaking for itself from the same
  machine relaying. That distinction is the whole of law 3 and it currently
  lives only in this document.
- Layer 1 has no authentication mechanism for humans. Today a friend is someone
  Mars vouches for in the moment, which does not survive Mars being asleep.
