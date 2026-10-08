"""Path resolution and other cross-platform helpers."""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

from groundmeas.towers.paths import (
    ensure_directory,
    file_uri,
    resolve_path,
    sorted_listdir,
)


def test_resolve_relative_path_against_base(tmp_path):
    base = tmp_path / "config"
    assert resolve_path("../data/x.xlsx", base) == tmp_path / "data" / "x.xlsx"
    assert resolve_path("data", base) == base / "data"


def test_resolve_absolute_path_is_kept(tmp_path):
    absolute = tmp_path / "abs" / "file.xml"
    assert resolve_path(str(absolute), "/somewhere/else") == absolute


def test_resolve_expands_home_and_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("TGM_TEST_ROOT", str(tmp_path))
    assert resolve_path("$TGM_TEST_ROOT/data", "/irrelevant") == tmp_path / "data"
    home = Path(os.path.expanduser("~"))
    assert resolve_path("~/campaign", "/irrelevant") == home / "campaign"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_resolve_empty_values(value, tmp_path):
    assert resolve_path(value, tmp_path) is None


def test_file_uri_round_trip_with_special_characters(tmp_path):
    target = tmp_path / "Campaign #1 Süd" / "protocol.html"
    target.parent.mkdir()
    target.write_text("x", encoding="utf-8")
    uri = file_uri(target)
    assert uri.startswith("file://")
    assert " " not in uri and "#1" not in uri  # blanks and '#' are percent-encoded
    parsed = urlparse(uri)
    decoded = unquote(parsed.path)
    if os.name == "nt":  # file:///C:/... -> /C:/...
        decoded = decoded.lstrip("/")
    assert Path(decoded) == target.resolve()


@pytest.mark.skipif(os.name != "nt", reason="drive letters exist on Windows only")
def test_windows_drive_letters_give_valid_uris():
    assert (
        file_uri(r"C:\Data\Campaign 1\x.html") == "file:///C:/Data/Campaign%201/x.html"
    )


def test_sorted_listdir_is_deterministic(tmp_path):
    # no names differing only in case: macOS and Windows file systems ignore case
    for name in ["b.txt", "A.txt", unicodedata.normalize("NFD", "ä.txt")]:
        (tmp_path / name).write_text("x", encoding="utf-8")
    first = sorted_listdir(tmp_path)
    assert first == sorted_listdir(tmp_path)
    assert first.index("A.txt") < first.index("b.txt")


def test_ensure_directory_creates_parents(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    assert ensure_directory(target) == target
    assert target.is_dir()
    ensure_directory(target)  # idempotent
