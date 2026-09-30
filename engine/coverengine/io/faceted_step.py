"""Fast reader for faceted STEP files: meshes saved as STEP (only flat faces, straight edges).

Some exporters (e.g. "Spatial InterOp 3D", SketchUp, mesh tools) write a triangle or quad mesh
as STEP, one planar face per facet. OpenCascade converts every facet into a full B-rep face,
which takes about 2 minutes for 100,000 facets. Such a file needs no geometry kernel: each face
is a polygon of points. This module reads those polygons straight from the text and returns
None for any file it cannot handle exactly (curved geometry, assemblies, instancing, faces
with holes, several length units), which then goes through OpenCascade (ADR-023).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from coverengine.io.parts import Part, split_bodies, unique_paths

# Anything that is not a plane bounded by straight lines, or that places items with
# transforms, sends the file to OpenCascade. SURFACE_CURVE and PCURVE may stay: OpenCascade
# wraps straight edges in them, and any curved 3D edge they could carry is caught above.
_NOT_FACETED = re.compile(
    rb"B_SPLINE|BEZIER|RATIONAL|CIRCLE|ELLIPSE|PARABOLA|HYPERBOLA|CYLINDRICAL_SURFACE|"
    rb"CONICAL_SURFACE|SPHERICAL_SURFACE|TOROIDAL_SURFACE|SURFACE_OF_|OFFSET_|TRIMMED_|"
    rb"CURVE_BOUNDED|POLYLINE|NEXT_ASSEMBLY_USAGE|MAPPED_ITEM|"
    rb"ITEM_DEFINED_TRANSFORMATION|REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION"
)
_ENTITY = re.compile(rb"#(\d+)\s*=\s*([A-Z0-9_]*)\s*\((.*)\)\s*$", re.S)
_SPLIT = re.compile(rb";\s*(?=#\d+\s*=)")
_STRING = re.compile(rb"'(?:[^']|'')*'")
_REF = re.compile(rb"#(\d+)")
_NUMBER = re.compile(rb"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
# SI prefix of a metre-based unit -> mm per unit
_SI_PREFIX_MM = {
    b"$": 1000.0,
    b".MILLI.": 1.0,
    b".CENTI.": 10.0,  # param-ok: centimetre
    b".DECI.": 100.0,  # param-ok: decimetre
    b".MICRO.": 1e-3,
    b".KILO.": 1e6,
}

_WANTED = {
    b"CARTESIAN_POINT",
    b"VERTEX_POINT",
    b"EDGE_CURVE",
    b"ORIENTED_EDGE",
    b"EDGE_LOOP",
    b"POLY_LOOP",
    b"FACE_BOUND",
    b"FACE_OUTER_BOUND",
    b"ADVANCED_FACE",
    b"FACE_SURFACE",
    b"CLOSED_SHELL",
    b"OPEN_SHELL",
    b"PRODUCT",
}


class NotFaceted(Exception):
    """The file needs the full CAD reader."""


@dataclass
class FacetedModel:
    parts: list[Part]
    unit_name: str  # as written in the file, e.g. "METRE" or "millimetre"
    mm_per_unit: float  # what one file unit is in mm, per the file's own definition
    facets: int


def _flag(args: bytes) -> bool:
    """The last .T./.F. flag of an argument list."""
    t, f = args.rfind(b".T."), args.rfind(b".F.")
    return t > f


def _refs(args: bytes) -> list[int]:
    return [int(r) for r in _REF.findall(_STRING.sub(b"''", args))]


_UNIT_ENTITY = re.compile(rb"#(\d+)\s*=\s*\(([^;]*?LENGTH_UNIT\s*\(\s*\)[^;]*)\)\s*;")
_SI_LENGTH = re.compile(rb"SI_UNIT\s*\(\s*([^,\s]+)\s*,\s*\.METRE\.\s*\)")
_CONVERSION = re.compile(rb"CONVERSION_BASED_UNIT\s*\(\s*'([^']*)'\s*,\s*#(\d+)")
_SI_NAMES = {1000.0: "metre", 1.0: "millimetre", 10.0: "centimetre"}  # param-ok: unit names


def step_length_unit(data: bytes) -> tuple[str, float] | None:
    """(name, mm per unit) of a STEP file's length unit, from its definition in the file.

    A conversion-based unit ('INCH', or a mislabelled 'METRE') is defined as a multiple of an
    SI unit; OpenCascade converts by that definition, so this is what the file really means.
    None when the file has no single, readable length unit.
    """
    units = {int(m.group(1)): m.group(2) for m in _UNIT_ENTITY.finditer(data)}

    def si_mm(entity: bytes) -> float | None:
        m = _SI_LENGTH.search(entity)
        return _SI_PREFIX_MM.get(m.group(1)) if m else None

    conversions = {}
    for entity in units.values():
        m = _CONVERSION.search(entity)
        if m:
            conversions[(m.group(1), int(m.group(2)))] = m
    if not conversions:
        factors = {si_mm(e) for e in units.values()}
        if len(factors) != 1 or None in factors:
            return None
        (mm,) = factors
        assert mm is not None
        return _SI_NAMES.get(mm, f"{mm:g} mm"), mm
    results = set()
    for name, measure_id in conversions:
        m = re.search(
            # the value may be typed, LENGTH_MEASURE(25.4), or bare, 25.4
            rb"#%d\s*=\s*LENGTH_MEASURE_WITH_UNIT\s*\(\s*(?:LENGTH_MEASURE\s*\(\s*)?"
            rb"([-+0-9.Ee]+)\s*\)?\s*,\s*#(\d+)" % measure_id,
            data,
        )
        base = units.get(int(m.group(2))) if m else None
        base_mm = si_mm(base) if base else None
        if m is None or base_mm is None:
            return None
        results.add((name.decode("ascii", "replace"), float(m.group(1)) * base_mm))
    return results.pop() if len(results) == 1 else None


def read_faceted_step(path: Path) -> FacetedModel | None:
    """Polygons of a faceted STEP file in mm, or None if the file is not faceted."""
    data = path.read_bytes()
    start, end = data.find(b"DATA;"), data.rfind(b"ENDSEC;")
    if start < 0 or end < start or _NOT_FACETED.search(data):
        return None
    unit = step_length_unit(data)
    if unit is None:
        return None
    try:
        return _parse(data[start + len(b"DATA;") : end], path.stem, *unit)
    except NotFaceted:
        return None


def _parse(body: bytes, fallback_name: str, unit_name: str, mm_per_unit: float) -> FacetedModel:
    ents: dict[bytes, dict[int, bytes]] = {t: {} for t in _WANTED}
    for chunk in _SPLIT.split(body):
        m = _ENTITY.match(chunk.strip().rstrip(b";"))
        if not m:
            continue
        kind = m.group(2)
        if not kind:  # complex instance "( A() B() )": units, read by step_length_unit
            continue
        table = ents.get(kind)
        if table is not None:
            table[int(m.group(1))] = m.group(3)

    point_ids, coords = [], []
    for k, args in ents[b"CARTESIAN_POINT"].items():
        inner = _STRING.sub(b"''", args)  # the name could hold digits
        c = [float(x) for x in _NUMBER.findall(inner[inner.index(b"(") :])]
        if len(c) == 3:  # 2D points belong to parameter-space curves (pcurves)
            point_ids.append(k)
            coords.append(c)
    xyz = np.array(coords, dtype=np.float64) * mm_per_unit
    point_row = dict(zip(point_ids, range(len(point_ids)), strict=True))

    vertex_point = {k: _refs(a)[0] for k, a in ents[b"VERTEX_POINT"].items()}
    edge_ends = {}
    for k, a in ents[b"EDGE_CURVE"].items():
        r = _refs(a)
        edge_ends[k] = (vertex_point[r[0]], vertex_point[r[1]])
    oriented_start = {}
    for k, a in ents[b"ORIENTED_EDGE"].items():
        v1, v2 = edge_ends[_refs(a)[0]]
        oriented_start[k] = v1 if _flag(a) else v2
    loops = {k: [oriented_start[r] for r in _refs(a)] for k, a in ents[b"EDGE_LOOP"].items()}
    loops.update({k: _refs(a) for k, a in ents[b"POLY_LOOP"].items()})
    bounds = {**ents[b"FACE_BOUND"], **ents[b"FACE_OUTER_BOUND"]}
    faces = {**ents[b"ADVANCED_FACE"], **ents[b"FACE_SURFACE"]}
    shells = {**ents[b"CLOSED_SHELL"], **ents[b"OPEN_SHELL"]}
    if not faces or not shells:
        raise NotFaceted("no faces")

    def polygon(face_args: bytes) -> list[int]:
        refs = _refs(face_args)
        if len(refs) != 2:  # one bound plus the plane; holes need a real triangulator
            raise NotFaceted("face with holes")
        bound = bounds[refs[0]]
        try:
            loop = [point_row[p] for p in loops[_refs(bound)[0]]]
        except KeyError as exc:
            raise NotFaceted("loop without 3D points") from exc
        # the loop runs counter-clockwise around the outward normal when the bound and
        # the face agree with the plane; each disagreement reverses it
        if _flag(bound) != _flag(face_args):
            loop.reverse()
        return loop

    names = [
        _STRING.findall(a)[0].strip(b"'").decode("utf-8", "replace")
        for a in ents[b"PRODUCT"].values()
    ]
    name = names[0] if len(names) == 1 and names[0].strip() else fallback_name
    parts: list[Part] = []
    facets = 0
    for shell_args in shells.values():
        tris: list[tuple[int, int, int]] = []
        for face_id in _refs(shell_args):
            loop = polygon(faces[face_id])
            facets += 1
            tris.extend((loop[0], loop[i], loop[i + 1]) for i in range(1, len(loop) - 1))
        if tris:
            f = np.array(tris, dtype=np.int64)
            used, local = np.unique(f, return_inverse=True)
            parts.extend(split_bodies("", xyz[used], local.reshape(f.shape)))
    paths = unique_paths(name + p.path for p in parts)
    for part, p in zip(parts, paths, strict=True):
        part.path = p
    return FacetedModel(parts, unit_name, mm_per_unit, facets)
