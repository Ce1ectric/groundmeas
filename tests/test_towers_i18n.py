"""Translations of the protocol texts."""

from __future__ import annotations

import string

import pytest

from groundmeas.towers.i18n import (
    DEFAULT_LANGUAGE,
    STRINGS,
    SUPPORTED_LANGUAGES,
    format_number,
    get_strings,
    missing_keys,
    normalize_language,
    translate,
)


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_language_is_complete(language):
    assert missing_keys(language) == set()


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_placeholders_match_english(language):
    formatter = string.Formatter()
    for key, english in STRINGS["en"].items():
        expected = {f for _, f, _, _ in formatter.parse(english) if f}
        found = {f for _, f, _, _ in formatter.parse(STRINGS[language][key]) if f}
        assert found == expected, key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, DEFAULT_LANGUAGE),
        ("", DEFAULT_LANGUAGE),
        ("DE", "de"),
        ("de-AT", "de"),
        ("en_GB", "en"),
    ],
)
def test_normalize_language(raw, expected):
    assert normalize_language(raw) == expected


def test_unsupported_language_raises():
    with pytest.raises(ValueError, match="Unsupported language"):
        normalize_language("xx")


def test_translate_with_placeholders():
    assert translate("hint_fast", "de", position="19,7").startswith("Lage 19,7 %")
    assert (
        translate("plot_max_with", "en", value=12.4) == "Max. with add. resistor: 12 V"
    )


def test_translate_unknown_key_raises():
    with pytest.raises(KeyError):
        translate("no_such_key", "en")


@pytest.mark.parametrize(
    ("value", "language", "expected"),
    [
        (0.398, "de", "0,398"),
        (0.398, "en", "0.398"),
        (12, "de", "12"),
        ("1.5", "de", "1,5"),
    ],
)
def test_format_number(value, language, expected):
    assert format_number(value, language) == expected


def test_get_strings_returns_table():
    assert get_strings("de")["protocol_header"] == "Protokoll Erdungsmessung"
