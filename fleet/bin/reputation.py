#!/usr/bin/env python3
"""Who is trusted here, how they got there, and how it ends.

`docs/TRUST-LAYERS.md` says who may instruct this machine. It has one hole,
named at the bottom of its own page: *"Layer 1 has no authentication mechanism
for humans... today a friend is someone Mars vouches for in the moment, which
does not survive Mars being asleep."*

This is the thing that survives Mars being asleep.

Three rules, and everything else follows:

**1. Trust is vouched, never claimed.** An arriving agent has a score of zero
and nobody's word behind it. Someone already trusted has to put their own name
on it. Vouching costs the voucher nothing up front and everything if they are
wrong, which is the only arrangement under which a vouch means anything.

**2. Trust is earned slowly.** A vouch buys a *ceiling*, not a score. The score
underneath it comes from behaving — work landed, reviews given, handoffs
written — and each deed is worth slightly less than the one before it, so a
long honest record beats a burst of activity. You cannot grind your way to the
top in an afternoon.

**3. Trust ends at once, and it does not come back.** One hostile act burns the
actor: score zero, permanently, every vouch they issued dead with them, and a
mark on everyone who vouched for them. There is no appeal call in this module
and there will not be one. Burning is the only irreversible operation in the
system, on purpose — a reputation you can restore by asking is a reputation an
attacker can restore by asking.

Authority still flows down and never up: `vouch_power` is zero unless you have
earned real standing, so a fresh actor cannot bootstrap a friend, and a burned
one cannot bootstrap anyone.

    python3 fleet/bin/reputation.py                  # the standings
    python3 fleet/bin/reputation.py join <id> --kind agent
    python3 fleet/bin/reputation.py vouch <from> <to> --why "..."
    python3 fleet/bin/reputation.py deed <id> --what "review" --weight 2
    python3 fleet/bin/reputation.py burn <id> --by mars --why "..."
    python3 fleet/bin/reputation.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
STORE = Path(os.environ.get("FLEET_REPUTATION", FLEET / "data" / "reputation.json"))
LEDGER = Path(os.environ.get("FLEET_REPUTATION_LEDGER",
                             FLEET / "data" / "reputation.jsonl"))

# The operator is the root of trust and is not scored — the same way the
# TRUST-LAYERS document does not rank layer 0. Everything else descends from
# here, so this list is the one place trust can enter the system.
ROOT = ("mars",)

CEILING_PER_VOUCH = 20      # what one live voucher's word is worth
VOUCH_THRESHOLD = 10        # score needed before your vouch carries weight
ROOT_VOUCH_POWER = 3        # the operator's word is worth three friends'
BURN_STAKE = 8              # what vouching for a burned actor costs you

KINDS = ("human", "agent", "machine")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path | None = None) -> dict:
    p = Path(path or STORE)
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        data = {}
    data.setdefault("actors", {})
    data.setdefault("vouches", [])
    for name in ROOT:
        data["actors"].setdefault(name, {
            "id": name, "kind": "human", "root": True,
            "joined": _now(), "deeds": [], "burned": None,
        })
    return data


def save(data: dict, path: Path | None = None) -> None:
    p = Path(path or STORE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _log(_event: str, **fields) -> None:
    """Append-only. The store can be hand-edited; this cannot be un-written,
    which is what makes a burn survive somebody's second thoughts."""
    p = Path(LEDGER)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps({"at": _now(), "event": _event, **fields}) + "\n")


# ---------------------------------------------------------------- scoring

def earned(actor: dict) -> float:
    """Deeds with diminishing returns: the nth deed is worth w/(1+n/10).

    Sub-linear on purpose. Ten small deeds should not equal one that mattered,
    and a thousand tiny ones should not equal anything at all — otherwise the
    cheapest path to trust is a loop that writes handoffs to itself."""
    total = 0.0
    for n, deed in enumerate(actor.get("deeds", [])):
        try:
            weight = float(deed.get("weight", 1))
        except (TypeError, ValueError):
            weight = 1.0
        total += weight / (1 + n / 10)
    return total


def is_burned(actor: dict) -> bool:
    return bool(actor.get("burned"))


