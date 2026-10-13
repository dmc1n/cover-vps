"""The Desk approval stamps the PDFs (ADR-128): fresh web pipeline covers, PDFs still being
written, empty PDFs, and the old definitive approvals as history."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pymupdf
import pytest
from coverapi import approval, desk
from coverapi.jobs import Jobs, JobSpec
from coverapi.store import Store
from coverengine.export import drawing
from coverengine.io.kind import confirm
from coverengine.testshapes import chair, load_config, write_stl
from fastapi import HTTPException

TESTER = SimpleNamespace(name="Tester", username="tester")


@pytest.fixture(scope="module")
def fresh_model(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("approval")
    shape = chair(load_config()["furniture"]["chair"])
    source = root / "chair.stl"
    write_stl(source, shape.vertices, shape.faces, shape.name)
    store = Store(root / "data")
    store.ensure()
    jobs = Jobs(store, drape_after_export=False)
    imported = jobs.submit(JobSpec("chair", ["import"], {}, source=str(source)))
    assert jobs.wait(imported["id"], 600)["status"] == "done"
    model = store.model_dir("chair")
    confirm(model, "product")
    run = jobs.submit(JobSpec("chair", ["hull", "cut", "flatten", "export"], {}))
    result = jobs.wait(run["id"], 600)
    assert result["status"] == "done", result
    return model


def test_a_desk_approval_stamps_without_opening_the_drawing(
    fresh_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert not (fresh_model / "sizes.pdf").exists()
    savefig = drawing.PdfPages.savefig
    unfinished = []

    def inspect_pending(pdf: Any, *args: Any, **kwargs: Any) -> None:
        savefig(pdf, *args, **kwargs)
        pdf._file.fh.flush()
        # Matplotlib has written page objects, but not the page tree until close().
        with pymupdf.open(pdf._file.fh.name) as pending:
            unfinished.append(pending.page_count)
        # Another request must never find that unfinished drawing in the cache.
        assert not (fresh_model / "sizes.pdf").exists()

    monkeypatch.setattr(drawing.PdfPages, "savefig", inspect_pending)
    learning = fresh_model.parent.parent / "learning"
    st = desk.apply(fresh_model, desk.Action(action="approve"), TESTER, learning)
    assert unfinished and all(count == 0 for count in unfinished)
    assert st["status"] == "approved" and st["approved"]["cut"] == desk.cut_fingerprint(fresh_model)
    assert sorted(st["approved"]["stamped"]) == sorted(approval.STAMPED)
    for filename in approval.STAMPED:
        assert desk.stamped_ok(fresh_model, filename)
        with pymupdf.open(fresh_model / filename) as original:
            with pymupdf.open(fresh_model / "approved" / filename) as stamped:
                assert original.page_count > 0
                assert stamped.page_count == original.page_count
                text = [page.get_text() for page in stamped]
                assert all("APPROVED" in t and "Tester" in t and "revision" in t for t in text)
    # no temporary file is left behind
    assert sorted(p.name for p in (fresh_model / "approved").iterdir()) == sorted(approval.STAMPED)
    # a stamped copy edited by hand is not served as approved
    (fresh_model / "approved" / "sizes.pdf").write_bytes(b"%PDF-1.4 changed")
    assert not desk.stamped_ok(fresh_model, "sizes.pdf")


def _built(tmp_path: Path, empty: str | None = None) -> Path:
    d = tmp_path / "models" / "suns-x"
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps({"model_id": "suns-x"}))
    (d / "cut.dxf").write_text("cut")
    (d / "finished.json").write_text(json.dumps({"pieces": []}))
    for name in approval.STAMPED:
        with pymupdf.open() as pdf:
            pdf.new_page()
            pdf.save(d / name)
    if empty:
        # A valid PDF page tree with no pages (PyMuPDF itself refuses to save one).
        (d / empty).write_bytes(
            b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
            b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
        )
    return d


@pytest.mark.parametrize("filename", approval.STAMPED)
def test_an_empty_pdf_refuses_the_approval_without_side_effects(
    tmp_path: Path, filename: str
) -> None:
    d = _built(tmp_path, filename)
    before = (d / "cover.json").read_text()
    with pytest.raises(HTTPException) as exc:
        desk.apply(d, desk.Action(action="approve"), TESTER, tmp_path / "learning")
    assert exc.value.status_code == 400 and f"{filename} has no pages" in str(exc.value.detail)
    assert not (d / "desk.json").exists()
    assert not (d / "approved").exists() or not any((d / "approved").iterdir())
    assert (d / "cover.json").read_text() == before


def test_a_missing_pdf_is_noted_and_a_later_approval_restamps(tmp_path: Path) -> None:
    d = _built(tmp_path)
    (d / "cutting-list.pdf").unlink()
    st = desk.apply(d, desk.Action(action="approve"), TESTER, tmp_path / "learning")
    assert list(st["approved"]["stamped"]) == ["sizes.pdf"]
    assert not desk.stamped_ok(d, "cutting-list.pdf")
    assert st["history"][-1]["stamped"] == ["sizes.pdf"]


def test_the_old_definitive_approval_is_history(tmp_path: Path) -> None:
    import hashlib

    d = _built(tmp_path)
    cut = hashlib.sha256((d / "cut.dxf").read_bytes()).hexdigest()
    (d / approval.APPROVAL_JSON).write_text(json.dumps({
        "approved_by": "rick", "name": "Rick", "time": 1, "revision": 2, "note": "",
        "files": {"cut.dxf": cut}}))  # fmt: skip
    old = approval.legacy(d)
    assert old and old["valid"] and old["legacy"]
    (d / "cut.dxf").write_text("another cut")
    assert approval.legacy(d)["valid"] is False  # type: ignore[index]
    assert not hasattr(approval, "approve") and not hasattr(approval, "withdraw")
