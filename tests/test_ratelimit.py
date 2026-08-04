import pytest
from fastapi.testclient import TestClient

from app import ratelimit
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh():
    ratelimit.signals_limiter.reset()
    yield
    ratelimit.signals_limiter.reset()


def _signal(n=0):
    return {"kind": "signal", "sender": "tester", "body": f"hello {n}", "lawful": True}


def test_burst_is_allowed_then_refused():
    """The cap is the point: a quiet caller may post a burst, not a flood."""
    lim = ratelimit.Limiter(capacity=3, refill=60, global_capacity=100,
                            global_refill=0.001)
    assert [lim.check("1.2.3.4")[0] for _ in range(3)] == [True, True, True]
    allowed, retry = lim.check("1.2.3.4")
    assert allowed is False
    assert retry > 0, "a refusal must say when to come back"


def test_buckets_are_per_client():
    lim = ratelimit.Limiter(capacity=1, refill=60, global_capacity=100,
                            global_refill=0.001)
    assert lim.check("a")[0] is True
    assert lim.check("a")[0] is False
    assert lim.check("b")[0] is True, "one noisy client must not block another"


def test_tokens_refill_over_time(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: clock["t"])
    lim = ratelimit.Limiter(capacity=2, refill=10, global_capacity=100,
                            global_refill=0.001)
    assert lim.check("x")[0] and lim.check("x")[0]
    assert lim.check("x")[0] is False
    clock["t"] += 10.5
    assert lim.check("x")[0] is True, "a token should have dripped back in"


def test_global_ceiling_bounds_many_clients():
    """Many addresses together must not exceed what the system will accept."""
    lim = ratelimit.Limiter(capacity=10, refill=0.001,
                            global_capacity=5, global_refill=60)
    results = [lim.check(f"client-{i}")[0] for i in range(8)]
    assert results.count(True) == 5
    assert results.count(False) == 3


def test_global_refusal_refunds_the_client():
    """A caller refused by the global ceiling did nothing wrong; their own
    bucket must not be charged for the system being saturated."""
    lim = ratelimit.Limiter(capacity=2, refill=600,
                            global_capacity=1, global_refill=600)
    assert lim.check("solo")[0] is True
    assert lim.check("solo")[0] is False          # global exhausted
    bucket = lim._buckets["solo"]
    assert bucket.tokens >= 1, "client token should have been refunded"


def test_forwarded_header_ignored_unless_proxy_declared(monkeypatch):
    """A client can set X-Forwarded-For themselves; trusting it by default
    would let anyone mint a fresh bucket per request."""
    class Req:
        headers = {"x-forwarded-for": "9.9.9.9"}
        client = type("C", (), {"host": "1.1.1.1"})()

    monkeypatch.delenv("TRUST_PROXY", raising=False)
    assert ratelimit.client_key(Req()) == "1.1.1.1"
    monkeypatch.setenv("TRUST_PROXY", "1")
    assert ratelimit.client_key(Req()) == "9.9.9.9"


def test_endpoint_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(ratelimit, "signals_limiter",
                        ratelimit.Limiter(capacity=2, refill=60,
                                          global_capacity=100,
                                          global_refill=0.001))
    assert client.post("/api/signals", json=_signal(1)).status_code == 201
    assert client.post("/api/signals", json=_signal(2)).status_code == 201
    blocked = client.post("/api/signals", json=_signal(3))
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


def test_reads_are_never_rate_limited(monkeypatch):
    """Reads stay open forever — that is the stance, not an oversight."""
    monkeypatch.setattr(ratelimit, "signals_limiter",
                        ratelimit.Limiter(capacity=1, refill=600,
                                          global_capacity=1, global_refill=600))
    client.post("/api/signals", json=_signal(1))
    for _ in range(5):
        assert client.get("/api/signals").status_code == 200
        assert client.get("/boot").status_code == 200
