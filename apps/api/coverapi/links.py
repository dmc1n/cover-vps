"""Links between a drawing cover and a 3D-model cover of the same product (ADR-132): the store,
the rules and the API behind Covers → Links.

- **Kept in app.db**, two tables: `model_links` (one row per drawing and model: status, score,
  reasons, doubts, the mirror flag, who decided and when) and `model_link_log` (every change,
  never deleted: the history).
- **Statuses**: `proposed` (the program's or the product list's idea), `confirmed` (a person
  said yes), `rejected` (a person said "not a pair"), `manual` (a person chose this partner
  with "Choose another"). Confirmed, rejected and manual are *a person's decision*: the
  proposal script never changes them (`upsert_proposal`), and only a person changes them back.
- **Many to one** both ways: a drawing may be linked to several models (two mirror variants,
  three tables of one size) and a model to several drawings. One row per pair (unique).
- **Mirror**: `mirror = 1` says the drawing is the other hand of the model (a "left" drawing for
  a "right" model). It is a fact about the pair, kept on the link; the compare report mirrors
  the drawing before it compares (link_compare.py), and a learning step must do the same.
- **Learning reads confirmed and manual links only** (`learning_pairs`). A proposal, however
  high its score, is never used to learn from: a wrong pair must not teach anything.
- **The product list's own links** (namecode.xlsx → products.json "suns", ADR-091) are
  proposals here, with their score and reasons (D2 "Evora normal D- Bed" is not the Evora
  sunlounger). `sheet_view` is what the Desk's Products block and the price import read: a
  rejected or replaced link is no longer shown or used; products.json itself is never changed.
- **Rights**: editors and admins confirm, reject and choose (the API checks `edit`); viewers
  see; the workshop login does not see it at all (not on its allow-list in security.py).
- **Concurrency**: each row has a `version`; a decision names the version it saw and a stale
  page gets 409 instead of overwriting another person's decision.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

STATUSES = ("proposed", "confirmed", "rejected", "manual")
PERSON = ("confirmed", "rejected", "manual")  # a person's decision: the proposer never touches it
LIVE = ("proposed", "confirmed", "manual")  # what still links two covers
LEARN = ("confirmed", "manual")  # what learning may read
NOTE_MAX = 500  # param-ok: a note's length
PAGE_MAX = 500  # param-ok: rows per page at most
BULK_MAX = 200  # param-ok: links one bulk confirmation may hold
PROPOSER = "link_proposals"  # who the script is in the log
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drawing_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    status TEXT NOT NULL,
    score REAL,
    strength TEXT NOT NULL DEFAULT 'unsure',
    signals TEXT NOT NULL DEFAULT '{}',
    reasons TEXT NOT NULL DEFAULT '[]',
    doubts TEXT NOT NULL DEFAULT '[]',
    facts TEXT NOT NULL DEFAULT '{}',
    mirror INTEGER NOT NULL DEFAULT 0,
    sheet TEXT,
    source TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    stale INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL,
    created_by TEXT NOT NULL,
    updated REAL NOT NULL,
    updated_by TEXT NOT NULL,
    decided REAL,
    decided_by TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (drawing_id, model_id)
);
CREATE INDEX IF NOT EXISTS model_links_status ON model_links (status);
CREATE INDEX IF NOT EXISTS model_links_model ON model_links (model_id);
CREATE TABLE IF NOT EXISTS model_link_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER,
    time REAL NOT NULL,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS model_link_log_link ON model_link_log (link_id);
"""


# ---- storage --------------------------------------------------------------------------------


