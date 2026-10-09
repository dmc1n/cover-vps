"""Check list (`checklist.pdf`, ADR-110): one sheet per cover for the workshop to tick off while
measuring a sewn cover.

Page 1 (A4 landscape): the cover seen from the front, the back, the left and the right, all at
one scale, with its seams, hem and numbered air vents; the overall size, the skirt heights and
every vent (opening width and height, bottom edge above the hem, distance to the seam or corner
on its left and right, as seen from outside), each with an empty box for the measured value and
a tick box. Page 2 and on: the hem length and flat size of every piece and every seam's length,
for a closer check.

The numbers are the cutting file's own (`coverengine.measure.check_points`: the flat pieces, the
vents as `place_vents` cut them), not re-estimated. All sizes along the fabric, seam to seam,
in cm with one decimal. Made when it is opened, again when the cover changed (as sizes.pdf).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Polygon, Rectangle

from coverengine import __version__
from coverengine.export import drawing
from coverengine.export.drawing import A4_MM, FONT, HASH_CHARS, MM_PER_CM, MM_PER_INCH, View
from coverengine.params import EffectiveParams

CHECKLIST_PDF = "checklist.pdf"
DPI = 150  # param-ok: resolution of the shaded views in the PDF
ROW = 4.6  # param-ok: layout, table row height on paper (mm)
VENT_COLOUR = "#1b1b1b"
FACING = 0.3  # param-ok: display, a vent is drawn in a view when it faces the viewer this much
LABEL_ROOM = 0.12  # param-ok: layout, share of a view's height kept under it for its size
VIEW_BOX = (0.22, 0.33)  # param-ok: layout, a view's share of the page (width, height)
LOW_VIEW_MM = 45.0  # param-ok: layout, views lower than this on paper go two by two
VIEW_GAP_MM = 6.0  # param-ok: layout, between two rows of views
MEASURE_COLUMNS = [("Measured", 17.0, "box"), ("OK", 7.0, "box")]  # param-ok: layout
MARGIN = 10.0  # param-ok: layout, page margin (mm)
SMALL = FONT - 0.5  # param-ok: layout, the tables' font size
LINE_W = 0.5  # param-ok: layout, a box's line width


def cm(mm: float | None) -> str:
    return "–" if mm is None else f"{mm / MM_PER_CM:.1f}"


def _side_views() -> list[View]:
    x, y, z = np.eye(3)
    return [
        View("front", -y, x, z),
        View("back", y, -x, z),
        View("left", -x, -y, z),
        View("right", x, y, z),
    ]


def _turn(deg: float) -> Any:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _view(
    ax: Any,
    cover: drawing.Cover,
    view: View,
    vents: list[dict[str, Any]],
    turn: Any,
    span: tuple[float, float],
) -> None:
    """One side of the cover in a view `span` (width, height, mm) big: every view at one
    scale."""
    drawing._shaded(ax, cover, view)
    v = cover.vertices
    lo = np.array([v @ view.right, v @ view.up]).min(axis=1)
    hi = np.array([v @ view.right, v @ view.up]).max(axis=1)
    for x in vents:
        n = turn @ np.asarray(x["normal"], dtype=np.float64)
        if float(n @ view.eye) < FACING:
            continue
        c = np.asarray(x["corners_mm"], dtype=np.float64) @ turn.T
        p2 = np.column_stack([c @ view.right, c @ view.up])
        ax.add_patch(Polygon(p2, closed=True, color=VENT_COLOUR, zorder=6))
        at = p2.mean(axis=0)
        ax.text(float(at[0]), float(at[1]), f"V{x['number']}", color="white",
                fontsize=SMALL, weight="bold", ha="center", va="center", zorder=7)  # fmt: skip
    mid = (lo + hi) / 2
    ax.set_xlim(mid[0] - span[0] / 2, mid[0] + span[0] / 2)
    ax.set_ylim(lo[1] - span[1] * LABEL_ROOM, lo[1] + span[1] * (1 - LABEL_ROOM))
    ax.set_title(view.name.capitalize(), fontsize=FONT + 1, loc="left")
    size = hi - lo
    ax.text(float(mid[0]), float(lo[1] - span[1] * LABEL_ROOM / 2),
            f"{cm(float(size[0]))} cm wide, {cm(float(size[1]))} cm high",
            fontsize=FONT - 1, ha="center", va="center", color="#333")  # fmt: skip


class _Sheet:
    """Text, boxes and table rows placed on a page in mm."""

    def __init__(self, fig: Figure, size: tuple[float, float]) -> None:
        self.fig, self.w, self.h = fig, size[0], size[1]

    def text(self, x: float, y: float, s: str, size: float = FONT, **kw: Any) -> None:
        self.fig.text(x / self.w, y / self.h, s, fontsize=size, va="center", **kw)

    def line(self, x0: float, x1: float, y: float) -> None:
        from matplotlib.lines import Line2D

        self.fig.add_artist(Line2D([x0 / self.w, x1 / self.w], [y / self.h] * 2, lw=0.3,
                                   color="#999"))  # fmt: skip

    def box(self, x: float, y: float, w: float, h: float) -> None:
        self.fig.add_artist(Rectangle((x / self.w, y / self.h), w / self.w, h / self.h,
                                      fill=False, lw=LINE_W, edgecolor="#555"))  # fmt: skip

    def table(
        self,
        x: float,
        y: float,
        title: str,
        columns: list[tuple[str, float, str]],
        rows: list[list[str]],
    ) -> float:
        """Rows from y down; columns (header, width mm, l | r | box); returns the y below."""
        self.text(x, y, title, FONT + 1.5, weight="bold")
        y -= ROW
        cx = x
        for head, w, align in columns:
            self.text(cx + (w - 1 if align == "r" else 0), y, head, SMALL, weight="bold",
                      ha="right" if align == "r" else "left")  # fmt: skip
            cx += w
        self.line(x, cx, y - ROW / 2)
        for r in rows:
            y -= ROW
            cx = x
            for (_, w, align), cell in zip(columns, r, strict=True):
                if align == "box":
                    self.box(cx + 0.5, y - ROW * 0.38, w - 1.5, ROW * 0.76)  # param-ok: layout
                else:
                    self.text(cx + (w - 1 if align == "r" else 0), y, cell, SMALL,
                              ha="right" if align == "r" else "left")  # fmt: skip
                cx += w
            self.line(x, cx, y - ROW / 2)
        return y - ROW * 1.5  # param-ok: layout


VENT_COLUMNS = [
    ("Vent", 28.0, "l"),  # param-ok: layout
    ("Width", 11.0, "r"),
    ("", 14.0, "box"),
    ("Height", 12.0, "r"),
    ("", 14.0, "box"),
    ("Above hem", 16.0, "r"),
    ("", 14.0, "box"),
    ("Left", 11.0, "r"),
    ("", 14.0, "box"),
    ("Right", 11.0, "r"),
    ("", 14.0, "box"),
    ("OK", 7.0, "box"),
]  # param-ok: layout


def _vent_rows(vents: list[dict[str, Any]]) -> list[list[str]]:
    rows = []
    for x in vents:
        s = x.get("sides") or {}
        rows.append([
            f"V{x['number']} {x['piece']}", cm(x["size_mm"][0]), "", cm(x["size_mm"][1]), "",
            cm(x.get("above_hem_mm")), "", cm((s.get("left") or {}).get("mm")), "",
            cm((s.get("right") or {}).get("mm")), "", "",
        ])  # fmt: skip
    return rows


def _first_page(
    cover: drawing.Cover, points: dict[str, Any], params: EffectiveParams
) -> list[Figure]:
    w, h = A4_MM[1], A4_MM[0]  # landscape
    fig = Figure(figsize=(w / MM_PER_INCH, h / MM_PER_INCH))
    sheet = _Sheet(fig, (w, h))
    tol = float(params["tolerance.cover_mm"])  # type: ignore[arg-type]
    sheet.text(
        MARGIN, h - MARGIN, f"{cover.model_id}: check list for the sewn cover", 13, weight="bold"
    )
    sheet.text(
        MARGIN,
        h - 16,
        "Measure along the fabric with a tape measure, seam to seam, in cm. Write what you "
        f"measure; tick OK when it is within ±{tol / MM_PER_CM:g} cm. Left and right as seen "
        "from outside, facing that side.",
        FONT,
    )
    turn = _turn(cover.rotation_deg)
    vents = points["vents"]
    views = _side_views()
    v = cover.vertices
    wide = max(float(np.ptp(v @ vw.right)) for vw in views)
    high = float(np.ptp(v[:, 2])) / (1 - 1.5 * LABEL_ROOM)  # param-ok: layout, with its size line
    # one scale for every view: the widest side fits, and the highest
    top = h - 24.0  # param-ok: layout, under the title
    # four in a row; a long low cover two by two, so the views are not tiny
    bw, bh = VIEW_BOX[0] * w, VIEW_BOX[1] * h
    scale = max(wide / bw, high / bh)
    cols_n, step = 4, 0.24  # param-ok: layout
    if high / scale < LOW_VIEW_MM:
        cols_n, step = 2, 0.48  # param-ok: layout
        bw = (step - 0.02) * w  # param-ok: layout
        scale = max(wide / bw, 2 * high / bh)
    vh = high / scale  # a view's height on paper (mm)
    span = (bw * scale, high)
    for k, view in enumerate(views):
        row, col = divmod(k, cols_n)
        y0 = top - (row + 1) * vh - row * VIEW_GAP_MM
        ax = fig.add_axes((0.035 + col * step, y0 / h, bw / w, vh / h))
        _view(ax, cover, view, vents, turn, span)
    rows_n = len(views) // cols_n

    by_group: dict[str, list[dict[str, Any]]] = {}
    for p in points["points"]:
        by_group.setdefault(p["group"], []).append(p)
    y = top - rows_n * vh - (rows_n - 1) * VIEW_GAP_MM - 8.0  # param-ok: layout
    room = int((y - 22) / ROW) - 2  # param-ok: layout, rows above the footer
    cols = [("What", 56.0, "l"), ("Should be", 16.0, "r"), *MEASURE_COLUMNS]  # param-ok: layout
    rows = [[p["label"], cm(p["mm"]), "", ""] for g in ("Overall", "Skirt")
            for p in by_group.get(g, [])]  # fmt: skip
    sheet.table(MARGIN, y, "The cover (cm)", cols, rows[:room])

    x0 = 116.0  # param-ok: layout
    vrows = _vent_rows(vents)
    if vrows:
        yb = sheet.table(x0, y, "Air vents (cm): the opening, its bottom edge above the hem, "
                         "the seam or corner beside it", VENT_COLUMNS, vrows[:room])  # fmt: skip
        if len(vrows) > room:
            sheet.text(x0, yb, f"… {len(vrows) - room} more vents on the next page", FONT)
        else:
            note = (
                "Left / Right: from the side of the opening, along its bottom edge, to the seam "
                "beside it (or to the cover's corner when",
                "that comes first). Above hem: from the cover's lower edge up to the bottom of "
                "the opening.",
            )
            for k, text in enumerate(note):
                sheet.text(x0, yb - k * ROW * 0.8, text, FONT - 0.5)  # param-ok: layout
    else:
        sheet.text(x0, y, "No air vents on this cover.", FONT + 1)
    _foot(sheet, cover, w)
    pages = [fig]
    if len(rows) > room:
        pages += _more(cover, "The cover, continued (cm)", cols, rows[room:])
    if len(vrows) > room:
        pages += _more(cover, "Air vents, continued (cm)", VENT_COLUMNS, vrows[room:])
    return pages


def _foot(sheet: _Sheet, cover: drawing.Cover, w: float) -> None:
    sheet.text(
        MARGIN,
        6,
        f"Cover Studio {__version__} · parameters {cover.doc['parameter_hash'][:HASH_CHARS]} · "
        "numbers from the cutting file, along the fabric, seam to seam",
        FONT - 1,
        color="#555",
    )
    sheet.text(w - MARGIN, 6, "Checked by: ____________   Date: __________", FONT, ha="right")


def _more(
    cover: drawing.Cover, title: str, columns: list[tuple[str, float, str]], rows: list[list[str]]
) -> list[Figure]:
    """Rows over as many portrait pages as they need."""
    w, h = A4_MM
    pages = []
    per = int((h - 45) / ROW) - 2  # param-ok: layout
    for k in range(0, len(rows), per):
        fig = Figure(figsize=(w / MM_PER_INCH, h / MM_PER_INCH))
        sheet = _Sheet(fig, (w, h))
        sheet.text(MARGIN, h - 12, f"{cover.model_id}: check list", 11, weight="bold")
        sheet.table(MARGIN, h - 3 * MARGIN, title, columns, rows[k : k + per])
        _foot(sheet, cover, w)
        pages.append(fig)
    return pages


def write_checklist(model_dir: Path, params: EffectiveParams, out: Path) -> Path:
    from coverengine.measure import check_points

    doc = json.loads((model_dir / "pattern.json").read_text(encoding="utf-8"))
    cover = drawing.load_cover(model_dir, doc, params)
    cover.hem_z = float(cover.vertices[:, 2].min())
    points = check_points(model_dir, params)
    figures = _first_page(cover, points, params)
    cols = [("What", 120.0, "l"), ("Should be", 20.0, "r"), *MEASURE_COLUMNS]  # param-ok: layout
    rows = [[p["label"], cm(p["mm"]), "", ""] for p in points["points"] if p["group"] == "Pieces"]
    figures += _more(cover, "Pieces (cm): the hem of each piece seam to seam on the cover; the "
                     "flat piece seam to seam, in its narrowest box", cols, rows)  # fmt: skip
    rows = [[p["label"], cm(p["mm"]), "", ""] for p in points["points"] if p["group"] == "Seams"]
    figures += _more(cover, "Seams (cm): length on the cover, end to end", cols, rows)
    with PdfPages(
        out, metadata={"CreationDate": None, "Creator": f"cover-pattern-engine {__version__}"}
    ) as pdf:
        for fig in figures:
            pdf.savefig(fig, dpi=DPI)
    from coverengine.export.brand import brand

    return brand(out)


def ensure_checklist(model_dir: Path) -> Path | None:
    """The check list, made when it is asked for; again when the cut pieces changed. None when
    the cover is not exported yet."""
    finished = model_dir / "finished.json"
    out = model_dir / CHECKLIST_PDF
    if not (finished.is_file() and (model_dir / "pattern.json").is_file()):
        return None
    if out.is_file() and out.stat().st_mtime >= finished.stat().st_mtime:
        return out
    from coverengine.params.registry import Registry, resolve_model

    params = resolve_model(model_dir, {}, Registry.load(None), None)
    return write_checklist(model_dir, params, out)
