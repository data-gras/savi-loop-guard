# Contributing to savi-loop-guard

Thanks for taking a look. This is a small, focused package: the bar for a
change is "does it make loop detection more correct or more useful," not
"is it a good idea in general."

## Dev setup

```bash
git clone https://github.com/data-gras/savi-loop-guard.git
cd savi-loop-guard
pip install -e ".[dev]"
pytest -q
```

No external services, no Docker, no API keys. The whole test suite runs
offline in a couple of seconds. If it doesn't, that's a bug in the package,
not your environment.

## Before opening a PR

- Add a test that fails without your change and passes with it. `tests/test_detector.py`
  has plenty of examples for both the velocity and structural checks.
- Keep `install_requires` empty. Zero third-party dependencies is a
  deliberate, stated feature of this package (see the README); a PR that
  adds one needs a very good reason and will likely be turned down.
- Run `pytest -q` locally before pushing. CI runs the same command.
- Small, focused PRs over large ones. If you're planning something bigger
  than a bug fix (a new detection strategy, a changed default), open an
  issue first to discuss it, saves both of us a rewritten PR.

## Reporting a bug

Open an issue with: the `CallEvent` sequence you fed in (or a minimal
repro), what `check()` returned, and what you expected instead. "It didn't
detect my loop" is much easier to fix with the actual events than a
description of them.

## Security issues

Don't open a public issue for a security concern, see [SECURITY.md](SECURITY.md).

## License

By contributing, you agree your contribution is licensed under this
project's [MIT License](LICENSE).
