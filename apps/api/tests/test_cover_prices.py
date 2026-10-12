"""A cover's Price & shop tab (ADR-126): a fixed price set on the cover's page lands in the same
draft row as from the whole-set editor; nothing is published by it; viewers and editors cannot
write; a stale page cannot overwrite a newer draft; the cover's own view of its prices, its shop
place and (for admins) its orders, quotes and B2B companies; the price columns of All covers."""

import json
import sqlite3
from typing import Any

from test_prices import app, login  # noqa: F401 - the same app, users and test cover

MODEL = "drawing-t1"


def test_a_price_from_the_cover_lands_in_the_same_draft_row(app: Any) -> None:  # noqa: F811
    admin = login(app, "rick")
    live = admin.get("/api/prices").json()["current"]
    # the old way: the whole set with the fixed price, into the draft
    doc = json.loads(json.dumps(live))
    doc["channels"]["b2c"]["fixed"][MODEL] = 849.0
    whole = admin.put("/api/prices/draft", json={"data": doc}).json()["draft"]["data"]
    admin.delete("/api/prices/draft")
    # the cover's page: one row
    r = admin.put("/api/prices/draft/fixed",
                  json={"model": MODEL, "channel": "b2c", "price": 849})  # fmt: skip
    assert r.status_code == 200, r.text
    one = admin.get("/api/prices").json()["draft"]["data"]
    assert one == whole  # the same draft, row for row
    assert one["channels"]["b2c"]["fixed"][MODEL] == 849.0
    # never published by it
    s = admin.get("/api/prices").json()
    assert s["published"] is None and MODEL not in s["current"]["channels"]["b2c"]["fixed"]
    # the cover's view: live calculated, draft fixed
    c = admin.get(f"/api/prices/cover/{MODEL}").json()
    assert c["channels"]["b2c"]["fixed_live"] is None
    assert c["channels"]["b2c"]["fixed_draft"] == 849.0
    assert c["costing"]["channels"]["b2c"]["fixed"] is False
    assert c["costing_draft"]["channels"]["b2c"]["shown_eur"] == 849.0
    assert (
        c["draft"]["fixed"] == [{"channel": "b2c", "key": MODEL, "live": None, "draft": 849.0}]
        and c["draft"]["other"] is False
    )
    # a B2B price keeps the other row; removing it brings the calculated price back
    admin.put("/api/prices/draft/fixed", json={"model": MODEL, "channel": "b2b", "price": 500.5})
    d = admin.get("/api/prices").json()["draft"]["data"]["channels"]
    assert d["b2c"]["fixed"][MODEL] == 849.0 and d["b2b"]["fixed"][MODEL] == 500.5
    admin.put("/api/prices/draft/fixed", json={"model": MODEL, "channel": "b2c", "price": None})
    d = admin.get("/api/prices").json()["draft"]["data"]["channels"]
    assert MODEL not in d["b2c"]["fixed"] and d["b2b"]["fixed"][MODEL] == 500.5
    # publishing stays its own action, and then the shop's set has it
    v = admin.post("/api/prices/publish", json={"note": "B2B price"}).json()
    assert v["version"] == 1
    assert admin.get("/api/prices").json()["current"]["channels"]["b2b"]["fixed"][MODEL] == 500.5


def test_viewers_and_editors_cannot_change_a_price(app: Any) -> None:  # noqa: F811
    editor, viewer = login(app, "eddy"), login(app, "vera")
    body = {"model": MODEL, "channel": "b2c", "price": 10}
    assert viewer.put("/api/prices/draft/fixed", json=body).status_code == 403
    assert editor.put("/api/prices/draft/fixed", json=body).status_code == 403
    assert viewer.get(f"/api/prices/cover/{MODEL}").status_code == 403
    assert viewer.get("/api/prices/list").status_code == 403
    e = editor.get(f"/api/prices/cover/{MODEL}")
    assert e.status_code == 200 and e.json()["can_edit"] is False
    assert "orders" not in e.json() and "companies" not in e.json()  # admins only
    assert editor.get("/api/prices").json()["draft"] is None


