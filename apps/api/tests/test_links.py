"""Drawing/model links: synthetic scores, decisions, permissions and consumers only."""

import importlib.util
import json
import selectors
import socket
import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from coverapi import link_score as ls
from coverapi import links, prices_import, products_sheet
from coverapi.main import create_app
from coverengine.params import Registry
from fastapi import HTTPException
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]
DRAWING = "drawing-d2"
MODEL = "suns-sunlounger-evora"


@pytest.fixture(autouse=True)
def isolated_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path))
    links._CACHE.clear()
    yield
    links._CACHE.clear()


@pytest.fixture(scope="module")
def p() -> Any:
    return Registry.load(None).resolve()


@pytest.fixture
def true_pair() -> tuple[ls.Facts, ls.Facts]:
    drawing = ls.Facts(
        DRAWING,
        "drawing",
        families={"evora"},
        types={"sunlounger"},
        cover_cm=[222, 93, 80],
        plan="straight",
        kind="lounger",
    )
    model = ls.Facts(
        MODEL,
        "model",
        families={"evora"},
        types={"sunlounger"},
        cover_cm=[224, 92, 78],
        plan="straight",
        kind="lounger",
    )
    return drawing, model


@pytest.fixture
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    conn = links.connect(tmp_path / "app.db")
    try:
        yield conn
    finally:
        conn.close()


def proposal(**extra: Any) -> dict[str, Any]:
    return {
        "drawing_id": DRAWING,
        "model_id": MODEL,
        "score": 0.95,
        "signals": {"names": 1.0, "size": 1.0},
        "reasons": ["same family", "sizes agree"],
        "doubts": [],
        "mirror": False,
        "sheet": None,
        **extra,
    }


def insert(db: sqlite3.Connection, **extra: Any) -> dict[str, Any]:
    spec = proposal(**extra)
    assert links.upsert_proposal(db, spec, "high", {}) == "new"
    row = db.execute(
        "SELECT * FROM model_links WHERE drawing_id=? AND model_id=?",
        (spec["drawing_id"], spec["model_id"]),
    ).fetchone()
    assert row is not None
    return links.row_out(row)


def write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def cover(models: Path, mid: str) -> Path:
    d = models / mid
    write_json(d / "cover.json", {"format_version": 1, "model_id": mid})
    return d


def test_d2_sheet_link_is_contradicted(p: Any) -> None:
    drawing = ls.Facts(
        DRAWING,
        "drawing",
        families={"evora"},
        types={"d-bed"},
        cover_cm=[230, 204, 82],
        plan="straight",
        kind="lounger",
        sheet_linked=[MODEL],
        sheet_label="Evora normal D- Bed",
    )
    model = ls.Facts(
        MODEL,
        "model",
        families={"evora"},
        types={"sunlounger"},
        cover_cm=[222, 92.6, 78.2],
        plan="straight",
        kind="lounger",
    )
    result = ls.score(drawing, model, p)
    assert result["score"] < p["links.propose_min"]
    assert any("says no" in doubt for doubt in result["doubts"])
    assert ls.strength(result, p) == "unsure"
    assert result["sheet"] == "linked"
    # Even a contradicted sheet pair must reach the queue for a person's review.
    proposed, alone = ls.proposals([drawing], [model], p, per_drawing=1)
    assert proposed == [result]
    assert alone == []


def test_true_pair_is_high(true_pair: tuple[ls.Facts, ls.Facts], p: Any) -> None:
    result = ls.score(*true_pair, p)
    assert result["score"] >= p["links.bulk_min"]
    assert result["doubts"] == []
    assert ls.strength(result, p) == "high"


@pytest.mark.parametrize("sides,mirror,signal", [({"left"}, True, 0.5), ({"both"}, False, 1.0)])
def test_side_mirror(
    true_pair: tuple[ls.Facts, ls.Facts], p: Any, sides: set[str], mirror: bool, signal: float
) -> None:
    drawing, model = true_pair
    result = ls.score(replace(drawing, sides=sides), replace(model, sides={"right"}), p)
    assert result["mirror"] is mirror
    assert result["signals"]["side"] == signal


