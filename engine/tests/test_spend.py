"""What the AI costs, kept and guarded (ADR-078)."""

from pathlib import Path

import pytest
from coverengine import spend
from coverengine.errors import CoverError
from coverengine.params import Registry


def _params(**over: object):  # type: ignore[no-untyped-def]
    return Registry.load(None).resolve(trial={"spend.budget_eur_month": 10,
                                              "spend.hourly_spike_eur": 100, **over})  # fmt: skip


def test_every_answer_is_written_down_and_warns_then_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path))
    p = _params()
    one = {"prompt_tokens": 1_000_000, "completion_tokens": 100_000}  # flash: 0.30 + 0.25 = €0.55
    assert spend.record(p, "gemini-3.8-flash", one) == pytest.approx(0.55)
    assert spend.status(p)["passed_pct"] is None
    for _ in range(9):
        spend.record(p, "gemini-3.8-flash", one)
    s = spend.status(p)
    assert s["month_eur"] == pytest.approx(5.5) and s["passed_pct"] == 50.0 and not s["stopped"]
    for _ in range(9):
        spend.record(p, "gemini-3.8-flash", one)
    with pytest.raises(CoverError, match="budget"):
        spend.guard(p)  # €10.45 of €10: no more paid calls
    assert not spend.status(_params(**{"spend.hard_stop": False}))["stopped"]


def test_reasoning_counts_as_output_and_an_unknown_model_as_the_dearest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path))
    p = _params()
    u = {"prompt_tokens": 0, "completion_tokens": 0,
         "completion_tokens_details": {"reasoning_tokens": 1_000_000}}  # fmt: skip
    assert spend.record(p, "gemini-3.1-pro-preview", u) == pytest.approx(12.0)
    assert spend.record(p, "some-new-model", {"completion_tokens": 1_000_000}) == pytest.approx(
        12.0
    )
