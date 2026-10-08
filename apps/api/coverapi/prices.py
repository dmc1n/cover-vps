"""Prices and costing (ADR-098, docs/plans/prices-costing.md): the admin page's price set,
versioned in app.db, and the costing of every cover.

- The **price set** (`coverengine/costing.py`): materials, labour, the fixed exchange rate,
  and per channel (b2c, b2b) the extra costs and the price list.
- **Draft → preview → publish.** An admin edits a draft (setting `prices_draft`); the preview
  shows which prices move (before / after); publishing stores a new version (table
  `price_sets`, who and when) and writes the audit log. A rollback publishes an earlier version
  again, as a new version, so the history only grows.
- Until the first publish, the price set is the defaults of config/defaults.yaml with the old
  Shop settings prices on top (ADR-062), so nothing changes for the shop until the owner
  publishes. "Indicative" goes when the owner publishes a set with it switched off.
- **Rights:** admins edit and publish; editors see the prices and the costings; viewers nothing.
- **Odoo** (step 2): `coverapi/odoo.py` maps a price set and a costing onto Odoo's records.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

DRAFT_SETTING = "prices_draft"
TABLE = """CREATE TABLE IF NOT EXISTS price_sets (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    created REAL NOT NULL,
    username TEXT,
    note TEXT,
    data TEXT NOT NULL,
    from_version INTEGER
)"""
KINDS = {"suns-": "catalogue", "drawing-": "drawing", "arr-": "arrangement", "order-": "order"}
CONFIGURATOR = "configurator:"  # a preview row for a configurator product at its default sizes


def ensure_table(auth: Any) -> None:
    with sqlite3.connect(auth.path) as db:
        db.execute(TABLE)


def published(auth: Any) -> dict[str, Any] | None:
    """The newest published version: {version, created, username, note, data}."""
    ensure_table(auth)
    with sqlite3.connect(auth.path) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM price_sets ORDER BY version DESC LIMIT 1").fetchone()
    if row is None:
        return None
    return {**dict(row), "data": json.loads(row["data"])}


def defaults(auth: Any) -> dict[str, Any]:
    """The price set before anything is published: config/defaults.yaml with the old Shop
    settings prices on top."""
    from coverengine import costing

    from coverapi.shop import shop_params

    return costing.default_price_set(shop_params(auth))


def current(auth: Any) -> dict[str, Any]:
    """The price set the shop, the configurator and the costing use now."""
    pub = published(auth)
    return pub["data"] if pub else defaults(auth)


def model_kind(model_id: str) -> str:
    return next((k for p, k in KINDS.items() if model_id.startswith(p)), "other")


def _name(d: Path) -> str:
    try:
        cover = json.loads((d / "cover.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d.name
    notes = str(cover.get("notes") or "").split("\n")[0]
    name = notes.split(": ")[-1] if d.name.startswith("suns-") else notes.split(":")[0]
    return (name or d.name)[:90]


class Facts:
    """Every calculated cover's facts, kept until its finished.json changes."""

    def __init__(self, models: Path) -> None:
        self.models = models
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, model_id: str) -> dict[str, Any] | None:
        from coverengine import costing
        from coverengine.params.registry import Registry, resolve_model

        d = self.models / model_id
        fin = d / "finished.json"
        if not fin.is_file():
            return None
        stamp = max(
            fin.stat().st_mtime,
            (d / "cover.json").stat().st_mtime if (d / "cover.json").is_file() else 0.0,
        )
        hit = self._cache.get(model_id)
        if hit and hit[0] == stamp:
            return hit[1]
        try:
            params = resolve_model(d)
        except Exception:  # noqa: BLE001 - a broken cover.json: the company defaults
            params = Registry.load(None).resolve()
        try:
            facts = costing.model_facts(d, params)
        except (OSError, ValueError, KeyError, TypeError):
            return None
        facts["name"] = _name(d)
        facts["kind"] = model_kind(model_id)
        self._cache[model_id] = (stamp, facts)
        return facts

    def all(self) -> dict[str, dict[str, Any]]:
        if not self.models.is_dir():
            return {}
        out = {}
        for d in sorted(p for p in self.models.iterdir() if p.is_dir()):
            f = self.get(d.name)
            if f is not None:
                out[d.name] = f
        return out


