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


def test_one_visitor_s_day_is_capped_and_kept_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-099: the public shop's AI suggestions are written down per visitor (a daily tag of
    the address, never the address) and a visitor's day is capped (suggest.visitor_eur_day)."""
    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path))
    p = _params(**{"suggest.visitor_eur_day": 1.0})
    one = {"prompt_tokens": 1_000_000, "completion_tokens": 100_000}  # €0.55
    with spend.for_visitor("203.0.113.9") as tag:
        spend.record(p, "gemini-3.8-flash", one)
        spend.record_eur("search", 0.5)
    spend.record(p, "gemini-3.8-flash", one)  # not a visitor's: the studio's own work
    assert spend.visitor_eur("203.0.113.9") == pytest.approx(1.05)
    assert spend.visitor_eur("198.51.100.7") == 0.0
    ledger = next((tmp_path / "usage").glob("ai-*.jsonl")).read_text()
    assert "203.0.113.9" not in ledger and tag in ledger
    with pytest.raises(CoverError, match="today"):
        spend.guard_visitor(p, "203.0.113.9")
    spend.guard_visitor(p, "198.51.100.7")  # another visitor goes on
