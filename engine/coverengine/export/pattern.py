"""Pattern sheets: every panel laid out at 1:1 on one sheet, as DXF (cut and pen layers, for
the cutting table) and SVG (to view or print), plus an SVG of the stretch per triangle.

Panels are placed in rows, `export.sheet_spacing_mm` apart; the machine's software nests them.
M4 patterns have no seam allowances (paper test); M5 adds allowances and the hem.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import numpy as np
from numpy.typing import NDArray

from coverengine.export.dxf import DxfStyle, SheetWriter
from coverengine.flatten.pattern import PERCENT, PanelPattern
from coverengine.flatten.solve import singular_values
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]

CUT_COLOUR, PEN_COLOUR = 1, 5  # param-ok: AutoCAD colour index, red and blue
# Rows are filled up to this width before starting the next (mm).
ROW_WIDTH_MM = 6000.0  # param-ok: sheet layout only; the machine nests
# Stretch picture: full colour at this stretch (%).
STRETCH_FULL_PCT = 2.0  # param-ok: display scale


@dataclass
class Placed:
    pattern: PanelPattern
    offset: Array  # added to the panel's own coordinates


def layout(patterns: list[PanelPattern], spacing: float) -> tuple[list[Placed], float, float]:
    """Rows of panels, tallest first; returns the placements and the sheet size."""
    order = sorted(patterns, key=lambda p: (-float(np.ptp(p.outline[:, 1])), p.index))
    placed: list[Placed] = []
    x = y = row_h = 0.0
    width = 0.0
    for p in order:
        w, h = np.ptp(p.outline, axis=0)
        if x > 0 and x + w > ROW_WIDTH_MM:
            x, y, row_h = 0.0, y + row_h + spacing, 0.0
        placed.append(Placed(p, np.array([x, y]) - p.outline.min(axis=0)))
        x += w + spacing
        width = max(width, x - spacing)
        row_h = max(row_h, h)
    return placed, width, y + row_h


def _style(params: EffectiveParams) -> DxfStyle:
    return DxfStyle(
        dxf_version=str(params["export.dxf_version"]),
        cut_layer=str(params["export.cut_layer"]),
        pen_layer=str(params["export.pen_layer"]),
        cut_color=CUT_COLOUR,
        pen_color=PEN_COLOUR,
        text="strokes" if params["export.text_mode"] == "strokes" else "text",
    )


def _arrow(at: Array, length: float) -> list[list[tuple[float, float]]]:
    tip = at + [0.0, length]
    head = length / 4
    shaft = [(float(at[0]), float(at[1])), (float(tip[0]), float(tip[1]))]
    barbs = [
        (float(tip[0] - head), float(tip[1] - head)),
        (float(tip[0]), float(tip[1])),
        (float(tip[0] + head), float(tip[1] - head)),
    ]
    return [shaft, barbs]


def write_dxf(path: Path, placed: list[Placed], params: EffectiveParams) -> None:
    sheet = SheetWriter(_style(params))
    height = float(params["pen.label_height_mm"])  # type: ignore[arg-type]
    for pl in placed:
        o = pl.offset
        sheet.cut_polyline([(float(x + o[0]), float(y + o[1]), 0.0) for x, y in pl.pattern.outline])
        for m in pl.pattern.pen:
            at = np.asarray(m["at"], dtype=np.float64) + o
            if m["type"] == "label":
                sheet.pen_text(m["text"], (float(at[0]), float(at[1])), height)
            elif m["type"] == "seam_label":
                sheet.pen_text(m["text"], (float(at[0]), float(at[1])), height * 0.6)
            elif m["type"] == "arrow_up":
                for stroke in _arrow(at, float(m["length"])):
                    sheet.pen_polyline(stroke)
            elif m["type"] == "tick":
                end = at + np.asarray(m["dir"]) * float(m["length"])
                sheet.pen_line((float(at[0]), float(at[1])), (float(end[0]), float(end[1])))
    sheet.save(path)


def _svg_head(width: float, height: float) -> list[str]:
    pad = 20.0  # param-ok: margin of the SVG drawing
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width + 2 * pad:.1f}mm" '
        f'height="{height + 2 * pad:.1f}mm" '
        f'viewBox="{-pad:.1f} {-pad:.1f} {width + 2 * pad:.1f} {height + 2 * pad:.1f}">',
        # the pattern's y axis points up; SVG's points down
        f'<g transform="translate(0 {height:.1f}) scale(1 -1)">',
    ]


def write_svg(
    path: Path, placed: list[Placed], width: float, height: float, params: EffectiveParams
) -> None:
    label_h = float(params["pen.label_height_mm"])  # type: ignore[arg-type]
    out = _svg_head(width, height)
    out.append('<g id="cut" fill="none" stroke="#d00" stroke-width="1">')
    for pl in placed:
        pts = " ".join(
            f"{x + pl.offset[0]:.2f},{y + pl.offset[1]:.2f}" for x, y in pl.pattern.outline
        )
        out.append(f'<polygon points="{pts}"/>')
    out.append("</g>")
    out.append('<g id="pen" fill="none" stroke="#00c" stroke-width="0.8">')
    texts = []
    for pl in placed:
        for m in pl.pattern.pen:
            at = np.asarray(m["at"], dtype=np.float64) + pl.offset
            if m["type"] in ("label", "seam_label"):
                size = label_h if m["type"] == "label" else label_h * 0.6
                texts.append((at, size, m["text"]))
            elif m["type"] == "arrow_up":
                for stroke in _arrow(at, float(m["length"])):
                    out.append(
                        '<polyline points="'
                        + " ".join(f"{x:.2f},{y:.2f}" for x, y in stroke)
                        + '"/>'
                    )
            elif m["type"] == "tick":
                end = at + np.asarray(m["dir"]) * float(m["length"])
                out.append(
                    f'<line x1="{at[0]:.2f}" y1="{at[1]:.2f}" x2="{end[0]:.2f}" y2="{end[1]:.2f}"/>'
                )
    out.append("</g></g>")
    # text outside the flipped group so it reads the right way up
    out.append('<g id="pen-text" fill="#00c" font-family="sans-serif">')
    for at, size, text in texts:
        out.append(
            f'<text x="{at[0]:.2f}" y="{height - at[1]:.2f}" '
            f'font-size="{size:.1f}">{escape(text)}</text>'
        )
    out.append("</g></svg>")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _colour(pct: float) -> str:
    """White at 0, red for stretch, blue for compression, full at STRETCH_FULL_PCT."""
    t = min(abs(pct) / STRETCH_FULL_PCT, 1.0)
    light = int(round(255 * (1 - t)))
    return f"#ff{light:02x}{light:02x}" if pct >= 0 else f"#{light:02x}{light:02x}ff"


def write_stretch_svg(path: Path, placed: list[Placed], width: float, height: float) -> None:
    out = _svg_head(width, height)
    for pl in placed:
        f = pl.pattern.flat
        s1, s2, _ = singular_values(f.vertices, f.faces, f.uv)
        signed = np.where(s1 - 1 >= 1 - s2, s1 - 1, s2 - 1) * PERCENT
        uv = f.uv + pl.offset  # the outline is part of the same flat map
        for tri, pct in zip(f.faces, signed, strict=True):
            pts = " ".join(f"{uv[i, 0]:.1f},{uv[i, 1]:.1f}" for i in tri)
            out.append(f'<polygon points="{pts}" fill="{_colour(float(pct))}" stroke="none"/>')
        pts = " ".join(
            f"{x + pl.offset[0]:.2f},{y + pl.offset[1]:.2f}" for x, y in pl.pattern.outline
        )
        out.append(f'<polygon points="{pts}" fill="none" stroke="#333" stroke-width="1"/>')
    out.append("</g></svg>")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def write_all(out: Path, patterns: list[PanelPattern], params: EffectiveParams) -> dict[str, Any]:
    spacing = float(params["export.sheet_spacing_mm"])  # type: ignore[arg-type]
    placed, width, height = layout(patterns, spacing)
    write_dxf(out / "pattern.dxf", placed, params)
    write_svg(out / "pattern.svg", placed, width, height, params)
    write_stretch_svg(out / "pattern-stretch.svg", placed, width, height)
    return {
        "sheet_mm": [round(width, 1), round(height, 1)],
        "placements": {
            pl.pattern.name: [round(float(pl.offset[0]), 2), round(float(pl.offset[1]), 2)]
            for pl in placed
        },
    }
