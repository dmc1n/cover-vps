"""M0 machine test sheets: learn the cutting table's DXF conventions (PLAN.md, M0).

Geometry and variants come from `testdata/machine/testsheet.yaml`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from coverengine.export.dxf import (
    DxfStyle,
    SheetWriter,
    arc_points,
    circle_bulge_points,
    polygon_points,
    rect_points,
    rounded_rect_points,
)
from coverengine.params.registry import repo_root


def spec_path() -> Path:
    return repo_root() / "testdata" / "machine" / "testsheet.yaml"


def load_spec(path: Path | None = None) -> dict[str, Any]:
    return dict(YAML(typ="safe", pure=True).load((path or spec_path()).read_text()))


def _style(variant: Mapping[str, Any], colors: Mapping[str, int]) -> DxfStyle:
    return DxfStyle(
        dxf_version=variant["dxf_version"],
        cut_layer=str(variant["cut_layer"]),
        pen_layer=str(variant["pen_layer"]),
        cut_color=int(colors["cut"]),
        pen_color=int(colors["pen"]),
        colors=variant["colors"],
        text=variant["text"],
    )


def _draw_cut(w: SheetWriter, item: Mapping[str, Any]) -> None:
    kind = item["type"]
    if kind == "rect":
        (x, y), (sx, sy) = item["at"], item["size"]
        w.cut_polyline(rect_points(x, y, sx, sy))
    elif kind == "rounded_rect":
        (x, y), (sx, sy) = item["at"], item["size"]
        w.cut_polyline(rounded_rect_points(x, y, sx, sy, item["radius"]))
    elif kind == "circle_entity":
        w.cut_circle(tuple(item["center"]), item["radius"])
    elif kind == "circle_bulge":
        w.cut_polyline(circle_bulge_points(tuple(item["center"]), item["radius"]))
    elif kind == "circle_segments":
        w.cut_polyline(polygon_points(tuple(item["center"]), item["radius"], item["segments"]))
    else:
        raise ValueError(f"testsheet: unknown cut type {kind!r}")


def _draw_pen(w: SheetWriter, item: Mapping[str, Any], title: str) -> None:
    kind = item["type"]
    if kind == "text":
        w.pen_text(str(item["text"]), tuple(item["at"]), item["height"])
    elif kind == "title":
        w.pen_text(title, tuple(item["at"]), item["height"])
    elif kind == "edge_ticks":
        x, y, sx, sy = item["rect"]
        step, length = item["spacing"], item["length"]
        for i in range(1, int(sx // step)):
            px = x + i * step
            w.pen_line((px, y), (px, y + length))
            w.pen_line((px, y + sy), (px, y + sy - length))
        for i in range(1, int(sy // step)):
            py = y + i * step
            w.pen_line((x, py), (x + length, py))
            w.pen_line((x + sx, py), (x + sx - length, py))
    elif kind == "inset_rect":
        x, y, sx, sy = item["rect"]
        d = item["inset"]
        pts = [(px, py) for px, py, _ in rect_points(x + d, y + d, sx - 2 * d, sy - 2 * d)]
        w.pen_polyline(pts, closed=True)
    elif kind == "arc":
        w.pen_arc(tuple(item["center"]), item["radius"], item["start_deg"], item["end_deg"])
    elif kind == "arc_segments":
        w.pen_polyline(
            arc_points(
                tuple(item["center"]),
                item["radius"],
                item["start_deg"],
                item["end_deg"],
                item["segments"],
            )
        )
    elif kind == "scale_bar":
        x, y = item["at"]
        length, step = item["length"], item["tick_spacing"]
        w.pen_line((x, y), (x + length, y))
        n = round(length / step)
        for i in range(n + 1):
            major = i in (0, n) or 2 * i == n
            h = item["major_tick"] if major else item["tick"]
            w.pen_line((x + i * step, y), (x + i * step, y + h))
    else:
        raise ValueError(f"testsheet: unknown pen type {kind!r}")


def build(variant: Mapping[str, Any], spec: Mapping[str, Any]) -> SheetWriter:
    w = SheetWriter(_style(variant, spec["colors"]))
    title = f"{spec['title']} - VARIANT {variant['id']} - {variant['note']}"
    for item in spec["cut"]:
        _draw_cut(w, item)
    for item in spec["pen"]:
        _draw_pen(w, item, title)
    return w


def write_all(out_dir: Path, spec: Mapping[str, Any] | None = None) -> list[Path]:
    s = spec or load_spec()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for variant in s["variants"]:
        path = out_dir / variant["file"]
        build(variant, s).save(path)
        paths.append(path)
    return paths
