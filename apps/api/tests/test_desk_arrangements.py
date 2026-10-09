"""Arrangements at the Desk (ADR-115): sent by their maker, approved by Rens or Wout, the DXF
only once approved, and an approved arrangement never changes silently."""

import json
from pathlib import Path
from typing import Any

import pytest
from coverapi import desk
from coverapi import questions as Q
from coverapi.arrangements import changes
from coverapi.main import create_app
from fastapi.testclient import TestClient

USERS = (
    ("rick", "Rick", "admin"),
    ("rens", "Rens de Vries", "editor"),
    ("wouter", "Wouter Bekkers", "editor"),
    ("vera", "Vera", "editor"),  # builds arrangements, does not approve
    ("vic", "Vic", "viewer"),
)
RECT_A = [[-1700.0, -1000.0], [-400.0, -1000.0], [-400.0, 1000.0], [-1700.0, 1000.0]]
RECT_B = [[-400.0, -500.0], [1700.0, -500.0], [1700.0, 500.0], [-400.0, 500.0]]


def _secret(user: str) -> str:
    return f"a-long-secret-for-{user[::-1]}-9"


def _arrangement(root: Path, name: str, title: str, built: bool = True) -> Path:
    models = root / "models"
    for m in ("suns-chaise", "suns-sofa"):
        (models / m).mkdir(parents=True, exist_ok=True)
        (models / m / "cover.json").write_text(json.dumps({"notes": f"x: SUNS-{m}"}))
    d = models / name
    d.mkdir(parents=True)
    members = [
        {"model_id": "suns-chaise", "x_mm": -1050.0, "y_mm": 0.0, "rot_deg": 0.0,
         "mirror": False, "version": {"model_glb": None, "size_mm": [1300, 2000, 850]},
         "plan_mm": RECT_A},
        {"model_id": "suns-sofa", "x_mm": 650.0, "y_mm": 0.0, "rot_deg": 0.0, "mirror": False,
         "version": {"model_glb": None, "size_mm": [2100, 1000, 850]}, "plan_mm": RECT_B},
    ]  # fmt: skip
    doc = {"format_version": 1, "id": name, "name": title, "gap_mm": 0.0,
           "footprint": "follow", "members": members, "size_mm": [3400, 2000, 850]}  # fmt: skip
    (d / "arrangement.json").write_text(json.dumps(doc))
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "status": "draft",
                                              "tags": ["arrangement"]}))  # fmt: skip
    if built:
        (d / "finished.json").write_text(json.dumps({"pieces": [
            {"name": "top", "quantity": 1, "size_mm": [1400, 900]},
            {"name": "vent-hood", "quantity": 4, "size_mm": [280, 315]}]}))  # fmt: skip
        (d / "cut.dxf").write_text("0\nEOF\n")
    return d


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    root = tmp_path / "data"
    a = create_app(root, login_required=True)
    auth = a.state.auth
    for user, name, role in USERS:
        u = auth.add_user(user, name, role, f"{user}@example.com", False)
        auth.set_password(auth.invite(u.id), _secret(user))
    _arrangement(root, "arr-portofino", "Portofino chaise + 2-seater")
    _arrangement(root, "arr-unbuilt", "Not built yet", built=False)
    d = root / "models" / "drawing-c1"
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "status": "draft"}))
    return a


def login(app: Any, user: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user, "password": _secret(user)})
    assert r.status_code == 200, r.text
    return c


