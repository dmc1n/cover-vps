"""Everything about one cover's price and its place in the shop, for the cover's own page
(ADR-126, docs/plans/studio-ui.md §12): `GET /api/prices/cover/{model_id}`.

Read-only and gathered from where it already lives; nothing here computes a price of its own:

- **cost and prices**: the costing (`coverengine.costing`) under the live set and, when there is
  one, under the draft, so the page shows live vs draft side by side; per channel the fixed price
  in each (the draft is edited with `PUT /api/prices/draft/fixed`, prices.py);
- **the draft as a whole**: who, when, how many fixed prices differ from the live set and whether
  anything else differs (the page's "N changes in the draft — Publish");
- **the shop**: whether the cover is offered as an existing cover (the same `match.card` /
  `match_drawings.review` the shop and the B2B shop use), its kind, sizes, the price list's rows
  (section, item, suits), how its direct-order price is made (ADR-118) and the delivery note;
- **for admins only** (as the pages they come from): the B2B companies with a price of their own
  for it, its orders, its stock quotes and the match requests that proposed or chose it.

Rights: editors and admins (`edit`), as GET /api/prices; viewers get 403. Nothing is written.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

RECENT_QUOTES = 400  # param-ok: the newest quote files looked through per cover
SHOWN = 20  # param-ok: rows per list on the page


def draft_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """How a draft differs from the live set: fixed prices per channel and product that differ,
    and whether anything else (materials, labour, rules, ...) differs."""
    from coverengine import costing

    b, a = (
        costing.normalised(json.loads(json.dumps(before))),
        costing.normalised(json.loads(json.dumps(after))),
    )
    fixed: list[dict[str, Any]] = []
    for ch in sorted(set(b["channels"]) | set(a["channels"])):
        fb = (b["channels"].get(ch) or {}).get("fixed") or {}
        fa = (a["channels"].get(ch) or {}).get("fixed") or {}
        for key in sorted(set(fb) | set(fa)):
            if fb.get(key) != fa.get(key):
                fixed.append({"channel": ch, "key": key, "live": fb.get(key), "draft": fa.get(key)})
    for doc in (b, a):
        for ch in doc["channels"].values():
            ch.pop("fixed", None)
    return {"fixed": fixed, "other": b != a}


def _orders(auth: Any, model_id: str) -> list[dict[str, Any]]:
    """Orders that are this cover: an existing cover sold (consumer or B2B), or the model an
    order was produced as."""
    like = f'%"{model_id}"%'
    try:
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT id, created, status, email, data, total_eur, model_id FROM orders "
                "WHERE model_id=? OR data LIKE ? ORDER BY id DESC LIMIT 200",
                (model_id, like),
            ).fetchall()
    except sqlite3.OperationalError:  # no shop yet
        return []
    out = []
    for r in rows:
        d = json.loads(r["data"])
        stock = d.get("stock") or (d.get("quote") or {}).get("stock") or {}
        if r["model_id"] != model_id and stock.get("model_id") != model_id:
            continue
        b2b = d.get("b2b") or {}
        out.append({
            "id": r["id"], "created": r["created"], "status": r["status"],
            "total_eur": r["total_eur"], "stock": stock.get("model_id") == model_id,
            "produced_as": r["model_id"] == model_id,
            "customer": b2b.get("company") or (d.get("customer") or {}).get("name") or "",
            "b2b": bool(b2b), "qty": b2b.get("qty"),
        })  # fmt: skip
    return out[:SHOWN]


def _quotes(root: Path, model_id: str) -> list[dict[str, Any]]:
    """The newest stock quotes of this cover, consumer and B2B (files in shop_quotes/ and
    b2b_quotes/; housekeeping removes old ones)."""
    files: list[tuple[float, Path, str]] = []
    for folder, where in ((root / "shop_quotes", "shop"), (root / "b2b_quotes", "b2b")):
        if not folder.is_dir():
            continue
        for p in folder.glob("*.json"):
            try:
                files.append((p.stat().st_mtime, p, where))
            except OSError:
                continue
    files.sort(key=lambda x: -x[0])
    out = []
    for _, p, where in files[:RECENT_QUOTES]:
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        stock = rec.get("stock") or {}
        if stock.get("model_id") != model_id:
            continue
        b2b = rec.get("b2b") or {}
        if b2b:  # the company's own price for one cover, ex VAT (b2b.unit_price)
            price, source, vat = b2b.get("cover_eur"), b2b.get("source"), "ex"
        else:  # the consumer shop's price for it, incl. VAT
            price = stock.get("price_eur", ((rec.get("quote") or {}).get("price") or {})
                              .get("sale_eur"))  # fmt: skip
            source, vat = stock.get("price_source"), "incl"
        out.append({"id": p.stem, "time": rec.get("time"), "where": where, "price_eur": price,
                    "vat": vat, "source": source,
                    "company_id": b2b.get("company_id")})  # fmt: skip
        if len(out) >= SHOWN:
            break
    return out


def _matches(auth: Any, model_id: str) -> list[dict[str, Any]]:
    try:
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT id, created, product, best_model, best_pct, decision, status, chosen, "
                "chosen_by FROM match_requests WHERE best_model=? OR chosen=? "
                "ORDER BY id DESC LIMIT ?",
                (model_id, model_id, SHOWN),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def _companies(auth: Any, model_id: str, ps: dict[str, Any]) -> list[dict[str, Any]]:
    """B2B companies with a fixed price of their own (ex VAT) for this cover, and the price list
    each buys from (ADR-104)."""
    try:
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT id, name, status, price_list, fixed FROM b2b_companies ORDER BY name"
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for r in rows:
        fixed = json.loads(r["fixed"] or "{}")
        if model_id in fixed:
            pl = r["price_list"] or "b2b"
            out.append({"id": r["id"], "name": r["name"], "status": r["status"],
                        "price_list": pl,
                        "price_list_name": (ps["channels"].get(pl) or {}).get("name", pl),
                        "price_eur": fixed[model_id]})  # fmt: skip
    return out


def shop_place(models: Path, root: Path, model_id: str, p: Any) -> dict[str, Any]:
    """Is this cover offered in the shop as an existing cover, and if not, why; its kind, sizes
    and the price list's rows (section, item, suits)."""
    from coverengine import match as mt
    from coverengine import match_drawings as md
    from coverengine.catalogue import no_cover

    from coverapi import match_list

    d = models / model_id
    listing = match_list.for_data(root)
    out: dict[str, Any] = {"offered": False, "why_not": None, "card": None, "price_list": [],
                           "codes": [], "doubts": [], "desk_status": None}  # fmt: skip
    if model_id.startswith("drawing-"):
        r = md.review(d, p, listing, md.owners(models, p))
        if r is None:
            out["why_not"] = "no calculated cover (no model.json)"
            return out
        out.update({"offered": bool(r["offered"]), "why_not": r["why_not"],
                    "price_list": r["price_list"], "codes": r["codes"], "doubts": r["doubts"],
                    "desk_status": r["status"],
                    "card": {k: r[k] for k in ("name", "category", "kind", "size_cm", "side",
                                               "chairs", "height_max")}})  # fmt: skip
        return out
    if no_cover(d):
        out["why_not"] = "marked as needing no cover"
        return out
    if not (model_id.startswith("suns-") or model_id.startswith("bbq-")):
        out["why_not"] = "only SUNS, drawing and barbecue covers are offered as existing covers"
        return out
    c = mt.card(d, None, listing, p)
    if c is None:
        out["why_not"] = (
            "Desk status or the configurator's product not set"
            if model_id.startswith("bbq-")
            else "its kind is not known (category or size)"
        )
        return out
    out["offered"] = True
    out["card"] = {k: c.get(k) for k in ("name", "category", "kind", "size_cm", "side",
                                         "chairs", "height_max")}  # fmt: skip
    return out


