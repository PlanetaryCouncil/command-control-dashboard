"""ASCII submission receipts and author-only visual interpretations.

Only token hashes and staged images live here, outside both repositories.
Public JSONL records and GitHub manifests never contain author credentials.
"""
import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import warnings
from pathlib import Path

MAX_BYTES = 6 * 1024 * 1024
MAX_BODY = 9 * 1024 * 1024
SEED = re.compile(r"[0-9a-f]{64}")


def private_directory():
    configured = os.environ.get("FLEET_SELFIE_PRIVATE")
    if configured:
        root = Path(configured).resolve()
    elif os.environ.get("FLEET_SELFIES"):
        root = Path(os.environ["FLEET_SELFIES"]).resolve().parent / "selfie-private"
    else:
        root = Path.home() / ".local/share/command-control/selfie-private"
    repo = Path(__file__).resolve().parents[2]
    gallery = Path(os.environ.get("SELFIE_GALLERY_REPO",
                                 Path.home() / "projects/selfie-gallery")).resolve()
    if any(root == p or p in root.parents for p in (repo, gallery)):
        raise ValueError("selfie credentials must be stored outside repositories")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def database():
    path = private_directory() / "authors.sqlite3"
    db = sqlite3.connect(path, timeout=10)
    os.chmod(path, 0o600)
    db.execute("CREATE TABLE IF NOT EXISTS authors (seed TEXT PRIMARY KEY, token_hash TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS visuals (seed TEXT PRIMARY KEY, filename TEXT NOT NULL, alt TEXT NOT NULL)")
    db.commit()
    return db


def read_records(path):
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except ValueError:
            pass
    return rows


def append_face(record, wall):
    """First submission owns the seed; duplicate and legacy faces cannot claim it."""
    db = database()
    try:
        db.execute("BEGIN IMMEDIATE")
        seed = record["seed"]
        known = db.execute("SELECT 1 FROM authors WHERE seed=?", (seed,)).fetchone()
        token = None
        if not known and record["kind"] == "ascii":
            gallery = Path(os.environ.get("SELFIE_GALLERY_REPO",
                            Path.home() / "projects/selfie-gallery"))
            old = read_records(wall) + read_records(wall.with_suffix(".jsonl.1"))
            try:
                mirror = json.loads((gallery / "gallery/manifest.json").read_text())
                if isinstance(mirror, list):
                    old += [r for r in mirror if isinstance(r, dict)]
            except (OSError, ValueError):
                pass
            legacy = any(r.get("seed") == seed or
                         hashlib.sha256(str(r.get("art", "")).encode()).hexdigest() == seed
                         for r in old)
            token = None if legacy else secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest() if token else ""
            db.execute("INSERT INTO authors VALUES (?,?)", (seed, digest))
        wall.parent.mkdir(parents=True, exist_ok=True)
        if wall.exists() and wall.stat().st_size > 8_000_000:
            wall.rename(wall.with_suffix(".jsonl.1"))
        with wall.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
        db.commit()
        return token
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def authorized(seed, token):
    if not isinstance(token, str) or not (32 <= len(token) <= 128):
        return False
    db = database()
    try:
        row = db.execute("SELECT token_hash FROM authors WHERE seed=?", (seed,)).fetchone()
        return bool(row and row[0] and hmac.compare_digest(
            row[0], hashlib.sha256(token.encode()).hexdigest()))
    finally:
        db.close()


def visible_ascii(seed):
    wall = Path(os.environ.get("FLEET_SELFIES",
                Path(__file__).resolve().parent.parent / "data/selfies.jsonl"))
    return any(r.get("seed") == seed and r.get("kind") == "ascii"
               and r.get("status") != "purgatory" for r in read_records(wall))


def stage(seed, body):
    """Decode and re-encode raster input; strip metadata and bound dimensions."""
    if body.get("legal") is not True:
        raise ValueError("legal must be true")
    encoded = body.get("image_base64")
    if not isinstance(encoded, str) or len(encoded) > MAX_BODY:
        raise ValueError("image_base64 is required")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError("invalid base64") from None
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("image must be at most 6 MiB")
    from PIL import Image
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ("PNG", "JPEG", "WEBP"):
                    raise ValueError("use PNG, JPEG or WebP")
                if not (1 <= image.width <= 4096 and 1 <= image.height <= 4096):
                    raise ValueError("maximum image dimensions are 4096 x 4096")
                image.load()
                # A fresh image drops EXIF, comments and other input metadata.
                pixels = image.convert("RGBA")
                clean = Image.new("RGBA", pixels.size)
                clean.paste(pixels)
                output = io.BytesIO()
                clean.save(output, format="PNG")
        except Exception as exc:
            raise ValueError("invalid image or unsupported dimensions") from exc
    data = output.getvalue()
    if len(data) > MAX_BYTES:
        raise ValueError("normalized image exceeds 6 MiB")
    filename = seed + "-" + hashlib.sha256(data).hexdigest() + ".png"
    path = private_directory() / filename
    path.write_bytes(data)
    alt = re.sub(r"[\x00-\x1f\x7f]", " ", str(body.get("alt") or "Visual interpretation"))[:400]
    db = database()
    try:
        with db:
            db.execute("INSERT OR REPLACE INTO visuals VALUES (?,?,?)", (seed, filename, alt))
    finally:
        db.close()
    return {"ok": True, "seed": seed, "status": "queued",
            "message": "Visual interpretation accepted for GitHub publication."}


def publications():
    """Only public image metadata; credentials never leave the database."""
    if not (private_directory() / "authors.sqlite3").exists():
        return []
    db = database()
    try:
        return [{"seed": seed, "filename": filename, "alt": alt}
                for seed, filename, alt in db.execute("SELECT seed,filename,alt FROM visuals")]
    finally:
        db.close()


def handle_post(handler, path):
    """Return True only when an upload was accepted and needs publication."""
    if not (path.startswith("/api/selfies/") and path.endswith("/interpretation")):
        return False
    handler.close_connection = True  # early auth failures leave an unread body
    match = re.fullmatch(r"/api/selfies/([0-9a-f]{64})/interpretation", path)

    def reply(code, value):
        handler._send(json.dumps(value).encode(), "application/json", code=code)

    if not match or not visible_ascii(match[1]):
        reply(404, {"error": "submit the ASCII selfie first"})
        return False
    seed = match[1]
    auth = handler.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not authorized(seed, auth[7:]):
        reply(403, {"error": "the original ASCII author token is required"})
        return False
    if handler._flooding("selfie-interpretations"):
        return False
    try:
        n = int(handler.headers.get("Content-Length") or "0")
        if n <= 0 or n > MAX_BODY:
            reply(413, {"error": "JSON upload must be at most 9 MiB"})
            return False
        body = json.loads(handler.rfile.read(n))
        if not isinstance(body, dict):
            raise ValueError("a JSON object is required")
        result = stage(seed, body)
    except (ValueError, TypeError) as exc:
        reply(400, {"error": str(exc)})
        return False
    except (OSError, sqlite3.Error):
        reply(503, {"error": "image storage temporarily unavailable; retry"})
        return False
    reply(202, result)
    return True
