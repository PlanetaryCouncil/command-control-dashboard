"""Process snapshot: RSS in MB, heaviest sitters, no extra ps storm."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fleet" / "bin"))
import procs  # noqa: E402


def test_short_name_is_the_binary():
    assert procs._short_name("/usr/local/opt/node@22/bin/node gateway") == "node"
    assert procs._short_name("agy") == "agy"


def test_heavies_rank_by_rss_and_skip_mice():
    rows = [
        {"pid": 1, "rss_kb": 50*1024, "cpu": 1, "mem": 2, "elapsed": "1:00",
         "cmd": "/Apps/Chrome.app/Contents/MacOS/Google Chrome"},
        {"pid": 2, "rss_kb": 700*1024, "cpu": 14, "mem": 8, "elapsed": "12-00:00",
         "cmd": "/usr/local/opt/node@22/bin/node openclaw/dist/index.js gateway"},
        {"pid": 3, "rss_kb": 8*1024, "cpu": 0.1, "mem": 0.2, "elapsed": "0:01",
         "cmd": "/usr/sbin/cfprefsd daemon"},
    ]
    h = procs.heavies(rows)
    assert [x["pid"] for x in h] == [2, 1]
    assert h[0]["label"] == "OpenClaw gateway"
    assert h[0]["rss_mb"] == 700.0
    assert h[1]["label"] == "Google"


def test_snapshot_has_rss_and_heavies():
    snap = procs.snapshot()
    assert "heavies" in snap
    for bucket in ("fleet", "external", "heavies"):
        for p in snap[bucket]:
            assert "rss_mb" in p
    if snap["heavies"]:
        rss = [p["rss_mb"] for p in snap["heavies"]]
        assert rss == sorted(rss, reverse=True)
