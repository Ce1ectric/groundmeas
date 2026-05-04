# Contributing to groundmeas

We welcome contributions. Follow these steps to set up a local development environment.

## Development setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Ce1ectric/groundmeas.git
   cd groundmeas
   ```

2. Install dependencies (Poetry):
   ```bash
   poetry install
   ```

3. Activate the environment:
   ```bash
   poetry shell
   ```

## Pre-commit hooks

`.pre-commit-config.yaml` ships a small set of hooks that mirror the CI
gates so issues can be caught locally:

```bash
poetry run pre-commit install --hook-type pre-commit --hook-type pre-push
```

After installation:

- on every commit, `black` formats staged Python files and the standard
  hygiene hooks (trailing whitespace, end-of-file, YAML / TOML / merge
  conflict markers, large files) run;
- on every push, the changelog gate (`scripts/check_changelog.py`
  against `origin/main`) and `cffconvert --validate` run.

A push hook can be bypassed in an emergency with `git push --no-verify`,
but the same checks then run in CI.

## Running tests

We use `pytest`.

```bash
pytest
```

## Building documentation

We use MkDocs with the Read the Docs theme and mkdocstrings.

1. Install doc dependencies:
   ```bash
   poetry add -D mkdocs mkdocstrings[python]
   ```

2. Serve documentation locally:
   ```bash
   mkdocs serve
   ```

3. Build the static site:
   ```bash
   mkdocs build
   ```

## Changelog

`groundmeas` follows the
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
convention. Every change that is observable to a user — added
features, behavioural changes, bug fixes, deprecations, removals,
security fixes — must be recorded in `CHANGELOG.md` under the
`[Unreleased]` block as part of the same pull request.

Use the standard categories:

`Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`,
`Docs`, `Internal`. Pure refactors, test changes, packaging tweaks and
CI work go under `Internal`.

The triage backlog (Roadmap, Ideas inbox) lives at the bottom of the
same file.

### CI gate

The CI pipeline rejects pull requests that change files under
`src/groundmeas/` without touching the `[Unreleased]` block. The check
is implemented in `scripts/check_changelog.py` and can be reproduced
locally:

```bash
python scripts/check_changelog.py --base origin/main
```

If a change really has no user-visible impact (for example a typo fix
in a docstring that is not exposed in the rendered docs), apply the
`skip-changelog` label to the pull request to bypass the check.

`CITATION.cff` is also validated on every push and pull request via
`cffconvert --validate`; the same check runs locally during
`poetry run release`.

## Release process

Releases are cut with the included Typer script:

```bash
poetry run release          # prompts for major / minor / patch
```

The script

1. bumps the version in `pyproject.toml`, `src/groundmeas/__init__.py`
   and `CITATION.cff`,
2. validates `CITATION.cff` (warning only if `cffconvert` is missing),
3. moves the `[Unreleased]` block in `CHANGELOG.md` into a dated
   `## [X.Y.Z] — YYYY-MM-DD` section, inserts a fresh empty
   `[Unreleased]` block, and refreshes the compare-link footer,
4. regenerates `THIRD_PARTY_NOTICES.md`,
5. runs the test suite,
6. commits, tags `vX.Y.Z` and pushes — the tag triggers the PyPI
   publish job via OIDC Trusted Publishing.

The release aborts when `[Unreleased]` has no bullet entries. Pass
`--allow-empty` to release anyway (e.g. for a packaging-only patch
release):

```bash
poetry run release -- --allow-empty
```
