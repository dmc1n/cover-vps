"""The drawing desk (ADR-079): the AI sorts, Rens, Rick and Wouter approve; the DXF waits."""

import json
import time
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient


def _model(root: Path, name: str, outcome: str | None, score: float | None) -> Path:
    d = root / "models" / name
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "model_id": name,
                                              "status": "draft", "tags": ["drawing"]}))  # fmt: skip
    (d / "finished.json").write_text(json.dumps({"pieces": [
        {"name": "top", "quantity": 1, "size_mm": [1000, 800]},
        {"name": "vent-hood", "quantity": 4, "size_mm": [280, 315]}]}))  # fmt: skip
    (d / "cut.dxf").write_text("0\nEOF\n")
    if outcome:
        (d / "check.json").write_text(json.dumps({
            "code": name, "outcome": outcome, "gemini": {"score": score, "summary": "s"},
            "deepseek": {"score": score, "summary": "s"}}))  # fmt: skip
    return d


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    root = tmp_path / "data"
    a = create_app(root, login_required=True)
    auth = a.state.auth
    users = (("rick", "Rick", "admin"), ("rens", "Rens de Vries", "editor"),
             ("vera", "Vera", "editor"))  # fmt: skip
    for user, name, role in users:
        u = auth.add_user(user, name, role, f"{user}@example.com", False)
        auth.set_password(auth.invite(u.id), f"a-long-secret-for-{user[::-1]}-9")
    _model(root, "drawing-a", "agreed: same", 95)
    _model(root, "drawing-b", "agreed: different", 20)
    _model(root, "drawing-c", "person to check", 70)
    _model(root, "drawing-d", "agreed: different", 70)
    _model(root, "drawing-e", None, None)
    _model(root, "suns-chair", None, None)
    return a


def login(app: Any, user: str) -> TestClient:
    c = TestClient(app)
    r = c.post(
        "/api/auth/login", json={"username": user, "password": f"a-long-secret-for-{user[::-1]}-9"}
    )
    assert r.status_code == 200, r.text
    return c


def test_the_queue_puts_what_needs_a_person_first(app: Any) -> None:
    q = login(app, "vera").get("/api/desk?scope=drawings").json()
    order = [i["id"] for i in q["items"]]
    # AIs disagree, poor, middling, not checked, then what the AIs found right
    assert order == ["drawing-c", "drawing-b", "drawing-d", "drawing-e", "drawing-a"]
    assert q["items"][0]["vents"] == 4 and q["items"][0]["pieces"] == 1
    assert q["counts"]["ai-checked"] == 4 and q["counts"]["new"] == 1
    assert q["can_approve"] is False
    # by default every model (owner, 7 Oct 2026: all approvals at the Desk), SUNS ones too
    every = login(app, "vera").get("/api/desk").json()["items"]
    assert len(every) == 6 and any(i["id"] == "suns-chair" for i in every)


def test_only_approvers_decide_and_the_catalogue_follows(app: Any, tmp_path: Path) -> None:
    vera, rens = login(app, "vera"), login(app, "rens")
    assert vera.post("/api/desk/drawing-b", json={"action": "approve"}).status_code == 403
    assert rens.get("/api/desk").json()["can_approve"] is True  # "Rens" on the list
    r = rens.post("/api/desk/drawing-b", json={"action": "produced", "done": True})
    assert r.status_code == 409  # approve first
    assert (
        rens.post("/api/desk/drawing-b", json={"action": "approve"}).json()["status"] == "approved"
    )
    cover = tmp_path / "data" / "models" / "drawing-b" / "cover.json"
    assert json.loads(cover.read_text())["status"] == "checked"
    r = rens.post("/api/desk/drawing-b", json={"action": "produced", "done": True})
    assert r.json()["status"] == "produced"
    assert json.loads(cover.read_text())["status"] == "production"
    r = rens.post(
        "/api/desk/drawing-b", json={"action": "fit", "fits": False, "note": "2 cm short"}
    )
    assert r.json()["fit"]["note"] == "2 cm short"
    rens.post("/api/desk/drawing-b", json={"action": "undo"})  # the fit
    st = rens.post("/api/desk/drawing-b", json={"action": "undo"}).json()  # produced
    assert st["status"] == "approved"
    assert json.loads(cover.read_text())["status"] == "checked"


def test_a_reject_needs_a_reason_and_is_logged_not_an_ai_lesson(app: Any, tmp_path: Path) -> None:
    """ADR-082: a reject's words no longer go into AI prompts; corrections change the cover."""
    rick = login(app, "rick")
    assert rick.post("/api/desk/drawing-a", json={"action": "reject"}).status_code == 400
    r = rick.post("/api/desk/drawing-a", json={
        "action": "reject", "reasons": ["shape"], "text": "the front must be round"})  # fmt: skip
    assert r.json()["status"] == "rejected"
    learning = tmp_path / "data" / "learning"
    assert not (learning / "lessons.json").is_file()
    assert "the front must be round" in (learning / "desk.jsonl").read_text()
    card = rick.get("/api/desk/drawing-a").json()
    assert (
        card["desk"]["rejected"]["reasons"] == ["shape"]
        and "before" not in card["desk"]["history"][0]
    )


