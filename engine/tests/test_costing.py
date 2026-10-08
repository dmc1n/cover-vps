"""Prices and costing (ADR-098): a cover with known pieces gives the expected metres, minutes and
prices; rounding, margin, IDR conversion, fixed prices and the checks on a price set."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from coverengine import costing, quote
from coverengine.params import Registry

PARAMS = Registry.load(None).resolve()


def _edge(kind: str, mm: float) -> dict[str, Any]:
    return {"kind": kind, "length_mm": mm}


@pytest.fixture()
def model(tmp_path: Path) -> Path:
    """A cover of 3 panels (one top, a skirt cut twice), 3 vents, 4 m of roll, 2 balloons."""
    d = tmp_path / "test-model"
    d.mkdir()
    pieces = [
        {
            "id": "P1",
            "name": "top",
            "quantity": 1,
            "area_m2": 1.0,
            "edges": [_edge("seam", 1000), _edge("hem", 2000)],
        },
        {
            "id": "P2",
            "name": "skirt",
            "quantity": 2,
            "area_m2": 0.5,
            "edges": [_edge("seam", 500), _edge("hem", 1500)],
        },
        {"id": "P3", "name": "vent-hood", "quantity": 3, "area_m2": 0.1, "edges": []},
        {"id": "P4", "name": "vent-membrane", "quantity": 3, "area_m2": 0.05, "edges": []},
    ]
    (d / "finished.json").write_text(
        json.dumps({"pieces": pieces, "sheet": {"roll_length_mm": 4000.0}})
    )
    (d / "hull.json").write_text(json.dumps({"support": {"kind": "balloons", "balloons": 2}}))
    return d


def price_set() -> dict[str, Any]:
    ps = costing.default_price_set(PARAMS)
    ps["exchange"] = {"idr_per_eur": 15000.0, "date": "2026-10-08", "note": ""}
    ps["fabrics"] = [
        {
            "code": "acryl",
            "name": "Acrylic",
            "colours": "Navy, Taupe",
            "price": 20.0,
            "currency": "EUR",
            "roll_width_mm": 1500.0,
            "waste_pct": 10.0,
        }
    ]
    for c in ps["components"]:
        c["price"], c["currency"] = (
            {"vent_set": 5.0, "cord": 1.0, "elastic": 2.0, "balloon": 10.0, "frame": 50.0}[
                c["code"]
            ],
            "EUR",
        )
    ps["labour"]["rate"], ps["labour"]["currency"] = 600000.0, "IDR"  # = 40 EUR an hour
    minutes = {"cut_setup": 10, "piece": 6, "seam": 3, "vent": 10, "hem": 2, "pack": 9}
    for op in ps["labour"]["operations"]:
        op["minutes"] = float(minutes[op["code"]])
    ps["channels"]["b2c"].update(
        method="markup",
        pct=100.0,
        base="landed",
        rounding="0.95",
        vat_pct=21.0,
        show_vat=True,
        fixed={},
        extras={
            "shipping": {"amount": 20.0, "currency": "EUR"},
            "duties": {"mode": "pct", "value": 10.0},
            "packaging": {"amount": 30000.0, "currency": "IDR"},
        },
    )
    ps["channels"]["b2b"].update(
        method="margin",
        pct=40.0,
        base="landed",
        rounding="1",
        vat_pct=21.0,
        show_vat=False,
        fixed={},
        extras={
            "shipping": {"amount": 0.0, "currency": "EUR"},
            "duties": {"mode": "fixed", "value": 5.0, "currency": "EUR"},
            "packaging": {"amount": 1.0, "currency": "EUR"},
        },
    )
    assert costing.validate(ps) == []
    return ps


def test_the_facts_come_from_the_cut_pieces(model: Path) -> None:
    f = costing.model_facts(model, PARAMS)
    assert f["piece"] == 3 and f["pieces_total"] == 9
    assert f["fabric_m"] == 4.0 and f["fabric_m2"] == pytest.approx(2.45)
    assert f["seam_m"] == pytest.approx(1.0)  # 1000 + 2 x 500 mm of seam edge, each seam twice
    assert f["hem_m"] == pytest.approx(5.0)  # 2000 + 2 x 1500 mm
    assert f["vent"] == 3 and f["balloon"] == 2 and f["frame"] == 0
    assert f["cord_m"] == pytest.approx(5.0 + float(PARAMS["quote.cord_extra_m"]))
    assert f["elastic_m"] == 0


def test_a_known_cover_gives_the_expected_costing(model: Path) -> None:
    f = costing.model_facts(model, PARAMS)
    c = costing.costing(f, price_set(), "test-model")
    by = {x["code"]: x for x in c["lines"]}
    assert by["acryl"]["qty"] == pytest.approx(4.4)  # 4 m + 10 % waste
    assert by["acryl"]["eur"] == 88.0
    assert by["vent_set"]["eur"] == 15.0 and by["cord"]["eur"] == 6.25
    assert "elastic" not in by and "balloon" not in by  # balloons are sold next to the cover
    # 10 + 3x6 + 1x3 + 3x10 + 5x2 + 9 = 80 minutes at 600,000 IDR = 40 EUR an hour
    assert c["labour_minutes"] == 80
    assert c["labour_eur"] == pytest.approx(53.34)  # each line rounded to cents
    assert by["seam"]["idr"] == 30000  # 3 minutes, shown in rupiah too
    assert c["cost_eur"] == pytest.approx(162.59)
    assert c["cost_idr"] == round(162.59 * 15000)
    b2c = c["channels"]["b2c"]
    ex = {e["code"]: e["eur"] for e in b2c["extras"]}
    assert ex == {"shipping": 20.0, "duties": 18.26, "packaging": 2.0}  # 10 % of cost + shipping
    assert b2c["landed_eur"] == pytest.approx(202.85)
    assert b2c["gross_eur"] == 490.95  # 202.85 x 2 x 1.21 = 490.90, up to .95
    assert b2c["net_eur"] == pytest.approx(490.95 / 1.21, abs=0.01)
    assert b2c["accessories"]["balloon"]["count"] == 2
    assert b2c["accessories"]["balloon"]["shown_eur"] == pytest.approx(2 * 24.95)
    b2b = c["channels"]["b2b"]
    assert b2b["landed_eur"] == pytest.approx(168.59)
    assert b2b["shown_eur"] == b2b["net_eur"] == 281.0  # 168.59 / 0.6 = 280.98, whole euros
    assert b2b["margin_pct"] == pytest.approx((281 - 168.59) / 281 * 100, abs=0.1)


def test_a_fixed_price_wins_in_its_channel_only(model: Path) -> None:
    ps = price_set()
    ps["channels"]["b2b"]["fixed"] = {"test-model": 250.0}
    c = costing.costing(costing.model_facts(model, PARAMS), ps, "test-model")
    assert c["channels"]["b2b"]["net_eur"] == 250.0 and c["channels"]["b2b"]["fixed"]
    assert c["channels"]["b2c"]["gross_eur"] == 490.95
    other = costing.costing(costing.model_facts(model, PARAMS), ps, "another-model")
    assert other["channels"]["b2b"]["net_eur"] == 281.0


def test_a_fabric_in_rupiah_and_on_a_narrower_roll(model: Path) -> None:
    ps = price_set()
    ps["fabrics"].append(
        {
            "code": "olefin",
            "name": "Olefin",
            "colours": "Black",
            "price": 300000.0,
            "currency": "IDR",
            "roll_width_mm": 1200.0,
            "waste_pct": 0.0,
        }
    )
    c = costing.costing(costing.model_facts(model, PARAMS), ps, colour="Black")
    line = c["lines"][0]
    assert line["code"] == "olefin" and line["qty"] == pytest.approx(5.0)  # 4 m x 1500 / 1200
    assert line["eur"] == pytest.approx(5 * 20.0)  # 300,000 IDR = 20 EUR a metre


@pytest.mark.parametrize(
    ("x", "mode", "want"),
    [
        (123.2, "0.95", 123.95),
        (123.95, "0.95", 123.95),
        (123.96, "0.95", 124.95),
        (10.0, "0.99", 10.99),
        (12.01, "1", 13.0),
        (12.0, "1", 12.0),
        (101.0, "5", 105.0),
        (101.0, "10", 110.0),
        (12.345, "none", 12.35),
    ],
)
def test_rounding(x: float, mode: str, want: float) -> None:
    assert costing.round_price(x, mode) == pytest.approx(want)


def test_the_checks_name_what_is_wrong() -> None:
    ps = price_set()
    bad = copy.deepcopy(ps)
    bad["exchange"]["idr_per_eur"] = 0
    bad["channels"]["b2b"]["pct"] = 100.0  # a margin of 100 % has no price
    bad["channels"]["b2c"]["rounding"] = "0.42"
    bad["components"][0]["currency"] = "USD"
    bad["labour"]["operations"][0]["per"] = "moon"
    errs = " | ".join(costing.validate(bad))
    for word in ("exchange rate", "b2b", "rounding", "currency", "counted per"):
        assert word in errs
    loose = copy.deepcopy(ps)
    loose["fabrics"][0]["price"] = "21,5"  # as typed on the page
    assert costing.normalised(loose)["fabrics"][0]["price"] == 21.5


def test_the_configurator_uses_the_price_set() -> None:
    ps = price_set()
    q1 = quote.proposal("sofa", {}, PARAMS, ps)
    ps2 = copy.deepcopy(ps)
    ps2["fabrics"][0]["price"] = 40.0
    q2 = quote.proposal("sofa", {}, PARAMS, ps2)
    assert q2["price"]["cost_eur"] > q1["price"]["cost_eur"]
    assert q1["price"]["sale_eur"] == q1["price"]["costing"]["channels"]["b2c"]["gross_eur"]
    assert str(q1["price"]["sale_eur"]).endswith(".95")
    assert q1["price"]["b2b_ex_vat_eur"] < q1["price"]["sale_ex_vat_eur"]
    # the yaml defaults when nothing is published
    assert quote.proposal("sofa", {}, PARAMS)["price"]["placeholder_prices"] is True


def test_placeholders_are_the_documented_values_still_to_confirm() -> None:
    reg = Registry.load(None)
    unconfirmed = {k for k, s in reg.specs.items() if s.to_confirm}
    documented = costing.default_price_set(PARAMS)
    ps = copy.deepcopy(documented)
    every = costing.placeholders(ps, documented, unconfirmed)
    assert "fabric:coverlast.price" in every and "exchange.idr_per_eur" in every
    assert "b2c.vat_pct" not in every and "fabric:coverlast.roll_width_mm" not in every
    assert all(costing.FIELD_KEYS[f] in unconfirmed for f in every)
    # changed, switched to rupiah, or confirmed: no longer a placeholder
    ps["labour"]["operations"][0]["minutes"] += 1
    ps["components"][0]["currency"] = "IDR"
    ps["channels"]["b2b"]["extras"]["duties"]["mode"] = "fixed"
    ps["confirmed"] = ["b2c.pct"]
    left = set(costing.placeholders(ps, documented, unconfirmed))
    gone = {"operation:cut_setup.minutes", "component:vent_set.price", "b2b.duties", "b2c.pct"}
    assert left == set(every) - gone
    assert costing.field_value(ps, "component:nope.price") is None
    assert costing.validate(ps) == []  # the confirmed list does not trouble the checks