def test_another_family_adds_doubt(true_pair: tuple[ls.Facts, ls.Facts], p: Any) -> None:
    drawing, model = true_pair
    result = ls.score(drawing, replace(model, families={"vento"}), p)
    assert any("another family" in doubt for doubt in result["doubts"])
    assert ls.strength(result, p) == "unsure"


@pytest.mark.parametrize(
    "shape,expected",
    [
        ("rectangle", ("straight", None)),
        ("left-l", ("L", "left")),
        ("right-l", ("L", "right")),
        ("u", ("U", None)),
        ("disc", ("round", None)),
    ],
)
def test_plan_shape(shape: str, expected: tuple[str, str | None]) -> None:
    grid = np.ones((40, 60), dtype=bool)
    if shape in {"left-l", "right-l"}:
        grid[20:, 30:] = False
        if shape == "right-l":
            grid = grid[:, ::-1]
    elif shape == "u":
        grid[20:, 20:40] = False
    elif shape == "disc":
        y, x = np.ogrid[-30:31, -30:31]
        grid = x * x + y * y <= 30 * 30
    assert ls.plan_shape(grid) == expected


@pytest.mark.parametrize(
    "text,expected", [("Evora normal D- Bed", "d-bed"), ("SUNS Sunlounger Evora", "sunlounger")]
)
def test_lounger_type(text: str, expected: str) -> None:
    assert ls.lounger_type(text) == expected
    assert ls.types_of([text])[0] == {expected}


def test_types_of_combines_mirror_hands() -> None:
    types, sides = ls.types_of(["Evora sunlounger left", "Evora sunlounger right"])
    assert types == {"sunlounger"}
    assert sides == {"both"}


def test_size_signal_missing_close_and_incompatible(p: Any) -> None:
    assert ls.size_signal(None, [222, 93, 80], p) == (None, [])
    signal, differences = ls.size_signal([222, 93, 80], [224, 92, 78], p)
    assert signal == 1.0
    assert differences == [2, -1, -2]
    signal, differences = ls.size_signal([230, 204, 82], [222, 92.6, 78.2], p)
    assert signal == 0.0
    assert differences == [-8, -111.4, -3.8]


def test_picture_signal_detects_mirror_and_missing_images() -> None:
    image = np.zeros((8, 12), dtype=bool)
    image[1:7, 1:4] = True
    assert ls.picture_signal(image, image.copy()) == (1.0, False)
    assert ls.picture_signal(image, image[:, ::-1]) == (1.0, True)
    assert ls.picture_signal(None, image) == (None, False)
    assert ls.picture_signal(image, image[:4]) == (None, False)


def test_proposals_rank_limit_and_report_unpaired(
    true_pair: tuple[ls.Facts, ls.Facts], p: Any
) -> None:
    drawing, model = true_pair
    second = replace(model, id="suns-second")
    alone_drawing = ls.Facts("drawing-alone", "drawing")
    proposed, alone = ls.proposals([drawing, alone_drawing], [model, second], p, per_drawing=1)
    assert [(r["drawing_id"], r["model_id"]) for r in proposed] == [(drawing.id, second.id)]
    assert alone == [alone_drawing.id]


def test_upsert_new_unchanged_updated(db: sqlite3.Connection) -> None:
    spec = proposal()
    assert links.upsert_proposal(db, spec, "high", {}) == "new"
    row = dict(db.execute("SELECT * FROM model_links").fetchone())
    assert row["status"] == "proposed"
    assert links.upsert_proposal(db, spec, "high", {}) == "unchanged"
    assert dict(links.get(db, row["id"])) == row
    assert links.upsert_proposal(db, {**spec, "score": 0.9}, "high", {}) == "updated"
    updated = links.get(db, row["id"])
    assert updated["score"] == 0.9
    assert updated["version"] == row["version"] + 1
    assert [event["action"] for event in links.history(db, row["id"])] == ["propose", "refresh"]


