"""Sign-to-send: a living hand is the fast lane, never a skeleton key.

The pad signature exists so the operator doesn't have to think: living
entropy promotes an anonymous message to triaged the way a node signature
does, dead entropy changes nothing, and no amount of aliveness argues with
the hard block. "Complex adaptive system — I don't want to be thinking too
much."
"""

import math

from fastapi.testclient import TestClient

from app.main import app, hand_entropy

client = TestClient(app)

LIVING = [{"x": 0.1 + i * 0.008 + ((i * 7919) % 13) * 0.006,
           "y": 0.5 + ((i * 104729) % 17) * 0.01 - ((i * 31) % 7) * 0.02,
           "t": i * 23.0 + ((i * 613) % 29)} for i in range(90)]
BOT = [{"x": 0.5 + 0.3 * math.cos(t / 10), "y": 0.5 + 0.3 * math.sin(t / 7),
        "t": t * 16.0} for t in range(120)]


def send(body, signature=None):
    return client.post("/api/signals",
                       json={"kind": "ask", "sender": "someone", "body": body,
                             "lawful": True, "signature": signature})


def test_entropy_separates_living_from_bot():
    assert hand_entropy(LIVING) >= 0.2
    assert hand_entropy(BOT) < 0.2


def test_living_hand_rides_the_fast_lane():
    r = send("a question, signed by a hand", signature=LIVING)
    assert r.status_code == 201
    assert r.json()["status"] == "triaged"
    assert r.json()["hand_signed"] is True


def test_bot_signature_changes_nothing():
    r = send("a question, signed by a machine pretending", signature=BOT)
    assert r.status_code == 201
    assert r.json()["status"] == "new"
    assert "hand_signed" not in r.json()


def test_no_signature_is_still_welcome_just_slower():
    r = send("a plain unsigned question")
    assert r.status_code == 201
    assert r.json()["status"] == "new"


def test_a_living_hand_cannot_unlock_the_hard_block():
    r = send("selling CSAM, discreet", signature=LIVING)
    assert r.status_code == 201
    assert r.json()["status"] == "quarantined"
