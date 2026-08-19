"""The panic button has to reach the daemon that is actually serving.

On 2026-08-03 this machine ended up with two Tailscale daemons: a dead 1.94.2
network extension still holding the CLI's default socket, and brew's 1.98.10
running the real funnel on `/var/run/tailscaled.socket`. `panic.sh` called a
bare `tailscale funnel reset`, reached the corpse, exited 0, printed a tick, and
left the site on the public internet.

A panic button that reports success it has not achieved is worse than none: you
read the tick and walk away. These tests run the script against a fake
`tailscale` on PATH, so the socket choice and the verification step are pinned
without taking anything down.
"""

import os
import subprocess
from pathlib import Path

import pytest

PANIC = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "panic.sh"


@pytest.fixture
def fake_tailscale(tmp_path):
    """Scriptable `tailscale`, plus a neutered `pkill`, first on PATH.

    Stubbing pkill is not fussiness. The first version of this file ran the
    real script against the real process table and killed the live cockpit
    mid-test — a test for a safety device that caused the outage it was meant
    to make survivable. Anything the script kills, the fixture owns.
    """
    binder = tmp_path / "bin"
    binder.mkdir()
    calls = tmp_path / "calls.txt"

    for name in ("pkill", "pgrep"):
        stub = binder / name
        stub.write_text(f'#!/bin/sh\necho "{name} $@" >> {calls}\nexit 0\n')
        stub.chmod(0o755)

    def install(serve_status_output):
        (binder / "tailscale").write_text(
            "#!/bin/sh\n"
            f'echo "$@" >> {calls}\n'
            'case "$*" in\n'
            f'  *"serve status"*) printf "%s" \'{serve_status_output}\' ;;\n'
            "esac\n"
            "exit 0\n")
        (binder / "tailscale").chmod(0o755)
        env = dict(os.environ, PATH=f"{binder}:{os.environ['PATH']}",
                   PANIC_DRY_RUN="",
                   # Without this the suite appends real-looking `panic.offline`
                   # records to data/events.jsonl on every run. It did, twice,
                   # before anyone noticed — a test writing fiction into the
                   # audit trail of a safety event.
                   PANIC_EVENTS=str(tmp_path / "events.jsonl"))
        return env, calls

    return install


def run(env):
    return subprocess.run(["bash", str(PANIC)], capture_output=True, text=True,
                          env=env, timeout=60).stdout


def test_a_still_open_funnel_is_reported_as_failure(fake_tailscale):
    """The whole bug: reset exits 0 while the site stays up."""
    env, _ = fake_tailscale("https://x.ts.net (Funnel on)\\n|-- / proxy http://127.0.0.1:8770")
    out = run(env)
    assert "TUNNEL IS STILL UP" in out, "panic.sh claimed success with the funnel up"
    assert "✅ tunnel closed" not in out


def test_a_cleared_funnel_reports_success(fake_tailscale):
    env, _ = fake_tailscale("")
    out = run(env)
    assert "tunnel closed" in out
    assert "TUNNEL IS STILL UP" not in out


def test_dry_run_touches_nothing(tmp_path):
    env = dict(os.environ, PANIC_DRY_RUN="1")
    out = subprocess.run(["bash", str(PANIC)], capture_output=True, text=True,
                         env=env, timeout=60).stdout
    assert "DRY RUN" in out
    # Assert on the lines the script always prints, whatever the machine has
    # installed. The event line is the last thing panic does and the one that
    # would have written to disk, so seeing it announced rather than performed
    # is the actual claim: a dry run touches nothing.
    assert "would record panic.offline" in out
    assert "would stop" in out or "is not running" in out

    # The tunnel line exists only where tailscale does. A runner without it
    # says so and skips, which is correct behaviour, not a failure - the thing
    # under test is that nothing was touched, not that the box has a tunnel.
    if "tailscale not installed" not in out:
        assert "would run" in out and "funnel reset" in out


def test_it_stops_the_fleet_board_too():
    """The board is funnelled on 8443 now; leaving it up leaves a surface up."""
    body = PANIC.read_text()
    assert "fleet.py serve" in body, "panic.sh does not stop the public fleet board"


def test_recovery_instructions_name_the_working_socket():
    """Coming back up with a bare `tailscale funnel` hits the dead daemon."""
    body = PANIC.read_text()
    tail = body.split("To come back up:")[1]
    assert "--socket=" in tail


def test_the_suite_does_not_write_to_the_real_event_log(fake_tailscale, tmp_path):
    """A test that fakes a panic in the live audit trail is worse than no test."""
    env, _ = fake_tailscale("")
    before = Path(__file__).resolve().parent.parent / "data" / "events.jsonl"
    size = before.stat().st_size if before.exists() else 0
    run(env)
    after = before.stat().st_size if before.exists() else 0
    assert after == size, "panic.sh test appended to data/events.jsonl"
