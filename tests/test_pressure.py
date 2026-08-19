"""The machine yields when it is swapping, not only when load is high."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fleet" / "bin"))
import pressure  # noqa: E402

VM = """\
Pages free:                               3690.
Pages active:                           505244.
Pages occupied by compressor:           577512.
"""


def test_compressor_gb_from_vm_stat():
    gb = pressure.compressor_gb(VM)
    assert 2.0 < gb < 2.5


def test_hot_when_compressor_is_heavy(monkeypatch):
    monkeypatch.setattr(pressure, "load1", lambda: 1.0)
    monkeypatch.setattr(pressure, "ncpu", lambda: 4)
    monkeypatch.setattr(pressure, "max_load", lambda: 4.0)
    snap = pressure.snapshot(VM)
    assert snap["hot"] is True
    assert "compressor" in snap["reason"]


def test_hot_when_load_exceeds_cores(monkeypatch):
    monkeypatch.setattr(pressure, "load1", lambda: 9.0)
    monkeypatch.setattr(pressure, "ncpu", lambda: 4)
    monkeypatch.setattr(pressure, "max_load", lambda: 4.0)
    monkeypatch.setattr(pressure, "compressor_gb", lambda text=None: 0.2)
    snap = pressure.snapshot()
    assert snap["hot"] is True
    assert "load 9.0" in snap["reason"]


def test_cool_when_load_and_ram_are_quiet(monkeypatch):
    monkeypatch.setattr(pressure, "load1", lambda: 1.2)
    monkeypatch.setattr(pressure, "ncpu", lambda: 4)
    monkeypatch.setattr(pressure, "max_load", lambda: 4.0)
    monkeypatch.setattr(pressure, "compressor_gb", lambda text=None: 0.3)
    assert pressure.too_hot() is False
    assert pressure.snapshot()["reason"] == "ok"
