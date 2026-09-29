"""Regenerate the dependency table in docs/LICENSES.md from installed package metadata.

Usage: uv run python scripts/licenses.py [--check]
--check exits 1 when docs/LICENSES.md is out of date (used by the test suite).
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, metadata, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "LICENSES.md"
BEGIN, END = "<!-- BEGIN GENERATED -->", "<!-- END GENERATED -->"

USED_FOR = {
    "numpy": "arrays",
    "scipy": "sparse solvers, spatial queries",
    "scikit-image": "marching cubes on the SDF grid",
    "trimesh": "mesh I/O",
    "libigl": "SLIM/ARAP parameterisation, winding numbers, cut_mesh",
    "potpourri3d": "geodesic paths (geometry-central)",
    "cadquery-ocp": "STEP/IGES import (OpenCascade)",
    "manifold3d": "mesh booleans and repair",
    "pymeshlab": "remeshing, repair filters",
    "shapely": "2D offsets",
    "ezdxf": "DXF read and write",
    "ruamel.yaml": "parameter file (config/defaults.yaml)",
    "matplotlib": "DXF preview renders, plots",
    "fastapi": "API (M6)",
    "uvicorn": "API server (M6)",
    "pytest": "tests (dev)",
    "ruff": "lint and format (dev)",
    "mypy": "type checks (dev)",
    "pre-commit": "commit hooks (dev)",
}

# Facts the package metadata does not tell.
NOTES = {
    "cadquery-ocp": (
        "bindings Apache-2.0; bundles OpenCascade (LGPL-2.1 with exception) and VTK (BSD)"
    ),
    "pymeshlab": "GPL-3.0: fine for internal use (ADR-013); review before distributing",
}

_SPDX_SHORT = re.compile(r"^[A-Za-z0-9.\-+ ()]{1,40}$")


def direct_dependencies() -> list[str]:
    names: list[str] = []
    engine = tomllib.loads((ROOT / "engine" / "pyproject.toml").read_text())["project"]
    root = tomllib.loads((ROOT / "pyproject.toml").read_text())
    specs = list(engine["dependencies"])
    for extra in engine.get("optional-dependencies", {}).values():
        specs += extra
    for group in root.get("dependency-groups", {}).values():
        specs += group
    for spec in specs:
        name = re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0]
        if name not in names:
            names.append(name)
    return names


def licence_of(name: str) -> str:
    m = metadata(name)
    expr = m.get("License-Expression")
    if expr:
        return expr
    lic = (m.get("License") or "").strip()
    if lic and _SPDX_SHORT.match(lic):
        return lic
    classifiers = [
        c.split(" :: ")[-1] for c in m.get_all("Classifier") or [] if c.startswith("License ::")
    ]
    return ", ".join(classifiers) or "see package"


def table() -> str:
    rows = ["| Package | Version | Licence | Used for | Note |", "|---|---|---|---|---|"]
    for name in direct_dependencies():
        try:
            ver, lic = version(name), licence_of(name)
        except PackageNotFoundError:
            ver, lic = "not installed", "?"
        rows.append(
            f"| {name} | {ver} | {lic} | {USED_FOR.get(name, '')} | {NOTES.get(name, '')} |"
        )
    return "\n".join(rows)


def render(doc: str) -> str:
    if BEGIN not in doc or END not in doc:
        raise SystemExit(f"{DOC}: markers {BEGIN} / {END} missing")
    head, rest = doc.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{BEGIN}\n{table()}\n{END}{tail}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    current = DOC.read_text()
    new = render(current)
    if args.check:
        if new != current:
            print("docs/LICENSES.md is out of date: run uv run python scripts/licenses.py")
            return 1
        return 0
    DOC.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
