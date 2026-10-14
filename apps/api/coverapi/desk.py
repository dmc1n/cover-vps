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

Arrangements (ADR-115): an `arr-*` model is approved here too. Its maker sends it to the Desk
(`sent`: who, when; status ai-checked, "ready for approval"); the approvers hear of it in their
daily digest. An approval records the cut file's fingerprint and the placement (members, places,
plan); a later change to either reopens it ("changed after approval", back to waiting), so an
approved arrangement never changes silently. Its cutting-table DXF waits for the approval
whatever `desk.gate_scope` says (`desk.gate_arrangements`).

One approval, every cover (ADR-128; owner, 13 Oct 2026, questions 83 and 84): the Desk's approval
is the only approval (the cover page's "definitive drawing" is retired; approval.py stamps the
PDFs on a Desk approval), and the cutting-table DXF of every cover waits for it
(`desk.gate_scope: all`): drawings, arrangements, SUNS and barbecue catalogue covers, shop orders.
Every approval records the cut file's fingerprint; a later change of the cut reopens it. A shop
order's cover is sent here as an *order* when someone in the studio sends the order to production
(shop.py): first in the queue, one click approves it (`order` in desk.json). The workshop login
(role "workshop") reads the Desk and adds fits, notes and pictures (`worker`); it never approves.

No cover (Rens, 9 Oct 2026, question 12): a model marked `"no_cover": true` in its cover.json is
kept but needs no cover, so it is not in the queue, an arrangement so marked is not announced,
and only a note or an undo is taken for it (`refuse_no_cover`).
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

from coverengine.catalogue import no_cover
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
_lock = threading.RLock()
ARRANGEMENT_PREFIX = "arr-"
ARRANGEMENT_JSON = "arrangement.json"  # as coverengine.arrange
WAITING = "ai-checked"  # an arrangement sent to the Desk: ready for approval (ADR-115)
DONE = ("approved", "produced")
NO_COVER_ACTIONS = ("note", "undo")  # all a model that needs no cover takes at the Desk
# a remark a person leaves (Rens, 14 Oct 2026: "is a cover not under 2nd round unchanged since
# my comment?") and who answers it: the studio's own actions (scripts/desk_open_remarks.py)
STUDIO_NAMES = ("Claude", "the studio")
REMARK_ACTIONS = ("reject", "comment", "note", "fit")


class Action(BaseModel):
    action: str  # approve | reject | note | produced | fit | prefer | undo
    reasons: list[str] = []
    text: str = ""
    done: bool = True
    fits: bool = True
    note: str = ""
    n: int | None = None
    pictures: list[str] = []  # names returned by POST /api/desk/{id}/pictures (ADR-096)
    # with a fit: what was measured on the sewn cover, mm per check-list key (ADR-111)
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
    with _lock:
        doc = _read(d / "desk.json")
        doc.setdefault("status", "new")
        doc.setdefault("history", [])
        if doc["status"] == "new" and (d / "check.json").is_file():
            doc["status"] = "ai-checked"
        if grandfather_fingerprint(d, doc):
            _write(d / "desk.json", doc)
        ok = doc.get("approved") or {}
        if (
            not is_arrangement(d)  # an arrangement: reopen_if_changed (its placement too)
            and doc["status"] in DONE
            and (ok.get("cut") or cut_newer(d, ok))
            and _changed_since_approval(d, doc)
        ):
            from coverengine.catalogue import set_info

            entry = _reopen(
                d,
                doc,
                "the studio",
                "changed after approval",
                "the cut file changed after the approval",
            )
            _write(d / "desk.json", doc)
            _catalogue(d, WAITING, set_info)
            _log(d.parent.parent / "learning", d, entry)
        return doc


def grandfather_fingerprint(d: Path, doc: dict[str, Any]) -> bool:
    """Amend an earlier approval made without a cut fingerprint once (ADR-120; every cover since
    ADR-128, when the gate covers them all); caller holds _lock and saves the document. An
    arrangement's approval always recorded its cut, so it is never amended here."""
    if is_arrangement(d) or doc.get("status") not in DONE:
        return False
    approved = doc.get("approved") or {}
    if approved.get("cut") or not (cut := cut_fingerprint(d)):
        return False
    if cut_newer(d, approved):
        return False  # written after that approval: not the file it was for (state reopens it)
    doc["approved"] = {**approved, "cut": cut}
    doc["approved_fingerprints"] = list(dict.fromkeys([*doc.get("approved_fingerprints", []), cut]))
    doc.setdefault("history", []).append(
        {
            "action": "fingerprint recorded",
            "by": "the studio",
            "time": time.time(),
            "text": "fingerprint recorded for an earlier approval",
            "cut": cut,
        }
    )
    return True


