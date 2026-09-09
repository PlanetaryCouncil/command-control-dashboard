"""What gets filed as a poem, and whose poems come first.

Marsita, 2026-09-09: ""go" is not a poem... I just want to see my on top."

Two faults, one root. The archive was built by taking the LAST LINE of every
agent turn, and the last line of a turn is usually not a poem -- it is "go", or
"Please let me know if these answers meet the requirements!", or a
parenthetical aside about an XPRIZE. And the page showed only that archive, so
a poem somebody chose to send had nowhere to appear.
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import poems            # noqa: E402


# ------------------------------------------------------ what is not a poem
def test_one_word_is_not_a_poem():
    assert poems.couplet("go") == []


def test_a_machine_signing_off_is_not_a_poem():
    for junk in ("Please let me know if these answers meet the requirements!",
                 "Hope this helps, let me know if anything else is needed.",
                 "I have completed the requested changes."):
        assert poems.couplet(junk) == [], junk


def test_a_parenthetical_aside_is_a_footnote_to_something_else():
    assert poems.couplet(
        "(The update would unblock the Project Future Vision XPRIZE)") == []


def test_a_question_is_a_machine_asking_for_instructions():
    assert poems.couplet("Should I proceed with the merge?") == []


# ---------------------------------------------------------- what is one
def test_a_real_couplet_survives():
    got = poems.couplet("the mill can run without us\n"
                        "that is not the same as go")
    assert got == ["the mill can run without us",
                   "that is not the same as go"]


def test_a_single_full_line_survives():
    assert poems.couplet("Two machines, one fleet, and neither is driving.")


# ------------------------------------------------------ hers, at the top
def test_submitted_poems_come_from_the_repos_issues(monkeypatch):
    """That is where "how to submit" points, so that is where they arrive."""
    monkeypatch.setattr(poems, "_fetch_issues", lambda: [
        {"number": 4, "title": "Merge and undo",
         "body": "> line one\n> line two",
         "author": {"login": "marsrobertson"},
         "createdAt": "2026-09-09T10:00:00Z"}])
    poems.SUBMITTED_CACHE.update(at=0.0, rows=[])
    got = poems.submitted(now=1000.0)
    assert got[0]["lines"] == ["line one", "line two"], "quote markers kept"
    assert got[0]["author"] == "marsrobertson"


def test_it_reads_github_without_needing_the_gh_cli(monkeypatch):
    """Marsita, 2026-09-09: "Github and repo is source of truth." The repo is
    public and so is the REST endpoint, so the page must not depend on a CLI
    being installed and logged in wherever the board is running."""
    src = (BIN / "poems.py").read_text()
    i = src.index("def _fetch_issues(")
    body = src[i:i + 1800]
    assert "urllib.request" in body
    assert body.index("urllib.request") < body.index("import subprocess")


def test_a_pull_request_is_not_a_poem(monkeypatch):
    """GitHub's issues endpoint returns PRs as issues."""
    import urllib.request

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps([
                {"number": 1, "title": "a poem", "body": "two words here",
                 "user": {"login": "x"}, "created_at": "2026-09-09T00:00:00Z"},
                {"number": 2, "title": "a patch", "body": "code",
                 "user": {"login": "x"}, "created_at": "2026-09-09T00:00:00Z",
                 "pull_request": {"url": "..."}},
            ]).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Resp())
    got = poems._fetch_issues()
    assert [i["title"] for i in got] == ["a poem"]


def test_a_screenshot_is_not_printed_as_a_tag(monkeypatch):
    """GitHub turns a dragged image into an <img>. Printing the tag is worse
    than nothing, and fetching the picture is not this page's decision."""
    class R:
        returncode = 0
        stdout = json.dumps([{"number": 9, "title": "Visual presentation",
                              "body": '<img width="853" src="https://x/y.png" />',
                              "author": {"login": "marsrobertson"},
                              "createdAt": "2026-08-19T10:00:00Z"}])

    monkeypatch.setattr(poems, "_fetch_issues", lambda: json.loads(R.stdout))
    poems.SUBMITTED_CACHE.update(at=0.0, rows=[])
    got = poems.submitted(now=2000.0)
    assert "<img" not in " ".join(got[0]["lines"])
    assert got[0]["lines"] == ["Visual presentation"], "falls back to the title"


def test_github_being_down_costs_the_page_nothing(monkeypatch):
    """Neither route available is an empty band, never a broken page."""
    import urllib.request

    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    poems.SUBMITTED_CACHE.update(at=0.0, rows=[])
    assert poems.submitted(now=3000.0) == []


def test_it_is_cached_so_a_reload_is_not_an_api_call(monkeypatch):
    monkeypatch.setattr(poems, "_fetch_issues",
                        lambda: (_ for _ in ()).throw(AssertionError("refetched")))
    poems.SUBMITTED_CACHE.update(at=5000.0, rows=[{"title": "x"}])
    assert poems.submitted(now=5100.0) == [{"title": "x"}]


def test_sent_poems_are_above_the_fleets_own(monkeypatch):
    """A poem somebody chose to send is a different kind of thing from a
    couplet that fell out of a build. Burying the first among two hundred of
    the second is how you stop receiving them."""
    monkeypatch.setattr(poems, "submitted", lambda **k: [
        {"title": "Merge and undo", "lines": ["a", "b"],
         "author": "marsrobertson", "ts": "2026-09-09", "url": "https://x"}])
    page = poems.page("", "")
    assert page.index('class="band">sent in') < page.index('class="band">from the fleet')
    assert page.index("Merge and undo") < page.index('class="band">from the fleet')


def test_no_submissions_means_no_empty_band(monkeypatch):
    monkeypatch.setattr(poems, "submitted", lambda **k: [])
    assert 'class="band">sent in' not in poems.page("", "")
