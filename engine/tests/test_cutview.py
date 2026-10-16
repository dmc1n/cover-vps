"""The Cutting file view's renderer (ADR-147): cut.dxf read back and drawn, on a test model.

The test model is a skirt piece with its vents (openings, hoods with the logo of ADR-146) and a
top, exported for the cutting table as `cover export` does; the renderer reads only the DXF."""

import io
from pathlib import Path
from typing import Any

import ezdxf
import numpy as np
import pytest
from coverengine.export import cutview as cv
from coverengine.export.cut import write_export
from coverengine.finish.finish import finish, finished_set
from coverengine.params import Registry
from tests.test_finish import FINISH, doc, square

SETTINGS = ("CUT", "PEN", 0.025, 30.0, 50.0)


def params(**overrides: Any) -> Any:
    return Registry.load().resolve(trial={**FINISH, **overrides})


def model(tmp: Path, **overrides: Any) -> tuple[Path, list[Any]]:
    """A built test model: a skirt piece 120 x 87 cm with its vents and hoods, and a top."""
    skirt = square("skirt-front", 1200, ["hem", "seam", "seam", "seam"], [False] * 4)
    skirt["outline_mm"] = [[0, 0], [1200, 0], [1200, 870], [0, 870]]
    top = square("top", 900, ["seam", "seam", "seam", "seam"], [True] * 4)
    top["id"] = "P2"
    for panel, at in ((skirt, [600, 600]), (top, [450, 450])):  # the labels pattern.json carries
        panel["pen"] = [{"type": "label", "text": panel["name"].upper(), "at": at}]
    d = doc(skirt, top)
    p = params(**overrides)
    pieces, warnings = finish(d, p)
    tmp.mkdir(parents=True, exist_ok=True)
    write_export(tmp, pieces, finished_set(d, pieces, warnings, p), p)
    return tmp / "cut.dxf", pieces


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[bytes, list[Any], str, dict[str, Any]]:
    path, pieces = model(tmp_path_factory.mktemp("cutview") / "m")
    data = path.read_bytes()
    svg, meta = cv.render(data, *SETTINGS)
    return data, pieces, svg, meta


def test_every_piece_of_the_cutting_file_with_its_name_and_size(built: Any) -> None:
    data, pieces, svg, meta = built
    copies = sum(pc.quantity for pc in pieces)
    assert len(meta["pieces"]) == copies
    names = sorted(p["name"] for p in meta["pieces"])
    assert names == sorted(
        f"{pc.id} {pc.name.upper()}" for pc in pieces for _ in range(pc.quantity)
    )
    for pc in pieces:
        w, h = np.ptp(pc.cut, axis=0)
        mine = [p for p in meta["pieces"] if p["name"] == f"{pc.id} {pc.name.upper()}"]
        for p in mine:
            assert p["size_mm"] == pytest.approx([w, h], abs=0.1)
    skirt = next(p for p in meta["pieces"] if p["name"].endswith("SKIRT-FRONT"))
    skirt_piece = next(pc for pc in pieces if pc.name == "skirt-front")
    assert skirt["openings"] == len(skirt_piece.openings) > 0  # the vents
    assert meta["fingerprint"] == cv.fingerprint(data)
    assert meta["skipped"] == {} and meta["loose_cut"] == 0


def test_a_rectangles_edges_corner_to_corner(built: Any) -> None:
    _, pieces, _, meta = built
    top = next(p for p in meta["pieces"] if p["name"].endswith("TOP"))
    w, h = top["size_mm"]
    assert len(top["edges"]) == 4
    assert sorted(e["length_mm"] for e in top["edges"]) == pytest.approx([h, h, w, w], abs=0.1)
    assert top["perimeter_mm"] == pytest.approx(2 * (w + h), abs=0.5)
    x0, y0, x1, y1 = top["box"]
    assert x1 - x0 == pytest.approx(w, abs=0.2) and y1 - y0 == pytest.approx(h, abs=0.2)
    for e in top["edges"]:
        assert x0 - 0.2 <= e["mid"][0] <= x1 + 0.2 and y0 - 0.2 <= e["mid"][1] <= y1 + 0.2


def test_the_drawing_has_cut_pen_and_texts_from_the_dxf(built: Any) -> None:
    data, _, svg, meta = built
    doc_ = ezdxf.read(io.StringIO(data.decode()))
    texts = [e.dxf.text for e in doc_.modelspace() if e.dxftype() == "TEXT"]
    cut = [e for e in doc_.modelspace() if e.dxf.layer == "CUT"]
    pen = [e for e in doc_.modelspace() if e.dxf.layer == "PEN" and e.dxftype() != "TEXT"]
    assert meta["layers"]["cut"] == len(cut) and meta["layers"]["pen"] == len(pen)
    assert meta["layers"]["texts"] == len(texts)
    assert svg.count("<text ") == len(texts)
    for word in ("LOGO", "TOP: SEW TO COVER", "OPEN EDGE, INSERT"):
        assert f">{word}<" in svg
    assert svg.count('class="cv-piece"') == len(meta["pieces"])
    for g in ("cv-cut", "cv-pen", "cv-text"):
        assert f'class="{g}"' in svg
    assert "<script" not in svg and "SECTION" not in svg and "AcDb" not in svg
    assert cv.render(data, *SETTINGS)[0] == svg  # deterministic


