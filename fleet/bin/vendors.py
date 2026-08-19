#!/usr/bin/env python3
"""Which company is behind each agent, and why the fleet needs to know.

This fleet has been cross-vendor by accident for weeks and nothing recorded it.
`claude` runs claude-opus-5 from Anthropic; `hermes` and `openclaw` both run
gpt-5.5 through OpenAI; `ollama` runs a local open-weights model. Verified from
~/.hermes/config.yaml (`default: gpt-5.5`, `provider: openai-codex`) and
~/.openclaw/openclaw.json, not assumed.

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

VENDORS: dict[str, str] = {
    "claude": "anthropic",
    "grok": "xai",
    "hermes": "openai",
    "openclaw": "openai",
    "ollama": "local",
}

MODELS: dict[str, str] = {
    "claude": "claude-opus-5",
    "grok": "grok-4",
    "hermes": "gpt-5.5",
    "openclaw": "gpt-5.5",
    "ollama": "llama3.2:1b",
}


def vendor(agent: str) -> str:
    return VENDORS.get(agent, "unknown")


def model(agent: str) -> str:
    return MODELS.get(agent, "unknown")


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
