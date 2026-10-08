"""What the AI costs, kept and guarded (ADR-078).

The owner, 6 October 2026, after Gemini's monthly cap was hit: "build a trigger yourself for
when the costs go up". Every paid AI answer is written down with its tokens and its estimated
cost in euros (prices per million tokens in `spend.prices`, to confirm against the providers'
bills). Three triggers:

- **warn**: at `spend.warn_pct` of `spend.budget_eur_month` (50 % and 80 %), and when one hour
  costs more than `spend.hourly_spike_eur`; the watchdog (scripts/watchdog.py, every 10 minutes)
  mails the admin;
- **stop**: at 100 % of the month's budget every paid call is refused (`guard`), until the
  budget is raised in config or the month ends (`spend.hard_stop: false` turns this off).

The ledger is <data>/usage/ai-YYYY-MM.jsonl, one line per answer.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coverengine.errors import CoverError
from coverengine.params import EffectiveParams

PER_MILLION = 1e6  # param-ok: prices are per million tokens
HOUR_S = 3600.0  # param-ok
EUR_DIGITS = 5  # param-ok: the ledger keeps cents' fractions
PERCENT = 100.0  # param-ok: a share as a percentage

# ADR-099: the public shop's visitor whose request a paid call serves: a tag of the address
# salted with the day (never the address itself), written on the ledger's line, so what one
# visitor costs in a day can be capped
_VISITOR: contextvars.ContextVar[str] = contextvars.ContextVar("spend_visitor", default="")


def _day(when: float | None = None) -> str:
    return datetime.fromtimestamp(when or time.time(), UTC).strftime("%Y-%m-%d")


def visitor_tag(address: str, when: float | None = None) -> str:
    """A visitor's address as a short one-way tag that changes every day (UTC)."""
    return hashlib.sha256(f"{_day(when)}|{address}".encode()).hexdigest()[:16]


@contextmanager
def for_visitor(address: str) -> Iterator[str]:
    """Every paid call inside is written down for this visitor (see visitor_eur). Threads
    started inside must carry the context along (contextvars.copy_context)."""
    token = _VISITOR.set(visitor_tag(address))
    try:
        yield _VISITOR.get()
    finally:
        _VISITOR.reset(token)


def visitor_eur(address: str, now: float | None = None) -> float:
    """What one visitor's requests cost the AI today (UTC), from the ledger."""
    now = now or time.time()
    tag, day = visitor_tag(address, now), _day(now)
    return sum(
        float(r.get("eur", 0))
        for r in _rows(now)
        if r.get("who") == tag and _day(float(r.get("t", 0))) == day
    )


def guard_visitor(params: EffectiveParams, address: str) -> None:
    """Refuse a visitor whose suggestions cost more than suggest.visitor_eur_day today."""
    cap = float(params["suggest.visitor_eur_day"])  # type: ignore[arg-type]
    if cap > 0 and visitor_eur(address) >= cap:
        raise CoverError("this visitor's AI budget for today is used up")


def _dir() -> Path:
    """The data folder's usage/ (the server's data folder also for scripts run by hand)."""
    env = os.environ.get("COVER_DATA_DIR")
    server = Path.home() / "cover-data"
    base = Path(env) if env else (server if server.is_dir() else Path("data"))
    return base / "usage"


def _ledger(when: float | None = None) -> Path:
    t = datetime.fromtimestamp(when or time.time(), UTC)
    return _dir() / f"ai-{t:%Y-%m}.jsonl"


def prices(params: EffectiveParams) -> dict[str, tuple[float, float]]:
    """Model -> (€ per million tokens in, out), from "model=in/out, ..."."""
    out = {}
    for item in str(params["spend.prices"]).split(","):
        if "=" not in item:
            continue
        name, cost = item.split("=", 1)
        a, b = cost.split("/", 1)
        out[name.strip()] = (float(a), float(b))
    return out


def cost_eur(params: EffectiveParams, model: str, tokens_in: int, tokens_out: int) -> float:
    table = prices(params)
    # an unknown model is priced as the dearest one we know (better to warn too early)
    p_in, p_out = table.get(model) or max(table.values(), key=lambda x: x[1], default=(0.0, 0.0))
    return (tokens_in * p_in + tokens_out * p_out) / PER_MILLION


def record(params: EffectiveParams, model: str, usage: Any, what: str = "") -> float:
    """Write one answer's cost to the month's ledger; returns the € estimate."""
    u = usage if isinstance(usage, dict) else {}
    t_in = int(u.get("prompt_tokens") or 0)
    t_out = int(u.get("completion_tokens") or 0)
    details = u.get("completion_tokens_details") or {}
    if isinstance(details, dict):  # reasoning is billed as output
        t_out += int(details.get("reasoning_tokens") or 0)
    eur = cost_eur(params, model, t_in, t_out)
    try:
        _dir().mkdir(parents=True, exist_ok=True)
        row = {"t": round(time.time(), 1), "model": model, "in": t_in, "out": t_out,
               "eur": round(eur, EUR_DIGITS), "what": what}  # fmt: skip
        if _VISITOR.get():
            row["who"] = _VISITOR.get()
        with _ledger().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass  # the ledger must never stop the work
    return eur


def record_eur(model: str, eur: float, what: str = "") -> None:
    """Write a cost known in euros (a search fee) to the month's ledger."""
    try:
        _dir().mkdir(parents=True, exist_ok=True)
        row = {"t": round(time.time(), 1), "model": model, "in": 0, "out": 0,
               "eur": round(eur, EUR_DIGITS), "what": what}  # fmt: skip
        if _VISITOR.get():
            row["who"] = _VISITOR.get()
        with _ledger().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def _rows(when: float | None = None) -> list[dict[str, Any]]:
    path = _ledger(when)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def status(params: EffectiveParams, now: float | None = None) -> dict[str, Any]:
    """This month's spend, the last hour's, the budget and which triggers fire."""
    now = now or time.time()
    rows = _rows(now)
    month = sum(float(r.get("eur", 0)) for r in rows)
    hour = sum(float(r.get("eur", 0)) for r in rows if now - float(r.get("t", 0)) <= HOUR_S)
    budget = float(params["spend.budget_eur_month"])  # type: ignore[arg-type]
    warn = [float(x) for x in str(params["spend.warn_pct"]).split(",") if x.strip()]
    pct = PERCENT * month / budget if budget > 0 else 0.0
    by_model: dict[str, float] = {}
    for r in rows:
        by_model[r.get("model", "?")] = by_model.get(r.get("model", "?"), 0.0) + float(
            r.get("eur", 0)
        )
    return {
        "month_eur": round(month, 2),
        "hour_eur": round(hour, 2),
        "budget_eur": budget,
        "pct": round(pct, 1),
        "passed_pct": max([w for w in warn if pct >= w], default=None),
        "spike": hour >= float(params["spend.hourly_spike_eur"]),  # type: ignore[arg-type]
        "stopped": bool(params["spend.hard_stop"]) and budget > 0 and month >= budget,
        "by_model": {k: round(v, 2) for k, v in sorted(by_model.items(), key=lambda kv: -kv[1])},
        "calls": len(rows),
    }


def guard(params: EffectiveParams) -> None:
    """Refuse a paid call when this month's budget is used up."""
    s = status(params)
    if s["stopped"]:
        raise CoverError(
            f"the AI budget for this month is used up (€{s['month_eur']} of €{s['budget_eur']}): "
            "raise spend.budget_eur_month to go on"
        )