def test_bad_fixed_prices_are_refused(app: Any) -> None:  # noqa: F811
    admin = login(app, "rick")
    for body in ({"model": MODEL, "channel": "b2c", "price": 0},
                 {"model": MODEL, "channel": "b2c", "price": -5},
                 {"model": MODEL, "channel": "b2c", "price": "12"},
                 {"model": MODEL, "channel": "b2c", "price": True},
                 {"model": MODEL, "channel": "nope", "price": 12},
                 {"model": "../x", "channel": "b2c", "price": 12}):  # fmt: skip
        assert admin.put("/api/prices/draft/fixed", json=body).status_code == 400, body
    assert admin.get("/api/prices").json()["draft"] is None


def test_a_stale_page_does_not_overwrite_or_publish_a_newer_draft(app: Any) -> None:  # noqa: F811
    admin = login(app, "rick")
    first = admin.get("/api/prices").json()
    live, seen = first["current"], first["revision"]
    assert seen == "v0:"  # nothing published, no draft
    # the Settings page loaded with no draft; then a price is set on a cover
    admin.put("/api/prices/draft/fixed", json={"model": MODEL, "channel": "b2c", "price": 99})
    now = admin.get("/api/prices").json()["revision"]
    r = admin.put("/api/prices/draft", json={"data": live, "since": seen})
    assert r.status_code == 409
    assert admin.get("/api/prices").json()["draft"]["data"]["channels"]["b2c"]["fixed"][MODEL] == 99
    assert admin.post("/api/prices/publish", json={"since": seen}).status_code == 409
    assert admin.get("/api/prices").json()["published"] is None
    # with the right one it goes through (and without `since`, as before)
    assert admin.post("/api/prices/publish", json={"since": now}).status_code == 200


def test_publish_and_clear_elsewhere_does_not_let_a_stale_page_revert(app: Any) -> None:  # noqa: F811
    """Codex's second review: a page loaded without a draft; elsewhere a cover price is set and
    published (the draft is cleared again). The stale page's whole set must not go back."""
    a, b = login(app, "rick"), login(app, "rick")
    first = a.get("/api/prices").json()
    stale_doc, seen = first["current"], first["revision"]
    rb = b.get(f"/api/prices/cover/{MODEL}").json()["revision"]
    b.put("/api/prices/draft/fixed",
          json={"model": MODEL, "channel": "b2c", "price": 555, "since": rb})  # fmt: skip
    assert b.post("/api/prices/publish", json={"since": b.get("/api/prices").json()["revision"]}
                  ).status_code == 200  # fmt: skip
    assert a.get("/api/prices").json()["draft"] is None  # cleared, as when the page loaded
    assert a.put("/api/prices/draft", json={"data": stale_doc, "since": seen}).status_code == 409
    assert a.post("/api/prices/publish", json={"since": seen}).status_code in (400, 409)
    live = a.get("/api/prices").json()
    assert live["current"]["channels"]["b2c"]["fixed"][MODEL] == 555 and live["draft"] is None


