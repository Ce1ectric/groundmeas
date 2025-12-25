"""
Backward-compatible shim for the CLI entry point.

The CLI implementation now lives in ``groundmeas.ui.cli``. This module simply
imports and re-exports ``app`` so existing entry points keep working.
"""

from groundmeas.ui.cli import app  # noqa: F401