def cut_newer(d: Path, approved: dict[str, Any]) -> bool:
    """The cut file was written after an approval that recorded no fingerprint (ADR-128): a
    grandfathered approval would bless a file nobody looked at."""
    when = approved.get("time")
    cut = d / "cut.dxf"
    if not isinstance(when, int | float) or not cut.is_file():
        return False
    return cut.stat().st_mtime > float(when) + 1.0  # param-ok: a second of clock slack


def check(d: Path) -> dict[str, Any]:
    return _read(d / "check.json")


def scores(c: dict[str, Any]) -> dict[str, float | None]:
    g = c.get("gemini_second") or c.get("gemini") or {}
    s = c.get("deepseek") or {}
    gs = g.get("score") if isinstance(g.get("score"), int | float) else None
    ds = s.get("score") if isinstance(s.get("score"), int | float) else None
    vals = [x for x in (gs, ds) if x is not None]
    return {"gemini": gs, "deepseek": ds, "avg": sum(vals) / len(vals) if vals else None}


def priority(
    status: str, outcome: str | None, avg: float | None, order: bool = False
) -> tuple[int, float]:
    """The queue's order: a shop order waiting for its quick approval first (ADR-128), then the
    AIs disagree, then poor, rejected and middling, then unchecked, then those the AIs found
    right, then approved and produced."""
    a = avg if avg is not None else 0.0
    if order and status not in (*DONE, "rejected"):
        return -1, a
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
    if is_arrangement(d):  # its own name, as made on the Arrangements page (ADR-115)
        name = str(_read(d / ARRANGEMENT_JSON).get("name") or "").strip()
        if name:
            return re.sub(r"\s+", " ", name)[:80]
    # a catalogue model (SUNS): its own name, as its notes carry it ("…: SUNS-Chaise lounge-…")
    notes = str(_read(d / "cover.json").get("notes") or "")
    name = notes.rsplit(": ", 1)[-1] if ": " in notes else d.name
    return re.sub(r"\s+", " ", name.replace("-", " ").replace("_", " ")).strip()[:80]


def remark_times(st: dict[str, Any]) -> tuple[float | None, float | None]:
    """(the last remark a person left that is not undone, the studio's last action): a remark
    newer than the studio's last action waits for us (desk_open_remarks.py, the same rule)."""
    hist = st.get("history") or []
    remark = max((float(h.get("time") or 0) for h in hist
                  if h.get("by") not in STUDIO_NAMES and h.get("action") in REMARK_ACTIONS
                  and not h.get("undone")), default=None)  # fmt: skip
    change = max(
        (float(h.get("time") or 0) for h in hist if h.get("by") in STUDIO_NAMES), default=None
    )
    return remark, change


def remark_open(st: dict[str, Any]) -> bool:
    remark, change = remark_times(st)
    return remark is not None and remark > (change or 0)


def _approval_holds(d: Path, st: dict[str, Any]) -> bool:
    """Approved (or produced) for the cutting file it has now: a second approval adds nothing."""
    return st["status"] in DONE and not _changed_since_approval(d, st)


def brief(d: Path) -> dict[str, Any]:
    st = state(d)
    c = check(d)
    sc = scores(c)
    _, count, vents = _pieces(d)
    cover = _read(d / "cover.json")
    last = st["history"][-1] if st["history"] else None
    order = waiting_order(st)
    remark, change = remark_times(st)
    return {
        "id": d.name,
        "code": _code(d),
        "drawing": d.name.startswith("drawing-"),
        "arrangement": is_arrangement(d),
        "sent": st.get("sent"),  # an arrangement sent to the Desk: who, when (ADR-115)
        "status": st["status"],
        "outcome": c.get("outcome"),
        "scores": sc,
        "tags": cover.get("tags") or [],
        "catalogue": cover.get("status", "draft"),
        "no_cover": no_cover(d),
        "pieces": count,
        "vents": vents,
        "products": product_labels(d),  # the workshop's product list (ADR-091)
        "has_picture": (d / "cover.png").is_file(),
        "last": last and {k: last.get(k) for k in ("action", "by", "time")},
        # reopened after a fix, for a person to look again (owner, 7 Oct 2026)
        "second_round": (st.get("second_round") or {}).get("why")
        if st["status"] not in ("approved", "produced", "rejected")
        else None,
        # the last remark a person left and the studio's last change: "Changed <date>" or
        # "Not changed yet", and the "Waiting for us" filter (Rens, 14 Oct 2026)
        "last_remark_time": remark,
        "last_change_time": change,
        "open_remark": remark is not None and remark > (change or 0),
        # a shop order's cover sent to production: first in the queue, approved with one
        # click (ADR-128); `built`: its cutting file exists, so the click can approve it
        "order": order and {k: order.get(k) for k in ("order", "b2b", "by", "time")},
        "built": (d / "cut.dxf").is_file(),
        "priority": list(priority(st["status"], c.get("outcome"), sc["avg"], bool(order))),
        "updated": (d / "cover.png").stat().st_mtime if (d / "cover.png").is_file() else None,
    }


