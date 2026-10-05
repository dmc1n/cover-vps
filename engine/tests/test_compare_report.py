"""What the program did with the workshop's upload, in plain words (ADR-074)."""

from pathlib import Path
from typing import Any

import pytest
from coverengine import compare

SURFACE = {"kind": "surface", "reference": "mine.stl", "triangles": 12,
           "read_as": {"unit": "m", "up": "Z", "turned_deg": 90, "fit_moved_mm": 2.0},
           "mean_mm": 1.2, "p95_mm": 4.0, "max_mm": 10.0, "within_fit_pct": 96.0,
           "roomier_pct": 3.0, "tighter_pct": 1.0,
           "size_mm": {"ours": [1200, 800, 700], "theirs": [1200, 800, 710]}}  # fmt: skip
DRAWING = {"kind": "drawing", "reference": "mine.pdf", "pages": 1,
           "written_mm": [800.0, 1200.0],
           "matched": [{"written_mm": 800.0, "ours": "top: flat width", "ours_mm": 800.0},
                       {"written_mm": 1200.0, "ours": "top: flat length", "ours_mm": 1200.0}],
           "missing_mm": [], "ai": {"lessons": [{"rule": "one top"}]}}  # fmt: skip
SOURCE = {"name": "mine.stl", "by": "rick", "time": 0, "bytes": 2_000_000}


def test_a_close_3d_reference_agrees_and_says_how_it_was_read() -> None:
    dc = {"deepseek": {"verdict": "agrees", "summary": "Fits."}}
    r = compare.report("surface", SURFACE, SOURCE, dc)
    assert r["verdict"] == "agrees" and r["headline"].startswith("Your reference agrees")
    text = " ".join(" ".join(s["detail"]) for s in r["steps"])
    assert "read in m with Z up" in text and "Turned 90°" in text and "96.0 %" in text
    assert "uploaded by rick" in text and "DeepSeek" in text


def test_when_the_ai_reads_the_numbers_otherwise_a_person_looks() -> None:
    dc = {"deepseek": {"verdict": "differs", "summary": "Too tight at the arms."}}
    assert compare.report("surface", SURFACE, SOURCE, dc)["verdict"] == "look"


def test_a_failed_double_check_is_shown_and_the_numbers_decide() -> None:
    far = {**SURFACE, "within_fit_pct": 40.0}
    r = compare.report("surface", far, SOURCE, {"error": "the AI did not answer"})
    assert r["verdict"] == "differs"
    assert any("Not done" in d for s in r["steps"] for d in s["detail"])


@pytest.mark.parametrize(
    ("outcome", "missing", "verdict"),
    [("agreed: same", [], "agrees"), ("agreed: same", [990.0], "look"),
     ("agreed: different", [], "differs"), ("person to check", [], "look")],
)  # fmt: skip
def test_a_pdf_verdict_needs_its_sizes_and_both_ais(
    outcome: str, missing: list[float], verdict: str
) -> None:
    res = {**DRAWING, "missing_mm": missing, "written_mm": [*DRAWING["written_mm"], *missing]}
    dc = {"gemini": {"same": True, "score": 90}, "deepseek": {"same": True}, "outcome": outcome}
    r = compare.report("drawing", res, {**SOURCE, "name": "mine.pdf"}, dc)
    assert r["verdict"] == verdict
    two = next(s for s in r["steps"] if s["title"] == "Double check by two AIs")
    assert any(d.startswith("Gemini") for d in two["detail"])
    assert any(d.startswith("Outcome: " + outcome) for d in two["detail"])


def test_the_changes_step_lists_proposed_and_accepted_lessons() -> None:
    acc = [{"rule": "one top", "accepted_by": "rick", "time": 0}]
    step = compare.changes_step(DRAWING, acc)
    assert step["detail"][0].startswith("Nothing in the program")
    assert any("proposed 1 lesson" in d for d in step["detail"])
    assert any("Accepted by rick" in d and "one top" in d for d in step["detail"])


def test_the_double_check_of_a_drawing_uses_both_ais(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coverengine import crosscheck

    (tmp_path / "cover.png").write_bytes(b"")
    (tmp_path / "finished.json").write_text("{}")
    seen: list[Any] = []
    monkeypatch.setattr(crosscheck, "run", lambda pdf, m: seen.append(pdf) or {"outcome": "x"})
    assert compare.double_check("drawing", DRAWING, tmp_path / "d.pdf", tmp_path) == {
        "outcome": "x"
    }
    assert seen == [tmp_path / "d.pdf"]
    # without the program's picture the check says why, it does not fail
    (tmp_path / "cover.png").unlink()
    assert "error" in compare.double_check("drawing", DRAWING, tmp_path / "d.pdf", tmp_path)


def test_the_double_check_of_a_3d_model_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import coverengine.ai as ai

    def boom(*a: Any, **k: Any) -> dict[str, Any]:
        raise RuntimeError("offline")

    monkeypatch.setattr(ai, "ask_parts", boom)
    assert compare.double_check("surface", SURFACE, Path("x.stl"), Path("."))["error"] == "offline"