def test_the_cutting_dxf_waits_for_approval(app: Any) -> None:
    vera, rens, rick = login(app, "vera"), login(app, "rens"), login(app, "rick")
    url = "/api/models/drawing-e/files/cut.dxf"
    r = vera.get(url)
    assert r.status_code == 403 and "approve" in r.json()["detail"]
    assert vera.get(f"{url}?override=1").status_code == 403  # only an admin may override
    assert rick.get(f"{url}?override=1").status_code == 200
    hist = rick.get("/api/desk/drawing-e").json()["desk"]["history"]
    assert hist[-1]["action"] == "dxf override"
    rens.post("/api/desk/drawing-e", json={"action": "approve"})
    assert vera.get(url).status_code == 200
    # every cover since ADR-128 (Rens, question 84 b): a SUNS cover waits too
    assert vera.get("/api/models/suns-chair/files/cut.dxf").status_code == 403
    assert vera.get("/api/desk/drawing-a").json()["dxf_ok"] is False
    # the catalogue status set by hand never opens the gate
    cover = app.state.store.models / "suns-chair" / "cover.json"
    cover.write_text(cover.read_text().replace('"draft"', '"production"'))
    assert vera.get("/api/models/suns-chair/files/cut.dxf").status_code == 403
    rens.post("/api/desk/suns-chair", json={"action": "approve"})
    assert vera.get("/api/models/suns-chair/files/cut.dxf").status_code == 200


def test_drawing_fingerprint_reopens_and_revision_gate(app: Any, tmp_path: Path) -> None:
    from coverapi import desk

    d = tmp_path / "data/models/drawing-a"
    rens = login(app, "rens")
    viewer = login(app, "vera")
    old = d / "revisions/001"
    unapproved = d / "revisions/002"
    old.mkdir(parents=True)
    unapproved.mkdir()
    (old / "cut.dxf").write_bytes((d / "cut.dxf").read_bytes())
    (unapproved / "cut.dxf").write_text("never approved")
    base = "/api/models/drawing-a"
    assert viewer.get(f"{base}/revisions/001/cut.dxf").status_code == 403
    approved = rens.post("/api/desk/drawing-a", json={"action": "approve"}).json()
    cut = desk.cut_fingerprint(d)
    assert approved["approved"]["cut"] == cut
    assert approved["approved_fingerprints"] == [cut]
    assert viewer.get(f"{base}/revisions/001/cut.dxf").status_code == 200
    assert viewer.get(f"{base}/revisions/002/cut.dxf").status_code == 403
    rens.post("/api/desk/drawing-a", json={"action": "produced"})
    (d / "cut.dxf").write_text("rebuilt cut")
    assert viewer.get(f"{base}/files/cut.dxf").status_code == 403
    st = desk.state(d)
    assert st["status"] == desk.WAITING
    assert "approved" not in st and "produced" not in st
    assert st["history"][-1]["action"] == "changed after approval"
    assert json.loads((d / "cover.json").read_text())["status"] == "draft"
    assert viewer.get(f"{base}/revisions/001/cut.dxf").status_code == 200
    assert viewer.get(f"{base}/revisions/002/cut.dxf").status_code == 403
    rens.post("/api/desk/drawing-a", json={"action": "approve"})
    assert desk.state(d)["approved_fingerprints"] == [cut, desk.cut_fingerprint(d)]
    assert viewer.get(f"{base}/files/cut.dxf").status_code == 200


@pytest.mark.parametrize("status", ["approved", "produced"])
def test_drawing_legacy_approval_is_grandfathered(app: Any, tmp_path: Path, status: str) -> None:
    from coverapi import desk

    d = tmp_path / "data/models/drawing-a"
    (d / "desk.json").write_text(
        json.dumps(
            {"status": status, "approved": {"by": "Rens", "time": time.time() + 60}, "history": []}
        )
    )
    assert login(app, "vera").get("/api/models/drawing-a/files/cut.dxf").status_code == 200
    st = desk.state(d)
    assert st["status"] == status
    assert st["approved"]["by"] == "Rens"
    assert st["approved"]["cut"] == desk.cut_fingerprint(d)
    assert st["history"][-1]["text"] == "fingerprint recorded for an earlier approval"
    assert len(st["history"]) == 1
    (d / "cut.dxf").write_text("changed later")
    assert desk.state(d)["status"] == desk.WAITING


