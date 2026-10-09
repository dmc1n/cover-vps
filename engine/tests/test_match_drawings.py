"""ADR-114: approved drawing covers offered as "we already make a cover that fits": the kind from
the price list, the product names or the shape, the table's own size under a cover with chairs,
the hand of an L, doubtful ones held back until a person confirms, and a cover rejected at the
Desk dropping out at once."""

import json
import os
import time
from pathlib import Path
from typing import Any

from coverengine import match, match_drawings
from coverengine.params import Registry

P = Registry.load(None).resolve(
    trial={"match.tight_cm": 1.0, "match.loose_cm": 4.0, "match.tight_falloff_cm": 4.0,
           "match.loose_falloff_cm": 20.0, "match.weights": "1,1,1",
           "match.threshold_pct": 90.0, "match.choice_pct": 80.0}
)  # fmt: skip
T1_ROW = {"code": "T1", "section": "Dining tables", "item": "Suns Cover dining tables",
          "suitable": "Tables 340 x 100 cm including chairs", "size": "350 x 166 x 87 cm",
          "row": 1}  # fmt: skip
C12_ROW = {"code": "C12", "section": "Corner sets", "item": "Suns cover corner set left",
           "suitable": "Savona / Siena : 3-seater left, corner, 2-seater right",
           "size": "327 x 252 x 84 x 93 cm", "row": 2}  # fmt: skip
LISTING = {"stamp": "a", "rows": {"t1": [T1_ROW], "c12": [C12_ROW]}}


def _drawing(models: Path, mid: str, size_cm: tuple[float, float, float], notes: str,
             status: str | None = "approved", labels: list[str] | None = None,
             category: str = "Lounge › Sofasets", **cover: Any) -> Path:  # fmt: skip
    d = models / mid
    d.mkdir(parents=True, exist_ok=True)
    code = mid.removeprefix("drawing-").upper()
    (d / "cover.json").write_text(json.dumps({"notes": notes, "category": category, **cover}))
    (d / "model.json").write_text(json.dumps({"size_mm": [x * 10 for x in size_cm]}))
    if status:
        (d / "desk.json").write_text(json.dumps({"code": code, "status": status}))
    (d / "products.json").write_text(json.dumps({"labels": ["Cover 13", *(labels or [])]}))
    return d


def _later(path: Path) -> None:
    """A file changed a moment later (a test runs faster than the clock's resolution)."""
    t = time.time() + 5
    os.utime(path, (t, t))


def test_an_approved_dining_cover_gives_its_table_size_and_fits_a_lower_table(
    tmp_path: Path,
) -> None:
    _drawing(tmp_path, "drawing-t1", (350, 166, 87), "Drawing T1: box, built from the sizes")
    c = match.card(tmp_path / "drawing-t1", None, LISTING, P)
    assert c is not None and c["kind"] == "dining_set"  # cover.json says Sofasets: corrected
    assert c["size_cm"] == [340.0, 100.0, 86.0] and c["chairs"] is True and c["height_max"]
    assert c["name"] == "SUNS cover dining tables – Tables 340 x 100 cm including chairs"
    given = {"table_length_cm": 340, "table_width_cm": 100, "table_height_cm": 75}
    r = match.match("dining_set", given, tmp_path, P, listing=LISTING)
    best = r["matches"][0]
    assert best["model_id"] == "drawing-t1" and best["score_pct"] == 100.0  # 75 fits under 86
    assert r["decision"] == "existing" and best["name"].startswith("SUNS cover dining")
    assert not match.match("dining_set", {**given, "chairs": False}, tmp_path, P,
                           listing=LISTING)["matches"]  # fmt: skip


def test_only_approved_or_produced_covers_and_a_rejected_one_drops_out(tmp_path: Path) -> None:
    d = _drawing(tmp_path, "drawing-t1", (350, 166, 87), "Drawing T1: box")
    _drawing(tmp_path, "drawing-t9", (310, 166, 87), "Drawing T9: box", status="rejected",
             labels=["Table 300 x 100"])  # fmt: skip
    _drawing(tmp_path, "drawing-t10", (250, 166, 87), "Drawing T10: box", status="produced",
             labels=["Table 240 x 100"])  # fmt: skip
    _drawing(tmp_path, "drawing-t3", (230, 166, 87), "Drawing T3: box", status="ai-checked",
             labels=["Table 220x100"])  # fmt: skip
    ids = {c["model_id"] for c in match.cards(tmp_path, None, LISTING, P)}
    assert ids == {"drawing-t1", "drawing-t10"}
    assert match.card(tmp_path / "drawing-t9", None, LISTING, P) is None
    (d / "desk.json").write_text(json.dumps({"code": "T1", "status": "rejected"}))
    _later(d / "desk.json")
    ids = {c["model_id"] for c in match.cards(tmp_path, None, LISTING, P)}
    assert ids == {"drawing-t10"}  # the cache saw the Desk's decision


