"""The reviewer is handed the branch's patch, not a git fatal.

2026-08-27: verify merged origin/main, then asked the reviewer to read
`git diff main...branch` from the shared checkout. Local main on the NUC
tracks a different lineage and has no merge-base with the pipeline branch,
so the three-dot diff was `fatal: no merge base` and the reviewer rejected
"no diff was provided in the message".
"""

import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import pipeline  # noqa: E402


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True, check=True)


def _fake_pytest(tmp_path, exit_code):
    p = tmp_path / f"pytest{exit_code}"
    p.write_text(f"#!/bin/sh\necho '3 passed'\nexit {exit_code}\n")
    p.chmod(0o755)
    return p


@pytest.fixture
def unrelated_main(tmp_path, monkeypatch):
    """Local `main` is an unrelated history; the pipeline branch lives on
    `origin/main`. That is the NUC's shape, not a hypothetical."""
    r = tmp_path / "repo"
    r.mkdir()
    git("init", "-q", "-b", "main", cwd=r)
    git("config", "user.email", "t@t", cwd=r)
    git("config", "user.name", "t", cwd=r)
    (r / "wip.txt").write_text("unrelated main\n")
    git("add", "-A", cwd=r)
    git("commit", "-qm", "wip on local main", cwd=r)

    git("checkout", "-q", "--orphan", "pipeline-main", cwd=r)
    git("rm", "-qf", "wip.txt", cwd=r)
    (r / "keep.txt").write_text("origin main\n")
    git("add", "-A", cwd=r)
    git("commit", "-qm", "origin main", cwd=r)
    git("update-ref", "refs/remotes/origin/main",
        git("rev-parse", "HEAD", cwd=r).stdout.strip(), cwd=r)

    git("checkout", "-q", "-b", "rota/feature", cwd=r)
    (r / "feature.txt").write_text("the actual change\n")
    git("add", "-A", cwd=r)
    git("commit", "-qm", "implement the proposal", cwd=r)
    git("checkout", "-q", "main", cwd=r)

    wt = tmp_path / "wt" / "feature"
    git("worktree", "add", "-q", str(wt), "rota/feature", cwd=r)

    monkeypatch.setattr(pipeline, "REPO", r)
    monkeypatch.setattr(pipeline, "STATE", tmp_path / "pipeline.jsonl")
    monkeypatch.setattr(pipeline, "WORKTREES", tmp_path / "wt")
    monkeypatch.setattr(pipeline, "remote_main", lambda: "origin/main")
    monkeypatch.setattr(pipeline, "venv_pytest",
                        lambda: _fake_pytest(tmp_path, 0))
    monkeypatch.setattr(pipeline, "reviewer_name", lambda: "hermes")
    monkeypatch.setattr(pipeline.ev, "emit", lambda *a, **k: None)
    return r, wt


def test_reviewer_prompt_contains_the_branch_patch(unrelated_main, monkeypatch):
    repo, wt = unrelated_main
    captured = {}

    def ask(_chat, prompt, _noop):
        captured["prompt"] = prompt
        return "APPROVE the change is the file it claims"

    monkeypatch.setitem(pipeline.ASKERS, "hermes", ask)

    r = pipeline.verify({"worktree": str(wt), "branch": "rota/feature",
                         "proposal_ts": "t1"})
    prompt = captured["prompt"]
    assert "no merge base" not in prompt
    assert "feature.txt" in prompt
    assert "the actual change" in prompt
    assert r["ok"] is True


def test_verify_does_not_diff_against_local_main():
    src = (BIN / "pipeline.py").read_text()
    body = src[src.index("def verify("):src.index("def land(")]
    assert 'f"main...{branch}"' not in body
    assert 'f"{base}...HEAD"' in body
