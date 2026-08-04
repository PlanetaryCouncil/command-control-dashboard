"""Durable op logs, one JSONL file per resource, plus reconciliation into the
existing read-projection files (life.json / horizons.json).

Why append to a file rather than rewrite it: an op log's entire value is that
it is add-only. A node that crashes mid-write leaves a truncated last line at
worst, never a corrupted history — recovery is "drop the last line if it
doesn't parse," never "restore from backup."
"""

from __future__ import annotations

import json
from pathlib import Path

from app.sync import Clock, Conflict, Op, OpLog, make_ops


class OpLogStore:
    def __init__(self, path: Path, node_id: str):
        self.path = path
        self.node_id = node_id
        self.log = OpLog()
        self._load()
        self.clock = Clock(node_id)

    def _load(self) -> None:
        if not self.path.exists():
            return
        ops = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ops.append(Op.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                continue  # a truncated last line from a crash — skip, don't fail to boot
        self.log.merge(ops)

    def record(self, resource: str, target_id: str, fields: dict) -> list[Conflict]:
        """Write local changes: append ops, persist, merge into memory."""
        seq0 = self.log.count_for_node(self.node_id)
        ops = make_ops(self.clock, resource, target_id, fields)
        # make_ops starts seq at 1 each call — offset so seq is unique across
        # this node's whole history, since count_for_node is what a restarted
        # process uses to resume numbering.
        ops = [
            Op(o.node_id, seq0 + i + 1, o.hlc, o.resource, o.target_id, o.field, o.value)
            for i, o in enumerate(ops)
        ]
        conflicts = self.log.merge(ops)
        self._append(ops)
        return conflicts

    def receive(self, remote_ops: list[dict]) -> list[Conflict]:
        """Absorb ops pushed by another node."""
        ops = [Op.from_dict(d) for d in remote_ops]
        for op in ops:
            self.clock.observe(op.hlc)
        new_ops = [o for o in ops if not self.log.has(o.id)]  # only what's actually new
        conflicts = self.log.merge(ops)
        if new_ops:
            self._append(new_ops)
        return conflicts

    def _append(self, ops: list[Op]) -> None:
        if not ops:
            return
        with self.path.open("a") as fh:
            for op in ops:
                fh.write(json.dumps(op.to_dict()) + "\n")

    def project(self, resource: str) -> dict:
        return self.log.project(resource)


def reconcile_into(target_list: list[dict], id_key: str, projection: dict) -> list[str]:
    """Apply an op-log projection onto a list of dicts keyed by id_key.
    Returns the ids actually touched, so callers know what to re-timestamp."""
    by_id = {item.get(id_key): item for item in target_list}
    touched = []
    for target_id, fields in projection.items():
        item = by_id.get(target_id)
        if item is None:
            continue
        if any(item.get(f) != v for f, v in fields.items()):
            item.update(fields)
            touched.append(target_id)
    return touched
