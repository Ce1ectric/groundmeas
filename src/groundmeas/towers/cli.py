"""
groundmeas.towers.cli
=====================

``gm-cli towers`` — evaluate measurement campaigns of overhead-line towers.

Steps of ``gm-cli towers run`` (they run in this order when several are
given):

    --calc    evaluate all measurements -> JSON per tower + Excel summary
    --print   diagrams + protocol (HTML/PDF) per tower
    --zip     pack the PDF protocols into one archive
    --stats   statistics report over all towers (German)

Without a step option ``--calc --print --zip`` is run. Examples::

    gm-cli towers demo demo
    gm-cli towers run --config demo/config.json
    gm-cli towers run --config campaign/config.json --print --worker 4
    gm-cli towers run --config campaign/config.json --print --no-pdf
    gm-cli towers flatten delivery/ measurements/ --apply --report mapping.csv

Exit codes: ``0`` success, ``1`` processing error, ``2`` invalid usage or
configuration.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional

import typer

from .config import (
    CONFIG_ENV_VAR,
    ConfigError,
    resolve_config_path,
    write_example_config,
)
from .flatten import (
    DEFAULT_LINE_PATTERN,
    DEFAULT_TOWER_PATTERN,
    apply_flatten,
    plan_flatten,
)

__all__ = ["STEPS", "app", "configure_logging", "run_steps"]

logger = logging.getLogger("groundmeas")

STEPS = ("calc", "print", "zip", "stats")
"""Steps in execution order."""

app = typer.Typer(
    help=(
        "Evaluate earthing measurements of overhead-line towers (OMICRON COMPANO 100 "
        "and HGT1): earthing impedance, touch and step voltages, assessment against the "
        "permissible touch voltage, JSON/Excel results and PDF protocols."
    ),
    no_args_is_help=True,
)


def configure_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Send the package's log messages to the console.

    Parameters
    ----------
    verbose : bool, optional
        Show debug messages.
    quiet : bool, optional
        Show warnings and errors only.
    """
    level = logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    logger.handlers[:] = [handler]
    logger.setLevel(level)
    logger.propagate = False


def run_steps(
    steps: List[str],
    *,
    worker: int = 1,
    print_pdf: bool = True,
) -> None:
    """Run campaign steps in pipeline order with the active configuration.

    Parameters
    ----------
    steps : list of str
        Subset of `STEPS`; an empty list runs ``calc``, ``print`` and ``zip``
        (without ``zip`` if ``print_pdf`` is false).
    worker : int, optional
        Parallel processes for the ``print`` step.
    print_pdf : bool, optional
        Create PDF files (``print``, ``stats``); ``False`` writes HTML only.
    """
    # imported lazily: --help and the demo stay fast
    from .campaign import calculate_summary
    from .protocol import print_protocol, zip_protocols
    from .stats import generate_asset_report

    selected = [step for step in STEPS if step in steps]
    if not selected:
        selected = ["calc", "print", "zip"] if print_pdf else ["calc", "print"]
    for step in selected:
        logger.info("--- %s ---", step)
        if step == "calc":
            calculate_summary()
        elif step == "print":
            print_protocol(worker_count=worker, print_pdf=print_pdf)
        elif step == "zip":
            zip_protocols()
        elif step == "stats":
            generate_asset_report(print_pdf=print_pdf)


def _activate_config(config: Optional[Path]) -> str:
    config_path = resolve_config_path(config)
    if not os.path.isfile(config_path):
        typer.echo(
            f"Error: configuration file not found: {config_path} "
            "(use --config PATH; create an example with `gm-cli towers demo DIR`)",
            err=True,
        )
        raise typer.Exit(code=2)
    # inherited by the worker processes of the print step
    os.environ[CONFIG_ENV_VAR] = config_path
    logger.info("Using configuration %s", config_path)
    return config_path


_CONFIG_OPTION = typer.Option(
    None,
    "--config",
    "-c",
    help=f"Campaign configuration (default: ${CONFIG_ENV_VAR} or ./config.json)",
)
_VERBOSE_OPTION = typer.Option(False, "--verbose", "-v", help="Show debug messages")
_QUIET_OPTION = typer.Option(
    False, "--quiet", "-q", help="Show warnings and errors only"
)


