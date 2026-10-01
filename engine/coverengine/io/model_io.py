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
import math
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


@dataclass
class Units:
    detected: str | None  # what the file declares (unit id, or "<n> mm" if not a common unit)
    used: str  # what was applied
    scale: float  # loaded values -> mm
    mm_per_file_unit: float  # after --units; what one number in the file became
    warnings: list[str]


def _unit_label(mm: float) -> str:
    for u, value in UNIT_MM.items():
        if math.isclose(mm, value, rel_tol=1e-9):
            return u
    return f"{mm:g} mm"


def _cad_units(name: str | None, mm_per_unit: float | None, override: str | None) -> Units:
    """STEP and IGES: OpenCascade already converted to mm by the file's unit definition."""
    warnings: list[str] = []
    if mm_per_unit is None:
        if override is not None:
            raise CoverError(f"file declares unit {name!r}; --units cannot be applied to it")
        return Units(name, "mm", 1.0, 1.0, [f"file unit {name!r} unknown; assumed mm"])
    detected = _unit_label(mm_per_unit)
    named = unit_id(name) if name else None
    if named is not None and named != detected:
        warnings.append(
            f"the file names its unit {name!r} but defines it as {mm_per_unit:g} mm; the "
            "definition was used"
        )
    if override is None:
        return Units(detected, detected, 1.0, mm_per_unit, warnings)
    if override != detected:
        warnings.append(f"file declares {detected}; treated as {override} as requested (--units)")
    return Units(detected, override, UNIT_MM[override] / mm_per_unit, UNIT_MM[override], warnings)


def _mesh_units(fmt: str, declared: str | None, override: str | None, default: str) -> Units:
    """STL, OBJ, PLY store no unit; glTF is metres by definition."""
    used = override or declared or default
    warnings = []
    if override and declared and override != declared:
        warnings.append(
            f"{fmt} files are in {declared}; treated as {override} as requested (--units)"
        )
    return Units(declared, used, UNIT_MM[used], UNIT_MM[used], warnings)


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

    if units is not None and units not in UNIT_MM:
        raise CoverError(f"unknown unit {units!r}; use one of mm | cm | m | inch")
    if fmt in ("step", "iges"):
        cad = load_cad(
            src,
            float(params["import.deflection_mm"]),
            float(params["import.angular_deflection_deg"]),
            float(params["import.sew_tolerance_mm"]),
        )
        raw_parts = cad.parts
        unit = _cad_units(cad.unit_name, cad.mm_per_unit, units)
    else:
        mesh = load_mesh_parts(src)
        raw_parts = mesh.parts
        unit = _mesh_units(fmt, mesh.units_declared, units, str(params["import.default_units"]))
    detected, used, scale, warnings = unit.detected, unit.used, unit.scale, unit.warnings
    plausible = (
        float(params["import.min_plausible_size_mm"]),
        float(params["import.max_plausible_size_mm"]),
    )

    orient = np.eye(4)
    orient[:3, :3] = rotation(up_axis, front) * scale
    parts = [p.transformed(orient) for p in raw_parts]
    classify(parts, min_part_mm, patterns)
    kept = [p for p in parts if p.status == KEPT]
    if not kept:
        msg = (
            f"{src}: all {len(parts)} parts were dropped (smaller than {min_part_mm:g} mm or "
            "excluded)"
        )
        lo, hi = _extent(parts)
        hint = plausibility_warning(
            [float(x) for x in hi - lo], used, *plausible, mm_per_unit=unit.mm_per_file_unit
        )
        notes = [*warnings, hint or "check --min-part-mm and --exclude"]
        raise CoverError("; ".join([msg, *notes]))
    lo, hi = _extent(kept)
    shift = np.eye(4)
    shift[:3, 3] = ground_translation((lo, hi))
    # canonical coordinates are what model.glb stores: 32-bit floats
    parts = [_as_float32(p.transformed(shift)) for p in parts]
    kept = [p for p in parts if p.status == KEPT]
    lo, hi = _extent(kept)

    size: Array = hi - lo
    warning = plausibility_warning(
        [float(x) for x in size], used, *plausible, mm_per_unit=unit.mm_per_file_unit
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
    return glb_bytes([(p.path, trimesh.Trimesh(p.vertices, p.faces, process=False)) for p in parts])


def glb_bytes(meshes: Sequence[tuple[str, trimesh.Trimesh]]) -> bytes:
    """A GLB with canonical mm Z-up meshes under the glTF (metres, Y up) root node."""
    scene = trimesh.Scene()
    scene.graph.update(frame_from=scene.graph.base_frame, frame_to=ROOT_NODE, matrix=_TO_GLTF)
    for name, mesh in meshes:
        scene.add_geometry(mesh, node_name=name, geom_name=name, parent_node_name=ROOT_NODE)
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


def load_model_parts(model_dir: Path) -> tuple[trimesh.Trimesh, NDArray[np.int64]]:
    """The canonical mesh and, per face, the number of the part it came from (a cover surface
    drawn as separate pieces: each part is one piece, ADR-045)."""
    glb = model_dir / MODEL_GLB if model_dir.is_dir() else model_dir
    mesh = load_model(model_dir)
    scene = trimesh.load(glb, force="scene", process=False)
    assert isinstance(scene, trimesh.Scene)
    counts = [
        len(scene.geometry[scene.graph[node][1]].faces)
        for node in sorted(scene.graph.nodes_geometry, key=_node_order(scene))
    ]
    return mesh, np.repeat(np.arange(len(counts), dtype=np.int64), counts)


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