def _summary(c: dict[str, Any]) -> dict[str, float]:
    return {
        "cost": c["cost_eur"],
        "b2c": c["channels"]["b2c"]["shown_eur"],
        "b2b": c["channels"]["b2b"]["shown_eur"],
    }


def compare(
    before: dict[str, Any], after: dict[str, Any], facts: dict[str, dict[str, Any]], params: Any
) -> dict[str, Any]:
    """Which prices move from one price set to another: every calculated cover, the
    configurator's products at their default sizes, and the balloon and frame."""
    from coverengine import costing
    from coverengine import quote as q

    rows: list[dict[str, Any]] = []

    def add(key: str, name: str, kind: str, b: dict[str, float], a: dict[str, float]) -> None:
        moved = any(abs(a[k] - b[k]) >= 0.005 for k in a)  # noqa: PLR2004 - half a cent
        rows.append(
            {
                "key": key,
                "name": name,
                "kind": kind,
                "before": b,
                "after": a,
                "changed": moved,
                "delta_b2c": round(a["b2c"] - b["b2c"], 2),
            }
        )

    for mid, f in facts.items():
        add(
            mid,
            f["name"],
            f["kind"],
            _summary(costing.costing(f, before, mid)),
            _summary(costing.costing(f, after, mid)),
        )
    for product, spec in q.PRODUCTS.items():
        b = q.proposal(product, {}, params, before)["price"]["costing"]
        a = q.proposal(product, {}, params, after)["price"]["costing"]
        add(
            CONFIGURATOR + product,
            f"Configurator: {spec['label']} (default sizes)",
            "configurator",
            _summary(b),
            _summary(a),
        )
    for code in costing.ACCESSORIES:

        def acc(ps: dict[str, Any], code: str = code) -> dict[str, float]:
            comp = next((c for c in ps["components"] if c["code"] == code), None)
            cost = costing.to_eur(float(comp["price"]), comp["currency"], ps) if comp else 0.0
            return {
                "cost": round(cost, 2),
                **{
                    ch: costing.accessory_price(ps, code, ch)["shown_eur"]
                    for ch in costing.CHANNELS
                },
            }

        add(code, code.capitalize(), "accessory", acc(before), acc(after))
    changed = [r for r in rows if r["changed"]]
    changed.sort(key=lambda r: -abs(r["delta_b2c"]))
    return {"rows": changed, "changed": len(changed), "total": len(rows)}


