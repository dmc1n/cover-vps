"""`cover import`: a manufacturer's file becomes a canonical model directory (FORMATS.md, M1).

    models/<id>/model.glb    kept parts, mm, Z up, on the ground, front toward -Y
    models/<id>/model.json   source, units, placement, part counts, warnings
    models/<id>/parts.json   every part with its size and whether it was kept

model.glb stores the canonical mm Z-up coordinates in its meshes under one root node whose
transform converts to glTF's metres and Y up, so any glTF viewer shows the model upright and
at true size while the engine reads the exact mm values (`load_model`).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray

from coverengine import __version__
from coverengine.errors import CoverError
from coverengine.io.cad import IGES_SUFFIXES, STEP_SUFFIXES, load_cad
from coverengine.io.meshfile import GLTF_SUFFIXES, MESH_SUFFIXES, load_mesh_parts
from coverengine.io.parts import DROPPED_SMALL, EXCLUDED, KEPT, Part, classify
from coverengine.io.placement import (
    UNIT_MM,
    ground_translation,
    plausibility_warning,
    rotation,
    unit_id,
)
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]

FORMAT_VERSION = 1
ROOT_NODE = "cover_model_mm_zup"
MODEL_GLB = "model.glb"
MODEL_JSON = "model.json"
PARTS_JSON = "parts.json"
CHUNK_BYTES = 1024 * 1024
SUPPORTED_SUFFIXES = STEP_SUFFIXES + IGES_SUFFIXES + MESH_SUFFIXES
# canonical mm Z up -> glTF metres Y up (inverse of the "y" up-axis rotation, scaled)
_TO_GLTF = np.array(
    [[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=np.float64
) * np.array([[1e-3], [1e-3], [1e-3], [1.0]])


@dataclass
class ImportResult:
    out_dir: Path
    model: dict[str, Any]
    parts: list[Part]
    warnings: list[str] = field(default_factory=list)


def _num(x: float, digits: int = 6) -> float:
    return round(float(x), digits) + 0.0  # + 0.0 turns -0.0 into 0.0


def _vec(v: Sequence[float] | Array, digits: int = 6) -> list[float]:
    return [_num(x, digits) for x in v]


def file_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in STEP_SUFFIXES:
        return "step"
    if suffix in IGES_SUFFIXES:
        return "iges"
    if suffix in MESH_SUFFIXES:
        return suffix.lstrip(".")
    supported = " ".join(sorted(SUPPORTED_SUFFIXES))
    raise CoverError(f"{path}: unsupported file type {suffix or '(none)'}; supported: {supported}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_BYTES), b""):
            h.update(chunk)
    return h.hexdigest()


def remembered_exclusions(out_dir: Path) -> list[str]:
    """Exclusion patterns of an earlier import into the same model directory."""
    previous = out_dir / MODEL_JSON
    if not previous.is_file():
        return []
    doc = json.loads(previous.read_text(encoding="utf-8"))
    return [str(p) for p in doc.get("parts", {}).get("exclude", [])]


def _units(
    fmt: str, declared: list[str] | str | None, override: str | None, default_units: str
) -> tuple[str | None, str, float, list[str]]:
    """(units declared by the file, units used, scale of loaded values to mm, warnings)."""
    warnings: list[str] = []
    if override is not None and override not in UNIT_MM:
        raise CoverError(f"unknown unit {override!r}; use one of mm | cm | m | inch")
    if fmt in ("step", "iges"):
        names = declared if isinstance(declared, list) else []
        ids = [unit_id(n) for n in names]
        if len(set(names)) > 1:
            warnings.append(
                f"file declares several length units ({', '.join(names)}); used the first"
            )
        detected = ids[0] if ids and ids[0] else (names[0] if names else None)
        # OpenCascade already converted from the declared unit to mm
        if override is None:
            return detected, detected or "mm", 1.0, warnings
        if detected not in UNIT_MM:
            raise CoverError(f"file declares unit {detected!r}; --units cannot be applied to it")
        if override != detected:
            warnings.append(
                f"file declares {detected}; treated as {override} as requested (--units)"
            )
        return detected, override, UNIT_MM[override] / UNIT_MM[detected], warnings
    detected = declared if isinstance(declared, str) else None
    used = override or detected or default_units
    if override and detected and override != detected:
        warnings.append(
            f"{fmt} files are in {detected}; treated as {override} as requested (--units)"
        )
    return detected, used, UNIT_MM[used], warnings


def import_model(
    src: Path,
    out_dir: Path,
    params: EffectiveParams,
    exclude: Sequence[str] = (),
    units: str | None = None,
    forget_exclusions: bool = False,
) -> ImportResult:
    if not src.is_file():
        raise CoverError(f"no such file: {src}")
    fmt = file_format(src)
    patterns = [] if forget_exclusions else remembered_exclusions(out_dir)
    patterns += [p for p in exclude if p not in patterns]

    min_part_mm = float(params["import.min_part_mm"])
    up_axis = str(params["import.up_axis"])
    if up_axis == "auto":
        up_axis = "y" if src.suffix.lower() in GLTF_SUFFIXES else "z"
    front = str(params["import.front"])

    if fmt in ("step", "iges"):
        cad = load_cad(
            src,
            float(params["import.deflection_mm"]),
            float(params["import.angular_deflection_deg"]),
            float(params["import.sew_tolerance_mm"]),
        )
        raw_parts, declared = cad.parts, cad.units_declared
        declared_arg: list[str] | str | None = declared
    else:
        mesh = load_mesh_parts(src)
        raw_parts, declared_arg = mesh.parts, mesh.units_declared
    detected, used, scale, warnings = _units(
        fmt, declared_arg, units, str(params["import.default_units"])
    )

    orient = np.eye(4)
    orient[:3, :3] = rotation(up_axis, front) * scale
    parts = [p.transformed(orient) for p in raw_parts]
    classify(parts, min_part_mm, patterns)
    kept = [p for p in parts if p.status == KEPT]
    if not kept:
        raise CoverError(
            f"{src}: all {len(parts)} parts were dropped (smaller than {min_part_mm:g} mm or "
            "excluded); check the units or lower --min-part-mm"
        )
    lo, hi = _extent(kept)
    shift = np.eye(4)
    shift[:3, 3] = ground_translation((lo, hi))
    # canonical coordinates are what model.glb stores: 32-bit floats
    parts = [_as_float32(p.transformed(shift)) for p in parts]
    kept = [p for p in parts if p.status == KEPT]
    lo, hi = _extent(kept)

    size: Array = hi - lo
    warning = plausibility_warning(
        [float(x) for x in size],
        used,
        float(params["import.min_plausible_size_mm"]),
        float(params["import.max_plausible_size_mm"]),
    )
    if warning:
        warnings.append(warning)

    counts = {s: sum(p.status == s for p in parts) for s in (KEPT, DROPPED_SMALL, EXCLUDED)}
    import_keys = [k for k in params.keys() if k.startswith("import.")]
    model: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "engine_version": __version__,
        "id": out_dir.resolve().name,
        "source": {
            "file": src.name,
            "format": fmt,
            "sha256": sha256(src),
            "units_detected": detected,
            "units_used": used,
        },
        "placement": {
            "up_axis": up_axis,
            "front": front,
            "scale_to_mm": _num(scale, 9),
            "rotation": rotation(up_axis, front).astype(int).tolist(),
            "translation_mm": _vec(shift[:3, 3]),
            "ground_offset_mm": _num(shift[2, 3]),
        },
        "parts": {
            "total": len(parts),
            "kept": counts[KEPT],
            "dropped_small": counts[DROPPED_SMALL],
            "excluded": counts[EXCLUDED],
            "min_part_mm": min_part_mm,
            "exclude": patterns,
        },
        "mesh": {
            "vertices": sum(len(p.vertices) for p in kept),
            "triangles": sum(len(p.faces) for p in kept),
        },
        "bbox_mm": [_vec(lo), _vec(hi)],
        "size_mm": _vec(size),
        "import_parameters": {k: params[k] for k in import_keys},
        "parameter_sources": {k: params.source(k) for k in import_keys},
        "warnings": warnings,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / MODEL_GLB).write_bytes(_glb(kept))
    _write_json(out_dir / PARTS_JSON, {"format_version": FORMAT_VERSION, "parts": _records(parts)})
    _write_json(out_dir / MODEL_JSON, model)
    return ImportResult(out_dir, model, parts, warnings)


def _extent(parts: Sequence[Part]) -> tuple[Array, Array]:
    lo = np.min(np.array([p.bounds[0] for p in parts], dtype=np.float64), axis=0)
    hi = np.max(np.array([p.bounds[1] for p in parts], dtype=np.float64), axis=0)
    return lo, hi


def _as_float32(p: Part) -> Part:
    return Part(p.path, p.vertices.astype(np.float32).astype(np.float64), p.faces, p.status, p.rule)


def _records(parts: Sequence[Part]) -> list[dict[str, Any]]:
    out = []
    for p in parts:
        lo, hi = p.bounds
        vol = p.volume()
        out.append(
            {
                "path": p.path,
                "status": p.status,
                "rule": p.rule,
                "triangles": len(p.faces),
                "bbox_mm": [_vec(lo, 3), _vec(hi, 3)],
                "size_mm": _vec(hi - lo, 3),
                "volume_mm3": None if vol is None else _num(vol, 1),
            }
        )
    return out


def _write_json(path: Path, doc: dict[str, Any]) -> None:
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _glb(parts: Sequence[Part]) -> bytes:
    scene = trimesh.Scene()
    scene.graph.update(frame_from=scene.graph.base_frame, frame_to=ROOT_NODE, matrix=_TO_GLTF)
    for p in parts:
        mesh = trimesh.Trimesh(p.vertices, p.faces, process=False)
        scene.add_geometry(mesh, node_name=p.path, geom_name=p.path, parent_node_name=ROOT_NODE)
    data = scene.export(file_type="glb")
    assert isinstance(data, bytes)
    return data


def load_model(model_dir: Path) -> trimesh.Trimesh:
    """The canonical mesh of an imported model: all kept parts, mm, Z up (a triangle soup)."""
    glb = model_dir / MODEL_GLB if model_dir.is_dir() else model_dir
    if not glb.is_file():
        raise CoverError(f"no imported model at {model_dir} (run cover import first)")
    scene = trimesh.load(glb, force="scene", process=False)
    if not isinstance(scene, trimesh.Scene) or ROOT_NODE not in scene.graph.nodes:
        raise CoverError(f"{glb}: not written by cover import")
    verts, faces, offset = [], [], 0
    for node in sorted(scene.graph.nodes_geometry, key=_node_order(scene)):
        transform, geom_name = scene.graph.get(frame_to=node, frame_from=ROOT_NODE)
        geom = scene.geometry[geom_name]
        verts.append(np.asarray(geom.vertices) @ transform[:3, :3].T + transform[:3, 3])
        faces.append(np.asarray(geom.faces, dtype=np.int64) + offset)
        offset += len(geom.vertices)
    return trimesh.Trimesh(np.vstack(verts), np.vstack(faces), process=False)


def _node_order(scene: trimesh.Scene):  # type: ignore[no-untyped-def]
    """Nodes in the order the parts were written (the glTF node list order)."""
    order = {name: i for i, name in enumerate(scene.geometry)}
    return lambda node: order.get(scene.graph[node][1], len(order))


def read_model_json(model_dir: Path) -> dict[str, Any]:
    path = model_dir / MODEL_JSON
    if not path.is_file():
        raise CoverError(f"no imported model at {model_dir} (run cover import first)")
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return doc
