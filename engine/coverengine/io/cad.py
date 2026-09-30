"""STEP and IGES import through OpenCascade (cadquery-ocp), keeping the assembly structure.

The assembly tree is walked with part names and placements. Each distinct part shape is
tessellated once and reused for every placed copy (a model with 200 identical screws meshes one
screw). OpenCascade converts every length to mm while reading; the unit the file was written in
is reported so `model.json` can record it.
"""

from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from coverengine.errors import CoverError
from coverengine.io.faceted_step import read_faceted_step, step_length_unit
from coverengine.io.parts import Part, split_bodies, unique_paths

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

STEP_SUFFIXES = (".step", ".stp")
STL_HEADER_BYTES = 80
STL_RECORD = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
IGES_SUFFIXES = (".iges", ".igs")


# IGES global section unit flag -> mm per unit (IGES 5.3, section 2.2.4.3)
IGES_UNIT_FLAG_MM = {
    1: 25.4,  # inch
    2: 1.0,  # mm
    4: 304.8,  # foot
    6: 1000.0,  # metre
    8: 0.0254,  # param-ok: IGES unit flag 8 = mil
    9: 1e-3,  # micron
    10: 10.0,  # param-ok: IGES unit flag 10 = cm
}


@dataclass
class CadModel:
    parts: list[Part]
    unit_name: str | None  # the length unit's name as written in the file
    mm_per_unit: float | None  # what the file defines one unit as; OpenCascade converted by it


def _quiet() -> None:
    """OpenCascade prints transfer statistics to stdout; keep only failures."""
    from OCP.Message import Message, Message_Gravity

    for printer in Message.DefaultMessenger_s().Printers():
        printer.SetTraceLevel(Message_Gravity.Message_Fail)


def _label_name(label: object) -> str:
    from OCP.TDataStd import TDataStd_Name

    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):  # type: ignore[attr-defined]
        return str(attr.Get().ToExtString()).strip()
    return ""


def _is_generated_name(name: str) -> bool:
    # OpenCascade names unnamed instances after their label entry, e.g. "=>[0:1:1:2]"
    return not name or name.startswith("=>")


def _matrix(location: object) -> Array:
    trsf = location.Transformation()  # type: ignore[attr-defined]
    m = np.eye(4)
    for r in range(3):
        for c in range(4):
            m[r, c] = trsf.Value(r + 1, c + 1)
    return m


def _mesh_all(shapes: list[object], deflection_mm: float, angle_deg: float) -> None:
    """Mesh every distinct shape in one parallel run (parallelism is per face, so meshing
    shapes one by one would leave one-face parts such as tubes on a single core). The result
    does not depend on the number of threads (checked with 1 to 8 cores, ADR-022)."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopoDS import TopoDS_Compound

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    # relative=False: deflection is absolute, in mm
    BRepMesh_IncrementalMesh(compound, deflection_mm, False, math.radians(angle_deg), True)


def _triangles(shape: object, scratch: Path) -> tuple[Array, IntArray]:
    """Triangles of a meshed shape. OpenCascade writes them as binary STL, read back with numpy,
    which keeps the per-triangle work in compiled code."""
    from OCP.StlAPI import StlAPI_Writer

    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    stl = scratch / "part.stl"
    if not writer.Write(shape, str(stl)):
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    data = stl.read_bytes()
    count = int(np.frombuffer(data, dtype="<u4", count=1, offset=STL_HEADER_BYTES)[0])
    records = np.frombuffer(data, dtype=STL_RECORD, count=count, offset=STL_HEADER_BYTES + 4)
    vertices = records["v"].reshape(-1, 3).astype(np.float64)
    faces = np.arange(len(vertices), dtype=np.int64).reshape(-1, 3)
    return vertices, faces


def _read_document(path: Path) -> tuple[object, str | None, float | None]:
    """The XCAF document, the file's length unit name and its size in mm."""
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document

    _quiet()
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    suffix = path.suffix.lower()
    name: str | None = None
    mm: float | None = None
    if suffix in STEP_SUFFIXES:
        from OCP.collections import Sequence_TCollection_AsciiString as Names
        from OCP.STEPCAFControl import STEPCAFControl_Reader

        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        status = reader.ReadFile(str(path))
        if status != IFSelect_ReturnStatus.IFSelect_RetDone:
            raise CoverError(f"{path}: not a readable STEP file ({status.name})")
        lengths, angles, solid_angles = Names(), Names(), Names()
        reader.ChangeReader().FileUnits(lengths, angles, solid_angles)
        if lengths.Length() > 0:
            name = str(lengths.Value(1).ToCString())
        # OpenCascade converts by the unit's definition, which can differ from its name
        unit = step_length_unit(path.read_bytes())
        if unit is not None:
            name, mm = unit
    elif suffix in IGES_SUFFIXES:
        from OCP.IGESCAFControl import IGESCAFControl_Reader

        reader = IGESCAFControl_Reader()
        reader.SetNameMode(True)
        status = reader.ReadFile(str(path))
        if status != IFSelect_ReturnStatus.IFSelect_RetDone:
            raise CoverError(f"{path}: not a readable IGES file ({status.name})")
        header = reader.IGESModel().GlobalSection()
        name = str(header.UnitName().ToCString())
        mm = IGES_UNIT_FLAG_MM.get(int(header.UnitFlag()))
    else:
        raise CoverError(f"{path}: not a STEP or IGES file")
    if not reader.Transfer(doc):
        raise CoverError(f"{path}: OpenCascade could not convert the file's geometry")
    return doc, name, mm


