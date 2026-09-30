"""The export for the cutting table (M5): `cut.dxf`, `cut.svg` and `cutting-list.pdf`.

Pieces are placed in rows on one sheet, `export.sheet_spacing_mm` apart (the machine's software
nests them). CUT layer: each piece's outline with allowances, and its openings (air vents). PEN
layer: stitch and fold lines, weld guides, marks and text. The cutting list gives every piece
with its size, and the fabric needed, estimated by laying the pieces on the roll in rows
across its usable width.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from numpy.typing import NDArray

from coverengine import __version__
from coverengine.export.dxf import DxfStyle, SheetWriter
from coverengine.finish.finish import Piece, narrow_size
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]

CUT_COLOUR, PEN_COLOUR = 1, 5  # param-ok: AutoCAD colour index, red and blue
ROW_WIDTH_MM = 6000.0  # param-ok: sheet layout only; the machine nests
A4_MM = (210.0, 297.0)  # param-ok: paper size
MM_PER_INCH = 25.4  # param-ok: unit conversion
FONT = 8.0  # param-ok: layout
MM_PER_CM, MM_PER_M = 10.0, 1000.0  # param-ok: unit conversion
LEFT_MM = 15.0  # param-ok: layout, left margin of the cutting list
COLUMNS_MM = (15.0, 60.0, 72.0, 105.0, 125.0)  # param-ok: layout, column positions
NOTE_CHARS = 60  # param-ok: layout
REVISION_CHARS = 6  # param-ok: layout


@dataclass
class Placed:
    piece: Piece
    copy: int
    offset: Array


def layout(pieces: list[Piece], spacing: float) -> tuple[list[Placed], float, float]:
    """Every copy of every piece in rows, tallest first; placements and the sheet size."""
    items = [(pc, c) for pc in pieces for c in range(pc.quantity)]
    items.sort(key=lambda it: (-float(np.ptp(it[0].cut[:, 1])), it[0].id, it[1]))
    placed: list[Placed] = []
    x = y = row_h = width = 0.0
    for pc, c in items:
        w, h = np.ptp(pc.cut, axis=0)
        if x > 0 and x + w > ROW_WIDTH_MM:
            x, y, row_h = 0.0, y + row_h + spacing, 0.0
        placed.append(Placed(pc, c, np.array([x, y]) - pc.cut.min(axis=0)))
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


def _xy(a: Array) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in a]


def write_dxf(path: Path, placed: list[Placed], params: EffectiveParams) -> None:
    sheet = SheetWriter(_style(params))
    for pl in placed:
        o = pl.offset
        sheet.cut_polyline([(float(x + o[0]), float(y + o[1]), 0.0) for x, y in pl.piece.cut])
        for hole in pl.piece.openings:
            sheet.cut_polyline([(float(x + o[0]), float(y + o[1]), 0.0) for x, y in hole])
        for line in pl.piece.pen_lines:
            sheet.pen_polyline(_xy(line + o))
        for text, at, height in pl.piece.pen_text:
            p = at + o
            sheet.pen_text(text, (float(p[0]), float(p[1])), height)
    sheet.save(path)


def write_svg(path: Path, placed: list[Placed], width: float, height: float) -> None:
    pad = 20.0  # param-ok: margin of the SVG drawing
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width + 2 * pad:.1f}mm" '
        f'height="{height + 2 * pad:.1f}mm" '
        f'viewBox="{-pad:.1f} {-pad:.1f} {width + 2 * pad:.1f} {height + 2 * pad:.1f}">',
        f'<g transform="translate(0 {height:.1f}) scale(1 -1)">',
        '<g id="cut" fill="none" stroke="#d00" stroke-width="1">',
    ]
    for pl in placed:
        for ring in [pl.piece.cut, *pl.piece.openings]:
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in ring + pl.offset)
            out.append(f'<polygon points="{pts}"/>')
    out.append('</g><g id="pen" fill="none" stroke="#00c" stroke-width="0.6">')
    texts = []
    for pl in placed:
        for line in pl.piece.pen_lines:
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in line + pl.offset)
            out.append(f'<polyline points="{pts}"/>')
        for text, at, h in pl.piece.pen_text:
            texts.append((at + pl.offset, h, text))
    out.append("</g></g>")
    out.append('<g id="pen-text" fill="#00c" font-family="sans-serif">')
    for at, h, text in texts:
        out.append(
            f'<text x="{at[0]:.2f}" y="{height - at[1]:.2f}" font-size="{h:.1f}">'
            f"{escape(text)}</text>"
        )
    out.append("</g></svg>")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def roll_length(pieces: list[Piece], usable: float, spacing: float) -> float:
    """Fabric length (mm) on the roll: every copy turned to its narrowest width across the roll
    where it fits, laid in rows (shelves) across the usable width, longest first."""
    items = []
    for pc in pieces:
        across, along = narrow_size(pc.cut)
        for _ in range(pc.quantity):
            items.append((along, across) if across <= usable else (across, along))
    # each item: (length along the roll, width across the roll); shelves by first fit
    items.sort(key=lambda it: -it[0])
    shelves: list[list[float]] = []  # [shelf length, width used]
    for along, across in items:
        for shelf in shelves:
            if shelf[1] + spacing + across <= usable and along <= shelf[0]:
                shelf[1] += spacing + across
                break
        else:
            shelves.append([along, across])
    return sum(s[0] for s in shelves) + spacing * max(len(shelves) - 1, 0)


def write_cutting_list(
    path: Path,
    pieces: list[Piece],
    finished: dict[str, Any],
    params: EffectiveParams,
) -> float:
    usable = float(params["roll.usable_width_mm"])  # type: ignore[arg-type]
    spacing = float(params["export.sheet_spacing_mm"])  # type: ignore[arg-type]
    length = roll_length(pieces, usable, spacing)
    fig = Figure(figsize=(A4_MM[0] / MM_PER_INCH, A4_MM[1] / MM_PER_INCH))

    def text(x: float, y: float, s: str, size: float = FONT, bold: bool = False) -> None:
        fig.text(x / A4_MM[0], 1 - y / A4_MM[1], s, fontsize=size, weight="bold" if bold else None)

    text(LEFT_MM, 18, f"Cutting list: {finished['model_id']}", 14, True)  # param-ok: layout
    method = "double stitched" if finished["construction"] == "double_stitch" else "welded"
    revision = finished["parameter_hash"][:REVISION_CHARS]
    text(LEFT_MM, 26, f"{method} · pattern revision {revision} · engine {__version__}")  # param-ok
    cols = list(zip(COLUMNS_MM, ("Piece", "Qty", "Size (cm)", "Area (m²)", "Note"), strict=True))
    y = 40.0  # param-ok: layout
    for x, h in cols:
        text(x, y, h, FONT, True)
    area = 0.0
    for pc in pieces:
        y += 6.0  # param-ok: layout, row height
        size = np.ptp(pc.cut, axis=0) / 10.0  # param-ok: mm to cm
        a = float(abs(_area(pc.cut))) / 1e6
        area += a * pc.quantity
        cells = [
            f"{pc.id} {pc.name}",
            str(pc.quantity),
            f"{size[0]:.1f} × {size[1]:.1f}",
            f"{a:.3f}",
            (pc.note or ("opening for air vents" if pc.openings else ""))[:NOTE_CHARS],
        ]
        for (x, _), c in zip(cols, cells, strict=True):
            text(x, y, c)
    y += 12.0  # param-ok: layout
    text(LEFT_MM, y, f"Fabric area: {area:.2f} m² (with allowances)", FONT, True)
    y += 6.0  # param-ok: layout
    roll = float(params["roll.width_mm"])  # type: ignore[arg-type]
    text(
        LEFT_MM,
        y,
        f"Fabric needed: about {length / MM_PER_M:.2f} m of a {roll / MM_PER_CM:g} cm roll "
        f"({usable / MM_PER_CM:g} cm usable), pieces laid in rows; the machine's nesting may "
        "use less.",
    )
    for i, w in enumerate(finished.get("warnings", [])[:12]):  # param-ok: layout
        text(LEFT_MM, y + 10 + 5 * i, f"warning: {w}"[:120], FONT - 1)  # param-ok: layout
    with PdfPages(path, metadata={"CreationDate": None, "Creator": "cover-pattern-engine"}) as pdf:
        pdf.savefig(fig)
    return length


def _area(ring: Array) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return float(0.5 * (x @ np.roll(y, -1) - y @ np.roll(x, -1)))  # param-ok: layout or units


def write_export(
    out: Path, pieces: list[Piece], finished: dict[str, Any], params: EffectiveParams
) -> dict[str, Any]:
    spacing = float(params["export.sheet_spacing_mm"])  # type: ignore[arg-type]
    placed, width, height = layout(pieces, spacing)
    write_dxf(out / "cut.dxf", placed, params)
    write_svg(out / "cut.svg", placed, width, height)
    length = write_cutting_list(out / "cutting-list.pdf", pieces, finished, params)
    return {"sheet_mm": [round(width, 1), round(height, 1)], "roll_length_mm": round(length, 0)}
