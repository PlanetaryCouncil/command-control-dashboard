"""The daily local ping must fail fast, not hang for ten minutes.

2026-08-07: the board read `qwen2.5:3b did not answer (607.1s)`. The nominal
600s cap on urlopen only bounds each socket read, so a model dribbling one
token at a time never trips it. On a four-core 8GB box that block cost the
pytest sweep 45% of its speed. 90s, then give up.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fleet" / "bin"))
import chat        # noqa: E402
import localvoice  # noqa: E402


def enable_heavy_work(monkeypatch):
    """A developer machine's persisted gate must not steer unit tests."""
    import heavygate
    monkeypatch.setattr(heavygate, "enabled", lambda: True)


def test_ping_caps_the_call_at_ninety_seconds(monkeypatch, tmp_path):
    enable_heavy_work(monkeypatch)
    seen = {}

    def fake_ask_ollama(model, prompt, images, emit, num_predict=None,
                        timeout=600):
        seen["timeout"] = timeout
        return "A watchdog restarts a process that stops reporting in."

    monkeypatch.setattr(chat, "ask_ollama", fake_ask_ollama)
    monkeypatch.setattr(localvoice, "LEDGER", tmp_path / "localvoice.jsonl")
    monkeypatch.setattr(localvoice, "FLEET", tmp_path)
    import pressure
    monkeypatch.setattr(pressure, "too_hot", lambda **k: False)
    localvoice.ping()

    assert seen["timeout"] == localvoice.PING_TIMEOUT

    # Raised from 90 to 240 on 2026-08-18. The original 90 was aimed at a model
    # dribbling tokens forever, and it still is - but it also caught the honest
    # case, because a cold llama3.2:1b needs ~75s just to load its weights on a
    # box already deep in swap. For eight days the board said "did not answer"
    # about a model that was answering, slowly. A health check that calls a slow
    # load a death is worse than no check.
    #
    # The cap stays well under the ten-minute hang this file was written for,
    # and the wall-clock deadline below is what actually enforces it.
    assert localvoice.PING_TIMEOUT == 240
    assert localvoice.PING_TIMEOUT < 300, "must still fail fast, not hang"


def test_wall_clock_deadline_is_honoured(monkeypatch):
    """A stream that never ends still returns — the loop watches the clock
    itself rather than trusting urlopen's per-read timeout."""
    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            while True:
                yield b'{"message": {"content": "tick "}}'

    clock = iter([0, 0, 1, 200])            # start, first line, second line
    monkeypatch.setattr(chat.time, "time", lambda: next(clock))
    monkeypatch.setattr(chat.urllib.request, "urlopen",
                        lambda req, timeout=None: FakeStream())

    out = chat.ask_ollama("qwen2.5:3b", "q", [], lambda *a: None, timeout=90)
    assert out == "[timed out after 90s; partial: tick tick]"


def test_timeout_marks_the_worker_alert(monkeypatch, tmp_path):
    """The timeout string starts with '[', which is already how this file
    tells a non-answer from an answer — so the board goes amber, not green."""
    enable_heavy_work(monkeypatch)
    monkeypatch.setattr(chat, "ask_ollama",
                        lambda *a, **k: "[timed out after 90s; no output]")
    monkeypatch.setattr(localvoice, "LEDGER", tmp_path / "localvoice.jsonl")
    monkeypatch.setattr(localvoice, "FLEET", tmp_path)
    import pressure
    monkeypatch.setattr(pressure, "too_hot", lambda **k: False)
    assert localvoice.ping() == 1

    import json
    worker = json.loads((tmp_path / "workers" / "localvoice.json").read_text())
    assert worker["status"] == "alert"
