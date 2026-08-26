#!/usr/bin/env python3
"""Which modules are wired into something that runs, and which are asleep.

Coverage said 44% and named 25 files with zero lines executed. That number
alone cannot be acted on, because it treats two very different things the
same way: a module that fires unattended at 04:00 and has no test, and a
module nothing has invoked since the day it was written. The first is a
risk. The second is a drawer.

So this asks a narrower question with a checkable answer: is there a path
from something that RUNS to this file? Runners are the things this machine
actually starts -- launchd plists, systemd units, shell scripts, the
watchdog list, cron -- plus any module imported by a module a runner
reaches. Everything the walk cannot get to is dormant.

Dormant is not an insult and not a deletion order. It is permission to
leave a file alone. The output exists so the fleet argues about a list of
names instead of about a percentage.

  dormancy.py               report, grouped
  dormancy.py --json        same, for the board
  dormancy.py --untested    only the modules that are wired AND uncovered
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
ROOT = FLEET.parent

SOURCE_DIRS = ("fleet/bin", "legacy/app", "self-improve/loop")

# Things this machine starts on its own. A module reached from one of these
# runs whether or not anyone is watching, which is exactly when an untested
# line costs something.
RUNNER_GLOBS = ("*.plist", "*.service", "*.sh", "*.timer", "crontab*")

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "worktrees",
             ".claude", "tests", "legacy/static"}


def _skip(p: Path) -> bool:
    return any(part in SKIP_DIRS for part in p.parts)


def modules() -> dict[str, Path]:
    """Every source module, keyed by path relative to the repo root.

    Keyed by path and not by name: `fleet/bin/fleet.py` is the engine and
    `legacy/app/fleet.py` is the read-only cockpit view of it, two different
    files that share a stem. An earlier version of this keyed by stem and
    asserted uniqueness, which is how that was found."""
    found: dict[str, Path] = {}
    for d in SOURCE_DIRS:
        for p in sorted((ROOT / d).rglob("*.py")):
            if _skip(p):
                continue
            found[str(p.relative_to(ROOT))] = p
    return found


def _by_stem(mods: dict[str, Path]) -> dict[str, list[str]]:
    """Import lines here are bare `import foo` against a patched sys.path, so
    a stem is all there is to match on. Where a stem is ambiguous every
    candidate is taken: calling a sleeping module awake wastes a look, calling
    an awake one asleep hides a live risk, and only one of those is cheap."""
    out: dict[str, list[str]] = {}
    for key, path in mods.items():
        out.setdefault(path.stem, []).append(key)
    return out


def entry_points(mods: dict[str, Path]) -> set[str]:
    """Modules named by something that runs unattended."""
    texts: list[str] = []
    for glob in RUNNER_GLOBS:
        for p in sorted(ROOT.rglob(glob)):
            if _skip(p):
                continue
            try:
                texts.append(p.read_text(errors="ignore"))
            except OSError:
                continue
    blob = "\n".join(texts)
    seeds: set[str] = set()
    for stem, keys in _by_stem(mods).items():
        # `foo.py` in a command line, not `foo` in a sentence: the extension
        # is what makes it an invocation rather than a mention.
        if re.search(rf"\b{re.escape(stem)}\.py\b", blob):
            seeds.update(keys)
    return seeds


def imports_of(path: Path, stems: dict[str, list[str]]) -> set[str]:
    """Local modules this file imports, as repo-relative keys."""
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except (OSError, SyntaxError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[-1])
            for a in node.names:
                names.add(a.name)
    out: set[str] = set()
    for n in names:
        out.update(stems.get(n, ()))
    return out


def reachable(mods: dict[str, Path], seeds: set[str]) -> set[str]:
    """Transitive closure of imports from the runners."""
    stems = _by_stem(mods)
    seen, stack = set(seeds), list(seeds)
    while stack:
        cur = stack.pop()
        for dep in imports_of(mods[cur], stems):
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)
    return seen


def coverage_by_module() -> dict[str, float]:
    """Percentages from the last `coverage run`, if there is one. Absent data
    is reported as absent, never as zero -- a missing measurement and a
    measured zero are opposite facts."""
    try:
        import coverage
    except ImportError:
        return {}
    try:
        cov = coverage.Coverage(data_file=str(ROOT / ".coverage"))
        cov.load()
        data = cov.get_data()
    except Exception:
        return {}
    out: dict[str, float] = {}
    for filename in data.measured_files():
        try:
            key = str(Path(filename).resolve().relative_to(ROOT))
        except ValueError:
            continue
        try:
            _, executable, _, missing, _ = cov.analysis2(filename)
        except Exception:
            continue
        if not executable:
            continue
        out[key] = 100.0 * (len(executable) - len(missing)) / len(executable)
    return out


def build() -> dict:
    mods = modules()
    seeds = entry_points(mods)
    live = reachable(mods, seeds)
    cov = coverage_by_module()

    def row(key: str) -> dict:
        return {
            "module": mods[key].stem,
            "path": key,
            "started_directly": key in seeds,
            "coverage": cov.get(key),
        }

    awake = sorted(live)
    asleep = sorted(set(mods) - live)
    return {
        "awake": [row(s) for s in awake],
        "asleep": [row(s) for s in asleep],
        "totals": {"modules": len(mods), "awake": len(awake),
                   "asleep": len(asleep), "entry_points": len(seeds)},
    }


def _fmt(rows: list[dict]) -> str:
    if not rows:
        return "  (none)\n"
    out = []
    for r in rows:
        c = r["coverage"]
        pct = "  n/a" if c is None else f"{c:5.1f}%"
        mark = "*" if r["started_directly"] else " "
        out.append(f"  {mark} {pct}  {r['path']}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--untested", action="store_true",
                    help="only awake modules under 50%% coverage")
    args = ap.parse_args()

    report = build()
    if args.untested:
        risky = [r for r in report["awake"]
                 if r["coverage"] is not None and r["coverage"] < 50]
        if args.json:
            print(json.dumps(risky, indent=2))
        else:
            print("AWAKE AND UNDER-TESTED "
                  "(runs unattended, under 50% covered)\n")
            print(_fmt(sorted(risky, key=lambda r: r["coverage"])))
        return 0

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    t = report["totals"]
    print(f"{t['modules']} modules -- {t['awake']} awake, {t['asleep']} asleep"
          f"  ({t['entry_points']} started directly, marked *)\n")
    print("AWAKE  reachable from something that runs unattended\n")
    print(_fmt(report["awake"]))
    print("ASLEEP  nothing that runs reaches these; leaving them alone is a "
          "choice, not neglect\n")
    print(_fmt(report["asleep"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