def test_the_queue_names_arrangements_and_the_card_shows_the_plan(app: Any) -> None:
    vic = login(app, "vic")
    every = vic.get("/api/desk").json()["items"]
    arr = next(i for i in every if i["id"] == "arr-portofino")
    assert arr["arrangement"] is True and arr["code"] == "Portofino chaise + 2-seater"
    assert arr["status"] == "new" and arr["sent"] is None
    assert next(i for i in every if i["id"] == "drawing-c1")["arrangement"] is False
    only = vic.get("/api/desk?scope=arrangements").json()["items"]
    assert sorted(i["id"] for i in only) == ["arr-portofino", "arr-unbuilt"]
    card = vic.get("/api/desk/arr-portofino").json()
    a = card["arrangement_info"]
    assert a["name"] == "Portofino chaise + 2-seater"
    assert [m["model_id"] for m in a["members"]] == ["suns-chaise", "suns-sofa"]
    assert a["members"][0]["code"] == "SUNS suns chaise" and a["members"][0]["exists"]
    plan = a["plan"]
    assert plan["footprint"] == "follow" and len(plan["rects_mm"]) == 2
    # follow: an L, so more corners than a rectangle, and wider than the pieces by the clearance
    assert len(plan["outline_mm"]) > 5 and plan["size_mm"][0] > 3400
    assert card["dxf_ok"] is False  # gated, though gate_scope is "drawings"
    assert vic.get("/api/desk/drawing-c1").json()["arrangement_info"] is None


def test_send_to_the_desk(app: Any, tmp_path: Path) -> None:
    vic, vera = login(app, "vic"), login(app, "vera")
    assert vic.post("/api/arrangements/arr-portofino/send").status_code == 403  # viewer
    assert vera.post("/api/arrangements/arr-unbuilt/send").status_code == 409  # not built
    assert vera.post("/api/arrangements/drawing-c1/send").status_code == 400
    r = vera.post("/api/arrangements/arr-portofino/send")
    assert r.status_code == 200, r.text
    st = r.json()["desk"]
    assert st["status"] == "ai-checked" and st["sent"]["by"] == "Vera" and st["at_desk"]
    again = vera.post("/api/arrangements/arr-portofino/send").json()["desk"]
    assert again["sent"]["time"] == st["sent"]["time"]  # a second click changes nothing
    hist = json.loads((tmp_path / "data/models/arr-portofino/desk.json").read_text())["history"]
    assert [h["action"] for h in hist] == ["sent to the Desk"]
    listed = vera.get("/api/arrangements").json()
    assert next(x for x in listed if x["id"] == "arr-portofino")["desk"]["status"] == "ai-checked"
    log = (tmp_path / "data/learning/desk.jsonl").read_text()
    assert "sent to the Desk" in log


