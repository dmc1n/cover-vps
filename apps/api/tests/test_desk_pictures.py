"""Pictures at the Desk (ADR-096): an approver attaches marked pictures to a reject or comment."""

import io
import json
import random
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from test_desk import app, login  # noqa: F401 - the fixture

PNG_SIZE = (64, 48)


def _jpeg_with_exif() -> bytes:
    img = Image.new("RGB", PNG_SIZE, (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    exif[0x0131] = "editor 1.0"  # Software
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", PNG_SIZE, (0, 0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


def _upload(client: Any, model: str, *datas: bytes, kind: str = "image/png") -> Any:
    files = [("files", (f"shot-{i}.png", data, kind)) for i, data in enumerate(datas)]
    return client.post(f"/api/desk/{model}/pictures", files=files)


def test_only_approvers_upload_pictures(app: Any) -> None:  # noqa: F811
    vera, rens, rick = login(app, "vera"), login(app, "rens"), login(app, "rick")
    assert _upload(vera, "drawing-a", _png()).status_code == 403
    r = _upload(rens, "drawing-a", _png())
    assert r.status_code == 200, r.text
    assert len(r.json()["pictures"]) == 1
    assert _upload(rick, "drawing-a", _png(), _jpeg_with_exif()).status_code == 200  # admin
    assert _upload(rens, "no-such-model", _png()).status_code == 404


def test_a_picture_is_kept_as_png_without_metadata(app: Any, tmp_path: Path) -> None:  # noqa: F811
    rens = login(app, "rens")
    name = _upload(rens, "drawing-a", _jpeg_with_exif(), kind="image/jpeg").json()["pictures"][0]
    path = tmp_path / "data" / "models" / "drawing-a" / "desk" / name
    assert name.endswith(".png") and path.is_file()
    with Image.open(path) as kept:
        assert kept.format == "PNG" and kept.size == PNG_SIZE
        assert not kept.getexif() and "exif" not in kept.info
    assert b"SecretCam" not in path.read_bytes()
    # served through the model's file route, to logged-in people only
    r = login(app, "vera").get(f"/api/models/drawing-a/files/desk/{name}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    from fastapi.testclient import TestClient

    assert TestClient(app).get(f"/api/models/drawing-a/files/desk/{name}").status_code == 401


def test_bad_files_are_refused(app: Any) -> None:  # noqa: F811
    rens = login(app, "rens")
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
    assert _upload(rens, "drawing-a", svg).status_code == 400
    assert _upload(rens, "drawing-a", b"not a picture at all").status_code == 400
    buf = io.BytesIO()
    Image.new("RGB", PNG_SIZE).save(buf, "GIF")
    assert _upload(rens, "drawing-a", buf.getvalue(), kind="image/gif").status_code == 400
    assert _upload(rens, "drawing-a", _png()[:40]).status_code == 400  # cut short
    assert _upload(rens, "drawing-a", *([_png()] * 9)).status_code == 400  # more than 8


def test_a_too_big_picture_is_refused(app: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    from coverapi import desk

    monkeypatch.setattr(desk, "MB", 100)  # 15 "MB" is now 1500 bytes
    rens = login(app, "rens")
    noise = Image.frombytes("RGB", (60, 60), random.Random(1).randbytes(60 * 60 * 3))
    buf = io.BytesIO()
    noise.save(buf, "PNG")
    assert len(buf.getvalue()) > 1500
    r = _upload(rens, "drawing-a", buf.getvalue())
    assert r.status_code == 413 and "at most" in r.json()["detail"]


def test_no_path_leads_out_of_the_pictures(app: Any, tmp_path: Path) -> None:  # noqa: F811
    rens = login(app, "rens")
    # (a plain "../" is folded away by the client itself; these reach the route as written)
    for name in ("..%2Fcover.json", "x%2F..%2F..%2Fcover.json", "cover.json", "%2Fetc%2Fpasswd"):
        assert rens.get(f"/api/models/drawing-a/files/desk/{name}").status_code == 404
    bad = {"action": "reject", "reasons": ["shape"], "pictures": ["../cover.json"]}
    assert rens.post("/api/desk/drawing-a", json=bad).status_code == 400
    # a picture of another model is not this model's
    other = _upload(rens, "drawing-b", _png()).json()["pictures"][0]
    if not (tmp_path / "data" / "models" / "drawing-a" / "desk" / other).exists():
        bad["pictures"] = [other]
        assert rens.post("/api/desk/drawing-a", json=bad).status_code == 400


def test_the_history_links_the_pictures(app: Any, tmp_path: Path) -> None:  # noqa: F811
    rens = login(app, "rens")
    names = _upload(rens, "drawing-a", _png(), _png()).json()["pictures"]
    assert len(set(names)) == 2
    body = {"action": "reject", "reasons": ["shape"], "text": "see the arrow", "pictures": names}
    r = rens.post("/api/desk/drawing-a", json=body)
    assert r.status_code == 200, r.text
    card = rens.get("/api/desk/drawing-a").json()
    assert card["desk"]["history"][-1]["pictures"] == names
    raw = json.loads((tmp_path / "data" / "models" / "drawing-a" / "desk.json").read_text())
    assert raw["history"][-1]["pictures"] == names
    rows = (tmp_path / "data" / "learning" / "desk.jsonl").read_text().splitlines()
    row = json.loads(rows[-1])
    assert row["picture_paths"] == [f"models/drawing-a/desk/{n}" for n in names]
    # a comment with only a picture; not with nothing; approve takes none
    one = _upload(rens, "drawing-a", _png()).json()["pictures"]
    assert rens.post("/api/desk/drawing-a", json={"action": "note"}).status_code == 400
    r = rens.post("/api/desk/drawing-a", json={"action": "note", "pictures": one})
    assert r.status_code == 200 and r.json()["status"] == "rejected"  # a comment changes nothing
    assert r.json()["history"][-1]["pictures"] == one
    approve = {"action": "approve", "pictures": one}
    assert rens.post("/api/desk/drawing-a", json=approve).status_code == 400
    # undo takes the comment back, the reject stays
    assert rens.post("/api/desk/drawing-a", json={"action": "undo"}).json()["status"] == "rejected"


def test_a_correction_carries_its_pictures_into_the_test_case(
    app: Any,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path / "data"))
    rens = login(app, "rens")
    names = _upload(rens, "drawing-c", _png()).json()["pictures"]
    body = {"kind": "shape", "chips": ["round front"], "text": "see picture", "pictures": names}
    r = rens.post("/api/desk/drawing-c/correct", json=body)
    assert r.status_code == 200, r.text
    case = json.loads((tmp_path / "data" / "learning" / "cases" / r.json()["case"]).read_text())
    assert case["feedback"]["picture_paths"] == [f"models/drawing-c/desk/{names[0]}"]
    hist = rens.get("/api/desk/drawing-c").json()["desk"]["history"]
    assert hist[-1]["pictures"] == names