def vouch_power(data: dict, actor_id: str, _seen: frozenset = frozenset()) -> int:
    """How much this actor's vouch is worth. Zero is the normal answer.

    `_seen` closes the obvious attack: three strangers vouching in a circle.
    Re-entering an actor already on the path returns zero, so a cycle creates
    no standing at all — trust has to come from outside the ring or it does
    not exist."""
    actor = data["actors"].get(actor_id)
    if not actor or is_burned(actor) or actor_id in _seen:
        return 0
    if actor.get("root"):
        return ROOT_VOUCH_POWER
    return 1 if score(data, actor_id, _seen | {actor_id}) >= VOUCH_THRESHOLD else 0


def vouchers(data: dict, actor_id: str) -> list[str]:
    return [v["from"] for v in data.get("vouches", []) if v.get("to") == actor_id]


def ceiling(data: dict, actor_id: str, _seen: frozenset = frozenset()) -> int:
    """Vouches buy headroom, not standing. Nobody vouching for you means you
    can work here and earn nothing by it — which is the correct treatment of a
    stranger, not a punishment."""
    actor = data["actors"].get(actor_id, {})
    if actor.get("root"):
        return 100
    return CEILING_PER_VOUCH * sum(vouch_power(data, v, _seen | {actor_id})
                                   for v in vouchers(data, actor_id))


def score(data: dict, actor_id: str, _seen: frozenset = frozenset()) -> int:
    actor = data["actors"].get(actor_id)
    if not actor:
        return 0
    if is_burned(actor):
        return 0                      # not "reduced". Zero, and it stays zero.
    if actor.get("root"):
        return 100
    return int(min(earned(actor), ceiling(data, actor_id, _seen)))


def standing(data: dict, actor_id: str) -> str:
    actor = data["actors"].get(actor_id)
    if not actor:
        return "unknown"
    if is_burned(actor):
        return "burned"
    if actor.get("root"):
        return "operator"
    if not vouch_power_sum(data, actor_id):
        return "unvouched"
    s = score(data, actor_id)
    if s >= VOUCH_THRESHOLD:
        return "trusted"
    return "vouched"


def vouch_power_sum(data: dict, actor_id: str) -> int:
    return sum(vouch_power(data, v) for v in vouchers(data, actor_id))


# ---------------------------------------------------------------- mutations

def join(data: dict, actor_id: str, kind: str = "agent", note: str = "") -> dict:
    """Anyone may join. Joining buys nothing — that is the point of it being
    open. A burned id can never be re-registered; the name is spent."""
    actor_id = actor_id.strip().lower()
    if not actor_id:
        raise ValueError("actor id required")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    existing = data["actors"].get(actor_id)
    if existing:
        if is_burned(existing):
            raise ValueError(f"{actor_id} is burned; the name does not return")
        return existing
    actor = {"id": actor_id, "kind": kind, "joined": _now(),
             "note": note, "deeds": [], "burned": None}
    data["actors"][actor_id] = actor
    _log("join", actor=actor_id, kind=kind, note=note)
    return actor


def vouch(data: dict, from_id: str, to_id: str, why: str = "") -> dict:
    """Put your name on someone. Costs nothing today, costs BURN_STAKE if they
    turn out to be hostile — so a vouch is a bet, not a greeting."""
    if from_id not in data["actors"]:
        raise ValueError(f"unknown voucher {from_id}")
    if to_id not in data["actors"]:
        raise ValueError(f"unknown actor {to_id}")
    if from_id == to_id:
        raise ValueError("cannot vouch for yourself")
    if is_burned(data["actors"][from_id]):
        raise ValueError(f"{from_id} is burned and vouches for nobody")
    if is_burned(data["actors"][to_id]):
        raise ValueError(f"{to_id} is burned and cannot be vouched for")
    for v in data["vouches"]:
        if v.get("from") == from_id and v.get("to") == to_id:
            return v
    rec = {"from": from_id, "to": to_id, "why": why, "at": _now()}
    data["vouches"].append(rec)
    _log("vouch", **rec)
    return rec


def deed(data: dict, actor_id: str, what: str, weight: float = 1.0,
         by: str = "") -> dict:
    """Record behaviour. Weight is small on purpose: 1 for ordinary work, 2-3
    for something that took judgement. Nothing here is worth 20."""
    actor = data["actors"].get(actor_id)
    if not actor:
        raise ValueError(f"unknown actor {actor_id}")
    if is_burned(actor):
        raise ValueError(f"{actor_id} is burned; deeds no longer count")
    rec = {"what": what, "weight": float(weight), "at": _now(), "by": by}
    actor.setdefault("deeds", []).append(rec)
    _log("deed", actor=actor_id, **rec)
    return rec


