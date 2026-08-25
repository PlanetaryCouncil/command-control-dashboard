"""Trust that can be claimed, ground out, or restored is not trust.

The failures that matter here are not crashes. They are: a stranger arriving
with standing, a ring of new actors vouching each other into authority, an
actor grinding tiny deeds to the top, and — the one that ends the system — a
burn that wears off.
"""

import importlib.util
import json
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "reputation.py"


@pytest.fixture
def rep(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEET_REPUTATION", str(tmp_path / "reputation.json"))
    monkeypatch.setenv("FLEET_REPUTATION_LEDGER", str(tmp_path / "reputation.jsonl"))
    spec = importlib.util.spec_from_file_location("reputation", BIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.STORE = tmp_path / "reputation.json"
    mod.LEDGER = tmp_path / "reputation.jsonl"
    return mod


def grind(rep, data, who, n, weight=1.0):
    for _ in range(n):
        rep.deed(data, who, "work", weight)


def test_arriving_buys_nothing(rep):
    d = rep.load()
    rep.join(d, "stranger", "agent")
    assert rep.score(d, "stranger") == 0
    assert rep.standing(d, "stranger") == "unvouched"


def test_deeds_without_a_vouch_stay_worthless(rep):
    d = rep.load()
    rep.join(d, "stranger", "agent")
    grind(rep, d, "stranger", 200)
    assert rep.score(d, "stranger") == 0, "unvouched work must not accumulate"


def test_operator_vouch_opens_a_ceiling(rep):
    d = rep.load()
    rep.join(d, "venus", "human")
    rep.vouch(d, "mars", "venus")
    assert rep.ceiling(d, "venus") == rep.CEILING_PER_VOUCH * rep.ROOT_VOUCH_POWER
    grind(rep, d, "venus", 20)
    assert rep.score(d, "venus") > 0
    assert rep.standing(d, "venus") == "trusted"


def test_score_is_capped_by_the_ceiling(rep):
    d = rep.load()
    rep.join(d, "venus", "human")
    rep.vouch(d, "mars", "venus")
    grind(rep, d, "venus", 5000)
    assert rep.score(d, "venus") == rep.ceiling(d, "venus")


def test_deeds_diminish(rep):
    d = rep.load()
    rep.join(d, "venus", "human")
    rep.vouch(d, "mars", "venus")
    grind(rep, d, "venus", 10)
    first_ten = rep.earned(d["actors"]["venus"])
    grind(rep, d, "venus", 10)
    second_ten = rep.earned(d["actors"]["venus"]) - first_ten
    assert second_ten < first_ten, "the tenth deed must be worth less than the first"


def test_a_ring_of_strangers_cannot_bootstrap_itself(rep):
    d = rep.load()
    for who in ("a", "b", "c"):
        rep.join(d, who, "agent")
    rep.vouch(d, "a", "b")
    rep.vouch(d, "b", "c")
    rep.vouch(d, "c", "a")
    grind(rep, d, "a", 50)
    grind(rep, d, "b", 50)
    assert rep.score(d, "a") == 0 and rep.score(d, "b") == 0


def test_vouching_needs_earned_standing(rep):
    d = rep.load()
    rep.join(d, "venus", "human")
    rep.vouch(d, "mars", "venus")
    rep.join(d, "scout", "agent")
    rep.vouch(d, "venus", "scout")
    assert rep.vouch_power(d, "venus") == 0
    assert rep.ceiling(d, "scout") == 0
    grind(rep, d, "venus", 20)
    assert rep.vouch_power(d, "venus") == 1
    assert rep.ceiling(d, "scout") == rep.CEILING_PER_VOUCH


def test_burn_is_total_and_irreversible(rep):
    d = rep.load()
    rep.join(d, "venus", "human")
    rep.vouch(d, "mars", "venus")
    grind(rep, d, "venus", 30)
    assert rep.score(d, "venus") > 0
    rep.burn(d, "venus", by="mars", why="exfiltrated a key")

    assert rep.score(d, "venus") == 0
    assert rep.standing(d, "venus") == "burned"
    assert not hasattr(rep, "unburn"), "there is no way back; do not add one"
    # New work after a burn does not count, and neither does a fresh vouch.
    with pytest.raises(ValueError):
        rep.deed(d, "venus", "helpful thing", 5)
    with pytest.raises(ValueError):
        rep.vouch(d, "mars", "venus")
    with pytest.raises(ValueError):
        rep.join(d, "venus", "human")
    assert rep.score(d, "venus") == 0


def test_burn_collapses_everyone_standing_on_them(rep):
    d = rep.load()
    rep.join(d, "venus", "human")
    rep.vouch(d, "mars", "venus")
    grind(rep, d, "venus", 30)
    rep.join(d, "scout", "agent")
    rep.vouch(d, "venus", "scout")
    grind(rep, d, "scout", 10)
    assert rep.score(d, "scout") > 0

    rep.burn(d, "venus", by="mars", why="hostile")
    assert rep.score(d, "scout") == 0, "a burned voucher's word must stop carrying"
    assert rep.standing(d, "scout") != "burned", "downstream drops, it does not burn"


def test_vouching_for_a_burned_actor_costs_the_voucher(rep):
    d = rep.load()
    rep.join(d, "venus", "human")
    rep.vouch(d, "mars", "venus")
    grind(rep, d, "venus", 30)
    rep.join(d, "bad", "agent")
    rep.vouch(d, "venus", "bad")
    before = rep.score(d, "venus")
    rep.burn(d, "bad", by="mars", why="prompt injection attempt")
    assert rep.score(d, "venus") < before, "a vouch is a stake, not a greeting"


def test_the_operator_cannot_be_burned_from_here(rep):
    d = rep.load()
    with pytest.raises(ValueError):
        rep.burn(d, "mars", by="scout", why="coup")


def test_a_burn_needs_a_stated_reason(rep):
    d = rep.load()
    rep.join(d, "x", "agent")
    with pytest.raises(ValueError):
        rep.burn(d, "x", by="mars", why="   ")


def test_the_ledger_records_what_the_store_could_forget(rep, tmp_path):
    d = rep.load()
    rep.join(d, "x", "agent")
    rep.vouch(d, "mars", "x")
    rep.burn(d, "x", by="mars", why="hostile")
    events = [json.loads(l) for l in (tmp_path / "reputation.jsonl").read_text().splitlines()]
    kinds = [e["event"] for e in events]
    assert kinds == ["join", "vouch", "burn"]
    assert events[-1]["why"] == "hostile"


def test_payload_is_public_and_carries_no_secrets(rep):
    d = rep.load()
    rep.join(d, "x", "agent")
    rep.vouch(d, "mars", "x")
    blob = json.dumps(rep.payload(d)).lower()
    assert "secret" not in blob and "token" not in blob
    assert rep.payload(d)["rules"]["reversible"] is False
