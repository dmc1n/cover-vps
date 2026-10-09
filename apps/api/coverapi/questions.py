"""Questions at the Desk (ADR-109): the open questions for the owner and the workshop, answered
in the studio instead of by mail or over SSH.

The owner, 9 October 2026: "for Rens it's easier if we put the questions in a tab in the Desk so
he can answer there; I (Rick) am the only one with SSH access. And every day around 18:00 check
and process the answers."

- **Kept in app.db**, three tables: `questions` (the question, its context, options and state),
  `question_answers` (every answer, never deleted: a new answer by the same person replaces the
  old one by pointing at it) and `question_log` (every change, who and when: the audit trail).
- **A question** has a title, the question itself (Dutch), context, the covers it is about (links
  to their Desk cards), pictures (a plan view, a before/after; the Desk's picture checks,
  ADR-096), 2 to 5 options plus "anders, namelijk…", and who may answer (the Desk's approvers
  by default).
- **The state:** open -> answered (someone answered) -> processed (what was done, a note the
  answerer sees). Several people may answer; all answers show. The owner (`questions.owners`)
  marks one as final, marks a question processed, or opens it again.
- **Answers** carry an option (or "anders" with words), a comment and pictures, uploaded first
  as at the Desk (`POST /api/questions/{id}/pictures`), checked and re-encoded as PNG.
- **Mail, quietly** (`question_mails`, hourly): new questions go to the approvers in at most one
  digest per `questions.digest_hours`; new answers go to the owners in at most one digest per
  `questions.answer_digest_hours`; nothing per click.
- **The main session** fetches new answers and marks questions processed with
  `scripts/questions.py new|done` (the same functions, straight on app.db).
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

TOPICS = (
    "vents",
    "shape",
    "seams",
    "sizes",
    "drawings",
    "workshop",
    "webshop",
    "b2b",
    "prices",
    "film",
    "other",
)
STATUSES = ("open", "answered", "processed")
OTHER = -1  # the choice "anders, namelijk…"
MIN_OPTIONS, MAX_OPTIONS = 2, 5
FOLDER = "questions"  # in the data folder: questions/<id>/<picture>.png
PICTURE_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9]{1,4}\.png$")
TEXT_MAX = 4000  # characters of a comment or a note
MAIL_KEY = "questions_mail"  # the settings row with the last digests' times
HOUR_S = 3600.0
FIRST_MAIL_S = 120.0  # the first look for due digests, a while after the app starts
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    topic TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    models TEXT NOT NULL DEFAULT '[]',
    pictures TEXT NOT NULL DEFAULT '[]',
    options TEXT NOT NULL DEFAULT '[]',
    other_allowed INTEGER NOT NULL DEFAULT 1,
    answerers TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    final_answer INTEGER,
    final_by TEXT,
    final_time REAL,
    processed_note TEXT,
    processed_by TEXT,
    processed_time REAL,
    source TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL,
    created_by TEXT NOT NULL,
    updated REAL NOT NULL,
    announced REAL
);
CREATE TABLE IF NOT EXISTS question_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    name TEXT NOT NULL,
    choice INTEGER,
    other TEXT NOT NULL DEFAULT '',
    comment TEXT NOT NULL DEFAULT '',
    pictures TEXT NOT NULL DEFAULT '[]',
    time REAL NOT NULL,
    replaced_by INTEGER,
    notified REAL
);
CREATE INDEX IF NOT EXISTS question_answers_q ON question_answers (question_id);
CREATE TABLE IF NOT EXISTS question_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER,
    time REAL NOT NULL,
    username TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT
);
"""


class AnswerIn(BaseModel):
    choice: int | None = None  # an option's index, or -1 for "anders, namelijk…"
    other: str = ""
    comment: str = ""
    pictures: list[str] = []  # names returned by POST /api/questions/{id}/pictures


class FinalIn(BaseModel):
    answer_id: int | None = None  # None takes the final mark away


class NoteIn(BaseModel):
    note: str = ""


class QuestionIn(BaseModel):
    title: str
    text: str
    topic: str = "other"
    context: str = ""
    models: list[str] = []
    options: list[str] = []
    other_allowed: bool = True
    answerers: str = ""
    key: str | None = None


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


