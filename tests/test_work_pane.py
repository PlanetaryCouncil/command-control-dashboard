"""The work pane reads the repo, and reads it correctly.

Two things worth pinning. The parse: porcelain status puts a SPACE in column 1
for an unstaged change, and stripping the output shifts every path left by one
character — that shipped a pane reading "leet/bin/fleet.py". And the split: a
public viewer is shown landed history, which is on GitHub anyway, but never
the uncommitted tree, which is not published yet and does not become published
by appearing on a board.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fleet" / "bin"))

import work


def _repo(tmp_path):
    def git(*a):
        subprocess.run(("git", *a), cwd=tmp_path, check=True,
                       capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "kept.txt").write_text("one\n")
    git("add", "-A")
    git("commit", "-qm", "first")
    return git


def test_unstaged_paths_survive_the_porcelain_parse(tmp_path, monkeypatch):
    git = _repo(tmp_path)
    monkeypatch.setattr(work, "REPO", tmp_path)
    (tmp_path / "kept.txt").write_text("two\n")     # modified, not staged
    (tmp_path / "new.txt").write_text("x\n")        # untracked
    paths = {d["path"] for d in work._dirty()}
    assert paths == {"kept.txt", "new.txt"}         # not {"ept.txt", ...}
    del git


def test_a_clean_tree_reports_nothing_dirty(tmp_path, monkeypatch):
    _repo(tmp_path)
    monkeypatch.setattr(work, "REPO", tmp_path)
    assert work._dirty() == []


def test_public_is_not_shown_the_uncommitted_tree(tmp_path, monkeypatch):
    _repo(tmp_path)
    monkeypatch.setattr(work, "REPO", tmp_path)
    (tmp_path / "secret-wip.txt").write_text("x\n")

    pub = work.snapshot(local=False)
    # Absent, not zero: "0 uncommitted" would be a claim about a tree the
    # viewer was never shown.
    assert pub["dirty"] is None
    assert pub["dirty_count"] is None
    assert "secret-wip" not in repr(pub)

    loc = work.snapshot(local=True)
    assert loc["dirty_count"] == 1
    assert loc["dirty"][0]["path"] == "secret-wip.txt"


def test_landed_history_is_public(tmp_path, monkeypatch):
    _repo(tmp_path)
    monkeypatch.setattr(work, "REPO", tmp_path)
    pub = work.snapshot(local=False)
    assert pub["branch"] in ("main", "master")
    assert pub["recent"] and pub["recent"][0]["subject"] == "first"


def test_a_directory_that_is_not_a_repo_reports_empty(tmp_path, monkeypatch):
    """A pane must degrade to "nothing to report", never to a 500."""
    monkeypatch.setattr(work, "REPO", tmp_path)     # no git init
    d = work.snapshot(local=True)
    assert d["branch"] == "?"
    assert d["recent"] == [] and d["today"] == [] and d["hot"] == []