def test_the_dxf_only_once_approved(app: Any, tmp_path: Path) -> None:
    vera, rens, wout = login(app, "vera"), login(app, "rens"), login(app, "wouter")
    url = "/api/models/arr-portofino/files/cut.dxf"
    assert vera.get(url).status_code == 403
    vera.post("/api/arrangements/arr-portofino/send")
    assert rens.get(url).status_code == 403  # waiting is not approved
    assert vera.post("/api/desk/arr-portofino", json={"action": "approve"}).status_code == 403
    r = wout.post("/api/desk/arr-portofino", json={"action": "approve"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert vera.get(url).status_code == 200
    one = vera.get("/api/arrangements/arr-portofino").json()["desk"]
    assert one["approved"]["by"] == "Wouter Bekkers" and one["dxf_ok"] is True
    assert "cut" not in one["approved"]  # the fingerprints stay on the server
    # the switch: off, an arrangement follows gate_scope like any other model
    d = tmp_path / "data/models/arr-unbuilt"
    on = {"desk.require_approval_for_dxf": True, "desk.gate_scope": "drawings",
          "desk.gate_arrangements": True}  # fmt: skip
    assert desk.dxf_allowed(d, on) is False
    assert desk.dxf_allowed(d, {**on, "desk.gate_arrangements": False}) is True


def test_a_change_after_approval_reopens_it(app: Any, tmp_path: Path) -> None:
    vera, rens = login(app, "vera"), login(app, "rens")
    d = tmp_path / "data/models/arr-portofino"
    vera.post("/api/arrangements/arr-portofino/send")
    rens.post("/api/desk/arr-portofino", json={"action": "approve"})
    assert json.loads((d / "cover.json").read_text())["status"] == "checked"
    # rebuilt elsewhere (the model page): the cut file differs from the one approved
    (d / "cut.dxf").write_text("0\nSECTION\n0\nEOF\n")
    assert vera.get("/api/models/arr-portofino/files/cut.dxf").status_code == 403
    item = next(i for i in vera.get("/api/desk").json()["items"] if i["id"] == "arr-portofino")
    assert item["status"] == "ai-checked"
    st = json.loads((d / "desk.json").read_text())
    last = st["history"][-1]
    assert last["action"] == "changed after approval" and "cut file" in last["text"]
    assert st["sent"]["announced"] is None and "approved" not in st
    assert json.loads((d / "cover.json").read_text())["status"] == "draft"
    # approved again; then the plan is changed on the Arrangements page
    rens.post("/api/desk/arr-portofino", json={"action": "approve"})
    user = type("U", (), {"name": "Vera", "username": "vera"})()
    entry = desk.arrangement_changed(d, ["plan follow → box"], user, tmp_path / "data/learning")
    assert entry and entry["action"] == "changed after approval"
    assert desk.state(d)["status"] == "ai-checked"
    # rejected, then changed: back to waiting as well
    rens.post("/api/desk/arr-portofino", json={"action": "reject", "text": "te ruim"})
    entry = desk.arrangement_changed(d, ["place of suns-sofa"], user, tmp_path / "data/learning")
    assert entry and entry["action"] == "changed after rejection"
    assert desk.state(d)["status"] == "ai-checked" and "rejected" not in desk.state(d)
    # not sent yet: a change is nobody's business at the Desk
    assert desk.arrangement_changed(tmp_path / "data/models/arr-unbuilt", ["x"], user,
                                    tmp_path / "data/learning") is None  # fmt: skip


def test_what_changed_in_words() -> None:
    m = {"model_id": "a", "x_mm": 0.0, "y_mm": 0.0, "rot_deg": 0.0, "mirror": False}
    old = {"name": "x", "gap_mm": 0.0, "footprint": "follow",
           "members": [{**m, "version": {"model_glb": "1"}}]}  # fmt: skip
    assert changes(old, old, Path("/nowhere")) == []
    assert changes(old, {**old, "name": "y"}, Path("/nowhere")) == []  # a name alone
    moved = {**old, "members": [{**m, "x_mm": 100.0, "version": {"model_glb": "1"}}]}
    assert changes(old, moved, Path("/nowhere")) == ["place of a"]
    assert changes(old, {**old, "footprint": "box"}, Path("/nowhere")) == ["plan follow → box"]
    other = {**old, "members": [{**m, "version": {"model_glb": "2"}}]}
    assert changes(old, other, Path("/nowhere")) == ["furniture of a changed"]


def test_the_approvers_digest_lists_arrangements_once(app: Any, tmp_path: Path) -> None:
    from coverengine.params import Registry

    auth = app.state.auth
    params = Registry.load(None).resolve()
    mails: list[tuple[str, str, str]] = []
    models = tmp_path / "data/models"

    def send(to: str, subject: str, text: str) -> None:
        mails.append((to, subject, text))

    login(app, "vera").post("/api/arrangements/arr-portofino/send")
    Q.question_mails(auth, params, "https://studio", send, models)
    assert sorted(m[0] for m in mails) == [
        "rens@example.com", "rick@example.com", "wouter@example.com"
    ]  # fmt: skip
    assert "opstelling" in mails[0][1]
    assert "Portofino chaise + 2-seater" in mails[0][2] and "/#/desk/arr-portofino" in mails[0][2]
    mails.clear()
    auth.set_setting(Q.MAIL_KEY, {})  # even when the next digest is due: not twice
    Q.question_mails(auth, params, "https://studio", send, models)
    assert mails == []
