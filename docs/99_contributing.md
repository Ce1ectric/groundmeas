# Contributing to groundmeas

We welcome contributions! Here's how you can help.

## Development Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/Ce1ectric/groundmeas.git
    cd groundmeas
    ```

2.  **Install dependencies** (using Poetry):
    ```bash
    poetry install
    ```

3.  **Activate the environment**:
    ```bash
    poetry shell
    ```

## Running Tests

We use `pytest` for testing.

```bash
pytest
```

## Building Documentation

We use `mkdocs` with `mkdocstrings` for documentation.

1.  **Install doc dependencies**:
    ```bash
    poetry add -D mkdocs mkdocs-material mkdocstrings[python]
    ```

2.  **Serve documentation locally**:
    ```bash
    mkdocs serve
    ```
    Open `http://127.0.0.1:8000` in your browser.

3.  **Build static site**:
    ```bash
    mkdocs build
    ```

## Release Process

Use the included script to release a new version:

```bash
python scripts/release.py
```
