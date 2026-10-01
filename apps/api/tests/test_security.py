"""Logins, rights and approval (ADR-047): nothing without a login, nothing beyond one's rights."""

from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    a = create_app(tmp_path / "data", login_required=True)
    auth = a.state.auth
    admin = auth.add_user("rick", "Rick", "admin", "rick@example.com", True)
    viewer = auth.add_user("vera", "Vera", "viewer")
    editor = auth.add_user("eddy", "Eddy", "editor")
    for u, pw in ((admin, "a-long-admin-password"), (viewer, "a-long-viewer-password"),
                  (editor, "a-long-editor-password")):  # fmt: skip
        auth.set_password(auth.invite(u.id), pw)
    return a


def login(app: Any, user: str, pw: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return c


def test_nothing_without_a_login(app: Any) -> None:
    c = TestClient(app)
    assert c.get("/api/health").status_code == 200
    for path in (
        "/api/models",
        "/api/parameters",
        "/api/admin/users",
        "/api/models/x/files/cut.dxf",
    ):
        assert c.get(path).status_code == 401, path
    assert c.post("/api/batch", json={}).status_code == 401
    r = c.get("/api/health")
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors" in r.headers["content-security-policy"]


def test_wrong_passwords_lock_the_account(app: Any) -> None:
    c = TestClient(app)
    for _ in range(5):
        r = c.post("/api/auth/login", json={"username": "vera", "password": "wrong"})
        assert r.status_code == 401
    r = c.post("/api/auth/login", json={"username": "vera", "password": "a-long-viewer-password"})
    assert r.status_code == 429  # locked for a while, even with the right password


def test_rights(app: Any) -> None:
    viewer = login(app, "vera", "a-long-viewer-password")
    assert viewer.get("/api/models").status_code == 200
    assert viewer.post("/api/batch", json={"model_ids": []}).status_code == 403
    assert viewer.get("/api/admin/users").status_code == 403
    editor = login(app, "eddy", "a-long-editor-password")
    assert editor.get("/api/admin/users").status_code == 403
    assert editor.post("/api/models/x/approve", json={}).status_code == 403  # no can_approve
    admin = login(app, "rick", "a-long-admin-password")
    users = admin.get("/api/admin/users").json()["users"]
    assert {u["username"] for u in users} == {"rick", "vera", "eddy"}
    assert all("pw_hash" not in u for u in users)


def test_requests_from_another_site_are_refused(app: Any) -> None:
    admin = login(app, "rick", "a-long-admin-password")
    r = admin.post(
        "/api/admin/users", json={"username": "evil"}, headers={"origin": "https://evil.example"}
    )
    assert r.status_code == 403


def test_invite_link_sets_the_password_once(app: Any) -> None:
    admin = login(app, "rick", "a-long-admin-password")
    r = admin.post("/api/admin/users", json={"username": "wout", "name": "Wout", "role": "admin"})
    assert r.status_code == 200, r.text
    token = r.json()["link"].rsplit("/", 1)[1]
    new = TestClient(app)
    assert new.get(f"/api/auth/invite/{token}").json()["username"] == "wout"
    assert new.post(f"/api/auth/invite/{token}", json={"password": "short"}).status_code == 400
    r = new.post(f"/api/auth/invite/{token}", json={"password": "a-very-good-new-password"})
    assert r.status_code == 200
    assert new.get("/api/auth/me").json()["user"]["username"] == "wout"
    again = TestClient(app).post(
        f"/api/auth/invite/{token}", json={"password": "another-good-one!"}
    )
    assert again.status_code == 400  # once only


def test_the_last_admin_cannot_be_removed(app: Any) -> None:
    admin = login(app, "rick", "a-long-admin-password")
    rick = next(u for u in admin.get("/api/admin/users").json()["users"] if u["username"] == "rick")
    r = admin.put(f"/api/admin/users/{rick['id']}", json={"role": "viewer"})
    assert r.status_code == 400


def test_logout_ends_the_session(app: Any) -> None:
    c = login(app, "vera", "a-long-viewer-password")
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/models").status_code == 401
