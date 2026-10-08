"""Render the per-tower protocol as HTML and convert HTML pages to PDF.

The protocol is a Jinja2 template (``templates/protocol.html`` with
``templates/protocol.css``) rendered into the folder that also holds the
diagrams; images are referenced by file name, so the folder can be moved or
opened on any operating system. PDF files are printed by a headless Chromium
browser driven by Playwright (optional dependency, ``pip install
"groundmeas[pdf]"``). Install the browser once with:

    gm-cli towers install-browser

(equivalent to ``python -m playwright install chromium``).

If that download is not possible (e.g. behind a corporate proxy), an installed
Google Chrome or Microsoft Edge is used automatically; a specific browser can
be selected with the environment variable ``GROUNDMEAS_BROWSER``.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .i18n import format_number, get_strings, translate
from .naming import safe_filename
from .paths import ensure_directory, file_uri

__all__ = [
    "BROWSER_ENV_VAR",
    "TEMPLATE_DIR",
    "export_html",
    "format_number_with_comma",
    "generate_pdf",
    "install_browser",
    "zip_pdfs",
]

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"
"""Folder that contains the protocol and statistics templates and the stylesheet."""
TEMPLATE_NAME = "protocol.html"
BROWSER_ENV_VAR = "GROUNDMEAS_BROWSER"
"""Environment variable naming the browser for PDF printing.

Either the path of a Chromium-based executable or a Playwright channel such as
``chrome`` or ``msedge``. The former name ``TOWER_GROUNDING_BROWSER`` is still
read if this variable is unset.
"""
LEGACY_BROWSER_ENV_VAR = "TOWER_GROUNDING_BROWSER"
_CHANNELS = ("chromium", "chrome", "chrome-beta", "msedge", "msedge-beta", "msedge-dev")
STYLESHEET_NAME = "protocol.css"


def format_number_with_comma(number: Any) -> str:
    """Render a number with a decimal comma (German style).

    Parameters
    ----------
    number : Any
        Value to format.

    Returns
    -------
    str
        ``str(number)`` with ``.`` replaced by ``,``.
    """
    return str(number).replace(".", ",")


def _environment(language: str) -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "htm", "xml"]),
    )
    env.globals["num"] = lambda value: format_number(value, language)
    # name used by templates written for version 0.1
    env.globals["formatNumberWithComma"] = env.globals["num"]
    return env


def export_html(
    data: dict[str, Any],
    export_path: str | os.PathLike[str] | None = None,
    print_pdf: bool = True,
    *,
    language: str = "en",
    logo_path: str | os.PathLike[str] | None = None,
) -> tuple[str, str | None]:
    """Render the protocol of one tower.

    Parameters
    ----------
    data : dict
        Template variables (see ``templates/protocol.html``); ``line_number`` and
        ``tower`` determine the file names.
    export_path : str, os.PathLike or None, optional
        Output folder (default: current working directory). The stylesheet and
        the logo are copied there.
    print_pdf : bool, optional
        Also create the PDF (requires Playwright and Chromium).
    language : str, optional
        Language of the protocol texts.
    logo_path : str, os.PathLike or None, optional
        Image shown in the header; no logo if ``None``.

    Returns
    -------
    tuple of (str, str or None)
        Paths of the HTML file and of the PDF (``None`` if not printed).
    """
    output_dir = Path(export_path) if export_path is not None else Path.cwd()
    env = _environment(language)
    template = env.get_template(TEMPLATE_NAME)

    context = dict(data)
    context["t"] = get_strings(language)
    context["language"] = language
    context["company_logo"] = ""
    if logo_path:
        logo = Path(logo_path)
        target = output_dir / safe_filename(logo.name)
        if logo.resolve() != target.resolve():
            shutil.copy(logo, target)
        context["company_logo"] = target.name

    base_name = safe_filename(f"{data['line_number']}_{data['tower']}")
    html_path = output_dir / f"{base_name}.html"
    html_path.write_text(template.render(**context), encoding="utf-8")
    shutil.copy(TEMPLATE_DIR / STYLESHEET_NAME, output_dir / STYLESHEET_NAME)

    pdf_path = output_dir / f"{base_name}.pdf"
    if print_pdf:
        generate_pdf(html_path, pdf_path, language=language)
        return os.fspath(html_path), os.fspath(pdf_path)
    return os.fspath(html_path), None


def generate_pdf(
    html_path: str | os.PathLike[str],
    pdf_path: str | os.PathLike[str],
    footer_text: str | None = None,
    *,
    language: str = "en",
) -> None:
    """Print a local HTML file to an A4 PDF with headless Chromium.

    Parameters
    ----------
    html_path : str or os.PathLike
        HTML file to print; relative resources (images, CSS) are resolved
        against its folder.
    pdf_path : str or os.PathLike
        PDF file to write.
    footer_text : str or None, optional
        If given, every page gets a footer with this text on the left and the
        page number (``Page x of y``) on the right.
    language : str, optional
        Language of the page-number text.

    Raises
    ------
    RuntimeError
        If Playwright or a Chromium-based browser is not available.
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            'PDF export needs Playwright: pip install "groundmeas[pdf]", then run '
            "`gm-cli towers install-browser` (or use --no-pdf for HTML protocols)"
        ) from exc

    margin = {"top": "0.5in", "right": "0.5in", "bottom": "0.5in", "left": "0.5in"}
    options: dict[str, Any] = {
        "path": os.fspath(pdf_path),
        "format": "A4",
        "margin": margin,
        "print_background": True,
    }
    if footer_text:
        page_text = translate(
            "page_footer",
            language,
            page='<span class="pageNumber"></span>',
            pages='<span class="totalPages"></span>',
        )
        margin["bottom"] = "0.7in"
        options["display_header_footer"] = True
        options["header_template"] = "<span></span>"
        options["footer_template"] = (
            '<div style="font-size:8px; color:#52514e; width:100%; padding:0 0.5in; '
            'display:flex; justify-content:space-between; font-family:system-ui, sans-serif;">'
            f"<span>{footer_text}</span><span>{page_text}</span></div>"
        )

    with sync_playwright() as playwright:
        browser = _launch_browser(playwright, PlaywrightError)
        try:
            page = browser.new_page()
            page.goto(file_uri(html_path), wait_until="load")
            page.pdf(**options)
        finally:
            browser.close()


