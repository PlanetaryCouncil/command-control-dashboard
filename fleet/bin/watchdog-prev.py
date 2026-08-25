#!/usr/bin/env python3
"""Print the previous watchdog result as `head<TAB>summary<TAB>when`, but only
if it was a PASS that recorded which commit it tested.

Its own file rather than a heredoc inside watchdog.sh: the skip decision is the
part of that script most likely to be wrong in a way nobody notices, and a
shell heredoc is the worst place to read or test one.

Prints nothing when there is no usable previous result — no previous file, a
failure, an older record from before `head` was written, or unparseable JSON.
Nothing means "run the tests", which is the safe answer to every one of those.
"""

import json
import sys
from pathlib import Path


def previous(path) -> str:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return ""
    if data.get("status") != "pass" or not data.get("head"):
        return ""
    fields = [str(data.get(k) or "").replace("\t", " ").replace("\n", " ")
              for k in ("head", "summary", "last_run")]
    return "\t".join(fields)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(2)
    out = previous(sys.argv[1])
    if out:
        print(out)