@pytest.mark.parametrize("status", ["confirmed", "rejected", "manual"])
def test_person_rows_survive_refresh_and_stale(db: sqlite3.Connection, status: str) -> None:
    row = insert(db)
    if status == "manual":
        links.choose(db, DRAWING, MODEL, "editor", note="chosen by hand")
    else:
        links.decide(db, row["id"], status, "editor", note="reviewed")
    before = dict(links.get(db, row["id"]))
    history = links.history(db, row["id"])
    changed = proposal(score=0.1, reasons=["different reasons"], doubts=["new doubt"], mirror=True)
    assert links.upsert_proposal(db, changed, "unsure", {"new": "facts"}) == "person"
    assert dict(links.get(db, row["id"])) == before
    abandoned = insert(db, model_id="suns-abandoned")
    kept = insert(db, model_id="suns-kept")
    assert links.mark_stale(db, {(DRAWING, "suns-kept")}) == 1
    assert dict(links.get(db, row["id"])) == before
    assert links.history(db, row["id"]) == history
    assert links.get(db, abandoned["id"])["stale"] == 1
    assert links.get(db, abandoned["id"])["version"] == abandoned["version"] + 1
    assert links.get(db, kept["id"])["stale"] == 0
    assert db.execute("SELECT count(*) FROM model_links").fetchone()[0] == 3
    assert links.mark_stale(db, {(DRAWING, "suns-kept")}) == 0


def test_decide_stale_version_is_conflict(db: sqlite3.Connection) -> None:
    row = insert(db)
    updated = links.decide(db, row["id"], "confirmed", "editor", version=row["version"])
    with pytest.raises(HTTPException) as exc:
        links.decide(db, row["id"], "rejected", "admin", version=row["version"])
    assert exc.value.status_code == 409
    assert links.row_out(links.get(db, row["id"])) == updated
    assert len(links.history(db, row["id"])) == 2


@pytest.mark.parametrize("existing", [False, True])
def test_choose_replaces_and_logs_both(db: sqlite3.Connection, existing: bool) -> None:
    old = insert(db)
    new = insert(db, model_id="suns-other") if existing else None
    result = links.choose(
        db,
        DRAWING,
        "suns-other",
        "editor",
        replaces=old["id"],
        note="better fit",
        replaces_version=old["version"],
    )
    assert result["link"]["status"] == "manual"
    assert result["link"]["model_id"] == "suns-other"
    assert result["link"]["note"] == "better fit"
    if new:
        assert result["link"]["id"] == new["id"]
    rejected = links.row_out(links.get(db, old["id"]))
    assert result["replaced"] == rejected
    assert rejected["status"] == "rejected"
    assert rejected["note"] == "replaced by suns-other"
    assert links.history(db, old["id"])[-1]["action"] == "reject"
    chosen_log = links.history(db, result["link"]["id"])[-1]
    assert chosen_log["action"] == "choose"
    assert chosen_log["by"] == "editor"
    assert chosen_log["to"] == "manual"


def test_learning_pairs_only_person_approved(db: sqlite3.Connection, tmp_path: Path) -> None:
    for status in ("proposed", "confirmed", "rejected"):
        row = insert(db, model_id=f"suns-{status}")
        if status != "proposed":
            links.decide(db, row["id"], status, "editor")
    links.choose(db, DRAWING, "suns-manual", "editor")
    assert [(r["model_id"], r["status"]) for r in links.learning_pairs(tmp_path / "app.db")] == [
        ("suns-confirmed", "confirmed"),
        ("suns-manual", "manual"),
    ]


