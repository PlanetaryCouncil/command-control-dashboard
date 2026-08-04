#!/usr/bin/env python3
"""The gallery slot: what the home dashboard is showing right now.

  art.py show                                   what's hanging
  art.py set IMAGE_URL "Title" [--artist A] [--url LINK] [--note N]

This board is a home dashboard and the home makes art — so it curates one
piece at a time, on purpose, by hand. Setting a new piece announces it on
the live stream; the previous piece goes into art/history.jsonl so the
gallery remembers what hung before.

Marsita, 2026-08-04: "we are home dashboard — we curate latest art —
this is art."
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
ART = FLEET / "art"
CURRENT = ART / "current.json"
HISTORY = ART / "history.jsonl"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import events as ev  # noqa: E402


def show() -> None:
    try:
        d = json.loads(CURRENT.read_text())
    except (OSError, ValueError):
        print("the gallery is empty — art.py set IMAGE_URL \"Title\"")
        return
    print(f"{d.get('title', '?')} — {d.get('artist', '?')}")
    print(f"  image  {d.get('image')}")
    print(f"  link   {d.get('url')}")
    print(f"  since  {d.get('since')}")
    if d.get("note"):
        print(f"  note   {d['note']}")


def set_piece(image: str, title: str, artist: str, url: str, note: str) -> None:
    ART.mkdir(exist_ok=True)
    try:
        old = json.loads(CURRENT.read_text())
        with HISTORY.open("a") as fh:
            fh.write(json.dumps(old) + "\n")
    except (OSError, ValueError):
        pass
    piece = {"title": title, "artist": artist, "image": image,
             "url": url or image, "note": note,
             "since": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    CURRENT.write_text(json.dumps(piece, indent=2) + "\n")
    ev.emit("art", "ok", f"[art] now showing: {title}"
            + (f" — {artist}" if artist else ""))
    print(f"hung: {title}")


def fetch_and_hang(url: str, title: str, artist: str, note: str) -> None:
    """Pull a submitted image into the house, then hang it.

    Issues are the easy door (drag, drop, done), but a githubusercontent
    URL must not become the board's dependency: on a private repo those
    links expire, on a public one every visitor's browser then fetches
    from a third party. So the file comes home to fleet/static/ first,
    shrunk if it is heavy — a 2.9MB hero once made the whole board feel
    broken.
    """
    import subprocess
    import urllib.request
    ART.mkdir(exist_ok=True)
    dest = FLEET / "static" / "artwork.png"
    req = urllib.request.Request(url, headers={"User-Agent": "fleet-art/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if len(data) > 25_000_000:
        raise SystemExit("refused: over 25MB")
    dest.write_bytes(data)
    if len(data) > 900_000:          # shrink, keep the original beside it
        (FLEET / "static" / "artwork-full.jpg").write_bytes(data)
        subprocess.run(["sips", "-Z", "1400", "-s", "format", "jpeg",
                        "-s", "formatOptions", "82", str(dest),
                        "--out", str(dest)],
                       capture_output=True)
    kb = dest.stat().st_size // 1024
    print(f"fetched {len(data)//1024}KB -> {kb}KB at static/artwork.png")
    set_piece("/static/artwork.png", title, artist, "", note)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("set")
    s.add_argument("image")
    s.add_argument("title")
    s.add_argument("--artist", default="Marsita the Ultra")
    s.add_argument("--url", default="")
    s.add_argument("--note", default="")
    sub.add_parser("show")
    f = sub.add_parser("fetch")
    f.add_argument("url")
    f.add_argument("title")
    f.add_argument("--artist", default="")
    f.add_argument("--note", default="")
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch_and_hang(a.url, a.title, a.artist, a.note)
    elif a.cmd == "set":
        set_piece(a.image, a.title, a.artist, a.url, a.note)
    else:
        show()
