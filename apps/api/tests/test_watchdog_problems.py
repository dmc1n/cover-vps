"""The admins' red banner (ADR-153): GET /api/admin/problems lists the watchdog's open problems
with when each started; admins only; both state formats; a broken file is no problem list."""

import json
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient


def _secret(user: str) -> str:
    return f"a-long-secret-for-{user[::-1]}-9"


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    a = create_app(tmp_path / "data", login_required=True)
    for user, role in (("rick", "admin"), ("rens", "editor"), ("werkplaats", "workshop")):
        u = a.state.auth.add_user(user, user.title(), role, f"{user}@example.com", False)
        a.state.auth.set_password(a.state.auth.invite(u.id), _secret(user))
    return a


def login(app: Any, user: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user, "password": _secret(user)})
    assert r.status_code == 200, r.text
    return c


def test_open_problems_for_admins_only(app: Any) -> None:
    state = app.state.store.root / "watchdog.json"
    rick = login(app, "rick")
    assert rick.get("/api/admin/problems").json() == {"problems": []}
    state.write_text(json.dumps({"version": 2, "problems": {
        "service:caddy": {"kind": "service", "subject": "caddy", "since": 2000.0,
                          "last_mail": 2000.0, "clear_runs": 0,
                          "text": "the service caddy is not running"},
        "backup": {"kind": "backup", "subject": "", "since": 1000.0, "last_mail": 1000.0,
                   "clear_runs": 1, "text": "the last backup failed"},
    }}))  # fmt: skip
    got = rick.get("/api/admin/problems").json()["problems"]
    assert [p["key"] for p in got] == ["backup", "service:caddy"]  # oldest first
    assert got[1] == {"key": "service:caddy", "kind": "service", "subject": "caddy",
                      "text": "the service caddy is not running", "since": 2000.0}  # fmt: skip
    system = rick.get("/api/admin/system").json()
    assert system["open_problems"] == ["the last backup failed", "the service caddy is not running"]
    for user in ("rens", "werkplaats"):
        assert login(app, user).get("/api/admin/problems").status_code == 403


def test_old_format_and_broken_file(app: Any) -> None:
    state = app.state.store.root / "watchdog.json"
    rick = login(app, "rick")
    state.write_text(json.dumps({"disk": {"since": 5.0, "told": 6.0, "text": "only 38 GB"}}))
    assert rick.get("/api/admin/problems").json()["problems"] == [
        {"key": "disk", "kind": "disk", "subject": "", "text": "only 38 GB", "since": 5.0}
    ]
    state.write_text("")  # the full disk of 12 Oct 2026 left an empty file
    assert rick.get("/api/admin/problems").json() == {"problems": []}
    state.write_text("{not json")
    assert rick.get("/api/admin/problems").json() == {"problems": []}
