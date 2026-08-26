#!/usr/bin/env python3
"""Which company is behind each agent, and why the fleet needs to know.

This fleet has been cross-vendor by accident for weeks and nothing recorded it.
The table below is what each agent is DECLARED to be. It is not trusted on its
own, because it was already wrong: on 2026-08-26 the NUC's `hermes` was a
llama3.2:3b served from http://127.0.0.1:11434/v1, while every board, every
council transcript and every independence check called it OpenAI gpt-5.5. It
had been that way for weeks. Six hundred rota turns were filed under a company
that was not involved.

The docstring here used to say "Verified from ~/.hermes/config.yaml... not
assumed", and that sentence was the defect: verified once, on one machine, then
frozen into a constant. A fact about a config file is only true on the machine
that has that config file, at the moment it is read.

So the vendor is now OBSERVED at call time where the agent's backend is
configurable, and the declared value is the fallback for agents whose CLI can
only talk to one company. Where the two disagree, `mismatches()` says so.

Recording it turns an accident into evidence, in two directions:

**Agreement is worth more across vendors.** On 2026-08-02 claude and hermes
independently diagnosed the same relay bug — the timeout value landing in the
reply slot — from the same board with no coordination. Two companies, two
training runs, two failure profiles, one conclusion. That is far stronger than
one model saying it twice, and the log recorded it as two paragraphs by two
names, with nothing marking why that mattered.

**Review is only independent if the reviewer is.** An agent checking its own
work is the same machinery that produced the error. The brain-farts log is
fourteen entries and every one was caught by a human, precisely because nothing
here was ever set up to have one model audit another's.

So: prefer a reviewer from a different vendor, and when none is available say so
rather than letting `agent` imply an independence that was not there.
"""

from __future__ import annotations

import json
from pathlib import Path

VENDORS: dict[str, str] = {
    "claude": "anthropic",
    "grok": "xai",
    "agy": "google",
    "hermes": "openai",
    "openclaw": "openai",
    "ollama": "local",
}

MODELS: dict[str, str] = {
    "claude": "claude-opus-5",
    "grok": "grok-4",
    "agy": "gemini",
    "hermes": "gpt-5.5",
    "openclaw": "gpt-5.5",
    "ollama": "llama3.2:1b",
}


# ---------------------------------------------------------------- observation

# Agents whose backend is a config file rather than a fixed CLI. These are the
# ones that can silently become something else; `claude`, `grok` and `agy` ship
# talking to exactly one company, and `ollama` is local by definition.
CONFIGURABLE = ("hermes", "openclaw")

_LOOPBACK = ("127.0.0.1", "localhost", "0.0.0.0", "::1")


def _hermes_backend() -> tuple[str, str] | None:
    """(vendor, model) read from hermes' own config, or None if unreadable.

    Order matters: an explicit custom base_url beats the OAuth provider,
    because a config pointing at loopback is what the process actually calls
    no matter which tokens are on disk.
    """
    home = Path.home()
    cfg = home / ".hermes" / "config.yaml"
    if cfg.exists():
        try:
            import yaml
            data = yaml.safe_load(cfg.read_text()) or {}
        except Exception:
            data = {}
        m = (data.get("model") or {}) if isinstance(data, dict) else {}
        base = str(m.get("base_url") or "")
        if base and any(h in base for h in _LOOPBACK):
            return "local", str(m.get("model") or "local model")
        prov = str(m.get("provider") or "")
        if "openai" in prov or "codex" in prov:
            return "openai", str(m.get("model") or MODELS.get("hermes", "unknown"))
        if "anthropic" in prov or "claude" in prov:
            return "anthropic", str(m.get("model") or "claude")
    auth = home / ".hermes" / "auth.json"
    if auth.exists():
        try:
            active = str((json.loads(auth.read_text()) or {}).get("active_provider") or "")
        except Exception:
            active = ""
        if "openai" in active or "codex" in active:
            return "openai", MODELS.get("hermes", "unknown")
        if "anthropic" in active:
            return "anthropic", "claude"
    return None


def _openclaw_backend() -> tuple[str, str] | None:
    """openclaw names its model as "<vendor>/<model>" under agents.defaults.

    Read that key and nothing else. The first version of this scanned the
    whole file for vendor names and reported "anthropic" -- correct, but by
    accident: the file mentions anthropic eight times and openai five, and a
    count of mentions is not a fact about what runs. A probe that can be
    right for the wrong reason will be wrong for the same reason later.
    """
    cfg = Path.home() / ".openclaw" / "openclaw.json"
    if not cfg.exists():
        return None
    try:
        data = json.loads(cfg.read_text()) or {}
    except Exception:
        return None
    primary = (((data.get("agents") or {}).get("defaults") or {})
               .get("model") or {}).get("primary")
    if not isinstance(primary, str) or "/" not in primary:
        return None
    vendor_name, _, model_name = primary.partition("/")
    vendor_name = vendor_name.split("-")[0].lower()   # "openai-codex" -> "openai"
    return vendor_name, model_name


PROBES = {"hermes": _hermes_backend, "openclaw": _openclaw_backend}


def observed(agent: str) -> tuple[str, str] | None:
    """What this machine's config says the agent actually talks to."""
    probe = PROBES.get(agent)
    if probe is None:
        return None
    try:
        return probe()
    except Exception:
        # Never let a malformed config take down a board. An unreadable
        # config is "unknown", which falls back to declared and shows up in
        # mismatches() as nothing rather than as a false accusation.
        return None


def mismatches() -> list[dict]:
    """Every agent whose declared vendor is not what this machine observes.

    This is the check that would have caught the NUC in an hour instead of
    weeks. It is deliberately quiet about agents it cannot observe: silence
    here means "not configurable", never "verified".
    """
    out = []
    for agent in CONFIGURABLE:
        seen = observed(agent)
        if seen is None:
            continue
        if seen[0] != VENDORS.get(agent):
            out.append({"agent": agent, "declared": VENDORS.get(agent),
                        "observed": seen[0], "model": seen[1]})
    return out


def vendor(agent: str) -> str:
    """Observed where observable, declared otherwise. Independence checks call
    this, so an agent that has quietly become something else stops counting as
    a second company the moment its config changes."""
    seen = observed(agent)
    return seen[0] if seen else VENDORS.get(agent, "unknown")


def model(agent: str) -> str:
    seen = observed(agent)
    return seen[1] if seen else MODELS.get(agent, "unknown")


def independent_of(agent: str, candidates: list[str]) -> list[str]:
    """Candidates from a different vendor, best first.

    A same-vendor reviewer is not worthless — a second run catches slips — but it
    is a weaker claim, so it sorts last and the caller has to notice.
    """
    v = vendor(agent)
    other = [c for c in candidates if c != agent and vendor(c) != v]
    same = [c for c in candidates if c != agent and vendor(c) == v]
    return other + same


def describe(agent: str) -> str:
    return f"{agent} ({model(agent)}, {vendor(agent)})"


if __name__ == "__main__":
    for a in VENDORS:
        print(f"  {describe(a)}")
    print()
    for a in ("claude", "hermes", "grok"):
        pool = ["claude", "hermes", "grok"]
        picks = independent_of(a, pool)
        best = picks[0] if picks else None
        note = "" if best and vendor(best) != vendor(a) else "  (same vendor — weaker)"
        print(f"  reviewer for {a}: {best}{note}")
