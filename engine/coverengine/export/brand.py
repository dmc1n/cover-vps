"""The S2DIO and SUNS logos on every page of the program's PDFs (size drawing, cutting list,
catalogue), top right, as vector pictures. The pages keep no date or random id, so the same
cover still gives the same file (rule 10)."""

from __future__ import annotations

from pathlib import Path

BRAND = Path(__file__).resolve().parents[1] / "brand"
LOGOS = ("s2dio-mark.svg", "suns.svg")
HEIGHT_PT = 22.0  # param-ok: logo height on the page (about 8 mm)
MARGIN_PT = 26.0  # param-ok: from the page edge
GAP_PT = 6.0  # param-ok: between the logos


def brand(path: Path) -> Path:
    import pymupdf

    logos = []
    for name in LOGOS:
        svg = pymupdf.open(BRAND / name)
        logos.append(pymupdf.open("pdf", svg.convert_to_pdf()))
    doc = pymupdf.open(path)
    for i in range(doc.page_count):
        page = doc[i]
        x = page.rect.x1 - MARGIN_PT
        for logo in reversed(logos):
            r = logo[0].rect
            w = HEIGHT_PT * r.width / r.height
            box = pymupdf.Rect(
                x - w, page.rect.y0 + MARGIN_PT, x, page.rect.y0 + MARGIN_PT + HEIGHT_PT
            )
            page.show_pdf_page(box, logo, 0)
            x -= w + GAP_PT
    doc.set_metadata({"creator": "Cover Studio (S2DIO x SUNS)", "producer": "cover-pattern-engine"})
    data = doc.tobytes(garbage=3, deflate=True, no_new_id=True)
    path.write_bytes(data)
    return path
