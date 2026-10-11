"""A model kept but needing no cover (Rens, 9 Oct 2026, question 12: the Portofino daybed with
roof): `"no_cover": true` in its cover.json. The catalogue and `cover model` set and show it, the
matching never offers it (not as an existing, a similar or a drawing cover), the report lists it
as "no cover", and models without the mark behave as before."""

import csv
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from coverengine import match, match_drawings, quote, stepcache
from coverengine.catalogue import info, is_no_cover, no_cover, set_info
from coverengine.cli import main
from coverengine.errors import CoverError
from coverengine.params import Registry

P = Registry.load(None).resolve(
    trial={"match.tight_cm": 1.0, "match.loose_cm": 4.0, "match.tight_falloff_cm": 4.0,
           "match.loose_falloff_cm": 20.0, "match.weights": "1,1,1",
           "match.threshold_pct": 90.0, "match.choice_pct": 80.0}
)  # fmt: skip
DINING = {"table_length_cm": 238, "table_width_cm": 100, "table_height_cm": 76}


def _cover(models: Path, mid: str, size_cm: tuple[float, float, float], **cover: Any) -> Path:
    d = models / mid
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps({"category": "Shop › Tafels", **cover}))
    (d / "model.json").write_text(json.dumps({"size_mm": [x * 10 for x in size_cm]}))
    return d


def _later(path: Path) -> None:
    t = time.time() + 5
    os.utime(path, (t, t))


def test_the_mark_round_trips_through_the_catalogue(tmp_path: Path) -> None:
    d = _cover(tmp_path, "suns-daybed-with-roof-portofino", (200, 150, 220), status="draft")
    assert info(d)["no_cover"] is False and info(d)["no_cover_reason"] == ""
    assert no_cover(d) is False and no_cover(tmp_path / "nothing-here") is False
    out = set_info(d, {"no_cover": True, "no_cover_reason": " the roof is its own cover "})
    assert out["no_cover"] is True and out["no_cover_reason"] == "the roof is its own cover"
    doc = json.loads((d / "cover.json").read_text())
    assert doc["no_cover"] is True and doc["no_cover_reason"] == "the roof is its own cover"
    assert doc["category"] == "Shop › Tafels" and doc["status"] == "draft"  # the rest kept
    assert no_cover(d) is True and is_no_cover(doc)
    out = set_info(d, {"no_cover": False})  # off again: the mark and its reason go
    assert out["no_cover"] is False
    doc = json.loads((d / "cover.json").read_text())
    assert "no_cover" not in doc and "no_cover_reason" not in doc
    set_info(d, {"no_cover_reason": "a reason alone"})  # a reason only lives next to the mark
    assert "no_cover_reason" not in json.loads((d / "cover.json").read_text())
    with pytest.raises(CoverError):
        set_info(d, {"no_cover": "yes"})
    assert not is_no_cover({"no_cover": "true"}) and not is_no_cover(None)


