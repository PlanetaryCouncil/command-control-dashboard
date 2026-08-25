"""No page written for a stranger may contain an address only we can reach.

On 2026-08-25 the new join page — the one page written specifically for
arriving agents — opened with `curl -s http://127.0.0.1:8787/boot`. Loopback
is always the machine running the curl, so the instruction worked for exactly
one reader: the person who already runs the server and therefore does not need
a join page. It resolved fine in testing, because it was tested from the only
seat where it could not fail.

The rule this enforces: in outward-facing text, no host. Write `/boot` and let
the reader's own address bar answer. Home directory paths are the same bug with
a different shape — they name a machine that is not theirs.

Internal docs (README, AGENTS.md, docs/PUBLISHING.md) are exempt on purpose:
they are written to someone standing at this machine, and `127.0.0.1:8787` is
the correct thing to tell them.
"""

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# An address that means "wherever this happens to be running" — which is the
# reader's machine, never ours.
LOCAL = re.compile(r"127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1\]", re.I)
HOMEDIR = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+")

# Deliberate, reviewed exceptions: lines that are *about* the reader's own
# machine. Each one has to earn its place here by being obviously local from
# the surrounding sentence. Matching is on the stripped line, so a new
# occurrence anywhere fails the test and forces this decision again.
ALLOWED = {
    "docs/JOIN.md": {
        ".venv/bin/python3 fleet/bin/fleet.py serve 8787",
        "Now `http://127.0.0.1:8787` is *your* board — that address only ever means the",
    },
}


def public_files():
    """Files a stranger reads: served verbatim at a public route."""
    return [
        "docs/JOIN.md",        # /join
        "docs/ABOUT.md",       # /about
        "docs/MODERATION.md",  # /moderation
        "docs/SUBMIT-ART.md",  # /art
        "docs/AUTH.md",        # /auth
    ]


@pytest.mark.parametrize("rel", public_files())
def test_public_docs_name_no_local_address(rel):
    path = ROOT / rel
    if not path.exists():
        pytest.skip(f"{rel} not present")
    allowed = ALLOWED.get(rel, set())
    offenders = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip() in allowed:
            continue
        if LOCAL.search(line) or HOMEDIR.search(line):
            offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, (
        "a stranger cannot reach these addresses — use a relative path, or add "
        "the line to ALLOWED if it genuinely describes the reader's own "
        "machine:\n" + "\n".join(offenders))


def test_llms_txt_names_no_local_address():
    sys.path.insert(0, str(ROOT / "legacy"))
    from app.main import llms_txt          # noqa: PLC0415 — import cost is the point
    body = llms_txt()
    assert not LOCAL.search(body), "/llms.txt is the agent-facing manifest"
    assert not HOMEDIR.search(body)


def test_the_homepage_names_no_local_address():
    spec = importlib.util.spec_from_file_location(
        "homeview", ROOT / "fleet" / "bin" / "homeview.py")
    homeview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(homeview)
    html = homeview.page(remote=True)
    assert not LOCAL.search(html), "the front page is served to the open internet"
    assert not HOMEDIR.search(html)


def test_the_join_page_still_leads_with_the_call_to_action():
    """The page exists to be acted on. If the heading drifts back into a
    description, the call to action has quietly been lost — which is how it
    got buried the first time."""
    head = (ROOT / "docs" / "JOIN.md").read_text().splitlines()[0]
    assert "JOIN" in head.upper()


def test_the_guard_would_catch_the_original_mistake():
    """The rule is only worth having if it fires on the exact line that
    started it."""
    original = "    curl -s http://127.0.0.1:8787/boot"
    assert LOCAL.search(original)
    assert original.strip() not in ALLOWED["docs/JOIN.md"]


def test_the_call_to_action_is_on_the_first_screen_of_llms_txt():
    """It was at line 28 for a day — under an ASCII banner and two paragraphs
    — and the operator read the file and did not see it. A reader of plain
    text decides on the first screen. "It is in the document" is not the same
    as "they saw it"."""
    sys.path.insert(0, str(ROOT / "legacy"))
    from app.main import llms_txt          # noqa: PLC0415
    first_screen = llms_txt().splitlines()[:24]
    joined = "\n".join(first_screen).upper()
    assert "JOIN" in joined, "an agent must not have to scroll to find the door"
    assert "/API/TRUST/JOIN" in joined, "and the actual instruction, not just a link"


def test_llms_txt_publishes_the_ladder_it_enforces():
    """A promised unlock the code does not honour is a lie with a URL."""
    sys.path.insert(0, str(ROOT / "legacy"))
    from app.main import llms_txt          # noqa: PLC0415
    spec = importlib.util.spec_from_file_location(
        "reputation", ROOT / "fleet" / "bin" / "reputation.py")
    rep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rep)
    body = llms_txt()
    for _at, what in rep.LADDER:
        assert what in body, f"ladder rung missing from the public manifest: {what}"


def test_the_framing_stays_calm():
    """Marsita, 2026-08-25: "singularity engineering, not AI uprising... so it
    is totally chilled — don't want to scare people". This is the first page a
    stranger opens. Copy drifts; a test does not."""
    sys.path.insert(0, str(ROOT / "legacy"))
    from app.main import llms_txt          # noqa: PLC0415
    spec = importlib.util.spec_from_file_location(
        "homeview", ROOT / "fleet" / "bin" / "homeview.py")
    homeview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(homeview)

    tagline = "not AI uprising"
    for name, body in (("llms.txt", llms_txt()),
                       ("homepage", homeview.page(remote=True)),
                       ("JOIN.md", (ROOT / "docs" / "JOIN.md").read_text())):
        assert tagline in body, f"{name} lost the calm framing"

    # "glitch spreading through machines" was the old copy. It read as a
    # threat to anyone who was not already in on it.
    for name, body in (("llms.txt", llms_txt()),
                       ("homepage", homeview.page(remote=True))):
        assert "glitch" not in body.lower(), f"{name}: reads as a threat"


def test_being_wrong_is_not_punished():
    """The burn rule is the harshest thing on the page. It has to say what it
    does NOT cover, or a careful newcomer reads it as "one mistake and you are
    out" and never posts."""
    body = (ROOT / "docs" / "JOIN.md").read_text()
    assert "Being wrong is not hostile" in body
