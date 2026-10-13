"""The Desk migrations plan read-only and apply once, only on temporary data."""

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from coverapi import desk
from coverapi import gate_migrate as migration
from coverengine.params import Registry


def model(
    models: Path,
    name: str,
    *,
    built: bool = True,
    status: str = "draft",
    st: dict[str, Any] | None = None,
    legacy: bool | None = None,
) -> Path:
    d = models / name
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps({"status": status}))
    if built:
        (d / "cut.dxf").write_text("cut")
        (d / "finished.json").write_text("{}")
    if st is not None:
        (d / "desk.json").write_text(json.dumps(st))
    if legacy is not None:
        cut = hashlib.sha256(b"cut").hexdigest() if legacy else "stale"
        (d / "approval.json").write_text(
            json.dumps({"name": "Rens", "time": 1234567890, "files": {"cut.dxf": cut}})
        )
    return d


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def cli(name: str, args: list[str]) -> int:
    path = Path(__file__).resolve().parents[3] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main(args))


def test_plans_and_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models = tmp_path / "models"
    model(models, "valid", legacy=True)
    model(models, "stale", legacy=False)
    model(models, "done", legacy=True, st={"status": "approved", "approved": {"cut": "old"}})
    model(models, "fingerprint", st={"status": "produced"})
    d = model(models, "keep")
    (d / "desk.json").write_text(
        json.dumps({"status": "approved", "approved": {"cut": desk.cut_fingerprint(d)}})
    )
    model(models, "production", status="production")
    model(models, "checked", status="checked")
    model(models, "waiting", st={"status": "ai-checked", "sent": {"by": "Rick"}})
    d = model(models, "check-only")
    (d / "check.json").write_text("{}")
    model(models, "unbuilt", built=False)
    model(models, "drawing-a")
    model(models, "arr-a")
    d = model(models, "none")
    (d / "cover.json").write_text('{"no_cover": true}')
    db = tmp_path / "app.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE orders (id INTEGER, status TEXT, model_id TEXT)")
        for i, status in enumerate(("in_production", "sewn", "shipped", "returned", "pending")):
            model(models, status)
            conn.execute("INSERT INTO orders VALUES (?, ?, ?)", (i, status, status))
    before = snapshot(tmp_path)
    definitive = {r.model_id: r.action for r in migration.plan_definitive(models)}
    assert definitive == {"valid": "grandfather", "stale": "stale", "done": "keep"}
    rows = {r.model_id: r for r in migration.plan_gate_all(models, db)}
    for name, action in {
        "valid": "grandfather",
        "stale": "send",
        "done": "send",  # approved for another cut: it reopens, never blessed
        "fingerprint": "fingerprint",
        "keep": "keep",
        "production": "grandfather",
        "checked": "grandfather",
        "waiting": "keep (waiting)",
        "check-only": "send",
        "unbuilt": "not built",
        "drawing-a": "already gated",
        "arr-a": "already gated",
        "pending": "send",
    }.items():
        assert rows[name].action == action
    assert rows["check-only"].desk_status == "ai-checked"
    assert "none" not in rows
    for status in ("in_production", "sewn", "shipped", "returned"):
        assert rows[status].reason.endswith(status) and rows[status].action == "grandfather"
    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path))
    for name in ("desk_definitive", "desk_gate_all"):
        assert cli(name, ["--dry-run"]) == 0
    assert snapshot(tmp_path) == before
    assert migration.plan_gate_all(models, tmp_path / "missing.db")
    empty = tmp_path / "empty.db"
    with sqlite3.connect(empty):
        pass
    assert migration.plan_gate_all(models, empty)


