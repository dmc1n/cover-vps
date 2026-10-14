"""Proposals for Covers → Links (ADR-132): which drawing cover and which 3D-model cover are the
same product, with a score and the reasons.

    COVER_DATA_DIR=~/cover-data uv run python scripts/link_proposals.py --dry-run | --apply
        [--models DIR] [--db FILE] [--json OUT.json] [--per-drawing 3] [--only drawing-d2,...]
        [--gemini-ties N --budget-eur 5]

Scores every drawing cover against every SUNS model and arrangement (coverapi.link_score) and
keeps per drawing its best pairs from `links.propose_min` on, plus every pair the product list
(namecode.xlsx) links, whatever its score: those were shown as facts before; now a person
confirms or rejects them (D2 "Evora normal D- Bed" and the Evora sunlounger).

--apply writes the proposals into app.db (`model_links`, with the history in `model_link_log`).
A person's decision (confirmed, rejected, chosen by hand) is never changed: such a pair is only
counted as "kept". Proposals the script no longer makes are marked stale, never deleted.
--dry-run (the default) does the same on an in-memory copy of app.db and says what would
change; nothing is written. Only the main session applies, after review.

--gemini-ties N: for at most N drawings whose two best proposals score within 0.02 of each
other, Gemini (ai.vision_model) looks at the drawing's 3D view and the candidates' renders and
picks one; its pick is a reason and a small `ai` signal, never a decision. Every call goes into
the AI ledger; the run stops at --budget-eur (at most 5).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from coverapi import link_score as ls
from coverapi import links, match_list
from coverengine.params import Registry
from coverengine.staging import guard_staging_output

TIE = 0.02  # param-ok: two proposals this close are a tie
AI_BONUS = 0.03  # param-ok: Gemini's pick of a tie: a small push, not a decision
MAX_BUDGET_EUR = 5.0  # param-ok: the owner's cap for this tie-break (14 Oct 2026)
DEFAULT_PER_DRAWING = 3  # param-ok: proposals per drawing shown in the queue

AI_SYSTEM = """You compare a furniture cover drawing with renders of covers made from 3D models.
The first picture is the drawing's 3D view (a cover for one product). The next pictures are
candidate covers, numbered from 1. Which candidate is the same product (same shape, same
proportions, same hand: left/right)? If none fits, say 0. Answer with JSON only:
{"best": <number>, "confidence": <0..1>, "why": "one short sentence"}"""


def _png(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = base64.b64encode(path.read_bytes()).decode()
    mime = "image/jpeg" if path.suffix == ".jpg" else "image/png"
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def tie_break(
    props: list[dict[str, Any]], models: Path, p: Any, limit: int, budget: float
) -> dict[str, Any]:
    """Gemini's pick among tied proposals (at most `limit` drawings, `budget` euros)."""
    from coverengine import spend
    from coverengine.ai import ask_parts

    vision = Registry.load(None).resolve(
        trial={
            "ai.provider": str(p["ai.vision_provider"]),
            "ai.model": str(p["ai.vision_model"]),
        },
        server={"ai.base_url": str(p["ai.vision_base_url"])},
    )
    by_drawing: dict[str, list[dict[str, Any]]] = {}
    for r in props:
        if r["sheet"] != "linked":
            by_drawing.setdefault(r["drawing_id"], []).append(r)
    spent, asked = 0.0, 0
    for did, rs in sorted(by_drawing.items()):
        rs.sort(key=lambda r: -r["score"])
        if len(rs) < 2 or rs[0]["score"] - rs[1]["score"] > TIE or asked >= limit:  # noqa: PLR2004
            continue
        if spent >= budget:
            break
        tied = [r for r in rs if rs[0]["score"] - r["score"] <= TIE][:4]  # param-ok: four at most
        first = _png(models / did / "reference.png") or _png(models / did / "cover.png")
        pics = [_png(models / r["model_id"] / "cover.png") for r in tied]
        if first is None or any(x is None for x in pics):
            continue
        parts: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": f"Drawing {did}; candidates: " + ", ".join(r["model_id"] for r in tied),
            }
        ]
        parts += [first, *[x for x in pics if x]]
        try:
            ans = ask_parts(vision, AI_SYSTEM, parts, note=f"link tie-break {did}")
        except Exception as exc:  # noqa: BLE001 - no answer: the tie stays a tie
            print(f"  Gemini on {did}: {exc}", file=sys.stderr)
            continue
        asked += 1
        u = ans.get("_usage") or {}
        spent += spend.cost_eur(
            vision,
            str(vision["ai.model"]),
            int(u.get("prompt_tokens") or 0),
            int(u.get("completion_tokens") or 0),
        )
        best = int(ans.get("best") or 0)
        for i, r in enumerate(tied, start=1):
            r["signals"]["ai"] = 1.0 if i == best else 0.0
            if i == best:
                r["score"] = round(min(1.0, r["score"] + AI_BONUS), 3)
                r["reasons"].append(f"Gemini picked it among {len(tied)} ties: {ans.get('why')}")
    return {"asked": asked, "eur": round(spent, 4)}


