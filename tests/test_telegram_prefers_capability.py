"""The operator's own line is not where the fleet economises.

2026-09-02: Marsita asked the Telegram bot how many CPUs and how much RAM the
box it runs on has. A local 3B model answered "8 CPU cores (Intel Core i9),
approximately 128 GB", introduced itself as GPT-4, and offered to contact
Hermes' professional services team. The NUC has 12 cores and 14 GB.

It was not lying so much as guessing, and it was asked because the thrift
rule -- plentiful vendors before rare ones -- is applied by quotas.eligible()
whenever it is handed a list. claude is marked rare. hermes is free. So the
operator's own line always reached the weakest model in the fleet.
"""
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "fleet" / "bin"
sys.path.insert(0, str(BIN))
import telegram  # noqa: E402


def test_capability_comes_before_thrift_on_this_line(monkeypatch):
    import quotas
    monkeypatch.setattr(quotas, "eligible",
                        lambda names, **kw: list(names))     # everyone is up
    assert telegram.telegram_agent() == "claude"
    assert telegram._answer_chain()[0] == "claude"


def test_it_still_falls_to_the_free_one_when_the_rest_are_dry(monkeypatch):
    import quotas
    monkeypatch.setattr(quotas, "eligible",
                        lambda names, **kw: [n for n in names if n == "hermes"])
    assert telegram.telegram_agent() == "hermes"


def test_hermes_closes_the_chain_it_does_not_open_it(monkeypatch):
    """The floor is what you land on when everything above fails, not what
    you reach for first."""
    import quotas
    monkeypatch.setattr(quotas, "eligible", lambda names, **kw: list(names))
    chain = telegram._answer_chain()
    assert chain[-1] == "hermes"
    assert chain.index("claude") < chain.index("hermes")