def _sew(shape: object, tolerance_mm: float) -> object:
    """Join loose faces (IGES) into shells so neighbouring faces share their edges."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing

    sewing = BRepBuilderAPI_Sewing(tolerance_mm)
    sewing.Add(shape)
    sewing.Perform()
    return sewing.SewedShape()


def load_cad(
    path: Path, deflection_mm: float, angular_deflection_deg: float, sew_tolerance_mm: float
) -> CadModel:
    """Read a STEP or IGES file into parts in mm, in the file's own coordinates."""
    from OCP.collections import Sequence_TDF_Label
    from OCP.TDF import TDF_Label
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    if path.suffix.lower() in STEP_SUFFIXES:
        faceted = read_faceted_step(path)
        if faceted is not None:
            return CadModel(faceted.parts, faceted.unit_name, faceted.mm_per_unit)
    doc, unit_name, mm_per_unit = _read_document(path)
    sew = path.suffix.lower() in IGES_SUFFIXES
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())  # type: ignore[attr-defined]
    shapes: dict[str, object] = {}  # distinct part shapes by label entry
    placed: list[tuple[str, str, Array]] = []  # (path, prototype entry, transform)

    def entry(label: TDF_Label) -> str:
        from OCP.TCollection import TCollection_AsciiString
        from OCP.TDF import TDF_Tool

        s = TCollection_AsciiString()
        TDF_Tool.Entry_s(label, s)
        return str(s.ToCString())

    def walk(label: TDF_Label, loc: TopLoc_Location, prefix: str, name: str) -> None:
        here = f"{prefix}/{name}" if prefix else name
        if tool.IsAssembly_s(label):
            children = Sequence_TDF_Label()
            tool.GetComponents_s(label, children, False)
            for child in children:
                ref = TDF_Label()
                if not tool.GetReferredShape_s(child, ref):
                    continue
                child_name = _label_name(child)
                if _is_generated_name(child_name):
                    child_name = _label_name(ref) or "part"
                walk(ref, loc.Multiplied(tool.GetLocation_s(child)), here, child_name)
            return
        key = entry(label)
        if key not in shapes:
            shape = tool.GetShape_s(label)
            shapes[key] = _sew(shape, sew_tolerance_mm) if sew else shape
        placed.append((here, key, _matrix(loc)))

    roots = Sequence_TDF_Label()
    tool.GetFreeShapes(roots)
    for root in roots:
        walk(root, TopLoc_Location(), "", _label_name(root) or "part")
    _mesh_all(list(shapes.values()), deflection_mm, angular_deflection_deg)
    with tempfile.TemporaryDirectory(prefix="coverengine-") as tmp:
        meshes = {key: _triangles(shape, Path(tmp)) for key, shape in shapes.items()}

    # split each distinct shape once; placed copies only move its bodies
    bodies = {key: split_bodies("", v, f) for key, (v, f) in meshes.items()}
    paths = unique_paths(p for p, _, _ in placed)
    parts: list[Part] = []
    for part_path, (_, key, matrix) in zip(paths, placed, strict=True):
        for body in bodies[key]:
            moved = body.transformed(matrix)
            moved.path = part_path + body.path  # body paths are "" or "/1", "/2", ...
            parts.append(moved)
    return CadModel(parts, unit_name, mm_per_unit)
