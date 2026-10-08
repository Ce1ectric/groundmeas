"""PDF printing with a headless Chromium (skipped if no browser is available)."""

from __future__ import annotations

import shutil

import pytest

from groundmeas.towers import pdf as html_printer
from groundmeas.towers.protocol import print_protocol

pytestmark = pytest.mark.pdf


@pytest.fixture(autouse=True)
def _require_browser(chromium_available):
    if not chromium_available:
        pytest.skip(
            'no PDF printing: pip install "groundmeas[pdf]" and run '
            "`gm-cli towers install-browser`"
        )


def test_protocol_pdf(evaluated_demo, tmp_path):
    target = tmp_path / "campaign"
    shutil.copytree(evaluated_demo.parent, target)
    print_protocol(config_path=target / "config.json")
    pdf = target / "results" / "html_files" / "LX-01_3.pdf"
    assert pdf.read_bytes()[:5] == b"%PDF-"
    assert pdf.stat().st_size > 20_000  # contains the diagrams


def test_pdf_with_footer(tmp_path):
    html = tmp_path / "page.html"
    html.write_text("<html><body><h1>Footer test</h1></body></html>", encoding="utf-8")
    html_printer.generate_pdf(
        html, tmp_path / "page.pdf", footer_text="Report", language="de"
    )
    assert (tmp_path / "page.pdf").read_bytes()[:5] == b"%PDF-"


def test_browser_from_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setenv(html_printer.BROWSER_ENV_VAR, str(tmp_path / "no-such-browser"))
    html = tmp_path / "page.html"
    html.write_text("<html></html>", encoding="utf-8")
    with pytest.raises(
        Exception
    ):  # noqa: B017, PT011 - Playwright raises its own error type
        html_printer.generate_pdf(html, tmp_path / "page.pdf")