def _now() -> float:
    return time.time()


def log(db: sqlite3.Connection, qid: int | None, who: str, action: str, detail: Any = None) -> None:
    db.execute(
        "INSERT INTO question_log (question_id, time, username, action, detail) VALUES (?,?,?,?,?)",
        (qid, _now(), who, action, None if detail is None else json.dumps(detail)),
    )


def _clean_text(s: str, what: str) -> str:
    s = (s or "").strip()
    if len(s) > TEXT_MAX:
        raise HTTPException(400, f"{what}: at most {TEXT_MAX} characters")
    return s


def _model_ref(models_dir: Path | None, model_id: str) -> dict[str, Any]:
    """A cover the question is about: its id, its code, whether it has a picture."""
    ref: dict[str, Any] = {"id": model_id, "code": model_id, "picture": False}
    d = models_dir / model_id if models_dir is not None else None
    if d is not None and d.is_dir():
        from coverapi.desk import _code

        try:
            ref["code"] = _code(d)
        except Exception:  # noqa: BLE001 - the id is a fine name too
            pass
        ref["picture"] = (d / "cover.png").is_file()
    elif model_id.startswith("drawing-"):
        ref["code"] = model_id.removeprefix("drawing-").upper()
    return ref


def check_question(q: dict[str, Any]) -> dict[str, Any]:
    """A new question's fields, checked and trimmed."""
    title = (q.get("title") or "").strip()
    text = (q.get("text") or "").strip()
    if not title or not text:
        raise HTTPException(400, "a question needs a title and its text")
    topic = q.get("topic") or "other"
    if topic not in TOPICS:
        raise HTTPException(400, f"topic: one of {', '.join(TOPICS)}")
    options = [str(o).strip() for o in q.get("options") or [] if str(o).strip()]
    if options and not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
        raise HTTPException(400, f"{MIN_OPTIONS} to {MAX_OPTIONS} options, or none (free answer)")
    return {
        "key": q.get("key") or None,
        "title": title[:200],
        "text": text[:TEXT_MAX],
        "topic": topic,
        "context": str(q.get("context") or "").strip()[:TEXT_MAX],
        "models": list(dict.fromkeys(str(m) for m in q.get("models") or [])),
        "options": options,
        "other_allowed": bool(q.get("other_allowed", True)),
        "answerers": str(q.get("answerers") or "").strip(),
        "source": str(q.get("source") or "")[:500],
    }


def add_question(
    db: sqlite3.Connection, q: dict[str, Any], by: str, models_dir: Path | None = None
) -> tuple[int, bool]:
    """Add a question; one with a `key` that exists already is left as it is (an import may
    run again). Returns (id, made)."""
    c = check_question(q)
    if c["key"]:
        row = db.execute("SELECT id FROM questions WHERE key=?", (c["key"],)).fetchone()
        if row:
            return int(row["id"]), False
    refs = [_model_ref(models_dir, m) for m in c["models"]]
    now = _now()
    cur = db.execute(
        "INSERT INTO questions (key, title, text, topic, context, models, options, other_allowed,"
        " answerers, source, created, created_by, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            c["key"],
            c["title"],
            c["text"],
            c["topic"],
            c["context"],
            json.dumps(refs),
            json.dumps(c["options"], ensure_ascii=False),
            int(c["other_allowed"]),
            c["answerers"],
            c["source"],
            now,
            by,
            now,
        ),
    )
    qid = int(cur.lastrowid or 0)
    log(db, qid, by, "add", {k: c[k] for k in ("key", "title", "topic")})
    return qid, True


def folder(root: Path, qid: int) -> Path:
    return root / FOLDER / str(int(qid))


def picture_path(root: Path, qid: int, name: str) -> Path | None:
    """A question's picture by name; only names this module made, so no path leads out."""
    if not PICTURE_RE.match(name):
        return None
    p = folder(root, qid) / name
    return p if p.is_file() else None


def save_picture(root: Path, qid: int, data: bytes, params: Any) -> str:
    """Checked and kept as a fresh PNG without metadata, as at the Desk (ADR-096)."""
    from coverapi import desk

    return desk.save_picture(folder(root, qid), data, params, sub="")


