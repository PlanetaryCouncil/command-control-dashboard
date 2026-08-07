"""The pipeline must find the venv that exists on THIS machine.

2026-08-07: all four builds of the night succeeded and all four verifications
failed with "pytest does not exist". `.venv` was hardcoded — true on the Mac,
false on the NUC, whose `.venv` is python 3.14 (no pytest, no coincurve wheel)
and whose working environment is `.venv311`. The builder agents reported the
problem accurately and were powerless to route around it, because the
permission rules only granted the path that was wrong.
"""

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import pipeline  # noqa: E402


def test_prefers_an_existing_pytest(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    real = tmp_path / ".venv311" / "bin"
    real.mkdir(parents=True)
    (real / "pytest").write_text("#!/bin/sh\n")
    assert pipeline.venv_pytest() == real / "pytest"


def test_plain_venv_wins_when_both_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    for name in (".venv", ".venv311"):
        d = tmp_path / name / "bin"
        d.mkdir(parents=True)
        (d / "pytest").write_text("#!/bin/sh\n")
    assert pipeline.venv_pytest() == tmp_path / ".venv" / "bin" / "pytest"


def test_falls_back_to_the_conventional_path(tmp_path, monkeypatch):
    """No venv anywhere: still name `.venv`, so the error a human reads
    points at the place they expect to look."""
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    assert pipeline.venv_pytest() == tmp_path / ".venv" / "bin" / "pytest"


def test_no_hardcoded_venv_pytest_left_in_the_stages():
    """The whole bug was one literal path in two places. Keep it gone."""
    src = (BIN / "pipeline.py").read_text()
    body = src[src.index("def build("):]
    assert '.venv" / "bin" / "pytest"' not in body, \
        "verify must ask venv_pytest(), not hardcode a venv"
