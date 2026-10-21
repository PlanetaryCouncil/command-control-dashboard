"""The image gate must survive direct requests and concurrent replay."""
import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "fleet/bin/portraits.py"
spec = importlib.util.spec_from_file_location("portraits_under_test", SRC)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def solve(token):
    nonce = 0
    while int.from_bytes(hashlib.sha256(f"{token}:{nonce}".encode()).digest(), "big") >> (256-p.BITS):
        nonce += 1
    return str(nonce)


def test_fresh_work_one_second_expiry_and_image_binding():
    now = [0.0]
    gate = p.Gate(clock=lambda: now[0])
    token = gate.issue("codex")["challenge"]
    nonce = solve(token)
    assert not gate.redeem("codex", token, nonce)  # too early
    now[0] = 1.1
    assert not gate.redeem("other", token, nonce)
    assert not gate.redeem("codex", token, "NaN")
    assert not gate.redeem("codex", token[:-1] + "z", nonce)
    assert gate.redeem("codex", token, nonce)
    assert not gate.redeem("codex", token, nonce)
    token = gate.issue("codex")["challenge"]
    now[0] += p.TTL
    assert not gate.redeem("codex", token, solve(token))


def test_parallel_replay_only_one_response():
    now = [0.0]
    gate = p.Gate(clock=lambda: now[0])
    token = gate.issue("codex")["challenge"]
    nonce = solve(token)
    now[0] = 2.0
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: gate.redeem("codex", token, nonce), range(8)))
    assert sum(results) == 1


def test_outstanding_challenges_bounded_and_pruned(monkeypatch):
    monkeypatch.setattr(p, "LIMIT", 2)
    now = [0.0]
    gate = p.Gate(clock=lambda: now[0])
    gate.issue("a")
    gate.issue("b")
    with pytest.raises(OverflowError):
        gate.issue("c")
    now[0] = p.TTL
    gate.issue("c")
    assert len(gate.pending) == 1


class Handler:
    def __init__(self, path):
        self.path = path
        self.code = None
        self.body = b""

    def send_error(self, code):
        self.code = code

    def _send(self, body, ctype=None, cache="no-store", code=200):
        self.body, self.code, self.cache = body, code, cache

    def _flooding(self, bucket):
        return False


def test_direct_image_denied_metadata_safe_and_storage_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEET_PORTRAITS", str(tmp_path))
    (tmp_path / "catalog.json").write_text(json.dumps([
        {"id": "codex", "who": "Codex", "file": "/secret/location"}]))
    image = b"private image bytes"
    (tmp_path / "codex.png").write_bytes(image)
    handler = Handler("/api/portraits/codex/image")
    assert p.handle(handler, handler.path)
    assert handler.code == 403 and image not in handler.body
    handler = Handler("/api/portraits")
    p.handle(handler, handler.path)
    assert b"secret" not in handler.body and image not in handler.body
    assert handler.cache == "no-store"
    (tmp_path / "codex.png").unlink()
    (tmp_path / "codex.png").symlink_to(SRC)
    with pytest.raises(FileNotFoundError):
        p.image_path("codex")
    monkeypatch.setenv("FLEET_PORTRAITS", str(p.ROOT / "fleet/static"))
    monkeypatch.setattr(p, "catalog", lambda: [{"id": "codex"}])
    with pytest.raises(FileNotFoundError):
        p.image_path("codex")


def test_valid_work_releases_image_then_denies_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEET_PORTRAITS", str(tmp_path))
    (tmp_path / "catalog.json").write_text('[{"id":"codex"}]')
    (tmp_path / "codex.png").write_bytes(b"image bytes")
    now = [0.0]
    gate = p.Gate(clock=lambda: now[0])
    monkeypatch.setattr(p, "GATE", gate)
    handler = Handler("/api/portraits/codex/challenge")
    p.handle(handler, handler.path)
    token = json.loads(handler.body)["challenge"]
    nonce = solve(token)
    now[0] = 1.1
    handler = Handler(f"/api/portraits/codex/image?challenge={token}&nonce={nonce}")
    p.handle(handler, "/api/portraits/codex/image")
    assert handler.code == 200 and handler.body == b"image bytes"
    assert handler.cache == "no-store"
    p.handle(handler, "/api/portraits/codex/image")
    assert handler.code == 403
