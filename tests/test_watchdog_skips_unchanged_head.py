"""The hourly watchdog must not re-run 500 tests over a tree that has not moved.

It also must not lie about it. The dangerous version of this optimisation is
the one that reports a fresh green for a run that never happened — the board
then shows evidence it does not have. So: skip, and say "unchanged since
<sha>", carrying the real previous summary forward.

Everything that could make a skip wrong has to re-run: a dirty tree, a missing
previous result, a previous failure.
"""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WATCHDOG = ROOT / "fleet" / "bin" / "watchdog.sh"

spec = importlib.util.spec_from_file_location(
    "watchdog_prev", ROOT / "fleet" / "bin" / "watchdog-prev.py")
prev_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prev_mod)


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


@pytest.fixture
def project(tmp_path):
    """A tiny git repo with one passing test and its own venv-less runner."""
    repo = tmp_path / "proj"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "proj"\nversion = "0"\n')
    git(repo.parent, "init", "proj")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "one")
    return repo


def head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def write_worker(fleet, name, **fields):
    out = fleet / "workers" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fields))
    return out


# ------------------------------------------------------- the prev-result read

def test_prev_reads_a_green_record(tmp_path):
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"status": "pass", "head": "abc123",
                             "summary": "5 passed", "last_run": "then"}))
    assert prev_mod.previous(p) == "abc123\t5 passed\tthen"


@pytest.mark.parametrize("record", [
    {"status": "fail", "head": "abc123", "summary": "1 failed"},
    {"status": "pass", "summary": "5 passed"},          # pre-`head` record
    {"status": "skip", "head": "abc123"},
])
def test_prev_declines_anything_not_a_green_with_a_commit(tmp_path, record):
    p = tmp_path / "w.json"
    p.write_text(json.dumps(record))
    assert prev_mod.previous(p) == "", "empty means run the tests, which is safe"


def test_prev_survives_a_corrupt_or_missing_file(tmp_path):
    assert prev_mod.previous(tmp_path / "nope.json") == ""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert prev_mod.previous(bad) == ""


def test_prev_cannot_break_the_tab_separation(tmp_path):
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"status": "pass", "head": "abc",
                             "summary": "5 passed\tinjected\nnewline",
                             "last_run": "then"}))
    assert prev_mod.previous(p).count("\t") == 2


# ------------------------------------------------------------ the script path

def run_watchdog(project, fleet_home, env_extra=None):
    import os
    env = dict(os.environ)
    env.pop("WATCHDOG_FORCE", None)
    # These tests run against the REAL fleet directory on purpose (the
    # watchdog derives it from its own location and the worker files are
    # backed up and restored around each case). The event log is the one
    # thing that must not be shared: without this redirect every full run
    # put eleven records on the LIVE public board, inventing failures for
    # "proj" and "brokenproj", projects that have never existed. The board
    # was showing a red "3 NEED YOU" written by its own test suite.
    import tempfile
    env["FLEET_EVENTS"] = str(
        Path(tempfile.mkdtemp(prefix="watchdog-events-")) / "events.jsonl")
    env.update(env_extra or {})
    return subprocess.run(["bash", str(WATCHDOG), str(project)],
                          capture_output=True, text=True, env=env, timeout=300)


def test_a_clean_unchanged_tree_is_skipped_and_says_so(project, monkeypatch):
    fleet = ROOT / "fleet"
    name = project.name
    out = fleet / "workers" / f"{name}.json"
    existed = out.exists()
    backup = out.read_text() if existed else None
    try:
        write_worker(fleet, name, status="pass", head=head(project),
                     summary="5 passed", last_run="2026-08-25T00:00:00Z")
        res = run_watchdog(project, fleet)
        assert "skipped" in res.stdout, res.stdout + res.stderr
        rec = json.loads(out.read_text())
        assert rec["status"] == "pass"
        assert "unchanged since" in rec["summary"], \
            "a skip must not pass itself off as a fresh run"
        assert "5 passed" in rec["summary"], "the real result carries forward"
        assert rec["duration_s"] == 0
    finally:
        if backup is not None:
            out.write_text(backup)
        elif out.exists():
            out.unlink()


