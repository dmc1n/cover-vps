"""Delivery by carrier, a fixed amount per country as the fallback (QUESTIONS 28/29, ADR-136)."""

from typing import Any

import pytest
from coverapi import shipping
from coverengine.params import Registry

TABLE: list[dict[str, Any]] = [{"country": "NL", "name": "Netherlands", "eur": 6.95},
         {"country": "BE", "name": "Belgium", "eur": None}]  # fmt: skip


def params(**over: Any) -> Any:
    return Registry.load(None).resolve(trial=over)


def source(r: shipping.Rate | None) -> str:
    assert r is not None
    return r.source


class Fake:
    name = "fake"

    def __init__(self, eur: float | None, fail: bool = False) -> None:
        self.eur, self.fail = eur, fail
        self.seen: list[tuple[shipping.Parcel, str, str]] = []

    def configured(self) -> bool:
        return True

    def rate(self, parcel: shipping.Parcel, country: str, postcode: str) -> shipping.Rate | None:
        self.seen.append((parcel, country, postcode))
        if self.fail:
            raise TimeoutError("carrier down")
        return None if self.eur is None else shipping.Rate(self.eur, "fake", "parcel")


def test_the_parcel_follows_the_cover() -> None:
    p = params(**{"shipping.boxes_cm": "60x40x30, 40x30x15,bad", "shipping.fabric_g_per_m2": 300,
                  "shipping.pack_g": 450, "shipping.folded_l_per_m2": 2.5})  # fmt: skip
    small = shipping.parcel_for(4.0, p)  # 1.65 kg, 10 litres
    assert small.weight_kg == pytest.approx(1.7) and small.box_cm == (40, 30, 15)
    big = shipping.parcel_for(20.0, p)  # 50 litres: the 72-litre box
    assert big.box_cm == (60, 40, 30) and big.weight_kg == pytest.approx(6.5)
    huge = shipping.parcel_for(200.0, p)
    assert huge.box_cm == (60, 40, 30)  # the largest; the plan says what the workshop does


def test_fixed_amounts_until_a_carrier_is_set_up() -> None:
    p = params()
    assert p["shipping.carrier"] == "fixed"
    assert shipping.quote(TABLE, "nl", "1234AB", 6.0, p) == shipping.Rate(6.95, "fixed")
    assert shipping.quote(TABLE, "BE", "", 6.0, p) == shipping.Rate(0.0, "fixed")
    assert shipping.quote(TABLE, "FR", "", 6.0, p) is None  # we do not deliver there


def test_dhl_without_an_account_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DHL_API_USER_ID", raising=False)
    monkeypatch.delenv("DHL_API_KEY", raising=False)
    p = params(**{"shipping.carrier": "dhl"})
    assert not shipping.DhlCarrier().configured()
    assert shipping.quote(TABLE, "NL", "", 6.0, p) == shipping.Rate(6.95, "fixed")


def test_a_carrier_rate_wins_and_a_failing_carrier_never_stops_an_order() -> None:
    p = params(**{"shipping.carrier": "dhl"})
    ok = Fake(8.40)
    assert shipping.quote(TABLE, "nl", "1234AB", 6.0, p, {"dhl": ok}) == shipping.Rate(
        8.40, "fake", "parcel"
    )
    assert ok.seen[0][1:] == ("NL", "1234AB")
    assert source(shipping.quote(TABLE, "NL", "", 6.0, p, {"dhl": Fake(None)})) == "fixed"
    assert source(shipping.quote(TABLE, "NL", "", 6.0, p, {"dhl": Fake(1, fail=True)})) == "fixed"
    assert shipping.quote(TABLE, "FR", "", 6.0, p, {"dhl": ok}) is None
    assert source(shipping.quote(TABLE, "NL", "", None, p, {"dhl": ok})) == "fixed"
