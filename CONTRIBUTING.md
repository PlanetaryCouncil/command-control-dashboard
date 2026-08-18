# Contributing

Short, because you have common sense and a long list of rules would insult it.

## The shape of it

Open an issue. That is the front door — say what you noticed, or what you want.
A pull request is welcome too, and an issue first is kinder to both of us if
the change is large enough that you would be sad to have it declined.

## Running the thing

```
python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/pip install pytest httpx2
.venv/bin/pytest -q
```

That is the whole setup. If it does not work on your machine, that is a bug in
this file and worth an issue on its own.

To see it run: `docs/SPIN-IT-UP.md`.

## What gets merged

Tests pass, and the change explains itself.

The commit messages here are longer than usual on purpose. They say what was
broken and why the fix is shaped the way it is, because in a year the diff will
still be obvious and the reason will not. Match that if you can. If writing the
reason down is hard, that is usually the code telling you something.

New behaviour comes with a test. Not for coverage — so that the next person can
change the code without wondering what they broke.

## Things worth knowing before you touch them

**`docs/TRUST-LAYERS.md`** — who is allowed to make this machine do things.
Anything that reads outside input should be read alongside it. The short
version: a layer describes a statement, not a machine, and nothing promotes
itself.

**Secrets never enter this repo.** Tokens live in `~/.config/fleet/`, node
secrets live in the environment. If a change needs a credential, it needs a
path to one, not the credential.

**Endpoints are local-only by default.** If you add one the public can reach,
it needs a rate limit, and say in the commit message why the limit is that
number.

## If you find a security problem

`SECURITY.md`. Please do not open a public issue for it.

## Art

There is an issue template for it. The gallery is part of the project, not a
decoration on it.
