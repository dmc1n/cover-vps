"""Pictures and PDFs from outside, opened within limits (ADR-123).

A small file can unpack to an enormous picture (a "decompression bomb": a PNG of a few KB that
claims 100 000 x 100 000 pixels), and a PDF can have thousands of pages or a page the size of a
field. Everything a person or a customer uploads goes through here before it is decoded or
rendered: the size in pixels is read from the header first and refused above
`limits.image_max_mp`; Pillow's own bomb warning is an error; a large JPEG is decoded at a
reduced scale straight away (`draft`); a PDF may have at most `limits.pdf_max_pages` pages and is
rendered at a resolution that keeps each page under the pixel cap.
"""

from __future__ import annotations

import io
import math
import warnings
from pathlib import Path
from typing import Any

from coverengine.errors import CoverError

MEGA = 1_000_000  # param-ok: pixels per megapixel
POINTS_PER_INCH = 72.0  # param-ok: PDF units
JPEG_MAX_REDUCE = 8  # param-ok: a JPEG decodes at 1/1, 1/2, 1/4 or 1/8 scale


class TooLargeImage(CoverError, ValueError):
    """A picture or PDF over the limits; the message is meant for the person who sent it."""


def max_pixels(params: Any | None = None) -> int:
    """`limits.image_max_mp` in pixels (server-only, so the company default when not given)."""
    if params is None:
        from coverengine.params import Registry

        params = Registry.load(None).resolve()
    return int(float(params["limits.image_max_mp"]) * MEGA)


def open_image(data: bytes, limit_px: int, draft_edge: int | None = None) -> Any:
    """The picture in `data`, decoded, or TooLargeImage / OSError. A JPEG is decoded at 1/2, 1/4
    or 1/8 scale when that keeps it under the cap (a 50 MP phone photo is fine), and further
    while its long side stays at least `draft_edge` (the picture is made that small anyway)."""
    from PIL import Image

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            im = Image.open(io.BytesIO(data))
            w, h = im.size
            if w <= 0 or h <= 0:
                raise TooLargeImage("the picture has no size")
            if im.format == "JPEG":
                k = 1
                while k < JPEG_MAX_REDUCE and (
                    (w // k) * (h // k) > limit_px
                    or (draft_edge and max(w, h) // (k * 2) >= draft_edge)
                ):
                    k *= 2
                if k > 1:
                    im.draft(im.mode, (-(-w // k), -(-h // k)))
                    w, h = im.size
            if w * h > limit_px:
                raise TooLargeImage(
                    f"the picture is too large ({w} x {h} pixels; at most "
                    f"{limit_px / MEGA:g} megapixels)"
                )
            im.load()
        except (Image.DecompressionBombWarning, Image.DecompressionBombError):
            raise TooLargeImage("the picture is too large") from None
    return im


def check_pdf(pdf: Path | bytes, max_pages: int, limit_px: int, dpi: float) -> int:
    """The PDF's page count, or TooLargeImage when it has more than `max_pages` pages or a
    page that at `dpi` would be more than `limit_px` pixels."""
    import pymupdf

    try:
        if isinstance(pdf, bytes):
            doc = pymupdf.open(stream=pdf, filetype="pdf")
        else:
            doc = pymupdf.open(pdf)
    except Exception as exc:  # noqa: BLE001 - pymupdf raises its own kinds
        raise TooLargeImage(f"not a readable PDF: {exc}") from None
    with doc:
        n = int(doc.page_count)
        if n > max_pages:
            raise TooLargeImage(f"the PDF has {n} pages; at most {max_pages}")
        for page in doc.pages():
            if page_pixels(page, dpi) > limit_px:
                raise TooLargeImage("a page of the PDF is too large to show")
    return n


def page_pixels(page: Any, dpi: float) -> float:
    r = page.rect
    return (r.width / POINTS_PER_INCH * dpi) * (r.height / POINTS_PER_INCH * dpi)


def safe_dpi(page: Any, dpi: float, limit_px: int) -> float:
    """`dpi`, or less so the rendered page stays within `limit_px` pixels."""
    px = page_pixels(page, dpi)
    return dpi if px <= limit_px else dpi * math.sqrt(limit_px / px)


def check_upload_pdf(pdf: Path | bytes, params: Any | None = None) -> int:
    """An uploaded drawing within limits.pdf_max_pages pages, each page within
    limits.image_max_mp at limits.pdf_render_dpi; its page count or TooLargeImage."""
    if params is None:
        from coverengine.params import Registry

        params = Registry.load(None).resolve()
    return check_pdf(pdf, int(params["limits.pdf_max_pages"]), max_pixels(params),
                     float(params["limits.pdf_render_dpi"]))  # fmt: skip
