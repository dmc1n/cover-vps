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
produced -> "production", rejected -> "draft". Every action is logged in learning/desk.jsonl.

Corrections (ADR-082) change the cover itself, not an AI prompt: a seam removed or added (piece
edits the cut reads), a vent count or height, a skirt seam height (parameter overrides in the
cover's own settings), a size read wrong, a shape that is missing. Each is kept as a test case,
and the same parameter correction on `desk.learn_after` covers of a group is proposed as the
group's rule (coverengine/learned.py). A reject's words are no longer an AI lesson.

Pictures (ADR-096): an approver attaches pictures to a reject, a comment, a fit note or a
correction (a snapshot of the 3D view or the drawing, a file, a paste), marked with red arrows,
circles and lines in the browser. They are uploaded first (`POST /api/desk/{id}/pictures`),
checked and re-encoded as PNG without metadata into the model's desk/ folder, and then named in
the action; the history entry, learning/desk.jsonl and a correction's test case carry them.
"""

from __future__ import annotations

import io
import json
import re
import threading
import time
import warnings
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from coverapi.products_sheet import product_labels, products_card

STATUSES = ("new", "ai-checked", "rejected", "approved", "produced")
CATALOGUE = {"approved": "checked", "produced": "production", "rejected": "draft"}
REASONS = ("shape", "size", "seams", "vents", "pieces", "other")
PAGE_DPI = 110  # param-ok: a drawing page as a picture on the desk
MAX_PAGES = 4  # param-ok
LOW = 60.0  # param-ok: below this average the AIs found the cover poor
PICTURES_DIR = "desk"  # the Desk's pictures, in the model's folder (ADR-096)
PICTURE_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9]{1,4}\.png$")
PICTURE_FORMATS = ("JPEG", "PNG", "WEBP")
WITH_PICTURES = ("reject", "note", "fit")
MB = 1024 * 1024  # param-ok: bytes in a megabyte
_lock = threading.Lock()


class Action(BaseModel):
    action: str  # approve | reject | note | produced | fit | prefer | undo
    reasons: list[str] = []
    text: str = ""
    done: bool = True
    fits: bool = True
    note: str = ""
    n: int | None = None
    pictures: list[str] = []  # names returned by POST /api/desk/{id}/pictures (ADR-096)
    # with a fit: what was measured on the sewn cover, mm per check-list key (ADR-110)
    measured: dict[str, float] = {}


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
    if st.get("code") or c.get("code"):
        return str(st.get("code") or c.get("code"))
    if d.name.startswith("drawing-"):
        return d.name.removeprefix("drawing-").upper()
    # a catalogue model (SUNS): its own name, as its notes carry it ("…: SUNS-Chaise lounge-…")
    notes = str(_read(d / "cover.json").get("notes") or "")
    name = notes.rsplit(": ", 1)[-1] if ": " in notes else d.name
    return re.sub(r"\s+", " ", name.replace("-", " ").replace("_", " ")).strip()[:80]


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
        "products": product_labels(d),  # the workshop's product list (ADR-091)
        "has_picture": (d / "cover.png").is_file(),
        "last": last and {k: last.get(k) for k in ("action", "by", "time")},
        # reopened after a fix, for a person to look again (owner, 7 Oct 2026)
        "second_round": (st.get("second_round") or {}).get("why")
        if st["status"] not in ("approved", "produced", "rejected")
        else None,
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


# ---- pictures (ADR-096) ---------------------------------------------------------------------


def _settings() -> Any:
    from coverengine.params import Registry

    return Registry.load(None).resolve()


def picture_file(d: Path, name: str) -> Path | None:
    """A Desk picture of this model by its name, or None: only names the Desk made itself, so
    no path can lead out of the model's desk/ folder."""
    if not PICTURE_RE.match(name):
        return None
    path = d / PICTURES_DIR / name
    return path if path.is_file() else None


def save_picture(d: Path, data: bytes, params: Any) -> str:
    """Check an uploaded picture with Pillow and keep it as a fresh PNG without metadata."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    most = float(params["desk.picture_max_mb"])
    if len(data) > most * MB:
        raise HTTPException(413, f"a picture may be at most {most:g} MB")
    try:
        with warnings.catch_warnings():
            # a picture that unpacks to an enormous size is refused, not only warned about
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                fmt = probe.format
                probe.verify()
            img = Image.open(io.BytesIO(data))
            img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):  # fmt: skip
        raise HTTPException(400, "not a picture: use JPG, PNG or WebP") from None
    if fmt not in PICTURE_FORMATS:
        raise HTTPException(400, "not a picture: use JPG, PNG or WebP")
    upright = ImageOps.exif_transpose(img)  # a phone photo the right way up; its EXIF goes
    alpha = upright.mode in ("RGBA", "LA", "PA") or "transparency" in upright.info
    clean = upright.convert("RGBA" if alpha else "RGB")
    clean.info = {}  # no EXIF, text chunks, ICC or comments are written into the PNG
    side = int(params["desk.picture_max_side_px"])
    clean.thumbnail((side, side))
    folder = d / PICTURES_DIR
    folder.mkdir(exist_ok=True)
    with _lock:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        n = 1
        while (folder / f"{stamp}-{n}.png").exists():
            n += 1
        name = f"{stamp}-{n}.png"
        clean.save(folder / name, "PNG")
    return name


def check_pictures(d: Path, names: list[str], params: Any) -> list[str]:
    """The pictures an action names: uploaded for this model, not too many."""
    names = list(dict.fromkeys(names))
    most = int(params["desk.pictures_max"])
    if len(names) > most:
        raise HTTPException(400, f"at most {most} pictures")
    missing = [n for n in names if picture_file(d, n) is None]
    if missing:
        raise HTTPException(400, f"no such picture: {', '.join(missing)[:200]}")
    return names


def picture_paths(d: Path, names: list[str], base: Path) -> list[str]:
    """Where the pictures are, relative to the data folder: for the learning step to look."""
    out = []
    for n in names:
        p = d / PICTURES_DIR / n
        try:
            out.append(str(p.relative_to(base)))
        except ValueError:
            out.append(str(p))
    return out


# ---- actions --------------------------------------------------------------------------------


def apply(d: Path, a: Action, user: Any, learning: Path) -> dict[str, Any]:
    from coverengine.catalogue import revisions, set_info

    pictures: list[str] = []
    if a.pictures:
        if a.action not in WITH_PICTURES:
            raise HTTPException(400, f"pictures go with {', '.join(WITH_PICTURES)}")
        pictures = check_pictures(d, a.pictures, _settings())
    # outside the lock: the check list's points take a moment
    rows = measured_rows(d, a.measured) if a.action == "fit" and a.measured else []
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
        elif a.action == "note":
            # a comment: only the history changes (ADR-096)
            if not (a.text.strip() or pictures):
                raise HTTPException(400, "write a few words or add a picture")
            entry["text"] = a.text
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
            if rows:  # measured against the check list: the differences are kept
                st["fit"]["measured"] = rows
                entry["measured"] = rows
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
        if pictures:
            entry["pictures"] = pictures
        entry["before"] = before
        st["history"].append(entry)
        _write(d / "desk.json", st)
        if a.action in ("approve", "reject", "produced"):
            _catalogue(d, st["status"], set_info)
        _log(learning, d, entry)
    return state(d)


def measured_rows(d: Path, measured: dict[str, float]) -> list[dict[str, Any]]:
    """Measured values (mm) against the check list's points (ADR-110): expected, measured and
    the difference per key, for the learning step to find systematic deviations."""
    from coverengine.measure import check_points, deviations

    if not (d / "pattern.json").is_file() or not (d / "panels.npz").is_file():
        raise HTTPException(409, "no calculated cover to measure against")
    rows = deviations(check_points(d)["points"], measured)
    if not rows:
        raise HTTPException(400, "none of the measured values belongs to the check list")
    return rows


def _catalogue(d: Path, status: str, set_info: Any) -> None:
    target = CATALOGUE.get(status, "draft")
    try:
        set_info(d, {"status": target})
    except Exception:  # noqa: BLE001 - the desk's own state is what counts
        pass


def _log(learning: Path, d: Path, entry: dict[str, Any]) -> None:
    learning.mkdir(parents=True, exist_ok=True)
    row = {"model": d.name, **{k: v for k, v in entry.items() if k != "before"}}
    if entry.get("pictures") and "picture_paths" not in row:  # for the learning step (ADR-096)
        row["picture_paths"] = picture_paths(d, entry["pictures"], learning.parent)
    with (learning / "desk.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


# ---- corrections that change the cover (ADR-082) --------------------------------------------

SHAPES = ("round front", "back profile missing", "taper missing", "wrong height", "mirrored",
          "other")  # fmt: skip
CM_TO_MM = 10.0  # param-ok: cm to mm


class Feedback(BaseModel):
    kind: str  # seam | size | vents | shape
    op: str = ""  # seam: remove | add | skirt
    seam: str = ""  # seam remove: its id in panels.json ("top-1/top-2")
    piece: str = ""  # seam add: the piece to split
    axis: str = "z"  # seam add: z (a height) | x (along the width) | y (front to back)
    at_cm: float | None = None  # seam add: where; skirt: the height above the hem
    what: str = ""  # size: which size
    read_cm: float | None = None
    correct_cm: float | None = None
    count: int | None = None  # vents
    above_hem_cm: float | None = None  # vents
    chips: list[str] = []
    text: str = ""
    pictures: list[str] = []  # names returned by POST /api/desk/{id}/pictures (ADR-096)


class RuleRequest(BaseModel):
    group: str
    key: str
    value: Any


def first_steps(key: str) -> list[str]:
    """The steps a changed parameter needs (the server decides, not the browser)."""
    group = key.split(".", 1)[0]
    if group == "hull":
        return ["hull", "cut", "flatten", "export"]
    if group in ("seams", "roll"):
        return ["cut", "flatten", "export"]
    if group in ("flatten", "fabric"):
        return ["flatten", "export"]
    return ["export"]


def _set_params(d: Path, params: dict[str, Any]) -> None:
    from coverengine import learned

    doc = _read(d / "cover.json")
    tree = doc.setdefault("parameters", {})
    for key, value in params.items():
        learned.set_dotted(tree, key, value)
    _write(d / "cover.json", doc)


def seams_of(d: Path) -> list[dict[str, Any]]:
    from coverengine import learned

    return learned.seam_points(d)


def pieces_of(d: Path) -> list[dict[str, Any]]:
    from coverengine import learned

    return learned.piece_points(d)


def _drawn(d: Path) -> bool:
    from coverengine import learned

    return learned.editable(d)


def correct(d: Path, fb: Feedback, user: Any, base: Path) -> dict[str, Any]:
    """One correction: what it changes, the test case it leaves, the steps to recalculate."""
    from coverengine import learned
    from coverengine.params import resolve_model

    who = user.name or user.username
    now = time.time()
    params: dict[str, Any] = {}
    edit: dict[str, Any] | None = None
    expect: dict[str, Any] = {}
    steps: list[str] = []
    pictures = check_pictures(d, fb.pictures, _settings()) if fb.pictures else []
    _, before_pieces, _ = _pieces(d)
    if fb.kind == "seam":
        if fb.op in ("remove", "add") and not _drawn(d):
            raise HTTPException(400, "this cover's seams follow the furniture: move its skirt "
                                "seam here, or place seams in the seam editor")  # fmt: skip
        if fb.op == "remove":
            hit = next((x for x in seams_of(d) if x["id"] == fb.seam), None)
            if hit is None or hit["at"] is None:
                raise HTTPException(404, f"no seam {fb.seam!r} on this cover")
            edit = {"op": "join", "at": hit["at"], "seam": fb.seam}
            expect = {"pieces_at_most": max(before_pieces - 1, 1), "no_seam_near": hit["at"]}
        elif fb.op == "add":
            pieces = pieces_of(d)
            piece = next((x for x in pieces if x["name"] == fb.piece), None)
            if piece is None or fb.at_cm is None or fb.axis not in ("x", "y", "z"):
                raise HTTPException(400, "give the piece, the direction (x, y, z) and where (cm)")
            i = "xyz".index(fb.axis)
            # z: a height above the hem (the cover's lowest point); x, y: from the piece's start
            lo = min(p["min"][2] for p in pieces) if fb.axis == "z" else piece["min"][i]
            edit = {"op": "split", "at": piece["at"], "axis": fb.axis,
                    "value_mm": round(lo + fb.at_cm * CM_TO_MM, 1), "piece": fb.piece}  # fmt: skip
            expect = {"pieces_at_least": before_pieces + 1}
        elif fb.op == "skirt":
            if fb.at_cm is None:
                raise HTTPException(400, "give the skirt seam's height above the hem (cm)")
            params["seams.skirt_height_mm"] = round(fb.at_cm * CM_TO_MM, 1)
        else:
            raise HTTPException(400, "seam: remove, add or skirt")
        steps = ["cut", "flatten", "export"]
    elif fb.kind == "vents":
        if fb.count is not None:
            params["features.vents_total"] = int(fb.count)
            expect["vents"] = int(fb.count)
        if fb.above_hem_cm is not None:
            params["features.vent_above_hem_mm"] = round(fb.above_hem_cm * CM_TO_MM, 1)
        if not params:
            raise HTTPException(400, "give the vent count or their height above the hem")
    elif fb.kind == "size":
        if fb.correct_cm is None:
            raise HTTPException(400, "give the right size (cm)")
        doc = _read(d / "drawing_corrections.json")
        doc.setdefault("sizes", []).append({"what": fb.what, "read_cm": fb.read_cm,
                                            "correct_cm": fb.correct_cm, "by": who,
                                            "time": now})  # fmt: skip
        _write(d / "drawing_corrections.json", doc)
    elif fb.kind == "shape":
        bad = [c for c in fb.chips if c not in SHAPES]
        if bad or not (fb.chips or fb.text.strip()):
            raise HTTPException(400, f"choose what is wrong ({', '.join(SHAPES)}) or a few words")
    else:
        raise HTTPException(400, "kind: seam, size, vents or shape")
    for key in params:
        if len(first_steps(key)) > len(steps):
            steps = first_steps(key)
    old_cover = _read(d / "cover.json")
    if params:
        _set_params(d, params)
        expect["params"] = params
        try:
            resolve_model(d)  # the settings must still resolve before a job is queued
        except Exception as exc:  # noqa: BLE001
            _write(d / "cover.json", old_cover)
            raise HTTPException(400, f"the correction makes the settings invalid: {exc}") from None
    if edit is not None:
        learned.add_edit(d, {**edit, "by": who, "time": now})
    entry = {"kind": fb.kind, "op": fb.op, "seam": fb.seam, "piece": fb.piece,
             "axis": fb.axis if fb.op == "add" else None, "at_cm": fb.at_cm, "what": fb.what,
             "read_cm": fb.read_cm, "correct_cm": fb.correct_cm, "count": fb.count,
             "above_hem_cm": fb.above_hem_cm, "chips": fb.chips, "text": fb.text,
             "params": params, "edit": edit, "by": who, "time": now,
             # the pictures, and where they are for a later fix to look at (ADR-096)
             "pictures": pictures, "picture_paths": picture_paths(d, pictures, base)}  # fmt: skip
    entry = {k: v for k, v in entry.items() if v not in (None, "", [], {})}
    with _lock:
        path = d / "feedback.json"
        kept = json.loads(path.read_text("utf-8")) if path.is_file() else []
        kept.append(entry)
        _write(path, kept)
        case = learned.write_case(d, {"feedback": entry, "expect": expect,
                                      "check": "auto" if expect else "manual"}, base)  # fmt: skip
        st = state(d)
        hist = {"action": f"correct {fb.kind}", "by": who, "time": now,
                "before": {k: v for k, v in st.items() if k != "history"},
                "detail": {k: v for k, v in entry.items()
                           if k not in ("by", "time", "pictures", "picture_paths")}}  # fmt: skip
        if pictures:
            hist["pictures"] = pictures
        if st["status"] in ("approved", "produced") and (params or edit):
            # the cover changes: the approval was for the one before
            st["status"] = "ai-checked"
            st.pop("approved", None)
            st.pop("produced", None)
        st["history"].append(hist)
        _write(d / "desk.json", st)
        _log(base / "learning", d, hist)
    return {"steps": steps, "case": case.name, "expect": expect, "entry": entry}


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
    def queue(request: Request, scope: str = "all") -> dict[str, Any]:
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
            "pictures_max": int(params["desk.pictures_max"]),  # type: ignore[arg-type]
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
            "product_list": products_card(d),
            "pages": pages,
            "dxf_ok": dxf_allowed(d, Registry.load(None).resolve()),
        }

    @app.get("/api/desk/{model_id}/page/{page}")
    def page(model_id: str, page: int, request: Request) -> FileResponse:
        current_user(request)
        return FileResponse(
            drawing_page(folder(model_id), store.root, page), media_type="image/png"
        )

    def submit(model_id: str, steps: list[str]) -> dict[str, Any] | None:
        jobs = getattr(app.state, "jobs", None)
        if jobs is None or not steps:
            return None
        from coverapi.jobs import JobSpec

        job: dict[str, Any] = jobs.submit(JobSpec(model_id, steps, {}))
        return job

    @app.post("/api/desk/{model_id}/pictures")
    async def pictures_upload(
        model_id: str,
        request: Request,
        files: list[UploadFile] = File(...),  # noqa: B008 - FastAPI's way
    ) -> dict[str, Any]:
        """Pictures for a reject, a comment or a correction, checked and kept as PNG
        (ADR-096). The action that follows names them."""
        user = current_user(request)
        params = Registry.load(None).resolve()
        if not approver(user, params):
            raise HTTPException(403, "only Rens, Rick, Wouter (desk.approvers) or an admin")
        d = folder(model_id)
        most = int(params["desk.pictures_max"])
        if not files or len(files) > most:
            raise HTTPException(400, f"send 1 to {most} pictures")
        limit = int(float(params["desk.picture_max_mb"]) * MB)
        datas = [await f.read(limit + 1) for f in files]  # one byte more shows "too big"
        return {"pictures": [save_picture(d, data, params) for data in datas]}

    @app.get("/api/desk/{model_id}/correct")
    def correct_view(model_id: str, request: Request) -> dict[str, Any]:
        """What can be corrected: seams, pieces, the sizes read, the vents, the history."""
        from coverengine.params import resolve_model

        current_user(request)
        d = folder(model_id)
        try:
            p = resolve_model(d)
            now = {k: p[k] for k in ("features.vents_total", "features.vent_above_hem_mm",
                                     "seams.skirt_height_mm")}  # fmt: skip
        except Exception:  # noqa: BLE001
            now = {}
        sizes: list[float] = []
        pdf = drawing_pdf(d, store.root)
        if pdf is not None:
            try:
                from coverengine.drawing_views import written_cm

                sizes = written_cm(pdf)
            except Exception:  # noqa: BLE001 - the list is a help, never a stop
                sizes = []
        _, count, vents = _pieces(d)
        fb = d / "feedback.json"
        return {
            "seams": seams_of(d),
            "pieces": pieces_of(d),
            "drawn": _drawn(d),
            "sizes_cm": sizes,
            "read": _read(d / "drawing_features.json"),
            "settings": now,
            "piece_count": count,
            "vents": vents,
            "shapes": list(SHAPES),
            "feedback": json.loads(fb.read_text("utf-8")) if fb.is_file() else [],
            "edits": _read(d / "part_edits.json").get("edits", []),
        }

    @app.post("/api/desk/{model_id}/correct")
    def correct_action(model_id: str, fb: Feedback, request: Request) -> dict[str, Any]:
        user = current_user(request)
        if not approver(user, Registry.load(None).resolve()):
            raise HTTPException(403, "only Rens, Rick, Wouter (desk.approvers) or an admin")
        out = correct(folder(model_id), fb, user, store.root)
        out["job"] = submit(model_id, out["steps"])
        return out

    @app.get("/api/desk-rules")
    def rules_view(request: Request) -> dict[str, Any]:
        """The groups' learned rules, and corrections made often enough to become one."""
        from coverengine import learned

        current_user(request)
        params = Registry.load(None).resolve()
        rdir = learned.rules_dir(store.root)
        groups = sorted(p.stem for p in rdir.glob("*.yaml")) if rdir and rdir.is_dir() else []
        shapes: dict[str, dict[str, int]] = {}
        models = Path(store.models)
        for d in sorted(p for p in models.iterdir() if (p / "feedback.json").is_file()):
            g = learned.group_of(d) or "other"
            for f in json.loads((d / "feedback.json").read_text("utf-8")):
                for c in f.get("chips") or []:
                    shapes.setdefault(g, {})[c] = shapes.setdefault(g, {}).get(c, 0) + 1
        after = int(params["desk.learn_after"])  # type: ignore[arg-type]
        tol = float(params["tolerance.cover_mm"])  # type: ignore[arg-type]
        return {
            "rules": {g: learned.rules(g, store.root) for g in groups},
            "proposals": learned.proposals(models, store.root, after),
            "shape_problems": shapes,
            "learn_after": after,
            # sewn covers measured against their check lists (ADR-110)
            "measured": learned.measured_deviations(models, tol, after),
        }

    @app.post("/api/desk-rules")
    def accept_rule(req: RuleRequest, request: Request) -> dict[str, Any]:
        """A person makes a repeated correction the rule for a group; its covers recalculate."""
        from coverengine import learned
        from coverengine.params import resolve_model

        user = current_user(request)
        params = Registry.load(None).resolve()
        if not approver(user, params):
            raise HTTPException(403, "only Rens, Rick, Wouter (desk.approvers) or an admin")
        if req.key not in params.keys():
            raise HTTPException(400, f"no setting {req.key!r}")
        who = user.name or user.username
        row = learned.write_rule(req.group, req.key, req.value, who,
                                 "made the rule at the Desk", store.root)  # fmt: skip
        models = Path(store.models)
        covers = [d for d in sorted(models.iterdir()) if (d / "cover.json").is_file()]
        members = [d for d in covers if learned.group_of(d) == req.group]
        jobs: list[Any] = []
        for d in members:
            try:
                resolve_model(d)
            except Exception:  # noqa: BLE001 - a cover that does not resolve is not run
                continue
            learned.write_case(d, {"feedback": {"kind": "rule", "group": req.group,
                                                "key": req.key, "value": req.value},
                                   "expect": {"params": {req.key: req.value}},
                                   "check": "auto"}, store.root)  # fmt: skip
            job = submit(d.name, first_steps(req.key))
            if job:
                jobs.append(job.get("id"))
        learning.mkdir(parents=True, exist_ok=True)
        with (learning / "desk.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"action": "rule", **row}) + "\n")
        return {"rule": row, "covers": [d.name for d in members], "jobs": jobs}

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
