"""The cutting preview keeps DXF downloads gated and follows exact Desk approvals."""

import json
from pathlib import Path
from typing import Any

import ezdxf
import pytest
from coverapi import cutview, desk
from coverapi.main import create_app
from coverapi.security import workshop_may
from fastapi.testclient import TestClient
from tests.test_cutview import model

USERS = (
    ("admin", "admin"),
    ("designer", "editor"),
    ("rens", "viewer"),
    ("wout", "editor"),
    ("reader", "viewer"),
    ("bench", "workshop"),
    ("wouter", "workshop"),
)
BASE = "/api/models/test-chair/cutview"
ROUTES = ("", ".svg", "/diff?a=1&b=current")


def _secret(user: str) -> str:
    return f"a-long-secret-for-{user[::-1]}-9"


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    """A private data root with a real export, a kept revision and invited users."""
    root = tmp_path / "data"
    a = create_app(root, login_required=True)
    for name, role in USERS:
        user = a.state.auth.add_user(name, name.title(), role, f"{name}@example.com", False)
        a.state.auth.set_password(a.state.auth.invite(user.id), _secret(name))
    d = root / "models" / "test-chair"
    path, _ = model(d)
    (d / "cover.json").write_text(
        json.dumps({"format_version": 1, "model_id": d.name, "status": "draft"})
    )
    kept = d / "revisions" / "001"
    kept.mkdir(parents=True)
    (kept / "cut.dxf").write_bytes(path.read_bytes())
    (kept.parent / "index.json").write_text(json.dumps([{"number": 1}]))
    return a


def _folder(tmp_path: Path) -> Path:
    return tmp_path / "data" / "models" / "test-chair"


def _login(app: Any, user: str) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"username": user, "password": _secret(user)})
    assert response.status_code == 200, response.text
    return client


def _change_cut(d: Path) -> None:
    """Add a valid CUT piece so both the fingerprint and the diff change."""
    path = d / "cut.dxf"
    drawing = ezdxf.readfile(path)
    drawing.modelspace().add_circle((-500, -500), 100, dxfattribs={"layer": "CUT"})
    drawing.saveas(path)


@pytest.mark.parametrize(
    ("user", "status"),
    [
        ("admin", 200),
        ("designer", 200),
        ("rens", 200),
        ("reader", 403),
        ("bench", 403),
        ("wouter", 403),
    ],
)
@pytest.mark.parametrize("suffix", ROUTES)
def test_unapproved_rights(app: Any, user: str, status: int, suffix: str) -> None:
    """A name grants preview access to a viewer, but never to the workshop role."""
    response = _login(app, user).get(BASE + suffix)
    assert response.status_code == status, response.text


def test_preview_leaves_the_dxf_gate_closed(app: Any) -> None:
    client = _login(app, "designer")
    assert client.get("/api/models/test-chair/files/cut.dxf").status_code == 403
    for suffix, content_type in (
        ("", "application/json"),
        (".svg", "image/svg+xml"),
        ("/diff?a=1&b=current", "application/json"),
    ):
        response = client.get(BASE + suffix)
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].split(";")[0] == content_type
        assert not {"SECTION", "ENTITIES", "AcDbEntity", "EOF"} & {
            line.strip() for line in response.text.splitlines()
        }
        assert "AcDbEntity" not in response.text
        assert "<script" not in response.text.lower()
    svg = client.get(BASE + ".svg")
    disposition = svg.headers["content-disposition"]
    assert disposition.startswith("inline;") and disposition.endswith('.svg"')
    meta = client.get(BASE).json()
    assert meta["pieces"] and not meta["approved"] and not meta["downloadable"]
    assert "_geometry" not in meta
    for piece in meta["pieces"]:
        assert {"name", "size_mm", "box", "edges"} <= piece.keys()
        assert "outline" not in piece
        assert len(piece["size_mm"]) == 2 and len(piece["box"]) == 4


def test_approval_and_changed_bytes_control_the_watermark(app: Any, tmp_path: Path) -> None:
    client, workshop = _login(app, "designer"), _login(app, "bench")
    svg = client.get(BASE + ".svg")
    assert svg.headers["x-cutview-watermark"] == "1"
    assert "PREVIEW – NOT FOR CUTTING" in svg.text and 'data-watermark="1"' in svg.text
    meta = client.get(BASE).json()
    assert meta["watermark"] is True
    assert meta["watermark_text"] == "PREVIEW – NOT FOR CUTTING"
    approved = _login(app, "wout").post("/api/desk/test-chair", json={"action": "approve"})
    assert approved.status_code == 200, approved.text
    svg = client.get(BASE + ".svg")
    assert svg.headers["x-cutview-watermark"] == "0"
    assert "PREVIEW – NOT FOR CUTTING" not in svg.text
    meta = client.get(BASE).json()
    assert meta["approved"] is True and meta["downloadable"] is True
    assert meta["watermark"] is False and meta["watermark_text"] is None
    for suffix in ROUTES:
        assert workshop.get(BASE + suffix).status_code == 200
    _change_cut(_folder(tmp_path))
    svg = client.get(BASE + ".svg")
    assert svg.headers["x-cutview-watermark"] == "1"
    assert "PREVIEW – NOT FOR CUTTING" in svg.text
    assert client.get(BASE).json()["approved"] is False
    for suffix in ROUTES:
        assert workshop.get(BASE + suffix).status_code == 403