def add_question_picture(
    db: sqlite3.Connection, root: Path, qid: int, data: bytes, caption: str, by: str, params: Any
) -> str:
    """A picture that belongs to the question itself (a plan view, a before/after)."""
    row = _row(db, qid)
    name = save_picture(root, qid, data, params)
    pics = json.loads(row["pictures"])
    pics.append({"name": name, "caption": caption.strip()[:200]})
    db.execute(
        "UPDATE questions SET pictures=?, updated=? WHERE id=?",
        (json.dumps(pics, ensure_ascii=False), _now(), qid),
    )
    log(db, qid, by, "picture", {"name": name, "caption": caption})
    return name


def _row(db: sqlite3.Connection, qid: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
    if row is None:
        raise HTTPException(404, f"no question {qid}")
    return row


def _answer_out(a: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": a["id"],
        "username": a["username"],
        "name": a["name"],
        "choice": a["choice"],
        "other": a["other"],
        "comment": a["comment"],
        "pictures": json.loads(a["pictures"]),
        "time": a["time"],
    }


def question_out(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    answers = db.execute(
        "SELECT * FROM question_answers WHERE question_id=? AND replaced_by IS NULL ORDER BY id",
        (row["id"],),
    ).fetchall()
    return {
        "id": row["id"],
        "key": row["key"],
        "title": row["title"],
        "text": row["text"],
        "topic": row["topic"],
        "context": row["context"],
        "models": json.loads(row["models"]),
        "pictures": json.loads(row["pictures"]),
        "options": json.loads(row["options"]),
        "other_allowed": bool(row["other_allowed"]),
        "answerers": row["answerers"],
        "status": row["status"],
        "final_answer": row["final_answer"],
        "final_by": row["final_by"],
        "processed": {
            "note": row["processed_note"],
            "by": row["processed_by"],
            "time": row["processed_time"],
        }
        if row["processed_time"]
        else None,
        "created": row["created"],
        "created_by": row["created_by"],
        "updated": row["updated"],
        "source": row["source"],
        "answers": [_answer_out(a) for a in answers],
    }


def get(db: sqlite3.Connection, qid: int) -> dict[str, Any]:
    return question_out(db, _row(db, qid))


def listing(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute("SELECT * FROM questions ORDER BY id").fetchall()
    return [question_out(db, r) for r in rows]


def answer(
    db: sqlite3.Connection, root: Path, qid: int, a: AnswerIn, username: str, name: str
) -> dict[str, Any]:
    row = _row(db, qid)
    if row["status"] == "processed":
        raise HTTPException(409, "this question is processed already; ask the owner to reopen it")
    options = json.loads(row["options"])
    other = _clean_text(a.other, "anders")
    comment = _clean_text(a.comment, "comment")
    if a.choice is not None:
        if a.choice == OTHER:
            if not row["other_allowed"]:
                raise HTTPException(400, "this question has no 'anders' choice")
            if not other:
                raise HTTPException(400, "anders, namelijk…: write what")
        elif not 0 <= a.choice < len(options):
            raise HTTPException(400, "no such option")
    if a.choice is None and not (comment or a.pictures):
        raise HTTPException(400, "choose an option or write a comment")
    pics = list(dict.fromkeys(a.pictures))
    bad = [p for p in pics if picture_path(root, qid, p) is None]
    if bad:
        raise HTTPException(400, f"no such picture: {', '.join(bad)[:200]}")
    now = _now()
    cur = db.execute(
        "INSERT INTO question_answers (question_id, username, name, choice, other, comment,"
        " pictures, time) VALUES (?,?,?,?,?,?,?,?)",
        (
            qid,
            username,
            name,
            a.choice,
            other if a.choice == OTHER else "",
            comment,
            json.dumps(pics),
            now,
        ),
    )
    aid = int(cur.lastrowid or 0)
    # the same person's earlier answer is replaced (kept, for the audit trail)
    db.execute(
        "UPDATE question_answers SET replaced_by=? WHERE question_id=? AND username=? AND id<>?"
        " AND replaced_by IS NULL",
        (aid, qid, username, aid),
    )
    if row["final_answer"] is not None:
        old = db.execute(
            "SELECT replaced_by FROM question_answers WHERE id=?", (row["final_answer"],)
        ).fetchone()
        if old is not None and old["replaced_by"] == aid:
            db.execute(
                "UPDATE questions SET final_answer=NULL, final_by=NULL, final_time=NULL WHERE id=?",
                (qid,),
            )
    db.execute("UPDATE questions SET status='answered', updated=? WHERE id=?", (now, qid))
    log(
        db,
        qid,
        username,
        "answer",
        {"answer": aid, "choice": a.choice, "other": other, "comment": comment, "pictures": pics},
    )
    return get(db, qid)


def mark_final(db: sqlite3.Connection, qid: int, answer_id: int | None, who: str) -> dict[str, Any]:
    _row(db, qid)
    if answer_id is not None:
        a = db.execute(
            "SELECT id FROM question_answers WHERE id=? AND question_id=? AND replaced_by IS NULL",
            (answer_id, qid),
        ).fetchone()
        if a is None:
            raise HTTPException(404, f"no answer {answer_id} on question {qid}")
    db.execute(
        "UPDATE questions SET final_answer=?, final_by=?, final_time=?, updated=? WHERE id=?",
        (answer_id, who if answer_id else None, _now() if answer_id else None, _now(), qid),
    )
    log(db, qid, who, "final", {"answer": answer_id})
    return get(db, qid)


def mark_done(db: sqlite3.Connection, qid: int, note: str, who: str) -> dict[str, Any]:
    _row(db, qid)
    note = _clean_text(note, "note")
    if not note:
        raise HTTPException(400, "say what was done (shown to whoever answered)")
    now = _now()
    db.execute(
        "UPDATE questions SET status='processed', processed_note=?, processed_by=?, "
        "processed_time=?, updated=? WHERE id=?",
        (note, who, now, now, qid),
    )
    log(db, qid, who, "processed", {"note": note})
    return get(db, qid)


def reopen(db: sqlite3.Connection, qid: int, who: str) -> dict[str, Any]:
    _row(db, qid)
    n = db.execute(
        "SELECT COUNT(*) FROM question_answers WHERE question_id=? AND replaced_by IS NULL", (qid,)
    ).fetchone()[0]
    db.execute(
        "UPDATE questions SET status=?, processed_note=NULL, processed_by=NULL, "
        "processed_time=NULL, updated=? WHERE id=?",
        ("answered" if n else "open", _now(), qid),
    )
    log(db, qid, who, "reopen")
    return get(db, qid)


def answers_since(db: sqlite3.Connection, since: float) -> list[dict[str, Any]]:
    """Every answer given after `since` (epoch seconds), with its question: for the daily run."""
    rows = db.execute(
        "SELECT a.*, q.title, q.text AS qtext, q.options, q.status, q.final_answer, q.models "
        "FROM question_answers a JOIN questions q ON q.id = a.question_id "
        "WHERE a.time > ? ORDER BY a.time",
        (since,),
    ).fetchall()
    out = []
    for r in rows:
        options = json.loads(r["options"])
        choice = r["choice"]
        chosen = (
            f"anders: {r['other']}"
            if choice == OTHER
            else options[choice]
            if choice is not None and 0 <= choice < len(options)
            else None
        )
        out.append(
            {
                **_answer_out(r),
                "question_id": r["question_id"],
                "question": r["title"],
                "question_text": r["qtext"],
                "chosen": chosen,
                "replaced": r["replaced_by"] is not None,
                "final": r["final_answer"] == r["id"],
                "question_status": r["status"],
                "models": [m["id"] for m in json.loads(r["models"])],
            }
        )
    return out


# ---- rights ---------------------------------------------------------------------------------


def _names(s: str) -> set[str]:
    return {n.strip().lower() for n in str(s).split(",") if n.strip()}


def _matches(user: Any, names: set[str]) -> bool:
    first = (user.name or "").strip().split(" ")[0].lower()
    return bool(user.active and (user.username.lower() in names or first in names))


def may_answer(user: Any, q: dict[str, Any] | sqlite3.Row, params: Any) -> bool:
    """The question's own answerers, or the Desk's approvers; admins always."""
    from coverapi.desk import approver

    if user.may("admin"):
        return True
    own = _names(q["answerers"] or "")
    return _matches(user, own) if own else approver(user, params)


def is_owner(user: Any, params: Any) -> bool:
    """Who marks an answer final and a question processed (`questions.owners`; the local user
    when logins are off)."""
    if user.id == 0 and user.may("admin"):
        return True
    return _matches(user, _names(str(params["questions.owners"])))


# ---- mail, quietly --------------------------------------------------------------------------


def _people(auth: Any, names: set[str]) -> list[Any]:
    return [u for u in auth.users() if u.email and _matches(u, names)]


def question_mails(
    auth: Any, params: Any, base_url: str, send: Any, models_dir: Path | None = None
) -> dict[str, int]:
    """The digests that are due: new questions (and what was done with yours) to the people who
    may answer, new answers to the owners. At most one of each per its interval. The
    arrangements sent to the Desk since the last digest go to the approvers in the same
    questions digest (ADR-115): one mail a day, never one per click."""
    from coverapi import desk

    sent = {"questions": 0, "answers": 0}
    state = dict(auth.setting(MAIL_KEY, {}) or {})
    now = _now()
    with opened(auth.path) as db:
        hours = float(params["questions.digest_hours"])
        if hours > 0 and now - float(state.get("questions", 0)) >= hours * HOUR_S:
            new = db.execute(
                "SELECT * FROM questions WHERE announced IS NULL AND status<>"
                "'processed' ORDER BY id"
            ).fetchall()
            since = float(state.get("questions", 0))
            done = db.execute(
                "SELECT * FROM questions WHERE processed_time > ? ORDER BY id", (since,)
            ).fetchall()
            default = _names(str(params["desk.approvers"]))
            arrs = desk.arrangements_to_announce(models_dir) if models_dir else []
            people: dict[str, Any] = {}
            for q in [*new, *done]:
                for u in _people(auth, _names(q["answerers"]) or default):
                    people[u.username] = u
            if arrs:
                for u in _people(auth, default):
                    people[u.username] = u
            for u in people.values():
                mine_arrs = arrs if _matches(u, default) else []
                mine_new = [q for q in new if _matches(u, _names(q["answerers"]) or default)]
                answered = {
                    r["question_id"]
                    for r in db.execute(
                        "SELECT question_id FROM question_answers WHERE username=?", (u.username,)
                    )
                }
                mine_done = [q for q in done if q["id"] in answered]
                if not (mine_new or mine_done or mine_arrs):
                    continue
                lines = [f"Hallo {(u.name or u.username).split(' ')[0]},", ""]
                if mine_arrs:
                    lines += [
                        f"{len(mine_arrs)} opstelling(en) wachten op je goedkeuring op de Desk:",
                        "",
                    ]
                    for a in mine_arrs:
                        how = "opnieuw, na een wijziging" if a["again"] else f"van {a['by']}"
                        lines.append(f"- {a['code']} ({how})\n  {base_url}/#/desk/{a['id']}")
                    lines.append("")
                if mine_new:
                    lines += [f"Er staan {len(mine_new)} nieuwe vragen voor je op de Desk:", ""]
                    lines += [
                        f"- {q['title']}\n  {base_url}/#/questions/{q['id']}" for q in mine_new
                    ]
                    lines.append("")
                if mine_done:
                    lines += ["Verwerkt (wat er met je antwoord is gedaan):", ""]
                    lines += [f"- {q['title']}: {q['processed_note']}" for q in mine_done]
                    lines.append("")
                lines += [f"Alle vragen: {base_url}/#/questions", ""]
                send(
                    u.email,
                    f"Cover Studio: {len(mine_new)} nieuwe vragen"
                    if mine_new
                    else f"Cover Studio: {len(mine_arrs)} opstelling(en) klaar voor goedkeuring"
                    if mine_arrs
                    else "Cover Studio: je antwoorden zijn verwerkt",
                    "\n".join(lines),
                )
                sent["questions"] += 1
            if new:
                db.execute(
                    "UPDATE questions SET announced=? WHERE announced IS NULL AND "
                    "status<>'processed'",
                    (now,),
                )
            if arrs and models_dir:
                desk.mark_announced(models_dir, [a["id"] for a in arrs], now)
            if new or done or arrs:
                state["questions"] = now
        hours = float(params["questions.answer_digest_hours"])
        if hours > 0 and now - float(state.get("answers", 0)) >= hours * HOUR_S:
            rows = db.execute(
                "SELECT a.*, q.title, q.options FROM question_answers a JOIN questions q ON "
                "q.id=a.question_id WHERE a.notified IS NULL AND a.replaced_by IS NULL "
                "ORDER BY a.time"
            ).fetchall()
            if rows:
                lines = [f"{len(rows)} new answers on the Desk:", ""]
                for r in rows:
                    opts = json.loads(r["options"])
                    c = r["choice"]
                    chosen = (
                        f"anders: {r['other']}"
                        if c == OTHER
                        else opts[c]
                        if c is not None and 0 <= c < len(opts)
                        else "—"
                    )
                    lines.append(
                        f"- {r['title']} — {r['name']}: {chosen}"
                        + (f"\n  “{r['comment']}”" if r["comment"] else "")
                        + f"\n  {base_url}/#/questions/{r['question_id']}"
                    )
                for u in _people(auth, _names(str(params["questions.owners"]))):
                    send(u.email, f"Cover Studio: {len(rows)} new answers", "\n".join(lines))
                    sent["answers"] += 1
                db.execute("UPDATE question_answers SET notified=? WHERE notified IS NULL", (now,))
                state["answers"] = now
    auth.set_setting(MAIL_KEY, state)
    return sent


# ---- the routes -----------------------------------------------------------------------------


def install(app: FastAPI, auth: Any, root: Path, models_dir: Path) -> None:
    from coverengine.params import Registry

    from coverapi import mailer
    from coverapi.desk import MB
    from coverapi.security import DEFAULT_PUBLIC_URL, PUBLIC_URL_KEY, current_user

    def params() -> Any:
        return Registry.load(None).resolve()

    def db() -> Any:
        return opened(auth.path)

    with db():  # the tables exist before the first request
        pass

    def who(user: Any) -> str:
        return str(user.name or user.username)

    def decorate(q: dict[str, Any], user: Any, p: Any) -> dict[str, Any]:
        q["can_answer"] = may_answer(user, q, p) and q["status"] != "processed"
        yours = [a["id"] for a in q["answers"] if a["username"] == user.username]
        q["you_answered"] = bool(yours)
        q["your_answer"] = yours[-1] if yours else None
        return q

    @app.get("/api/questions")
    def questions_list(request: Request) -> dict[str, Any]:
        user = current_user(request)
        p = params()
        with db() as c:
            items = [decorate(q, user, p) for q in listing(c)]
        return {
            "items": items,
            "counts": {s: sum(1 for q in items if q["status"] == s) for s in STATUSES},
            "for_you": sum(
                1
                for q in items
                if q["status"] == "open" and q["can_answer"] and not q["you_answered"]
            ),
            "topics": list(TOPICS),
            "is_owner": is_owner(user, p),
            "pictures_max": int(p["desk.pictures_max"]),
        }

    @app.get("/api/questions/count")
    def questions_count(request: Request) -> dict[str, int]:
        """For the tab's badge: open questions, and those still waiting for you."""
        user = current_user(request)
        p = params()
        with db() as c:
            items = listing(c)
        mine = [
            q
            for q in items
            if q["status"] == "open"
            and may_answer(user, q, p)
            and not any(a["username"] == user.username for a in q["answers"])
        ]
        return {"open": sum(1 for q in items if q["status"] == "open"), "for_you": len(mine)}

    @app.get("/api/questions/answers")
    def questions_answers(request: Request, since: float = 0.0) -> dict[str, Any]:
        """The answers given after `since` (epoch seconds): for the daily processing."""
        user = current_user(request)
        if not (is_owner(user, params()) or user.may("admin")):
            raise HTTPException(403, "only the owner (questions.owners) or an admin")
        with db() as c:
            return {"since": since, "answers": answers_since(c, since)}

    @app.get("/api/questions/{qid}")
    def questions_one(qid: int, request: Request) -> dict[str, Any]:
        user = current_user(request)
        with db() as c:
            return decorate(get(c, qid), user, params())

    @app.get("/api/questions/{qid}/pictures/{name}")
    def questions_picture(qid: int, name: str, request: Request) -> FileResponse:
        current_user(request)
        path = picture_path(root, qid, name)
        if path is None:
            raise HTTPException(404, "no such picture")
        return FileResponse(path, media_type="image/png")

    @app.post("/api/questions")
    def questions_add(q: QuestionIn, request: Request) -> dict[str, Any]:
        user = current_user(request)
        if not (is_owner(user, params()) or user.may("admin")):
            raise HTTPException(403, "only the owner (questions.owners) or an admin")
        with db() as c:
            qid, _ = add_question(
                c, {**q.model_dump(), "source": "studio"}, user.username, models_dir
            )
            return decorate(get(c, qid), user, params())

    @app.post("/api/questions/{qid}/pictures")
    async def questions_pictures(
        qid: int,
        request: Request,
        files: list[UploadFile] = File(...),  # noqa: B008 - FastAPI's way
    ) -> dict[str, Any]:
        user = current_user(request)
        p = params()
        with db() as c:
            row = _row(c, qid)
        if not may_answer(user, row, p):
            raise HTTPException(403, "only the people this question is for, or an admin")
        most = int(p["desk.pictures_max"])
        if not files or len(files) > most:
            raise HTTPException(400, f"send 1 to {most} pictures")
        limit = int(float(p["desk.picture_max_mb"]) * MB)
        datas = [await f.read(limit + 1) for f in files]
        return {"pictures": [save_picture(root, qid, d, p) for d in datas]}

    @app.post("/api/questions/{qid}/answer")
    def questions_answer(qid: int, a: AnswerIn, request: Request) -> dict[str, Any]:
        user = current_user(request)
        p = params()
        if len(a.pictures) > int(p["desk.pictures_max"]):
            raise HTTPException(400, f"at most {int(p['desk.pictures_max'])} pictures")
        with db() as c:
            if not may_answer(user, _row(c, qid), p):
                raise HTTPException(403, "only the people this question is for, or an admin")
            out = answer(c, root, qid, a, user.username, who(user))
        auth.log(user, "question answered", {"question": qid, "choice": a.choice})
        return decorate(out, user, p)

    def owner_only(request: Request) -> Any:
        user = current_user(request)
        if not is_owner(user, params()):
            raise HTTPException(403, "only the owner (questions.owners)")
        return user

    @app.post("/api/questions/{qid}/final")
    def questions_final(qid: int, f: FinalIn, request: Request) -> dict[str, Any]:
        user = owner_only(request)
        with db() as c:
            return decorate(mark_final(c, qid, f.answer_id, who(user)), user, params())

    @app.post("/api/questions/{qid}/done")
    def questions_done(qid: int, n: NoteIn, request: Request) -> dict[str, Any]:
        user = owner_only(request)
        with db() as c:
            return decorate(mark_done(c, qid, n.note, who(user)), user, params())

    @app.post("/api/questions/{qid}/reopen")
    def questions_reopen(qid: int, request: Request) -> dict[str, Any]:
        user = owner_only(request)
        with db() as c:
            return decorate(reopen(c, qid, who(user)), user, params())

    def due() -> dict[str, int]:
        if not mailer.configured(auth):
            return {"questions": 0, "answers": 0}
        base = str(auth.setting(PUBLIC_URL_KEY, DEFAULT_PUBLIC_URL)).rstrip("/")
        return question_mails(
            auth,
            params(),
            base,
            lambda to, subject, text: mailer.send(auth, to, subject, text),
            models_dir,
        )

    def mail_loop() -> None:
        time.sleep(FIRST_MAIL_S)
        while True:
            try:
                due()
            except Exception:  # noqa: BLE001 - try again in an hour
                pass
            time.sleep(HOUR_S)

    app.state.question_mails = due
    threading.Thread(target=mail_loop, daemon=True, name="question-mails").start()