def test_the_watermark_is_part_of_the_drawing(built: Any) -> None:
    _, _, svg, meta = built
    marked = cv.watermarked(svg, meta, "test r1")
    assert cv.WATERMARK in marked and 'data-watermark="1"' in marked
    assert marked.count(cv.WATERMARK) >= 3  # across the sheet, in the band, in the title
    assert "<title>PREVIEW – NOT FOR CUTTING</title>" in marked
    band = cv.band_mm(meta)
    assert f'viewBox="0 -{cv._num(band)} ' in marked  # the band above the drawing
    clean = cv.clean(svg)
    assert cv.WATERMARK not in clean and "<!--WATERMARK" not in clean


def test_drawn_from_the_dxf_not_from_the_export_s_svg(tmp_path: Path) -> None:
    """A circle added to the DXF by hand is drawn and counted as a piece; another layer is
    drawn as "other"; centimetre units are scaled to millimetres."""
    path, pieces = model(tmp_path / "m")
    doc_ = ezdxf.readfile(path)
    doc_.modelspace().add_circle((-500, -500), 100, dxfattribs={"layer": "CUT"})
    doc_.modelspace().add_line((0, -900), (100, -900), dxfattribs={"layer": "NOTES"})
    buf = io.StringIO()
    doc_.write(buf)
    _, meta = cv.render(buf.getvalue().encode(), *SETTINGS)
    assert len(meta["pieces"]) == sum(pc.quantity for pc in pieces) + 1
    circle = next(p for p in meta["pieces"] if p["size_mm"] == pytest.approx([200, 200], abs=0.5))
    assert len(circle["edges"]) == 1 and circle["perimeter_mm"] == pytest.approx(628.3, abs=1)
    assert meta["layers"]["other"] == 1 and "NOTES" in meta["layers"]["names"]
    cm = ezdxf.new("R2010", units=5)
    cm.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True,
                                   dxfattribs={"layer": "CUT"})  # fmt: skip
    buf = io.StringIO()
    cm.write(buf)
    _, meta = cv.render(buf.getvalue().encode(), *SETTINGS)
    assert meta["pieces"][0]["size_mm"] == pytest.approx([100, 50])


def test_stroked_texts_and_a_piece_without_a_label(tmp_path: Path) -> None:
    path, pieces = model(tmp_path / "m", **{"export.text_mode": "strokes"})
    svg, meta = cv.render(path.read_bytes(), *SETTINGS)
    assert meta["layers"]["texts"] == 0 and "<text " not in svg
    assert len(meta["pieces"]) == sum(pc.quantity for pc in pieces)
    assert all(p["name"].startswith("#") for p in meta["pieces"])


def test_compare_two_revisions(tmp_path: Path) -> None:
    """The vent logo moved (ADR-146) is a pen-only change; a bigger top is a size change; the
    revision stamp alone is no change."""
    a, _ = model(tmp_path / "a")
    b, _ = model(tmp_path / "b", **{"features.vent_logo_above_edge_mm": 120})
    ma = cv.render(a.read_bytes(), *SETTINGS)[1]
    mb = cv.render(b.read_bytes(), *SETTINGS)[1]
    out = cv.compare(ma, mb, 1.0)
    hoods = [r for r in out["pieces"] if r["name"].endswith("VENT-HOOD")]
    assert hoods and all(r["status"] == "pen" for r in hoods)
    assert all(r["status"] == "same" for r in out["pieces"] if r not in hoods)
    assert out["pen_only"] and out["cut_same"]
    assert cv.compare(ma, ma, 1.0)["counts"]["same"] == len(ma["pieces"])
    c, _ = model(tmp_path / "c", **{"stitching.allowance_mm": 25})
    mc = cv.render(c.read_bytes(), *SETTINGS)[1]
    out = cv.compare(ma, mc, 1.0)
    assert out["counts"]["size"] >= 2 and not out["cut_same"]
    fewer = dict(mc, pieces=mc["pieces"][:-1], _geometry=mc[cv.GEOMETRY][:-1])
    out = cv.compare(mc, fewer, 1.0)
    assert out["counts"]["removed"] == 1
    assert cv.compare(fewer, mc, 1.0)["counts"]["added"] == 1


def test_a_big_cover_draws_quickly() -> None:
    """Many pieces with long outlines and many marks (a big lounge set) stay well under a
    second or two (the cache makes the next look instant)."""
    import time

    sheet = ezdxf.new("R2010", units=4)
    msp = sheet.modelspace()
    rng = np.random.default_rng(1)
    for k in range(60):
        t = np.linspace(0, 2 * np.pi, 800, endpoint=False)
        r = 400 + 30 * np.sin(5 * t) + rng.uniform(0, 2, len(t))
        ox, oy = (k % 10) * 1000, (k // 10) * 1000
        msp.add_lwpolyline(np.column_stack([ox + r * np.cos(t), oy + r * np.sin(t)]),
                           close=True, dxfattribs={"layer": "CUT"})  # fmt: skip
        for j in range(40):
            msp.add_line((ox + j, oy), (ox + j, oy + 50), dxfattribs={"layer": "PEN"})
        msp.add_text(f"P{k + 1} PIECE", height=15, dxfattribs={"layer": "PEN"}).set_placement(
            (ox - 50, oy)
        )
    buf = io.StringIO()
    sheet.write(buf)
    start = time.perf_counter()
    _, meta = cv.render(buf.getvalue().encode(), *SETTINGS)
    assert len(meta["pieces"]) == 60
    assert time.perf_counter() - start < 6
