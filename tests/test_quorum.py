"""One vendor is not a fleet. It is a model with a cron job.

Every integrity claim here rests on more than one company being in the room.
The council refuses to sit with fewer than two participants. The pipeline's
whole promise is that the agent reviewing a diff works for a different vendor
than the one who wrote it. Lose that and the machinery keeps running, keeps
logging, keeps looking busy -- and has stopped doing the only thing that made
its output worth anything.

That is exactly what happened. For three weeks the NUC ran forty rota turns
out of forty on one vendor while the council logged "needs at least two
participants, got 1" every three hours, and nobody was told, because the
other agents were not DOWN. They were held. These tests pin the distinction.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))

_spec = importlib.util.spec_from_file_location(
    "quotas", ROOT / "fleet" / "bin" / "quotas.py")
quotas = importlib.util.module_from_spec(_spec)
sys.modules["quotas"] = quotas
_spec.loader.exec_module(quotas)


def _rows(**states):
    """A pulse row per agent. `ok` and `spend` are the two fields the
    eligibility walk actually reads."""
    out = {}
    for agent, (ok, spend) in states.items():
        out[agent] = {"agent": agent, "ok": ok, "spend": spend,
                      "vendor": quotas.vendors.vendor(agent)}
    return out


def _cfg(**spend):
    """eligible() reads rarity from the CONFIG, not from the pulse row --
    the row's `spend` field is a copy for display. A test that set it only
    on the row proved nothing, because eligible() never looks there."""
    return {"quotas": {"spend": spend}}


def _spending(scheduled, rows, cfg=None):
    return quotas.eligible(scheduled, cfg=cfg or {}, rows=rows)


def test_two_agents_from_one_company_are_not_a_quorum():
    """hermes and openclaw are both OpenAI. Counting healthy AGENTS says two
    and everything looks fine; counting VENDORS says one and the pipeline
    cannot review across vendors. The second count is the true one."""
    rows = _rows(hermes=(True, "plenty"), openclaw=(True, "plenty"))
    spending = _spending(["hermes", "openclaw"], rows)
    assert len(spending) == 2, "both agents are healthy"
    vendors_in_room = {quotas.vendors.vendor(a) for a in spending}
    assert vendors_in_room == {"openai"}
    assert len(vendors_in_room) < 2, "two agents, one company, no quorum"


def test_held_is_not_down_and_that_is_the_whole_bug():
    """A `rare` agent reports ok=True. It is healthy and it is never picked,
    because eligible() prefers plentiful vendors whenever one exists. Any
    check that watches for unhealthy agents sees nothing wrong here."""
    rows = _rows(hermes=(True, "plenty"), grok=(True, "rare"),
                 agy=(True, "rare"))
    cfg = _cfg(grok="rare", agy="rare")
    assert all(r["ok"] for r in rows.values()), "nobody is down"
    spending = _spending(["hermes", "grok", "agy"], rows, cfg)
    assert spending == ["hermes"], "and yet only one agent can spend a turn"


def test_a_lone_rare_vendor_still_gets_to_work():
    """`plenty or live` -- when nothing plentiful is up, the rare ones run
    rather than the fleet going silent. Being careful with a tight plan must
    not become refusing to work at all."""
    rows = _rows(grok=(True, "rare"), agy=(True, "rare"))
    cfg = _cfg(grok="rare", agy="rare")
    assert _spending(["grok", "agy"], rows, cfg) == ["grok", "agy"]


def test_quorum_needs_two_distinct_vendors():
    rows = _rows(hermes=(True, "plenty"), grok=(True, "plenty"))
    spending = _spending(["hermes", "grok"], rows)
    assert len({quotas.vendors.vendor(a) for a in spending}) >= 2
