r"""Cross-platform path helpers.

Configuration files may contain absolute paths (``C:\Data\...`` on Windows,
``/Users/...`` on macOS), paths relative to the configuration file, ``~`` for
the home directory and environment variables (``$HOME``, ``%USERPROFILE%``).
`resolve_path` turns all of them into absolute `pathlib.Path`
objects so that one configuration can be shared between operating systems,
e.g. inside a synchronised cloud folder.
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

__all__ = ["ensure_directory", "file_uri", "resolve_path", "sorted_listdir"]


def resolve_path(
    value: str | os.PathLike[str] | None, base_dir: str | os.PathLike[str]
) -> Path | None:
    """Resolve a path from a configuration file.

    Parameters
    ----------
    value : str, os.PathLike or None
        Path as written in the configuration. ``~`` and environment variables
        are expanded; relative paths are interpreted relative to ``base_dir``.
    base_dir : str or os.PathLike
        Directory that relative paths refer to (normally the folder that
        contains the configuration file).

    Returns
    -------
    pathlib.Path or None
        Absolute, normalised path, or ``None`` if ``value`` is empty.

    Examples
    --------
    >>> resolve_path("../data/measurements", "/projects/campaign/config").as_posix()
    '/projects/campaign/data/measurements'
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(os.path.expandvars(os.path.expanduser(text)))
    if not path.is_absolute():
        path = Path(base_dir) / path
    return Path(os.path.normpath(path))


def file_uri(path: str | os.PathLike[str]) -> str:
    """Return a ``file://`` URI for a local file.

    Unlike string concatenation this works for Windows drive letters and
    percent-encodes blanks, ``#`` and non-ASCII characters.

    Parameters
    ----------
    path : str or os.PathLike
        Local file path (relative paths are made absolute).

    Returns
    -------
    str
        URI such as ``file:///C:/Data/LX-01_8.html``.
    """
    return Path(path).resolve().as_uri()


def sorted_listdir(directory: str | os.PathLike[str]) -> list[str]:
    """List a directory in a deterministic, platform-independent order.

    ``os.listdir`` returns entries in file-system order, which differs between
    APFS, NTFS and ext4. Sorting by the NFC-normalised name makes outputs (row
    order of summaries, processing order, log messages) identical on all
    operating systems.

    Parameters
    ----------
    directory : str or os.PathLike
        Directory to list.

    Returns
    -------
    list of str
        Entry names (not paths), sorted.
    """
    return sorted(
        os.listdir(directory),
        key=lambda name: (unicodedata.normalize("NFC", name), name),
    )


def ensure_directory(path: str | os.PathLike[str]) -> Path:
    """Create ``path`` (including parents) if it does not exist.

    Parameters
    ----------
    path : str or os.PathLike
        Directory to create.

    Returns
    -------
    pathlib.Path
        The directory path.
    """
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory
