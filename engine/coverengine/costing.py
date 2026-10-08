"""Prices and costing (ADR-098, docs/plans/prices-costing.md): what a cover costs to make and
what it sells for, per channel.

A *price set* is one JSON document, shaped after Odoo so step 2 can sync it
(`apps/api/coverapi/odoo.py` holds the mapping):

- `exchange`: the fixed rate, rupiah per euro, entered by hand and dated (res.currency.rate);
- `fabrics` and `components`: purchase prices in EUR or IDR (product.template, standard_price);
  each component says what it is counted `per` (a vent, a metre of cord, a cover, ...), so a
  cover's bill of materials follows from its facts (mrp.bom lines);
- `labour`: the hourly rate (EUR or IDR) and the operations with their minutes, each counted
  `per` something (mrp.routing.workcenter);
- `channels`: b2c (the webshop) and b2b (Sunsit, dealers), each with its own extra costs
  (shipping, duties, packaging: lines of their own, never folded into the cost price) and its
  own price list (markup or margin, rounding, VAT shown or not, fixed prices per product:
  product.pricelist).

The cover's *facts* (pieces, metres of fabric and seam, hem, vents, cord, balloons) come from
the real cut pieces (`finished.json`, its nesting estimate) or from the configurator's
proposal. `costing()` turns facts and a price set into lines: materials, labour, components =
the cost price; then each channel's extra costs and its price.

The documented defaults live in config/defaults.yaml (`quote.*`); the admin page's published
price set (app.db, versioned) replaces them.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

from coverengine.params import EffectiveParams

FORMAT_VERSION = 1
CURRENCIES = ("EUR", "IDR")
CHANNELS = ("b2c", "b2b")
METHODS = ("markup", "margin")
BASES = ("landed", "cost")  # the markup on the cost price plus the extra costs, or on cost only
DUTY_MODES = ("pct", "fixed")
# what a line is counted per: the cover's facts
PER = (
    "cover",
    "piece",
    "seam_m",
    "hem_m",
    "vent",
    "cord_m",
    "elastic_m",
    "fabric_m",
    "balloon",
    "frame",
)
PER_LABEL = {
    "cover": "per cover",
    "piece": "per piece",
    "seam_m": "per m of seam",
    "hem_m": "per m of hem",
    "vent": "per vent",
    "cord_m": "per m of cord",
    "elastic_m": "per m of elastic",
    "fabric_m": "per m of fabric",
    "balloon": "per balloon",
    "frame": "per frame",
}
PER_UNIT = {"cover": "pc", "piece": "pc", "vent": "pc", "balloon": "pc", "frame": "pc"}
ROUNDINGS = ("none", "0.01", "0.95", "0.99", "0.90", "1", "5", "10")
ACCESSORIES = ("balloon", "frame")  # sold as products of their own, next to the cover
MM_PER_M = 1000.0  # param-ok: unit conversion
MIN_PER_H = 60.0  # param-ok: unit conversion
PERCENT = 100.0  # param-ok: ratio to percent
CENTS = 2  # param-ok: money is rounded to cents


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


# ---- the default price set, from config/defaults.yaml -------------------------------------------


def default_price_set(params: EffectiveParams) -> dict[str, Any]:
    """The price set the yaml documents (and the old shop settings, when `params` carry them):
    used until the owner publishes one on the admin page."""

    def extras(channel: str) -> dict[str, Any]:
        return {
            "shipping": {"amount": _p(params, f"quote.{channel}_shipping_eur"), "currency": "EUR"},
            "duties": {"mode": "pct", "value": _p(params, "quote.duties_pct"), "currency": "EUR"},
            "packaging": {"amount": _p(params, "quote.packaging_eur"), "currency": "EUR"},
        }

    return {
        "format_version": FORMAT_VERSION,
        "indicative": bool(params["quote.prices_are_placeholders"]),
        "exchange": {
            "idr_per_eur": _p(params, "quote.idr_per_eur"),
            "date": str(params["quote.idr_rate_date"]),
            "note": "",
        },
        "fabrics": [
            {
                "code": "coverlast",
                "name": str(params["quote.fabric_name"]),
                "colours": str(params["quote.colours"]),
                "price": _p(params, "quote.fabric_eur_per_m"),
                "currency": "EUR",
                "roll_width_mm": _p(params, "roll.width_mm"),
                "waste_pct": _p(params, "quote.waste_pct"),
            }
        ],
        "components": [
            {
                "code": "vent_set",
                "name": "Air vent set (insert, membrane, logo)",
                "per": "vent",
                "price": _p(params, "quote.vent_eur"),
                "currency": "EUR",
            },
            {
                "code": "cord",
                "name": "Drawcord",
                "per": "cord_m",
                "price": _p(params, "quote.cord_eur_per_m"),
                "currency": "EUR",
            },
            {
                "code": "elastic",
                "name": "Elastic",
                "per": "elastic_m",
                "price": _p(params, "quote.elastic_eur_per_m"),
                "currency": "EUR",
            },
            {
                "code": "balloon",
                "name": "Table balloon",
                "per": "balloon",
                "price": _p(params, "quote.balloon_eur"),
                "currency": "EUR",
            },
            {
                "code": "frame",
                "name": "Cover frame",
                "per": "frame",
                "price": _p(params, "quote.frame_eur"),
                "currency": "EUR",
            },
        ],
        "labour": {
            "rate": _p(params, "quote.labour_eur_per_hour"),
            "currency": "EUR",
            "operations": [
                {
                    "code": "cut_setup",
                    "name": "Cutting setup",
                    "per": "cover",
                    "minutes": _p(params, "quote.minutes_cut_setup"),
                },
                {
                    "code": "piece",
                    "name": "Per piece (cut, mark, handle)",
                    "per": "piece",
                    "minutes": _p(params, "quote.minutes_per_piece"),
                },
                {
                    "code": "seam",
                    "name": "Double stitching",
                    "per": "seam_m",
                    "minutes": _p(params, "quote.minutes_per_seam_m"),
                },
                {
                    "code": "vent",
                    "name": "Air vent (opening, hood, insert, logo)",
                    "per": "vent",
                    "minutes": _p(params, "quote.minutes_per_vent"),
                },
                {
                    "code": "hem",
                    "name": "Hem with cord channel",
                    "per": "hem_m",
                    "minutes": _p(params, "quote.minutes_per_hem_m"),
                },
                {
                    "code": "pack",
                    "name": "Folding and packing",
                    "per": "cover",
                    "minutes": _p(params, "quote.minutes_pack"),
                },
            ],
        },
        "channels": {
            "b2c": {
                "name": "Consumers (webshop)",
                "method": "markup",
                "pct": _p(params, "quote.markup_pct"),
                "base": "landed",
                "rounding": str(params["quote.b2c_rounding"]),
                "vat_pct": _p(params, "quote.vat_pct"),
                "show_vat": True,
                "extras": extras("b2c"),
                "fixed": {},
            },
            "b2b": {
                "name": "Business (Sunsit, dealers)",
                "method": "markup",
                "pct": _p(params, "quote.b2b_markup_pct"),
                "base": "landed",
                "rounding": str(params["quote.b2b_rounding"]),
                "vat_pct": _p(params, "quote.vat_pct"),
                "show_vat": False,
                "extras": extras("b2b"),
                "fixed": {},
            },
        },
    }


# ---- which values are still placeholders --------------------------------------------------------

# A field of the price set and the config/defaults.yaml key its default comes from. A field whose
# key is marked "to confirm" there, and whose value is still that default, is a placeholder on the
# admin page until the owner changes it or confirms it (the set's `confirmed` list).
FIELD_KEYS = {
    "exchange.idr_per_eur": "quote.idr_per_eur",
    "fabric:coverlast.price": "quote.fabric_eur_per_m",
    "fabric:coverlast.waste_pct": "quote.waste_pct",
    "fabric:coverlast.colours": "quote.colours",
    "fabric:coverlast.roll_width_mm": "roll.width_mm",
    "component:vent_set.price": "quote.vent_eur",
    "component:cord.price": "quote.cord_eur_per_m",
    "component:elastic.price": "quote.elastic_eur_per_m",
    "component:balloon.price": "quote.balloon_eur",
    "component:frame.price": "quote.frame_eur",
    "labour.rate": "quote.labour_eur_per_hour",
    "operation:cut_setup.minutes": "quote.minutes_cut_setup",
    "operation:piece.minutes": "quote.minutes_per_piece",
    "operation:seam.minutes": "quote.minutes_per_seam_m",
    "operation:vent.minutes": "quote.minutes_per_vent",
    "operation:hem.minutes": "quote.minutes_per_hem_m",
    "operation:pack.minutes": "quote.minutes_pack",
    "b2c.pct": "quote.markup_pct",
    "b2b.pct": "quote.b2b_markup_pct",
    "b2c.vat_pct": "quote.vat_pct",
    "b2b.vat_pct": "quote.vat_pct",
    "b2c.shipping": "quote.b2c_shipping_eur",
    "b2b.shipping": "quote.b2b_shipping_eur",
    "b2c.duties": "quote.duties_pct",
    "b2b.duties": "quote.duties_pct",
    "b2c.packaging": "quote.packaging_eur",
    "b2b.packaging": "quote.packaging_eur",
}


def field_value(ps: dict[str, Any], fid: str) -> Any:
    """A field of the price set by its id (FIELD_KEYS), with its currency or mode when it has
    one, so a price switched to rupiah is no longer the euro default; None when it is gone."""
    try:
        if fid == "exchange.idr_per_eur":
            return ps["exchange"]["idr_per_eur"]
        if fid == "labour.rate":
            return [ps["labour"]["rate"], ps["labour"]["currency"]]
        if ":" in fid:
            kind, rest = fid.split(":", 1)
            code, attr = rest.rsplit(".", 1)
            rows = {
                "fabric": ps["fabrics"],
                "component": ps["components"],
                "operation": ps["labour"]["operations"],
            }[kind]
            row = next((r for r in rows if r.get("code") == code), None)
            if row is None:
                return None
            return [row[attr], row["currency"]] if attr == "price" else row[attr]
        channel, attr = fid.split(".", 1)
        ch = ps["channels"][channel]
        if attr in ("shipping", "packaging"):
            return [ch["extras"][attr]["amount"], ch["extras"][attr]["currency"]]
        if attr == "duties":
            return [ch["extras"]["duties"]["mode"], ch["extras"]["duties"]["value"]]
        return ch[attr]
    except (KeyError, TypeError, ValueError):
        return None


def placeholders(
    ps: dict[str, Any], documented: dict[str, Any], unconfirmed: set[str]
) -> list[str]:
    """The ids of the fields still at their documented placeholder: the yaml key is "to confirm"
    (`unconfirmed`), the value equals `documented` (the yaml's own price set) and the owner has
    not confirmed it (the set's `confirmed` list)."""
    confirmed = set(ps.get("confirmed") or [])
    out = []
    for fid, key in FIELD_KEYS.items():
        if key not in unconfirmed or fid in confirmed:
            continue
        v = field_value(ps, fid)
        if v is not None and v == field_value(documented, fid):
            out.append(fid)
    return out


# ---- checking a price set -----------------------------------------------------------------------


def _num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x)


def validate(ps: Any) -> list[str]:
    """What is wrong with a price set, in words for the admin page (empty: fine)."""
    errs: list[str] = []
    if not isinstance(ps, dict):
        return ["the price set must be an object"]

    def money(where: str, amount: Any, cur: Any) -> None:
        if not _num(amount) or amount < 0:
            errs.append(f"{where}: a price of 0 or more")
        if cur not in CURRENCIES:
            errs.append(f"{where}: currency EUR or IDR")

    ex = ps.get("exchange") or {}
    if not _num(ex.get("idr_per_eur")) or ex["idr_per_eur"] <= 0:
        errs.append("exchange rate: rupiah per euro, more than 0")
    fabrics = ps.get("fabrics") or []
    if not fabrics:
        errs.append("fabrics: at least one")
    for i, f in enumerate(fabrics):
        name = f.get("name") or f"fabric {i + 1}"
        money(f"fabric {name}", f.get("price"), f.get("currency"))
        if not _num(f.get("roll_width_mm")) or f["roll_width_mm"] <= 0:
            errs.append(f"fabric {name}: roll width in mm")
        if not _num(f.get("waste_pct")) or not 0 <= f["waste_pct"] < PERCENT:
            errs.append(f"fabric {name}: waste between 0 and 100 %")
    lab = ps.get("labour") or {}
    money("labour rate", lab.get("rate"), lab.get("currency"))
    for kind, rows in (
        ("component", ps.get("components") or []),
        ("operation", lab.get("operations") or []),
    ):
        codes = [r.get("code") for r in rows]
        if len(set(codes)) != len(codes) or not all(codes):
            errs.append(f"{kind}s: every one needs its own code")
        for r in rows:
            name = r.get("name") or r.get("code")
            if r.get("per") not in PER:
                errs.append(f"{kind} {name}: counted per one of {', '.join(PER)}")
            if kind == "component":
                money(f"component {name}", r.get("price"), r.get("currency"))
            elif not _num(r.get("minutes")) or r["minutes"] < 0:
                errs.append(f"operation {name}: minutes, 0 or more")
    chans = ps.get("channels") or {}
    for c in CHANNELS:
        ch = chans.get(c)
        if not isinstance(ch, dict):
            errs.append(f"price list {c}: missing")
            continue
        if ch.get("method") not in METHODS:
            errs.append(f"price list {c}: markup or margin")
        pct: Any = ch.get("pct")
        top = PERCENT if ch.get("method") == "margin" else math.inf
        if not _num(pct) or not 0 <= pct < top:
            errs.append(f"price list {c}: a percentage (a margin below 100 %)")
        if ch.get("base") not in BASES:
            errs.append(f"price list {c}: base landed or cost")
        if str(ch.get("rounding")) not in ROUNDINGS:
            errs.append(f"price list {c}: rounding one of {', '.join(ROUNDINGS)}")
        if not _num(ch.get("vat_pct")) or not 0 <= ch["vat_pct"] < PERCENT:
            errs.append(f"price list {c}: VAT between 0 and 100 %")
        ext = ch.get("extras") or {}
        for k in ("shipping", "packaging"):
            e = ext.get(k) or {}
            money(f"{c} {k}", e.get("amount"), e.get("currency"))
        d = ext.get("duties") or {}
        if d.get("mode") not in DUTY_MODES or not _num(d.get("value")) or d["value"] < 0:
            errs.append(f"{c} duties: a percentage or a fixed amount, 0 or more")
        if d.get("mode") == "fixed" and d.get("currency", "EUR") not in CURRENCIES:
            errs.append(f"{c} duties: currency EUR or IDR")
        for key, v in (ch.get("fixed") or {}).items():
            if not _num(v) or v <= 0:
                errs.append(f"{c} fixed price for {key}: more than 0")
    return errs


def normalised(ps: dict[str, Any]) -> dict[str, Any]:
    """A copy with numbers as numbers (the page may send "12.5") and the rounding a string."""
    out = copy.deepcopy(ps)

    def fix(d: Any) -> None:
        if isinstance(d, dict):
            for k, v in list(d.items()):
                if k in (
                    "price",
                    "amount",
                    "value",
                    "minutes",
                    "rate",
                    "pct",
                    "vat_pct",
                    "idr_per_eur",
                    "roll_width_mm",
                    "waste_pct",
                ) and isinstance(v, str):
                    try:
                        d[k] = float(v.replace(",", "."))
                    except ValueError:
                        pass
                else:
                    fix(v)
        elif isinstance(d, list):
            for x in d:
                fix(x)

    fix(out)
    for ch in (out.get("channels") or {}).values():
        if isinstance(ch, dict):
            ch["rounding"] = str(ch.get("rounding", "none"))
            fixed = ch.get("fixed") or {}
            for k, v in list(fixed.items()):
                if v in (None, ""):
                    del fixed[k]
                elif isinstance(v, str):
                    try:
                        fixed[k] = float(v.replace(",", "."))
                    except ValueError:
                        pass
    return out


# ---- the maths ----------------------------------------------------------------------------------


def to_eur(amount: float, currency: str, ps: dict[str, Any]) -> float:
    return amount if currency == "EUR" else amount / float(ps["exchange"]["idr_per_eur"])


def to_idr(eur: float, ps: dict[str, Any]) -> float:
    return eur * float(ps["exchange"]["idr_per_eur"])


def round_price(x: float, rounding: str) -> float:
    """Up to the next price that ends as asked: 1, 5, 10 = whole euros, fives, tens;
    0.95 / 0.99 / 0.90 = the next price ending in that many cents; none = cents."""
    x = round(x, CENTS)
    if rounding in ("none", "0.01"):
        return x
    r = float(rounding)
    if r >= 1:
        return float(math.ceil(round(x / r, 9)) * r)
    return round(math.ceil(round(x - r, 9)) + r, CENTS)


def fabric_for(
    ps: dict[str, Any], colour: str | None = None, code: str | None = None
) -> dict[str, Any]:
    """The fabric by its code, or the one offering this colour, else the first."""
    fabrics = ps["fabrics"]
    for f in fabrics:
        if code and f.get("code") == code:
            return dict(f)
    if colour:
        for f in fabrics:
            if colour.strip().lower() in [
                c.strip().lower() for c in str(f.get("colours", "")).split(",")
            ]:
                return dict(f)
    return dict(fabrics[0])


def _line(
    section: str,
    code: str,
    name: str,
    qty: float,
    unit: str,
    unit_price: float,
    currency: str,
    ps: dict[str, Any],
    note: str = "",
) -> dict[str, Any]:
    eur = to_eur(qty * unit_price, currency, ps)
    return {
        "section": section,
        "code": code,
        "name": name,
        "qty": round(qty, 3),
        "unit": unit,
        "unit_price": unit_price,
        "currency": currency,
        "eur": round(eur, CENTS),
        "idr": round(to_idr(eur, ps)),
        "note": note,
    }


def accessory_price(ps: dict[str, Any], code: str, channel: str) -> dict[str, float]:
    """A product sold next to the cover (a balloon, a frame): its cost and price in a channel."""
    comp = next((c for c in ps["components"] if c["code"] == code), None)
    cost = to_eur(float(comp["price"]), comp["currency"], ps) if comp else 0.0
    return _price(cost, cost, ps["channels"][channel], code)


def _price(cost: float, landed: float, ch: dict[str, Any], key: str | None) -> dict[str, float]:
    base = landed if ch.get("base", "landed") == "landed" else cost
    pct = float(ch["pct"]) / PERCENT
    net = base * (1 + pct) if ch["method"] == "markup" else base / (1 - pct)
    vat = float(ch["vat_pct"]) / PERCENT
    fixed = (ch.get("fixed") or {}).get(key) if key else None
    shown = float(fixed) if fixed else (net * (1 + vat) if ch["show_vat"] else net)
    shown = round_price(shown, str(ch["rounding"])) if not fixed else round(shown, CENTS)
    if ch["show_vat"]:
        gross, net = shown, shown / (1 + vat)
    else:
        net, gross = shown, shown * (1 + vat)
    margin = net - landed
    return {
        "net_eur": round(net, CENTS),
        "vat_eur": round(gross - net, CENTS),
        "gross_eur": round(gross, CENTS),
        "shown_eur": round(shown, CENTS),
        "margin_eur": round(margin, CENTS),
        "margin_pct": round(margin / net * PERCENT, 1) if net else 0.0,
        "fixed": bool(fixed),
    }


def costing(
    facts: dict[str, Any], ps: dict[str, Any], key: str | None = None, colour: str | None = None
) -> dict[str, Any]:
    """The cover's costing: line by line, the cost price, then per channel the extra costs and
    the price. `key` is the product (a model id) for a fixed price in a price list."""
    lines: list[dict[str, Any]] = []
    fab = fabric_for(ps, colour, facts.get("fabric"))
    metres = float(facts["fabric_m"])
    plan_m = metres
    note = f"{plan_m:.2f} m in the cut plan (nesting estimate)"
    plan_width = float(facts.get("roll_width_mm") or fab["roll_width_mm"])
    if plan_width and abs(plan_width - float(fab["roll_width_mm"])) > 1:
        metres *= plan_width / float(fab["roll_width_mm"])
        note = (
            f"{plan_m:.2f} m in the cut plan on a {plan_width:g} mm roll, scaled to "
            f"{fab['roll_width_mm']:g} mm"
        )
    waste = float(fab["waste_pct"]) / PERCENT
    lines.append(
        _line(
            "fabric",
            fab["code"],
            fab["name"],
            metres * (1 + waste),
            "m",
            float(fab["price"]),
            fab["currency"],
            ps,
            f"{note}, + {fab['waste_pct']:g} % waste",
        )
    )
    q = {**{k: float(facts.get(k) or 0) for k in PER}, "cover": 1.0, "fabric_m": metres}
    for c in ps["components"]:
        if c["code"] in ACCESSORIES or c.get("separate"):
            continue
        n = q[c["per"]]
        if n:
            lines.append(
                _line(
                    "component",
                    c["code"],
                    c["name"],
                    n,
                    PER_UNIT.get(c["per"], "m"),
                    float(c["price"]),
                    c["currency"],
                    ps,
                )
            )
    lab = ps["labour"]
    minutes = 0.0
    for op in lab["operations"]:
        n = q[op["per"]]
        if not n or not op["minutes"]:
            continue
        m = n * float(op["minutes"])
        minutes += m
        lines.append(
            _line(
                "labour",
                op["code"],
                op["name"],
                m / MIN_PER_H,
                "h",
                float(lab["rate"]),
                lab["currency"],
                ps,
                f"{round(n, 2):g} x {float(op['minutes']):g} min "
                f"{PER_LABEL[op['per']]} = {m:.1f} min",
            )
        )
    cost = round(sum(x["eur"] for x in lines), CENTS)
    sums = {
        s: round(sum(x["eur"] for x in lines if x["section"] == s), CENTS)
        for s in ("fabric", "component", "labour")
    }
    channels: dict[str, Any] = {}
    for name, ch in ps["channels"].items():
        ext = ch["extras"]
        ship = to_eur(float(ext["shipping"]["amount"]), ext["shipping"]["currency"], ps)
        pack = to_eur(float(ext["packaging"]["amount"]), ext["packaging"]["currency"], ps)
        d = ext["duties"]
        duty = (
            (cost + ship) * float(d["value"]) / PERCENT
            if d["mode"] == "pct"
            else to_eur(float(d["value"]), d.get("currency", "EUR"), ps)
        )
        extras: list[dict[str, Any]] = [
            {"code": "shipping", "name": "Shipping", "eur": round(ship, CENTS)},
            {
                "code": "duties",
                "name": (
                    f"Import duties ({float(d['value']):g} % of cost + shipping)"
                    if d["mode"] == "pct"
                    else "Import duties (fixed)"
                ),
                "eur": round(duty, CENTS),
            },
            {"code": "packaging", "name": "Packaging", "eur": round(pack, CENTS)},
        ]
        for e in extras:
            e["idr"] = round(to_idr(e["eur"], ps))
        landed = round(cost + sum(e["eur"] for e in extras), CENTS)
        price = _price(cost, landed, ch, key)
        acc = {}
        for code in ACCESSORIES:
            n = int(q[code])
            if n:
                a = accessory_price(ps, code, name)
                acc[code] = {
                    "count": n,
                    **{k: round(v * n, CENTS) if k.endswith("_eur") else v for k, v in a.items()},
                }
        channels[name] = {
            "name": ch.get("name", name),
            "extras": extras,
            "extras_eur": round(landed - cost, CENTS),
            "landed_eur": landed,
            "method": ch["method"],
            "pct": ch["pct"],
            "base": ch.get("base"),
            "show_vat": ch["show_vat"],
            "vat_pct": ch["vat_pct"],
            **price,
            "accessories": acc,
        }
    return {
        "facts": {k: facts.get(k) for k in (*PER, "fabric_m2", "pieces_total") if k in facts},
        "fabric": {"code": fab["code"], "name": fab["name"]},
        "lines": lines,
        "fabric_eur": sums["fabric"],
        "components_eur": sums["component"],
        "labour_eur": sums["labour"],
        "labour_minutes": round(minutes, 1),
        "cost_eur": cost,
        "cost_idr": round(to_idr(cost, ps)),
        "channels": channels,
        "exchange": ps["exchange"],
        "indicative": bool(ps.get("indicative", True)),
    }


# ---- a model's facts, from its cut pieces -------------------------------------------------------


def model_facts(model_dir: Path, params: EffectiveParams) -> dict[str, Any]:
    """What a calculated cover consists of, from `finished.json` (the pieces as cut and the
    cut plan's roll length) and `hull.json` (balloons, frame). `params` are the model's own
    (hem type, a middle cord)."""
    fin = json.loads((model_dir / "finished.json").read_text(encoding="utf-8"))
    pieces = fin.get("pieces") or []
    panels = [p for p in pieces if not str(p.get("name", "")).startswith("vent-")]
    hoods = [p for p in pieces if str(p.get("name", "")).startswith("vent-hood")]
    vents = sum(int(p.get("quantity", 1)) for p in hoods)
    if not hoods:
        vents = sum(len(p.get("openings_mm") or []) * int(p.get("quantity", 1)) for p in panels)

    def edges(kind: str) -> float:
        return sum(
            float(e.get("length_mm") or 0) * int(p.get("quantity", 1))
            for p in panels
            for e in p.get("edges") or []
            if e.get("kind") == kind
        )

    hem_m = edges("hem") / MM_PER_M
    seam_m = edges("seam") / 2 / MM_PER_M  # every seam is on two pieces
    hem = str(params["hem.type"])
    cords = 2 if bool(params["features.middle_cord"]) else 1
    support: dict[str, Any] = {}
    hull = model_dir / "hull.json"
    if hull.is_file():
        support = json.loads(hull.read_text(encoding="utf-8")).get("support") or {}
    kind = str(support.get("kind") or "none")
    sheet = fin.get("sheet") or {}
    return {
        "piece": sum(int(p.get("quantity", 1)) for p in panels),
        "pieces_total": sum(int(p.get("quantity", 1)) for p in pieces),
        "fabric_m": round(float(sheet.get("roll_length_mm") or 0) / MM_PER_M, 3),
        "fabric_m2": round(
            sum(float(p.get("area_m2") or 0) * int(p.get("quantity", 1)) for p in pieces), 3
        ),
        "roll_width_mm": _p(params, "roll.width_mm"),
        "seam_m": round(seam_m, 3),
        "hem_m": round(hem_m, 3),
        "vent": vents,
        "cord_m": round((hem_m + _p(params, "quote.cord_extra_m")) * cords, 3)
        if hem == "drawcord_channel"
        else 0.0,
        "elastic_m": round(hem_m, 3) if hem == "elastic_channel" else 0.0,
        "balloon": int(support.get("balloons") or (1 if kind == "balloon" else 0))
        if kind.startswith("balloon")
        else 0,
        "frame": 1 if kind == "frame" else 0,
    }
