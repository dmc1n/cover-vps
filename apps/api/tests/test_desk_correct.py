"""Corrections at the Desk that change the cover itself, and rules learned from them (ADR-082)."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_desk import _model, login


class FakeJobs:
    def __init__(self) -> None:
        self.specs: list[Any] = []

    def submit(self, spec: Any) -> dict[str, Any]:
        self.specs.append(spec)
        return {"id": f"job-{len(self.specs)}"}


@pytest.fixture()
def desk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from coverapi.main import create_app

    root = tmp_path / "data"
    monkeypatch.setenv("COVER_DATA_DIR", str(root))
    a = create_app(root, login_required=True)
    auth = a.state.auth
    for user, name, role in (("rick", "Rick", "admin"), ("rens", "Rens", "editor"),
                             ("vera", "Vera", "editor")):  # fmt: skip
        u = auth.add_user(user, name, role, f"{user}@example.com", False)
        auth.set_password(auth.invite(u.id), f"a-long-secret-for-{user[::-1]}-9")
    for i in range(1, 7):
        _model(root, f"drawing-r{i}", "agreed: different", 40)
    a.state.jobs = FakeJobs()
    return a


def test_a_vent_correction_is_the_covers_setting_and_a_test_case(desk: Any) -> None:
    rens, vera = login(desk, "rens"), login(desk, "vera")
    body = {"kind": "vents", "count": 6, "above_hem_cm": 30}
    assert vera.post("/api/desk/drawing-r1/correct", json=body).status_code == 403
    r = rens.post("/api/desk/drawing-r1/correct", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["steps"] == ["export"] and out["job"] == {"id": "job-1"}
    root = desk.state.store.root
    cover = json.loads((root / "models" / "drawing-r1" / "cover.json").read_text())
    assert cover["parameters"]["features"] == {"vents_total": 6, "vent_above_hem_mm": 300.0}
    case = json.loads((root / "learning" / "cases" / out["case"]).read_text())
    assert case["expect"]["vents"] == 6 and case["check"] == "auto"
    view = rens.get("/api/desk/drawing-r1/correct").json()
    assert view["settings"]["features.vents_total"] == 6 and view["feedback"][-1]["count"] == 6
    hist = rens.get("/api/desk/drawing-r1").json()["desk"]["history"]
    assert hist[-1]["action"] == "correct vents"


def test_a_correction_after_approval_asks_for_a_new_approval(desk: Any) -> None:
    rens = login(desk, "rens")
    rens.post("/api/desk/drawing-r2", json={"action": "approve"})
    rens.post("/api/desk/drawing-r2/correct", json={"kind": "vents", "count": 4})
    assert rens.get("/api/desk/drawing-r2").json()["status"] == "ai-checked"


def test_sizes_and_shapes_are_kept_for_the_reader_and_the_developer(desk: Any) -> None:
    rens = login(desk, "rens")
    size = {"kind": "size", "what": "length", "read_cm": 125.8, "correct_cm": 152.4}
    r = rens.post("/api/desk/drawing-r3/correct", json=size)
    assert r.status_code == 200 and r.json()["steps"] == []
    root = desk.state.store.root
    fix = json.loads((root / "models" / "drawing-r3" / "drawing_corrections.json").read_text())
    assert fix["sizes"][0]["correct_cm"] == 152.4
    assert rens.post("/api/desk/drawing-r3/correct", json={"kind": "shape"}).status_code == 400
    r = rens.post("/api/desk/drawing-r3/correct", json={"kind": "shape",
                                                         "chips": ["round front"]})  # fmt: skip
    assert r.json()["expect"] == {}
    rules = rens.get("/api/desk-rules").json()
    assert rules["shape_problems"]["drawing-r"]["round front"] == 1


def test_seams_of_a_cover_drawn_in_parts_can_be_removed_not_of_a_tensioned_one(desk: Any) -> None:
    rens = login(desk, "rens")
    r = rens.post("/api/desk/drawing-r4/correct",
                  json={"kind": "seam", "op": "remove", "seam": "top/skirt"})  # fmt: skip
    assert r.status_code == 400 and "follow the furniture" in r.json()["detail"]
    r = rens.post("/api/desk/drawing-r4/correct", json={"kind": "seam", "op": "skirt", "at_cm": 25})
    assert r.status_code == 200 and r.json()["steps"] == ["cut", "flatten", "export"]


def test_the_same_correction_on_five_covers_becomes_a_rule_a_person_accepts(desk: Any) -> None:
    rens, vera = login(desk, "rens"), login(desk, "vera")
    for i in range(1, 6):
        rens.post(f"/api/desk/drawing-r{i}/correct", json={"kind": "vents", "above_hem_cm": 30})
    (prop,) = rens.get("/api/desk-rules").json()["proposals"]
    assert prop["group"] == "drawing-r" and prop["key"] == "features.vent_above_hem_mm"
    rule = {"group": "drawing-r", "key": prop["key"], "value": prop["value"]}
    assert vera.post("/api/desk-rules", json=rule).status_code == 403
    out = rens.post("/api/desk-rules", json=rule).json()
    assert len(out["covers"]) == 6 and len(out["jobs"]) == 6  # the sixth gets it too
    after = rens.get("/api/desk-rules").json()
    assert after["proposals"] == [] and after["rules"]["drawing-r"]["features"] == {
        "vent_above_hem_mm": 300.0}  # fmt: skip
    from coverengine.params import resolve_model

    six = desk.state.store.root / "models" / "drawing-r6"
    assert resolve_model(six)["features.vent_above_hem_mm"] == 300.0
    assert rens.post("/api/desk-rules", json={**rule, "key": "nope.nothing"}).status_code == 400


def test_the_correct_view_lists_the_seams_and_pieces(desk: Any) -> None:
    c: TestClient = login(desk, "rick")
    view = c.get("/api/desk/drawing-r5/correct").json()
    assert view["seams"] == [] and view["pieces"] == [] and view["drawn"] is False
    assert "round front" in view["shapes"]
