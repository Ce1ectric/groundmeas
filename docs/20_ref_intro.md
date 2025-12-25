# Reference overview

Use the reference section when you need exact signatures, arguments, and behavior.

- `21_ref_api.md`: Python API reference (all public functions and helpers).
- `22_ref_cli.md`: CLI reference (every Typer command with arguments and behavior).

Tip: All database operations require `groundmeas.db.connect_db(path)` once per process. The CLI resolves the path automatically; Python code must call it explicitly.
