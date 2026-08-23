"""A turn that narrates the prompt back is unusable, not proposed.

On 2026-08-07 three of the six entries in `already_proposed` were the model
describing the prompt — "the message seems to be an invitation for discussion",
"here is the reformatted text from what appears to be a Discord proposal". They
exit clean, so the errored-turn check misses them, and each one took a board
slot a human and the next agent had to read past. They are now filed
`unusable` and kept off the board.
"""

import importlib.util
import json
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rota = _load("rota")


def test_the_three_observed_narrations_are_caught():
    for text in [
        "The message seems to be an invitation for discussion and "
        "proposal-making about the fleet.",
        "Here is the reformatted text from what appears to be a Discord "
        "proposal or discussion log",
        "The format you requested is typically used for programming code or "
        "API documentation, but the text you provided appears to be a log",
        "I'll answer the three questions based on the provided text. 1. What "
        "would most improve this machine",
    ]:
        assert rota.narrated(text), text


def test_stderr_quota_dump_is_a_harness_failure():
    assert rota.harness_failed(
        "[stderr] Error: Individual quota reached. Please upgrade")
    assert rota.harness_failed("[error] boom")
    assert rota.harness_failed("[timed out after 180s; no output]")
    assert not rota.harness_failed(
        "Write static/basex/index.html as a one-page explainer")


def test_a_real_proposal_is_not_narration():
    real = (
        "Stagger heavyweight runs when the fleet is active. The sweep and the "
        "rota both fire on the hour and the machine hits load 15."
    )
    assert not rota.narrated(real)


def test_quoting_the_board_further_down_is_still_a_proposal():
    """Only the opening is examined — a real proposal may quote the board."""
    out = (
        "Stagger heavyweight runs when the fleet is active.\n\n" + "x " * 200 +
        "\nFor context, the text you provided appears to be a log of that."
    )
    assert not rota.narrated(out)


def test_the_board_skips_unusable_turns(tmp_path, monkeypatch):
    council = _load("council")
    rota_dir = tmp_path / "rota"
    rota_dir.mkdir()
    rows = [
        {"ts": "2026-08-07T14:18:00Z", "agent": "hermes", "outcome": "unusable",
         "text": "The message seems to be an invitation for discussion"},
        {"ts": "2026-08-07T14:40:00Z", "agent": "claude", "outcome": "proposed",
         "text": "Stagger heavyweight runs when the fleet is active."},
    ]
    (rota_dir / "proposals.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(council, "FLEET", tmp_path)

    gists = [r["gist"] for r in council.already_asked()]
    assert gists == ["Stagger heavyweight runs when the fleet is active."]
    assert [r["by"] for r in council.proposal_ledger()] == ["claude"]