def test_sheet_view_and_used_suns_follow_decisions(db: sqlite3.Connection, tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    sheet = {"linked": ["suns-a"], "suggested": ["suns-b"]}
    assert links.sheet_view(DRAWING, sheet, path) == {
        "linked": [],
        "proposed": ["suns-a"],
        "suggested": ["suns-b"],
        "rejected": [],
    }
    assert links.used_suns(DRAWING, sheet["linked"], path) == ["suns-a"]
    a = insert(db, model_id="suns-a", sheet="linked")
    links.decide(db, a["id"], "rejected", "editor")
    links._CACHE.clear()
    view = links.sheet_view(DRAWING, sheet, path)
    assert view["rejected"] == ["suns-a"]
    assert view["proposed"] == view["linked"] == []
    assert links.used_suns(DRAWING, sheet["linked"], path) == []
    other = insert(db, model_id="suns-confirmed")
    links.decide(db, other["id"], "confirmed", "editor")
    links._CACHE.clear()
    assert links.sheet_view(DRAWING, sheet, path)["linked"] == ["suns-confirmed"]
    assert links.used_suns(DRAWING, sheet["linked"], path) == ["suns-confirmed"]
    links.decide(db, a["id"], "confirmed", "editor")
    links._CACHE.clear()
    view = links.sheet_view(DRAWING, sheet, path)
    assert view["linked"] == ["suns-a", "suns-confirmed"]
    assert view["proposed"] == view["rejected"] == []
    assert set(links.used_suns(DRAWING, sheet["linked"], path)) == {"suns-a", "suns-confirmed"}


def test_links_of_both_sides_excludes_rejected(db: sqlite3.Connection, tmp_path: Path) -> None:
    approved = insert(db)
    links.decide(db, approved["id"], "confirmed", "editor")
    pending = insert(db, model_id="suns-pending")
    rejected = insert(db, model_id="suns-rejected")
    links.decide(db, rejected["id"], "rejected", "editor")
    path = tmp_path / "app.db"
    assert [r["partner"] for r in links.links_of(path, DRAWING)] == [MODEL, "suns-pending"]
    reverse = links.links_of(path, MODEL)
    assert reverse[0]["partner"] == DRAWING
    assert reverse[0]["person"] is True
    assert links.links_of(path, "suns-pending")[0]["id"] == pending["id"]
    assert links.links_of(path, "suns-rejected") == []


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    # Some sandboxes block asyncio's local socket-pair wakeup. Poll only there,
    # so TestClient can still run the real ASGI app without opening a server.
    left, right = socket.socketpair()
    try:
        with left, right:
            left.send(b"wake")
    except PermissionError:
        original_select = selectors.DefaultSelector.select

        def poll(self: Any, timeout: float | None = None) -> Any:
            return original_select(self, 0.01 if timeout is None else min(timeout, 0.01))

        monkeypatch.setattr(selectors.DefaultSelector, "select", poll)
    a = create_app(tmp_path / "data", login_required=True)
    for role in ("admin", "editor", "viewer", "workshop"):
        user = a.state.auth.add_user(role, role.title(), role, f"{role}@example.com", False)
        a.state.auth.set_password(
            a.state.auth.invite(user.id), f"long-link-test-secret-{role[::-1]}-9"
        )
    cover(tmp_path / "data" / "models", DRAWING)
    cover(tmp_path / "data" / "models", MODEL)
    return a


def login(app: Any, role: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"username": role, "password": f"long-link-test-secret-{role[::-1]}-9"},
    )
    assert response.status_code == 200, response.text
    return client


def api_insert(app: Any, **extra: Any) -> dict[str, Any]:
    with links.opened(Path(app.state.store.root) / "app.db") as db:
        return insert(db, **extra)


def test_viewer_reads_but_cannot_change(app: Any, p: Any) -> None:
    row = api_insert(app)
    with login(app, "viewer") as client:
        response = client.get("/api/links")
        assert response.status_code == 200
        assert response.json()["may_edit"] is False
        assert response.json()["links"][0]["id"] == row["id"]
        assert (
            client.post(
                f"/api/links/{row['id']}/decide",
                json={"status": "confirmed", "version": row["version"]},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/links/choose", json={"drawing_id": DRAWING, "model_id": MODEL}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/links/bulk-confirm",
                json={"ids": [row["id"]], "min_score": p["links.bulk_min"]},
            ).status_code
            == 403
        )
        assert client.get(f"/api/links/{row['id']}").json()["status"] == "proposed"


