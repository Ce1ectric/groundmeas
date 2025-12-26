import subprocess
import re
import sys
from pathlib import Path
import typer
from rich.console import Console
from rich.prompt import Prompt

app = typer.Typer()
console = Console()

def run_command(command: str, shell: bool = False):
    try:
        result = subprocess.run(
            command, 
            shell=shell, 
            check=True, 
            text=True, 
            capture_output=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error running command:[/bold red] {command}")
        console.print(e.stderr)
        sys.exit(1)

@app.command()
def release():
    """
    Interactive release script:
    1. Asks for version bump type (major, minor, patch).
    2. Bumps version in pyproject.toml, __init__.py, and CITATION.cff.
    3. Runs tests.
    4. Commits, tags, and pushes to remote.
    """
    console.print("[bold green]Starting Release Process...[/bold green]")

    # 1. Ask for version bump
    bump_type = Prompt.ask(
        "Select version bump type", 
        choices=["patch", "minor", "major"], 
        default="patch"
    )

    # 2. Bump version using poetry
    console.print(f"Bumping version ({bump_type})...")
    run_command(f"poetry version {bump_type}", shell=True)
    
    # Get new version
    new_version = run_command("poetry version --short", shell=True)
    console.print(f"[bold blue]New version:[/bold blue] {new_version}")

    # 3. Update __init__.py
    init_file = Path("src/groundmeas/__init__.py")
    content = init_file.read_text()
    
    # Regex to replace __version__ = "..."
    new_content = re.sub(
        r'__version__ = "[^"]+"', 
        f'__version__ = "{new_version}"', 
        content
    )
    
    if content == new_content:
        console.print("[yellow]Warning: Could not update __version__ in __init__.py (pattern not found?)[/yellow]")
    else:
        init_file.write_text(new_content)
        console.print(f"Updated {init_file}")

    # 3b. Update CITATION.cff version
    citation_file = Path("CITATION.cff")
    if citation_file.exists():
        cit_content = citation_file.read_text()
        new_cit = re.sub(r"^version:\\s*.*$", f"version: {new_version}", cit_content, flags=re.MULTILINE)
        if cit_content == new_cit:
            console.print("[yellow]Warning: Could not update version in CITATION.cff (pattern not found?).[/yellow]")
        else:
            citation_file.write_text(new_cit)
            console.print(f"Updated {citation_file}")
    else:
        console.print("[yellow]Warning: CITATION.cff not found.[/yellow]")

    # 4. Run tests
    console.print("[bold green]Running tests...[/bold green]")
    try:
        # Run pytest directly
        subprocess.run(["pytest"], check=True)
        console.print("[bold green]Tests passed![/bold green]")
    except subprocess.CalledProcessError:
        console.print("[bold red]Tests failed! Aborting release.[/bold red]")
        # Revert changes? (Optional, but good practice would be to git checkout .)
        sys.exit(1)

    # 5. Git operations
    if Prompt.ask("Commit and Push?", choices=["y", "n"], default="y") == "y":
        run_command("git add pyproject.toml src/groundmeas/__init__.py CITATION.cff", shell=True)
        run_command(f'git commit -m "chore: bump version to {new_version}"', shell=True)
        run_command(f"git tag v{new_version}", shell=True)
        
        console.print("[bold green]Pushing to origin...[/bold green]")
        # Push current branch and tags
        run_command("git push origin HEAD --tags", shell=True)
        
        console.print(f"[bold green]Successfully released v{new_version}![/bold green]")
        console.print("GitHub Actions will now handle the deployment to PyPI.")
    else:
        console.print("[yellow]Aborted git push.[/yellow]")

if __name__ == "__main__":
    app()
