"""The seam to Odoo (ADR-098, step 2 of docs/plans/prices-costing.md). No connection yet.

The owner's Odoo is their own installation in Indonesia. Step 2 will talk to it through Odoo's
external API (XML-RPC or JSON-RPC: `/xmlrpc/2/common` to log in with an API key,
`/xmlrpc/2/object` `execute_kw` for search_read / create / write), with the URL, database,
API user and key in deploy/.env, never in code.

`records()` already gives what we would send, shaped as Odoo's models, each with an external id
(`cover_studio.<code>`) so a sync can create or update the same record again:

- res.currency.rate      the fixed rate (IDR per EUR, dated)
- product.template       fabrics and components (purchase price, currency, unit), the
                         accessories, and one product per cover (standard_price = cost price)
- mrp.workcenter         the workshop with its hourly cost
- mrp.bom                per cover: lines (fabric metres, components) and operations
                         (mrp.routing.workcenter: minutes per cover)
- product.pricelist      per channel (b2c, b2b) with the rule (markup or margin, rounding) and
                         fixed prices per product

This is the only module that knows Odoo's names; the rest of the studio talks price sets and
costings (`coverengine/costing.py`).
"""

from __future__ import annotations

from typing import Any

PREFIX = "cover_studio."
UOM = {"m": "m", "pc": "Units", "h": "Hours"}


def _xid(code: str) -> str:
    return PREFIX + code.replace(":", "_").replace("-", "_")


def _round_rule(rounding: str) -> dict[str, float]:
    """Our rounding as Odoo's price_round and price_surcharge (0.95: round to 1, then -0.05)."""
    if rounding in ("none", "0.01"):
        return {"price_round": 0.01, "price_surcharge": 0.0}
    r = float(rounding)
    if r >= 1:
        return {"price_round": r, "price_surcharge": 0.0}
    return {"price_round": 1.0, "price_surcharge": round(r - 1, 2)}


def records(ps: dict[str, Any], covers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The price set (and the given covers' facts) as Odoo records. `covers`: model id ->
    facts (`costing.model_facts`)."""
    from coverengine import costing

    ex = ps["exchange"]
    out: dict[str, Any] = {
        "res.currency.rate": [
            {
                "external_id": _xid(f"rate_idr_{ex.get('date', '')}"),
                "currency_id": "IDR",
                "name": ex.get("date"),
                "rate": ex["idr_per_eur"],
                "note": "units of IDR per 1 EUR; if the company currency is IDR, "
                "Odoo stores EUR at 1 / this",
            }
        ],
        "product.template": [],
        "mrp.workcenter": [],
        "mrp.bom": [],
        "product.pricelist": [],
    }
    for f in ps["fabrics"]:
        out["product.template"].append(
            {
                "external_id": _xid(f["code"]),
                "default_code": f["code"],
                "name": f["name"],
                "type": "product",
                "uom_id": "m",
                "purchase_ok": True,
                "sale_ok": False,
                "seller_ids": [{"price": f["price"], "currency_id": f["currency"]}],
                "x_roll_width_mm": f["roll_width_mm"],
                "x_waste_pct": f["waste_pct"],
                "x_colours": f.get("colours", ""),
            }
        )
    for c in ps["components"]:
        accessory = c["code"] in costing.ACCESSORIES
        out["product.template"].append(
            {
                "external_id": _xid(c["code"]),
                "default_code": c["code"],
                "name": c["name"],
                "type": "product",
                "uom_id": costing.PER_UNIT.get(c["per"], "m"),
                "purchase_ok": True,
                "sale_ok": accessory,
                "seller_ids": [{"price": c["price"], "currency_id": c["currency"]}],
            }
        )
    lab = ps["labour"]
    out["mrp.workcenter"].append(
        {
            "external_id": _xid("workshop"),
            "name": "Cover workshop",
            "costs_hour": lab["rate"],
            "currency_id": lab["currency"],
        }
    )
    for mid, f in covers.items():
        c = costing.costing(f, ps, mid)
        out["product.template"].append(
            {
                "external_id": _xid(mid),
                "default_code": mid,
                "name": f.get("name", mid),
                "type": "product",
                "sale_ok": True,
                "purchase_ok": False,
                "route_ids": ["Manufacture"],
                "standard_price": c["cost_eur"],
                "standard_price_currency": "EUR",
            }
        )
        lines = [
            {
                "product_id": _xid(x["code"]),
                "product_qty": x["qty"],
                "product_uom_id": UOM.get(x["unit"], x["unit"]),
            }
            for x in c["lines"]
            if x["section"] in ("fabric", "component")
        ]
        ops = [
            {
                "name": x["name"],
                "workcenter_id": _xid("workshop"),
                "time_cycle_manual": round(x["qty"] * 60, 2),
            }  # noqa: PLR2004 - hours to minutes
            for x in c["lines"]
            if x["section"] == "labour"
        ]
        out["mrp.bom"].append(
            {
                "external_id": _xid(f"bom_{mid}"),
                "product_tmpl_id": _xid(mid),
                "product_qty": 1,
                "type": "normal",
                "bom_line_ids": lines,
                "operation_ids": ops,
            }
        )
    for name, ch in ps["channels"].items():
        pct = float(ch["pct"])
        rule = {
            "applied_on": "3_global",
            "compute_price": "formula",
            "base": "standard_price",
            **_round_rule(str(ch["rounding"])),
        }
        if ch["method"] == "markup":
            rule["price_markup"] = pct  # Odoo 17+; older: price_discount = -pct
        else:
            rule["x_margin_pct"] = pct  # Odoo has no margin rule: price = cost / (1 - margin)
        items = [rule] + [
            {
                "applied_on": "1_product",
                "product_tmpl_id": _xid(k),
                "compute_price": "fixed",
                "fixed_price": v,
            }
            for k, v in (ch.get("fixed") or {}).items()
        ]
        out["product.pricelist"].append(
            {
                "external_id": _xid(f"pricelist_{name}"),
                "name": ch.get("name", name),
                "currency_id": "EUR",
                "item_ids": items,
                "x_prices_include_vat": bool(ch["show_vat"]),
                "x_vat_pct": ch["vat_pct"],
                "x_extra_costs": ch["extras"],
                "x_markup_base": ch.get("base", "landed"),
            }
        )
    return out


def push(records: dict[str, Any]) -> None:  # pragma: no cover - step 2
    """Step 2: create or update these records in the owner's Odoo (XML-RPC execute_kw with
    the external ids). Needs ODOO_URL, ODOO_DB, ODOO_USER and ODOO_API_KEY in deploy/.env."""
    raise NotImplementedError("Odoo sync is step 2 (docs/plans/prices-costing.md)")