def test_revisions_and_piece_diff(app: Any, tmp_path: Path) -> None:
    client, workshop = _login(app, "designer"), _login(app, "bench")
    d = _folder(tmp_path)
    for suffix in ("", ".svg"):
        assert client.get(BASE + suffix + "?revision=1").status_code == 200
        assert client.get(BASE + suffix + "?revision=99").status_code == 404
        assert workshop.get(BASE + suffix + "?revision=1").status_code == 403
    fp = cutview.cv.fingerprint((d / "revisions/001/cut.dxf").read_bytes())
    st = desk.state(d)
    st["approved_fingerprints"] = [fp]
    (d / "desk.json").write_text(json.dumps(st))
    meta = workshop.get(BASE + "?revision=1")
    assert meta.status_code == 200, meta.text
    assert meta.json()["revision"] == 1 and meta.json()["approved"] is True
    assert workshop.get(BASE + ".svg?revision=1").headers["x-cutview-watermark"] == "0"
    assert workshop.get(BASE).status_code == 403
    assert workshop.get(BASE + "/diff?a=1&b=current").status_code == 403
    assert workshop.get(BASE + "/diff?a=1&b=1").status_code == 200
    _change_cut(d)
    response = client.get(BASE + "/diff?a=1&b=current")
    assert response.status_code == 200, response.text
    diff = response.json()
    assert diff["from"] == 1 and diff["to"] is None and diff["same_file"] is False
    assert diff["counts"]["added"] == 1
    assert {p["status"] for p in diff["pieces"]} == {"same", "added"}
    assert client.get(BASE + "/diff?a=1&b=bogus").status_code == 400
    assert client.get(BASE + "/diff?a=99&b=current").status_code == 404


@pytest.mark.parametrize("suffix", ROUTES)
def test_missing_cut_and_unknown_model(app: Any, tmp_path: Path, suffix: str) -> None:
    client = _login(app, "designer")
    (_folder(tmp_path) / "cut.dxf").unlink()
    assert client.get(BASE + suffix).status_code == 404
    assert client.get(BASE.replace("test-chair", "unknown-chair") + suffix).status_code == 404


def test_cache_reuses_render_and_tracks_bytes(
    app: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = cutview.cv.render
    calls = []

    def render(data: bytes, *args: Any) -> Any:
        calls.append(data)
        return original(data, *args)

    monkeypatch.setattr(cutview.cv, "render", render)
    client = _login(app, "designer")
    d = _folder(tmp_path)
    before = {p.relative_to(d) for p in d.rglob("*")}
    first = client.get(BASE + ".svg")
    assert first.status_code == 200 and len(calls) == 1
    assert client.get(BASE + ".svg").text == first.text
    assert client.get(BASE).status_code == 200 and len(calls) == 1
    _change_cut(d)
    assert client.get(BASE + ".svg").status_code == 200 and len(calls) == 2
    assert calls[0] != calls[1]
    cache = tmp_path / "data" / "cutview-cache"
    assert len(list(cache.glob("*.svg"))) == len(list(cache.glob("*.json"))) == 2
    assert {p.relative_to(d) for p in d.rglob("*")} == before


@pytest.mark.parametrize("suffix", ROUTES)
def test_too_large(app: Any, monkeypatch: pytest.MonkeyPatch, suffix: str) -> None:
    original = cutview._params()
    monkeypatch.setattr(
        cutview,
        "_params",
        lambda: {
            **original,
            "desk.preview_max_mb": 0.000001,
        },
    )
    assert _login(app, "designer").get(BASE + suffix).status_code == 413


def test_workshop_can_preview_when_the_gate_is_off(
    app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = cutview._params()
    monkeypatch.setattr(
        cutview,
        "_params",
        lambda: {
            **original,
            "desk.require_approval_for_dxf": False,
        },
    )
    client = _login(app, "wouter")
    for suffix in ROUTES:
        response = client.get(BASE + suffix)
        assert response.status_code == 200, response.text
    assert client.get(BASE).json()["downloadable"] is True
    assert client.get(BASE + ".svg").headers["x-cutview-watermark"] == "1"


def test_workshop_allow_list_names_only_preview_routes() -> None:
    for suffix in ("", ".svg", "/diff"):
        assert workshop_may("GET", "/api/models/x/cutview" + suffix)
    assert not workshop_may("GET", "/api/models/x/cutview.dxf")
