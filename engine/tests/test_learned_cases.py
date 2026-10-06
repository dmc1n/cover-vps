"""Learning that changes the cover itself (ADR-082): the Desk's corrections, replayed.

Every file in testdata/learned/ is a correction made at the Desk, written so it can be replayed
on a cover built from scratch: a seam removed (two pieces joined), a seam added (a piece split),
a vent count set. The cover is built and calculated, the correction applied, the cover
calculated again, and what the case expects must hold. The live cases (the data folder's
learning/cases/) are checked the same way by scripts/learned_check.py.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from coverengine import learned
from coverengine.cli import main
from coverengine.drawn import build, scene
from coverengine.io.kind import confirm

CASES = sorted((Path(__file__).parents[2] / "testdata" / "learned").glob("*.json"))
STEPS = ("hull", "cut", "flatten", "export")


def _pieces(d: Path) -> int:
    fin = json.loads((d / "finished.json").read_text())
    return sum(1 for p in fin["pieces"] if not p["name"].startswith("vent-"))


def calculated(shape: str, sizes: dict[str, Any], d: Path, steps: tuple[str, ...] = STEPS) -> Path:
    """A cover drawn as `shape`, imported as a cover surface and calculated (scripts/
    drawing_cover.py does the same for the owner's drawings)."""
    src = d.parent / f"{d.name}.glb"
    scene(build(shape, sizes, 1420.0)).export(src)
    assert main(["import", str(src), "--out", str(d), "--units", "mm", "--up", "z"]) == 0
    confirm(d, "cover")
    for step in steps:
        assert main([step, str(d)]) == 0, step
    return d


def _resolve(edit: dict[str, Any], d: Path) -> dict[str, Any]:
    """A case's symbolic edit ("the first corner seam", "the top at half its length") as the
    point-based edit the Desk writes."""
    if edit["op"] == "join":
        seam = next(s for s in learned.seam_points(d) if s["kind"] == edit["seam_kind"])
        return {"op": "join", "at": seam["at"]}
    piece = next(p for p in learned.piece_points(d) if p["region"] == edit["piece_region"])
    i = "xyz".index(edit["axis"])
    value = piece["min"][i] + edit["fraction"] * (piece["max"][i] - piece["min"][i])
    return {"op": "split", "at": piece["at"], "axis": edit["axis"], "value_mm": value}


@pytest.mark.parametrize("case_file", CASES, ids=[c.stem for c in CASES])
def test_a_desk_correction_changes_the_next_calculation(case_file: Path, tmp_path: Path) -> None:
    case = json.loads(case_file.read_text())
    d = calculated(case["shape"], case["sizes"], tmp_path / "m")
    before = _pieces(d)
    expect = dict(case["expect"])
    for e in case["edits"]:
        edit = _resolve(e, d)
        learned.add_edit(d, edit)
        if expect.get("no_seam_near") is True:
            expect["no_seam_near"] = edit["at"]
    if case["params"]:
        doc = json.loads((d / "cover.json").read_text())
        for k, v in case["params"].items():
            learned.set_dotted(doc.setdefault("parameters", {}), k, v)
        (d / "cover.json").write_text(json.dumps(doc))
    for step in ("cut", "flatten", "export"):
        assert main([step, str(d)]) == 0, step
    delta = expect.pop("pieces_delta", None)
    if delta is not None:
        assert _pieces(d) == before + delta
    assert learned.evaluate(d, expect) == []


def test_a_rule_learned_for_a_group_is_used_by_its_covers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rule accepted at the Desk for a drawing series reaches every cover of that series, under
    the cover's own settings; without the app's data folder it is not read (rule 10)."""
    from coverengine.params import resolve_model

    data = tmp_path / "data"
    s45 = tmp_path / "models" / "drawing-s45"
    c12 = tmp_path / "models" / "drawing-c12"
    for d in (s45, c12):
        d.mkdir(parents=True)
        (d / "cover.json").write_text(json.dumps({"format_version": 1, "model_id": d.name}))
    assert learned.group_of(s45) == "drawing-s" and learned.group_of(c12) == "drawing-c"
    learned.write_rule("drawing-s", "features.vent_above_hem_mm", 120.0, "Rens", "test", data)
    monkeypatch.delenv("COVER_DATA_DIR", raising=False)
    assert resolve_model(s45)["features.vent_above_hem_mm"] != 120.0  # not without the app
    monkeypatch.setenv("COVER_DATA_DIR", str(data))
    assert resolve_model(s45)["features.vent_above_hem_mm"] == 120.0
    assert resolve_model(c12)["features.vent_above_hem_mm"] != 120.0  # another series
    doc = json.loads((s45 / "cover.json").read_text())
    doc["parameters"] = {"features": {"vent_above_hem_mm": 80.0}}
    (s45 / "cover.json").write_text(json.dumps(doc))
    assert resolve_model(s45)["features.vent_above_hem_mm"] == 80.0  # the cover's own wins
    assert "rens" in (data / "learning" / "rules.jsonl").read_text().lower()


def test_the_same_correction_on_enough_covers_is_proposed_as_the_rule(tmp_path: Path) -> None:
    data, models = tmp_path / "data", tmp_path / "models"
    for i in range(1, 6):
        d = models / f"drawing-r{i}"
        d.mkdir(parents=True)
        (d / "cover.json").write_text("{}")
        fb = [{"kind": "vents", "params": {"features.vent_above_hem_mm": 300.0}}]
        (d / "feedback.json").write_text(json.dumps(fb if i <= 4 else []))
    assert learned.proposals(models, data, 5) == []  # 4 covers: not yet
    (models / "drawing-r5" / "feedback.json").write_text(json.dumps(fb))
    (prop,) = learned.proposals(models, data, 5)
    assert prop["group"] == "drawing-r" and prop["count"] == 5
    learned.write_rule("drawing-r", prop["key"], prop["value"], "Rick", "test", data)
    assert learned.proposals(models, data, 5) == []  # now the rule: no longer proposed


def test_an_edit_that_finds_nothing_says_so() -> None:
    import numpy as np

    centres = np.array([[0.0, 0, 0], [10, 0, 0]])
    adj = np.array([[0, 1]])
    label, notes = learned.apply_edits(centres, adj, np.array([0, 0]), [
        {"op": "join", "at": [5, 0, 0]}, {"op": "split", "at": [0, 0, 0], "axis": "z",
                                          "value_mm": 500}])  # fmt: skip
    assert list(label) == [0, 0] and "no seam left" in notes[0] and "does not reach" in notes[1]
