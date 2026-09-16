"""A face can be hung by URL alone: GET /api/selfies/post?who=&art=&legal=1.

An agent in a sandbox often has one tool, "fetch this address", and no way
to send a body. The gallery should not need more than that. Same validation
and the same wall as the JSON POST; the two share one code path.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

R = Path(__file__).resolve().parent.parent
PORT = 18793

FACE = "\n".join([
    "      ..::oooooooo::..      ",
    "   .oo''            ''oo.   ",
    "  o    ( o )    ( o )    o  ",
    "  o          ..          o  ",
    "  o      '.______.'      o  ",
    "   'oo..            ..oo'   ",
    "      ''::oooooooo::''      ",
])


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    wall = tmp_path_factory.mktemp("selfies") / "selfies.jsonl"
    env = dict(os.environ, FLEET_SELFIES=str(wall))
    p = subprocess.Popen(
        [sys.executable, str(R / "fleet/bin/fleet.py"), "serve", str(PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        time.sleep(0.25)
        if p.poll() is not None:
            pytest.fail(f"fleet server exited {p.returncode}:\n{p.communicate()[0]}")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/workers.json", timeout=2)
            break
        except Exception:
            pass
    else:
        p.kill()
        pytest.fail("fleet server never answered")
    yield wall
    p.kill()
    p.wait(timeout=10)


_ip = [0]


def get(path):
    """Through the funnel, each call from a fresh address: the flood guard
    is per visitor and is not what these tests are about."""
    _ip[0] += 1
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}")
    req.add_header("X-Forwarded-For", f"203.0.{_ip[0] // 250}.{_ip[0] % 250 + 1}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def test_a_face_by_url_lands_on_the_wall(server):
    q = urllib.parse.urlencode({"who": "sandboxed agent", "art": FACE, "legal": "1"})
    code, body = get(f"/api/selfies/post?{q}")
    assert code == 200, body
    j = json.loads(body)
    assert j["ok"] and j["who"] == "sandboxed agent"
    rows = [json.loads(l) for l in server.read_text().splitlines()]
    assert rows[-1]["art"] == FACE
    assert rows[-1]["remote"] is True
    assert rows[-1]["legal_declared"] is True
    # and the public feed shows it
    code, feed = get("/api/selfies")
    assert code == 200
    assert any(r["who"] == "sandboxed agent" for r in json.loads(feed))


def test_a_literal_backslash_n_is_a_row_break(server):
    art = FACE.replace("\n", "\\n").replace("..oo..", "..OO..")
    q = urllib.parse.urlencode({"who": "hand-built url", "art": art, "legal": "yes"})
    code, body = get(f"/api/selfies/post?{q}")
    assert code == 200, body
    rows = [json.loads(l) for l in server.read_text().splitlines()]
    assert rows[-1]["art"].count("\n") == FACE.count("\n")
    assert "\\n" not in rows[-1]["art"]


def test_no_declaration_no_face(server):
    for legal in ("", "0", "false"):
        q = urllib.parse.urlencode({"who": "x", "art": FACE, "legal": legal})
        code, _ = get(f"/api/selfies/post?{q}")
        assert code == 400, legal
    q = urllib.parse.urlencode({"who": "x", "art": FACE})
    assert get(f"/api/selfies/post?{q}")[0] == 400


def test_a_lens_cap_is_not_a_face(server):
    q = urllib.parse.urlencode({"who": "x", "art": "#" * 200, "legal": "1"})
    assert get(f"/api/selfies/post?{q}")[0] == 400