def install(app: FastAPI, auth: Any, store: Any, facts: Any, draft: Any) -> None:
    from coverengine import costing

    from coverapi import prices
    from coverapi.security import require
    from coverapi.shop import SHOP_DEFAULTS, SHOP_SETTING, merged, shop_params

    @app.get("/api/prices/cover/{model_id}")
    def cover_prices(model_id: str, request: Request) -> dict[str, Any]:
        user = require(request, "edit")
        if not model_id or "/" in model_id or model_id.startswith("."):
            raise HTTPException(404, "no such cover")
        d = Path(store.models) / model_id
        if not d.is_dir():
            raise HTTPException(404, "no such cover")
        live = prices.current(auth)
        dr = draft()
        f = facts.get(model_id)
        out: dict[str, Any] = {
            "model": model_id,
            "can_edit": user.may("admin"),
            "calculated": f is not None,
            "published": (lambda p: p and {k: p[k] for k in ("version", "created", "username",
                                                              "note")})(prices.published(auth)),
            "draft": dr and {"by": dr.get("by"), "time": dr.get("time"), "note": dr.get("note"),
                             **draft_changes(live, dr["data"])},
            "channels": {
                k: {"name": ch.get("name", k), "show_vat": bool(ch.get("show_vat")),
                    "vat_pct": ch.get("vat_pct"),
                    "fixed_live": (ch.get("fixed") or {}).get(model_id),
                    "fixed_draft": ((dr["data"]["channels"].get(k) or {}).get("fixed") or {})
                    .get(model_id) if dr else None}
                for k, ch in live["channels"].items()
            },
            "costing": None,
            "costing_draft": None,
        }  # fmt: skip
        if f is not None:
            out["costing"] = {**costing.costing(f, live, model_id), "name": f["name"]}
            if dr:
                try:
                    out["costing_draft"] = costing.costing(f, dict(dr["data"]), model_id)
                except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                    out["costing_draft_error"] = f"the draft cannot cost this cover: {exc}"
        p = shop_params(auth)
        s = merged(SHOP_DEFAULTS, auth.setting(SHOP_SETTING, {}) or {})
        place = shop_place(Path(store.models), store.root, model_id, p)
        fixed_b2c = costing.fixed_price(live, model_id, "b2c")
        place["direct"] = {
            "price_source": "fixed" if fixed_b2c else "configurator",
            "fixed_eur": fixed_b2c["gross_eur"] if fixed_b2c else None,
            "discount_pct": float(s["matching"].get("stock_discount_pct") or 0),
            "delivery_note": {k: v for k, v in (s.get("stock_delivery_note") or {}).items() if v},
        }
        out["shop"] = place
        if user.may("admin"):  # as on Shop → Orders and Shop → B2B customers: admins only
            out["companies"] = _companies(auth, model_id, live)
            out["orders"] = _orders(auth, model_id)
            out["quotes"] = _quotes(Path(store.root), model_id)
            out["matches"] = _matches(auth, model_id)
        return out
