"""The drawing desk (ADR-079): people approve covers, the AI only sorts them.

The owner, 6 October 2026: "a hyper-modern dashboard where we keep track of everything, also a
checkbox when the cover has actually been produced"; the cutting table's DXF only once a cover
is approved; Rens, Rick and Wouter approve (`desk.approvers`).

Per model `desk.json` (written atomically) keeps the pipeline and its history:

    new -> ai-checked -> approved (who, when) -> produced (who, when)
                      \\-> rejected (who, when, reasons, text)

plus the fit after sewing, a preferred revision, the drawing's code and PDF. `check.json` holds
the latest Gemini + DeepSeek check (scripts/drawing_crosscheck.py writes it; desk_import.py
copied the earlier ones). Approval sets the catalogue status too: approved -> "checked",
produced -> "production", rejected -> "draft". A reject with words becomes a lesson for the AI
(learning/lessons.json, ADR-070) and every action is logged in learning/desk.jsonl.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

STATUSES = ("new", "ai-checked", "rejected", "approved", "produced")
CATALOGUE = {"approved": "checked", "produced": "production", "rejected": "draft"}
REASONS = ("shape", "size", "seams", "vents", "pieces", "other")
PAGE_DPI = 110  # param-ok: a drawing page as a picture on the desk
MAX_PAGES = 4  # param-ok
LOW = 60.0  # param-ok: below this average the AIs found the cover poor
_lock = threading.Lock()


class Action(BaseModel):
    action: str  # approve | reject | produced | fit | prefer | undo
    reasons: list[str] = []
    text: str = ""
    done: bool = True
    fits: bool = True
    note: str = ""
    n: int | None = None


# ---- state ----------------------------------------------------------------------------------


def _read(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        doc = {}
    return doc if isinstance(doc, dict) else {}


def _write(path: Path, doc: Any) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)  # never half written


def state(d: Path) -> dict[str, Any]:
    doc = _read(d / "desk.json")
    doc.setdefault("status", "new")
    doc.setdefault("history", [])
    if doc["status"] == "new" and (d / "check.json").is_file():
        doc["status"] = "ai-checked"
    return doc


def check(d: Path) -> dict[str, Any]:
    return _read(d / "check.json")


def scores(c: dict[str, Any]) -> dict[str, float | None]:
    g = c.get("gemini_second") or c.get("gemini") or {}
    s = c.get("deepseek") or {}
    gs = g.get("score") if isinstance(g.get("score"), int | float) else None
    ds = s.get("score") if isinstance(s.get("score"), int | float) else None
    vals = [x for x in (gs, ds) if x is not None]
    return {"gemini": gs, "deepseek": ds, "avg": sum(vals) / len(vals) if vals else None}


def priority(status: str, outcome: str | None, avg: float | None) -> tuple[int, float]:
    """The queue's order: the AIs disagree, then poor, rejected and middling, then unchecked,
    then those the AIs found right, then approved and produced."""
    a = avg if avg is not None else 0.0
    if status == "produced":
        return 7, a
    if status == "approved":
        return 6, a
    if status == "rejected":
        return 2, a
    if outcome == "person to check":
        return 0, a
    if outcome == "agreed: different":
        return (1, a) if a < LOW else (3, a)
    if outcome == "agreed: same":
        return 5, a
    return 4, a  # not checked, or the check failed


def _pieces(d: Path) -> tuple[list[dict[str, Any]], int, int]:
    fin = _read(d / "finished.json")
    pieces = fin.get("pieces") or []
    vents = sum(int(p.get("quantity") or 0) for p in pieces if p.get("name") == "vent-hood")
    count = sum(1 for p in pieces if not str(p.get("name", "")).startswith("vent-"))
    return pieces, count, vents


def _code(d: Path) -> str:
    st = _read(d / "desk.json")
    c = check(d)
    return str(st.get("code") or c.get("code") or d.name.removeprefix("drawing-").upper())


def brief(d: Path) -> dict[str, Any]:
    st = state(d)
    c = check(d)
    sc = scores(c)
    _, count, vents = _pieces(d)
    cover = _read(d / "cover.json")
    last = st["history"][-1] if st["history"] else None
    return {
        "id": d.name,
        "code": _code(d),
        "drawing": d.name.startswith("drawing-"),
        "status": st["status"],
        "outcome": c.get("outcome"),
        "scores": sc,
        "tags": cover.get("tags") or [],
        "catalogue": cover.get("status", "draft"),
        "pieces": count,
        "vents": vents,
        "has_picture": (d / "cover.png").is_file(),
        "last": last and {k: last.get(k) for k in ("action", "by", "time")},
        "priority": list(priority(st["status"], c.get("outcome"), sc["avg"])),
        "updated": (d / "cover.png").stat().st_mtime if (d / "cover.png").is_file() else None,
    }


# ---- permissions ----------------------------------------------------------------------------


def approver(user: Any, params: Any) -> bool:
    if user.may("admin"):
        return True
    names = {n.strip().lower() for n in str(params["desk.approvers"]).split(",") if n.strip()}
    first = (user.name or "").strip().split(" ")[0].lower()
    return user.active and (user.username.lower() in names or first in names)


def dxf_allowed(d: Path, params: Any) -> bool:
    if not bool(params["desk.require_approval_for_dxf"]):
        return True
    if str(params["desk.gate_scope"]) != "all" and not d.name.startswith("drawing-"):
        return True
    st = state(d)
    if d.name.startswith("drawing-") or (d / "desk.json").is_file():
        return st["status"] in ("approved", "produced")
    return _read(d / "cover.json").get("status") in ("checked", "production")


# ---- the drawing ----------------------------------------------------------------------------


def drawing_pdf(d: Path, data_dir: Path) -> Path | None:
    if (d / "reference.pdf").is_file():
        return d / "reference.pdf"
    st = _read(d / "desk.json")
    if st.get("pdf"):
        given = Path(str(st["pdf"]))
        given = given if given.is_absolute() else data_dir / given
        if given.is_file():
            return given
    code = _code(d)
    hits = sorted((data_dir / "uploads").glob(f"*/* - {code}.pdf"))
    return hits[0] if hits else None


def drawing_page(d: Path, data_dir: Path, page: int) -> Path:
    """One page of the drawing as a PNG, made once and kept in desk-cache/."""
    import pymupdf

    pdf = drawing_pdf(d, data_dir)
    if pdf is None:
        raise HTTPException(404, "no drawing for this cover")
    cache = d / "desk-cache"
    out = cache / f"page-{page}.png"
    if out.is_file() and out.stat().st_mtime >= pdf.stat().st_mtime:
        return out
    doc = pymupdf.open(pdf)
    if not 0 <= page < min(doc.page_count, MAX_PAGES):
        raise HTTPException(404, "no such page")
    cache.mkdir(exist_ok=True)
    doc[page].get_pixmap(dpi=PAGE_DPI).save(out)
    return out


# ---- actions --------------------------------------------------------------------------------


def apply(d: Path, a: Action, user: Any, learning: Path) -> dict[str, Any]:
    from coverengine.catalogue import revisions, set_info

    with _lock:
        st = state(d)
        before = {k: v for k, v in st.items() if k != "history"}
        now = time.time()
        who = user.name or user.username
        entry: dict[str, Any] = {"action": a.action, "by": who, "time": now}
        if a.action == "approve":
            st["status"] = "approved"
            st["approved"] = {"by": who, "time": now}
            st.pop("rejected", None)
        elif a.action == "reject":
            bad = [r for r in a.reasons if r not in REASONS]
            if bad or not (a.reasons or a.text.strip()):
                raise HTTPException(400, f"give a reason ({', '.join(REASONS)}) or a few words")
            st["status"] = "rejected"
            st["rejected"] = {"by": who, "time": now, "reasons": a.reasons, "text": a.text}
            st.pop("approved", None)
            st.pop("produced", None)
            entry |= {"reasons": a.reasons, "text": a.text}
        elif a.action == "produced":
            if a.done and st["status"] not in ("approved", "produced"):
                raise HTTPException(409, "approve the cover before marking it produced")
            if a.done:
                st["status"] = "produced"
                st["produced"] = {"by": who, "time": now}
            else:
                st["status"] = "approved"
                st.pop("produced", None)
            entry["done"] = a.done
        elif a.action == "fit":
            st["fit"] = {"fits": a.fits, "note": a.note, "by": who, "time": now}
            entry |= {"fits": a.fits, "note": a.note}
        elif a.action == "prefer":
            numbers = [r["number"] for r in revisions(d)]
            if a.n not in numbers:
                raise HTTPException(404, f"no revision {a.n}")
            # TODO(ADR-079): a revision keeps only its cut files, not the 3D; "prefer" marks
            # which one the workshop cuts (its DXF), it does not restore the 3D
            st["preferred_revision"] = a.n
            entry["n"] = a.n
        elif a.action == "undo":
            # the last action not yet undone (an undo itself is not undone: undo twice goes
            # two steps back)
            hist = st["history"]
            i = next((k for k in range(len(hist) - 1, -1, -1)
                      if "before" in hist[k] and not hist[k].get("undone")), None)  # fmt: skip
            if i is None:
                raise HTTPException(409, "nothing to undo")
            hist[i]["undone"] = True
            st = {**hist[i]["before"], "history": hist}
            entry = {"action": "undo", "by": who, "time": now, "undid": hist[i].get("action")}
            st["history"].append(entry)
            _write(d / "desk.json", st)
            _catalogue(d, st["status"], set_info)
            _log(learning, d, entry)
            return state(d)
        else:
            raise HTTPException(400, f"unknown action {a.action!r}")
        entry["before"] = before
        st["history"].append(entry)
        _write(d / "desk.json", st)
        if a.action in ("approve", "reject", "produced"):
            _catalogue(d, st["status"], set_info)
        if a.action == "reject" and a.text.strip():
            _lesson(learning, d, a, who, now)
        _log(learning, d, entry)
    return state(d)


def _catalogue(d: Path, status: str, set_info: Any) -> None:
    target = CATALOGUE.get(status, "draft")
    try:
        set_info(d, {"status": target})
    except Exception:  # noqa: BLE001 - the desk's own state is what counts
        pass


def _log(learning: Path, d: Path, entry: dict[str, Any]) -> None:
    learning.mkdir(parents=True, exist_ok=True)
    row = {"model": d.name, **{k: v for k, v in entry.items() if k != "before"}}
    with (learning / "desk.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _lesson(learning: Path, d: Path, a: Action, who: str, now: float) -> None:
    """A reject in words is a lesson for every later AI prompt (ADR-055, ADR-070)."""
    path = learning / "lessons.json"
    kept = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    lesson = {"rule": a.text.strip(), "check": ", ".join(a.reasons) or "desk",
              "applies_to": "drawing covers", "model_id": d.name, "from": "desk",
              "accepted_by": who, "time": now}  # fmt: skip
    if not any(k.get("rule") == lesson["rule"] for k in kept):
        kept.append(lesson)
        learning.mkdir(parents=True, exist_ok=True)
        _write(path, kept)


# ---- the routes -----------------------------------------------------------------------------


def install(app: FastAPI, store: Any) -> None:
    from coverengine.params import Registry

    from coverapi.security import current_user

    learning = store.root / "learning"

    def folder(model_id: str) -> Path:
        try:
            d = Path(store.model_dir(model_id))
        except KeyError:
            raise HTTPException(404, f"no model {model_id!r}") from None
        if not d.is_dir():
            raise HTTPException(404, f"no model {model_id!r}")
        return d

    @app.get("/api/desk")
    def queue(request: Request, scope: str = "drawings") -> dict[str, Any]:
        user = current_user(request)
        params = Registry.load(None).resolve()
        dirs = sorted(p for p in Path(store.models).iterdir() if (p / "cover.json").is_file())
        if scope != "all":
            dirs = [p for p in dirs if p.name.startswith("drawing-")]
        items = sorted((brief(p) for p in dirs), key=lambda b: (b["priority"], b["code"]))
        counts = {s: sum(1 for i in items if i["status"] == s) for s in STATUSES}
        avgs = [i["scores"]["avg"] for i in items if i["scores"]["avg"] is not None]
        from coverengine import spend

        try:
            money = spend.status(params)
        except Exception:  # noqa: BLE001
            money = None
        return {
            "items": items,
            "counts": counts,
            "avg_score": round(sum(avgs) / len(avgs), 1) if avgs else None,
            "spend": money,
            "can_approve": approver(user, params),
            "reasons": list(REASONS),
        }

    @app.get("/api/desk/{model_id}")
    def card(model_id: str, request: Request) -> dict[str, Any]:
        from coverengine.catalogue import revisions

        current_user(request)
        d = folder(model_id)
        pieces, count, vents = _pieces(d)
        pdf = drawing_pdf(d, store.root)
        pages = 0
        if pdf is not None:
            import pymupdf

            pages = min(pymupdf.open(pdf).page_count, MAX_PAGES)
        st = state(d)
        st["history"] = [{k: v for k, v in h.items() if k != "before"} for h in st["history"]]
        return {
            **brief(d),
            "desk": st,
            "check": check(d),
            "read": _read(d / "drawing_features.json"),
            "notes": _read(d / "cover.json").get("notes", ""),
            "pieces_list": [
                {k: p.get(k) for k in ("name", "quantity", "size_mm", "area_m2")} for p in pieces
            ],  # fmt: skip
            "revisions": revisions(d),
            "pages": pages,
            "dxf_ok": dxf_allowed(d, Registry.load(None).resolve()),
        }

    @app.get("/api/desk/{model_id}/page/{page}")
    def page(model_id: str, page: int, request: Request) -> FileResponse:
        current_user(request)
        return FileResponse(
            drawing_page(folder(model_id), store.root, page), media_type="image/png"
        )

    @app.post("/api/desk/{model_id}")
    def act(model_id: str, a: Action, request: Request) -> dict[str, Any]:
        user = current_user(request)
        params = Registry.load(None).resolve()
        if not approver(user, params):
            raise HTTPException(403, "only Rens, Rick, Wouter (desk.approvers) or an admin")
        return apply(folder(model_id), a, user, learning)


def gate(d: Path, model_id: str, request: Request) -> None:
    """The cutting table's DXF only for an approved cover (ADR-079); an admin may override
    with ?override=1, which the desk's history keeps."""
    from coverengine.params import Registry

    from coverapi.security import current_user

    params = Registry.load(None).resolve()
    if dxf_allowed(d, params):
        return
    user = current_user(request)
    if request.query_params.get("override") == "1" and user.may("admin"):
        with _lock:
            st = state(d)
            before = {k: v for k, v in st.items() if k != "history"}
            st["history"].append({"action": "dxf override", "by": user.name or user.username,
                                  "time": time.time(), "before": before})  # fmt: skip
            _write(d / "desk.json", st)
        return
    raise HTTPException(403, "this cover is not approved yet: approve it on the Desk first")