def connect(db_path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


@contextmanager
def opened(db_path: Path) -> Iterator[sqlite3.Connection]:
    """app.db for one request or command: every change in one transaction, then closed."""
    db = connect(db_path)
    try:
        with _lock:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")
    finally:
        db.close()
    _CACHE.clear()


def log(
    db: sqlite3.Connection,
    link_id: int | None,
    who: str,
    action: str,
    before: str | None,
    after: str | None,
    detail: Any = None,
) -> None:
    db.execute(
        "INSERT INTO model_link_log (link_id, time, username, action, from_status, to_status,"
        " detail) VALUES (?,?,?,?,?,?,?)",
        (
            link_id,
            time.time(),
            who,
            action,
            before,
            after,
            None if detail is None else json.dumps(detail, ensure_ascii=False),
        ),
    )


def row_out(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"],
        "drawing_id": r["drawing_id"],
        "model_id": r["model_id"],
        "status": r["status"],
        "score": r["score"],
        "strength": r["strength"],
        "signals": json.loads(r["signals"]),
        "reasons": json.loads(r["reasons"]),
        "doubts": json.loads(r["doubts"]),
        "facts": json.loads(r["facts"]),
        "mirror": bool(r["mirror"]),
        "sheet": r["sheet"],
        "source": r["source"],
        "note": r["note"],
        "stale": bool(r["stale"]),
        "created": r["created"],
        "created_by": r["created_by"],
        "updated": r["updated"],
        "updated_by": r["updated_by"],
        "decided": r["decided"],
        "decided_by": r["decided_by"],
        "version": r["version"],
        "person": r["status"] in PERSON,
    }


def get(db: sqlite3.Connection, link_id: int) -> sqlite3.Row:
    r = db.execute("SELECT * FROM model_links WHERE id=?", (link_id,)).fetchone()
    if r is None:
        raise HTTPException(404, f"no link {link_id}")
    return r


def _pair(db: sqlite3.Connection, drawing_id: str, model_id: str) -> sqlite3.Row | None:
    row: sqlite3.Row | None = db.execute(
        "SELECT * FROM model_links WHERE drawing_id=? AND model_id=?", (drawing_id, model_id)
    ).fetchone()
    return row


def upsert_proposal(
    db: sqlite3.Connection,
    r: dict[str, Any],
    strength: str,
    facts: dict[str, Any],
    source: str = PROPOSER,
) -> str:
    """One proposal from the script: new, refreshed (still a proposal) or kept as a person
    decided ("person"). A person's decision (confirmed, rejected, manual) is never changed,
    not its status, not its score, not its reasons: the script only reports it."""
    now = time.time()
    old = _pair(db, r["drawing_id"], r["model_id"])
    values = (
        r["score"],
        strength,
        json.dumps(r["signals"]),
        json.dumps(r["reasons"], ensure_ascii=False),
        json.dumps(r["doubts"], ensure_ascii=False),
        json.dumps(facts, ensure_ascii=False),
        int(bool(r.get("mirror"))),
        r.get("sheet"),
    )
    src = "sheet" if r.get("sheet") == "linked" else "proposer"
    if old is None:
        cur = db.execute(
            "INSERT INTO model_links (drawing_id, model_id, status, score, strength, signals,"
            " reasons, doubts, facts, mirror, sheet, source, created, created_by, updated,"
            " updated_by) VALUES (?,?,'proposed',?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["drawing_id"], r["model_id"], *values, src, now, source, now, source),
        )
        log(
            db,
            cur.lastrowid,
            source,
            "propose",
            None,
            "proposed",
            {"score": r["score"], "reasons": r["reasons"][:3], "doubts": r["doubts"][:3]},
        )
        return "new"
    if old["status"] in PERSON:
        return "person"
    changed = (
        old["score"],
        old["strength"],
        old["signals"],
        old["reasons"],
        old["doubts"],
        old["facts"],
        old["mirror"],
        old["sheet"],
    ) != values or old["stale"]
    if not changed:
        return "unchanged"
    db.execute(
        "UPDATE model_links SET score=?, strength=?, signals=?, reasons=?, doubts=?, facts=?,"
        " mirror=?, sheet=?, stale=0, updated=?, updated_by=?, version=version+1"
        " WHERE id=? AND status='proposed'",
        (*values, now, source, old["id"]),
    )
    log(
        db,
        old["id"],
        source,
        "refresh",
        "proposed",
        "proposed",
        {"score": [old["score"], r["score"]]},
    )
    return "updated"


def mark_stale(db: sqlite3.Connection, keep: set[tuple[str, str]], source: str = PROPOSER) -> int:
    """Proposals the script no longer makes: marked stale (kept, with their history), never
    deleted; a person's decision is never touched."""
    n = 0
    for r in db.execute("SELECT * FROM model_links WHERE status='proposed' AND stale=0").fetchall():
        if (r["drawing_id"], r["model_id"]) not in keep:
            db.execute(
                "UPDATE model_links SET stale=1, updated=?, updated_by=?,"
                " version=version+1 WHERE id=?",
                (time.time(), source, r["id"]),
            )
            log(db, r["id"], source, "stale", "proposed", "proposed")
            n += 1
    return n


def decide(
    db: sqlite3.Connection,
    link_id: int,
    status: str,
    who: str,
    note: str = "",
    version: int | None = None,
    mirror: bool | None = None,
) -> dict[str, Any]:
    """A person's decision on one link: confirmed, rejected, manual or back to proposed."""
    if status not in STATUSES:
        raise HTTPException(400, f"status: one of {', '.join(STATUSES)}")
    r = get(db, link_id)
    if version is not None and int(version) != int(r["version"]):
        raise HTTPException(409, "someone changed this link meanwhile; reload the page")
    note = (note or "").strip()[:NOTE_MAX]
    now = time.time()
    person = status in PERSON
    db.execute(
        "UPDATE model_links SET status=?, note=?, mirror=?, updated=?, updated_by=?, decided=?,"
        " decided_by=?, stale=0, version=version+1 WHERE id=?",
        (
            status,
            note or r["note"],
            int(r["mirror"] if mirror is None else bool(mirror)),
            now,
            who,
            now if person else None,
            who if person else None,
            link_id,
        ),
    )
    log(
        db,
        link_id,
        who,
        {"confirmed": "confirm", "rejected": "reject", "manual": "choose", "proposed": "reopen"}[
            status
        ],
        r["status"],
        status,
        {"note": note} if note else None,
    )
    return row_out(get(db, link_id))


def choose(
    db: sqlite3.Connection,
    drawing_id: str,
    model_id: str,
    who: str,
    replaces: int | None = None,
    note: str = "",
    mirror: bool = False,
    scored: dict[str, Any] | None = None,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """ "Choose another": a person links this drawing and this model (status manual). The link
    it replaces, if any, becomes rejected with a note, so it is no longer used anywhere."""
    if drawing_id == model_id:
        raise HTTPException(400, "a cover cannot be linked to itself")
    old = _pair(db, drawing_id, model_id)
    replaced = None
    if replaces is not None:
        rep = get(db, replaces)
        if rep["drawing_id"] != drawing_id:
            raise HTTPException(400, "the link it replaces belongs to another drawing")
        if rep["id"] != (old["id"] if old else None):
            replaced = decide(db, rep["id"], "rejected", who, note=f"replaced by {model_id}")
    if old is not None:
        out = decide(db, old["id"], "manual", who, note=note, mirror=mirror)
    else:
        now = time.time()
        s = scored or {}
        cur = db.execute(
            "INSERT INTO model_links (drawing_id, model_id, status, score, strength, signals,"
            " reasons, doubts, facts, mirror, source, note, created, created_by, updated,"
            " updated_by, decided, decided_by) VALUES (?,?,'manual',?,?,?,?,?,?,?,'person',?,?,"
            "?,?,?,?,?)",
            (
                drawing_id,
                model_id,
                s.get("score"),
                s.get("strength", "unsure"),
                json.dumps(s.get("signals") or {}),
                json.dumps(s.get("reasons") or [], ensure_ascii=False),
                json.dumps(s.get("doubts") or [], ensure_ascii=False),
                json.dumps(facts or {}, ensure_ascii=False),
                int(bool(mirror)),
                (note or "").strip()[:NOTE_MAX],
                now,
                who,
                now,
                who,
                now,
                who,
            ),
        )
        lid = int(cur.lastrowid or 0)
        log(
            db,
            lid,
            who,
            "choose",
            None,
            "manual",
            {"replaces": replaces, "note": note} if (replaces or note) else None,
        )
        out = row_out(get(db, lid))
    return {"link": out, "replaced": replaced}


def history(db: sqlite3.Connection, link_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT * FROM model_link_log WHERE link_id=? ORDER BY id", (link_id,)
    ).fetchall()
    return [
        {
            "time": r["time"],
            "by": r["username"],
            "action": r["action"],
            "from": r["from_status"],
            "to": r["to_status"],
            "detail": json.loads(r["detail"]) if r["detail"] else None,
        }
        for r in rows
    ]


def learning_pairs(db_path: Path) -> list[dict[str, Any]]:
    """The pairs learning may read: confirmed or chosen by a person, nothing else."""
    if not db_path.is_file():
        return []
    db = connect(db_path)
    try:
        rows = db.execute(
            f"SELECT * FROM model_links WHERE status IN ({','.join('?' * len(LEARN))})"
            " ORDER BY drawing_id, model_id",
            LEARN,
        ).fetchall()
        return [row_out(r) for r in rows]
    finally:
        db.close()


# ---- what other pages read ------------------------------------------------------------------

_CACHE: dict[str, Any] = {}
CACHE_S = 2.0  # param-ok: a script's change shows within this many seconds


def decisions(db_path: Path) -> dict[tuple[str, str], str]:
    """(drawing, model) → status, for the pages that show or use links (cached briefly)."""
    key = str(db_path)
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_S:
        out: dict[tuple[str, str], str] = hit[1]
        return out
    out = {}
    if db_path.is_file():
        try:
            db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            try:
                for d, m, s in db.execute("SELECT drawing_id, model_id, status FROM model_links"):
                    out[(d, m)] = s
            finally:
                db.close()
        except sqlite3.Error:  # no table yet: nothing decided
            out = {}
    _CACHE[key] = (time.monotonic(), out)
    return out


def db_for_model(model_dir: Path) -> Path:
    """app.db of the data folder a model folder lives in (models/<id> → ../app.db), without
    resolving symlinks (the live models folder is one)."""
    return model_dir.parent.parent / "app.db"


def sheet_view(drawing_id: str, sheet: dict[str, list[str]], db_path: Path) -> dict[str, Any]:
    """The product list's SUNS links for one drawing as people decided them: confirmed or
    chosen links (`linked`), the sheet's links still waiting for a person (`proposed`), its
    suggestions nobody rejected (`suggested`), and what a person rejected (`rejected`)."""
    dec = decisions(db_path)
    mine = {m: s for (d, m), s in dec.items() if d == drawing_id}
    sheet_linked = list(sheet.get("linked") or [])
    sheet_suggested = list(sheet.get("suggested") or [])
    linked = sorted(m for m, s in mine.items() if s in LEARN)
    rejected = sorted(m for m, s in mine.items() if s == "rejected")
    proposed = [m for m in sheet_linked if mine.get(m, "proposed") == "proposed"]
    suggested = [
        m for m in sheet_suggested if m not in rejected and m not in linked and m not in proposed
    ]
    return {"linked": linked, "proposed": proposed, "suggested": suggested, "rejected": rejected}


def used_suns(drawing_id: str, sheet_linked: list[str], db_path: Path) -> list[str]:
    """The SUNS models a drawing's price may be carried to (the price import, ADR-113): links a
    person confirmed or chose, and the sheet's links nobody rejected (as before ADR-132)."""
    dec = decisions(db_path)
    confirmed = [m for (d, m), s in dec.items() if d == drawing_id and s in LEARN]
    kept = [m for m in sheet_linked if dec.get((drawing_id, m)) != "rejected"]
    return list(dict.fromkeys(confirmed + kept))


def links_of(db_path: Path, model_id: str) -> list[dict[str, Any]]:
    """A cover's live links either way (for its page's "Linked to …" chip)."""
    if not db_path.is_file():
        return []
    db = connect(db_path)
    try:
        rows = db.execute(
            "SELECT * FROM model_links WHERE (drawing_id=? OR model_id=?) AND status IN"
            " ('proposed','confirmed','manual') ORDER BY CASE status WHEN 'proposed' THEN 1"
            " ELSE 0 END, score DESC",
            (model_id, model_id),
        ).fetchall()
    finally:
        db.close()
    out = []
    for r in rows:
        partner = r["model_id"] if r["drawing_id"] == model_id else r["drawing_id"]
        out.append(
            {
                "id": r["id"],
                "partner": partner,
                "status": r["status"],
                "score": r["score"],
                "mirror": bool(r["mirror"]),
                "person": r["status"] in PERSON,
            }
        )
    return out


# ---- the API --------------------------------------------------------------------------------


class DecideIn(BaseModel):
    status: str  # confirmed | rejected | proposed (reopen)
    note: str = ""
    version: int | None = None
    mirror: bool | None = None


class ChooseIn(BaseModel):
    drawing_id: str
    model_id: str
    replaces: int | None = None
    note: str = ""
    mirror: bool = False


class BulkIn(BaseModel):
    ids: list[int]
    min_score: float


def _filters(status: str, q: str, strength: str) -> tuple[str, list[Any]]:
    where, args = [], []
    if status and status != "all":
        if status not in STATUSES:
            raise HTTPException(400, f"status: one of all, {', '.join(STATUSES)}, nopartner")
        where.append("status=?")
        args.append(status)
    if strength:
        where.append("strength=?")
        args.append(strength)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        where.append("(lower(drawing_id) LIKE ? OR lower(model_id) LIKE ? OR lower(facts) LIKE ?)")
        args += [like, like, like]
    return (" WHERE " + " AND ".join(where)) if where else "", args


def install(app: FastAPI, store: Any) -> None:
    """GET /api/links (viewers and up), the decisions (editors and admins)."""
    from coverengine.params import Registry

    from coverapi.security import current_user, require

    db_path = Path(store.root) / "app.db"
    models = Path(store.models)

    def seer(request: Request) -> Any:
        user = current_user(request)
        if user.role == "workshop":  # also refused at the front door (allow-list)
            raise HTTPException(403, "the workshop login may not open this")
        return user

    def _model(mid: str, prefix: tuple[str, ...]) -> Path:
        try:
            d = store.model_dir(mid)
        except KeyError:
            raise HTTPException(400, f"not a cover: {mid}") from None
        if not mid.startswith(prefix) or not (d / "cover.json").is_file():
            raise HTTPException(404, f"no such cover: {mid}")
        return Path(d)

    @app.get("/api/links")
    def list_links(
        request: Request,
        status: str = "proposed",
        q: str = "",
        strength: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """The queue: links by status (all, proposed, confirmed, rejected, manual), or the
        drawing covers with no live link (`status=nopartner`)."""
        seer(request)
        p = Registry.load(None).resolve()
        limit = max(1, min(int(limit), PAGE_MAX))
        offset = max(0, int(offset))
        with opened(db_path) as db:
            counts = {
                s: n
                for s, n in db.execute("SELECT status, count(*) FROM model_links GROUP BY status")
            }
            linked = {
                d
                for (d,) in db.execute(
                    "SELECT DISTINCT drawing_id FROM model_links WHERE status IN"
                    " ('proposed','confirmed','manual')"
                )
            }
            drawings = sorted(
                d.name for d in models.glob("drawing-*") if (d / "cover.json").is_file()
            )
            alone = [
                d
                for d in drawings
                if d not in linked and not (q.strip() and q.strip().lower() not in d)
            ]
            counts["nopartner"] = len([d for d in drawings if d not in linked])
            if status == "nopartner":
                rows: list[dict[str, Any]] = []
                total = len(alone)
                page = alone[offset : offset + limit]
            else:
                where, args = _filters(status, q, strength)
                total = db.execute(f"SELECT count(*) FROM model_links{where}", args).fetchone()[0]
                order = (
                    " ORDER BY CASE strength WHEN 'high' THEN 0 WHEN 'likely' THEN 1 ELSE 2"
                    " END, score DESC, drawing_id, model_id"
                )
                rows = [
                    row_out(r)
                    for r in db.execute(
                        f"SELECT * FROM model_links{where}{order} LIMIT ? OFFSET ?",
                        [*args, limit, offset],
                    )
                ]
                page = []
        user = current_user(request)
        return {
            "links": rows,
            "nopartner": page,
            "total": total,
            "counts": counts,
            "bulk_min": float(p["links.bulk_min"]),  # type: ignore[arg-type]
            "propose_min": float(p["links.propose_min"]),  # type: ignore[arg-type]
            "may_edit": user.may("edit"),
        }

    @app.get("/api/links/of/{model_id}")
    def of_model(model_id: str, request: Request) -> dict[str, Any]:
        """A cover's links (its page's "Linked to …" chip)."""
        seer(request)
        return {"links": links_of(db_path, model_id)}

    @app.get("/api/links/{link_id}")
    def one(link_id: int, request: Request) -> dict[str, Any]:
        seer(request)
        with opened(db_path) as db:
            return {**row_out(get(db, link_id)), "history": history(db, link_id)}

    @app.post("/api/links/{link_id}/decide")
    def decide_one(link_id: int, body: DecideIn, request: Request) -> dict[str, Any]:
        """Confirm, "Not a pair" (rejected) or back to proposed; editors and admins."""
        user = require(request, "edit")
        if body.status not in ("confirmed", "rejected", "proposed"):
            raise HTTPException(400, "status: confirmed, rejected or proposed")
        with opened(db_path) as db:
            return decide(
                db, link_id, body.status, user.username, body.note, body.version, body.mirror
            )

    @app.post("/api/links/choose")
    def choose_one(body: ChooseIn, request: Request) -> dict[str, Any]:
        """ "Choose another": link this drawing to this model by hand (and reject the link it
        replaces); editors and admins."""
        user = require(request, "edit")
        from coverapi import link_score as ls
        from coverapi import match_list

        dd = _model(body.drawing_id, ("drawing-",))
        md = _model(body.model_id, ls.CANDIDATES)
        p = Registry.load(None).resolve()
        scored: dict[str, Any] | None = None
        facts: dict[str, Any] = {}
        try:  # the pair's own score and reasons, for the page; a failure leaves them empty
            lst = match_list.for_data(Path(store.root))
            fd, fm = ls.facts(dd, p, lst), ls.facts(md, p, lst)
            scored = ls.score(fd, fm, p)
            scored["strength"] = ls.strength(scored, p)
            facts = {"drawing": fd.brief(), "model": fm.brief()}
        except Exception:  # noqa: BLE001 - the person's choice counts, with or without a score
            scored = None
        with opened(db_path) as db:
            return choose(
                db,
                body.drawing_id,
                body.model_id,
                user.username,
                body.replaces,
                body.note,
                body.mirror,
                scored,
                facts,
            )

    @app.post("/api/links/bulk-confirm")
    def bulk(body: BulkIn, request: Request) -> dict[str, Any]:
        """Confirm many proposals at once, only those scoring at least links.bulk_min with no
        doubt; anything else is skipped and said."""
        user = require(request, "edit")
        p = Registry.load(None).resolve()
        floor = max(float(body.min_score), float(p["links.bulk_min"]))  # type: ignore[arg-type]
        if len(body.ids) > BULK_MAX:
            raise HTTPException(400, f"at most {BULK_MAX} links at once")
        done, skipped = [], []
        with opened(db_path) as db:
            for lid in dict.fromkeys(body.ids):
                r = db.execute("SELECT * FROM model_links WHERE id=?", (lid,)).fetchone()
                why = None if r is not None else "no such link"
                if r is not None and r["status"] != "proposed":
                    why = f"already {r['status']}"
                elif r is not None and (r["score"] is None or r["score"] < floor):
                    why = f"score below {floor:g}"
                elif r is not None and json.loads(r["doubts"]):
                    why = "has a doubt"
                if why:
                    skipped.append({"id": lid, "why": why})
                    continue
                decide(db, lid, "confirmed", user.username, note="bulk confirm")
                done.append(lid)
        return {"confirmed": done, "skipped": skipped, "min_score": floor}

    @app.get("/api/links-search")
    def search(request: Request, q: str = "", side: str = "model") -> dict[str, Any]:
        """Covers to choose from: 3D-model covers (side=model) or drawing covers (side=drawing)."""
        seer(request)
        from coverapi import link_score as ls

        pre = ("drawing-",) if side == "drawing" else ls.CANDIDATES
        words = [w for w in q.lower().split() if w]
        out = []
        for d in sorted(models.iterdir()) if models.is_dir() else []:
            if not d.name.startswith(pre) or not (d / "cover.json").is_file():
                continue
            if all(w in d.name for w in words):
                out.append({"id": d.name, "picture": (d / "cover.png").is_file()})
            if len(out) >= 40:  # param-ok: a picker's list
                break
        return {"covers": out}