def test_workshop_cannot_read_links(app: Any) -> None:
    with login(app, "workshop") as client:
        assert client.get("/api/links").status_code == 403
        assert client.get("/api/links/of/x").status_code == 403


@pytest.mark.parametrize("role", ["editor", "admin"])
def test_editor_admin_decisions_versions_and_invalid_status(app: Any, role: str) -> None:
    row = api_insert(app)
    with login(app, role) as client:
        url = f"/api/links/{row['id']}/decide"
        response = client.post(url, json={"status": "confirmed", "version": row["version"]})
        assert response.status_code == 200, response.text
        confirmed = response.json()
        assert confirmed["status"] == "confirmed"
        assert confirmed["decided_by"] == role
        assert confirmed["version"] == row["version"] + 1
        assert (
            client.post(url, json={"status": "rejected", "version": row["version"]}).status_code
            == 409
        )
        response = client.post(url, json={"status": "rejected", "version": confirmed["version"]})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "rejected"
        bad = {"status": "manual", "version": confirmed["version"]}
        assert client.post(url, json=bad).status_code == 400
        # the version is required: a page that does not say what it saw cannot decide
        assert client.post(url, json={"status": "confirmed"}).status_code == 422
        detail = client.get(f"/api/links/{row['id']}")
        assert detail.status_code == 200
        assert detail.json()["status"] == "rejected"
        assert [h["action"] for h in detail.json()["history"]] == ["propose", "confirm", "reject"]


def test_bulk_confirm_enforces_floor_and_skip_reasons(app: Any, p: Any) -> None:
    floor = float(p["links.bulk_min"])
    high = api_insert(app, model_id="suns-high", score=min(1.0, floor + 0.05))
    low = api_insert(app, model_id="suns-low", score=floor - 0.01)
    doubtful = api_insert(app, model_id="suns-doubt", score=1.0, doubts=["another family"])
    rejected = api_insert(app, model_id="suns-rejected", score=1.0)
    with links.opened(Path(app.state.store.root) / "app.db") as db:
        rejected = links.decide(db, rejected["id"], "rejected", "editor")
    with login(app, "editor") as client:
        items = [{"id": r["id"], "version": r["version"]} for r in (high, low, doubtful, rejected)]
        response = client.post("/api/links/bulk-confirm", json={"items": items, "min_score": 0.0})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["min_score"] == floor
        assert result["confirmed"] == [high["id"]]
        skipped = {r["id"]: r["why"] for r in result["skipped"]}
        assert set(skipped) == {low["id"], doubtful["id"], rejected["id"]}
        assert "score below" in skipped[low["id"]]
        assert "doubt" in skipped[doubtful["id"]]
        assert "rejected" in skipped[rejected["id"]]
        for row, status in (
            (high, "confirmed"),
            (low, "proposed"),
            (doubtful, "proposed"),
            (rejected, "rejected"),
        ):
            assert client.get(f"/api/links/{row['id']}").json()["status"] == status


def test_nopartner_lists_only_drawings_without_live_links(app: Any) -> None:
    models = Path(app.state.store.models)
    cover(models, "drawing-alone")
    cover(models, "drawing-rejected")
    api_insert(app)
    rejected = api_insert(app, drawing_id="drawing-rejected")
    with links.opened(Path(app.state.store.root) / "app.db") as db:
        links.decide(db, rejected["id"], "rejected", "editor")
    with login(app, "viewer") as client:
        response = client.get("/api/links", params={"status": "nopartner"})
        assert response.status_code == 200, response.text
        assert response.json()["nopartner"] == ["drawing-alone", "drawing-rejected"]
        assert response.json()["total"] == 2
        assert response.json()["links"] == []


