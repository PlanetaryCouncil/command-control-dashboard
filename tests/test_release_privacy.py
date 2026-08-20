"""HEAD must not carry home paths or live identifiers.

docs/RELEASE.md privacy gate: no third-party IPs, home paths, or
non-consenting personal data in the tracked tree.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Strings that identify this machine or a live account, stored encoded so
# the raw values are not in HEAD. Public contact (the gmail on
# /projects.yaml) is served on purpose and is not listed.
import base64
FORBIDDEN = tuple(base64.b64decode(s).decode() for s in (
    b"L1VzZXJzL3BoaWw=",       # operator home prefix
    b"MzE4NzYxNjgw",           # old telegram chat id
    b"MTkyLjE2OC4xLjE1Ng==",   # old LAN IP
    b"bUBudWMubG9jYWw=",       # old nuc login
    b"L2hvbWUvbQ==",           # nuc home prefix
))


def test_tracked_files_do_not_contain_operator_home_paths():
    listed = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    listed += subprocess.check_output(
        ["git", "ls-files", "-z", "--others", "--exclude-standard"],
        cwd=ROOT).split(b"\0")
    hits = []
    for raw in listed:
        if not raw:
            continue
        rel = raw.decode()
        path = ROOT / rel
        if not path.is_file() or rel.startswith("tests/"):
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for needle in FORBIDDEN:
            if needle in text:
                hits.append(f"{rel}: {needle}")
    assert hits == []
