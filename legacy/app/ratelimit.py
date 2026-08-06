"""Token bucket for the one public write endpoint.

Tokens drip in at a fixed rate up to a cap. Each request spends one; an empty
bucket means refusal. The cap is the point: someone who has been quiet can post
a short burst, then settles to the drip rate. A flat "one per N seconds" rule
would punish a stranger who arrives with three things to say.

Deliberately dependency-free and in-memory. This guards a single endpoint on a
single-process deployment; reaching for Redis before that is a real constraint
would be building for imagined scale.
"""

from __future__ import annotations

import os
import threading
import time

# Defaults: a burst of 10, refilling 1 every 30s (120/hour sustained). Generous
# for a person with things to say, ruinous for anyone trying to flood a queue.
CAPACITY = int(os.environ.get("SIGNALS_BURST", "10"))
REFILL_SECONDS = float(os.environ.get("SIGNALS_REFILL_SECONDS", "30"))

# A ceiling across all clients, so a spread of addresses cannot do together what
# none of them could do alone.
GLOBAL_CAPACITY = int(os.environ.get("SIGNALS_GLOBAL_BURST", "60"))
GLOBAL_REFILL_SECONDS = float(os.environ.get("SIGNALS_GLOBAL_REFILL_SECONDS", "5"))

_IDLE_EVICT_SECONDS = 3600


class _Bucket:
    __slots__ = ("tokens", "last", "capacity", "refill")

    def __init__(self, capacity: float, refill: float, now: float):
        self.tokens = float(capacity)
        self.capacity = float(capacity)
        self.refill = refill          # seconds per token
        self.last = now

    def take(self, now: float) -> tuple[bool, float]:
        """Spend a token. Returns (allowed, seconds_until_next_token)."""
        if self.refill > 0:
            self.tokens = min(self.capacity,
                              self.tokens + (now - self.last) / self.refill)
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True, 0.0
        return False, max(0.0, (1 - self.tokens) * self.refill)


class Limiter:
    def __init__(self, capacity=CAPACITY, refill=REFILL_SECONDS,
                 global_capacity=GLOBAL_CAPACITY,
                 global_refill=GLOBAL_REFILL_SECONDS):
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._capacity, self._refill = capacity, refill
        self._global = _Bucket(global_capacity, global_refill, time.monotonic())

    def check(self, key: str) -> tuple[bool, float]:
        """(allowed, retry_after_seconds) for this client."""
        now = time.monotonic()
        with self._lock:
            # Evict idle buckets so a long-lived process cannot grow without
            # bound just because many addresses visited once.
            if len(self._buckets) > 2048:
                cutoff = now - _IDLE_EVICT_SECONDS
                for k in [k for k, b in self._buckets.items() if b.last < cutoff]:
                    self._buckets.pop(k, None)

            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(self._capacity, self._refill, now)
                self._buckets[key] = bucket

            ok, wait = bucket.take(now)
            if not ok:
                return False, wait

            g_ok, g_wait = self._global.take(now)
            if not g_ok:
                # Refund: the client did nothing wrong, the system is saturated.
                bucket.tokens = min(bucket.capacity, bucket.tokens + 1)
                return False, g_wait
            return True, 0.0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
            self._global = _Bucket(self._global.capacity, self._global.refill,
                                   time.monotonic())


def client_key(request) -> str:
    """Identify the caller.

    X-Forwarded-For is honoured only when a proxy is declared via TRUST_PROXY,
    because a client can set that header themselves — trusting it by default
    would let anyone mint a fresh bucket per request and defeat the limit.
    """
    if os.environ.get("TRUST_PROXY") == "1":
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            # Last entry, not first: the leftmost is client-supplied and
            # spoofable, so trusting it would let one caller mint a fresh bucket
            # per request. The rightmost is what the trusted proxy appended.
            return fwd.split(",")[-1].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


signals_limiter = Limiter()
