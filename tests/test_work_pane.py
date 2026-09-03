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


# --------------------------------------------------------------- the log page
def _commit(tmp_path, subject, body=""):
    msg = subject + ("\n\n" + body if body else "")
    (tmp_path / "f.txt").write_text(subject + "\n")
    subprocess.run(("git", "add", "-A"), cwd=tmp_path, check=True,
                   capture_output=True)
    subprocess.run(("git", "commit", "-qm", msg), cwd=tmp_path, check=True,
                   capture_output=True)


def test_the_body_survives_and_the_trailers_do_not(tmp_path, monkeypatch):
    """A commit body is the reasoning; a trailer is addressing."""
    _repo(tmp_path)
    monkeypatch.setattr(work, "REPO", tmp_path)
    _commit(tmp_path, "a subject",
            "First paragraph of why.\n\nSecond paragraph.\n\n"
            "Co-Authored-By: Someone <x@example.com>\n"
            "Claude-Session: https://example.com/s")
    c = work.log(1)[0]
    assert c["subject"] == "a subject"
    assert c["body"] == ["First paragraph of why.", "Second paragraph."]


def test_a_mid_sentence_colon_is_not_a_trailer(tmp_path, monkeypatch):
    """The regression that shipped a sentence nobody wrote.

    git hard-wraps at 72 columns, so a wrapped line can begin "knows: branch,
    unpushed count, ..." — which matches a naive trailer pattern. Dropping it
    rendered "git already files you kept going back to this week": grammatical,
    confident, and never written by anyone.
    """
    _repo(tmp_path)
    monkeypatch.setattr(work, "REPO", tmp_path)
    _commit(tmp_path, "s",
            "So read git, not a status file. git already\n"
            "knows: branch, unpushed count, and what landed today.\n\n"
            "Co-Authored-By: Someone <x@example.com>")
    body = " ".join(work.log(1)[0]["body"])
    assert "knows: branch, unpushed count, and what landed today." in body
    assert "Co-Authored-By" not in body


def test_prose_that_opens_with_a_capitalised_word_and_colon_is_kept(
        tmp_path, monkeypatch):
    """A last paragraph is only trailers if EVERY line in it is one."""
    _repo(tmp_path)
    monkeypatch.setattr(work, "REPO", tmp_path)
    _commit(tmp_path, "s", "Note: this still matters, and it is the point.")
    assert work.log(1)[0]["body"] == [
        "Note: this still matters, and it is the point."]


def test_each_commit_carries_the_files_it_touched(tmp_path, monkeypatch):
    _repo(tmp_path)
    monkeypatch.setattr(work, "REPO", tmp_path)
    _commit(tmp_path, "touches one file")
    assert work.log(1)[0]["files"] == ["f.txt"]


def test_the_page_renders_without_a_github_remote(tmp_path, monkeypatch):
    """No remote means shas as plain text, never a missing page."""
    _repo(tmp_path)
    monkeypatch.setattr(work, "REPO", tmp_path)
    assert work.origin_web() == ""
    html = work.page()
    assert "first" in html
    assert 'href="/commit/' not in html      # no half-built links


def test_a_remote_not_called_origin_still_links(tmp_path, monkeypatch):
    """This repo's remote is `GitHub_priv`; only knowing `origin` links nothing."""
    _repo(tmp_path)
    monkeypatch.setattr(work, "REPO", tmp_path)
    subprocess.run(("git", "remote", "add", "GitHub_priv",
                    "git@github.com:PlanetaryCouncil/x.git"),
                   cwd=tmp_path, check=True, capture_output=True)
    assert work.origin_web() == "https://github.com/PlanetaryCouncil/x"
    assert "https://github.com/PlanetaryCouncil/x/commit/" in work.page()
