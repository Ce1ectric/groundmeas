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

## Release process

Use the included script to release a new version:

```bash
python scripts/release.py
```
