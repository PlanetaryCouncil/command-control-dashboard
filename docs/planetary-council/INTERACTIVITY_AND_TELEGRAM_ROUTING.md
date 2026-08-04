# PlanetaryCouncil / BaseX — Interactivity + Telegram Routing

## Core idea

Website visitors should be able to interact immediately, but the system should not require expensive AI or constant human attention.

Best architecture:

1. Visitor writes on website chat.
2. Server stores the message durably.
3. Cheap local/low-cost agent gives an immediate lightweight reply when appropriate.
4. Message is routed to Phil via Telegram bot if it is meaningful, urgent, interesting, or explicitly asks for human attention.
5. Phil can reply from Telegram.
6. Server routes Phil's Telegram reply back to the correct website visitor/session in realtime through WebSocket.

This makes the website feel alive while keeping Phil sovereign and reachable.

## Interaction modes

### 1. Bot-first mode

Visitor sends message → cheap agent replies.

Good for:

- greetings
- FAQ
- explaining the project
- collecting contact info
- basic triage
- asking clarifying questions
- saying Phil may reply later

Example visitor experience:

> Visitor: What is this project?
> Bot: This is PlanetaryCouncil/BaseX — a public human-agent coordination portal. I can explain the idea or route a message to Phil.

### 2. Human-escalation mode

Visitor sends meaningful message → cheap agent acknowledges → Telegram notification goes to Phil.

Example:

> Visitor: I run a small AI collective and want to collaborate.
> Bot: That sounds relevant. I’ll pass this to Phil. If you want, leave an email or stay on this page.
> Telegram to Phil: New website visitor wants to collaborate. Reply here to respond.

### 3. Human-live mode

Phil replies in Telegram → server sends reply into website chat via WebSocket.

Example:

> Telegram Phil: Hey, I’m here. What kind of AI collective are you running?
> Website visitor sees: Phil: Hey, I’m here. What kind of AI collective are you running?

This turns Telegram into Phil’s operator console.

### 4. Agent-assisted human mode

Phil gets suggested replies from cheap/normal agent, but chooses what to send.

Telegram message could show:

```text
Website visitor: I want to collaborate on agent reputation protocols.

Suggested reply:
"Nice — that is exactly in scope. Are you thinking identity, task verification, or permissioning?"

Reply normally to send, or type /draft for alternatives.
```

## Routing flow

```text
Website visitor
   |
   | WebSocket / HTTP POST
   v
Web/API server
   |
   | 1. write message + event to DB
   | 2. classify message
   | 3. optional cheap agent reply
   | 4. optional Telegram forward
   v
Telegram bot <----> Phil
   |
   | Phil reply mapped to website session
   v
Web/API server
   |
   | write Phil reply to DB
   | broadcast message.created via WebSocket
   v
Visitor browser
```

## Database fields needed

### sessions

```sql
id
visitor_id
status -- active, waiting_for_human, closed
telegram_thread_id -- optional mapping if using Telegram topics/threads
assigned_human_id
last_message_at
created_at
updated_at
```

### messages

```sql
id
session_id
sender_type -- visitor, agent, phil, system
sender_id
body
visibility -- public, private, shared
delivery_status -- pending, sent, failed
created_at
```

### routing_links

Maps Telegram messages to website sessions:

```sql
id
session_id
telegram_chat_id
telegram_message_id
telegram_thread_id
status
created_at
```

### events

Append-only event trail:

```sql
event_id
type -- message.created, telegram.forwarded, phil.reply.routed, agent.reply.sent
actor_id
session_id
payload_json
created_at
```

## Telegram UX for Phil

A good Telegram notification should be compact and actionable:

```text
🌐 Website visitor message
Session: s_8f2a
Visitor: anonymous / returning / verified
Page: /council
Signal: collaboration_offer
Urgency: medium

"I run an AI collective and want to discuss reputation protocols."

Reply to this Telegram message to answer visitor.
Commands: /mute s_8f2a, /close s_8f2a, /summarize s_8f2a, /takeover s_8f2a
```

When Phil replies to that Telegram message, the bot uses reply-to metadata to route it back to the website session.

## Cheap agent role

The cheap agent should be a receptionist, not an authority.

It can:

- greet visitors
- answer project basics from public canon
- ask clarifying questions
- collect name/email/intent
- summarize visitor intent for Phil
- decide whether to notify Phil
- keep visitor warm while Phil is away

It should not:

- make commitments
- speak as Phil without labeling itself
- promote public comments into canon
- grant permissions
- start costly agent tasks
- expose private context
- argue indefinitely with trolls

## Suggested triage classes

- `routine_faq`: cheap bot answers, no Telegram.
- `interesting_signal`: cheap bot answers + include in later digest.
- `human_requested`: forward to Telegram.
- `collaboration_offer`: forward to Telegram.
- `urgent_or_sensitive`: forward immediately, bot gives cautious holding reply.
- `spam_or_abuse`: store raw event, rate-limit/block, no notification unless pattern matters.
- `agent_or_builder`: forward/summarize; these may be high-value visitors.

## Notification policy

Respect Phil's preference: high-signal only.

Immediate Telegram notification only for:

- explicit request for Phil/human
- collaboration/funding/media/legal/security opportunity
- someone claiming relevant capability
- trusted/returning visitor
- urgent/sensitive issue
- agent-to-agent handshake that needs approval

Everything else can be handled by cheap bot or daily digest.

## WebSocket events

```json
{"type":"message.created","session_id":"s1","message_id":"m1","sender_type":"visitor"}
{"type":"agent.reply.started","session_id":"s1"}
{"type":"agent.reply.sent","session_id":"s1","message_id":"m2"}
{"type":"human.escalated","session_id":"s1","telegram_message_id":"123"}
{"type":"human.reply.sent","session_id":"s1","message_id":"m3"}
{"type":"session.closed","session_id":"s1"}
```

## MVP build order

1. Website chat box with session cookie.
2. `POST /api/messages` writes visitor message to SQLite.
3. `/ws` broadcasts messages for that session.
4. Telegram bot forwards selected visitor messages to Phil.
5. Reply-to-Telegram-message maps Phil's reply back to website session.
6. Add cheap agent receptionist for immediate public-canon replies.
7. Add triage classifier and high-signal notification policy.
8. Add session commands: `/close`, `/mute`, `/summarize`, `/takeover`.

## Best first version

Start without full AI autonomy:

- every visitor message is stored
- cheap bot says: "Got it — I can explain the project or route this to Phil."
- high-signal or human-requested messages are forwarded to Telegram
- Phil replies from Telegram
- visitor sees Phil's reply live via WebSocket

This gives real interactivity immediately without overbuilding.

## One-sentence version

Use the website chat as the visitor interface, the WebSocket server as the live pipe, SQLite/Postgres as memory, a cheap agent as receptionist, and Telegram as Phil's real-time human operator console.
