"""The catalogue report PDF (`cover report`): a summary, then every model with its grade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

A4 = (8.27, 11.69)  # param-ok: paper size (inches)
ROWS = 44  # param-ok: layout, table rows per page
COLOUR = {"ready": "#1a7f37", "check": "#b26a00", "failed": "#c62828"}
MM_PER_M = 1000.0  # param-ok: unit conversion


def write_report(path: Path, rows: list[dict[str, Any]], title: str) -> None:
    order = {"failed": 0, "check": 1, "ready": 2}
    rows = sorted(rows, key=lambda r: (order[r["grade"]], r["id"]))
    counts = {g: sum(r["grade"] == g for r in rows) for g in order}
    pages = [rows[i : i + ROWS] for i in range(0, len(rows), ROWS)] or [[]]
    with PdfPages(path, metadata={"CreationDate": None, "Creator": "cover-pattern-engine"}) as pdf:
        for n, chunk in enumerate(pages):
            fig = Figure(figsize=A4)
            if n == 0:
                fig.text(0.06, 0.965, f"Covers: {title}", fontsize=15, weight="bold")
                fig.text(
                    0.06,
                    0.945,
                    f"{len(rows)} models: {counts['ready']} ready, {counts['check']} to check, "
                    f"{counts['failed']} failed. Ready = every piece within the stretch limit, "
                    "smooth edges, seams matching within 5 mm.",
                    fontsize=7,
                )
            y = 0.915
            head = ["Model", "Grade", "Pieces", "Stretch", "Roll", "What to check"]
            xs = [0.06, 0.47, 0.54, 0.60, 0.67, 0.73]
            for x, h in zip(xs, head, strict=True):
                fig.text(x, y, h, fontsize=7, weight="bold")
            for r in chunk:
                y -= 0.0195
                roll = r.get("roll_length_mm")
                cells = [
                    r["id"][:62],
                    r["grade"],
                    str(r.get("panels", "")),
                    f"{r['max_stretch_pct']:.1f} %" if "max_stretch_pct" in r else "",
                    f"{roll / MM_PER_M:.1f} m" if roll else "",
                    "; ".join(r.get("reasons", []))[:70],
                ]
                for i, (x, c) in enumerate(zip(xs, cells, strict=True)):
                    colour = COLOUR[r["grade"]] if i == 1 else "black"
                    fig.text(x, y, c, fontsize=6, color=colour)
            fig.text(0.94, 0.02, f"page {n + 1} of {len(pages)}", fontsize=6, ha="right")
            pdf.savefig(fig)
