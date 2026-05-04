# scripts/release.py
"""
Interactive release script for `groundmeas`.

Bumps the version in ``pyproject.toml``, ``src/groundmeas/__init__.py``
and ``CITATION.cff``, moves the ``[Unreleased]`` block in
``CHANGELOG.md`` into a dated version section (delegated to
``scripts._changelog.bump_changelog``), regenerates third-party notices,
runs the test suite and finally creates the release commit, tag and
push.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Prompt

# Local stdlib-only helpers (no typer / rich dependency, easy to test).
try:
    from scripts._changelog import bump_changelog
except ImportError:  # pragma: no cover — fallback when run as a script
    import importlib.util

    _here = Path(__file__).resolve().parent
    _spec = importlib.util.spec_from_file_location(
        "_groundmeas_release_changelog", _here / "_changelog.py"
    )
    assert _spec is not None and _spec.loader is not None
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    bump_changelog = _mod.bump_changelog


app = typer.Typer()
console = Console()


# ---------------------------------------------------------------------------
# Shell helper
# ---------------------------------------------------------------------------


def run_command(command: str, shell: bool = False) -> str:
    """Run a shell command and return stripped stdout, abort on failure."""
    try:
        result = subprocess.run(
            command,
            shell=shell,
            check=True,
            text=True,
            capture_output=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error running command:[/bold red] {command}")
        console.print(e.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Version bookkeeping in CITATION.cff
# ---------------------------------------------------------------------------


def update_citation_version(citation_file: Path, new_version: str) -> bool:
    """
    Update the ``version:`` field inside ``CITATION.cff``.

    Matches lines that start with ``version:`` (with optional whitespace
    and quotes) while avoiding the ``cff-version`` header.

    Parameters
    ----------
    citation_file : Path
        Path to the ``CITATION.cff`` file.
    new_version : str
        The version string to write (without leading ``v``).

    Returns
    -------
    bool
        ``True`` if a line was substituted, ``False`` otherwise.
    """
    content = citation_file.read_text()
    pattern = re.compile(r"(?m)^\s*version:\s*[\"']?[^\"'\n]*[\"']?\s*$")
    new_line = f"version: {new_version}"

    updated_content, count = pattern.subn(new_line, content, count=1)
    if count == 0:
        return False

    if not updated_content.endswith("\n"):
        updated_content += "\n"
    citation_file.write_text(updated_content)
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@app.command()
def release(
    allow_empty: bool = typer.Option(
        False,
        "--allow-empty",
        help="Allow releasing with an empty CHANGELOG.md [Unreleased] block.",
    ),
) -> None:
    """
    Interactive release entry point.

    Steps:

    1. Ask for the version bump type (``major``/``minor``/``patch``).
    2. Bump the version in ``pyproject.toml``, ``__init__.py`` and
       ``CITATION.cff``.
    3. Move the ``[Unreleased]`` block in ``CHANGELOG.md`` into a dated
       section and refresh the compare links.
    4. Regenerate the third-party notices.
    5. Run the test suite.
    6. Commit, tag and push.
    """
    console.print("[bold green]Starting Release Process...[/bold green]")

    # 1. Ask for version bump
    bump_type = Prompt.ask(
        "Select version bump type",
        choices=["patch", "minor", "major"],
        default="patch",
    )

    # 2. Bump version using poetry
    console.print(f"Bumping version ({bump_type})...")
    run_command(f"poetry version {bump_type}", shell=True)
    new_version = run_command("poetry version --short", shell=True)
    console.print(f"[bold blue]New version:[/bold blue] {new_version}")

    # 3a. Update __init__.py
    init_file = Path("src/groundmeas/__init__.py")
    content = init_file.read_text()
    new_content = re.sub(
        r'__version__ = "[^"]+"',
        f'__version__ = "{new_version}"',
        content,
    )
    if content == new_content:
        console.print(
            "[yellow]Warning: Could not update __version__ in "
            "__init__.py (pattern not found?)[/yellow]"
        )
    else:
        init_file.write_text(new_content)
        console.print(f"Updated {init_file}")

    # 3b. Update CITATION.cff
    citation_file = Path("CITATION.cff")
    if citation_file.exists():
        if update_citation_version(citation_file, new_version):
            console.print(f"Updated {citation_file}")
        else:
            console.print(
                "[yellow]Warning: Could not update version in "
                "CITATION.cff (version key not found).[/yellow]"
            )
        # Validate the CFF file via cffconvert if available. We treat a
        # missing tool as a soft warning (CI catches this anyway), but
        # an actual validation failure is hard-fail — a broken
        # CITATION.cff blocks Zenodo metadata extraction on release.
        try:
            subprocess.run(
                ["cffconvert", "--validate"],
                check=True,
                capture_output=True,
                text=True,
            )
            console.print("[bold green]CITATION.cff is valid.[/bold green]")
        except FileNotFoundError:
            console.print(
                "[yellow]Warning: 'cffconvert' not installed, "
                "skipping CITATION.cff validation.[/yellow]"
            )
        except subprocess.CalledProcessError as exc:
            console.print("[bold red]CITATION.cff validation failed:[/bold red]")
            if exc.stdout:
                console.print(exc.stdout)
            if exc.stderr:
                console.print(exc.stderr)
            sys.exit(1)
    else:
        console.print("[yellow]Warning: CITATION.cff not found.[/yellow]")

    # 3c. Move [Unreleased] block in CHANGELOG.md
    changelog_file = Path("CHANGELOG.md")
    if changelog_file.exists():
        try:
            bump_changelog(
                changelog_file,
                new_version=new_version,
                allow_empty=allow_empty,
            )
            console.print(f"Updated {changelog_file}")
        except RuntimeError as exc:
            console.print(f"[bold red]CHANGELOG bump failed:[/bold red] {exc}")
            sys.exit(1)
    else:
        console.print("[yellow]Warning: CHANGELOG.md not found.[/yellow]")

    # 3d. Regenerate third-party notices/licenses
    console.print("[bold green]Generating third-party notices...[/bold green]")
    try:
        subprocess.run(
            ["python", "scripts/generate_third_party_licenses.py"],
            check=True,
        )
        console.print("[bold green]Third-party notices updated.[/bold green]")
    except subprocess.CalledProcessError:
        console.print(
            "[bold red]Failed to generate third-party notices. "
            "Aborting release.[/bold red]"
        )
        sys.exit(1)

    # 4. Run tests
    console.print("[bold green]Running tests...[/bold green]")
    try:
        subprocess.run(["pytest"], check=True)
        console.print("[bold green]Tests passed![/bold green]")
    except subprocess.CalledProcessError:
        console.print("[bold red]Tests failed! Aborting release.[/bold red]")
        sys.exit(1)

    # 5. Git operations
    if Prompt.ask("Commit and Push?", choices=["y", "n"], default="y") == "y":
        run_command(
            "git add pyproject.toml src/groundmeas/__init__.py "
            "CITATION.cff CHANGELOG.md",
            shell=True,
        )
        run_command(
            f'git commit -m "chore: bump version to {new_version}"',
            shell=True,
        )
        run_command(f"git tag v{new_version}", shell=True)

        console.print("[bold green]Pushing to origin...[/bold green]")
        run_command("git push origin HEAD --tags", shell=True)

        console.print(f"[bold green]Successfully released v{new_version}![/bold green]")
        console.print("GitHub Actions will now handle the deployment to PyPI.")
    else:
        console.print("[yellow]Aborted git push.[/yellow]")


if __name__ == "__main__":
    app()