@pytest.mark.parametrize("scoring_fails", [False, True])
def test_editor_choose_minimal_covers(
    app: Any, monkeypatch: pytest.MonkeyPatch, scoring_fails: bool
) -> None:
    if scoring_fails:

        def unavailable(*args: Any, **kwargs: Any) -> None:
            raise ValueError("synthetic cover cannot be scored")

        monkeypatch.setattr(ls, "facts", unavailable)
    with login(app, "editor") as client:
        response = client.post("/api/links/choose", json={"drawing_id": DRAWING, "model_id": MODEL})
        assert response.status_code == 200, response.text
        row = response.json()["link"]
        assert row["status"] == "manual"
        assert row["drawing_id"] == DRAWING
        assert row["model_id"] == MODEL
        assert row["decided_by"] == "editor"
        if scoring_fails:
            assert row["score"] is None
        response = client.get(f"/api/links/of/{MODEL}")
        assert response.status_code == 200
        assert response.json()["links"][0]["partner"] == DRAWING


def test_links_search_minimal_covers(app: Any) -> None:
    with login(app, "viewer") as client:
        response = client.get("/api/links-search", params={"q": "evora"})
        assert response.status_code == 200
        assert response.json()["covers"] == [{"id": MODEL, "picture": False}]
        response = client.get("/api/links-search", params={"q": "d2", "side": "drawing"})
        assert response.status_code == 200
        assert response.json()["covers"] == [{"id": DRAWING, "picture": False}]


@pytest.mark.parametrize("existing_db", [False, True])
def test_products_card_follows_person_decisions(tmp_path: Path, existing_db: bool) -> None:
    data = tmp_path / "data"
    d = cover(data / "models", DRAWING)
    path = data / "app.db"
    if existing_db:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
        conn.close()
    write_json(
        d / "products.json",
        {
            "labels": ["Evora normal D- Bed"],
            "rows": [{"Code": "D2", "Product": "Evora normal D- Bed", "_internal": "hidden"}],
            "suns": {"linked": ["suns-a"], "suggested": ["suns-b"]},
        },
    )
    card = products_sheet.products_card(d)
    assert card["suns"]["proposed"] == ["suns-a"]
    assert card["suns"]["linked"] == []
    assert card["suns"]["suggested"] == ["suns-b"]
    assert card["columns"] == ["Code", "Product"]
    assert card["rows"] == [["D2", "Evora normal D- Bed"]]
    assert path.exists() is existing_db
    with links.opened(path) as db:
        row = insert(db, model_id="suns-a", sheet="linked")
        links.decide(db, row["id"], "rejected", "editor")
    links._CACHE.clear()
    suns = products_sheet.products_card(d)["suns"]
    assert suns["rejected"] == ["suns-a"]
    assert "suns-a" not in suns["proposed"] + suns["linked"]
    with links.opened(path) as db:
        links.decide(db, row["id"], "confirmed", "editor")
    links._CACHE.clear()
    suns = products_sheet.products_card(d)["suns"]
    assert suns["linked"] == ["suns-a"]
    assert suns["proposed"] == suns["rejected"] == []


def test_product_labels_drops_rejected_drawing(tmp_path: Path) -> None:
    data = tmp_path / "data"
    d = cover(data / "models", MODEL)
    doc = {"linked": [{"id": DRAWING, "code": "D2", "product": "Evora normal D- Bed"}]}
    write_json(d / "drawings.json", doc)
    assert products_sheet.product_labels(d) == ["D2 · Evora normal D- Bed"]
    with links.opened(data / "app.db") as db:
        row = insert(db, sheet="linked")
        links.decide(db, row["id"], "rejected", "editor")
    links._CACHE.clear()
    assert products_sheet.product_labels(d) == []
    assert products_sheet.products_card(d)["drawings"]["linked"] == []
    assert json.loads((d / "drawings.json").read_text()) == doc