def report_line(r: dict[str, Any], p: Any) -> str:
    s = ls.strength(r, p)
    extra = f" — {r['doubts'][0]}" if r["doubts"] else ""
    return (
        f"  {r['score']:.2f} {s:7} {r['drawing_id']:30} ↔ {r['model_id']:40}"
        f"{' [mirror]' if r['mirror'] else ''}{' [sheet]' if r['sheet'] else ''}{extra}"
    )


def main() -> None:
    data = Path(os.environ.get("COVER_DATA_DIR", "~/cover-data")).expanduser()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="say what would change (default)")
    mode.add_argument("--apply", action="store_true", help="write the proposals into app.db")
    ap.add_argument("--models", default=str(data / "models"))
    ap.add_argument("--db", default=str(data / "app.db"))
    ap.add_argument("--json", help="the whole proposal as JSON (not in a models folder)")
    ap.add_argument("--per-drawing", type=int, default=DEFAULT_PER_DRAWING)
    ap.add_argument("--only", default="", help="drawing ids, comma separated")
    ap.add_argument("--gemini-ties", type=int, default=0)
    ap.add_argument("--budget-eur", type=float, default=MAX_BUDGET_EUR)
    a = ap.parse_args()
    if a.json:
        guard_staging_output(Path(a.json).parent)
    p = Registry.load(None).resolve()
    models, db_path = Path(a.models), Path(a.db)
    lst = match_list.for_data(models.parent)
    drawings, others = ls.gather(models, p, lst)
    if a.only:
        only = {x.strip() for x in a.only.split(",") if x.strip()}
        drawings = [d for d in drawings if d.id in only]
    props, alone = ls.proposals(drawings, others, p, a.per_drawing)
    ai = {"asked": 0, "eur": 0.0}
    if a.gemini_ties > 0:
        ai = tie_break(props, models, p, a.gemini_ties, min(a.budget_eur, MAX_BUDGET_EUR))
    facts = {f.id: f.brief() for f in drawings + others}
    # where to write: app.db itself, or for a dry run an in-memory copy of it
    if a.apply:
        db = links.connect(db_path)
    else:
        db = sqlite3.connect(":memory:", isolation_level=None)
        if db_path.is_file():
            src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            src.backup(db)
            src.close()
        db.row_factory = sqlite3.Row
        db.executescript(links.SCHEMA)
    outcome: Counter[str] = Counter()
    kept: list[tuple[str, str, str]] = []
    try:
        db.execute("BEGIN IMMEDIATE")
        for r in props:
            what = links.upsert_proposal(
                db,
                r,
                ls.strength(r, p),
                {"drawing": facts.get(r["drawing_id"]), "model": facts.get(r["model_id"])},
            )
            outcome[what] += 1
            if what == "person":
                old = db.execute(
                    "SELECT status FROM model_links WHERE drawing_id=? AND model_id=?",
                    (r["drawing_id"], r["model_id"]),
                ).fetchone()
                kept.append((r["drawing_id"], r["model_id"], old[0]))
        if not a.only:
            outcome["stale"] = links.mark_stale(
                db, {(r["drawing_id"], r["model_id"]) for r in props}
            )
        db.execute("COMMIT" if a.apply else "ROLLBACK")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    finally:
        db.close()
    strengths = Counter(ls.strength(r, p) for r in props)
    print(f"drawing covers: {len(drawings)}, 3D-model covers: {len(others)}")
    print(
        f"proposals: {len(props)} ({', '.join(f'{k} {v}' for k, v in sorted(strengths.items()))})"
        f"; from the product list: {sum(1 for r in props if r['sheet'] == 'linked')}"
    )
    print(f"drawings without a partner: {len(alone)}")
    print(
        ("written to " if a.apply else "dry run, would be: ")
        + ", ".join(f"{k} {v}" for k, v in sorted(outcome.items()))
    )
    if kept:
        print(f"a person's decision kept as it is ({len(kept)}):")
        for d, m, s in kept[:20]:  # param-ok: the first few
            print(f"  {d} ↔ {m}: {s}")
    if ai["asked"]:
        print(f"Gemini tie-breaks: {ai['asked']}, about €{ai['eur']:.3f} (in the AI ledger)")
    top = sorted(props, key=lambda r: (-r["score"], r["drawing_id"]))
    print("best proposals:")
    for r in [r for r in top if ls.strength(r, p) == "high"][:15]:  # param-ok: the first few
        print(report_line(r, p))
    print("product list links in doubt:")
    for r in [r for r in top if r["sheet"] == "linked" and r["doubts"]][:25]:  # param-ok: a page
        print(report_line(r, p))
    print("no partner: " + ", ".join(alone))
    if a.json:
        out = {
            "proposals": ls.to_json(props),
            "alone": alone,
            "outcome": dict(outcome),
            "kept": kept,
            "ai": ai,
            "facts": facts,
        }
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=1, ensure_ascii=False))
        print(f"written: {a.json}")


if __name__ == "__main__":
    main()
