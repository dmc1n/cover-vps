"""Only what changed is calculated again; the expensive extras on request (ADR-080)."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from coverengine.cli import main
from coverengine.io.model_io import import_model
from coverengine.params import Registry
from coverengine.testshapes import write_all as write_shapes

STEPS = ("hull", "cut", "flatten", "export")


@pytest.fixture(scope="module")
def box(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The test box, calculated once to the end, with a cover.json (as every model has)."""
    root = tmp_path_factory.mktemp("cache")
    write_shapes(root / "generated")
    d = root / "box"
    import_model(root / "generated" / "box_with_legs.stl", d, Registry.load().resolve())
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "parameters": {}}))
    for step in STEPS:
        assert main([step, str(d)]) == 0, step
    return d


def _run(d: Path, capsys: Any, *extra: str) -> list[str]:
    """The steps that really ran (not skipped)."""
    ran = []
    for step in STEPS:
        capsys.readouterr()
        assert main([step, str(d), *extra]) == 0, step
        if "unchanged, skipped" not in capsys.readouterr().out:
            ran.append(step)
    return ran


def test_every_step_leaves_a_stamp_and_an_unchanged_run_skips_all(
    box: Path, tmp_path: Path, capsys: Any
) -> None:
    d = tmp_path / "box"
    shutil.copytree(box, d)
    for step in STEPS:
        stamp = json.loads((d / "steps" / f"{step}.json").read_text())
        assert stamp["engine"] and stamp["files"] and stamp["params"], step
    assert _run(d, capsys) == []


def test_a_vent_setting_reruns_export_only_and_clearance_reruns_from_hull(
    box: Path, tmp_path: Path, capsys: Any
) -> None:
    d = tmp_path / "box"
    shutil.copytree(box, d)
    doc = json.loads((d / "cover.json").read_text())
    doc["parameters"] = {"features": {"vents_total": 3}}
    (d / "cover.json").write_text(json.dumps(doc))
    assert _run(d, capsys) == ["export"]
    doc["parameters"]["hull"] = {"clearance_mm": 25}
    (d / "cover.json").write_text(json.dumps(doc))
    assert _run(d, capsys) == list(STEPS)


def test_catalogue_notes_do_not_count_and_force_always_runs(
    box: Path, tmp_path: Path, capsys: Any
) -> None:
    d = tmp_path / "box"
    shutil.copytree(box, d)
    doc = json.loads((d / "cover.json").read_text())
    doc.update(status="checked", tags=["drawing"], notes="approved at the Desk")
    (d / "cover.json").write_text(json.dumps(doc))
    assert _run(d, capsys) == []
    assert _run(d, capsys, "--force") == list(STEPS)
    (d / "pattern.json").unlink()  # an output gone: that step runs again; its new pattern.json
    assert _run(d, capsys) == ["flatten"]  # is the same byte for byte, so export need not


def test_the_extras_are_made_when_asked(box: Path, tmp_path: Path) -> None:
    """No size drawing on every flatten; no vents.json on every export; a revision only when
    the cutting file changed."""
    from coverengine.catalogue import revisions
    from coverengine.export.drawing import ensure_sizes
    from coverengine.finish.vents3d import ensure_vents

    d = tmp_path / "box"
    shutil.copytree(box, d)
    assert not (d / "sizes.pdf").exists() and not (d / "vents.json").exists()
    assert ensure_sizes(d) == d / "sizes.pdf" and (d / "sizes.pdf").read_bytes()[:4] == b"%PDF"
    assert ensure_vents(d) == d / "vents.json"
    before = len(revisions(d))
    assert main(["export", str(d), "--force"]) == 0  # the same cut.dxf: no new revision
    assert len(revisions(d)) == before
    assert main(["export", str(d), "--force", "--save-version"]) == 0
    assert len(revisions(d)) == before + 1


def test_the_hull_rules_choose_without_any_ai(
    box: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Box pieces and balloons: a rule by default (hull.box_ai / hull.balloon_ai off)."""
    import coverengine.ai as ai

    def no_ai(*_: Any, **__: Any) -> Any:
        raise AssertionError("an AI call although hull.box_ai is off")

    monkeypatch.setattr(ai, "ask_parts", no_ai)
    monkeypatch.setattr(ai, "ask", no_ai)
    d = tmp_path / "box"
    shutil.copytree(box, d)
    (d / "cover.json").write_text(json.dumps({"parameters": {"hull": {"top": "box"}}}))
    assert main(["hull", str(d), "--set", "ai.provider=deepseek"]) == 0
    hull = json.loads((d / "hull.json").read_text())
    assert hull["box"]["chosen_by"] == "rule"


def test_no_drape_is_queued_after_a_calculation_by_default() -> None:
    from coverapi import main as api_main

    assert Registry.load().resolve()["drape.auto"] is False
    assert (
        api_main._auto_drape() is False or __import__("os").environ.get("COVER_AUTO_DRAPE") == "on"
    )