def burn(data: dict, actor_id: str, by: str, why: str) -> dict:
    """The irreversible one.

    Everything the actor earned goes to zero and stays there. Every vouch they
    issued stops carrying weight, so anyone standing on their word drops to
    whatever their remaining vouchers hold them at. Everyone who vouched *for*
    them takes a permanent negative deed — they staked their name and the stake
    is collected.

    There is no `unburn`. Do not add one. If a burn was a mistake, the honest
    repair is a new identity with new vouches, which is exactly as expensive as
    starting over should be.
    """
    actor = data["actors"].get(actor_id)
    if not actor:
        raise ValueError(f"unknown actor {actor_id}")
    if actor.get("root"):
        raise ValueError("the operator is the root of trust and cannot be burned here")
    if is_burned(actor):
        return actor["burned"]
    if not why.strip():
        raise ValueError("a burn needs a stated reason; it is on the record forever")

    mark = {"at": _now(), "by": by, "why": why}
    actor["burned"] = mark
    actor["deeds"] = []          # not deleted history — the ledger keeps it.

    staked = vouchers(data, actor_id)
    for v in staked:
        voucher = data["actors"].get(v)
        if not voucher or voucher.get("root") or is_burned(voucher):
            continue
        voucher.setdefault("deeds", []).append(
            {"what": f"vouched for {actor_id}, who was burned",
             "weight": -float(BURN_STAKE), "at": _now(), "by": by})

    _log("burn", actor=actor_id, by=by, why=why, stake_paid_by=staked)
    return mark


# ---------------------------------------------------------------- views

def payload(data: dict | None = None) -> dict:
    data = data or load()
    actors = []
    for actor_id in sorted(data["actors"]):
        actor = data["actors"][actor_id]
        actors.append({
            "id": actor_id,
            "kind": actor.get("kind", "agent"),
            "standing": standing(data, actor_id),
            "score": score(data, actor_id),
            "ceiling": ceiling(data, actor_id),
            "deeds": len(actor.get("deeds", [])),
            "vouched_by": vouchers(data, actor_id),
            "joined": actor.get("joined"),
            "burned": actor.get("burned"),
        })
    actors.sort(key=lambda a: (a["standing"] == "burned", -a["score"], a["id"]))
    return {
        "rules": {
            "ceiling_per_vouch": CEILING_PER_VOUCH,
            "vouch_threshold": VOUCH_THRESHOLD,
            "burn_stake": BURN_STAKE,
            "reversible": False,
        },
        "actors": actors,
        "vouches": data.get("vouches", []),
    }


def table(data: dict | None = None) -> str:
    p = payload(data)
    rows = ["  score  standing    kind     who              vouched by",
            "  -----  ----------  -------  ---------------  ----------"]
    for a in p["actors"]:
        rows.append(f"  {a['score']:>5}  {a['standing']:<10}  {a['kind']:<7}  "
                    f"{a['id']:<15}  {', '.join(a['vouched_by']) or '-'}")
    return "\n".join(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("join"); p.add_argument("id")
    p.add_argument("--kind", default="agent", choices=KINDS)
    p.add_argument("--note", default="")

    p = sub.add_parser("vouch"); p.add_argument("from_id"); p.add_argument("to_id")
    p.add_argument("--why", default="")

    p = sub.add_parser("deed"); p.add_argument("id")
    p.add_argument("--what", required=True); p.add_argument("--weight", type=float, default=1.0)
    p.add_argument("--by", default="")

    p = sub.add_parser("burn"); p.add_argument("id")
    p.add_argument("--by", default="mars"); p.add_argument("--why", required=True)

    args = ap.parse_args(argv)
    data = load()
    try:
        if args.cmd == "join":
            join(data, args.id, args.kind, args.note)
        elif args.cmd == "vouch":
            vouch(data, args.from_id, args.to_id, args.why)
        elif args.cmd == "deed":
            deed(data, args.id, args.what, args.weight, args.by)
        elif args.cmd == "burn":
            burn(data, args.id, args.by, args.why)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    if args.cmd:
        save(data)
    print(json.dumps(payload(data), indent=2) if args.json else table(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
