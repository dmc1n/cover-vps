"""The catalogue (M7): each model's family, status, tags and notes (in its `cover.json`), its
pattern revisions, and comparing two pattern sets.

- Family: names a preset `config/presets/<family>.yaml` (parameter layer 2), so a change to a
  family applies to every model of it that does not set the value itself.
- Status: draft (being worked on), checked (patterns looked over), production (cut from).
- Revisions: every export keeps its pattern.json, finished.json, cut.dxf and the model's
  cover.json and seams.json in `revisions/<n>/`, listed in `revisions/index.json`.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from coverengine.errors import CoverError
from coverengine.params.registry import list_families, read_cover_definition

STATUSES = ("draft", "checked", "production")
REVISIONS = "revisions"
KEPT = ("pattern.json", "finished.json", "cut.dxf", "cover.json", "seams.json")
INFO_FIELDS = ("family", "status", "tags", "notes")


def info(model_dir: Path) -> dict[str, Any]:
    cover = read_cover_definition(model_dir)
    return {
        "family": cover.get("family"),
        "status": cover.get("status", "draft"),
        "tags": list(cover.get("tags", [])),
        "notes": cover.get("notes", ""),
    }


def set_info(model_dir: Path, changes: dict[str, Any]) -> dict[str, Any]:
    """Change family, status, tags or notes in the model's cover.json (everything else kept)."""
    unknown = set(changes) - set(INFO_FIELDS)
    if unknown:
        raise CoverError(f"unknown field(s): {', '.join(sorted(unknown))}")
    if "status" in changes and changes["status"] not in STATUSES:
        raise CoverError(f"status must be one of {', '.join(STATUSES)}")
    family = changes.get("family")
    if family and family not in list_families():
        raise CoverError(f"no family {family!r}; known: {', '.join(list_families()) or 'none yet'}")
    if "tags" in changes:
        changes["tags"] = sorted({str(t).strip() for t in changes["tags"] if str(t).strip()})
    path = model_dir / "cover.json"
    doc = read_cover_definition(model_dir) or {"format_version": 1, "model_id": model_dir.name}
    for key, value in changes.items():
        if value in (None, "", []) and key != "status":
            doc.pop(key, None)
        else:
            doc[key] = value
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return info(model_dir)


def revisions(model_dir: Path) -> list[dict[str, Any]]:
    index = model_dir / REVISIONS / "index.json"
    if not index.is_file():
        return []
    data: list[dict[str, Any]] = json.loads(index.read_text(encoding="utf-8"))
    return data


def save_revision(model_dir: Path, trial: dict[str, Any]) -> dict[str, Any]:
    """Keep this export as the next revision."""
    pattern = model_dir / "pattern.json"
    if not pattern.is_file():
        raise CoverError(f"no pattern.json in {model_dir}")
    listed = revisions(model_dir)
    number = (listed[-1]["number"] + 1) if listed else 1
    folder = model_dir / REVISIONS / f"{number:03d}"
    folder.mkdir(parents=True, exist_ok=True)
    for name in KEPT:
        if (model_dir / name).is_file():
            shutil.copyfile(model_dir / name, folder / name)
    doc = json.loads(pattern.read_text(encoding="utf-8"))
    finished_path = model_dir / "finished.json"
    finished = (
        json.loads(finished_path.read_text(encoding="utf-8")) if finished_path.is_file() else {}
    )
    entry = {
        "number": number,
        "time": round(time.time()),
        "parameter_hash": doc["parameter_hash"],
        "trial": sorted(trial),
        "status": info(model_dir)["status"],
        "panels": doc["summary"]["panels"],
        "max_stretch_pct": doc["summary"]["max_stretch_pct"],
        "roll_length_mm": (finished.get("sheet") or {}).get("roll_length_mm"),
        "warnings": len(doc.get("warnings", [])) + len(finished.get("warnings", [])),
    }
    listed.append(entry)
    (model_dir / REVISIONS / "index.json").write_text(
        json.dumps(listed, indent=2) + "\n", encoding="utf-8"
    )
    return entry


def revision_file(model_dir: Path, number: int, name: str) -> Path:
    if name not in KEPT:
        raise CoverError(f"a revision keeps only {', '.join(KEPT)}")
    return model_dir / REVISIONS / f"{number:03d}" / name


def _flat(tree: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in tree.items():
        if isinstance(v, dict):
            out.update(_flat(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def compare(a: dict[str, Any], b: dict[str, Any], threshold_mm: float = 1.0) -> dict[str, Any]:
    """What changed between two PatternSets: panels whose flat size moved more than the
    threshold (or that are new or gone), and the settings that differ."""
    pa = {p["name"]: p for p in a["panels"]}
    pb = {p["name"]: p for p in b["panels"]}
    panels = []
    for name in sorted(set(pa) | set(pb)):
        if name not in pa or name not in pb:
            panels.append({"name": name, "change": "new" if name in pb else "gone"})
            continue
        da = (pa[name]["flat_width_mm"], pa[name]["flat_length_mm"])
        db = (pb[name]["flat_width_mm"], pb[name]["flat_length_mm"])
        if max(abs(x - y) for x, y in zip(da, db, strict=True)) > threshold_mm:
            panels.append({"name": name, "change": "size", "before_mm": da, "after_mm": db})
    fa, fb = _flat(a.get("parameters", {})), _flat(b.get("parameters", {}))
    settings = [
        {"key": k, "before": fa.get(k), "after": fb.get(k)}
        for k in sorted(set(fa) | set(fb))
        if fa.get(k) != fb.get(k)
    ]
    return {"panels": panels, "settings": settings}


def compare_files(a: Path, b: Path, threshold_mm: float = 1.0) -> dict[str, Any] | None:
    if not a.is_file() or not b.is_file():
        return None
    return compare(
        json.loads(a.read_text(encoding="utf-8")),
        json.loads(b.read_text(encoding="utf-8")),
        threshold_mm,
    )
