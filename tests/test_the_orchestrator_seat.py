"""The strongest available model leads, and only one builder runs at a time.

Two bugs met here on 2026-09-04.

The first was a wrong belief: that the Claude plan was dead, because the
Anthropic API refused hermes ("third-party apps now draw from your extra
usage") and Copilot listed thirty models it would not serve. Both true, both
irrelevant -- the `claude` CLI runs on the subscription, and it had been
sitting on the NUC working the whole time. The builder had been demoted to
grok on the strength of that belief.

The second was structural: three `fleet-build@` template instances, each on a
30-second gap with a four-hour timeout, each calling a 3B local model at 5
tokens/sec. Six cores pinned for a day, nothing built for three days.

These tests pin both fixes.
"""

import importlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import chat        # noqa: E402
import pipeline    # noqa: E402


def reload_chat(monkeypatch, value):
    """CLAUDE_MODEL binds at import, so a fixture that only sets the env var
    tests nothing. This is the same trap that let the suite write to the live
    events log for a day."""
    monkeypatch.setenv("FLEET_CLAUDE_MODEL", value)
    return importlib.reload(chat)


# --- the model ---------------------------------------------------------

def test_the_default_model_is_a_frontier_one():
    assert chat.CLAUDE_MODEL == "claude-fable-5-1"


def test_the_argv_carries_the_model():
    argv = chat.claude_argv("--allowedTools", "WebSearch")
    assert argv[:2] == ["claude", "--print"]
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == chat.CLAUDE_MODEL
    assert argv[-2:] == ["--allowedTools", "WebSearch"]


def test_an_empty_model_passes_no_flag(monkeypatch):
    """An older CLI does not know --model. Empty means "your default"."""
    mod = reload_chat(monkeypatch, "")
    try:
        assert "--model" not in mod.claude_argv("--allowedTools")
    finally:
        monkeypatch.delenv("FLEET_CLAUDE_MODEL", raising=False)
        importlib.reload(chat)


def test_the_model_is_overridable(monkeypatch):
    mod = reload_chat(monkeypatch, "claude-opus-5")
    try:
        assert "claude-opus-5" in mod.claude_argv()
    finally:
        monkeypatch.delenv("FLEET_CLAUDE_MODEL", raising=False)
        importlib.reload(chat)


def test_both_call_sites_share_one_argv():
    """pipeline's builder and chat's adapter drifting apart is how a model
    chosen in one becomes a model the other silently disagrees with."""
    src = (BIN / "pipeline.py").read_text()
    assert "chat.claude_argv(" in src
    assert '"claude", "--print"' not in src, "pipeline built its own argv again"


# --- who builds --------------------------------------------------------

def test_claude_builds_by_default(monkeypatch):
    monkeypatch.delenv("FLEET_BUILDER", raising=False)
    assert pipeline.builder_name() == "claude"


def test_the_builder_is_still_overridable(monkeypatch):
    monkeypatch.setenv("FLEET_BUILDER", "grok")
    assert pipeline.builder_name() == "grok"


# --- the cadence -------------------------------------------------------

CFG = json.loads((BIN.parent / "config.json").read_text())
APPLY = (BIN / "apply-config-systemd.sh").read_text()


def test_config_bounds_a_builder_slot():
    b = CFG["builders"]
    assert b["gap_seconds"] >= 60
    assert b["max_seconds"] >= b["gap_seconds"]


def test_the_builder_unit_is_generated_not_hand_written():
    """The runaway units were never in apply-config, so config.json said
    nothing about them and neither machine could be fixed by re-running it."""
    assert re.search(r'^\s*unit build\s', APPLY, re.M), "no generated build unit"
    assert "builders" in APPLY and "gap_seconds" in APPLY


def test_there_is_one_builder_not_three_instances():
    """The comment above the unit names the old template on purpose -- that is
    history worth keeping. What must not come back is a live `unit` line
    generating instances."""
    live = [l for l in APPLY.splitlines()
            if re.match(r"\s*unit\s", l) and not l.lstrip().startswith("#")]
    assert "fleet-build@" not in "\n".join(live), "instances race each other"
    # The only place the old name may still appear in live code is the
    # retirement loop that deletes them.
    assert 'disable --now "fleet-build@$i.timer"' in APPLY


def test_the_gap_counts_from_the_end_of_the_last_slot():
    """OnUnitActiveSec counts from the START, so a slow job queues against
    itself. OnUnitInactiveSec cannot overlap however long a slot runs."""
    line = [l for l in APPLY.splitlines() if re.match(r'\s*unit build\s', l)][0]
    assert 'after "$BD_GAP"' in line, line


def test_a_hung_slot_cannot_hold_the_timer_for_four_hours():
    assert "TimeoutStartSec=${UNIT_TIMEOUT:-3600}" in APPLY
    assert "$BD_MAX" in APPLY
    assert CFG["builders"]["max_seconds"] <= 3600


def test_the_builder_actually_sits():
    """Writing a unit without enabling it is how the NUC served the board for
    weeks while running none of the fleet."""
    sitting = re.search(r'^SITTING="([^"]+)"', APPLY, re.M).group(1).split()
    assert "build" in sitting


# --- the pool ----------------------------------------------------------

def test_claude_is_actually_in_the_builder_pool():
    """The default in builder_name() is theatre on its own: backlog.sh sets
    FLEET_BUILDER from next_builder.py, so a name absent from POOL never
    builds however the default reads. Fable 5.1 found this auditing its own
    fleet on 2026-09-04 -- it had been made the orchestrator and then left
    out of the rotation that chooses one."""
    import next_builder
    assert "claude" in next_builder.POOL
    assert next_builder.POOL[0] == "claude", "it leads"


def test_claude_is_allowed_to_spend():
    """eligible() reads the spend table. Marked 'rare' while the plan was
    believed dead, it would be skipped in favour of an exhausted vendor."""
    cfg = json.loads((BIN.parent / "config.json").read_text())
    assert cfg["quotas"]["spend"]["claude"] == "plenty"
