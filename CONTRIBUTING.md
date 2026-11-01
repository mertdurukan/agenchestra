# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

## Setup

- Python 3.9 or newer, Git. No other runtime dependency; `pytest` is only needed to run tests.
- Fork and clone the repository, then install the test runner:

```bash
python -m pip install pytest
```

## Running tests

Run tests from the repository root. Prefer a targeted run while you work:

```bash
# one file
PYTHONUTF8=1 python -m pytest plugins/orkestra/tests/test_cfg.py -q

# the same set CI runs
cd plugins/orkestra
PYTHONUTF8=1 python -m pytest tests/test_cfg.py tests/test_doktor.py tests/test_tasinabilirlik.py -q
```

The full suite (400+ test files under `plugins/orkestra/tests`) runs in parallel, one process per file:

```bash
python plugins/orkestra/scripts/test_paralel.py
```

`test_paralel.py` also takes `-n N` (workers) and file paths to run a subset. CI (`.github/workflows/orkestra-test.yml`) runs on Linux, Windows and macOS with Python 3.9 and 3.13, so keep changes portable (no hard-coded paths, use `os.path`).

## Pull requests

- Branch from `main`, keep one logical change per PR, and link the issue (`Fixes #N`).
- Add or update a test for any behavior change.
- Do not commit secrets, credentials or machine-specific paths.
- Fill in the pull request template and make sure the tests you touched pass locally.

## Commit style

- Short imperative subject, under about 72 characters, e.g. `Add tests for ret_nedeni.kok`.
- Explain the why in the body when it is not obvious.
- Do not rewrite history that is already pushed.

## Questions and security

Open an issue for questions. For vulnerabilities, follow [SECURITY.md](SECURITY.md) and do not file a public issue.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
