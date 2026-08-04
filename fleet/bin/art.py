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
    a = ap.parse_args()
    if a.cmd == "set":
        set_piece(a.image, a.title, a.artist, a.url, a.note)
    else:
        show()