def test_the_kind_from_the_product_names_then_the_shape(tmp_path: Path) -> None:
    _drawing(tmp_path, "drawing-t2", (290, 166, 87), "Drawing T2: box",
             labels=["Table 280x100"])  # fmt: skip
    _drawing(tmp_path, "drawing-r4", (160, 160, 87), "Drawing R4: round",
             labels=["Table 90 Ø"])  # fmt: skip
    _drawing(tmp_path, "drawing-s31", (95, 105, 83), "Drawing S31: sloped box",
             labels=["Bellano Lounge chair"])  # fmt: skip
    _drawing(tmp_path, "drawing-c23", (294, 294, 90), "Drawing C23: L shape, built")
    _drawing(tmp_path, "drawing-u2", (60, 60, 90), "Drawing U2: swept, built")
    r = {m: match_drawings.review(tmp_path / m, P) for m in
         ("drawing-t2", "drawing-r4", "drawing-s31", "drawing-c23", "drawing-u2")}  # fmt: skip
    assert r["drawing-t2"]["kind"] == "dining_set" and "product list" in r["drawing-t2"]["how"]
    assert r["drawing-t2"]["size_cm"] == [280.0, 100.0, 86.0]
    assert r["drawing-r4"]["kind"] == "round_set" and r["drawing-r4"]["size_cm"][:2] == [90, 90]
    assert r["drawing-s31"]["kind"] == "item"
    assert r["drawing-s31"]["size_cm"] == [103.0, 93.0, 82.0]  # the cover minus 1 cm a side
    assert r["drawing-c23"]["kind"] == "corner_sofa" and "shape" in r["drawing-c23"]["how"]
    assert r["drawing-u2"]["kind"] is None and not r["drawing-u2"]["offered"]


def test_the_hand_of_an_l_and_a_doubt_a_person_confirms(tmp_path: Path) -> None:
    _drawing(tmp_path, "drawing-c12", (327, 252, 84), "Drawing C12: L shape, built",
             labels=["Savona lounge set Left with arm"])  # fmt: skip
    given = {"long_side_cm": 325, "short_side_cm": 250, "back_height_cm": 83}
    left = match.match("corner_sofa", {**given, "side": "left"}, tmp_path, P, listing=LISTING)
    assert left["matches"][0]["model_id"] == "drawing-c12"
    assert left["matches"][0]["score_pct"] == 100.0 and left["matches"][0]["side"] == "left"
    right = match.match("corner_sofa", {**given, "side": "right"}, tmp_path, P, listing=LISTING)
    assert not right["matches"]  # the other hand never fits
    # the price list says left, the name and the plan say right: doubtful, not offered
    d = _drawing(tmp_path, "drawing-c12", (252, 327, 84), "Drawing C12: L shape, built",
                 labels=["Savona lounge set Right with arm"])  # fmt: skip
    r = match_drawings.review(d, P, LISTING)
    assert r is not None and not r["offered"] and any("left or right" in x for x in r["doubts"])
    _drawing(tmp_path, "drawing-c12", (252, 327, 84), "Drawing C12: L shape, built",
             labels=["Savona lounge set Right with arm"],
             match={"kind": "corner_sofa", "side": "right"})  # fmt: skip
    c = match.card(d, None, LISTING, P)
    assert c is not None and c["side"] == "right"  # a person's word confirms it


def test_a_price_list_row_about_another_product_is_not_used(tmp_path: Path) -> None:
    listing = {"stamp": "b", "rows": {"d6": [{"code": "D6", "section": "Blocchi items",
                                              "item": "", "suitable": "Blocchi hocker",
                                              "size": "140x113x45", "row": 3}]}}  # fmt: skip
    d = _drawing(tmp_path, "drawing-d6", (180, 215, 87), "Drawing D6: (hip) top view",
                 labels=["Blocchi daybed"])  # fmt: skip
    r = match_drawings.review(d, P, listing)
    assert r is not None and r["kind"] == "lounger"  # from the name, not the hocker's row
    assert not r["offered"] and any("D6: price list" in x for x in r["doubts"])


def test_two_covers_with_one_code_wait_for_a_person(tmp_path: Path) -> None:
    for mid in ("drawing-s10-box", "drawing-s10-plain"):
        d = _drawing(tmp_path, mid, (320, 115, 90), "Drawing S10: sloped box",
                     labels=["Bora/Volar 3- seater sofa"])  # fmt: skip
        (d / "desk.json").write_text(json.dumps({"code": "S10 (box)", "status": "approved"}))
    assert match_drawings.codes(tmp_path / "drawing-s10-box") == ["s10"]
    assert not [c for c in match.cards(tmp_path, None, None, P) if c["kind"] == "sofa"]


def test_words_say_the_kind() -> None:
    k = match_drawings.words_kind
    assert k("Suns cover corner set left", 300)[0] == "corner_sofa"
    assert k("Termoli and Sorrento CL right", 260)[0] == "corner_sofa"
    assert k("Aspen/ Kota/ Evora lounge normal SMALL w/o side table", 290)[0] is None
    assert k("Vento corner", 294)[0] == "corner_sofa" and k("Vento: corner", 112)[0] == "item"
    assert k("Bartable 140 Ø", 210)[0] == "round_set"
    assert k("Suns Cover Lounge  tables", 110)[0] == "item"
    assert k("lounge chair Stockholm/ Savona Sofa set", 113)[0] == "item"
    assert k("Suns Cover Chaise longue", 169)[0] == "lounger"
    assert k("Suns cover umbrella", 269)[0] == "none"
    assert k("Suns cover Ibiza style left", 295) == (
        "sofa",
        "Ibiza style: a corner and a sofa in one row",
    )
    assert match_drawings.sides(["Ibiza style left", "Ibiza style right"]) == "both"