def test_a_moved_head_is_not_skipped(project):
    fleet = ROOT / "fleet"
    name = project.name
    out = fleet / "workers" / f"{name}.json"
    existed = out.exists()
    backup = out.read_text() if existed else None
    try:
        write_worker(fleet, name, status="pass", head="0" * 40,
                     summary="5 passed", last_run="2026-08-25T00:00:00Z")
        res = run_watchdog(project, fleet)
        assert "skipped" not in res.stdout, "different commit must be tested"
    finally:
        if backup is not None:
            out.write_text(backup)
        elif out.exists():
            out.unlink()


def test_a_dirty_tree_is_never_skipped(project):
    fleet = ROOT / "fleet"
    name = project.name
    out = fleet / "workers" / f"{name}.json"
    existed = out.exists()
    backup = out.read_text() if existed else None
    try:
        write_worker(fleet, name, status="pass", head=head(project),
                     summary="5 passed", last_run="2026-08-25T00:00:00Z")
        (project / "tests" / "test_new.py").write_text("def test_n():\n    assert True\n")
        res = run_watchdog(project, fleet)
        assert "skipped" not in res.stdout, \
            "uncommitted work is exactly what needs testing"
    finally:
        if backup is not None:
            out.write_text(backup)
        elif out.exists():
            out.unlink()


def test_force_overrides_the_skip(project):
    fleet = ROOT / "fleet"
    name = project.name
    out = fleet / "workers" / f"{name}.json"
    existed = out.exists()
    backup = out.read_text() if existed else None
    try:
        write_worker(fleet, name, status="pass", head=head(project),
                     summary="5 passed", last_run="2026-08-25T00:00:00Z")
        res = run_watchdog(project, fleet, {"WATCHDOG_FORCE": "1"})
        assert "skipped" not in res.stdout
    finally:
        if backup is not None:
            out.write_text(backup)
        elif out.exists():
            out.unlink()


def test_a_real_run_records_the_commit_it_tested(project):
    """Without this the skip can never engage — and it would fail open,
    re-running forever, which is the bug it was written to remove."""
    fleet = ROOT / "fleet"
    name = project.name
    out = fleet / "workers" / f"{name}.json"
    existed = out.exists()
    backup = out.read_text() if existed else None
    try:
        if out.exists():
            out.unlink()
        run_watchdog(project, fleet)
        rec = json.loads(out.read_text())
        assert rec.get("head") == head(project)
    finally:
        if backup is not None:
            out.write_text(backup)
        elif out.exists():
            out.unlink()


def test_a_failing_run_still_reports(tmp_path):
    """The failure path wrote its digest using $STAMP, which write_status()
    only sets at the END of the run — so under `set -u` every failing watchdog
    died silently: no digest, no worker record, nothing on the board. A
    watchdog that goes quiet exactly when a project breaks is worse than none.
    """
    repo = tmp_path / "brokenproj"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_bad.py").write_text("def test_bad():\n    assert False\n")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "brokenproj"\nversion = "0"\n')
    git(repo.parent, "init", "brokenproj")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "one")

    fleet = ROOT / "fleet"
    out = fleet / "workers" / "brokenproj.json"
    try:
        res = run_watchdog(repo, fleet)
        assert "unbound variable" not in res.stderr, res.stderr
        assert out.exists(), res.stdout + res.stderr
        rec = json.loads(out.read_text())
        assert rec["status"] == "fail"
        assert rec["digest"], "a failed run must leave a digest to read"
        assert (fleet / rec["digest"]).exists()
        assert rec.get("head") == head(repo)
    finally:
        out.unlink(missing_ok=True)
        for junk in list(fleet.glob("digests/brokenproj-*.md")) + \
                list(fleet.glob("logs/brokenproj-*.log")):
            junk.unlink(missing_ok=True)
