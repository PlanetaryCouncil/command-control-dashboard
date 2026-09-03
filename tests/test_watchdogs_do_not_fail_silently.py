"""A missing per-machine file must not disable a whole tier of the fleet.

2026-09-03: `fleet-watchdogs.service` had been failing on the NUC every hour
since the box was re-cloned. The reason was one line -- projects.txt is
gitignored, because it holds absolute paths that differ per machine, so a new
machine has none and the script exited 1 before doing anything. systemd
recorded a permanently failed unit and nobody reads `systemctl --failed`.

The fleet's own repo is always present on a machine running the fleet, and it
has a test suite, so that is the honest default.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SH = (ROOT / "fleet" / "bin" / "run-watchdogs.sh").read_text()


def test_a_missing_list_is_not_a_failure():
    assert 'echo "no projects.txt"; exit 1;' not in SH
    head = SH.split("PY=")[0]
    assert "exit 1" not in head, "the list check must not abort the run"


def test_it_falls_back_to_the_repo_it_lives_in():
    assert 'SELF="$(cd "$FLEET/.." && pwd)"' in SH
    assert "defaulting to this repo" in SH


def test_the_fallback_is_written_down_not_just_used():
    """A default that leaves no file is a default you rediscover every hour
    and can never edit."""
    assert '> "$LIST"' in SH


def test_the_list_stays_out_of_git():
    """It is machine-specific; committing one machine's paths onto another is
    how the wrong repo gets watched."""
    ignored = (ROOT / ".gitignore").read_text()
    assert "fleet/projects.txt" in ignored
