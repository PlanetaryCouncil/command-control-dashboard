#!/usr/bin/env python3
"""Mirror the selfie wall into the gallery's GitHub Pages repo.

The wall is one file on this laptop (fleet/data/selfies.jsonl). The public
page is static, on GitHub Pages, and carries a copy in gallery/manifest.json
so it is never blank when the laptop sleeps. On 2026-09-16 the two had
drifted: 16 faces here, 9 there, 5 in common. This closes the gap and keeps
it closed.

Two triggers, one script:
  - the board runs it in the background the moment a face lands (fast path)
  - launchd runs it every 15 minutes (safety net: a missed event, a laptop
    that was asleep, a push that failed on a dead network)

Rules:
  - union, not overwrite: faces that only exist in the mirror (hand-added
    before the wall existed) stay
  - purgatory stays private; a damned face is gone from the wall, and is
    removed from the mirror too, by seed, so the operator's hand reaches
    the public copy
  - commit only when the mirror actually changed; a sync that commits a
    heartbeat buries the days something happened
  - a lock and a 60 s debounce, so a burst of faces is one push, not ten

Exit 0 on "nothing to do". Exit 1 on a failure worth seeing.
"""
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
WALL = Path(os.environ.get("FLEET_SELFIES", FLEET / "data" / "selfies.jsonl"))
GALLERY = Path(os.environ.get(
    "SELFIE_GALLERY_REPO", Path.home() / "projects" / "selfie-gallery"))
MANIFEST = GALLERY / "gallery" / "manifest.json"
DAMNED = WALL.with_name("selfies.damned")   # seeds the operator removed
LOCK = WALL.with_name("selfiesync.lock")
DEBOUNCE = 60


def seed_of(rec):
    return rec.get("seed") or hashlib.sha256(
        str(rec.get("art") or "").encode()).hexdigest()


def read_wall():
    """Blessed faces only, oldest first, in the mirror's flat shape."""
    out = []
    try:
        lines = WALL.read_text(errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("status") == "purgatory":
            continue
        st = d.get("stamp") if isinstance(d.get("stamp"), dict) else {}
        rec = {"kind": d.get("kind") or "ascii", "who": d.get("who") or "anonymous",
               "art": d.get("art") or "", "seed": seed_of(d)}
        if st.get("unix"):
            rec["unix"] = st["unix"]
        elif d.get("ts"):
            try:
                from datetime import datetime
                rec["unix"] = int(datetime.fromisoformat(d["ts"]).timestamp())
            except ValueError:
                pass
        btc = st.get("btc")
        if isinstance(btc, dict) and btc.get("height"):
            rec["btc"] = btc["height"]
        elif isinstance(btc, int):
            rec["btc"] = btc
        out.append(rec)
    return out


def read_mirror():
    try:
        m = json.loads(MANIFEST.read_text())
        return m if isinstance(m, list) else []
    except (OSError, ValueError):
        return []


def read_damned():
    try:
        return set(DAMNED.read_text().split())
    except OSError:
        return set()


def merge(wall, mirror, damned):
    """Newest first. Wall wins on a shared seed; mirror-only faces stay."""
    by_seed = {}
    for rec in mirror:
        rec = dict(rec)
        rec.setdefault("seed", seed_of(rec))
        by_seed[rec["seed"]] = rec
    for rec in wall:
        by_seed[rec["seed"]] = rec          # the wall's copy is the truth
    for s in damned:
        by_seed.pop(s, None)
    items = list(by_seed.values())
    items.sort(key=lambda r: r.get("unix") or 0, reverse=True)
    return items


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(GALLERY), *args],
                          capture_output=True, text=True, check=check)