def test_drawing_fingerprint_migration_is_read_only_and_idempotent(tmp_path: Path) -> None:
    import importlib.util

    script = Path(__file__).resolve().parents[3] / "scripts/desk_fingerprints.py"
    spec = importlib.util.spec_from_file_location("desk_fingerprints", script)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    d = _model(tmp_path, "drawing-old", None, None)
    path = d / "desk.json"
    original = json.dumps({"status": "produced", "history": [], "approved": {"by": "Rens"}})
    path.write_text(original)
    assert migration.main(["--models", str(d.parent), "--dry-run"]) == 0
    assert path.read_text() == original
    assert migration.main(["--models", str(d.parent), "--apply"]) == 0
    recorded = path.read_text()
    assert migration.migrate(d.parent, apply=True) == []
    assert path.read_text() == recorded
    assert len(json.loads(recorded)["history"]) == 1


def test_drawing_approval_requires_cut_and_missing_cut_reopens(app: Any, tmp_path: Path) -> None:
    from coverapi import desk

    d = tmp_path / "data/models/drawing-e"
    rens = login(app, "rens")
    (d / "cut.dxf").unlink()
    assert rens.post("/api/desk/drawing-e", json={"action": "approve"}).status_code == 400
    assert not (d / "desk.json").exists()
    (d / "cut.dxf").write_text("approved cut")
    rens.post("/api/desk/drawing-e", json={"action": "approve"})
    (d / "cut.dxf").unlink()
    # A plain Desk read reopens it, even before any download attempt.
    assert desk.state(d)["status"] == desk.WAITING
    assert (
        len([e for e in desk.state(d)["history"] if e["action"] == "changed after approval"]) == 1
    )


def test_the_workshop_lists_approved_covers_read_only(app: Any, tmp_path: Path) -> None:
    """Work → Workshop (ADR-124): approved and produced covers, their files and fits, for every
    logged-in person; the DXF link only where the approval gate lets it through."""
    vera, rens = login(app, "vera"), login(app, "rens")
    assert TestClient(app).get("/api/workshop").status_code == 401
    assert vera.get("/api/workshop").json()["items"] == []
    rens.post("/api/desk/drawing-b", json={"action": "approve"})
    rens.post("/api/desk/drawing-c", json={"action": "approve"})
    rens.post("/api/desk/drawing-c", json={"action": "produced", "done": True})
    rens.post("/api/desk/drawing-c", json={"action": "fit", "fits": False, "note": "2 cm short"})
    w = vera.get("/api/workshop").json()
    by = {i["id"]: i for i in w["items"]}
    assert set(by) == {"drawing-b", "drawing-c"}  # not the waiting ones
    assert [i["id"] for i in w["items"]][0] == "drawing-c"  # the latest first
    c = by["drawing-c"]
    assert c["status"] == "produced" and c["produced"]["by"] == "Rens de Vries"
    assert c["fit"] == {"fits": False, "note": "2 cm short", "by": "Rens de Vries",
                        "time": c["fit"]["time"], "measured": 0, "worst": None}  # fmt: skip
    assert c["dxf_ok"] is True and c["files"][-1] == "cut.dxf"
    assert "checklist.pdf" not in c["files"]  # no pattern.json: nothing to make it from
    # the cut file changes after the approval: the link goes, the Desk asks again
    (tmp_path / "data" / "models" / "drawing-b" / "cut.dxf").write_text("0\nSECTION\n0\nEOF\n")
    by = {i["id"]: i for i in vera.get("/api/workshop").json()["items"]}
    assert "drawing-b" not in by or by["drawing-b"]["dxf_ok"] is False
    assert vera.get("/api/models/drawing-b/files/cut.dxf").status_code == 403
    # the page changes nothing: the Desk's decisions are as they were
    assert vera.get("/api/desk/drawing-c").json()["desk"]["status"] == "produced"


@pytest.mark.parametrize(
    "name", ["drawing-k", "suns-lounger", "bbq-bge-large", "order-12", "blocchi-sofa", "2026-x"]
)
def test_every_cover_kind_waits_for_the_desk(app: Any, tmp_path: Path, name: str) -> None:
    """ADR-128 (Rens, question 84 b): the cut DXF of every cover is behind the Desk gate;
    a kept revision too, until its cut file was approved."""
    d = _model(tmp_path / "data", name, None, None)
    rev = d / "revisions" / "001"
    rev.mkdir(parents=True)
    (rev / "cut.dxf").write_bytes((d / "cut.dxf").read_bytes())
    vera, rens = login(app, "vera"), login(app, "rens")
    assert vera.get(f"/api/models/{name}/files/cut.dxf").status_code == 403
    assert vera.get(f"/api/models/{name}/revisions/1/cut.dxf").status_code == 403
    assert rens.post(f"/api/desk/{name}", json={"action": "approve"}).status_code == 200
    assert vera.get(f"/api/models/{name}/files/cut.dxf").status_code == 200
    assert vera.get(f"/api/models/{name}/revisions/1/cut.dxf").status_code == 200
    (d / "cut.dxf").write_text("0\nSECTION\n0\nEOF\n")  # a new cut: approve again
    assert vera.get(f"/api/models/{name}/files/cut.dxf").status_code == 403
    assert vera.get(f"/api/desk/{name}").json()["desk"]["status"] == "ai-checked"


