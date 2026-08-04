"""Multi-writer sync: an append-only op log with field-level last-write-wins.

Scope, deliberately: this is for YOUR trusted nodes (laptop, phone, an agent
host) — not arbitrary internet peers. That rules out heavier answers:

- A full CRDT library (Automerge/Yjs) solves concurrent structural edits —
  splicing the same list from two nodes at once. Nothing here does that; a
  personal dashboard's real conflicts are "status changed on device A,
  next_action changed on device B at the same time." Field-level LWW handles
  that with no drama, so we don't carry the bigger machine.
- WebRTC transport. Its only advantage over plain HTTP is a server-less data
  plane, but you still need a signaling server to introduce two peers. With a
  handful of known nodes, exposing a sync endpoint per node is LESS
  infrastructure. Solve the protocol here; move it onto WebRTC later for free
  if arbitrary-peer discovery is ever actually needed.

What this deliberately does NOT do: track causal history (no vector clocks),
so "were these two edits actually concurrent" is answered heuristically —
different node_id touching the same field is logged as a resolved conflict
even if the two writes were hours apart. That is a documented simplification,
not an oversight: true concurrency detection needs the vector-clock machinery
this module exists to avoid.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, order=True)
class HLC:
    """(wall_ms, counter, node_id) — compared lexicographically for a total
    order across nodes with no clock synchronization. node_id as the final
    tiebreaker means two ops are never exactly equal."""

    wall_ms: int
    counter: int
    node_id: str

    def to_tuple(self) -> tuple[int, int, str]:
        return (self.wall_ms, self.counter, self.node_id)

    @staticmethod
    def from_tuple(t: list | tuple) -> "HLC":
        return HLC(int(t[0]), int(t[1]), str(t[2]))


class Clock:
    """One per node. Hands out strictly increasing HLCs even if called twice
    in the same millisecond, and even if fed a remote timestamp from the
    future (adopts it, so the local clock never falls behind a peer it has
    seen)."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        self._last = HLC(0, 0, node_id)

    def tick(self, now_ms: int | None = None) -> HLC:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        if now_ms > self._last.wall_ms:
            self._last = HLC(now_ms, 0, self.node_id)
        else:
            self._last = HLC(self._last.wall_ms, self._last.counter + 1, self.node_id)
        return self._last

    def observe(self, remote: HLC) -> None:
        """Fold a remote timestamp into local state so future local ticks
        stay ahead of anything already seen, without adopting the remote
        node_id (a clock only ever emits its own id)."""
        if remote.wall_ms > self._last.wall_ms:
            self._last = HLC(remote.wall_ms, remote.counter, self.node_id)
        elif remote.wall_ms == self._last.wall_ms and remote.counter >= self._last.counter:
            self._last = HLC(remote.wall_ms, remote.counter, self.node_id)


@dataclass(frozen=True)
class Op:
    node_id: str
    seq: int
    hlc: HLC
    resource: str       # "project" | "horizon" | ...
    target_id: str      # e.g. project id, or horizon scale
    field: str
    value: object

    @property
    def id(self) -> str:
        return f"{self.node_id}:{self.seq}"

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id, "seq": self.seq, "hlc": list(self.hlc.to_tuple()),
            "resource": self.resource, "target_id": self.target_id,
            "field": self.field, "value": self.value,
        }

    @staticmethod
    def from_dict(d: dict) -> "Op":
        return Op(
            node_id=d["node_id"], seq=d["seq"], hlc=HLC.from_tuple(d["hlc"]),
            resource=d["resource"], target_id=d["target_id"],
            field=d["field"], value=d["value"],
        )


@dataclass
class Conflict:
    key: tuple[str, str, str]
    losing_op: Op
    winning_op: Op

    def to_dict(self) -> dict:
        return {
            "resource": self.key[0], "target_id": self.key[1], "field": self.key[2],
            "overwritten": {"node": self.losing_op.node_id, "value": self.losing_op.value,
                             "hlc": list(self.losing_op.hlc.to_tuple())},
            "kept": {"node": self.winning_op.node_id, "value": self.winning_op.value,
                      "hlc": list(self.winning_op.hlc.to_tuple())},
        }


class OpLog:
    """Append-only, dedup by op id, deterministic regardless of arrival order.

    merge() is the only thing that has to be correct: feed it the same set of
    ops in any order, from any number of calls, and project() must produce
    the same result every time.
    """

    def __init__(self):
        self._ops: dict[str, Op] = {}

    def merge(self, ops: list[Op]) -> list[Conflict]:
        """Absorb ops (idempotent — re-merging the same op is a no-op) and
        return conflicts newly created by this batch, in a stable order."""
        conflicts: list[Conflict] = []
        # Sort so a batch containing both an old and a newer op for the same
        # key resolves the same way regardless of the order the caller built
        # the list in.
        for op in sorted(ops, key=lambda o: o.hlc.to_tuple()):
            if op.id in self._ops:
                continue
            self._ops[op.id] = op
            key = (op.resource, op.target_id, op.field)
            current = self._current_winner(key, exclude=op.id)
            if current is not None and current.node_id != op.node_id:
                if op.hlc.to_tuple() > current.hlc.to_tuple():
                    conflicts.append(Conflict(key, losing_op=current, winning_op=op))
                else:
                    conflicts.append(Conflict(key, losing_op=op, winning_op=current))
        return conflicts

    def _current_winner(self, key: tuple[str, str, str], exclude: str | None = None) -> Op | None:
        candidates = [
            o for o in self._ops.values()
            if (o.resource, o.target_id, o.field) == key and o.id != exclude
        ]
        return max(candidates, key=lambda o: o.hlc.to_tuple(), default=None)

    def project(self, resource: str) -> dict[str, dict]:
        """{target_id: {field: value}} — last-write-wins per field, deterministic."""
        winners: dict[tuple[str, str], Op] = {}
        for op in self._ops.values():
            if op.resource != resource:
                continue
            key = (op.target_id, op.field)
            current = winners.get(key)
            if current is None or op.hlc.to_tuple() > current.hlc.to_tuple():
                winners[key] = op

        out: dict[str, dict] = {}
        for (target_id, fld), op in winners.items():
            out.setdefault(target_id, {})[fld] = op.value
        return out

    def to_list(self) -> list[dict]:
        return [op.to_dict() for op in sorted(self._ops.values(), key=lambda o: o.hlc.to_tuple())]

    @staticmethod
    def from_list(ops: list[dict]) -> "OpLog":
        log = OpLog()
        log.merge([Op.from_dict(d) for d in ops])
        return log

    def __len__(self) -> int:
        return len(self._ops)

    def has(self, op_id: str) -> bool:
        return op_id in self._ops

    def count_for_node(self, node_id: str) -> int:
        """Ops already committed from this node — lets a node resume its own
        seq counter after a restart without persisting it separately."""
        return sum(1 for o in self._ops.values() if o.node_id == node_id)


def make_ops(clock: Clock, resource: str, target_id: str, fields: dict) -> list[Op]:
    """One field per op — the granularity conflicts are detected at."""
    ops = []
    for f, v in fields.items():
        ops.append(Op(clock.node_id, _next_seq(clock), clock.tick(), resource, target_id, f, v))
    return ops


_seq_counters: dict[str, int] = {}


def _next_seq(clock: Clock) -> int:
    n = _seq_counters.get(clock.node_id, 0) + 1
    _seq_counters[clock.node_id] = n
    return n