def generated_changes(wall, damned):
    """Publish only normalized raster files and their seed/alt pairing."""
    import selfieuploads
    manifest = GALLERY / "generated/manifest.json"
    try:
        pairs = json.loads(manifest.read_text())
        if not isinstance(pairs, dict):
            raise ValueError("generated manifest must be an object")
    except FileNotFoundError:
        pairs = {}
    visible = {r["seed"] for r in wall if r.get("kind") == "ascii"}
    held = {r.get("seed") for r in selfieuploads.read_records(WALL)
            if r.get("status") == "purgatory"}
    for seed in damned | held:
        pairs.pop(seed, None)
    changes = {}
    for record in selfieuploads.publications():
        seed, filename = record["seed"], record["filename"]
        if seed not in visible or seed in damned or seed in held:
            continue
        if not re.fullmatch(r"[0-9a-f]{64}-[0-9a-f]{64}\.png", filename):
            raise ValueError("invalid staged image filename")
        data = (selfieuploads.private_directory() / filename).read_bytes()
        target = GALLERY / "generated" / filename
        if not target.exists() or target.read_bytes() != data:
            changes[target] = data
        pairs[seed] = {"src": "generated/" + filename, "alt": record["alt"]}
    new = (json.dumps(pairs, ensure_ascii=False, indent=2) + "\n").encode()
    if pairs or manifest.exists():
        if not manifest.exists() or manifest.read_bytes() != new:
            changes[manifest] = new
    return changes


def main():
    if not (GALLERY / ".git").is_dir():
        print(f"no gallery checkout at {GALLERY}", file=sys.stderr)
        return 1
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as lk:
        try:
            # A queued visual must not miss publication just because an ASCII
            # sync is already in flight. Forced workers wait, then reread state.
            fcntl.flock(lk, fcntl.LOCK_EX | (0 if "--now" in sys.argv else fcntl.LOCK_NB))
        except OSError:
            print("another sync is running")
            return 0
        lk.seek(0)
        try:
            last = float(lk.read().strip() or 0)
        except ValueError:
            last = 0
        if "--now" not in sys.argv and time.time() - last < DEBOUNCE:
            print("debounced")
            return 0

        # Refresh before merging so another writer's remote additions survive.
        dirty = git("status", "--porcelain", "--", "gallery/manifest.json",
                    "generated/manifest.json").stdout.strip()
        if dirty:
            print("manifest has local edits; not touching it", file=sys.stderr)
            return 1
        pulled = git("pull", "-q", "--ff-only", check=False)
        if pulled.returncode:
            print("gallery pull failed; not overwriting the mirror", file=sys.stderr)
            return 1
        wall, damned = read_wall(), read_damned()
        merged = merge(wall, read_mirror(), damned)
        new = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"
        old = MANIFEST.read_text() if MANIFEST.exists() else ""
        changes = generated_changes(wall, damned)
        if new != old:
            changes[MANIFEST] = new.encode()
        if not changes:
            # Retry our own unpublished sync commits after a transient push failure.
            pending = git("log", "--format=%s", "@{u}..HEAD", check=False)
            subjects = pending.stdout.splitlines() if pending.returncode == 0 else []
            if subjects and all(s.startswith("mirror:") for s in subjects):
                pushed = git("push", "-q", check=False)
                if pushed.returncode:
                    print("mirror push retry failed", file=sys.stderr)
                    return 1
            print(f"mirror current ({len(merged)} faces)")
            return 0

        # Never write over someone's uncommitted edits in that checkout.
        paths = [str(p.relative_to(GALLERY)) for p in changes]
        dirty = git("status", "--porcelain", "--", *paths).stdout.strip()
        if dirty:
            print("manifest has local edits; not touching it", file=sys.stderr)
            return 1
        for path, data in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        git("add", "--", *paths)
        git("commit", "--only", "-q", "-m",
            f"mirror: {len(merged)} faces on the wall\n\n"
            "Pushed by fleet/bin/selfiesync.py in command-control-dashboard. "
            "The wall on the laptop is the source; this file is its echo.",
            "--", *paths)
        r = git("push", "-q", check=False)
        if r.returncode:
            print(f"push failed: {r.stderr.strip()}", file=sys.stderr)
            return 1
        lk.seek(0); lk.truncate(); lk.write(str(time.time()))
        print(f"pushed mirror: {len(merged)} faces")
        return 0


if __name__ == "__main__":
    sys.exit(main())
