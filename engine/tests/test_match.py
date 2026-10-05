"""ADR-064: the customer's sizes against the covers we already make."""

import json
from pathlib import Path

from coverengine import match
from coverengine.params import Registry

P = Registry.load(None).resolve(
    trial={"match.tight_cm": 1.0, "match.loose_cm": 4.0, "match.tight_falloff_cm": 4.0,
           "match.loose_falloff_cm": 20.0, "match.weights": "1,1,1",
           "match.threshold_pct": 90.0, "match.choice_pct": 80.0}
)  # fmt: skip


def _cover(models: Path, mid: str, category: str, size_cm: tuple[float, float, float]) -> None:
    d = models / mid
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps({"category": f"Shop › {category}"}))
    (d / "model.json").write_text(json.dumps({"size_mm": [x * 10 for x in size_cm]}))


def test_the_kind_of_a_catalogue_cover() -> None:
    assert match.kind_of("suns-dining-nova-dia-120", "Tafels", [120, 120, 77]) == "round_set"
    assert match.kind_of("suns-dining-table-erice-240", "Tafels", [240, 100, 76]) == "dining_set"
    assert match.kind_of("suns-lounge-fiave-l-part-left", "Sofasets", [280, 90, 80]) == (
        "corner_sofa"
    )
    assert match.kind_of("suns-corner-kota", "Sofasets", [110, 110, 89]) == "item"  # a module
    assert match.kind_of("suns-2-seater-kota", "Sofasets", [180, 115, 88]) == "sofa"


def test_roomier_falls_slowly_tighter_falls_fast() -> None:
    assert match.size_score(0.0, P) == 1.0
    assert match.size_score(4.0, P) == 1.0  # within the allowed room
    assert abs(match.size_score(9.0, P) - 0.75) < 1e-9  # 5 cm over: a quarter of 20 cm
    assert match.size_score(-1.0, P) == 1.0
    assert abs(match.size_score(-3.0, P) - 0.5) < 1e-9  # 2 cm too small: half of 4 cm
    assert match.size_score(-6.0, P) == 0.0  # does not go on


def test_the_best_cover_and_what_to_offer(tmp_path: Path) -> None:
    _cover(tmp_path, "suns-dining-table-a-240", "Tafels", (240, 100, 76))
    _cover(tmp_path, "suns-dining-table-b-200", "Tafels", (200, 90, 75))
    _cover(tmp_path, "suns-dining-nova-dia-140", "Tafels", (140, 140, 76))
    _cover(tmp_path, "suns-2-seater-x", "Sofasets", (180, 100, 88))
    given = {"table_length_cm": 238, "table_width_cm": 100, "table_height_cm": 76}
    r = match.match("dining_set", given, tmp_path, P)
    assert r["matches"][0]["model_id"] == "suns-dining-table-a-240"
    assert r["matches"][0]["score_pct"] == 100.0 and r["decision"] == "existing"
    assert all("dia" not in m["model_id"] and "seater" not in m["model_id"] for m in r["matches"])
    longer = match.match("dining_set", {**given, "table_length_cm": 250}, tmp_path, P)
    assert longer["matches"][0]["score_pct"] == 0.0  # 10 cm too short: never a fit
    assert longer["decision"] == "custom"
    between = match.match("dining_set", {**given, "table_length_cm": 230}, tmp_path, P)
    assert 80 <= between["matches"][0]["score_pct"] < 90 and between["decision"] == "choice"


def test_the_other_hand_of_an_l_is_no_match(tmp_path: Path) -> None:
    _cover(tmp_path, "suns-lounge-x-l-part-left", "Sofasets", (280, 220, 80))
    given = {"long_side_cm": 280, "short_side_cm": 220, "back_height_cm": 80}
    assert match.match("corner_sofa", {**given, "side": "left"}, tmp_path, P)["matches"]
    assert not match.match("corner_sofa", {**given, "side": "right"}, tmp_path, P)["matches"]