def test_an_order_lands_first_in_the_queue_and_one_click_approves(app: Any, tmp_path: Path) -> None:
    """ADR-128: a shop order's cover sent to production is on the Desk as an order, first in
    the queue whatever the AIs said; its approval is one click and lets the DXF through."""
    from coverapi import desk

    root = tmp_path / "data"
    learning = root / "learning"
    d = _model(root, "order-7", "agreed: same", 99)
    st = desk.mark_order(d, 7, "Rick", learning)
    assert st["status"] == "ai-checked" and st["sent"]["by"] == "Rick"
    rens, vera = login(app, "rens"), login(app, "vera")
    q = vera.get("/api/desk").json()["items"]
    assert q[0]["id"] == "order-7" and q[0]["order"]["order"] == 7 and q[0]["built"]
    assert rens.post("/api/desk/order-7", json={"action": "approve"}).status_code == 200
    q = vera.get("/api/desk").json()["items"]
    assert q[0]["id"] != "order-7"
    st = desk.state(d)
    assert st["order"]["approved"] and st["history"][-1]["order"] == 7
    assert vera.get("/api/models/order-7/files/cut.dxf").status_code == 200
    # a catalogue cover already approved for its cut stays approved: ready to cut
    again = desk.mark_order(d, 8, "Rick", learning)
    assert again["status"] == "approved" and again["order"]["approved"]
    # one that is not built yet waits, without a quick approval
    (d / "cut.dxf").unlink()
    q = vera.get("/api/desk").json()["items"]
    assert next(i for i in q if i["id"] == "order-7")["built"] is False
    assert rens.post("/api/desk/order-7", json={"action": "approve"}).status_code == 400


def test_a_name_on_the_list_or_may_approve_approves_never_the_workshop(app: Any) -> None:
    """The one approval (ADR-128): admins, `desk.approvers`, and users marked may approve."""

    from coverapi import desk
    from coverapi.auth import User
    from coverengine.params import Registry

    p = Registry.load(None).resolve()
    flagged = User(9, "anna", "Anna", None, "editor", True, True)
    plain = User(10, "bert", "Bert", None, "editor", False, True)
    bench = User(11, "rens", "Rens", None, "workshop", False, True)
    assert desk.approver(flagged, p) and not desk.approver(plain, p)
    assert not desk.approver(bench, p) and desk.worker(bench, p)
    assert desk.may_act(bench, p, "fit") and not desk.may_act(bench, p, "approve")
    assert not desk.worker(plain, p)


def test_an_approval_older_than_its_cut_file_is_not_grandfathered(app: Any, tmp_path: Path) -> None:
    """ADR-128: an earlier approval without a fingerprint is amended with the current cut file
    only when that file is not newer than the approval; else the cover goes back to waiting."""
    from coverapi import desk

    d = tmp_path / "data/models/suns-chair"
    (d / "desk.json").write_text(
        json.dumps({"status": "approved", "approved": {"by": "Rens", "time": 123}, "history": []})
    )
    assert login(app, "vera").get("/api/models/suns-chair/files/cut.dxf").status_code == 403
    st = desk.state(d)
    assert st["status"] == desk.WAITING and "cut" not in (st.get("approved") or {})
    assert st["history"][-1]["action"] == "changed after approval"


def test_the_flat_pattern_dxf_is_only_served_as_the_approval_saw_it(
    app: Any, tmp_path: Path
) -> None:
    """Codex review (ADR-128): a flatten run after the approval rewrites pattern.dxf but not
    cut.dxf; the approval of the cut file must not let the new flat DXF through."""
    d = tmp_path / "data/models/suns-chair"
    (d / "pattern.dxf").write_text("0\nEOF\n")
    vera, rens = login(app, "vera"), login(app, "rens")
    url = "/api/models/suns-chair/files/pattern.dxf"
    assert vera.get(url).status_code == 403
    assert rens.post("/api/desk/suns-chair", json={"action": "approve"}).status_code == 200
    assert vera.get(url).status_code == 200
    (d / "pattern.dxf").write_text("0\nSECTION\n0\nEOF\n")  # flattened again
    assert vera.get(url).status_code == 403
    assert vera.get("/api/models/suns-chair/files/cut.dxf").status_code == 200
