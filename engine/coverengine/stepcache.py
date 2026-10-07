"""Only what changed is calculated again (ADR-080).

The team (6 Oct 2026): "with so many functions, every improvement recalculates so much". Each
step (hull, cut, flatten, export) leaves a stamp in <model>/steps/<step>.json:

- the parameters the step actually read while it ran (measured, not guessed: a step that never
  looks at `features.*` does not depend on it), with their values;
- the hash of every file it reads from the step before (and of cover.json without its catalogue
  notes and status);
- the hash of the engine's own code, so a new release calculates again.

The next run of that step compares: when nothing it depends on changed and its outputs are
there, it skips itself ("unchanged, skipped"). `--force` always calculates. A step written into
another folder (`--out`) is never skipped.

What the stamp records is what the step read; parameters copied whole into a file for the
record (the full parameter set in pattern.json) do not count as read, so pattern.json keeps the
record of the run that made its geometry.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from coverengine.params import EffectiveParams

STEPS_DIR = "steps"
# what each step reads from the steps before it, and what it must leave behind
INPUTS = {
    "hull": ("model.glb", "parts.json", "kind.json", "cover.json", "arrangement.json"),
    "cut": (
        "hull.glb",
        "hull.json",
        "hull_parts.npy",
        "seams.json",
        "proposals.json",
        "part_edits.json",  # the Desk's seam corrections (ADR-082)
        "cover.json",
    ),
    "flatten": ("panels.npz", "panels.json", "cover.json"),
    "export": ("pattern.json", "cover.json"),
}
OUTPUTS = {
    "hull": ("hull.glb", "hull.json"),
    "cut": ("panels.npz", "panels.json"),
    "flatten": ("pattern.json",),
    "export": ("finished.json", "cut.dxf"),
}
# what in cover.json is not compared as a file: the catalogue notes no step reads (the Desk and
# the catalogue change them often), and the parameters, compared value by value as they are read
NOT_INPUTS = ("status", "tags", "notes", "info", "parameters")

_engine_hash: str | None = None


def engine_hash() -> str:
    """The engine's own code: a change of code is a change of every step."""
    global _engine_hash
    if _engine_hash is None:
        root = Path(__file__).resolve().parent
        h = hashlib.sha256()
        for p in sorted(root.rglob("*.py")):
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
        _engine_hash = h.hexdigest()
    return _engine_hash


def _file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    if path.name == "cover.json":
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        doc = {k: v for k, v in doc.items() if k not in NOT_INPUTS}
        return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(step: str, model_dir: Path) -> dict[str, str | None]:
    return {name: _file_hash(model_dir / name) for name in INPUTS[step]}


def _value(params: EffectiveParams, key: str) -> Any:
    try:
        return params.peek(key)
    except KeyError:
        return "<gone>"


def unchanged(step: str, model_dir: Path, params: EffectiveParams) -> bool:
    """True when the step's stamp matches: same code, same input files, same values of every
    parameter it read last time, and its outputs are there."""
    stamp = model_dir / STEPS_DIR / f"{step}.json"
    if step not in INPUTS or not stamp.is_file():
        return False
    if not all((model_dir / name).is_file() for name in OUTPUTS[step]):
        return False
    try:
        doc = json.loads(stamp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if doc.get("engine") != engine_hash() or doc.get("files") != _files(step, model_dir):
        return False
    read = doc.get("params") or {}
    return all(_value(params, k) == v for k, v in read.items())


def write(step: str, model_dir: Path, params: EffectiveParams, read: set[str]) -> None:
    folder = model_dir / STEPS_DIR
    folder.mkdir(exist_ok=True)
    doc = {
        "step": step,
        "engine": engine_hash(),
        "files": _files(step, model_dir),
        "params": {k: _value(params, k) for k in sorted(read)},
    }
    tmp = folder / f"{step}.tmp"
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(folder / f"{step}.json")


def forget(model_dir: Path, steps: tuple[str, ...] = tuple(INPUTS)) -> None:
    """Drop the stamps: the next run calculates these steps again."""
    for step in steps:
        (model_dir / STEPS_DIR / f"{step}.json").unlink(missing_ok=True)


@contextmanager
def reading() -> Iterator[set[str]]:
    """While inside: every parameter a step reads is noted in the yielded set."""
    seen: set[str] = set()
    before = EffectiveParams.track
    EffectiveParams.track = seen
    try:
        yield seen
    finally:
        EffectiveParams.track = before
