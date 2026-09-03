"""A reload should come back to the conversation, not to a stranger.

Every page load spawns a new `claude`; without --continue that process has no
memory of anything said a second earlier. These tests pin the two halves: the
transcript directory is found where the CLI actually keeps it, and the flag is
only added when there is something to continue.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fleet" / "bin"))

import terminal


def test_transcript_dir_matches_the_cli_slug():
    d = terminal.transcript_dir("/Users/phil/projects/command-control-dashboard")
    assert d.name == "-Users-phil-projects-command-control-dashboard"
    assert d.parent == Path.home() / ".claude" / "projects"


def test_no_prior_session_when_the_directory_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert terminal.has_prior_session("/some/where") is False


def test_prior_session_seen_once_a_transcript_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    d = terminal.transcript_dir("/some/where")
    d.mkdir(parents=True)
    assert terminal.has_prior_session("/some/where") is False
    (d / "abc.jsonl").write_text("{}\n")
    assert terminal.has_prior_session("/some/where") is True


def _argv_for(monkeypatch, prior):
    """Spawn a Session with fork and exec stubbed, and report the argv used."""
    seen = {}
    monkeypatch.setattr(terminal, "has_prior_session", lambda cwd: prior)
    monkeypatch.setattr(terminal.pty, "fork", lambda: (123, 9))
    monkeypatch.setattr(terminal.Session, "resize", lambda self, c, r: None)
    # pid != 0, so the child branch never runs; capture argv from the closure.
    s = terminal.Session("/some/where")
    seen["argv"] = s._argv
    return seen["argv"]


# The argv is now prefixed with `tmux -2 new-session -A -s <name> --`, so the
# board's terminal outlives a board restart (2026-09-03). What these two tests
# were written to pin is unchanged and lives at the end of the list: resume
# when there is something to resume, start clean when there is not.
def _claude_part(argv):
    return argv[argv.index("--") + 1:] if "--" in argv else argv


def test_continue_is_passed_when_there_is_history(monkeypatch):
    assert _claude_part(_argv_for(monkeypatch, True)) == ["claude", "--continue"]


def test_first_visit_starts_clean(monkeypatch):
    assert _claude_part(_argv_for(monkeypatch, False)) == ["claude"]
