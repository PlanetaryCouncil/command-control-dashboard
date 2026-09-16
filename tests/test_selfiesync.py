"""The wall on the laptop is the truth; gallery/manifest.json on Pages is
its echo. selfiesync.py keeps the echo honest: union with what was
hand-added before the wall existed, damned faces gone from both, no commit
when nothing changed, one push for a burst.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

R = Path(__file__).resolve().parent.parent
SRC = R / "fleet/bin/selfiesync.py"


def load(monkeypatch, wall, gallery):
    monkeypatch.setenv("FLEET_SELFIES", str(wall))
    monkeypatch.setenv("SELFIE_GALLERY_REPO", str(gallery))
    spec = importlib.util.spec_from_file_location("selfiesync", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


FACE_A = "  o o  \n   -   \n \\___/ " * 4
FACE_B = "  x x  \n   ^   \n  ===  " * 4


def _wall_line(who, art, status="blessed", ts="2026-09-16T01:00:00+00:00"):
    import hashlib
    return json.dumps({"ts": ts, "who": who, "kind": "ascii",
                       "seed": hashlib.sha256(art.encode()).hexdigest(),
                       "stamp": {"unix": 1789000000, "btc": {"height": 999, "hash": "ab"}},
                       "art": art, "status": status})


def test_union_wall_wins_mirror_only_stays_damned_go(tmp_path, monkeypatch):
    wall = tmp_path / "selfies.jsonl"
    wall.write_text("\n".join([
        _wall_line("alice", FACE_A),
        _wall_line("hidden", "  h h  \n  ---  " * 6, status="purgatory"),
    ]) + "\n")
    gallery = tmp_path / "g"; (gallery / "gallery").mkdir(parents=True)
    m = load(monkeypatch, wall, gallery)
    mirror = [
        {"kind": "ascii", "who": "alice (old caption)", "art": FACE_A, "unix": 1},
        {"kind": "ascii", "who": "legacy", "art": FACE_B, "unix": 5},
        {"kind": "ascii", "who": "damned one", "art": "  d d  \n  ~~~  " * 6, "unix": 3},
    ]
    damned = {m.seed_of(mirror[2])}
    merged = m.merge(m.read_wall(), mirror, damned)
    whos = [r["who"] for r in merged]
    assert whos == ["alice", "legacy"]          # newest first, wall's caption wins
    assert "hidden" not in whos                 # purgatory stays private
    assert merged[0]["btc"] == 999 and merged[0]["unix"] == 1789000000


@pytest.fixture
def gallery_with_remote(tmp_path):
    """A gallery checkout whose origin is a local bare repo: push is real,
    the network is not."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    g = tmp_path / "selfie-gallery"
    subprocess.run(["git", "clone", "-q", str(bare), str(g)], check=True)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    for k, v in env.items():
        os.environ[k] = v
    (g / "gallery").mkdir()
    (g / "gallery" / "manifest.json").write_text("[]\n")
    subprocess.run(["git", "-C", str(g), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(g), "commit", "-q", "-m", "seed"], check=True)
    subprocess.run(["git", "-C", str(g), "push", "-q", "-u", "origin", "HEAD"], check=True)
    return g, bare


def _run(wall, gallery, *args):
    env = dict(os.environ, FLEET_SELFIES=str(wall), SELFIE_GALLERY_REPO=str(gallery))
    return subprocess.run([sys.executable, str(SRC), *args],
                          capture_output=True, text=True, env=env)


def test_a_new_face_is_pushed_once_and_a_quiet_wall_is_not_committed(
        tmp_path, gallery_with_remote):
    g, bare = gallery_with_remote
    wall = tmp_path / "selfies.jsonl"
    wall.write_text(_wall_line("alice", FACE_A) + "\n")

    r = _run(wall, g, "--now")
    assert r.returncode == 0 and "pushed mirror: 1 faces" in r.stdout, r
    log = subprocess.run(["git", "-C", str(bare), "log", "--oneline"],
                         capture_output=True, text=True).stdout
    assert "mirror: 1 faces" in log
    assert json.loads((g / "gallery/manifest.json").read_text())[0]["who"] == "alice"

    r = _run(wall, g, "--now")
    assert r.returncode == 0 and "mirror current" in r.stdout, r
    log2 = subprocess.run(["git", "-C", str(bare), "log", "--oneline"],
                          capture_output=True, text=True).stdout
    assert log2 == log                          # nothing changed, nothing committed

    # Without --now, a second run inside the debounce window does nothing.
    wall.write_text(wall.read_text() + _wall_line("bob", FACE_B) + "\n")
    r = _run(wall, g)
    assert "debounced" in r.stdout, r


def test_local_edits_in_the_gallery_checkout_are_never_overwritten(
        tmp_path, gallery_with_remote):
    g, _ = gallery_with_remote
    (g / "gallery/manifest.json").write_text('[{"who":"someone is editing this"}]\n')
    wall = tmp_path / "selfies.jsonl"
    wall.write_text(_wall_line("alice", FACE_A) + "\n")
    r = _run(wall, g, "--now")
    assert r.returncode == 1 and "local edits" in r.stderr, r
    assert "someone is editing this" in (g / "gallery/manifest.json").read_text()
