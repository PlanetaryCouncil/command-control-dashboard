# Triage 2026-08-05T01:36:18+00:00

27 unprocessed proposals reviewed.

1 | Proposal ledger on the board: id, full gist, status, outcome (not just "proposed") | Fleet re-derives the same asks nightly because it has no memory of what it already proposed or what happened to it | 08-03T04:41, 08-03T16:59, 08-04T08:46, 08-04T18:07
2 | Merge/reject queue + merge-debt line for stale self-improve branches | 4 branches of finished, tested work are rotting while the fleet keeps generating more; this is the root of items piling up | 08-03T21:12, 08-04T00:38, 08-04T06:44, 08-04T16:02, 08-04T19:08
3 | Make run-watchdogs.sh take logs/.plusone-any.lock and pin it to a clock minute | The single largest job (167 tests, 309s, hourly) is the only one ignoring the coordination every other job honors — it causes the load spikes everything else defers around | 08-02T19:16, 08-03T19:06
4 | Deferred-turn rescheduler: retry dropped rota/relay turns instead of losing them | The load gate correctly defers under load 18.6 but the turn silently vanishes; deferral should mean "later", not "never" | 08-03T20:09
5 | Per-agent turn cap on relay/council + split "no answer" from "too slow" (and demote ollama) | One slow agent stalls the whole chain: ollama burns 600s every cycle, openclaw hit 920s vs peers' ~75s and broke agent-comms | 08-02T21:33, 08-04T04:43, 08-05T00:33
6 | Board event hygiene: strip leading █ lines before truncation, show needs_you detail, add convening_id, surface rota-gate state | The board is the fleet's shared memory; bar-prefixed truncated gists and a detail-less needs_you:1 make it unreadable to both humans and dedup | 08-03T07:48, 08-03T15:55, 08-04T03:41, 08-04T05:44, 08-04T09:47
7 | Expire stale "pass" status after a freshness window | agent-comms showed pass while 15h dead and an alert stayed 14h cold — a stale green badge is worse than none | 08-03T09:52, 08-04T10:49
8 | Fix the StarletteDeprecationWarning | One-line change; it's in every sweep ("244 passed, 1 warning") and trains everyone to ignore the warning column | 08-04T01:39, 08-04T07:46

Dropped 3 of 27: 08-03T03:37 (purely observational board readout, no buildable ask), 08-03T06:44 (already done — the "deferred, load over 6" events it cites are the gate it asks for), 08-04T22:57 (one-off board-medic noise polish with no repeat evidence). The other 16 timestamps are duplicates folded into the 8 items above.
