"""Two AIs check a drawing cover and each other (ADR-072); the program decides the shape."""

import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from coverengine import crosscheck


@pytest.fixture
def case(tmp_path: Path) -> tuple[Path, Path]:
    doc = pymupdf.open()
    doc.new_page().insert_text((60, 500), "Height 45cm")
    doc.save(tmp_path / "d.pdf")
    model = tmp_path / "m"
    model.mkdir()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), 0)
    pix.save(model / "cover.png")
    (model / "finished.json").write_text(json.dumps({"pieces": [{"name": "top"}]}))
    return tmp_path / "d.pdf", model


def _answers(monkeypatch: pytest.MonkeyPatch, *answers: dict[str, Any]) -> list[str]:
    asked: list[str] = []
    queue = list(answers)

    def fake(params: Any, system: str, user: Any) -> dict[str, Any]:
        asked.append(system[:20])
        return dict(queue.pop(0))

    monkeypatch.setattr(crosscheck, "ask_parts", fake)
    return asked


def test_both_agree_without_a_second_look(case: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _answers(monkeypatch, {"same": True}, {"same": True})
    assert crosscheck.run(*case)["outcome"] == "agreed: same"
    assert len(asked) == 2


def test_a_disagreement_gets_a_second_look_then_a_person(
    case: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(monkeypatch, {"same": False}, {"same": True}, {"same": False})
    out = crosscheck.run(*case)
    assert out["outcome"] == "person to check" and "gemini_second" in out


def test_the_second_look_can_settle_it(case: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _answers(monkeypatch, {"same": False}, {"same": True}, {"same": True})
    assert crosscheck.run(*case)["outcome"] == "agreed: same"
