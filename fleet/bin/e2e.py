#!/usr/bin/env python3
"""End-to-end test against the real fleet: real agents, real infrastructure.

Unit tests prove functions behave. They cannot tell you the pipeline is wired
together, because every part can pass in isolation while nothing reaches the
other end.

So each check carries a **canary** — a token unique to this run, injected at one
end and asserted at the other. A canary that arrives proves the path was
actually traversed. A green check with no canary proves only that something
returned without erroring, which is the thing that lulls you.

Runs against live infrastructure and cleans up after itself. It writes only its
own throwaway worker file and event-log lines.

One honest caveat: the kill-switch check exercises the real endpoint, which
kills *all* fleet work — including the live board. That is the switch behaving
correctly, and launchd restarts it within seconds, but it does mean roughly ten
seconds of dashboard downtime per run. The check asserts the recovery rather
than glossing over it.

  e2e.py [--quick]        skip the checks that spend an agent turn
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FLEET / "bin"))

import events as ev  # noqa: E402

CANARY = "E2E-" + secrets.token_hex(4).upper()
RESULTS: list[dict] = []


def check(name: str, detail: str = ""):
    """Decorator-free recorder: call ok()/fail() from inside a step."""
    def record(passed, note=""):
        RESULTS.append({"check": name, "pass": passed, "note": note or detail})
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {note}" if note else ""))
    return record


def serve_test_instance(port: int, sig_file: Path | None = None):
    """Own server instance, so HTTP assertions do not depend on reaching the
    launchd-managed one (a sandboxed caller often cannot).

    sig_file isolates the signature wall (FLEET_SIGNATURES) so the signature
    canary's marks are written to a throwaway file, never the live wall."""
    env = dict(os.environ)
    if sig_file is not None:
        env["FLEET_SIGNATURES"] = str(sig_file)
    p = subprocess.Popen([sys.executable, str(FLEET / "bin" / "fleet.py"), "serve", str(port)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    for _ in range(40):
        time.sleep(0.25)
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{port}/workers.json", timeout=1)
            return p
        except Exception:
            continue
    return p


def get(port: int, path: str, timeout=15) -> str:
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return r.read().decode(errors="replace")


def post(port: int, path: str, body: dict, headers=None, timeout=15):
    """POST JSON; return (status, text). HTTP errors are returned, not raised,
    so a check can assert on a 403/422 the same way it asserts on a 200."""
    import urllib.error
    import urllib.request
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                data=json.dumps(body).encode(), headers=h,
                                method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def _jagged_path(n=60):
    """A living-hand pad path: zigzagging direction, irregular stride and
    timing — the three things hand_entropy rewards. Deterministic so the check
    is not flaky."""
    pts, t = [], 0.0
    for i in range(n):
        pts.append({"x": (i % 2) * 37.0 + (i * 0.9 % 11),
                    "y": (i * i % 31) + (i % 4) * 6.0,
                    "t": t})
        t += 7.0 + (i * 13 % 17)
    return pts


def _straight_path(n=60):
    """A dead-straight, even-timed path: entropy 0.0 — the spam the gate exists
    to catch."""
    return [{"x": i * 2.0, "y": i * 2.0, "t": i * 10.0} for i in range(n)]


# --------------------------------------------------------------------- checks
def check_event_pipeline(port):
    """Canary: an event emitted here must surface in the rendered dashboard."""
    rec = check("event reaches the dashboard")
    ev.emit("fleet", "info", f"[e2e] canary {CANARY}")
    time.sleep(0.4)

    on_disk = CANARY in (FLEET / "events.jsonl").read_text(errors="replace")
    if not on_disk:
        return rec(False, "never reached events.jsonl")
    try:
        html = get(port, "/one")
    except Exception as e:
        return rec(False, f"dashboard unreachable: {e}")
    rec(CANARY in html, "canary rendered" if CANARY in html
        else "on disk but absent from the page")


def check_worker_publication(port):
    """Canary: a worker file written here must appear in the board's JSON."""
    rec = check("worker status reaches the board")
    f = FLEET / "workers" / "e2e-probe.json"
    f.write_text(json.dumps({
        "worker": "e2e-probe", "kind": "test", "status": "pass",
        "summary": f"canary {CANARY}", "last_run": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                 time.gmtime()),
        "tests_passed": 1, "tests_failed": 0, "duration_s": 0.1,
    }))
    try:
        body = get(port, "/workers.json")
        rec(CANARY in body, "canary in /workers.json" if CANARY in body
            else "written but not served")
    except Exception as e:
        rec(False, f"unreachable: {e}")
    finally:
        f.unlink(missing_ok=True)


def check_signature_pipeline(port):
    """Canary: a signed pad path must traverse capture -> spam gate -> wall.

    Two remote marks carrying this run's canary: a living, jagged one that must
    reach the wall, and a dead-straight one that must be held in purgatory. If
    the gate ever inverts, stops scoring, or the endpoint stops serving, exactly
    one of these two assertions flips — which a single 200 could never tell you.
    """
    rec = check("signature: living hand reaches the wall, flat line to purgatory")
    import signature as sig
    jagged, straight = _jagged_path(), _straight_path()
    ej, es = sig.hand_entropy(jagged), sig.hand_entropy(straight)
    # The gate's own premise, asserted before we trust the endpoint's verdict.
    if not (ej >= 0.2 > es):
        return rec(False, f"fixture entropy off: jagged={ej} straight={es}")

    live, spam = f"{CANARY}-live", f"{CANARY}-spam"
    remote = {"X-Forwarded-For": "203.0.113.7"}   # make the gate actually judge
    s1, _ = post(port, "/api/signatures/sign",
                 {"points": jagged, "name": live, "kind": "human"}, remote)
    s2, _ = post(port, "/api/signatures/sign",
                 {"points": straight, "name": spam, "kind": "human"}, remote)
    if s1 != 200 or s2 != 200:
        return rec(False, f"sign POST returned {s1}/{s2}")
    time.sleep(0.3)
    try:
        data = json.loads(get(port, "/api/signatures"))
    except Exception as e:
        return rec(False, f"/api/signatures unreachable: {e}")
    collected = {d.get("name") for d in data.get("collected", [])}
    purgatory = {d.get("name") for d in data.get("purgatory", [])}
    if live not in collected:
        return rec(False, "living mark never reached the wall")
    if spam not in purgatory:
        return rec(False, "flat-line mark was not held in purgatory")
    if spam in collected:
        return rec(False, "flat-line mark leaked onto the wall")
    rec(True, f"living mark blessed (e={ej}), flat line quarantined (e={es})")


def check_moderation_wire(port):
    """Canary: the public board must forward a moderation vote to the cockpit,
    and the cockpit must refuse an UNSIGNED vote with 403 — proving the 2n+1
    override endpoint is alive and enforcing signing, end to end, while writing
    nothing (the 403 lands before any inbox mutation).

    The quorum arithmetic itself is exhaustively unit-tested in
    tests/test_override.py; this proves the wire from the public door to it,
    which is exactly the join a unit test cannot see.
    """
    rec = check("moderation: unsigned override is forwarded and refused (403)")
    status, body = post(port, f"/api/signals/{CANARY}-nope/override",
                        {"status": "declined"})
    if status == 403:
        return rec(True, "reached the cockpit, signing enforced")
    if status in (404, 502, 503):
        return rec(False, f"override not wired to the cockpit (HTTP {status})")
    rec(False, f"unexpected HTTP {status}: {body[:80]}")


def check_kill_switch(port):
    """Canary: a process started here must actually be killed by the endpoint.

    Note what this genuinely does: the kill switch kills *all* fleet work, which
    includes the launchd-managed board. That is correct behaviour, not a bug —
    but it means running this check briefly takes the live dashboard down. So
    the check also asserts it comes back, since a kill switch you cannot recover
    from is worse than none. Roughly ten seconds of downtime per run.
    """
    rec = check("kill switch stops a real process, and the board recovers")
    import urllib.request
    # launchd throttles respawns to roughly one per ten seconds. Killing a board
    # that has only just started means the restart is delayed past any sensible
    # window, and the check fails for a reason that has nothing to do with the
    # kill switch. Wait until the board has been up long enough to be restarted
    # promptly.
    for _ in range(20):
        up = subprocess.run(["pgrep", "-f", "fleet.py serve 8787"],
                            capture_output=True, text=True)
        if up.returncode == 0:
            age = subprocess.run(["ps", "-o", "etimes=", "-p", up.stdout.split()[0]],
                                 capture_output=True, text=True).stdout.strip()
            if age.isdigit() and int(age) > 12:
                break
        time.sleep(2)

    victim = subprocess.Popen(
        [sys.executable, str(FLEET / "bin" / "comms-heartbeat.py"),
         "--agents", "claude", "--name", "e2e-victim"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)
    try:
        token = json.loads(get(port, "/api/kill-token"))["token"]
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/kill", method="POST",
            data=json.dumps({"token": token, "only": "e2e-victim"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            killed = json.loads(r.read())["killed"]
        time.sleep(1)
        gone = victim.poll() is not None
        if not gone:
            return rec(False, "endpoint returned but the process survived")

        # The blanket kill takes the live board with it. Assert launchd brings
        # it back rather than quietly leaving the dashboard dead.
        recovered = False
        for _ in range(60):
            time.sleep(1)
            if subprocess.run(["pgrep", "-f", "fleet.py serve 8787"],
                              capture_output=True).returncode == 0:
                recovered = True
                break
        rec(recovered,
            f"killed {len(killed)}, board back up" if recovered
            else f"killed {len(killed)} but the live board did NOT restart")
    except Exception as e:
        rec(False, str(e))
    finally:
        if victim.poll() is None:
            victim.kill()
        (FLEET / "workers" / "e2e-victim.json").unlink(missing_ok=True)
        (FLEET / "logs" / ".e2e-victim.lock").unlink(missing_ok=True)


def check_agent_relay():
    """Canary: the relay's start number. An agent can only emit N+1 if N arrived."""
    rec = check("a real agent receives and transforms a value")
    (FLEET / "logs" / ".plusone-any.lock").unlink(missing_ok=True)
    import plusone
    res = plusone.play(["claude"], laps=1)
    hop = res["hops"][0] if res["hops"] else {}
    rec(bool(hop.get("ok")),
        f"{hop.get('received')} -> {hop.get('got')} in {hop.get('seconds')}s"
        if hop.get("ok") else f"expected {hop.get('expected')}, got {hop.get('got')}")


def check_agent_reads_live_state():
    """The strongest canary here.

    A canary event is emitted, then a real agent is asked what it sees on the
    board. If the token comes back, the agent genuinely read live state — not a
    cached prompt, not a plausible guess. Nothing else in this suite proves an
    agent is looking at the actual system.
    """
    rec = check("a real agent reads live fleet state")
    ev.emit("fleet", "info", f"[e2e] state canary {CANARY}")
    time.sleep(0.5)
    import chat, council
    state = council.board_state()
    if not any(CANARY in e for e in state["recent_events"]):
        return rec(False, "canary never reached board_state()")

    prompt = ("Below is live state from a monitoring system.\n\n"
              + "\n".join(state["recent_events"][-12:])
              + "\n\nOne line only: quote the token that begins with E2E- exactly "
                "as it appears. If there is none, reply NONE.")
    out = chat.ask_claude(prompt, [], lambda *a: None)
    rec(CANARY in (out or ""),
        "agent quoted the canary" if CANARY in (out or "")
        else f"agent did not see it: {str(out)[:80]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="skip checks that spend an agent turn")
    ap.add_argument("--port", type=int, default=8899)
    a = ap.parse_args()
    import heavygate
    if not heavygate.enabled() and not a.quick:
        print("heavy work off on this machine — skipping")
        return 0
    import pressure
    if pressure.too_hot() and not a.quick:
        snap = pressure.snapshot()
        print(f"deferred — {snap['reason']}")
        return 0

    print(f"canary: {CANARY}\n")
    ev.emit("fleet", "info", f"[e2e] run starting · canary {CANARY}")

    sig_file = FLEET / "logs" / f".e2e-signatures-{a.port}.jsonl"
    server = serve_test_instance(a.port, sig_file)
    try:
        check_event_pipeline(a.port)
        check_worker_publication(a.port)
        check_signature_pipeline(a.port)
        check_moderation_wire(a.port)
        check_kill_switch(a.port)   # takes the board down ~10s: keep it last
        if not a.quick:
            check_agent_relay()
            check_agent_reads_live_state()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        sig_file.unlink(missing_ok=True)

    passed = sum(1 for r in RESULTS if r["pass"])
    total = len(RESULTS)
    print(f"\n{passed}/{total} checks passed")
    ev.emit("fleet", "ok" if passed == total else "needs_you",
            f"[e2e] {passed}/{total} checks passed · canary {CANARY}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