def test_price_matcher_uses_decisions_and_filters_missing_models(tmp_path: Path) -> None:
    data = tmp_path / "data"
    models = data / "models"
    d = cover(models, DRAWING)
    for mid in ("suns-a", "suns-b", "suns-manual"):
        cover(models, mid)
    write_json(
        d / "products.json",
        {
            "labels": ["Cover 105", "Evora normal D- Bed"],
            "suns": {"linked": ["suns-a", "suns-missing"]},
        },
    )
    matcher = prices_import.Matcher(models, data)
    assert matcher.linked_suns(DRAWING) == ["suns-a"]
    with links.opened(data / "app.db") as db:
        row = insert(db, model_id="suns-a")
        links.decide(db, row["id"], "rejected", "editor")
        row = insert(db, model_id="suns-b")
        links.decide(db, row["id"], "confirmed", "editor")
        links.choose(db, DRAWING, "suns-manual", "editor")
        links.choose(db, DRAWING, "suns-unavailable", "editor")
    links._CACHE.clear()
    assert set(matcher.linked_suns(DRAWING)) == {"suns-b", "suns-manual"}
    matcher.products[DRAWING]["labels"].append("Vento other product")
    assert matcher.linked_suns(DRAWING) == []


@pytest.fixture
def script_models(tmp_path: Path) -> Path:
    models = tmp_path / "models"
    for mid in ("drawing-x", "suns-y"):
        d = cover(models, mid)
        write_json(
            d / "model.json",
            {"bbox_mm": [[0, 0, 0], [2200, 900, 800]], "size_mm": [2200, 900, 800]},
        )
        write_json(d / "hull.json", {"bbox_mm": [[0, 0, 0], [2200, 900, 800]]})
    write_json(
        models / "drawing-x" / "products.json",
        {"labels": ["Y sunlounger"], "suns": {"linked": ["suns-y"]}},
    )
    return models


def run_script(monkeypatch: pytest.MonkeyPatch, models: Path, db: Path, mode: str) -> None:
    spec = importlib.util.spec_from_file_location(
        "test_link_proposals", REPO / "scripts/link_proposals.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        sys, "argv", [str(spec.origin), "--models", str(models), "--db", str(db), mode]
    )
    module.main()


@pytest.mark.parametrize("existing_db", [False, True])
def test_script_dry_run_never_writes_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script_models: Path,
    capsys: pytest.CaptureFixture[str],
    existing_db: bool,
) -> None:
    path = tmp_path / "app.db"
    before = None
    if existing_db:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE unrelated (value TEXT)")
        conn.execute("INSERT INTO unrelated VALUES ('keep me')")
        conn.commit()
        conn.close()
        before = path.read_bytes()
    files = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    run_script(monkeypatch, script_models, path, "--dry-run")
    output = capsys.readouterr().out
    assert "dry run, would be:" in output
    assert "new 1" in output
    assert path.exists() is existing_db
    if existing_db:
        assert path.read_bytes() == before
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            assert (
                conn.execute("SELECT name FROM sqlite_master WHERE name='model_links'").fetchall()
                == []
            )
            assert conn.execute("SELECT value FROM unrelated").fetchall() == [("keep me",)]
        finally:
            conn.close()
    assert {
        p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
    } == files