@app.command("run")
def cli_run(
    calc: bool = typer.Option(
        False, "--calc", help="Evaluate all measurements (JSON + Excel)"
    ),
    print_: bool = typer.Option(
        False, "--print", help="Create diagrams and protocols per tower"
    ),
    zip_: bool = typer.Option(
        False, "--zip", help="Pack the PDF protocols into one archive"
    ),
    stats: bool = typer.Option(
        False, "--stats", help="Statistics report over all towers (German)"
    ),
    config: Optional[Path] = _CONFIG_OPTION,
    worker: int = typer.Option(
        1, "--worker", min=1, help="Parallel processes for --print"
    ),
    no_pdf: bool = typer.Option(
        False, "--no-pdf", help="Write HTML only (no Chromium needed)"
    ),
    verbose: bool = _VERBOSE_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Evaluate a campaign: calc, print, zip and stats steps.

    Without a step option --calc --print --zip is run (--calc --print with
    --no-pdf).
    """
    if verbose and quiet:
        typer.echo("Error: --verbose and --quiet exclude each other", err=True)
        raise typer.Exit(code=2)
    configure_logging(verbose=verbose, quiet=quiet)
    _activate_config(config)
    steps = [
        name
        for name, flag in (
            ("calc", calc),
            ("print", print_),
            ("zip", zip_),
            ("stats", stats),
        )
        if flag
    ]
    try:
        run_steps(steps, worker=worker, print_pdf=not no_pdf)
    except (ConfigError, FileNotFoundError) as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=2)
    except (PermissionError, RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=1)


@app.command("demo")
def cli_demo(
    directory: Path = typer.Argument(..., help="Folder to create"),
    language: str = typer.Option(
        "en", "--language", "-l", help="Language of the demo campaign (en or de)"
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Write into a non-empty folder"
    ),
) -> None:
    """Create a synthetic demo campaign (measurement files, workbooks, config)."""
    from .demo import write_demo_campaign

    configure_logging()
    try:
        demo_config = write_demo_campaign(
            directory, language=language, overwrite=overwrite
        )
    except (FileExistsError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2)
    logger.info("Demo campaign written to %s", demo_config.parent)
    logger.info("Run it with: gm-cli towers run --config %s", demo_config)


@app.command("example-config")
def cli_example_config(
    path: Path = typer.Argument(Path("config.json"), help="File to write"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace the file"),
) -> None:
    """Write an example campaign configuration to adapt."""
    try:
        target = write_example_config(path, overwrite=overwrite)
    except FileExistsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"Example configuration written to {target}")


@app.command("install-browser")
def cli_install_browser() -> None:
    """Download Playwright's Chromium for the PDF protocols."""
    from .pdf import install_browser

    configure_logging()
    code = install_browser()
    if code:
        raise typer.Exit(code=code)


def _check_pattern(option: str, pattern: str) -> None:
    """Exit with code 2 unless ``pattern`` compiles and has a capture group."""
    try:
        groups = re.compile(pattern).groups
    except re.error as exc:
        typer.echo(
            f"Error: {option} is not a valid regular expression: {exc}", err=True
        )
        raise typer.Exit(code=2)
    if groups < 1:
        typer.echo(f"Error: {option} needs one capture group: {pattern}", err=True)
        raise typer.Exit(code=2)


@app.command("flatten")
def cli_flatten(
    src_root: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        help="Root folder of the nested delivery (<line>/<tower folder>/...)",
    ),
    dest_flat: Path = typer.Argument(
        ..., help="Flat measurement folder (created if needed)"
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Copy the files (default: dry run)"
    ),
    report: Optional[Path] = typer.Option(
        None, "--report", help="Append the mapping to this CSV file (with --apply)"
    ),
    only: Optional[List[str]] = typer.Option(
        None,
        "--only",
        help="Restrict to this tower folder, relative to SRC_ROOT (repeatable)",
    ),
    line_pattern: str = typer.Option(
        DEFAULT_LINE_PATTERN,
        "--line-pattern",
        help="Regex with one group for the line folder",
    ),
    tower_pattern: str = typer.Option(
        DEFAULT_TOWER_PATTERN,
        "--tower-pattern",
        help="Regex with one group for the tower folder",
    ),
    map_strip: str = typer.Option(
        "LH-",
        "--map-strip",
        help="Prefix removed from the line in map file names ('' keeps the line)",
    ),
) -> None:
    """Copy a nested delivery (one folder per line and tower) into a flat folder.

    Line and tower are taken from the folder names, so typos in delivered
    file names are corrected. Without --apply only the plan is printed.
    Exits with 1 (and copies nothing) if two files map to the same name.
    """
    _check_pattern("--line-pattern", line_pattern)
    _check_pattern("--tower-pattern", tower_pattern)
    configure_logging()
    rows = plan_flatten(
        src_root,
        only=only or None,
        line_pattern=line_pattern,
        tower_pattern=tower_pattern,
        map_strip=map_strip,
    )
    for row in rows:
        if row["renamed"] == "yes" or row["reason"]:
            rel = Path(row["src"]).relative_to(src_root).as_posix()
            typer.echo(f"{rel} -> {row['dst']}  [{row['reason']}]")
    n_files = sum(1 for row in rows if row["dst"])
    n_renamed = sum(1 for row in rows if row["renamed"] == "yes")
    n_conflicts = sum(1 for row in rows if "CONFLICT" in row["reason"])
    typer.echo(f"{n_files} files, {n_renamed} renamed, {n_conflicts} conflicts")
    if n_conflicts:
        typer.echo("Aborted because of name conflicts.", err=True)
        raise typer.Exit(code=1)
    if not apply:
        typer.echo("Dry run: nothing copied (use --apply).")
        return
    copied = apply_flatten(rows, src_root, dest_flat, report=report)
    typer.echo(f"{copied} files copied to {dest_flat}")
