"""CAD test assemblies (STEP and IGES) written with OpenCascade, for the import tests.

Dimensions come from `testdata/shapes.yaml` (`furniture.chair` for the frame, `assemblies.*`
for cushion and hardware). Output is byte-identical across runs: the writers' time stamps are
replaced by a fixed one.
"""

from __future__ import annotations

import itertools
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from coverengine.testshapes import load_config

FIXED_STEP_TIME = "2000-01-01T00:00:00"


def assembly_specs(config: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Assembly name -> spec, with `like:` resolved."""
    cfg = config or load_config()
    raw = cfg.get("assemblies", {})
    out: dict[str, dict[str, Any]] = {}
    for name, spec in raw.items():
        base = dict(raw[spec["like"]]) if "like" in spec else {}
        base.update({k: v for k, v in spec.items() if k != "like"})
        base.setdefault("on_demand", False)
        out[name] = base
    return out


def _name(label: Any, text: str) -> None:
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name

    TDataStd_Name.Set_s(label, TCollection_ExtendedString(text))


def _translation(x: float, y: float, z: float) -> Any:
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.TopLoc import TopLoc_Location

    t = gp_Trsf()
    t.SetTranslation(gp_Vec(x, y, z))
    return TopLoc_Location(t)


def _grid(
    count: int, x0: float, y0: float, width: float, pitch: float
) -> list[tuple[float, float]]:
    cols = max(int(width // pitch), 1)
    return [(x0 + (i % cols) * pitch, y0 + (i // cols) * pitch) for i in range(count)]


def build_document(spec: Mapping[str, Any], chair: Mapping[str, Any]) -> Any:
    """XCAF document: chair / frame, cushion, hardware."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    sx, sy, sz = map(float, chair["seat"])
    seat_top = float(chair["seat_height"])
    bx, bt, bl = map(float, chair["back"])
    tilt = float(chair["back_tilt_deg"])
    lx, ly = map(float, chair["leg"])
    leg_h = seat_top - sz

    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    XCAFDoc_DocumentTool.SetLengthUnit_s(doc, 1e-3)  # document lengths are mm (unit in metres)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    def shape(s: Any, name: str) -> Any:
        label = tool.AddShape(s, False)
        _name(label, name)
        return label

    def assembly(name: str) -> Any:
        label = tool.NewShape()
        _name(label, name)
        return label

    root, frame, hardware = assembly("chair"), assembly("frame"), assembly("hardware")
    tool.AddComponent(root, frame, TopLoc_Location())

    seat = shape(BRepPrimAPI_MakeBox(gp_Pnt(-sx / 2, -sy / 2, leg_h), sx, sy, sz).Shape(), "seat")
    tool.AddComponent(frame, seat, TopLoc_Location())
    # back: slab on the rear edge of the seat, tilted backwards about its bottom edge
    rot = gp_Trsf()
    rot.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), math.radians(-tilt))
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(0, sy / 2 - bt, seat_top))
    move.Multiply(rot)
    back = shape(BRepPrimAPI_MakeBox(gp_Pnt(-bx / 2, 0, 0), bx, bt, bl).Shape(), "back")
    tool.AddComponent(frame, back, TopLoc_Location(move))
    leg = shape(BRepPrimAPI_MakeBox(lx, ly, leg_h).Shape(), "leg")
    for px in (-1, 1):
        for py in (-1, 1):
            x0 = px * sx / 2 - (lx if px > 0 else 0.0)
            y0 = py * sy / 2 - (ly if py > 0 else 0.0)
            tool.AddComponent(frame, leg, _translation(x0, y0, 0.0))

    cx, cy, cz = map(float, spec["cushion"])
    cushion = BRepPrimAPI_MakeBox(gp_Pnt(-cx / 2, -cy / 2, seat_top), cx, cy, cz).Shape()
    tool.AddComponent(root, shape(cushion, "cushion"), TopLoc_Location())

    tool.AddComponent(root, hardware, TopLoc_Location())
    pitch = float(spec["hardware_pitch"])
    sr, sl = float(spec["screw"]["radius"]), float(spec["screw"]["length"])
    screw = shape(BRepPrimAPI_MakeCylinder(sr, sl).Shape(), "screw M4")
    inner = sx - 2 * pitch
    for x, y in _grid(int(spec["screws"]), -inner / 2, -inner / 2, inner, pitch):
        tool.AddComponent(hardware, screw, _translation(x, y, leg_h - sl))
    wr, wt = float(spec["washer"]["radius"]), float(spec["washer"]["thickness"])
    for i, (x, y) in enumerate(_grid(int(spec["washers"]), -inner / 2, -inner / 2, inner, pitch)):
        axis = gp_Ax2(gp_Pnt(x, y, leg_h - sl - wt), gp_Dir(0, 0, 1))
        washer = shape(BRepPrimAPI_MakeCylinder(axis, wr, wt).Shape(), f"washer {i + 1}")
        tool.AddComponent(hardware, washer, TopLoc_Location())
    tool.UpdateAssemblies()
    return doc


