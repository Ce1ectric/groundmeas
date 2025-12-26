#!/usr/bin/env python3
"""
Generate third-party license files using pip-licenses.

Outputs:
- THIRD_PARTY_NOTICES.md        (human-readable Markdown summary)
- THIRD_PARTY_LICENSES_RAW.txt  (full license texts for audit purposes)

Intended usage:
    poetry run python scripts/generate_third_party_licenses.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

FORBIDDEN_LICENSES = "GPL;LGPL;AGPL"
ROOT = Path(__file__).resolve().parents[1]
IGNORE_PACKAGES = ["groundmeas"]

MD_FILE = ROOT / "THIRD_PARTY_NOTICES.md"
RAW_FILE = ROOT / "THIRD_PARTY_LICENSES_RAW.txt"

def enforce_license_policy() -> None:
    """Fail if forbidden licenses are detected."""
    subprocess.run(
        [
            "pip-licenses",
            "--ignore-packages",
            ",".join(IGNORE_PACKAGES),
            "--fail-on",
            FORBIDDEN_LICENSES,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def run_pip_licenses_json() -> list[dict]:
    """Run pip-licenses and return parsed JSON output."""
    result = subprocess.run(
        [
            "pip-licenses",
            "--ignore-packages",
            ",".join(IGNORE_PACKAGES),
            "--format=json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def run_pip_licenses_raw() -> str:
    """Run pip-licenses with full license texts."""
    result = subprocess.run(
        [
            "pip-licenses",
            "--ignore-packages",
            ",".join(IGNORE_PACKAGES),
            "--with-license-file",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def write_markdown(packages: list[dict]) -> None:
    """Write a clean, human-readable Markdown summary."""
    lines = [
        "# Third-Party Notices",
        "",
        "This project makes use of the following third-party open-source software.",
        "",
        "| Package | Version | License |",
        "|--------|---------|---------|",
    ]

    for pkg in sorted(packages, key=lambda p: p["Name"].lower()):
        name = pkg["Name"]
        version = pkg["Version"]
        license_ = pkg["License"]
        lines.append(f"| {name} | {version} | {license_} |")

    lines += [
        "",
        "Full license texts are provided in `THIRD_PARTY_LICENSES_RAW.txt`.",
        "",
    ]

    MD_FILE.write_text("\n".join(lines), encoding="utf-8")


def write_raw(text: str) -> None:
    """Write full license texts to raw file."""
    RAW_FILE.write_text(text, encoding="utf-8")


def main() -> None:
    
    enforce_license_policy()
    packages = run_pip_licenses_json()
    raw_text = run_pip_licenses_raw()

    write_markdown(packages)
    write_raw(raw_text)

    print("Generated:")
    print(f" - {MD_FILE.name}")
    print(f" - {RAW_FILE.name}")


if __name__ == "__main__":
    main()