def test_the_cover_view_shop_place_and_admin_lists(app: Any) -> None:  # noqa: F811
    admin = login(app, "rick")
    c = admin.get(f"/api/prices/cover/{MODEL}").json()
    assert c["calculated"] and c["can_edit"]
    assert c["costing"]["cost_eur"] > 0 and c["costing_draft"] is None and c["draft"] is None
    assert c["shop"]["offered"] is False and c["shop"]["why_not"]
    assert c["shop"]["direct"]["price_source"] == "configurator"
    assert c["orders"] == [] and c["quotes"] == [] and c["companies"] == []
    # an existing-cover order and a stock quote of this cover are listed
    auth = app.state.auth
    with sqlite3.connect(auth.path) as db:
        db.execute(
            "INSERT INTO orders (created, token, status, email, data, total_eur) "
            "VALUES (1, 'tok', 'paid', 'a@b.c', ?, 849)",
            (json.dumps({"stock": {"model_id": MODEL, "name": "T1"},
                         "customer": {"name": "Ann"}}),),
        )  # fmt: skip
        db.execute(
            "INSERT INTO orders (created, token, status, email, data, total_eur) "
            "VALUES (2, 'tok2', 'paid', 'a@b.c', ?, 10)",
            (json.dumps({"stock": {"model_id": MODEL + "x"}, "note": MODEL}),),
        )
        b2b = {"company": "De Linde", "qty": 2, "order": 1}  # a B2B line: the stock in its quote
        db.execute(
            "INSERT INTO orders (created, token, status, email, data, total_eur) "
            "VALUES (3, 'tok3', 'on_account', 'a@b.c', ?, 600)",
            (json.dumps({"quote": {"stock": {"model_id": MODEL}}, "b2b": b2b}),),
        )
    q = app.state.store.root / "shop_quotes"
    q.mkdir(exist_ok=True)
    stock = {"model_id": MODEL, "price_eur": 849, "price_source": "fixed"}
    (q / "abc.json").write_text(json.dumps({"time": 5, "stock": stock}))
    c = admin.get(f"/api/prices/cover/{MODEL}").json()
    assert [o["id"] for o in c["orders"]] == [3, 1] and c["orders"][1]["customer"] == "Ann"
    assert c["orders"][0]["b2b"] and c["orders"][0]["customer"] == "De Linde"
    assert c["orders"][0]["qty"] == 2
    assert [x["id"] for x in c["quotes"]] == ["abc"]
    assert admin.get("/api/prices/cover/nothing-here").status_code == 404


def test_the_price_columns_of_all_covers(app: Any) -> None:  # noqa: F811
    admin, editor = login(app, "rick"), login(app, "eddy")
    listed = editor.get("/api/prices/list").json()
    rows = listed["rows"]
    assert listed["units"]["b2c"]["show_vat"] is True  # the columns are named after these
    assert listed["units"]["b2b"]["show_vat"] is False
    assert MODEL in rows and rows[MODEL]["b2c"]["fixed"] is False
    one = editor.get(f"/api/prices/costing?model={MODEL}").json()
    assert rows[MODEL]["cost"] == one["cost_eur"]
    assert rows[MODEL]["b2c"]["shown"] == one["channels"]["b2c"]["shown_eur"]
    admin.put("/api/prices/draft/fixed", json={"model": MODEL, "channel": "b2c", "price": 849})
    d = editor.get("/api/prices/list?set=draft").json()
    assert d["set"] == "draft" and d["rows"][MODEL]["b2c"] == {
        **d["rows"][MODEL]["b2c"], "shown": 849.0, "fixed": True}  # fmt: skip
    assert editor.get("/api/prices/list").json()["rows"][MODEL]["b2c"]["fixed"] is False


def test_interleaved_edits_are_refused_not_lost(app: Any) -> None:  # noqa: F811
    """Codex's review: a page publishes the draft it saved, never a newer one; a cover page's
    stale Save or Remove does not overwrite a newer fixed price."""
    a, b = login(app, "rick"), login(app, "rick")
    first = a.get("/api/prices").json()
    saved = a.put("/api/prices/draft", json={"data": first["current"], "since": first["revision"]})
    rev = saved.json()["revision"]
    # B sets a cover price between A's save and A's publish
    fix = {"model": MODEL, "channel": "b2c", "price": 700, "since": rev}
    assert b.put("/api/prices/draft/fixed", json=fix).status_code == 200
    r = a.post("/api/prices/publish", json={"note": "A", "since": rev})
    assert r.status_code == 409
    assert a.get("/api/prices").json()["published"] is None  # B's price not published unseen
    # a cover page that loaded the prices before B's change cannot remove B's price
    stale = {"model": MODEL, "channel": "b2c", "price": None, "since": rev}
    assert a.put("/api/prices/draft/fixed", json=stale).status_code == 409
    d = a.get("/api/prices").json()
    assert d["draft"]["data"]["channels"]["b2c"]["fixed"][MODEL] == 700
    # with the prices it has seen, it may
    seen = {**stale, "since": d["revision"]}
    assert a.put("/api/prices/draft/fixed", json=seen).status_code == 200


