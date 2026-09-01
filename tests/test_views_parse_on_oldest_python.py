"""The board must parse on the oldest Python in the fleet.

Gaia runs 3.11 and the NUC runs 3.14. A triple-quoted string inside an
f-string is legal from 3.12 (PEP 701) and a SyntaxError before it, so a page
change written on the NUC parsed there and broke on the laptop -- the one
machine the terminal pane exists for. Views are the risk: they are one long
f-string each.
"""
import ast
import re
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "fleet" / "bin"
VIEWS = sorted(BIN.glob("*view*.py")) + [BIN / "nav.py"]

# f"..." opened with one quote style, containing the same style tripled.
NESTED = re.compile(r'f"""(?:(?!""")[\s\S])*?"""[^"\n]*?"""', re.S)


def test_every_view_parses():
    for f in VIEWS:
        if not f.exists():
            continue
        try:
            ast.parse(f.read_text())
        except SyntaxError as e:            # pragma: no cover - the failure IS the point
            raise AssertionError(f"{f.name} does not parse: {e}") from e


def test_no_triple_quoted_string_inside_an_f_string():
    for f in VIEWS:
        if not f.exists():
            continue
        src = f.read_text()
        for m in re.finditer(r'\{[^{}\n]*"""', src):
            line = src[:m.start()].count("\n") + 1
            raise AssertionError(
                f"{f.name}:{line} puts a triple-quoted string inside an "
                f"f-string placeholder; that is 3.12+ only. Hoist it into a "
                f"variable above the return.")
