# Reference overview

Use the reference section for exact signatures, arguments, and behavior. Every entry lists the function or command name, inputs, outputs, and a short description.

- `21_ref_api.md`: Python API reference for the public functions in `groundmeas`.
- `22_ref_cli.md`: CLI reference for every `gm-cli` command.

Tip: All database operations require `groundmeas.db.connect_db(path)` once per process. The CLI resolves the path automatically; Python code must call it explicitly.
