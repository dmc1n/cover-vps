"""The drawing read by the program from its own lines (ADR-072)."""

from pathlib import Path

import numpy as np
import pymupdf
import pytest
from coverengine.drawing_vectors import outline_shape


def _pdf(tmp_path: Path, label: str) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    t = np.linspace(0, 2 * np.pi, 80, endpoint=False)
    r = 1 + 0.2 * np.cos(2 * t)
    pts = [pymupdf.Point(300 + 120 * r[i] * np.cos(t[i]), 250 + 80 * r[i] * np.sin(t[i]))
           for i in range(80)]  # fmt: skip
    shape = page.new_shape()
    shape.draw_polyline([*pts, pts[0]])
    shape.finish(closePath=True)
    shape.commit()
    page.insert_text((60, 500), "45.0cm 17.7in Height")
    page.insert_textbox(pymupdf.Rect(40, 120, 200, 200), label)
    path = tmp_path / "S99.pdf"
    doc.save(path)
    return path


def test_the_outline_is_scaled_by_its_written_circumference(tmp_path: Path) -> None:
    read = outline_shape(_pdf(tmp_path, "141.1in circumference"))
    assert read is not None and read["scaled_by"]["size"] == "circumference"
    assert read["plan_cm"]["circumference"] == pytest.approx(358.4, abs=0.1)
    assert read["shape"]["height_cm"] == 45.0
    assert read["conflicts"] == []


def test_a_written_size_that_disagrees_is_reported_not_chosen_silently(tmp_path: Path) -> None:
    """S45: "152.4" next to "141.1in circumference" cannot both be true."""
    read = outline_shape(_pdf(tmp_path, "152.4\n141.1in circumference"))
    assert read is not None
    assert read["plan_cm"]["circumference"] == pytest.approx(358.4, abs=0.1)
    assert [c["written_cm"] for c in read["conflicts"]] == [152.4]


def test_a_drawing_without_a_closed_free_outline_gives_none(tmp_path: Path) -> None:
    doc = pymupdf.open()
    doc.new_page().insert_text((60, 500), "Height 45cm")
    doc.save(tmp_path / "box.pdf")
    assert outline_shape(tmp_path / "box.pdf") is None


def test_vents_without_a_number_are_counted_from_their_arrows(tmp_path: Path) -> None:
    """S21: "Air Vents" with six arrows and no number: six vents (ADR-075)."""
    from coverengine.drawing_vectors import features

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((300, 300), "Air Vents")
    leaders, heads = page.new_shape(), page.new_shape()
    for tx, ty in ((100, 500), (200, 520), (420, 480)):
        leaders.draw_line((310, 305), (tx, ty))
        dx, dy = tx - 310, ty - 305
        n = (dx**2 + dy**2) ** 0.5
        ux, uy = dx / n, dy / n
        bx, by = tx - 5 * ux, ty - 5 * uy
        heads.draw_polyline([(tx, ty), (bx - 1.6 * uy, by + 1.6 * ux),
                             (bx + 1.6 * uy, by - 1.6 * ux), (tx, ty)])  # fmt: skip
    leaders.finish(color=(0, 0, 0))
    leaders.commit()
    heads.finish(color=(0, 0, 0), fill=(0, 0, 0))
    heads.commit()
    doc.save(tmp_path / "v.pdf")
    got = features(tmp_path / "v.pdf")
    assert (got["vents_total"], got["vents_from"]) == (3, "arrows")
