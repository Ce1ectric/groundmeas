"""Protocols per tower (``--print``) and the ZIP archive (``--zip``)."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

import pytest

from groundmeas.towers import protocol as pp
from groundmeas.towers.pdf import (
    export_html,
    format_number_with_comma,
)
from groundmeas.towers.pdf import zip_pdfs


@pytest.fixture
def evaluated_copy(evaluated_demo, tmp_path):
    target = tmp_path / "campaign"
    shutil.copytree(evaluated_demo.parent, target)
    return target / "config.json"


def html_files(config: Path) -> dict[str, str]:
    folder = config.parent / "results" / "html_files"
    return {
        p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.html"))
    }


def test_protocols_in_english(evaluated_copy):
    assert pp.print_protocol(config_path=evaluated_copy, print_pdf=False) == 4
    pages = html_files(evaluated_copy)
    assert sorted(pages) == [
        "LX-01_21.html",
        "LX-01_3.html",
        "LX-01_37.html",
        "LX-01_8.html",
    ]
    page = pages["LX-01_3.html"]
    assert "Earthing measurement protocol" in page
    assert "The touch voltages exceed the permissible values" in page
    assert 'lang="en"' in page
    folder = evaluated_copy.parent / "results" / "html_files"
    for name in (
        "ZE_LX-01_3.png",
        "RA_LX-01_3.png",
        "US_LX-01_3.png",
        "UTbar_LX-01_3.png",
        "Map_LX-01_3.png",
    ):
        assert (folder / name).is_file(), name
    # images are referenced relative to the HTML file (portable between operating systems)
    sources = re.findall(r'src="([^"]*)"', page)
    assert sources and all("/" not in s and "\\" not in s for s in sources)
    assert "Company logo" not in page  # no logo configured


def test_protocols_in_german_with_logo(evaluated_demo_de, tmp_path, edit_config):
    target = tmp_path / "campaign"
    shutil.copytree(evaluated_demo_de.parent, target)
    config = target / "config.json"
    logo = target / "logo.png"
    shutil.copy(target / "measurements" / "Map_LX-01_3.png", logo)
    edit_config(config, logo="logo.png")
    pp.print_protocol(config_path=config, print_pdf=False)
    page = html_files(config)["LX-01_8.html"]
    assert (
        "Protokoll Erdungsmessung" in page
        and "Auslegung der Erdungsanlage korrekt" in page
    )
    assert (
        'src="logo.png"' in page
        and (target / "results" / "html_files" / "logo.png").is_file()
    )
    assert re.search(r"\d+,\d+ kA", page)  # decimal comma


def test_parallel_workers(evaluated_copy):
    assert (
        pp.print_protocol(worker_count=2, config_path=evaluated_copy, print_pdf=False)
        == 4
    )
    assert len(html_files(evaluated_copy)) == 4


def test_html_is_escaped(evaluated_copy, tmp_path):
    folder = tmp_path / "out"
    folder.mkdir()
    data = {
        "line_number": "L<1>",
        "tower": "2",
        "visual_findings": "<script>alert(1)</script>",
        "grounding_impedance_current": 50.0,
        "UD_value": 300.0,
        "UT_max_measured": 120,
        "impedances_table": {"Distanz": [0, 10], "ZE": [0, 0.3], "RA": [0, 0.6]},
        "touchvoltages_table": {"Ort": ["Mast & <Zaun>"], "UT": [12]},
    }
    html_path, pdf_path = export_html(data, folder, print_pdf=False)
    text = Path(html_path).read_text(encoding="utf-8")
    assert "<script>alert" not in text and "&lt;script&gt;" in text
    assert "Mast &amp; &lt;Zaun&gt;" in text
    assert (
        Path(html_path).name == "L_1__2.html"
    )  # characters invalid on Windows are replaced
    assert pdf_path is None


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (
            {
                "Messpunkte_UT": ["Mast (a)", "Mast (b)", "Gate (a)", "Gate (b)"],
                "UT_V": [10, 7, 4, 3],
                "Messpunkte_UT_Termination": ["1k", "2x1k", "1k", "2x1k"],
            },
            (["Mast", "Gate"], [10, 4], [7, 3]),
        ),
        (
            {
                "Messpunkte_UT": [
                    "Mast (kein Zusatzwiderstand)",
                    "Mast (mit Zusatzwiderstand 1kOhm)",
                ],
                "UT_V": [9, 6],
            },
            (["Mast"], [9], [6]),
        ),
        (
            {
                "Messpunkte_UT": [
                    "Tower (no additional resistor)",
                    "Tower (with additional resistor 1kOhm)",
                ],
                "UT_V": [9, 6],
            },
            (["Tower"], [9], [6]),
        ),
        ({"Messpunkte_UT": [], "UT_V": []}, ([], [], [])),
    ],
)
def test_split_by_termination(data, expected):
    assert pp._split_by_termination(data) == expected


def test_find_map(tmp_path):
    for name in [
        "Map_01-0815_15.PNG",
        "map_01-0815_16.jpg",
        "Map_01-0815_17.pdf",
        "Mapping_notes.png",
    ]:
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert pp._find_map("LH-01-0815", "015", [str(tmp_path)]).endswith(
        "Map_01-0815_15.PNG"
    )
    assert pp._find_map("LH-01-0815", "16", [str(tmp_path)]).endswith(
        "map_01-0815_16.jpg"
    )
    assert pp._find_map("LH-01-0815", "17", [str(tmp_path)]) is None  # not an image
    assert pp._find_map("LH-01-0815", "15", ["", str(tmp_path / "missing")]) is None


def test_zip_pdfs(tmp_path):
    source = tmp_path / "html"
    (source / "sub").mkdir(parents=True)
    for name in ("b.pdf", "a.PDF", "sub/c.pdf", "x.html"):
        (source / name).write_bytes(b"%PDF-1.7")
    archive = tmp_path / "out" / "protocols.zip"
    assert zip_pdfs(source, archive) == 3
    with zipfile.ZipFile(archive) as zf:
        assert zf.namelist() == ["a.PDF", "b.pdf", "sub/c.pdf"]


def test_zip_protocols(evaluated_copy):
    folder = evaluated_copy.parent / "results" / "html_files"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "LX-01_3.pdf").write_bytes(b"%PDF-1.7")
    assert pp.zip_protocols(config_path=evaluated_copy) == 1
    assert (evaluated_copy.parent / "results" / "protocols.zip").is_file()


def test_number_format_helper():
    assert format_number_with_comma(1.25) == "1,25"
