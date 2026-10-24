"""A public ASCII seed is not permission to attach an interpretation."""
import base64
import hashlib
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "fleet/bin"))
import selfieuploads as uploads


@pytest.fixture
def store(tmp_path, monkeypatch):
    wall = tmp_path / "selfies.jsonl"
    monkeypatch.setenv("FLEET_SELFIES", str(wall))
    monkeypatch.setenv("FLEET_SELFIE_PRIVATE", str(tmp_path / "private"))
    monkeypatch.setenv("SELFIE_GALLERY_REPO", str(tmp_path / "gallery"))
    return wall


def face(art="ASCII face " * 10):
    return {"seed": hashlib.sha256(art.encode()).hexdigest(), "kind": "ascii",
            "art": art, "who": "same name", "status": "blessed"}


def png_body():
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("comment", "discard this metadata")
    Image.new("RGB", (3, 4), "green").save(output, format="PNG", pnginfo=metadata)
    return {"image_base64": base64.b64encode(output.getvalue()).decode(),
            "alt": "Visual interpretation", "legal": True}


class Handler:
    def __init__(self, seed, token=None, body=None):
        data = json.dumps(body if body is not None else png_body()).encode()
        self.headers = {"Content-Length": str(len(data))}
        if token:
            self.headers["Authorization"] = "Bearer " + token
        self.rfile = io.BytesIO(data)
        self.path = f"/api/selfies/{seed}/interpretation"

    def _send(self, body, ctype=None, code=200):
        self.code, self.body = code, json.loads(body)

    def _flooding(self, bucket):
        return False


def test_only_original_token_can_attach_after_ascii(store):
    record = face()
    handler = Handler(record["seed"], "x" * 43)
    assert not uploads.handle_post(handler, handler.path)
    assert handler.code == 404
    token = uploads.append_face(record, store)
    other = face("another ASCII " * 10)
    other_token = uploads.append_face(other, store)
    for wrong in (None, "wrong" * 9, other_token):
        handler = Handler(record["seed"], wrong)
        assert not uploads.handle_post(handler, handler.path)
        assert handler.code == 403
        assert handler.rfile.tell() == 0  # do not decode an unauthorized upload
    assert uploads.append_face(record, store) is None  # repost cannot steal
    assert uploads.authorized(record["seed"], token)
    handler = Handler(record["seed"], token)
    assert uploads.handle_post(handler, handler.path)
    assert handler.code == 202 and handler.body["status"] == "queued"
    assert token not in store.read_text()
    assert token not in json.dumps(uploads.publications())
    db_bytes = (uploads.private_directory() / "authors.sqlite3").read_bytes()
    assert token.encode() not in db_bytes
    image = uploads.private_directory() / uploads.publications()[0]["filename"]
    with Image.open(image) as decoded:
        assert decoded.size == (3, 4) and "comment" not in decoded.info


def test_legacy_and_mirror_faces_cannot_be_claimed(store):
    record = face()
    store.write_text(json.dumps(record) + "\n")
    assert uploads.append_face(record, store) is None
    mirror_record = face("mirror-only face " * 10)
    gallery = Path(__import__("os").environ["SELFIE_GALLERY_REPO"]) / "gallery"
    gallery.mkdir(parents=True)
    (gallery / "manifest.json").write_text(json.dumps([mirror_record]))
    assert uploads.append_face(mirror_record, store) is None
    assert not uploads.authorized(record["seed"], "x" * 43)


def test_concurrent_reposts_issue_only_one_receipt(store):
    with ThreadPoolExecutor(max_workers=6) as pool:
        tokens = list(pool.map(lambda _: uploads.append_face(face(), store), range(6)))
    assert sum(t is not None for t in tokens) == 1


@pytest.mark.parametrize("payload", [
    {"image_base64": "<svg>not a raster</svg>", "legal": True},
    {"image_base64": base64.b64encode(b"not an image").decode(), "legal": True},
    {"image_base64": "", "legal": True},
    {"image_base64": "AAAA", "legal": False},
])
def test_invalid_images_rejected_without_publication(store, payload):
    record = face()
    token = uploads.append_face(record, store)
    handler = Handler(record["seed"], token, payload)
    assert not uploads.handle_post(handler, handler.path)
    assert handler.code == 400 and uploads.publications() == []


def test_large_dimensions_rejected_before_pixel_decode(store):
    record = face()
    token = uploads.append_face(record, store)
    output = io.BytesIO()
    Image.new("RGB", (4097, 1)).save(output, format="PNG")
    body = {"image_base64": base64.b64encode(output.getvalue()).decode(), "legal": True}
    handler = Handler(record["seed"], token, body)
    uploads.handle_post(handler, handler.path)
    assert handler.code == 400 and uploads.publications() == []


def test_held_ascii_does_not_accept_interpretations(store):
    record = face()
    token = uploads.append_face(record, store)
    record["status"] = "purgatory"
    store.write_text(json.dumps(record) + "\n")
    handler = Handler(record["seed"], token)
    uploads.handle_post(handler, handler.path)
    assert handler.code == 404


def test_oversized_upload_rejected_without_reading_body(store):
    record = face()
    token = uploads.append_face(record, store)
    handler = Handler(record["seed"], token)
    handler.headers["Content-Length"] = str(uploads.MAX_BODY + 1)
    uploads.handle_post(handler, handler.path)
    assert handler.code == 413 and handler.rfile.tell() == 0
