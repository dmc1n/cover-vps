"""Execute script entry points against synthetic live trees, without AI or network."""

import importlib.util
import sys
from pathlib import Path

import pytest
from coverengine import staging

ROOT = Path(__file__).resolve().parents[2]

# Audit manifest: scripts that write models or accept a report destination that
# could overwrite model files. Remaining scripts create non-model artifacts or
# are read-only; deliberate live-metadata workflows are listed separately below.
CASES = {
    "drawing_rebuild": ["LIVE", "--pdfs", "PDF"],
    "drawing_merge": [],
    "drawing_features": ["--models", "LIVE", "--pdfs", "PDF"],
    "drawing_outline": ["LIVE", "--pdfs", "PDF"],
    "drawing_cover": None,
    "c6_surface": None,
    "answers_stage": None,
    "bbq_models": None,
    "innerwalls_sweep": None,
    "film/hero_data": None,
    "drawing_covers": ["LIVE"],
    "drawing_swept": ["LIVE", "--pdfs", "PDF"],
    "drawing_crosscheck": ["LIVE", "--pdfs", "PDF"],
    "drawing_axes_check": ["--fix", "--pdfs", "PDF"],
    "s44_cover": None,
    "warehouse": None,
    "gpu_check": ["--out", "LIVE"],
    "learned_check": ["--recalc", "--models", "LIVE"],
    "catalogue_page": ["--out", "LIVE/file.html"],
    "desk_marks": ["MODEL", "PIC", "LIVE/marks"],
    "fewer_check": ["MODEL", "--json", "LIVE/report.json"],
    "matchcards": ["--out", "LIVE"],
    "given_build": ["LIVE"],
    "fewer_build": ["LIVE"],
}
OUT_OF_SCOPE = {
    "desk_fingerprints",
    "desk_arrangements",
    "desk_import",
    "questions",
    "prices_import",
    "quotes_clean",
}


def load(name):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "staging_test_" + name.replace("/", "_"), ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("alias", [False, True])
def test_refuses_before_write(tmp_path, monkeypatch, name, alias):
    repo = tmp_path / "repo"
    live = repo / "models"
    live.mkdir(parents=True)
    marker = live / "untouched"
    marker.write_text("original")
    monkeypatch.setattr(staging, "REPO_ROOT", repo)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    target = live
    if alias:
        target = tmp_path / "alias"
        target.symlink_to(live, target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    # Fixed report paths must be guarded too, including their symlink aliases.
    (tmp_path / "out").symlink_to(live, target_is_directory=True)
    module = load(name)
    args = CASES[name]
    if name == "c6_surface":
        monkeypatch.setattr(sys, "argv", [name, str(target / "surface.stl")])
    if name == "learned_check":
        monkeypatch.setattr(module.learned, "data_dir", lambda: tmp_path)
    if args is not None:
        argv = [
            arg.replace("LIVE", str(target)).replace("PDF", str(tmp_path / "pdfs")) for arg in args
        ]
        monkeypatch.setattr(sys, "argv", [name, *argv])
    with pytest.raises((ValueError, SystemExit)) as error:
        if name == "c6_surface":
            import runpy

            runpy.run_path(str(ROOT / "scripts/c6_surface.py"), run_name="__main__")
        elif name == "answers_stage":
            module.stage({"model": "x"}, target, tmp_path / "source")
        elif name == "bbq_models":
            module.one({"id": "x"}, target, set())
        elif name == "innerwalls_sweep":
            module.sweep("x", tmp_path / "source", target, None)
        elif name == "film/hero_data":
            module.build(tmp_path / "source", target)
        elif name == "drawing_cover":
            module.make("x", "box", {}, target)
        elif name == "s44_cover":
            module.main("missing.pdf", str(target / "surface.glb"))
        elif name == "warehouse":
            module.fetch(tmp_path / "missing.json", target)
        elif name == "catalogue_page":
            module.main(argv)
        else:
            module.main()
    assert "Unsafe staging" in str(error.value) or "Build in staging" in str(error.value)
    assert sorted(p.name for p in live.iterdir()) == ["untouched"]
    assert marker.read_text() == "original"


def test_writer_manifest():
    # Model-specific write markers: avoid treating renderers, ledgers, docs or
    # generic report generators as model writers. New model writes require audit.
    import re

    markers = re.compile(
        r'(?:model|live|dst|d) / "(?:cover|check|desk|product|model)\.(?:json|jpg|glb)"'
    )
    known = set(CASES) | OUT_OF_SCOPE | {"answers_stage", "bbq_models", "innerwalls_sweep"}
    for path in (ROOT / "scripts").glob("*.py"):
        source = path.read_text()
        if markers.search(source) and any(
            s in source for s in ("write_text", "write_bytes", "copytree")
        ):
            assert path.stem in known, f"audit model writer {path.name}"
            if path.stem not in OUT_OF_SCOPE:
                assert "guard_staging_output" in source, path.name


@pytest.mark.parametrize("name", ["drawing_rebuild", "drawing_merge"])
def test_legacy_replacement_refuses_even_with_safe_report(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    argv = [name]
    if name == "drawing_rebuild":
        argv += [str(tmp_path / "report"), "--pdfs", str(tmp_path / "pdfs")]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit, match="Build in staging"):
        load(name).main()
    assert not list(tmp_path.iterdir())


def test_warehouse_photos_refuses_live(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "REPO_ROOT", tmp_path)
    live = tmp_path / "models"
    live.mkdir()
    with pytest.raises(ValueError, match="Unsafe staging"):
        load("warehouse").photos(live, None)
    assert not list(live.iterdir())
