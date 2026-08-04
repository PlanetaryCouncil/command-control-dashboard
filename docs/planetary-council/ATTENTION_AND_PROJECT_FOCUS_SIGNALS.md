# PlanetaryCouncil / BaseX — Attention Signals for Project Focus

## Core idea

The website should not only let visitors talk. It should reveal which projects actually attract attention.

A visitor hovering, pausing, scrolling, opening details, returning, bookmarking, commenting, or asking about a project is a signal. Over time, those signals help answer:

> Which project should Phil / Hermes / agents focus on next?

This is not vanity analytics. It is civilizational/creative market sensing: attention becomes a weak vote, deeper engagement becomes a stronger vote, verified contribution becomes an even stronger vote.

## Attention ladder

Signals should be weighted by depth:

1. **Impression** — project card appeared on screen.
2. **Hover / pause** — visitor lingered over project card.
3. **Detail open** — visitor clicked/read full project page.
4. **Scroll depth** — visitor read enough to understand.
5. **Return visit** — visitor came back to same project.
6. **Question/comment** — visitor engaged verbally.
7. **Share/save** — visitor wanted to preserve or spread it.
8. **Contact/collab offer** — visitor offers help, money, skill, intro, or feedback.
9. **Verified contribution** — visitor actually produces value.

The key metric is not raw traffic. It is qualified attention.

## Hover seconds as first signal

Hover time is a useful low-friction signal:

```text
visitor hovers project card for 0.2s = probably accidental
visitor hovers for 2–5s = interest / curiosity
visitor hovers for 10s+ = strong attention or confusion
visitor repeatedly hovers same project = notable signal
```

But hover alone is noisy. Combine it with:

- viewport visibility time
- click/open details
- scroll depth
- repeat visits
- message/comment content
- visitor trust/reputation
- referrer/source
- device type

## Project focus score

Each project can have a dynamic score:

```text
focus_score =
  0.1 * impressions
+ 1.0 * meaningful_hover_seconds
+ 5.0 * detail_opens
+ 8.0 * deep_reads
+ 10.0 * return_visits
+ 20.0 * comments_or_questions
+ 40.0 * collaboration_offers
+ 100.0 * verified_contributions
```

Then adjust by quality:

- spam/bot traffic downweighted
- trusted visitors upweighted
- relevant domain experts upweighted
- repeated shallow curiosity capped
- private strategic priorities can override public attention

## Database tables

### project_attention_events

```sql
create table project_attention_events (
  id integer primary key autoincrement,
  event_id text unique not null,
  project_id text not null,
  visitor_id text,
  session_id text,
  event_type text not null,
  duration_ms integer,
  metadata_json text,
  created_at text not null
);
```

Event types:

- `project.impression`
- `project.hover_start`
- `project.hover_end`
- `project.visible_time`
- `project.detail_opened`
- `project.deep_read`
- `project.returned`
- `project.question_asked`
- `project.comment_added`
- `project.shared`
- `project.collaboration_offered`
- `project.contribution_verified`

### project_focus_scores

```sql
create table project_focus_scores (
  project_id text primary key,
  raw_attention_score real not null default 0,
  qualified_attention_score real not null default 0,
  strategic_priority_score real not null default 0,
  final_focus_score real not null default 0,
  top_signal_summary text,
  updated_at text not null
);
```

## WebSocket/dashboard use

The dashboard can show live attention:

- “3 visitors currently looking at BaseX”
- “PlanetaryCouncil intro page has 42 meaningful hover seconds today”
- “Trust/reputation project got 2 collaboration offers this week”
- “Mars culture OS page has high dwell but low comments: maybe confusing or compelling”

Realtime WebSocket events:

```json
{"type":"attention.project_hover","project_id":"basex","duration_ms":4200}
{"type":"attention.project_focus_changed","project_id":"trust-layer","score":87.2}
{"type":"attention.hot_project","project_id":"agent-boot-portal","reason":"high dwell + collaboration offer"}
```

## How it helps choose focus

The system should not blindly follow attention. It should show tension between:

- what Phil says matters
- what agents think is strategically important
- what visitors are actually drawn to
- what trusted collaborators offer to help with
- what has execution momentum

Useful dashboard card:

```text
Project Focus Radar

1. Agent Boot Portal
   - Public attention: medium
   - Strategic priority: very high
   - Execution readiness: high
   - Recommendation: focus now

2. Trust/Reputation Layer
   - Public attention: high
   - Strategic priority: high
   - Execution readiness: medium
   - Recommendation: collect collaborators / write spec

3. Holonic KB
   - Public attention: low
   - Strategic priority: high
   - Execution readiness: medium
   - Recommendation: build quietly as infrastructure
```

## Guardrails

- Do not optimize only for clicks; attention can be shallow.
- Do not let public curiosity override private/core mission.
- Do not store invasive tracking data unnecessarily.
- Use privacy-preserving anonymous visitor IDs unless identity is voluntarily provided.
- Clearly disclose basic analytics if public.
- Treat attention as signal, not command.

## One-sentence version

Measure which project cards people hover over, open, revisit, ask about, and contribute to — then combine that attention with strategic priority and trust to decide what Phil/Hermes should focus on next.