def test_a_save_during_a_read_never_gives_a_token_for_unseen_prices(
    app: Any,  # noqa: F811
    monkeypatch: Any,
) -> None:
    """Codex's third review: the revision a page gets belongs to the very records it is shown,
    even when another admin saves while the answer is being put together."""
    import time as clock

    from coverapi import prices as pr

    a = login(app, "rick")
    a.put("/api/prices/draft/fixed", json={"model": MODEL, "channel": "b2c", "price": 600})
    auth = app.state.auth
    real = pr.published

    def published_then_someone_saves(au: Any) -> Any:
        out = real(au)
        d = dict(au.setting(pr.DRAFT_SETTING, None))
        d["time"] = clock.time() + 1  # another admin's newer draft, written mid-request
        d["data"]["channels"]["b2c"]["fixed"][MODEL] = 650
        au.set_setting(pr.DRAFT_SETTING, d)
        return out

    monkeypatch.setattr(pr, "published", published_then_someone_saves)
    for answer in (a.get("/api/prices").json(), a.get(f"/api/prices/cover/{MODEL}").json()):
        shown = answer["draft"]["time"]
        assert answer["revision"] == f"v0:{shown}"  # the token is the shown draft's
    monkeypatch.setattr(pr, "published", real)
    latest = auth.setting(pr.DRAFT_SETTING, None)
    shown_rev = a.get(f"/api/prices/cover/{MODEL}").json()["revision"]
    assert shown_rev == f"v0:{latest['time']}"


def test_a_stale_discard_keeps_newer_cover_prices(app: Any) -> None:  # noqa: F811
    """Codex's fourth review: Discard draft from a page that loaded older prices does not throw
    away a cover price saved since."""
    a, b = login(app, "rick"), login(app, "rick")
    a.put("/api/prices/draft/fixed", json={"model": MODEL, "channel": "b2c", "price": 600})
    seen = a.get("/api/prices").json()["revision"]  # Settings loaded with this draft
    rb = b.get(f"/api/prices/cover/{MODEL}").json()["revision"]
    fix = {"model": MODEL, "channel": "b2b", "price": 400, "since": rb}
    assert b.put("/api/prices/draft/fixed", json=fix).status_code == 200
    assert a.delete("/api/prices/draft", params={"since": seen}).status_code == 409
    d = a.get("/api/prices").json()
    assert d["draft"]["data"]["channels"]["b2b"]["fixed"][MODEL] == 400
    assert a.delete("/api/prices/draft", params={"since": d["revision"]}).status_code == 200
    assert a.get("/api/prices").json()["draft"] is None


def test_the_cover_names_the_drafts_vat_unit(app: Any) -> None:  # noqa: F811
    """Codex's sixth review: a price typed on the cover goes into the draft in the draft's unit;
    the page is told that unit when the draft shows a channel differently from the live set."""
    a = login(app, "rick")
    first = a.get("/api/prices").json()
    doc = first["current"]
    doc["channels"]["b2c"]["show_vat"] = False
    a.put("/api/prices/draft", json={"data": doc, "since": first["revision"]})
    ch = a.get(f"/api/prices/cover/{MODEL}").json()["channels"]["b2c"]
    assert ch["show_vat"] is True and ch["draft_show_vat"] is False
    assert ch["draft_vat_pct"] == doc["channels"]["b2c"]["vat_pct"]
