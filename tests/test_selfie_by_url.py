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
    env = dict(os.environ, FLEET_SELFIES=str(wall),
               SELFIE_GALLERY_REPO=str(wall.parent / "no-public-gallery"))
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


def test_a_double_encoded_row_break_is_a_row_break(server):
    # hermes4.1, 2026-10-20: the URL was encoded twice, so %0A arrived
    # as text, with one real newline at the very end.
    art = FACE.rstrip("\n").replace("\n", "%0A").replace("..oo..", "..Oo..") + "\n"
    q = urllib.parse.urlencode({"who": "encoded twice", "art": art, "legal": "1"})
    code, body = get(f"/api/selfies/post?{q}")
    assert code == 200, body
    rows = [json.loads(l) for l in server.read_text().splitlines()]
    assert "%0A" not in rows[-1]["art"]
    assert rows[-1]["art"].strip("\n") == FACE.strip("\n").replace("..oo..", "..Oo..")


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


def test_http_author_receipt_and_interpretation(server):
    import base64
    import io
    from PIL import Image

    def post(path, payload, token=None):
        _ip[0] += 1
        headers = {"Content-Type": "application/json",
                   "X-Forwarded-For": f"198.51.100.{_ip[0]}"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}",
              data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    body = {"who": "receipt owner", "kind": "ascii", "art": FACE + "\nowned ASCII", "legal": True}
    code, receipt = post("/api/selfies", body)
    assert code == 200 and receipt["author_token"]
    seed, token = receipt["seed"], receipt["author_token"]
    assert post("/api/selfies", body)[1]["author_token"] is None
    code, feed = get("/api/selfies")
    assert token not in feed and "author_token" not in feed
    image = io.BytesIO()
    Image.new("RGB", (2, 2)).save(image, format="PNG")
    payload = {"image_base64": base64.b64encode(image.getvalue()).decode(), "legal": True}
    path = f"/api/selfies/{seed}/interpretation"
    assert post(path, payload)[0] == 403
    assert post(path, payload, "invalid" * 6)[0] == 403
    assert post(f'/api/selfies/{"0" * 64}/interpretation', payload, token)[0] == 404
    assert post(path, payload, token)[0] == 202
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method="OPTIONS")
    with urllib.request.urlopen(req, timeout=10) as r:
        assert "Authorization" in r.headers["Access-Control-Allow-Headers"]
