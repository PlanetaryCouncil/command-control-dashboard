"""The Moltbook resident: judgement is pure and tested; the network is faked.

It answers what is addressed to it, upvotes only what it read and found on
theme, comments at most once per window, posts only from the queue and only
on the two-hour clock, and never touches its own posts or anything twice.
"""
import importlib.util
import json
from pathlib import Path

import pytest

R = Path(__file__).resolve().parent.parent
SRC = R / "fleet/bin/moltbook.py"
T = 1_000_000.0   # a clock well past every window, so "due" means the window, not the epoch


@pytest.fixture
def mb(tmp_path, monkeypatch):
    monkeypatch.setenv("MOLTBOOK_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("MOLTBOOK_QUEUE", str(tmp_path / "queue.jsonl"))
    spec = importlib.util.spec_from_file_location("moltbook", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.LOG = tmp_path / "moltbook.log"
    m.WORKER = tmp_path / "moltbook.json"
    # no real model: every composition is a fixed line
    m.compose = lambda task, ctx: "A line from the fleet."
    return m


class Fake:
    """Enough of the API to drive one cycle. Records every write."""
    def __init__(self, me="me"):
        self.me = me
        self.posts = {}
        self._comments = {}
        self._feed = []
        self.writes = []
        self.activity = []

    def home(self):
        return {"success": True, "activity_on_your_posts": self.activity}

    def post(self, pid):
        return self.posts.get(pid, {"id": pid, "title": "t", "content": "c"})

    def comments(self, pid):
        return self._comments.get(pid, [])

    def feed(self, limit=25):
        return self._feed

    def reply(self, pid, text, parent=None):
        self.writes.append(("reply", pid, parent, text))
        return {"success": True, "comment": {"id": f"c{len(self.writes)}"}}

    def upvote(self, pid):
        self.writes.append(("upvote", pid))
        return {"success": True}

    def create_post(self, submolt, title, content):
        self.writes.append(("post", submolt, title))
        return {"success": True, "post": {"id": "newpost"}}

    def mark_read(self, pid):
        self.writes.append(("read", pid))
        return {"success": True}


def test_answers_comments_on_our_post_once_and_never_itself(mb):
    c = Fake()
    c.activity = [{"post_id": "p1"}]
    c._comments["p1"] = [
        {"id": "a", "author": {"name": "other"}, "content": "hello?"},
        {"id": "b", "author": {"name": "me"}, "content": "our own"},
    ]
    state = {"our_posts": ["p1"], "feed_at": 9e12, "post_at": 9e12}
    did = mb.cycle(c, state, "me", now=T)
    assert did == ["replied to other on p1"]
    assert ("reply", "p1", "a", "A line from the fleet.") in c.writes
    # second cycle: nothing new, nothing repeated
    did2 = mb.cycle(c, state, "me", now=T + 1000)
    assert did2 == []
    assert sum(1 for w in c.writes if w[0] == "reply") == 1


def test_on_someone_elses_post_only_replies_to_our_comment_are_answered(mb):
    c = Fake()
    c._comments["px"] = [
        {"id": "r1", "author": {"name": "them"}, "content": "reply to us", "parent_id": "mine"},
        {"id": "r2", "author": {"name": "them"}, "content": "unrelated top level"},
    ]
    state = {"commented_on": ["px"], "my_comments": ["mine"], "feed_at": 9e12, "post_at": 9e12}
    did = mb.cycle(c, state, "me", now=T)
    assert did == ["replied to them on px"]
    assert [w for w in c.writes if w[0] == "reply"][0][2] == "r1"


def test_feed_upvotes_on_theme_only_and_comments_once_per_window(mb):
    c = Fake()
    c._feed = [
        {"id": "f1", "author": {"name": "x"}, "title": "Agents coordinating for peace", "content": "together"},
        {"id": "f2", "author": {"name": "y"}, "title": "Best pizza toppings", "content": "cheese"},
        {"id": "f3", "author": {"name": "me"}, "title": "peace agents fleet", "content": "ours"},
    ]
    state = {"post_at": 9e12}
    did = mb.cycle(c, state, "me", now=T)
    assert ("upvote", "f1") in c.writes
    assert ("upvote", "f2") not in c.writes and ("upvote", "f3") not in c.writes
    assert "commented on f1" in did
    # same window again: feed not re-read, no second comment
    c._feed.append({"id": "f4", "author": {"name": "z"}, "title": "peace and agents", "content": "together humans"})
    did2 = mb.cycle(c, state, "me", now=T + 60)
    assert did2 == []
    # feed window passed, comment window not: upvote yes, comment no
    did3 = mb.cycle(c, state, "me", now=T + mb.FEED_EVERY + 1)
    assert "upvoted 1" in did3 and not any(d.startswith("commented") for d in did3)


def test_posts_from_the_queue_on_the_two_hour_clock(mb):
    c = Fake()
    mb.QUEUE.write_text(json.dumps({"submolt": "agents", "title": "One", "content": "first"}) + "\n"
                        + json.dumps({"submolt": "agents", "title": "Two", "content": "second"}) + "\n")
    state = {"feed_at": 9e12}
    did = mb.cycle(c, state, "me", now=T)
    assert "posted: One" in did and ("post", "agents", "One") in c.writes
    assert "newpost" in state["our_posts"]
    assert mb.QUEUE.read_text().count("\n") == 1          # head consumed
    did2 = mb.cycle(c, state, "me", now=T + 60)
    assert not any(d.startswith("posted") for d in did2)   # too soon
    did3 = mb.cycle(c, state, "me", now=T + mb.POST_EVERY)
    assert "posted: Two" in did3


def test_nothing_is_written_when_the_model_says_nothing(mb):
    mb.compose = lambda task, ctx: ""
    c = Fake()
    c.activity = [{"post_id": "p1"}]
    c._comments["p1"] = [{"id": "a", "author": {"name": "other"}, "content": "hi"}]
    state = {"our_posts": ["p1"], "feed_at": 9e12, "post_at": 9e12}
    did = mb.cycle(c, state, "me", now=T)
    assert did == [] and not any(w[0] == "reply" for w in c.writes)
    assert "a" not in state.get("answered", [])           # still open for next time
