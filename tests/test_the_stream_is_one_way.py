"""The board pane streams. It is not a terminal and cannot be typed into.

Marsita, 2026-09-05: "terminal in the browser is unworkable... scroll does not
work... 1 command only. And then nothing works, neither the typing in console,
neither the text area ---> bad UX... Just stream me stuff 1 way only... No
extra noise... Only the stuff I need to see."

Acceptance criteria, one test each:

  1. Nothing on the page can put a keystroke into the machine.
  2. Only three kinds of line: what was asked, what was answered, one grey
     signpost per tool.
  3. Thinking, tool results, system notices and attachments never appear.
  4. Scrolling up to read something is not undone by the next poll.
  5. The script parses -- checked by an engine, not by hope.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import stream            # noqa: E402


def row(**kw):
    return json.dumps(kw)


# ------------------------------------------------- 1. no way in, at all
def test_the_pane_has_no_input_of_any_kind():
    src = (BIN / "oneview.py").read_text()
    i = src.index("TERMPANE_HTML")
    pane = src[i:src.index("\n", i)]
    for gone in ("<textarea", "<form", "<button", 'id="term"'):
        assert gone not in pane, gone


def test_there_is_no_terminal_left_to_talk_to():
    src = (BIN / "oneview.py").read_text()
    assert "new Terminal(" not in src
    assert "new WebSocket(" not in src, "the pty socket is back"
    assert "/static/xterm.js" not in src
    assert "ws/terminal" not in src


# ------------------------------------------- 2 & 3. only what is wanted
def test_a_question_and_an_answer_survive():
    said = stream.parse(row(type="user", timestamp="2026-09-05T01:02:03Z",
                            message={"content": "fix the footer"}))
    assert said == {"at": "01:02:03", "who": "you", "text": "fix the footer"}
    ans = stream.parse(row(type="assistant", timestamp="2026-09-05T01:02:09Z",
                           message={"content": [{"type": "text", "text": "done"}]}))
    assert ans["who"] == "claude" and ans["text"] == "done"


def test_a_tool_is_one_grey_line_with_the_argument_that_names_it():
    got = stream.parse(row(type="assistant", timestamp="2026-09-05T01:02:03Z",
                           message={"content": [
                               {"type": "tool_use", "name": "Bash",
                                "input": {"command": "git push origin main"}}]}))
    assert got == {"at": "01:02:03", "who": "tool",
                   "text": "Bash · git push origin main"}


def test_a_long_command_is_clipped_not_pasted_whole():
    got = stream.parse(row(type="assistant", timestamp="2026-09-05T01:02:03Z",
                           message={"content": [
                               {"type": "tool_use", "name": "Bash",
                                "input": {"command": "x" * 500}}]}))
    assert len(got["text"]) < 130 and got["text"].endswith("…")


def test_thinking_alone_is_not_a_line():
    assert stream.parse(row(type="assistant", timestamp="2026-09-05T01:02:03Z",
                            message={"content": [{"type": "thinking",
                                                  "thinking": "hmm"}]})) is None


def test_a_tool_result_is_the_machine_answering_itself():
    """Replaying a command's stdout here would be the exact wall of terminal
    this page exists to replace."""
    assert stream.parse(row(type="user", timestamp="2026-09-05T01:02:03Z",
                            message={"content": [{"type": "tool_result",
                                                  "content": "1074 passed"}]})) is None


def test_system_notices_are_not_something_anyone_said():
    for junk in ("<system-reminder>be good</system-reminder>",
                 "<command-name>/compact</command-name>",
                 "Caveat: the messages below were generated"):
        assert stream.parse(row(type="user", timestamp="2026-09-05T01:02:03Z",
                                message={"content": junk})) is None


def test_system_and_attachment_rows_are_dropped():
    for kind in ("system", "attachment", "summary"):
        assert stream.parse(row(type=kind, message={"content": "x"})) is None


def test_a_broken_line_does_not_stop_the_stream():
    assert stream.parse("{ not json") is None


# ---------------------------------------------------- the tail it serves
def test_the_tail_reads_the_session_being_worked_in(tmp_path, monkeypatch):
    d = tmp_path / ".claude" / "projects"
    slug = re.sub(r"[^A-Za-z0-9-]", "-", str(tmp_path))
    (d / slug).mkdir(parents=True)
    old = d / slug / "old.jsonl"
    new = d / slug / "new.jsonl"
    old.write_text(row(type="assistant", timestamp="2026-09-01T00:00:00Z",
                       message={"content": [{"type": "text", "text": "stale"}]}) + "\n")
    new.write_text(row(type="assistant", timestamp="2026-09-05T00:00:00Z",
                       message={"content": [{"type": "text", "text": "live"}]}) + "\n")
    import os
    os.utime(old, (1, 1))
    monkeypatch.setattr(stream, "HOME", tmp_path)
    got = stream.tail(str(tmp_path))
    assert [l["text"] for l in got["lines"]] == ["live"]
    assert got["session"] == "new"


def test_no_transcript_is_an_empty_stream_not_a_500(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "HOME", tmp_path)
    assert stream.tail(str(tmp_path)) == {"lines": [], "session": "", "at": 0.0}


def test_the_endpoint_is_local_only():
    src = (BIN / "fleet.py").read_text()
    i = src.index('if path == "/api/stream":')
    assert "self._remote()" in src[i:i + 400]


# ------------------------------------------------------- 4. it stays put
def test_scrolling_up_survives_the_next_poll():
    """Being yanked back to the bottom mid-read is what made the old pane
    unusable. Only follow the tail if that is where you already were."""
    src = (BIN / "oneview.py").read_text()
    assert "const atEnd = body.scrollTop + body.clientHeight >= body.scrollHeight - 40;" in src
    assert "if (atEnd || !streamSeen) body.scrollTop = body.scrollHeight;" in src


def test_an_unchanged_stream_is_not_rerendered():
    """Rebuilding the list on every poll throws the scroll position away."""
    src = (BIN / "oneview.py").read_text()
    assert "if (sig === streamSeen) return;" in src


def test_it_polls_slowly_because_it_is_read_not_watched():
    assert "setInterval(loadStream, 3000);" in (BIN / "oneview.py").read_text()


# --------------------------------------------------------- 5. it parses
def test_the_boards_javascript_parses():
    node = shutil.which("node")
    if not node:
        return
    src = (BIN / "oneview.py").read_text()
    m = re.search(r"^JS = r?\"\"\"(.*?)^\"\"\"", src, re.S | re.M)
    assert m
    r = subprocess.run([node, "--check", "-"], input=m.group(1),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[-1500:]
