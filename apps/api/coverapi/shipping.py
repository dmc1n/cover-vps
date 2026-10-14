"""Delivery cost for a consumer order: a carrier's rate by the parcel's weight and box, with a
fixed amount per country as the fallback (owner, 11 Oct 2026, QUESTIONS 28/29; plan:
docs/plans/shipping-carrier.md, ADR-136).

The parcel comes from the cover itself: its cut fabric (m², from the quote) times
`shipping.fabric_g_per_m2` plus `shipping.pack_g`, in the first of `shipping.boxes_cm` whose
volume holds the folded cover (`shipping.folded_l_per_m2`). A carrier answers a `Rate` for a
parcel to a country, or None (no account, no answer, a country it does not serve); then the
country's fixed amount from Shop settings → shipping is used, as before.

DHL needs the owner's business account (API user id and key in deploy/.env); until then
`DhlCarrier.configured()` is False and every order uses the fixed amounts. The request itself
is written when the account exists (the plan lists the endpoint and what to send).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

GRAMS_PER_KG = 1000.0
CM3_PER_L = 1000.0


@dataclass(frozen=True)
class Parcel:
    weight_kg: float
    box_cm: tuple[int, int, int]  # length, width, height


@dataclass(frozen=True)
class Rate:
    eur: float  # incl. VAT, what the customer pays for delivery
    source: str  # "fixed" or the carrier's name
    service: str = ""


class Carrier(Protocol):
    name: str

    def configured(self) -> bool: ...

    def rate(self, parcel: Parcel, country: str, postcode: str) -> Rate | None: ...


def boxes(text: str) -> list[tuple[int, int, int]]:
    """ "40x30x15,50x40x20" -> [(40, 30, 15), (50, 40, 20)], smallest volume first."""
    out = []
    for item in text.split(","):
        parts = [p.strip() for p in item.lower().split("x")]
        if len(parts) == 3 and all(p.isdigit() for p in parts):  # param-ok: L x W x H
            a, b, c = (int(p) for p in parts)
            out.append((a, b, c))
    return sorted(out, key=lambda t: t[0] * t[1] * t[2])


def parcel_for(fabric_m2: float, params: Any) -> Parcel:
    """The cover's parcel: weight from its cut fabric plus packing; the smallest box that holds
    it folded (the largest box when none does: the workshop then packs two, see the plan)."""
    grams = fabric_m2 * float(params["shipping.fabric_g_per_m2"]) + float(params["shipping.pack_g"])
    litres = fabric_m2 * float(params["shipping.folded_l_per_m2"])
    sizes = boxes(str(params["shipping.boxes_cm"]))
    if not sizes:
        raise ValueError("shipping.boxes_cm lists no box")
    box = next((b for b in sizes if b[0] * b[1] * b[2] / CM3_PER_L >= litres), sizes[-1])
    return Parcel(weight_kg=math.ceil(grams / 100) / 10, box_cm=box)  # param-ok: 0.1 kg up


class DhlCarrier:
    """DHL Parcel (NL/BE/DE): needs the owner's account. Not configured: no rate."""

    name = "dhl"

    def configured(self) -> bool:
        from coverapi.security import env_value

        return bool(env_value("DHL_API_USER_ID") and env_value("DHL_API_KEY"))

    def rate(self, parcel: Parcel, country: str, postcode: str) -> Rate | None:
        if not self.configured():
            return None
        # The account's own rates come with the contract; the request (capabilities by
        # weight and box, docs/plans/shipping-carrier.md) is built once the account exists.
        return None


CARRIERS: dict[str, Carrier] = {"dhl": DhlCarrier()}


def fixed_rate(table: list[dict[str, Any]], country: str) -> Rate | None:
    """The country's fixed amount from Shop settings → shipping; None: we do not deliver there."""
    row = next((x for x in table if str(x.get("country", "")).upper() == country.upper()), None)
    if row is None:
        return None
    return Rate(eur=float(row.get("eur") or 0), source="fixed")


def quote(
    table: list[dict[str, Any]],
    country: str,
    postcode: str,
    fabric_m2: float | None,
    params: Any,
    carriers: dict[str, Carrier] | None = None,
) -> Rate | None:
    """Delivery for one cover: the chosen carrier's rate when it is set up and answers, else the
    country's fixed amount. None: we do not deliver to this country (no fixed row either)."""
    fallback = fixed_rate(table, country)
    if fallback is None:
        return None
    carrier = (carriers or CARRIERS).get(str(params["shipping.carrier"]))
    if carrier is None or not carrier.configured() or not fabric_m2:
        return fallback
    try:
        got = carrier.rate(parcel_for(fabric_m2, params), country.upper(), postcode)
    except Exception:  # noqa: BLE001 - a carrier that fails never stops an order
        got = None
    return got if got is not None else fallback
