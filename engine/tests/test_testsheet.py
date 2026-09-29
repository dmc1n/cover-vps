import math
from collections import Counter
from pathlib import Path

import ezdxf
import pytest
from coverengine.export import strokefont
from coverengine.export.testsheet import load_spec, write_all

SPEC = load_spec()
VARIANTS = {v["id"]: v for v in SPEC["variants"]}


@pytest.fixture(scope="module")
def sheets(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("sheets")
    write_all(out)
    return {vid: out / v["file"] for vid, v in VARIANTS.items()}


def _cut_entities(doc: ezdxf.document.Drawing, variant: dict) -> list:
    cut = str(variant["cut_layer"])
    ents = [e for e in doc.modelspace() if e.dxf.layer == cut]
    if variant["colors"] == "entity":
        ents = [e for e in ents if e.dxf.color == SPEC["colors"]["cut"]]
    return ents


@pytest.mark.parametrize("vid", list(VARIANTS))
def test_audit_clean(sheets: dict[str, Path], vid: str) -> None:
    doc = ezdxf.readfile(sheets[vid])
    auditor = doc.audit()
    assert not auditor.errors
    assert not auditor.fixes


@pytest.mark.parametrize("vid", list(VARIANTS))
def test_cut_geometry(sheets: dict[str, Path], vid: str) -> None:
    v = VARIANTS[vid]
    doc = ezdxf.readfile(sheets[vid])
    ents = _cut_entities(doc, v)
    assert len(ents) == len(SPEC["cut"])
    types = Counter(e.dxftype() for e in ents)
    poly = "POLYLINE" if v["dxf_version"] == "R12" else "LWPOLYLINE"
    assert types == {poly: len(SPEC["cut"]) - 1, "CIRCLE": 1}
    for e in ents:
        if e.dxftype() != "CIRCLE":
            assert e.is_closed
    circle = next(e for e in ents if e.dxftype() == "CIRCLE")
    o1 = next(c for c in SPEC["cut"] if c["id"] == "O1")
    assert circle.dxf.radius == o1["radius"]
    assert tuple(circle.dxf.center)[:2] == tuple(o1["center"])


def test_scale_strip_exact(sheets: dict[str, Path]) -> None:
    doc = ezdxf.readfile(sheets["A"])
    r1 = next(c for c in SPEC["cut"] if c["id"] == "R1")
    first = doc.modelspace().query("LWPOLYLINE[layer=='CUT']")[0]
    xs = [p[0] for p in first.get_points("xy")]
    ys = [p[1] for p in first.get_points("xy")]
    assert (max(xs) - min(xs), max(ys) - min(ys)) == tuple(r1["size"])
    assert (min(xs), min(ys)) == tuple(r1["at"])


def test_bulge_circle_and_corners(sheets: dict[str, Path]) -> None:
    doc = ezdxf.readfile(sheets["A"])
    polys = doc.modelspace().query("LWPOLYLINE[layer=='CUT']")
    bulges = [[round(p[2], 12) for p in e.get_points("xyb")] for e in polys]
    assert [1.0, 1.0] in bulges  # O2: two half circles
    corner = round(math.tan(math.pi / 8), 12)
    assert any(b.count(corner) == 4 for b in bulges)  # R3: four quarter-circle corners


def test_layers_and_units(sheets: dict[str, Path]) -> None:
    for vid, v in VARIANTS.items():
        doc = ezdxf.readfile(sheets[vid])
        assert str(v["cut_layer"]) in doc.layers
        assert str(v["pen_layer"]) in doc.layers
        if v["dxf_version"] != "R12":
            assert doc.header["$INSUNITS"] == 4
        pen_layer = str(v["pen_layer"])
        pen = [e for e in doc.modelspace() if e.dxf.layer == pen_layer]
        if v["colors"] == "entity":
            pen = [e for e in pen if e.dxf.color == SPEC["colors"]["pen"]]
        assert pen
        has_text = any(e.dxftype() == "TEXT" for e in pen)
        assert has_text == (v["text"] == "text"), vid


def test_colours_only_variant(sheets: dict[str, Path]) -> None:
    doc = ezdxf.readfile(sheets["D"])
    colors = Counter(e.dxf.color for e in doc.modelspace())
    assert set(colors) == {SPEC["colors"]["cut"], SPEC["colors"]["pen"]}
    assert {e.dxf.layer for e in doc.modelspace()} == {"0"}


def test_deterministic(sheets: dict[str, Path], tmp_path: Path) -> None:
    write_all(tmp_path)
    for p in sheets.values():
        assert p.read_bytes() == (tmp_path / p.name).read_bytes(), p.name


def test_committed_sheets_up_to_date(sheets: dict[str, Path]) -> None:
    """testdata/machine/*.dxf are what the owner cuts; they must match the generator."""
    committed = Path(__file__).resolve().parents[2] / "testdata" / "machine"
    for p in sheets.values():
        assert (committed / p.name).read_bytes() == p.read_bytes(), (
            f"run make testsheets ({p.name})"
        )


def test_strokefont_covers_sheet_text() -> None:
    texts = [str(i["text"]) for i in SPEC["pen"] if i["type"] == "text"]
    texts += [f"{SPEC['title']} - VARIANT {v['id']} - {v['note']}" for v in SPEC["variants"]]
    for t in texts:
        assert all(strokefont.supported(ch) for ch in t), t


def test_strokefont_geometry() -> None:
    strokes = strokefont.text_strokes("H", (10.0, 20.0), 12.0)
    pts = [p for s in strokes for p in s]
    assert min(y for _, y in pts) == 20.0
    assert max(y for _, y in pts) == 32.0
    assert strokefont.text_width("HH", 12.0) == pytest.approx(20.0)  # advance 12 + glyph 8
    with pytest.raises(ValueError):
        strokefont.glyph("~")
