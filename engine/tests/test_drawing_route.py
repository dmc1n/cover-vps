"""Route A: a drawing (PDF) read by the program and built as a cover, or "needs a person"
(ADR-081)."""

import json
from pathlib import Path

import numpy as np
import pymupdf
from coverengine.drawing_route import NEEDS_PERSON, build
from coverengine.params import Registry


def _kidney_pdf(path: Path) -> Path:
    """A plan drawn as one closed vector path, its circumference and height written, 4 vents."""
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
    page.insert_textbox(pymupdf.Rect(40, 120, 200, 200), "141.1in circumference")
    page.insert_text((60, 560), "4 Air Pocket")
    doc.save(path)
    return path


def test_a_drawn_outline_becomes_a_cover_with_the_drawings_vents(tmp_path: Path) -> None:
    pdf = _kidney_pdf(tmp_path / "cover 999 - S99.pdf")
    model = tmp_path / "models" / "drawing-s99"
    doc = build(pdf, model, Registry.load(None).resolve(), code="S99", log=lambda s: None)
    assert doc["status"] == "built" and doc["reader"] == "outline"
    assert (model / "reference.pdf").is_file() and (model / "cut.dxf").is_file()
    cover = json.loads((model / "cover.json").read_text())
    assert cover["parameters"]["features"]["vents_total"] == 4
    assert cover["parameters"]["hull"]["top"] == "given"
    fin = json.loads((model / "finished.json").read_text())
    assert sum(p["quantity"] for p in fin["pieces"] if p["name"] == "vent-hood") == 4
    read = json.loads((model / "drawing_read.json").read_text())
    assert read["pieces"] >= 2 and read["features"]["vents_from"] == "written"
    assert read["outline"]["plan_cm"]["circumference"] == 358.4


def test_a_drawing_it_cannot_read_builds_nothing_and_says_why(tmp_path: Path) -> None:
    doc = pymupdf.open()
    doc.new_page().insert_text((60, 500), "Cover 123, WeatherMax, Charcoal")
    pdf = tmp_path / "x.pdf"
    doc.save(pdf)
    model = tmp_path / "models" / "drawing-x"
    out = build(pdf, model, Registry.load(None).resolve(), code="X", log=lambda s: None)
    assert out["status"] == NEEDS_PERSON and out["reasons"]
    assert not (model / "model.glb").exists()  # nothing guessed
    check = json.loads((model / "check.json").read_text())
    assert check["outcome"] == "person to check"  # the Desk puts it first
