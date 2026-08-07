"""The log ceiling — and the ledgers it must never touch.

Marsita, issue #45: "trim by default log to 1000 lines as well. That's our
'context window', old and noisy messages are auto purged."

The dangerous half is not the trimming. It is trimming the wrong file: the
proposal ledger and the pipeline verdicts are the fleet's memory of what it
decided, and a truncated memory is worse than a large one.
"""

import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import trim  # noqa: E402


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    (tmp_path / "logs").mkdir()
    (tmp_path / "rota").mkdir()
    monkeypatch.setattr(trim, "FLEET", tmp_path)
    return tmp_path


def write(p: Path, n: int):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(f"line {i}\n" for i in range(n)))
    return p


def test_keeps_the_last_n_lines(fleet):
    p = write(fleet / "logs" / "noisy.log", 3000)
    dropped = trim.trim(p, 1000)
    kept = p.read_text().splitlines()
    assert dropped == 2000
    assert len(kept) == 1000
    assert kept[0] == "line 2000", "the RECENT thousand, not the first"
    assert kept[-1] == "line 2999"


def test_a_short_file_is_left_alone(fleet):
    p = write(fleet / "logs" / "quiet.log", 12)
    assert trim.trim(p, 1000) == 0
    assert len(p.read_text().splitlines()) == 12


def test_dry_run_changes_nothing(fleet):
    p = write(fleet / "logs" / "noisy.log", 2500)
    assert trim.trim(p, 1000, dry_run=True) == 1500
    assert len(p.read_text().splitlines()) == 2500


def test_the_ledgers_are_never_targeted(fleet):
    """Proposals and verdicts are memory, not chatter. Losing the record of
    what was decided is not the same as losing noise."""
    write(fleet / "logs" / "pipeline.jsonl", 5000)
    write(fleet / "logs" / "proposals.jsonl", 5000)
    write(fleet / "logs" / "chatter.jsonl", 5000)
    names = {p.name for p in trim.targets()}
    assert "pipeline.jsonl" not in names
    assert "proposals.jsonl" not in names
    assert "chatter.jsonl" in names, "ordinary jsonl logs are still trimmed"


def test_events_are_trimmed(fleet):
    """The event stream is the noisiest thing the fleet writes."""
    write(fleet / "events.jsonl", 4000)
    assert "events.jsonl" in {p.name for p in trim.targets()}


def test_a_missing_file_is_not_a_crash(fleet):
    assert trim.trim(fleet / "logs" / "gone.log", 1000) == 0
