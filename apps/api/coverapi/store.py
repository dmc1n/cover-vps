"""The data directory: `models/<id>/` exactly as the `cover` command writes it, uploads, jobs.

Everything the web app shows is read from these files, so the command line and the web app can
be used side by side on the same models.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coverengine.catalogue import compare_files, grade, info, revisions
from coverengine.params import Registry, resolve_model

# Files a model folder may hold, by step; the web app offers these for viewing and download.
STEP_FILES = {
    "import": ["model.glb", "model.json", "parts.json"],
    "hull": ["hull.glb", "hull.json", "preview.glb"],
    "cut": ["panels.glb", "panels.json", "seams.auto.json"],
    "flatten": ["pattern.json", "pattern.dxf", "pattern.svg", "pattern-stretch.svg", "sizes.pdf"],
    "export": ["finished.json", "cut.dxf", "cut.svg", "cutting-list.pdf"],
}
STEPS = list(STEP_FILES)
EXTRA_FILES = ["cover.json", "seams.json", "pattern.prev.json", "plan.png"]
ALLOWED = {f for files in STEP_FILES.values() for f in files} | set(EXTRA_FILES)
MEDIA = {
    ".glb": "model/gltf-binary",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".dxf": "application/dxf",
    ".png": "image/png",
}
UPLOAD_SUFFIXES = {".step", ".stp", ".iges", ".igs", ".stl", ".obj", ".ply", ".glb", ".gltf"}


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", Path(name).stem.lower()).strip("-")
    return s or "model"


@dataclass
class Store:
    root: Path

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def uploads(self) -> Path:
        return self.root / "uploads"

    @property
    def jobs(self) -> Path:
        return self.root / "jobs"

    def ensure(self) -> None:
        for d in (self.models, self.uploads, self.jobs):
            d.mkdir(parents=True, exist_ok=True)

    def model_dir(self, model_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", model_id):
            raise KeyError(model_id)
        return self.models / model_id

    def new_id(self, name: str) -> str:
        base = slug(name)
        model_id, n = base, 2
        while (self.models / model_id).exists() or (self.uploads / model_id).exists():
            model_id, n = f"{base}-{n}", n + 1
        return model_id

    def list_models(self) -> list[dict[str, Any]]:
        if not self.models.is_dir():
            return []
        ids = sorted(p.name for p in self.models.iterdir() if p.is_dir())
        return [self.summary(i, brief=True) for i in ids]

    def summary(self, model_id: str, brief: bool = False) -> dict[str, Any]:
        d = self.model_dir(model_id)
        if not d.is_dir():
            raise KeyError(model_id)
        files = sorted(f for f in ALLOWED if (d / f).is_file())
        done = [s for s in STEPS if all((d / f).is_file() for f in STEP_FILES[s][:1])]
        out: dict[str, Any] = {"id": model_id, "steps_done": done, "files": files}
        out.update(info(d))
        model = _read(d / "model.json")
        if model:
            out["size_mm"] = model.get("size_mm")
            out["source"] = (model.get("source") or {}).get("file")
        pattern = _read(d / "pattern.json")
        if pattern:
            out["panels"] = pattern["summary"]["panels"]
            out["max_stretch_pct"] = pattern["summary"]["max_stretch_pct"]
        warnings: list[str] = []
        for name in ("hull.json", "panels.json", "pattern.json", "finished.json"):
            warnings += (_read(d / name) or {}).get("warnings", [])
        out["warnings"] = warnings
        g = grade(d)
        out["grade"], out["reasons"] = g["grade"], g.get("reasons", [])
        if brief:
            return out
        hull = _read(d / "hull.json")
        panels = _read(d / "panels.json")
        finished = _read(d / "finished.json")
        out["model"] = model
        out["hull"] = (
            {k: hull[k] for k in ("area_m2", "hem", "drainage", "support")} if hull else None
        )
        if panels:
            out["cut"] = {
                "panels": panels["panels"],
                "seams": panels["seams"],
                "hem_length_mm": panels["hem_length_mm"],
                "skirt_height_mm": panels.get("skirt_height_mm"),
            }
        if pattern:
            out["pattern"] = {
                "summary": pattern["summary"],
                "panels": [
                    {
                        k: p[k]
                        for k in (
                            "id",
                            "name",
                            "flat_width_mm",
                            "flat_length_mm",
                            "stretch",
                            "fits_roll",
                        )
                    }
                    for p in pattern["panels"]
                ],
                "parameter_hash": pattern["parameter_hash"],
            }
        if finished:
            out["finished"] = {
                "pieces": [
                    {k: p[k] for k in ("id", "name", "quantity", "size_mm", "area_m2", "note")}
                    for p in finished["pieces"]
                ],
                "sheet": finished.get("sheet"),
            }
        out["diff"] = compare_files(d / "pattern.prev.json", d / "pattern.json")
        out["revisions"] = revisions(d)
        return out

    def parameters(self, model_id: str, trial: dict[str, Any] | None = None) -> dict[str, Any]:
        eff = resolve_model(self.model_dir(model_id), trial)
        return {"values": eff.flat(), "sources": eff.sources()}

    def save_parameters(self, model_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """Write the model's own settings to `cover.json` (only keys that differ from the
        default), keeping everything else in that file."""
        d = self.model_dir(model_id)
        registry = Registry.load()
        clean: dict[str, Any] = {}
        for key, value in values.items():
            clean[key] = registry.coerce(key, value, "web")
        path = d / "cover.json"
        doc = _read(path) or {"format_version": 1, "model_id": model_id}
        tree: dict[str, Any] = {}
        for key, v in sorted(clean.items()):
            node = tree
            *parents, leaf = key.split(".")
            for part in parents:
                node = node.setdefault(part, {})
            node[leaf] = v
        doc["parameters"] = tree
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return self.parameters(model_id)


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def registry_specs() -> list[dict[str, Any]]:
    registry = Registry.load()
    return [
        {
            "key": s.key,
            "group": s.key.split(".")[0],
            "default": s.default,
            "kind": s.kind,
            "choices": list(s.choices) if s.choices else None,
            "comment": s.comment,
            "to_confirm": s.to_confirm,
        }
        for s in registry.specs.values()
    ]