def test_script_apply_preserves_confirmed_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script_models: Path,
    capsys: pytest.CaptureFixture[str],
    p: Any,
) -> None:
    path = tmp_path / "app.db"
    run_script(monkeypatch, script_models, path, "--apply")
    assert "new 1" in capsys.readouterr().out
    with links.opened(path) as db:
        rows = db.execute("SELECT * FROM model_links").fetchall()
        assert len(rows) == 1
        row = links.row_out(rows[0])
        assert (row["drawing_id"], row["model_id"], row["status"]) == (
            "drawing-x",
            "suns-y",
            "proposed",
        )
        links.decide(db, row["id"], "confirmed", "editor", version=row["version"], note="reviewed")
        before = dict(links.get(db, row["id"]))
        log_before = links.history(db, row["id"])
    # Make the next proposal materially different, while retaining the sheet pair.
    write_json(script_models / "suns-y" / "hull.json", {"bbox_mm": [[0, 0, 0], [4500, 3000, 1600]]})
    rescored = ls.score(
        ls.facts(script_models / "drawing-x", p), ls.facts(script_models / "suns-y", p), p
    )
    assert rescored["score"] != before["score"]
    assert rescored["doubts"]
    database_bytes = path.read_bytes()
    run_script(monkeypatch, script_models, path, "--dry-run")
    assert "person 1" in capsys.readouterr().out
    assert path.read_bytes() == database_bytes
    run_script(monkeypatch, script_models, path, "--apply")
    assert "person 1" in capsys.readouterr().out
    with links.opened(path) as db:
        assert dict(links.get(db, row["id"])) == before
        assert links.history(db, row["id"]) == log_before


# ---- Codex's adversarial review: stale pages and withdrawn proposals ---------------------------


def test_choose_refuses_a_stale_replaced_link(db: sqlite3.Connection) -> None:
    old = insert(db)
    seen = old["version"]
    links.decide(db, old["id"], "confirmed", "rens", version=seen)  # someone confirmed meanwhile
    with pytest.raises(HTTPException) as err:
        links.choose(db, DRAWING, "suns-other", "editor", replaces=old["id"], replaces_version=seen)
    assert err.value.status_code == 409
    assert links.get(db, old["id"])["status"] == "confirmed"
    assert links._pair(db, DRAWING, "suns-other") is None
    with pytest.raises(HTTPException) as err:
        links.choose(db, DRAWING, "suns-other", "editor", replaces=old["id"])
    assert err.value.status_code == 400  # the version of the replaced link is required


def test_choose_never_revives_a_rejected_target_silently(db: sqlite3.Connection) -> None:
    target = insert(db, model_id="suns-other")
    links.decide(db, target["id"], "rejected", "rens", version=target["version"])
    with pytest.raises(HTTPException) as err:
        links.choose(db, DRAWING, "suns-other", "editor")
    assert err.value.status_code == 409
    assert links.get(db, target["id"])["status"] == "rejected"
    out = links.choose(db, DRAWING, "suns-other", "editor", override=True)
    assert out["link"]["status"] == "manual"


def test_choose_keeps_a_confirmed_target_as_it_is(db: sqlite3.Connection) -> None:
    target = insert(db, model_id="suns-other")
    confirmed = links.decide(db, target["id"], "confirmed", "rens", version=target["version"])
    out = links.choose(db, DRAWING, "suns-other", "editor", note="mine")
    assert out["link"]["status"] == "confirmed"
    assert out["link"]["version"] == confirmed["version"]
    assert links.get(db, target["id"])["decided_by"] == "rens"


def test_bulk_skips_withdrawn_and_changed_proposals(app: Any, p: Any) -> None:
    score = min(1.0, float(p["links.bulk_min"]) + 0.05)
    withdrawn = api_insert(app, model_id="suns-old", score=score)
    changed = api_insert(app, model_id="suns-changed", score=score)
    with links.opened(Path(app.state.store.root) / "app.db") as db:
        links.mark_stale(db, {(DRAWING, "suns-changed")})
    items = [
        {"id": withdrawn["id"], "version": withdrawn["version"] + 1},  # as the page now shows it
        {"id": changed["id"], "version": changed["version"] - 1},  # an older page
    ]
    with login(app, "editor") as client:
        response = client.post("/api/links/bulk-confirm", json={"min_score": 0.0, "items": items})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["confirmed"] == []
        why = {r["id"]: r["why"] for r in result["skipped"]}
        assert "old proposal" in why[withdrawn["id"]]
        assert "changed meanwhile" in why[changed["id"]]
    pairs = links.learning_pairs(Path(app.state.store.root) / "app.db")
    assert not [r for r in pairs if r["model_id"] in ("suns-old", "suns-changed")]