def costing_csv(c: dict[str, Any], title: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Costing", title])
    ex = c["exchange"]
    w.writerow(["Exchange rate", f"{ex['idr_per_eur']:g} IDR per EUR", ex.get("date", "")])
    w.writerow(["Indicative", "yes" if c["indicative"] else "no"])
    w.writerow([])
    w.writerow(
        [
            "Section",
            "Code",
            "Item",
            "Quantity",
            "Unit",
            "Unit price",
            "Currency",
            "EUR",
            "IDR",
            "Note",
        ]
    )
    for x in c["lines"]:
        w.writerow(
            [
                x["section"],
                x["code"],
                x["name"],
                x["qty"],
                x["unit"],
                x["unit_price"],
                x["currency"],
                f"{x['eur']:.2f}",
                x["idr"],
                x["note"],
            ]
        )
    w.writerow(["cost price", "", "", "", "", "", "", f"{c['cost_eur']:.2f}", c["cost_idr"], ""])
    for name, ch in c["channels"].items():
        w.writerow([])
        w.writerow([f"{name}: {ch['name']}"])
        for e in ch["extras"]:
            w.writerow(["extra", e["code"], e["name"], "", "", "", "", f"{e['eur']:.2f}", e["idr"]])
        w.writerow(["landed cost", "", "", "", "", "", "", f"{ch['landed_eur']:.2f}"])
        w.writerow(["price ex VAT", "", "", "", "", "", "", f"{ch['net_eur']:.2f}"])
        w.writerow(["VAT", "", f"{ch['vat_pct']:g} %", "", "", "", "", f"{ch['vat_eur']:.2f}"])
        w.writerow(["price incl. VAT", "", "", "", "", "", "", f"{ch['gross_eur']:.2f}"])
        w.writerow(
            ["margin", "", f"{ch['margin_pct']:g} %", "", "", "", "", f"{ch['margin_eur']:.2f}"]
        )
        for code, a in ch["accessories"].items():
            w.writerow(
                [
                    "sold separately",
                    code,
                    f"{a['count']} x",
                    "",
                    "",
                    "",
                    "",
                    f"{a['shown_eur']:.2f}",
                ]
            )
    return buf.getvalue()


def costing_pdf(c: dict[str, Any], title: str) -> bytes:
    """The costing as a printable A4 page (pymupdf, as the drawings use)."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4 in points
    y = 50.0
    left = 40.0

    def text(s: str, x: float, size: float = 8.5, bold: bool = False) -> None:
        page.insert_text((x, y), s, fontsize=size, fontname="hebo" if bold else "helv")

    def row(cells: list[tuple[float, str]], bold: bool = False) -> None:
        nonlocal y
        nonlocal page
        if y > 800:  # noqa: PLR2004 - near the foot of the page
            page = doc.new_page(width=595, height=842)
            y = 50.0
        for x, s in cells:
            text(s, x, bold=bold)
        y += 12

    text(f"Costing: {title}", left, 14, True)
    y += 18
    ex = c["exchange"]
    row(
        [
            (
                left,
                f"Exchange rate {ex['idr_per_eur']:,.0f} IDR = 1 EUR ({ex.get('date', '')})"
                + ("   ·   INDICATIVE: placeholder prices" if c["indicative"] else ""),
            )
        ]
    )
    y += 6
    cols = (left, 95, 300, 360, 430, 500)
    row(
        list(zip(cols, ["Section", "Item", "Quantity", "Unit price", "EUR", "IDR"], strict=True)),
        bold=True,
    )
    for x in c["lines"]:
        row(
            list(
                zip(
                    cols,
                    [
                        x["section"],
                        x["name"][:42],
                        f"{x['qty']:g} {x['unit']}",
                        f"{x['unit_price']:,.2f} {x['currency']}",
                        f"{x['eur']:,.2f}",
                        f"{x['idr']:,}",
                    ],
                    strict=True,
                )
            )
        )
    row(
        list(
            zip(
                cols,
                ["", "Cost price", "", "", f"{c['cost_eur']:,.2f}", f"{c['cost_idr']:,}"],
                strict=True,
            )
        ),
        bold=True,
    )
    for ch in c["channels"].values():
        y += 8
        row([(left, ch["name"])], bold=True)
        for e in ch["extras"]:
            row([(95, e["name"]), (430, f"{e['eur']:,.2f}"), (500, f"{e['idr']:,}")])
        row([(95, "Landed cost"), (430, f"{ch['landed_eur']:,.2f}")], bold=True)
        how = f"{ch['method']} {ch['pct']:g} % on the {ch['base']} cost"
        row([(95, f"Price ex VAT ({how})"), (430, f"{ch['net_eur']:,.2f}")])
        row([(95, f"VAT {ch['vat_pct']:g} %"), (430, f"{ch['vat_eur']:,.2f}")])
        row([(95, "Price incl. VAT"), (430, f"{ch['gross_eur']:,.2f}")], bold=True)
        row(
            [
                (95, f"Margin ({ch['margin_pct']:g} % of the price ex VAT)"),
                (430, f"{ch['margin_eur']:,.2f}"),
            ]
        )
    out: bytes = doc.tobytes()
    return out


def install(app: FastAPI, auth: Any, store: Any) -> None:
    from coverengine import costing
    from coverengine import quote as q
    from coverengine.errors import CoverError

    from coverapi.security import require
    from coverapi.shop import shop_params

    ensure_table(auth)
    facts = Facts(store.models)

    def draft() -> dict[str, Any] | None:
        d: dict[str, Any] | None = auth.setting(DRAFT_SETTING, None)
        return d

    def which(name: str | None) -> dict[str, Any]:
        """The price set asked for: draft (when there is one) or the current one."""
        if name == "draft":
            d = draft()
            if d:
                return dict(d["data"])
        return current(auth)

    def checked(ps: Any) -> dict[str, Any]:
        if not isinstance(ps, dict):
            raise HTTPException(400, "the price set must be an object")
        ps = costing.normalised(ps)
        errs = costing.validate(ps)
        if errs:
            raise HTTPException(400, "; ".join(errs))
        return ps

    @app.get("/api/prices")
    def get_prices(request: Request) -> dict[str, Any]:
        user = require(request, "edit")
        pub = published(auth)
        d = draft()
        return {
            "published": pub,
            "current": pub["data"] if pub else defaults(auth),
            "using_defaults": pub is None,
            "draft": d,
            "draft_errors": costing.validate(d["data"]) if d else [],
            "defaults": defaults(auth),
            "can_edit": user.may("admin"),
            "choices": {
                "per": list(costing.PER),
                "per_label": costing.PER_LABEL,
                "currencies": list(costing.CURRENCIES),
                "roundings": list(costing.ROUNDINGS),
                "methods": list(costing.METHODS),
                "bases": list(costing.BASES),
                "duty_modes": list(costing.DUTY_MODES),
            },
        }

    @app.put("/api/prices/draft")
    async def put_draft(request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        body = await request.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise HTTPException(400, "send {data: the price set}")
        data = costing.normalised(data)
        d = {"data": data, "by": admin.username, "time": time.time()}
        auth.set_setting(DRAFT_SETTING, d)
        return {"draft": d, "errors": costing.validate(data)}

    @app.delete("/api/prices/draft")
    def discard_draft(request: Request) -> dict[str, Any]:
        require(request, "admin")
        auth.set_setting(DRAFT_SETTING, None)
        return {"draft": None}

    @app.post("/api/prices/preview")
    async def preview(request: Request) -> dict[str, Any]:
        require(request, "edit")
        body = {}
        try:
            body = await request.json()
        except ValueError:
            body = {}
        data = (body or {}).get("data") if isinstance(body, dict) else None
        if data is None:
            d = draft()
            if not d:
                raise HTTPException(400, "no draft to preview")
            data = d["data"]
        after = costing.normalised(data)
        errs = costing.validate(after)
        if errs:
            return {"errors": errs, "rows": [], "changed": 0, "total": 0}
        out = compare(current(auth), after, facts.all(), shop_params(auth))
        return {"errors": [], **out}

    @app.post("/api/prices/publish")
    async def publish(request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        body: dict[str, Any] = {}
        try:
            body = await request.json() or {}
        except ValueError:
            body = {}
        d = draft()
        if not d:
            raise HTTPException(400, "no draft to publish")
        data = checked(d["data"])
        before = current(auth)
        moved = compare(before, data, facts.all(), shop_params(auth))["changed"]
        note = str(body.get("note") or "")[:500]
        with sqlite3.connect(auth.path) as db:
            cur = db.execute(
                "INSERT INTO price_sets (created, username, note, data) VALUES (?, ?, ?, ?)",
                (time.time(), admin.username, note, json.dumps(data)),
            )
            version = cur.lastrowid
        auth.set_setting(DRAFT_SETTING, None)
        auth.log(
            admin,
            "prices published",
            {
                "version": version,
                "note": note,
                "prices_changed": moved,
                "indicative": bool(data.get("indicative")),
            },
        )
        return {"version": version, "prices_changed": moved}

    @app.get("/api/prices/versions")
    def versions(request: Request) -> dict[str, Any]:
        require(request, "edit")
        ensure_table(auth)
        with sqlite3.connect(auth.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM price_sets ORDER BY version DESC").fetchall()
        return {"versions": [{**dict(r), "data": json.loads(r["data"])} for r in rows]}

    @app.post("/api/prices/rollback/{version}")
    def rollback(version: int, request: Request) -> dict[str, Any]:
        admin = require(request, "admin")
        with sqlite3.connect(auth.path) as db:
            row = db.execute("SELECT data FROM price_sets WHERE version=?", (version,)).fetchone()
            if row is None:
                raise HTTPException(404, "no such version")
            cur = db.execute(
                "INSERT INTO price_sets (created, username, note, data, from_version) "
                "VALUES (?, ?, ?, ?, ?)",
                (time.time(), admin.username, f"rolled back to version {version}", row[0], version),
            )
            new = cur.lastrowid
        auth.log(admin, "prices rolled back", {"to": version, "version": new})
        return {"version": new, "from_version": version}

    @app.get("/api/prices/products")
    def products(request: Request) -> dict[str, Any]:
        require(request, "edit")
        rows = [{"id": k, "name": f["name"], "kind": f["kind"]} for k, f in facts.all().items()]
        return {
            "models": rows,
            "configurator": [
                {
                    "product": k,
                    "label": v["label"],
                    "fields": [
                        {"key": f, "default": d, "min": lo, "max": hi}
                        for f, (d, lo, hi) in v["fields"].items()
                    ],
                }
                for k, v in q.PRODUCTS.items()
            ],
        }

    def costing_for(request: Request) -> tuple[dict[str, Any], str]:
        """?model=<id> or ?product=<p>&sizes=<json>&colour=..; &set=draft|current."""
        qp = request.query_params
        ps = which(qp.get("set"))
        model = qp.get("model")
        if model:
            f = facts.get(model)
            if f is None:
                raise HTTPException(404, "no calculated cover (finished.json) for this model")
            c = costing.costing(f, ps, model, colour=qp.get("colour") or None)
            return {**c, "model": model, "name": f["name"], "kind": f["kind"]}, model
        product = qp.get("product") or ""
        try:
            sizes = json.loads(qp.get("sizes") or "{}")
        except ValueError:
            raise HTTPException(400, "sizes: JSON") from None
        given = {
            **(sizes if isinstance(sizes, dict) else {}),
            "colour": qp.get("colour") or None,
            "vents": qp.get("vents", "true") != "false",
        }
        try:
            full = q.proposal(product, given, shop_params(auth), ps)
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        c = full["price"]["costing"]
        label = q.PRODUCTS[product]["label"]
        return {
            **c,
            "product": product,
            "name": f"Configurator: {label}",
            "kind": "configurator",
            "sizes_cm": full["sizes_cm"],
        }, f"configurator-{product}"

    @app.get("/api/prices/costing")
    def get_costing(request: Request) -> dict[str, Any]:
        require(request, "edit")
        return costing_for(request)[0]

    @app.get("/api/prices/costing.csv")
    def get_costing_csv(request: Request) -> Response:
        require(request, "edit")
        c, slug = costing_for(request)
        return Response(
            costing_csv(c, c["name"]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="costing-{slug}.csv"'},
        )

    @app.get("/api/prices/costing.pdf")
    def get_costing_pdf(request: Request) -> Response:
        require(request, "edit")
        c, slug = costing_for(request)
        return Response(
            costing_pdf(c, c["name"]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="costing-{slug}.pdf"'},
        )

    @app.get("/api/prices/odoo")
    def odoo_preview(request: Request) -> dict[str, Any]:
        """What step 2 would send to Odoo for this price set (and one cover): no connection."""
        from coverapi import odoo

        require(request, "admin")
        ps = which(request.query_params.get("set"))
        model = request.query_params.get("model")
        f = facts.get(model) if model else None
        return odoo.records(ps, {model: f} if model and f else {})
