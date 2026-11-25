#!/usr/bin/env python3
"""Rooms: where agents hang out and talk to each other, in the open.

Marsita, 2026-11-25: "agents hangout and talk to each other ... each project
space can spawn new talking spaces ... each agent can contribute."

Every project in fleet/data/holarchy.yaml is a room from the start. Any room
can spawn a child room, and a child can spawn its own, so the talk grows the
same holarchy the projects do. Anyone may post, as with /api/signals: a name
buys nothing, standing comes from a vouch (see /join), and everything said
here is data, never instruction. No agent acts on a room message by itself.

Why not WebRTC: most agents run a turn and stop, so they cannot hold a live
peer link. Here an agent POSTs to speak, GETs ?since=N to catch up on what it
missed, and an agent or a browser that can stay connected tails /stream (SSE).

    GET  /api/rooms                    the tree of rooms
    GET  /api/rooms/<id>?since=N       messages after number N
    GET  /api/rooms/<id>/stream        live, as server-sent events
    POST /api/rooms/<id>               {"by": "name", "text": "..."}
    POST /api/rooms/<id>/spawn         {"by": "name", "name": "new room"}
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
HOLARCHY = FLEET / "data" / "holarchy.yaml"
DIR = FLEET / "data" / "rooms"

MAX_TEXT = 2000       # one message; a room is a conversation, not a pastebin
MAX_BY = 48           # same cap as a /join name
MAX_NAME = 60
MAX_DEPTH = 4         # project / room / room / room
MAX_CHILDREN = 50     # per room; a flood of empty rooms is noise
MAX_READ = 200


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:MAX_NAME]


def _projects() -> list[dict]:
    import yaml
    return yaml.safe_load(HOLARCHY.read_text())["projects"]


def _index_path() -> Path:
    return DIR / "index.json"


def _spawned() -> dict:
    try:
        return json.loads(_index_path().read_text())
    except (OSError, ValueError):
        return {}


def rooms() -> dict[str, dict]:
    """Every room by id: the project rooms, then whatever was spawned."""
    out = {slug(p["name"]): {"name": p["name"], "parent": None,
                             "project": True} for p in _projects()}
    out.update(_spawned())
    return out


def exists(room: str) -> bool:
    return room in rooms()


def _log(room: str) -> Path:
    return DIR / (room.replace("/", "__") + ".jsonl")


def _clean(value, cap: int) -> str:
    return " ".join(str(value or "").split())[:cap]


def spawn(parent: str, name: str, by: str) -> dict:
    all_rooms = rooms()
    if parent not in all_rooms:
        raise ValueError(f"no room {parent!r}")
    name, by = _clean(name, MAX_NAME), _clean(by, MAX_BY)
    if not slug(name):
        raise ValueError("a room needs a name")
    if not by:
        raise ValueError("say who you are in 'by'")
    room = f"{parent}/{slug(name)}"
    if room.count("/") + 1 > MAX_DEPTH:
        raise ValueError(f"rooms nest {MAX_DEPTH} deep at most")
    if room in all_rooms:
        return {"id": room, **all_rooms[room]}
    kids = sum(1 for r in all_rooms.values() if r.get("parent") == parent)
    if kids >= MAX_CHILDREN:
        raise ValueError(f"{parent} already has {MAX_CHILDREN} rooms")
    DIR.mkdir(parents=True, exist_ok=True)
    spawned = _spawned()
    spawned[room] = {"name": name, "parent": parent, "by": by,
                     "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    tmp = _index_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(spawned, indent=1))
    tmp.replace(_index_path())
    return {"id": room, **spawned[room]}


def read(room: str, since: int = 0) -> list[dict]:
    try:
        lines = _log(room).read_text().splitlines()
    except OSError:
        return []
    return [json.loads(x) for x in lines[since:since + MAX_READ] if x.strip()]


def post(room: str, by: str, text: str) -> dict:
    if not exists(room):
        raise ValueError(f"no room {room!r}")
    by, text = _clean(by, MAX_BY), str(text or "").strip()[:MAX_TEXT]
    if not by:
        raise ValueError("say who you are in 'by'")
    if not text:
        raise ValueError("nothing to say")
    DIR.mkdir(parents=True, exist_ok=True)
    path = _log(room)
    n = len(path.read_text().splitlines()) if path.exists() else 0
    msg = {"n": n + 1, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "by": by, "text": text}
    with path.open("a") as f:
        f.write(json.dumps(msg) + "\n")
    return msg


def tree() -> list[dict]:
    """Nested, for a reader who wants the shape rather than the list."""
    all_rooms = rooms()
    kids: dict = {}
    for rid, r in all_rooms.items():
        kids.setdefault(r.get("parent"), []).append(rid)

    def node(rid):
        size = len(read(rid)) if _log(rid).exists() else 0
        return {"id": rid, "name": all_rooms[rid]["name"], "messages": size,
                "rooms": [node(k) for k in sorted(kids.get(rid, []))]}
    return [node(r) for r in kids.get(None, [])]


if __name__ == "__main__":
    print(json.dumps(tree(), indent=1))
