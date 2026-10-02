import json
from pathlib import Path
from typing import Any

import pytest
from coverengine.catalogue import compare, info, revisions, save_revision, set_info
from coverengine.errors import CoverError
from coverengine.params import resolve_model
from coverengine.params.registry import list_families


def model_dir(tmp_path: Path, cover: dict[str, Any] | None = None) -> Path:
    d = tmp_path / "m"
    d.mkdir()
    if cover is not None:
        (d / "cover.json").write_text(json.dumps(cover))
    return d


def test_family_preset_is_layer_two(tmp_path: Path) -> None:
    assert "table" in list_families()
    d = model_dir(tmp_path, {"family": "table"})
    p = resolve_model(d)
    assert p["hull.support"] == "balloons" and p.source("hull.support") == "preset"
    assert p["features.middle_cord"] is True  # table covers: the second drawcord
    d2 = tmp_path / "m2"
    d2.mkdir()
    (d2 / "cover.json").write_text(
        json.dumps({"family": "table", "parameters": {"hull": {"support": "none"}}})
    )
    q = resolve_model(d2)
    assert q["hull.support"] == "none" and q.source("hull.support") == "model"  # model wins


def test_unknown_family_is_an_error(tmp_path: Path) -> None:
    d = model_dir(tmp_path, {"family": "spaceship"})
    with pytest.raises(CoverError):
        resolve_model(d)
    with pytest.raises(CoverError):
        set_info(d, {"family": "spaceship"})


def test_info_keeps_the_rest_of_cover_json(tmp_path: Path) -> None:
    d = model_dir(tmp_path, {"parameters": {"hull": {"clearance_mm": 12}}})
    assert info(d)["status"] == "draft"
    out = set_info(d, {"status": "checked", "tags": ["lounge", " sofa ", ""], "notes": "hi"})
    assert out == {
        "family": None,
        "category": None,
        "status": "checked",
        "tags": ["lounge", "sofa"],
        "notes": "hi",
    }
    doc = json.loads((d / "cover.json").read_text())
    assert doc["parameters"] == {"hull": {"clearance_mm": 12}}
    with pytest.raises(CoverError):
        set_info(d, {"status": "shipped"})


def pattern(width: float, clearance: float) -> dict[str, Any]:
    return {
        "parameter_hash": f"h{width}{clearance}",
        "summary": {"panels": 1, "max_stretch_pct": 0.5},
        "parameters": {"hull": {"clearance_mm": clearance}},
        "panels": [{"name": "top", "flat_width_mm": width, "flat_length_mm": 900.0}],
        "warnings": [],
    }


def test_revisions_and_compare(tmp_path: Path) -> None:
    d = model_dir(tmp_path)
    (d / "pattern.json").write_text(json.dumps(pattern(500.0, 10)))
    assert save_revision(d, {})["number"] == 1
    (d / "pattern.json").write_text(json.dumps(pattern(503.0, 12)))
    r2 = save_revision(d, {"hull.clearance_mm": 12})
    assert r2["number"] == 2 and r2["trial"] == ["hull.clearance_mm"]
    assert [r["number"] for r in revisions(d)] == [1, 2]
    a = json.loads((d / "revisions" / "001" / "pattern.json").read_text())
    b = json.loads((d / "revisions" / "002" / "pattern.json").read_text())
    diff = compare(a, b)
    assert diff["panels"][0]["name"] == "top"
    assert diff["settings"] == [{"key": "hull.clearance_mm", "before": 10, "after": 12}]
    assert compare(a, a) == {"panels": [], "settings": []}
