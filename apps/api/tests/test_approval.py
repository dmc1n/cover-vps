"""Fresh web pipeline approvals and PDFs that are still being written."""

from pathlib import Path
from typing import Any

import pymupdf
import pytest
from coverapi import approval
from coverapi.jobs import Jobs, JobSpec
from coverapi.store import Store
from coverengine.export import drawing
from coverengine.io.kind import confirm
from coverengine.testshapes import chair, load_config, write_stl


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


def test_fresh_import_approves_without_opening_the_drawing(
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
    doc = approval.approve(fresh_model, "tester", "Tester")
    assert unfinished and all(count == 0 for count in unfinished)
    assert doc["valid"] and approval.state(fresh_model)["valid"]
    for filename in approval.STAMPED:
        with pymupdf.open(fresh_model / filename) as original:
            with pymupdf.open(fresh_model / "approved" / filename) as stamped:
                assert original.page_count > 0
                assert stamped.page_count == original.page_count
                assert all("APPROVED" in page.get_text() for page in stamped)


@pytest.mark.parametrize("filename", approval.STAMPED)
def test_empty_pdf_refuses_approval_without_side_effects(tmp_path: Path, filename: str) -> None:
    # A valid PDF page tree with no pages (PyMuPDF itself refuses to save one).
    empty = (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )
    (tmp_path / "cut.dxf").write_text("cut")
    for name in approval.STAMPED:
        with pymupdf.open() as pdf:
            pdf.new_page()
            pdf.save(tmp_path / name)
    (tmp_path / filename).write_bytes(empty)
    with pytest.raises(ValueError, match=rf"{filename} has no pages"):
        approval.approve(tmp_path, "tester", "Tester")
    assert not (tmp_path / "approval.json").exists()
    assert not (tmp_path / "approved").exists()
    assert not (tmp_path / "cover.json").exists()
