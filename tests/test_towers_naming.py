"""Identifiers, file-name parsing and cross-platform file names."""

from __future__ import annotations

import unicodedata

import pytest

from groundmeas.towers.naming import (
    FILE_NAME_STRUCTURES,
    extract_line_and_tower,
    has_extension,
    is_soil_resistivity_file,
    normalize_text,
    normalize_tower_id,
    safe_filename,
    tower_number,
    tower_sort_key,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8", "8"),
        ("008", "8"),
        ("08n", "8N"),
        ("28N", "28N"),
        (8, "8"),
        (8.0, "8"),
        ("12.0", "12"),
        (" 7a ", "7A"),
        ("A12", "A12"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_tower_id(raw, expected):
    assert normalize_tower_id(raw) == expected


def test_normalize_text_unifies_unicode_forms():
    nfd = unicodedata.normalize("NFD", "Mast Süd")
    assert nfd != "Mast Süd"
    assert normalize_text(nfd) == "Mast Süd"
    assert normalize_text("  x ") == "x"


@pytest.mark.parametrize(
    ("tower", "number"), [("28N", 28), ("08", 8), ("2M", 2), ("M", None)]
)
def test_tower_number(tower, number):
    assert tower_number(tower) == number


def test_tower_sort_key_orders_numerically():
    towers = ["10", "9", "2M", "2", "A", "100"]
    assert sorted(towers, key=tower_sort_key) == ["2", "2M", "9", "10", "100", "A"]


@pytest.mark.parametrize(
    ("filename", "structure", "expected"),
    [
        ("ZE_LX-01_8.xml", "PREFIX_LINENUMBER_TOWER", ("LX-01", "8")),
        ("UT_LX-01_008N.txt", "PREFIX_LINENUMBER_TOWER", ("LX-01", "008N")),
        ("123_456.xml", "LINENUMBER_TOWER", ("123", "456")),
        ("456_123.xml", "TOWER_LINENUMBER", ("123", "456")),
        ("incorrect.xml", "PREFIX_LINENUMBER_TOWER", (None, None)),
        ("ZE_LX-01_8_spez.Erdw..xml", "PREFIX_LINENUMBER_TOWER", (None, None)),
        ("ZE_LX-01_8.xml", "UNKNOWN", (None, None)),
    ],
)
def test_extract_line_and_tower(filename, structure, expected):
    assert extract_line_and_tower(filename, structure) == expected


def test_extract_line_and_tower_normalises_unicode():
    name = unicodedata.normalize("NFD", "ZE_Lö-1_3.xml")
    assert extract_line_and_tower(name, "PREFIX_LINENUMBER_TOWER") == ("Lö-1", "3")


def test_supported_structures():
    assert "PREFIX_LINENUMBER_TOWER" in FILE_NAME_STRUCTURES


@pytest.mark.parametrize(
    ("name", "extensions", "expected"),
    [
        ("a.xml", (".xml",), True),
        ("a.XML", (".xml",), True),
        ("dir/a.Txt", (".txt", ".xml"), True),
        ("a.xml.bak", (".xml",), False),
        ("a", (".xml",), False),
    ],
)
def test_has_extension(name, extensions, expected):
    assert has_extension(name, *extensions) is expected


def test_soil_resistivity_file_detection():
    assert is_soil_resistivity_file("ZE_LX-01_8_spez.Erdw..xml")
    assert is_soil_resistivity_file("ZE_LX-01_8_SPEZ.XML")
    assert not is_soil_resistivity_file("ZE_LX-01_8.xml")
    assert not is_soil_resistivity_file("UT_LX-01_8_spez.txt")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("LX-01_8", "LX-01_8"),
        ("L/X:01*8?", "L_X_01_8_"),
        ('a<b>c"d|e', "a_b_c_d_e"),
        ("name. ", "name"),
        ("CON", "_CON"),
        ("nul.json", "_nul.json"),
        ("", "_"),
    ],
)
def test_safe_filename(name, expected):
    assert safe_filename(name) == expected