# ---- permissions ----------------------------------------------------------------------------


WORKSHOP_ROLE = "workshop"  # as coverapi.auth.WORKSHOP
WORKER_ACTIONS = ("note", "fit")  # what the workshop login does at the Desk (ADR-128)


def approver(user: Any, params: Any) -> bool:
    """Approves, rejects, marks produced: an admin, a user marked *may approve*, or a name in
    `desk.approvers`. Never the workshop login, whatever its name or flag (ADR-128)."""
    if getattr(user, "role", None) == WORKSHOP_ROLE:
        return False
    if user.may("admin"):
        return True
    if user.may("approve"):  # the one approval: the flag that approved definitive drawings
        return True
    names = {n.strip().lower() for n in str(params["desk.approvers"]).split(",") if n.strip()}
    # the user name only (ADR-123): a display name is chosen freely, so "Rens Fake" is not Rens
    return bool(user.active and user.username.lower() in names)


def worker(user: Any, params: Any) -> bool:
    """Adds a fit (with what was measured), a comment and pictures on a Desk card: an approver,
    or the workshop login (ADR-128)."""
    if approver(user, params):
        return True
    return bool(user.active and getattr(user, "role", None) == WORKSHOP_ROLE)


def may_act(user: Any, params: Any, action: str) -> bool:
    return approver(user, params) or (action in WORKER_ACTIONS and worker(user, params))


def refuse_no_cover(d: Path, action: str) -> None:
    """A model that needs no cover is not approved, rejected or produced at the Desk."""
    if action not in NO_COVER_ACTIONS and no_cover(d):
        raise HTTPException(409, f"{d.name} needs no cover (not on the Desk): nothing to {action}")


def gated(d: Path, params: Any) -> bool:
    """Whether this cover's cutting-table DXF waits for a Desk approval: every cover with
    `desk.gate_scope: all` (the default since ADR-128), else drawings, and arrangements while
    `desk.gate_arrangements` is on (ADR-115)."""
    if not bool(params["desk.require_approval_for_dxf"]):
        return False
    if str(params["desk.gate_scope"]) == "all" or d.name.startswith("drawing-"):
        return True
    return is_arrangement(d) and bool(params["desk.gate_arrangements"])


def dxf_allowed(d: Path, params: Any, revision: Path | None = None, name: str = "cut.dxf") -> bool:
    """The cutting table's DXF: only for a cover the Desk approved for the cut file it has now
    (its fingerprint; an arrangement's placement too), or a kept revision whose cut file was
    approved at some time (ADR-079, 115, 120, 128). Never the catalogue status, which a person
    can set by hand. Another DXF (the flat pattern.dxf) only as the approval saw it: a flatten
    run after the approval rewrites it without touching cut.dxf (ADR-128)."""
    if not gated(d, params):
        return True
    st = state(d)
    if revision is not None:
        cut = cut_fingerprint(revision)
        return cut is not None and cut in st.get("approved_fingerprints", [])
    if st["status"] not in DONE or _changed_since_approval(d, st):
        return False
    if name == "cut.dxf":
        return True
    seen = (st.get("approved") or {}).get("pattern" if name == "pattern.dxf" else name)
    return seen is not None and seen == file_fingerprint(d / name)


def stamped_ok(d: Path, name: str) -> bool:
    """A stamped PDF (approved/<name>) is served while the Desk approval that stamped it holds:
    approved or produced, the same cut file, and this very file (ADR-128)."""
    st = state(d)
    ok = st.get("approved") or {}
    stamped = ok.get("stamped") or {}
    path = d / "approved" / name
    if st["status"] not in DONE or _changed_since_approval(d, st) or name not in stamped:
        return False
    import hashlib

    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()[:20] == stamped[name]


# ---- arrangements (ADR-115) -----------------------------------------------------------------


def is_arrangement(d: Path) -> bool:
    return d.name.startswith(ARRANGEMENT_PREFIX) and (d / ARRANGEMENT_JSON).is_file()


def file_fingerprint(f: Path) -> str | None:
    import hashlib

    return hashlib.sha256(f.read_bytes()).hexdigest()[:20] if f.is_file() else None


def cut_fingerprint(d: Path) -> str | None:
    """The cutting table's file as it is now: what a Desk approval is for."""
    return file_fingerprint(d / "cut.dxf")


def _placement(d: Path) -> dict[str, Any]:
    from coverengine.arrange import placement

    return placement(_read(d / ARRANGEMENT_JSON))


