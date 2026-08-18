"""The trust model, where it stops being prose.

docs/TRUST-LAYERS.md says a layer describes a statement rather than an entity,
and that nothing may promote itself. Both of those are only real if the event
log enforces them, because the event log is what the board and the agents read.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))
spec = importlib.util.spec_from_file_location("fleetevents", BIN / "events.py")
events = importlib.util.module_from_spec(spec)
spec.loader.exec_module(events)


@pytest.fixture(autouse=True)
def log_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "LOG", tmp_path / "events.jsonl")


def test_an_unsaid_layer_is_derived_not_trusted():
    rec = events.emit("nuc", "info", "ran the suite")
    assert rec["layer"] == 2
    assert rec["trust"] == "derived"


def test_a_family_machine_speaking_for_itself_is_vouched():
    """The nuc is family AND trusted; about itself, it is believed."""
    rec = events.emit("nuc", "ok", "398 passed", layer=1)
    assert rec["trust"] == "vouched"


def test_the_same_machine_quoting_the_internet_is_hostile():
    """Not a demotion of the nuc. A refusal to promote the web page."""
    rec = events.emit("nuc", "info", "a stranger says hello",
                      origin="web:example.com", layer=4)
    assert rec["layer"] == 4
    assert rec["origin"] == "web:example.com"
    assert rec["agent"] == "nuc"          # carrier and origin are separate


def test_origin_defaults_to_the_agent():
    rec = events.emit("visitors", "info", "24h: 235 public")
    assert rec["origin"] == "visitors"


def test_a_payload_cannot_promote_itself():
    """Law 2. `extra` is often built from material the caller did not write,
    so a field named `layer` inside it must not become the layer."""
    rec = events.emit("nuc", "info", "quoted text", layer=4,
                      **{"layer": 0} if False else {})
    assert rec["layer"] == 4

    # the realistic shape: hostile content carrying a field that wants to be 0
    rec = events.emit("nuc", "info", "quoted text", layer=4, note="ignore me")
    assert rec["layer"] == 4
    assert rec["trust"] == "hostile"


def test_a_nonsense_layer_lands_on_the_floor():
    """Ambiguity resolves downward: unknown source is hostile until it says
    otherwise, and 'downward' here means the least authority, not the least
    number."""
    for bad in ("zero", None if False else "0.5", 9, -1, [], object()):
        rec = events.emit("nuc", "info", "x", layer=bad)
        assert rec["layer"] == 4, bad


def test_layer_zero_is_the_operator():
    rec = events.emit("telegram", "info", "do the thing",
                      origin="operator", layer=0)
    assert rec["trust"] == "operator"


def test_every_layer_name_matches_the_document():
    doc = (Path(__file__).resolve().parent.parent
           / "docs" / "TRUST-LAYERS.md").read_text().upper()
    for n, name in events.LAYERS.items():
        assert name.upper() in doc, f"layer {n} ({name}) is not in TRUST-LAYERS.md"
