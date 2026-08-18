# Pre-public review — 18 August 2026

The repo is private and about to be made public, with issues as the way other
people contribute. This is what I found. **Nothing here leaks a secret**, which
was the thing worth checking first and hardest.

Three blockers, four things to fix soon, and a list of what is already right.

---

## Blockers — fix before the repo is public

### 1. CI has never run. Not once.

Every workflow run in the repo's history ended in `startup_failure`, in zero
seconds, having created zero jobs:

```
completed  startup_failure  watchdog: the protection existed only on paper   0s
completed  startup_failure  Merge pull request #52                           0s
completed  startup_failure  localvoice: a slow load is not a dead model       0s
completed  startup_failure  docs: a numbered table of what actually changed   0s
```

```
jobs: 0
X This run likely failed because of a workflow file issue.
```

**Now proven not to be the workflow file.** I pushed a trivial three-line
workflow alongside the real one — `runs-on: ubuntu-latest`, one `echo` — and it
failed identically. GitHub registers both workflows as `active` and then
refuses to build a run for either:

```
CI    | active | .github/workflows/ci.yml
hello | active | .github/workflows/hello.yml

 | startup_failure | path=BuildFailed
 | startup_failure | path=BuildFailed
```

An empty run name and `path=BuildFailed` means GitHub never got as far as
reading a file. So this is account or repository level, not the YAML: a
spending limit, or a ruleset requiring a workflow that cannot be resolved. The
billing API needs a scope this token does not have, so **the last step is
yours** — the Actions tab in a browser. The probe workflow has been removed
now that it has answered.

This matters more the moment the repo is public. A contributor opens a pull
request, sees no checks run, and has no idea whether they broke anything.
Neither do you.

### 2. CI would fail even if it started

Two independent reasons:

```yaml
pip install pytest httpx      # starlette wants httpx2
```

That is the exact bug fixed in `25b175d` for local runs — with `httpx`, all
fourteen HTTP test modules fail at *collection*. The workflow was never
updated because it never ran, so nobody saw it.

And `pyproject.toml` had **no `[build-system]` section**. Declaring one turned
a silent assumption into a visible failure:

```
error: Multiple top-level packages discovered in a flat-layout:
       ['data', 'fleet', 'legacy', 'githooks']
ERROR: Failed to build 'file:///home/YOU/ccd'
```

`pip install .` — the second step of the CI job — **has never been able to
work**. Fixed by telling setuptools to package nothing, which is honest: this
is a running system, not a library, and the install exists only to resolve
dependencies.

### 3. `.gitignore` ignores `.venv/` but not `.venv311/`

```
$ cat .gitignore
.venv/
```

A virtualenv **was** committed to this repo — 2,260 files of it:

```
$ git log --all --diff-filter=A --name-only | grep -c "site-packages"
2260
   260 .venv311/lib/python3.11/site-packages/pygments/lexers
    79 .venv311/lib/python3.11/site-packages/pip/_vendor/rich
```

It has since been removed from the tree, but the ignore rule was never widened,
so the next `python -m venv .venv312` gets committed the same way.

This is not only tidiness. **It caused a real outage.** Git tracked
`.venv311/lib/` but never `.venv311/bin/`, so when the directory was restored
from git it came back as a virtualenv with libraries and no interpreter — which
is why six fleet services died with `status=203/EXEC` on 18 August, and why
pytest could not run at all. Half a virtualenv in version control is worse than
none.

---

## Should fix soon

### 4. `/api/charge` accepts unbounded writes from anyone

It sits in `do_POST` with no `_remote()` block and no rate limiter, while its
neighbours have one or the other:

```
/api/selfies        -> _flooding("selfies")
/api/signatures/sign -> _rate_limited()
/api/selfies/judge   -> _remote() and 404
/api/charge          -> neither
```

It even records `"remote": self._remote()`, so it knows where the caller is and
allows it anyway. On a public box that is an append-only file anyone can grow.
Either rate-limit it like the selfie wall or make it local-only.

### 5. A personal email address is in the repo

```
fleet/data/projects.yaml:11:    email: marsXrobertson@gmail.com
```

Probably deliberate — a contact address on a public project is normal. Flagging
it so it is a decision rather than a discovery. A role address ages better than
a personal one.

### 6. The contribution path is not written down

`LICENSE` (MIT) and `SECURITY.md` are present. Missing:

- **`CONTRIBUTING.md`** — how to run the tests, what a good issue looks like,
  what gets merged.
- **`CODE_OF_CONDUCT.md`** — GitHub prompts for one and its absence is loud on
  a project inviting strangers.
- **Issue templates.** There is exactly one, `art-submission.yml`. If issues
  are the front door for contribution, there should be a bug template and a
  feature template beside it.

### 7. The Python versions no longer match reality

`requires-python = ">=3.11"` and the CI matrix tests 3.11 and 3.12. The NUC
now runs **3.14** — 3.11 was removed from the machine entirely, which is what
killed `.venv311`. The tested versions and the running version have no overlap.

---

## What is already right

Worth saying, because it is the part that would be expensive to fix late.

**No secrets anywhere in 191 commits.** I scanned the full history for tokens,
keys, passwords and private key blocks. The only hits were the words `secret`
and `password` inside documentation and vendored library source.

**Credentials were kept outside the tree on purpose, and it held.** The
Telegram bot token lives at `~/.config/fleet/telegram.env`, chmod 600, and
`telegram.py` refuses to start if that file is group-readable. Node secrets
live in the environment. `data/trusted_nodes.json` is a public list of *who*,
with no secrets in it — Kerckhoffs, deliberately.

**`fleet/data/homies.txt` is the example file, not the real one:**

```
# IP prefixes of YOUR OWN machines and gateways, one per line.
# Kept out of the repo: a home /64 prefix is a location
# fingerprint. The real list lives at ~/.config/fleet/homies.txt
```

Someone thought about this before it mattered.

**The operator-only endpoints are actually operator-only.** `/api/selfies/judge`
and `/api/signatures/judge` both check `_remote()` and return 404 rather than
403, so a remote caller cannot even confirm they exist. `CONTROL_PATHS` blocks
the terminal, chat and kill endpoints the same way.

**The only IP addresses in the tree are test fixtures** — `1.2.3.4` and
`9.9.9.9` in `test_ratelimit.py`.

**406 tests pass**, on both machines.

---

## The one-line version

The repo is safe to publish today. It is not yet ready to *receive* anyone:
nothing validates a contributor's pull request, and nothing tells them how to
open one.