def _changed_since_approval(d: Path, st: dict[str, Any]) -> list[str]:
    """What changed in an approved arrangement since its approval: its cut file, its placement.
    A missing approved cut fingerprint always requires a fresh approval."""
    ok = st.get("approved") or {}
    out = []
    if not ok.get("cut") or ok["cut"] != cut_fingerprint(d):
        out.append("the cut file")
    if is_arrangement(d) and ok.get("placement") and ok["placement"] != _placement(d):
        out.append("the members or the plan")
    return out


def _reopen(d: Path, st: dict[str, Any], who: str, action: str, why: str) -> dict[str, Any]:
    """Back to waiting for approval and sent again, so the digest announces it again. The
    caller holds _lock and writes desk.json."""
    before = {k: v for k, v in st.items() if k != "history"}
    now = time.time()
    st["status"] = WAITING
    for k in ("approved", "produced", "rejected"):
        st.pop(k, None)
    st["sent"] = {"by": who, "time": now, "announced": None}
    entry = {"action": action, "by": who, "time": now, "text": why, "before": before}
    st["history"].append(entry)
    return entry


def reopen_if_changed(d: Path, learning: Path) -> dict[str, Any] | None:
    """An approved arrangement whose cut file or placement changed since (a rebuild from the
    model page, a correction, a member rebuilt) goes back to waiting, the reason in its
    history."""
    if not is_arrangement(d) or not (d / "desk.json").is_file():
        return None
    from coverengine.catalogue import set_info

    with _lock:
        st = state(d)
        if st["status"] not in DONE:
            return None
        what = _changed_since_approval(d, st)
        if not what:
            return None
        why = f"{' and '.join(what)} changed after the approval"
        entry = _reopen(d, st, "the studio", "changed after approval", why)
        _write(d / "desk.json", st)
        _catalogue(d, WAITING, set_info)
        _log(learning, d, entry)
    return entry


def send_arrangement(d: Path, user: Any, learning: Path, note: str = "") -> dict[str, Any]:
    """Its maker sends a built arrangement to the Desk: ready for approval."""
    if not is_arrangement(d):
        raise HTTPException(400, "not an arrangement")
    return send(d, user, learning, note)


def send(d: Path, user: Any, learning: Path, note: str = "") -> dict[str, Any]:
    """A built cover to the Desk: ready for approval (ai-checked, `sent`), so the approvers'
    digest names it. Already waiting: nothing changes; approved or produced: refused (a change
    reopens it by itself). Used for arrangements (ADR-115), "Ask for approval" on a cover and
    scripts/desk_gate_all.py (ADR-128)."""
    refuse_no_cover(d, "send")
    if not ((d / "finished.json").is_file() and (d / "cut.dxf").is_file()):
        raise HTTPException(409, "build the cover first, then send it to the Desk")
    who = user.name or user.username
    with _lock:
        st = state(d)
        if st["status"] in DONE:
            raise HTTPException(409, f"already {st['status']}: change it to send it again")
        if st["status"] == WAITING and st.get("sent"):
            return st  # already waiting: a second click changes nothing, no second mail
        before = {k: v for k, v in st.items() if k != "history"}
        now = time.time()
        st["status"] = WAITING
        st.pop("rejected", None)
        st["sent"] = {"by": who, "time": now, "announced": None}
        entry = {"action": "sent to the Desk", "by": who, "time": now, "before": before}
        if note:
            entry["text"] = note
        st["history"].append(entry)
        _write(d / "desk.json", st)
        _log(learning, d, entry)
    return state(d)


def waiting_order(st: dict[str, Any]) -> dict[str, Any] | None:
    """The shop order this cover was sent to production for, while it waits for its quick
    approval (ADR-128); None once approved, rejected or without an order."""
    order = st.get("order")
    if not isinstance(order, dict) or order.get("approved") or st["status"] in (*DONE, "rejected"):
        return None
    return order


def mark_order(d: Path, order: int, who: str, learning: Path, b2b: bool = False) -> dict[str, Any]:
    """A shop order's cover sent to production by someone in the studio (shop.py): on the Desk
    as an order, first in the queue, one click approves it. A cover the Desk already approved
    for its current cut stays approved (a catalogue cover cut again): only the order is noted."""
    with _lock:
        st = state(d)
        now = time.time()
        before = {k: v for k, v in st.items() if k != "history"}
        st["order"] = {"order": int(order), "b2b": bool(b2b), "by": who, "time": now}
        entry: dict[str, Any] = {"action": "order to production", "by": who, "time": now,
                                 "order": int(order), "before": before}  # fmt: skip
        if st["status"] in DONE and not _changed_since_approval(d, st):
            st["order"]["approved"] = now  # nothing to approve: its approval holds
        elif st["status"] != WAITING or not st.get("sent"):
            st["status"] = WAITING
            for k in ("approved", "produced", "rejected"):
                st.pop(k, None)
            st["sent"] = {"by": who, "time": now, "announced": None}
        st["history"].append(entry)
        _write(d / "desk.json", st)
        if st["status"] == WAITING:
            from coverengine.catalogue import set_info

            _catalogue(d, WAITING, set_info)
        _log(learning, d, entry)
    return st