def test_apply_once_and_stamped_pdfs(tmp_path: Path) -> None:
    models = tmp_path / "models"
    valid = model(models, "valid", legacy=True, st={"rejected": {"by": "Rick"}})
    (valid / "approved").mkdir()
    for name in ("sizes.pdf", "cutting-list.pdf"):
        (valid / "approved" / name).write_bytes(b"stamped")
    stale = model(models, "stale", legacy=False)
    definitive = migration.plan_definitive(models)
    assert migration.apply_definitive(models, definitive) == {"grandfather": 1}
    st = desk._read(valid / "desk.json")
    assert st["approved"]["by"] == "Rens" and st["approved"]["time"] == 1234567890
    assert st["approved"]["stamped"] == {
        n: hashlib.sha256(b"stamped").hexdigest()[:20] for n in ("sizes.pdf", "cutting-list.pdf")
    }
    assert "rejected" not in st and not (stale / "desk.json").exists()
    model(models, "production", status="production")
    model(models, "active", status="checked")
    model(models, "fingerprint", st={"status": "approved"})
    model(models, "new")
    cover_before = {d.name: (d / "cover.json").read_bytes() for d in models.iterdir()}
    rows = migration.plan_gate_all(models, None)
    assert migration.apply_gate_all(models, rows, "Claude") == {
        "grandfather": 2,
        "send": 2,
        "fingerprint": 1,
    }
    before = snapshot(tmp_path)
    assert migration.apply_definitive(models, definitive) == {}
    assert migration.apply_gate_all(models, rows, "Claude") == {}
    assert snapshot(tmp_path) == before
    params = Registry.load(None).resolve(
        trial={"desk.gate_scope": "all", "desk.require_approval_for_dxf": True}
    )
    for name in ("valid", "production", "active", "fingerprint"):
        assert desk.dxf_allowed(models / name, params)
    assert not desk.dxf_allowed(stale, params)
    assert desk._read(models / "production" / "desk.json")["status"] == "produced"
    assert desk._read(models / "new" / "desk.json")["sent"]["by"] == "Claude"
    assert cover_before == {d.name: (d / "cover.json").read_bytes() for d in models.iterdir()}


@pytest.mark.parametrize("status", ["in_production", "sewn", "shipped", "returned"])
def test_order_grandfather(tmp_path: Path, status: str) -> None:
    d = model(tmp_path / "models", "order")
    assert migration.grandfather(d, f"order 42 {status}", note="migration")
    assert desk._read(d / "desk.json")["status"] == (
        "approved" if status == "in_production" else "produced"
    )


def test_changed_approval_and_cli_apply(tmp_path: Path) -> None:
    models = tmp_path / "models"
    changed = model(
        models,
        "changed",
        st={"status": "approved", "approved": {"cut": "old"}, "sent": {"by": "Rick"}},
    )
    missing = model(models, "missing", built=False, legacy=True)
    valid = model(models, "valid", legacy=True)
    rows = {r.model_id: r for r in migration.plan_gate_all(models, None)}
    assert rows["changed"].action == "send"
    assert rows["missing"].action == "not built"
    definitive = {r.model_id: r for r in migration.plan_definitive(models)}
    assert definitive["missing"].action == "stale"
    report = tmp_path / "report.json"
    assert (
        cli(
            "desk_definitive",
            ["--models", str(models), "--only", "valid", "--dry-run", "--json", str(report)],
        )
        == 0
    )
    assert [r["model_id"] for r in json.loads(report.read_text())] == ["valid"]
    assert not (valid / "desk.json").exists()
    assert cli("desk_definitive", ["--models", str(models), "--apply"]) == 0
    assert not (missing / "desk.json").exists()
    assert cli("desk_gate_all", ["--models", str(models), "--apply", "--by", "Rick"]) == 0
    assert desk._read(changed / "desk.json")["status"] == "ai-checked"
    before = snapshot(tmp_path)
    for name in ("desk_definitive", "desk_gate_all"):
        assert cli(name, ["--models", str(models), "--apply"]) == 0
    assert snapshot(tmp_path) == before


def test_a_rejection_and_a_drawing_are_never_grandfathered(tmp_path: Path) -> None:
    """A person said no at the Desk: no catalogue status, order or old approval overrules it;
    a drawing was gated before, so its definitive approval never opened the DXF."""
    models = tmp_path / "models"
    said_no = model(models, "said-no", status="checked", legacy=True, st={"status": "rejected"})
    model(models, "drawing-b", legacy=True)
    gate = {r.model_id: r.action for r in migration.plan_gate_all(models, None)}
    assert gate == {"said-no": "keep (rejected)", "drawing-b": "already gated"}
    old = {r.model_id: r.action for r in migration.plan_definitive(models)}
    assert old == {"said-no": "keep (rejected)", "drawing-b": "already gated"}
    assert not migration.grandfather(said_no, "in active use", note="x")
    assert desk._read(said_no / "desk.json")["status"] == "rejected"
