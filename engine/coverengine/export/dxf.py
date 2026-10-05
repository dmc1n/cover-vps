"""DXF sheet writer with a cut and a pen layer (conventions: docs/FORMATS.md, Exports).

Knows how the machine wants its DXF: layer names, colours per layer or per entity, TEXT
entities or single-stroke text, and the DXF version. Output is byte-deterministic.
"""

from __future__ import annotations

import io
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import ezdxf
from ezdxf.enums import TextEntityAlignment

from coverengine.export import strokefont

Point = tuple[float, float]
BulgePoint = tuple[float, float, float]  # x, y, bulge to the next vertex

INSUNITS_MM = 4

# Deterministic output (CLAUDE.md rule 10): no creation timestamps or random GUIDs in files.
ezdxf.options.write_fixed_meta_data_for_testing = True


@dataclass(frozen=True)
class DxfStyle:
    dxf_version: str
    cut_layer: str
    pen_layer: str
    cut_color: int
    pen_color: int
    colors: Literal["bylayer", "entity"] = "bylayer"
    text: Literal["text", "strokes"] = "text"


class SheetWriter:
    def __init__(self, style: DxfStyle) -> None:
        self.style = style
        r12 = style.dxf_version.upper() in ("R12", "AC1009")
        # R12 has no unit header; its importer must be set to mm (checklist).
        ezdxf_log = logging.getLogger("ezdxf")
        level = ezdxf_log.level
        if r12:  # ezdxf.new always sets units and warns that R12 cannot store them
            ezdxf_log.setLevel(logging.ERROR)
        try:
            self.doc = ezdxf.new(style.dxf_version, units=0 if r12 else INSUNITS_MM)
        finally:
            ezdxf_log.setLevel(level)
        if r12:
            del self.doc.header["$INSUNITS"]
        else:
            self.doc.header["$MEASUREMENT"] = 1  # metric
        self.msp = self.doc.modelspace()
        self._layer(style.cut_layer, style.cut_color)
        if style.pen_layer != style.cut_layer:
            self._layer(style.pen_layer, style.pen_color)

    @property
    def is_r12(self) -> bool:
        return self.doc.dxfversion == "AC1009"

    def _layer(self, name: str, color: int) -> None:
        if name in self.doc.layers:
            if self.style.colors == "bylayer":
                self.doc.layers.get(name).color = color
        else:
            self.doc.layers.add(name, color=color)

    def _attribs(self, kind: Literal["cut", "pen"]) -> dict[str, object]:
        layer = self.style.cut_layer if kind == "cut" else self.style.pen_layer
        attribs: dict[str, object] = {"layer": layer}
        if self.style.colors == "entity":
            attribs["color"] = self.style.cut_color if kind == "cut" else self.style.pen_color
        return attribs

    def _polyline(
        self, kind: Literal["cut", "pen"], points: Sequence[BulgePoint], closed: bool
    ) -> None:
        attribs = self._attribs(kind)
        if self.is_r12:
            self.msp.add_polyline2d(points, format="xyb", close=closed, dxfattribs=attribs)
        else:
            self.msp.add_lwpolyline(points, format="xyb", close=closed, dxfattribs=attribs)

    # -- cut --------------------------------------------------------------------------------

    def cut_polyline(self, points: Sequence[BulgePoint]) -> None:
        """Closed outline; bulge = tan(arc angle / 4) toward the next vertex."""
        self._polyline("cut", points, closed=True)

    def cut_circle(self, center: Point, radius: float) -> None:
        self.msp.add_circle(center, radius, dxfattribs=self._attribs("cut"))

    # -- pen --------------------------------------------------------------------------------

    def pen_polyline(self, points: Sequence[Point], closed: bool = False) -> None:
        self._polyline("pen", [(x, y, 0.0) for x, y in points], closed=closed)

    def pen_line(self, a: Point, b: Point) -> None:
        self.msp.add_line(a, b, dxfattribs=self._attribs("pen"))

    def pen_arc(self, center: Point, radius: float, start_deg: float, end_deg: float) -> None:
        self.msp.add_arc(center, radius, start_deg, end_deg, dxfattribs=self._attribs("pen"))

    def pen_text(self, text: str, insert: Point, height: float) -> None:
        if self.style.text == "strokes":
            for stroke in strokefont.text_strokes(text, insert, height):
                if len(stroke) == 1:
                    stroke = [stroke[0], stroke[0]]
                self.pen_polyline(stroke)
            return
        entity = self.msp.add_text(text, height=height, dxfattribs=self._attribs("pen"))
        entity.set_placement(insert, align=TextEntityAlignment.LEFT)

    # -- output -----------------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        # ezdxf registers some CLASS entries in hash-seed dependent order; the order carries no
        # meaning in DXF, so sort it for byte-identical files across runs.
        if not self.is_r12:
            self.doc.classes.add_required_classes(self.doc.dxfversion)
            classes = self.doc.classes.classes
            ordered = sorted(classes.items(), key=lambda kv: str(kv[0]))
            classes.clear()
            classes.update(ordered)
        stream = io.StringIO()
        self.doc.write(stream)
        return self.doc.encode(stream.getvalue())

    def save(self, path: Path) -> None:
        path.write_bytes(self.to_bytes())


def arc_points(
    center: Point, radius: float, start_deg: float, end_deg: float, segments: int
) -> list[Point]:
    cx, cy = center
    out = []
    for i in range(segments + 1):
        a = math.radians(start_deg + (end_deg - start_deg) * i / segments)
        out.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return out


def rect_points(x: float, y: float, w: float, h: float) -> list[BulgePoint]:
    return [(x, y, 0.0), (x + w, y, 0.0), (x + w, y + h, 0.0), (x, y + h, 0.0)]


def rounded_rect_points(x: float, y: float, w: float, h: float, r: float) -> list[BulgePoint]:
    b = math.tan(math.radians(90.0) / 4)  # param-ok: a quarter-circle corner
    return [
        (x + r, y, 0.0),
        (x + w - r, y, b),
        (x + w, y + r, 0.0),
        (x + w, y + h - r, b),
        (x + w - r, y + h, 0.0),
        (x + r, y + h, b),
        (x, y + h - r, 0.0),
        (x, y + r, b),
    ]


def circle_bulge_points(center: Point, radius: float) -> list[BulgePoint]:
    """A full circle as two half-circle arcs (bulge 1)."""
    cx, cy = center
    return [(cx + radius, cy, 1.0), (cx - radius, cy, 1.0)]


def polygon_points(center: Point, radius: float, segments: int) -> list[BulgePoint]:
    return [(x, y, 0.0) for x, y in arc_points(center, radius, 0.0, 360.0, segments)[:-1]]