def arrangement_changed(
    d: Path, what: list[str], user: Any, learning: Path
) -> dict[str, Any] | None:
    """The arrangement changed and is built again (Arrangements page). Approved or rejected:
    back to waiting ("changed after approval" / "changed after rejection"); waiting: noted in
    its history; not sent yet: nothing. Never silent once it is at the Desk."""
    if not what or not (d / "desk.json").is_file():
        return None
    from coverengine.catalogue import set_info

    who = user.name or user.username
    why = f"changed: {', '.join(what)}"
    with _lock:
        st = state(d)
        if st["status"] in DONE:
            entry = _reopen(d, st, who, "changed after approval", why)
        elif st["status"] == "rejected":
            entry = _reopen(d, st, who, "changed after rejection", why)
        elif st["status"] == WAITING and st.get("sent"):
            before = {k: v for k, v in st.items() if k != "history"}
            entry = {"action": "changed while waiting", "by": who, "time": time.time(),
                     "text": why, "before": before}  # fmt: skip
            st["history"].append(entry)
        else:
            return None
        _write(d / "desk.json", st)
        _catalogue(d, st["status"], set_info)
        _log(learning, d, entry)
    return entry


def arrangements_to_announce(models: Path) -> list[dict[str, Any]]:
    """Arrangements sent to the Desk and not yet in the approvers' digest (ADR-115)."""
    out = []
    for d in sorted(models.glob(ARRANGEMENT_PREFIX + "*")):
        if not is_arrangement(d) or no_cover(d):
            continue
        st = state(d)
        sent = st.get("sent") or {}
        if st["status"] == WAITING and sent and not sent.get("announced"):
            again = any(str(h.get("action", "")).startswith("changed after")
                        for h in st["history"])  # fmt: skip
            out.append({"id": d.name, "code": _code(d), "by": sent.get("by"), "again": again})
    return out


def mark_announced(models: Path, ids: list[str], when: float) -> None:
    with _lock:
        for model_id in ids:
            d = models / model_id
            st = state(d)
            if st.get("sent") and not st["sent"].get("announced"):
                st["sent"]["announced"] = when
                _write(d / "desk.json", st)


def arrangement_card(d: Path, models: Path) -> dict[str, Any]:
    """The arrangement on the Desk's card: its members with their places, and the plan."""
    from coverengine.arrange import plan_view, stale
    from coverengine.errors import CoverError

    doc = _read(d / ARRANGEMENT_JSON)
    try:
        view: dict[str, Any] | None = plan_view(doc, _settings())
    except (CoverError, KeyError, ValueError, TypeError):
        view = None  # an old or broken arrangement.json: the card shows the members only
    try:
        changed = set(stale(models, doc))
    except (OSError, KeyError):
        changed = set()
    members = []
    for m in doc.get("members") or []:
        md = models / str(m.get("model_id"))
        members.append({
            "model_id": m.get("model_id"),
            "code": _code(md) if md.is_dir() else m.get("model_id"),
            "x_mm": m.get("x_mm"), "y_mm": m.get("y_mm"), "rot_deg": m.get("rot_deg"),
            "mirror": bool(m.get("mirror")),
            "size_mm": (m.get("version") or {}).get("size_mm"),
            "exists": md.is_dir(),
            "has_picture": (md / "cover.png").is_file(),
            "stale": m.get("model_id") in changed,
        })  # fmt: skip
    return {"name": doc.get("name"), "gap_mm": doc.get("gap_mm"), "size_mm": doc.get("size_mm"),
            "time": doc.get("time"), "members": members, "plan": view,
            "stale": sorted(changed)}  # fmt: skip


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
    from coverengine.safeimage import max_pixels, render_page

    p = doc[page]  # never more pixels than limits.image_max_mp (ADR-123)
    render_page(p, PAGE_DPI, max_pixels()).save(out)
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


