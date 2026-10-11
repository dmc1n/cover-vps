from pathlib import Path

import pytest
from coverengine import staging


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    models = repo / "models"
    models.mkdir(parents=True)
    (models / "chair").mkdir()
    (models / "chair/model.json").write_text("live")
    home = tmp_path / "home"
    (home / "cover-data").mkdir(parents=True)
    (home / "cover-data/models").symlink_to(models, target_is_directory=True)
    monkeypatch.setattr(staging, "REPO_ROOT", repo)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return models


@pytest.mark.parametrize("suffix", ["", "chair", "chair/new"])
def test_live_and_alias_rejected(live: Path, suffix: str) -> None:
    for root in (live, Path.home() / "cover-data/models"):
        with pytest.raises(ValueError, match="Unsafe staging output"):
            staging.guard_staging_output(root / suffix)
    assert (live / "chair/model.json").read_text() == "live"


def test_ancestors_rejected(live: Path) -> None:
    for dst in (live.parent, live.parent.parent, Path.home() / "cover-data"):
        with pytest.raises(ValueError):
            staging.guard_staging_output(dst)


def test_safe_sibling_and_missing_output(live: Path) -> None:
    staging.guard_staging_output(live.parent / "models-staged/new", live / "chair")


@pytest.mark.parametrize("relation", ["same", "child", "parent", "alias"])
def test_source_overlap_rejected(tmp_path: Path, live: Path, relation: str) -> None:
    src = tmp_path / "source"
    src.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(src, target_is_directory=True)
    dst = {"same": src, "child": src / "new", "parent": tmp_path, "alias": alias}[relation]
    with pytest.raises(ValueError):
        staging.guard_staging_output(dst, src)


def test_existing_output_file_symlink_rejected(tmp_path: Path, live: Path) -> None:
    dst = tmp_path / "staging"
    dst.mkdir()
    (dst / "model.json").symlink_to(live / "chair/model.json")
    with pytest.raises(ValueError):
        staging.guard_staging_output(dst)
    assert (live / "chair/model.json").read_text() == "live"


@pytest.mark.parametrize("script", ["given_build", "fewer_build", "innerwalls_sweep"])
@pytest.mark.parametrize("alias", [False, True])
def test_scripts_refuse_live_output_before_writes(
    tmp_path: Path, live: Path, monkeypatch: pytest.MonkeyPatch, script: str, alias: bool
) -> None:
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[2] / "scripts" / f"{script}.py"
    spec = importlib.util.spec_from_file_location(script, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = Path.home() / "cover-data/models" if alias else live
    if script == "innerwalls_sweep":
        listing = tmp_path / "list.json"
        listing.write_text('[{"model": "chair"}]')
        args = [str(listing), "--out", str(out)]
    else:
        args = [str(out)]
    monkeypatch.setattr(sys, "argv", [str(path), *args, "--models", str(live)])
    with pytest.raises(ValueError):
        module.main()
    assert (live / "chair/model.json").read_text() == "live"
    assert sorted(p.name for p in live.iterdir()) == ["chair"]
