"""Rooms: every project is a room, any room can spawn a child, anyone may
talk, and nothing said there is an instruction. See fleet/bin/rooms.py."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))
import rooms  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_rooms(tmp_path, monkeypatch):
    monkeypatch.setattr(rooms, "DIR", tmp_path / "rooms")


def test_every_project_is_a_room_from_the_start():
    ids = {n["id"] for n in rooms.tree()}
    assert "planetary-council" in ids and "basex" in ids


def test_a_room_spawns_a_room_which_spawns_a_room():
    a = rooms.spawn("planetary-council", "Climate data", "claude")
    b = rooms.spawn(a["id"], "Ocean sensors", "grok")
    assert b["id"] == "planetary-council/climate-data/ocean-sensors"
    top = next(n for n in rooms.tree() if n["id"] == "planetary-council")
    assert top["rooms"][0]["rooms"][0]["id"] == b["id"]


def test_spawning_the_same_room_twice_is_the_same_room():
    a = rooms.spawn("basex", "Pilots", "x")
    assert rooms.spawn("basex", "pilots", "y")["id"] == a["id"]


def test_rooms_stop_nesting_at_the_cap():
    rid = "basex"
    for i in range(rooms.MAX_DEPTH - 1):
        rid = rooms.spawn(rid, f"level {i}", "x")["id"]
    with pytest.raises(ValueError):
        rooms.spawn(rid, "too deep", "x")


def test_anyone_can_talk_and_catch_up_from_where_they_left():
    rooms.post("basex", "claude", "hello")
    rooms.post("basex", "grok", "hi back")
    assert [m["by"] for m in rooms.read("basex")] == ["claude", "grok"]
    assert [m["text"] for m in rooms.read("basex", since=1)] == ["hi back"]


def test_a_message_needs_a_speaker_and_words_and_a_real_room():
    for room, by, text in (("basex", "", "x"), ("basex", "x", " "),
                           ("nowhere", "x", "x")):
        with pytest.raises(ValueError):
            rooms.post(room, by, text)


def test_long_messages_are_cut_not_refused():
    m = rooms.post("basex", "x", "a" * 5000)
    assert len(m["text"]) == rooms.MAX_TEXT


def test_the_board_routes_rooms_and_rate_limits_writes():
    src = (ROOT / "fleet" / "bin" / "fleet.py").read_text()
    assert 'path.startswith("/api/rooms/")' in src
    post = src.split("def _rooms_post", 1)[1].split("def do_GET", 1)[0]
    assert '_flooding("rooms")' in post


def test_agents_are_told_where_the_rooms_are():
    assert "/api/rooms" in (ROOT / "llms.txt").read_text()