def _unit_name(unit: str) -> str:
    return {"mm": "MM", "inch": "INCH", "m": "M", "cm": "CM"}[unit]


def write_document(doc: Any, path: Path, unit: str) -> None:
    from OCP.IGESCAFControl import IGESCAFControl_Writer
    from OCP.IGESControl import IGESControl_Controller
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Controller

    from coverengine.io.cad import _quiet

    _quiet()
    suffix = path.suffix.lower()
    if suffix == ".step":
        STEPControl_Controller.Init_s()
        Interface_Static.SetCVal_s("write.step.unit", _unit_name(unit))
        writer = STEPCAFControl_Writer()
        writer.SetNameMode(True)
        writer.Transfer(doc, STEPControl_AsIs)
        writer.Write(str(path))
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", FIXED_STEP_TIME, text, count=1)
        # assembly-link ids come from a counter that keeps running within one process
        ids = itertools.count(1)
        text = re.sub(
            r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\('\d+'([^;]*);",
            lambda m: (
                f"NEXT_ASSEMBLY_USAGE_OCCURRENCE('{next(ids)}'"
                + re.sub(r"\s*\n\s*", "", m.group(1))  # line wrapping depended on the id's length
                + ";"
            ),
            text,
        )
        path.write_text(text, encoding="utf-8")
    elif suffix == ".iges":
        IGESControl_Controller.Init_s()
        Interface_Static.SetCVal_s("write.iges.unit", _unit_name(unit))

        writer = IGESCAFControl_Writer()
        # IGES has no assembly tree and the writer orders its name entities differently on
        # every run; without names the file is reproducible (IGES imports carry no names anyway)
        writer.SetNameMode(False)
        writer.Transfer(doc)
        # the author defaults to the login name, which differs between machines
        from OCP.TCollection import TCollection_HAsciiString

        header = writer.Model().GlobalSection()
        header.SetAuthorName(TCollection_HAsciiString("coverengine"))
        writer.Model().SetGlobalSection(header)
        writer.Write(str(path))
        # global section dates (fixed-column format: replace with the same length)
        text = path.read_text(encoding="ascii")
        text = re.sub(r"15H\d{8}\.\d{6}", "15H20000101.000000", text)
        path.write_text(text, encoding="ascii")
    else:
        raise ValueError(f"unsupported CAD test file {path}")


def write_assembly(name: str, out_dir: Path, config: Mapping[str, Any] | None = None) -> list[Path]:
    cfg = config or load_config()
    spec = assembly_specs(cfg)[name]
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = build_document(spec, cfg["furniture"]["chair"])
    written = []
    for file_name, unit in spec["files"].items():
        path = out_dir / file_name
        write_document(doc, path, str(unit))
        written.append(path)
    return written


def write_assemblies(out_dir: Path, config: Mapping[str, Any] | None = None) -> list[Path]:
    """All assemblies except the on-demand ones (the 2,000-part timing model)."""
    cfg = config or load_config()
    return [
        p
        for name, spec in assembly_specs(cfg).items()
        if not spec["on_demand"]
        for p in write_assembly(name, out_dir, cfg)
    ]