def save_picture(d: Path, data: bytes, params: Any, sub: str = PICTURES_DIR) -> str:
    """Check an uploaded picture with Pillow and keep it as a fresh PNG without metadata, in
    `d/sub` (the model's desk/ folder; a question's own folder, ADR-109)."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    most = float(params["desk.picture_max_mb"])
    if len(data) > most * MB:
        raise HTTPException(413, f"a picture may be at most {most:g} MB")
    from coverengine.safeimage import TooLargeImage, max_pixels, open_image

    try:
        with warnings.catch_warnings():
            # a picture that unpacks to an enormous size is refused, not only warned about
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                fmt = probe.format
                probe.verify()
            # its size in pixels checked before decoding (limits.image_max_mp, ADR-123)
            img = open_image(data, max_pixels(params), int(params["desk.picture_max_side_px"]))
    except TooLargeImage as exc:
        raise HTTPException(413, str(exc)) from None
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
    folder = d / sub if sub else d
    folder.mkdir(parents=True, exist_ok=True)
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

    refuse_no_cover(d, a.action)
    pictures: list[str] = []
    if a.pictures:
        if a.action not in WITH_PICTURES:
            raise HTTPException(400, f"pictures go with {', '.join(WITH_PICTURES)}")
        pictures = check_pictures(d, a.pictures, _settings())
    # outside the lock: the check list's points take a moment
    rows = measured_rows(d, a.measured) if a.action == "fit" and a.measured else []
    who = user.name or user.username
    prepared: dict[str, Any] | None = None
    if a.action == "approve":
        # a second click while the first approval was still stamping (14 Oct 2026): said, not
        # stamped again
        _refuse_approved(d, state(d))
        # every cover: the approval is for its cutting file (ADR-120, ADR-128)
        cut_before = cut_fingerprint(d)
        if cut_before is None:
            raise HTTPException(
                400,
                "Build the arrangement's cutting file before approving it."
                if is_arrangement(d)
                else "Build the cover's cutting file before approving it.",
            )
        revs = revisions(d)
        revision = revs[-1]["number"] if revs else None
        from coverapi import approval

        try:  # the stamped PDFs, made outside the lock (a size drawing takes a moment)
            prepared = approval.prepare(d, who, time.time(), revision)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
    try:
        with _lock:
            st = state(d)
            before = {k: v for k, v in st.items() if k != "history"}
            now = time.time()
            entry: dict[str, Any] = {"action": a.action, "by": who, "time": now}
            if a.action == "approve":
                _refuse_approved(d, st)
                cut = cut_fingerprint(d)
                if cut != cut_before:
                    raise HTTPException(409, "the cutting file changed while approving: look again")
                st["status"] = "approved"
                st["approved"] = {"by": who, "time": now, "cut": cut, "revision": revision}
                if (pattern := file_fingerprint(d / "pattern.dxf")) is not None:
                    st["approved"]["pattern"] = pattern  # the flat DXF it saw (ADR-128)
                st["approved_fingerprints"] = list(
                    dict.fromkeys([*st.get("approved_fingerprints", []), cut])
                )
                if is_arrangement(d):  # what the approval is for (ADR-115)
                    st["approved"]["placement"] = _placement(d)
                if isinstance(st.get("order"), dict) and not st["order"].get("approved"):
                    st["order"]["approved"] = now  # the order's quick approval (ADR-128)
                    entry["order"] = st["order"].get("order")
                st.pop("rejected", None)
                assert prepared is not None
                from coverapi import approval

                st["approved"]["stamped"] = approval.commit(prepared)
                prepared = None
                entry["stamped"] = sorted(st["approved"]["stamped"])
                return _finish(d, a, st, before, entry, pictures, learning, set_info)
            return _act(d, a, st, before, entry, pictures, rows, learning, who, now)
    finally:
        if prepared is not None:
            from coverapi import approval

            approval.discard(prepared)


def _refuse_approved(d: Path, st: dict[str, Any]) -> None:
    if _approval_holds(d, st):
        ok = st.get("approved") or {}
        when = time.strftime("%d %b %H:%M", time.localtime(float(ok.get("time") or 0)))
        raise HTTPException(409, f"already approved by {ok.get('by', 'someone')} ({when}) for this "
                            "cutting file: nothing to approve again")  # fmt: skip


def _act(
    d: Path, a: Action, st: dict[str, Any], before: dict[str, Any], entry: dict[str, Any],
    pictures: list[str], rows: list[dict[str, Any]], learning: Path, who: str, now: float,
) -> dict[str, Any]:  # fmt: skip
    """Every action but an approval; the caller holds _lock."""
    from coverengine.catalogue import revisions, set_info

    if a.action == "reject":
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
        fingerprints = st.get("approved_fingerprints", [])
        st = {**hist[i]["before"], "history": hist}
        if fingerprints:
            st["approved_fingerprints"] = fingerprints
        entry = {"action": "undo", "by": who, "time": now, "undid": hist[i].get("action")}
        st["history"].append(entry)
        _write(d / "desk.json", st)
        _catalogue(d, st["status"], set_info)
        _log(learning, d, entry)
        return state(d)
    else:
        raise HTTPException(400, f"unknown action {a.action!r}")
    return _finish(d, a, st, before, entry, pictures, learning, set_info)


def _finish(
    d: Path, a: Action, st: dict[str, Any], before: dict[str, Any], entry: dict[str, Any],
    pictures: list[str], learning: Path, set_info: Any,
) -> dict[str, Any]:  # fmt: skip
    """Record the action in the history, the catalogue status and learning/desk.jsonl."""
    if pictures:
        entry["pictures"] = pictures
    entry["before"] = before
    st["history"].append(entry)
    _write(d / "desk.json", st)
    if a.action in ("approve", "reject", "produced"):
        _catalogue(d, st["status"], set_info)
    _log(learning, d, entry)
    return state(d)


# files the workshop works from, in this order (cut.dxf only when dxf_allowed says so)
WORKSHOP_FILES = ("cutting-list.pdf", "sizes.pdf", "checklist.pdf", "cut.svg", "cut.dxf")


def workshop_item(d: Path, params: Any) -> dict[str, Any] | None:
    """One approved or produced cover for Work → Workshop (ADR-124): what to cut and sew, and how
    it fitted. None for a cover the Desk has not approved. Read-only: the DXF's link is offered
    only when the approval gate (ADR-079/115/120) lets it through; the download itself is gated
    again by the server (`gate`)."""
    from coverengine.catalogue import REVISIONS, revisions

    st = state(d)
    if st["status"] not in DONE:
        return None
    files = {f for f in WORKSHOP_FILES if (d / f).is_file()}
    if (d / "pattern.json").is_file():
        files.add("sizes.pdf")  # made when it is opened (ADR-080)
        if (d / "finished.json").is_file():
            files.add("checklist.pdf")  # made when it is opened (ADR-111)
    dxf_ok = "cut.dxf" in files and dxf_allowed(d, params)
    preferred = st.get("preferred_revision")
    revision = None
    if preferred is not None and any(r["number"] == preferred for r in revisions(d)):
        folder = d / REVISIONS / f"{int(preferred):03d}"
        revision = {
            "n": int(preferred),
            "dxf": (folder / "cut.dxf").is_file(),
            "dxf_ok": (folder / "cut.dxf").is_file() and dxf_allowed(d, params, folder),
        }
    fit = st.get("fit")
    if fit:
        rows = fit.get("measured") or []
        worst = max(rows, key=lambda r: abs(float(r.get("diff_mm") or 0)), default=None)
        fit = {k: fit.get(k) for k in ("fits", "note", "by", "time")} | {
            "measured": len(rows),
            "worst": worst and {k: worst.get(k) for k in ("label", "diff_mm")},
        }
    approved = st.get("approved") or {}
    produced = st.get("produced") or {}
    _, count, vents = _pieces(d)
    return {
        "id": d.name,
        "code": _code(d),
        "drawing": d.name.startswith("drawing-"),
        "arrangement": is_arrangement(d),
        "status": st["status"],
        "approved": {k: approved.get(k) for k in ("by", "time")} if approved else None,
        "produced": {k: produced.get(k) for k in ("by", "time")} if produced else None,
        "since": produced.get("time") or approved.get("time"),
        "files": sorted(files - {"cut.dxf"}) + (["cut.dxf"] if "cut.dxf" in files else []),
        "dxf_ok": dxf_ok,
        # the PDFs stamped by the Desk's approval, while it holds (ADR-128)
        "stamped": [f for f in ("sizes.pdf", "cutting-list.pdf") if stamped_ok(d, f)],
        "revision": revision,
        "fit": fit,
        "pieces": count,
        "vents": vents,
        "products": product_labels(d),
        "has_picture": (d / "cover.png").is_file(),
    }


def measured_rows(d: Path, measured: dict[str, float]) -> list[dict[str, Any]]:
    """Measured values (mm) against the check list's points (ADR-111): expected, measured and
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
        dirs = sorted(p for p in Path(store.models).iterdir()
                      if (p / "cover.json").is_file() and not no_cover(p))  # fmt: skip
        if scope == "arrangements":
            dirs = [p for p in dirs if is_arrangement(p)]
        elif scope != "all":
            dirs = [p for p in dirs if p.name.startswith("drawing-")]
        for p in dirs:
            reopen_if_changed(p, learning)  # an approved arrangement never changes silently
        items = sorted((brief(p) for p in dirs), key=lambda b: (b["priority"], b["code"]))
        counts = {s: sum(1 for i in items if i["status"] == s) for s in STATUSES}
        avgs = [i["scores"]["avg"] for i in items if i["scores"]["avg"] is not None]
        from coverengine import spend

        try:
            money = spend.status(params) if user.may("edit") else None  # no money to others
        except Exception:  # noqa: BLE001
            money = None
        return {
            "items": items,
            "counts": counts,
            "avg_score": round(sum(avgs) / len(avgs), 1) if avgs else None,
            "spend": money,
            "can_approve": approver(user, params),
            # the workshop login: a fit, a comment, pictures; never approve (ADR-128)
            "can_note": worker(user, params),
            "reasons": list(REASONS),
            "pictures_max": int(params["desk.pictures_max"]),  # type: ignore[arg-type]
        }

    @app.get("/api/workshop")
    def workshop_list(request: Request) -> dict[str, Any]:
        """Work → Workshop (ADR-124, ADR-128): the approved covers, and the shop's orders that
        wait for production or are in it (without prices: the workshop login sees this page).
        Changes nothing; the DXF stays behind the approval gate; "Send to production" is the
        shop's route (POST /api/admin/orders/{id}/produce, editors and admins)."""
        user = current_user(request)
        params = Registry.load(None).resolve()
        dirs = sorted(p for p in Path(store.models).iterdir()
                      if (p / "cover.json").is_file() and not no_cover(p))  # fmt: skip
        items = [w for w in (workshop_item(p, params) for p in dirs) if w is not None]
        items.sort(key=lambda w: -float(w["since"] or 0))
        orders_of = getattr(app.state, "workshop_orders", None)
        orders = orders_of() if orders_of else []
        for o in orders:  # the order's cover at the Desk: waiting, approved, its DXF
            md = Path(store.models) / str(o.get("model_id") or "")
            if o.get("model_id") and md.is_dir():
                o["desk_status"] = state(md)["status"]
                o["dxf_ok"] = (md / "cut.dxf").is_file() and dxf_allowed(md, params)
        return {"items": items, "gate": bool(params["desk.require_approval_for_dxf"]),
                "orders": orders, "can_produce": user.may("edit")}  # fmt: skip

    @app.get("/api/desk/{model_id}")
    def card(model_id: str, request: Request) -> dict[str, Any]:
        from coverengine.catalogue import revisions

        current_user(request)
        d = folder(model_id)
        reopen_if_changed(d, learning)
        pieces, count, vents = _pieces(d)
        pdf = drawing_pdf(d, store.root)
        pages = 0
        if pdf is not None:
            import pymupdf

            pages = min(pymupdf.open(pdf).page_count, MAX_PAGES)
        st = state(d)
        # what an undo can take back (the button and the key follow it, never a silent 409)
        can_undo = any("before" in h and not h.get("undone") for h in st["history"])
        st["history"] = [{k: v for k, v in h.items() if k != "before"} for h in st["history"]]
        return {
            **brief(d),
            "desk": st,
            "can_undo": can_undo,
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
            # the members, their places and the plan (ADR-115)
            "arrangement_info": arrangement_card(d, Path(store.models))
            if is_arrangement(d)
            else None,
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
        if not worker(user, params):
            raise HTTPException(403, "only the approvers, the workshop or an admin")
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
        refuse_no_cover(folder(model_id), "correct")
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
            # sewn covers measured against their check lists (ADR-111)
            "measured": learned.measured_deviations(models, tol, after),
        }

    @app.post("/api/desk-rules")
    def accept_rule(req: RuleRequest, request: Request) -> dict[str, Any]:
        """A person makes a repeated correction the rule for a group; its covers recalculate."""
        from coverengine import learned
        from coverengine.params import resolve_model
        from coverengine.params.registry import list_families

        user = current_user(request)
        params = Registry.load(None).resolve()
        if not approver(user, params):
            raise HTTPException(403, "only Rens, Rick, Wouter (desk.approvers) or an admin")
        if req.key not in params.keys():
            raise HTTPException(400, f"no setting {req.key!r}")
        models = Path(store.models)
        covers = [d for d in sorted(models.iterdir())
                  if (d / "cover.json").is_file() and not no_cover(d)]  # fmt: skip
        # only a group that exists: a family preset or the group of a cover (ADR-123)
        known = set(list_families()) | {g for d in covers if (g := learned.group_of(d))}
        if not learned.valid_group(req.group) or req.group not in known:
            raise HTTPException(400, f"no group {req.group!r}")
        who = user.name or user.username
        try:
            row = learned.write_rule(req.group, req.key, req.value, who,
                                     "made the rule at the Desk", store.root)  # fmt: skip
        except ValueError as exc:  # a server-only setting, a wrong type
            raise HTTPException(400, str(exc)) from None
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
        if not may_act(user, params, a.action):
            if worker(user, params):  # the workshop login: a fit, a comment (ADR-128)
                raise HTTPException(403, "the workshop adds fits and comments; an approver decides")
            raise HTTPException(403, "only Rens, Rick, Wouter (desk.approvers) or an admin")
        return apply(folder(model_id), a, user, learning)


def gate(
    d: Path, model_id: str, request: Request, revision: Path | None = None, name: str = "cut.dxf"
) -> None:
    """The cutting table's DXF only for an approved cover (ADR-079); an admin may override
    with ?override=1, which the desk's history keeps."""
    from coverengine.params import Registry

    from coverapi.security import current_user

    params = Registry.load(None).resolve()
    if dxf_allowed(d, params, revision, name):
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