def test_cover_model_sets_and_shows_the_mark(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    d = _cover(tmp_path, "suns-daybed-with-roof-portofino", (200, 150, 220))
    assert main(["model", str(d), "--no-cover", "yes", "--no-cover-reason", "has a roof"]) == 0
    assert "no cover (not in the shop, not on the Desk): has a roof" in capsys.readouterr().out
    assert info(d)["no_cover"] is True and info(d)["no_cover_reason"] == "has a roof"
    assert main(["model", str(d)]) == 0
    assert "no cover" in capsys.readouterr().out
    assert main(["model", str(d), "--no-cover", "no"]) == 0
    assert "no cover" not in capsys.readouterr().out and info(d)["no_cover"] is False
    assert main(["model", str(d), "--no-cover", "no", "--no-cover-reason", "x"]) == 2
    assert main(["model", str(d), "--no-cover-reason", "roof"]) == 0  # a reason marks it
    assert no_cover(d)


def test_the_matching_never_offers_a_model_that_needs_no_cover(tmp_path: Path) -> None:
    _cover(tmp_path, "suns-dining-table-a-240", (240, 100, 76), no_cover=True)
    _cover(tmp_path, "suns-dining-table-b-200", (200, 90, 75))
    assert match.card(tmp_path / "suns-dining-table-a-240") is None
    assert match.card(tmp_path / "suns-dining-table-b-200") is not None  # as before
    ids = [c["model_id"] for c in match.cards(tmp_path)]
    assert ids == ["suns-dining-table-b-200"]
    r = match.match("dining_set", DINING, tmp_path, P)
    assert [m["model_id"] for m in r["matches"]] == ["suns-dining-table-b-200"]
    assert r["decision"] == "custom"  # the exact one is not offered: no "existing" cover
    assert match.entry(tmp_path, "suns-dining-table-a-240", "dining_set", DINING, P) is None
    near = quote.nearest("dining_set", DINING, tmp_path)  # "similar covers we make"
    assert [n["model_id"] for n in near] == ["suns-dining-table-b-200"]


def test_marking_a_model_drops_it_from_the_cached_cards(tmp_path: Path) -> None:
    _cover(tmp_path, "suns-dining-table-a-240", (240, 100, 76))
    r = match.match("dining_set", DINING, tmp_path, P)
    assert r["matches"][0]["model_id"] == "suns-dining-table-a-240"  # without the mark: offered
    d = tmp_path / "suns-dining-table-a-240"
    set_info(d, {"no_cover": True})
    _later(d / "cover.json")
    assert match.match("dining_set", DINING, tmp_path, P)["matches"] == []
    set_info(d, {"no_cover": False})
    _later(d / "cover.json")
    assert match.match("dining_set", DINING, tmp_path, P)["matches"][0]["score_pct"] == 100.0


def test_an_approved_drawing_cover_marked_no_cover_is_not_offered(tmp_path: Path) -> None:
    d = tmp_path / "drawing-t1"
    d.mkdir()
    (d / "cover.json").write_text(json.dumps({"notes": "Drawing T1", "no_cover": True,
                                              "match": {"kind": "dining_set"}}))  # fmt: skip
    (d / "model.json").write_text(json.dumps({"size_mm": [3500, 1660, 870]}))
    (d / "desk.json").write_text(json.dumps({"code": "T1", "status": "approved"}))
    r = match_drawings.review(d, P)
    assert r is not None and r["offered"] is False and r["why_not"] == "no cover"
    assert match.card(d, None, None, P) is None
    assert match_drawings.owners(tmp_path, P) == {}
    set_info(d, {"no_cover": False})
    assert match_drawings.review(d, P)["offered"] is True  # type: ignore[index]


def test_the_mark_does_not_make_the_steps_run_again(tmp_path: Path) -> None:
    d = _cover(tmp_path, "suns-x", (100, 100, 80))
    before = stepcache._file_hash(d / "cover.json")
    set_info(d, {"no_cover": True, "no_cover_reason": "roof"})
    assert stepcache._file_hash(d / "cover.json") == before


def test_the_report_lists_it_as_no_cover(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = tmp_path / "models"
    _cover(models, "suns-daybed-with-roof-portofino", (200, 150, 220), no_cover=True,
           no_cover_reason="has a roof")  # fmt: skip
    _cover(models, "suns-chair", (60, 60, 90))
    out = tmp_path / "report"
    assert main(["report", "--models", str(models), "--out", str(out)]) == 0
    assert "1 failed, 1 need no cover" in capsys.readouterr().out
    rows = {r["id"]: r for r in csv.DictReader((out / "catalogue.csv").open())}
    assert rows["suns-daybed-with-roof-portofino"]["grade"] == "no cover"
    assert rows["suns-daybed-with-roof-portofino"]["reasons"] == "has a roof"
    assert rows["suns-chair"]["grade"] == "failed"  # without the mark: as before