def _launch_browser(playwright: Any, error_type: type[Exception]) -> Any:
    """Start a Chromium-based browser for printing.

    Order: the browser named in `BROWSER_ENV_VAR` (an executable path or
    a channel such as ``chrome`` or ``msedge``), Playwright's own Chromium,
    then an installed Google Chrome or Microsoft Edge.
    """
    choice = (
        os.environ.get(BROWSER_ENV_VAR, "").strip()
        or os.environ.get(LEGACY_BROWSER_ENV_VAR, "").strip()
    )
    if choice:
        if choice in _CHANNELS:
            return playwright.chromium.launch(channel=choice)
        return playwright.chromium.launch(executable_path=choice)
    try:
        return playwright.chromium.launch()
    except error_type as exc:
        if "Executable doesn't exist" not in str(exc):
            raise
        for channel in ("chrome", "msedge"):
            try:
                browser = playwright.chromium.launch(channel=channel)
            except error_type:
                continue
            logger.info(
                "Playwright Chromium not installed; printing with the %s browser.",
                channel,
            )
            return browser
        raise RuntimeError(
            "No Chromium-based browser found for the PDF export. Run "
            "`gm-cli towers install-browser`, install Google Chrome or "
            f"Microsoft Edge, or set {BROWSER_ENV_VAR} to the path of a Chromium-based browser "
            "(use --no-pdf to create HTML protocols only)."
        ) from exc


def install_browser() -> int:
    """Download Playwright's Chromium into the shared Playwright browser cache.

    Runs ``python -m playwright install chromium`` with the interpreter of this
    installation, so it also works for isolated installs (``pipx``,
    ``uv tool``) where the ``playwright`` command is not on the ``PATH``.

    Returns
    -------
    int
        Exit code of the Playwright installer; ``1`` if Playwright (the
        ``pdf`` extra) is not installed.
    """
    if importlib.util.find_spec("playwright") is None:
        logger.error(
            'Playwright is not installed: pip install "groundmeas[pdf]" (or use '
            "--no-pdf for HTML protocols)"
        )
        return 1
    command = [sys.executable, "-m", "playwright", "install", "chromium"]
    logger.info("Running: %s", " ".join(command))
    return subprocess.call(command)


def zip_pdfs(
    source_directory: str | os.PathLike[str], zip_file_path: str | os.PathLike[str]
) -> int:
    """Pack every PDF below ``source_directory`` into ``zip_file_path``.

    Parameters
    ----------
    source_directory : str or os.PathLike
        Folder to search (recursively).
    zip_file_path : str or os.PathLike
        Archive to create (overwritten if it exists).

    Returns
    -------
    int
        Number of PDF files added. Archive member names are relative paths
        with ``/`` separators on every operating system.
    """
    ensure_directory(Path(zip_file_path).parent)
    number_of_pdfs = 0
    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_directory):
            dirs.sort()
            for file in sorted(files):
                if file.lower().endswith(".pdf"):
                    full_path = os.path.join(root, file)
                    arcname = Path(
                        os.path.relpath(full_path, source_directory)
                    ).as_posix()
                    zipf.write(full_path, arcname)
                    number_of_pdfs += 1
    logger.info("Created %d protocols in: %s", number_of_pdfs, zip_file_path)
    return number_of_pdfs
