"""Read the per-tower JSON files written by the ``calc`` step."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .naming import has_extension
from .paths import sorted_listdir

__all__ = ["json_reader"]

logger = logging.getLogger(__name__)


def json_reader(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Load all per-tower JSON files of a folder.

    Parameters
    ----------
    path : str or os.PathLike
        Folder that contains the ``<line>_<tower>.json`` files.

    Returns
    -------
    list of dict
        Parsed files in file-name order. Files that are not valid JSON or do
        not describe a tower (no ``Leitung``/``Mast`` keys) are skipped.
    """
    import_data_list: list[dict[str, Any]] = []
    for filename in sorted_listdir(path):
        if not has_extension(filename, ".json"):
            continue
        json_file_path = os.path.join(path, filename)
        try:
            with open(json_file_path, encoding="utf-8-sig") as file:
                import_data = json.load(file)
        except (OSError, ValueError) as exc:
            logger.warning("Skipping %s: %s", filename, exc)
            continue
        if not isinstance(import_data, dict) or not {"Leitung", "Mast"} <= set(
            import_data
        ):
            logger.debug("Skipping %s: not a tower result", filename)
            continue
        import_data_list.append(import_data)
    return import_data_list
