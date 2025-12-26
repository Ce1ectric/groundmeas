"""
Simple license reporter for installed distributions with compatibility hints.

Usage
-----
poetry run python scripts/license_check.py

What it does
------------
- Reads installed distributions (current environment).
- Prints name, version, license, and a heuristic compatibility status (MIT baseline).
- Flags missing license info as "UNKNOWN".
- Summarizes normalized license tokens and highlights GPL/AGPL/LGPL.
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Dict, List, Tuple

IGNORE_PACKAGES = {"groundmeas"}


def _license_for(dist: md.Distribution) -> str:
    lic = dist.metadata.get("License") or dist.metadata.get("license") or ""
    if lic:
        return lic.strip()
    classifiers = [
        c for c in dist.metadata.get_all("Classifier", []) if c.startswith("License")
    ]
    return "; ".join(classifiers) if classifiers else "UNKNOWN"


def collect() -> List[Tuple[str, str, str]]:
    """Collect (name, version, license) for all installed distributions except ignored."""
    rows: List[Tuple[str, str, str]] = []
    for dist in md.distributions():
        name = dist.metadata["Name"]
        if name and name.lower() in IGNORE_PACKAGES:
            continue
        version = dist.version
        license_str = _license_for(dist)
        rows.append((name, version, license_str))
    rows.sort(key=lambda r: r[0].lower())
    return rows


def _normalize_token(raw: str) -> str:
    token = raw.lower().strip()
    if "mit" in token:
        return "MIT"
    if "apache" in token:
        return "Apache-2.0"
    if "bsd" in token:
        return "BSD"
    if "mpl" in token:
        return "MPL"
    if "isc" in token:
        return "ISC"
    if "lgpl" in token:
        return "LGPL"
    if "gpl" in token and "agpl" not in token:
        return "GPL"
    if "agpl" in token:
        return "AGPL"
    if "public domain" in token or "unlicense" in token:
        return "Public-Domain"
    return raw.strip() or "UNKNOWN"


def _compatibility(tokens: List[str]) -> str:
    """
    Rough MIT-compatibility heuristic.

    Priority: NOT_COMPATIBLE (GPL/AGPL) > REVIEW (MPL/LGPL) > COMPATIBLE > UNKNOWN.
    """
    compat_set = {"MIT", "BSD", "Apache-2.0", "ISC", "Public-Domain"}
    review_set = {"MPL", "LGPL"}
    incompatible_set = {"GPL", "AGPL"}
    norms = [_normalize_token(t) for t in tokens]
    if any(t in incompatible_set for t in norms):
        return "NOT_COMPATIBLE (GPL/AGPL)"
    if any(t in review_set for t in norms):
        return "REVIEW (MPL/LGPL)"
    if any(t in compat_set for t in norms):
        return "COMPATIBLE"
    return "UNKNOWN"


def main() -> None:
    rows = collect()
    print(f"{'Package':<30} {'Version':<12} {'License':<30} Compatibility")
    print("-" * 120)
    unknown = 0
    buckets: Dict[str, int] = {}
    non_permissive: Dict[str, List[str]] = {}
    compat_counts: Dict[str, int] = {}
    compat_pkgs: Dict[str, List[str]] = {}
    for name, version, lic in rows:
        if lic == "UNKNOWN":
            unknown += 1
            buckets["UNKNOWN"] = buckets.get("UNKNOWN", 0) + 1
        tokens = [tok.strip() for tok in lic.split(";") if tok.strip()] or ["UNKNOWN"]
        for tok in tokens:
            norm = _normalize_token(tok)
            buckets[norm] = buckets.get(norm, 0) + 1
            if norm in {"GPL", "AGPL", "LGPL"}:
                non_permissive.setdefault(norm, []).append(name)
        comp = _compatibility(tokens)
        compat_counts[comp] = compat_counts.get(comp, 0) + 1
        compat_pkgs.setdefault(comp, []).append(name)
        print(f"{name:<30} {version:<12} {lic:<30} {comp}")
    print("-" * 120)
    print(f"Total packages: {len(rows)} | Unknown licenses: {unknown}")
    print("License summary (normalized):")
    for lic, count in sorted(buckets.items(), key=lambda kv: kv[0].lower()):
        print(f"  {lic}: {count}")
    print("Compatibility (heuristic relative to MIT):")
    for status, count in sorted(compat_counts.items(), key=lambda kv: kv[0]):
        print(f"  {status}: {count}")
    if non_permissive:
        print("Potentially non-permissive or weak-copyleft licenses detected:")
        for lic, pkgs in non_permissive.items():
            print(f"  {lic}: {', '.join(sorted(pkgs))}")
    if compat_pkgs.get("NOT_COMPATIBLE (GPL/AGPL)"):
        print("Review/replace (GPL/AGPL):", ", ".join(sorted(compat_pkgs["NOT_COMPATIBLE (GPL/AGPL)"])))
    if compat_pkgs.get("REVIEW (MPL/LGPL)"):
        print("Review conditions (MPL/LGPL):", ", ".join(sorted(compat_pkgs["REVIEW (MPL/LGPL)"])))
    if compat_pkgs.get("UNKNOWN"):
        print("Missing/unknown license metadata:", ", ".join(sorted(compat_pkgs["UNKNOWN"])))
    print("Note: This is a heuristic; consult legal counsel for definitive guidance.")


if __name__ == "__main__":
    main()
