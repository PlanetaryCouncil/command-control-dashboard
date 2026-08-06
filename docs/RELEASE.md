# Release checklist

A repeatable sequence for cutting a release and (the first time) flipping the
repository public. The order matters: privacy and security gates come before
anything is published, because Git makes mistakes durable in history and forks.

## 1. Security gates (must be closed)

- [ ] Remote callers cannot reach any control path or local-only action.
      (`tests/test_fleet_public.py`, `tests/test_public_tunnel.py`)
- [ ] `X-Forwarded-For` cannot be spoofed to look local; the fleet front door
      sanitises it before forwarding.
- [ ] Public endpoints do not leak private data (process command lines, prompts,
      tokens).
- [ ] `pytest -q` is fully green on a clean tree.

## 2. Privacy gates (must be closed, before the first public push)

- [ ] No third-party IPs, home paths, or non-consenting personal data in HEAD.
- [ ] Caller addresses are coarsened at capture, not just cleaned up after.
- [ ] Git history is clean: `git grep <sensitive-string> $(git rev-list --all)`
      returns nothing for every known target, and no sensitive file is
      recoverable via `git log --all --diff-filter=D`.
- [ ] Runtime-only state is **not tracked** (see `.gitignore`); example files
      exist where a fresh clone needs a shape.
- [ ] A full backup bundle exists before any history rewrite:
      `git bundle create ../backup.bundle --all`.

## 3. Baseline (before public)

- [ ] `LICENSE` present.
- [ ] `SECURITY.md` present with a private reporting route.
- [ ] CI runs the full suite on supported Python versions (`.github/workflows/ci.yml`).
- [ ] README / AUTH / PUBLISHING match the actual routes and trust model.

## 4. Cut the release

- [ ] Reconcile the intended branches onto `main` with reviewed history.
- [ ] `git status` is clean (discard runtime churn first).
- [ ] Tag: `git tag -a vX.Y.Z -m "..." && git push <remote> vX.Y.Z`.
- [ ] Verify the remote head matches local: `git ls-remote <remote> refs/heads/main`.

## 5. Flip visibility (operator, deliberately)

- [ ] Re-read `git log -p` for the release range one last time.
- [ ] Make the repository public.
- [ ] Confirm CI runs and passes on the public repo.

## Notes

- Runtime state files (`data/*.jsonl`, `data/*.json`, `fleet/state/*`,
  `fleet/rota/*`, `self-improve/state/*`) are written constantly by the running
  fleet. Never commit that churn as release source — discard it with
  `git checkout -- .` before tagging.
- The remote is `GitHub_priv`, not `origin`.
