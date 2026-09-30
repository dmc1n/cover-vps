"""STEP and IGES import through OpenCascade (cadquery-ocp), keeping the assembly structure.

The assembly tree is walked with part names and placements. Each distinct part shape is
tessellated once and reused for every placed copy (a model with 200 identical screws meshes one
screw). OpenCascade converts every length to mm while reading; the unit the file was written in
is reported so `model.json` can record it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from coverengine.errors import CoverError
from coverengine.io.parts import Part, split_bodies, unique_paths

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

STEP_SUFFIXES = (".step", ".stp")
IGES_SUFFIXES = (".iges", ".igs")


@dataclass
class CadModel:
    parts: list[Part]
    units_declared: list[str] = field(default_factory=list)  # unit names as written in the file


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


def _tessellate(shape: object, deflection_mm: float, angle_deg: float) -> tuple[Array, IntArray]:
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    # relative=False: absolute deflection in mm; parallel=False keeps the output deterministic
    BRepMesh_IncrementalMesh(shape, deflection_mm, False, math.radians(angle_deg), False)
    verts: list[Array] = []
    faces: list[IntArray] = []
    offset = 0
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None and tri.NbTriangles() > 0:
            trsf = loc.Transformation()
            nodes = (tri.Node(i).Transformed(trsf) for i in range(1, tri.NbNodes() + 1))
            v = np.array([(p.X(), p.Y(), p.Z()) for p in nodes], dtype=np.float64)
            t = np.array(
                [tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], dtype=np.int64
            )
            t -= 1
            if face.Orientation() == TopAbs_REVERSED:
                t = t[:, ::-1]
            verts.append(v)
            faces.append(t + offset)
            offset += len(v)
        explorer.Next()
    if not faces:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    return np.vstack(verts), np.vstack(faces)


def _read_document(path: Path) -> tuple[object, list[str]]:
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document

    _quiet()
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    suffix = path.suffix.lower()
    units: list[str] = []
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
        units = [str(lengths.Value(i).ToCString()) for i in range(1, lengths.Length() + 1)]
    elif suffix in IGES_SUFFIXES:
        from OCP.IGESCAFControl import IGESCAFControl_Reader

        reader = IGESCAFControl_Reader()
        reader.SetNameMode(True)
        status = reader.ReadFile(str(path))
        if status != IFSelect_ReturnStatus.IFSelect_RetDone:
            raise CoverError(f"{path}: not a readable IGES file ({status.name})")
        units = [str(reader.IGESModel().GlobalSection().UnitName().ToCString())]
    else:
        raise CoverError(f"{path}: not a STEP or IGES file")
    if not reader.Transfer(doc):
        raise CoverError(f"{path}: OpenCascade could not convert the file's geometry")
    return doc, units


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

    doc, units = _read_document(path)
    sew = path.suffix.lower() in IGES_SUFFIXES
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())  # type: ignore[attr-defined]
    meshes: dict[str, tuple[Array, IntArray]] = {}
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
        if key not in meshes:
            shape = tool.GetShape_s(label)
            if sew:
                shape = _sew(shape, sew_tolerance_mm)
            meshes[key] = _tessellate(shape, deflection_mm, angular_deflection_deg)
        placed.append((here, key, _matrix(loc)))

    roots = Sequence_TDF_Label()
    tool.GetFreeShapes(roots)
    for root in roots:
        walk(root, TopLoc_Location(), "", _label_name(root) or "part")

    parts: list[Part] = []
    for part_path, (_, key, matrix) in zip(
        unique_paths(p for p, _, _ in placed), placed, strict=True
    ):
        v, f = meshes[key]
        if len(f) == 0:
            continue
        v = v @ matrix[:3, :3].T + matrix[:3, 3]
        parts.extend(split_bodies(part_path, v, f))
    return CadModel(parts, units)
