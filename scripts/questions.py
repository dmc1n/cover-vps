"""The Desk's questions from the command line (ADR-109): for the daily processing of the answers.

    COVER_DATA_DIR=~/cover-data uv run python scripts/questions.py COMMAND ...

Commands:
    list [--status open|answered|processed] [--topic T]   the questions, one line each
    show ID                                  a question with its context and every answer
    new [--since 2026-10-09T18:00 | EPOCH] [--json]
                                             the answers given since then (default: since the last
                                             `ack`); replaced answers are marked
    ack [--at EPOCH]                         remember "seen until now" for the next `new`
    done ID "note" [--by NAME]               mark processed, with what was done (the answerer
                                             sees the note at the Desk and in the next digest)
    reopen ID [--by NAME]                    back to open / answered
    add FILE.json [--by NAME]                a new question (title, text, topic, context, models,
                                             options, answerers, key, pictures: [{path, caption}])
    import [--dry-run] [--results GLOB]      the open questions of 9 Oct 2026: the rejection
                                             agents' doubts and docs/QUESTIONS.md; run it again
                                             and nothing is added twice
    mail                                     send the digests that are due now (the app does this
                                             itself every hour)

Works straight on <data>/app.db, the same tables the studio uses. Only the main session runs it
on live data.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))

from coverapi import questions as Q  # noqa: E402
from fastapi import HTTPException  # noqa: E402

RESULTS = "/home/dev/cover-pattern-engine/.claude/worktrees/agent-*/out/rejections/*/results.json"
SEEN_FILE = "questions-seen.json"  # in the data folder: until when `new` has been read
MAX_IMPORT_PICTURES = 4  # compare pictures carried by one imported question


def data_dir() -> Path:
    return Path(os.environ.get("COVER_DATA_DIR", Path.home() / "cover-data")).expanduser()


def params() -> Any:
    from coverengine.params import Registry

    return Registry.load(None).resolve()


def when(t: float | None) -> str:
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t else "-"


def parse_time(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return datetime.fromisoformat(s).timestamp()


def chosen(q: dict[str, Any], a: dict[str, Any]) -> str:
    c = a["choice"]
    if c == Q.OTHER:
        return f"anders: {a['other']}"
    if c is not None and 0 <= c < len(q["options"]):
        return f"{chr(97 + c)}) {q['options'][c]}"
    return "(no option)"


# ---- commands -------------------------------------------------------------------------------


def cmd_list(db: Any, args: argparse.Namespace) -> int:
    for q in Q.listing(db):
        if args.status and q["status"] != args.status:
            continue
        if args.topic and q["topic"] != args.topic:
            continue
        n = len(q["answers"])
        print(f"{q['id']:>4}  {q['status']:<9}  {q['topic']:<9}  {n} ans  {q['title']}")
    return 0


def cmd_show(db: Any, args: argparse.Namespace) -> int:
    q = Q.get(db, args.id)
    print(f"#{q['id']} [{q['status']}] [{q['topic']}] {q['title']}\n")
    print(q["text"])
    if q["context"]:
        print(f"\nContext: {q['context']}")
    if q["models"]:
        print("Covers: " + ", ".join(f"{m['code']} ({m['id']})" for m in q["models"]))
    for i, o in enumerate(q["options"]):
        print(f"  {chr(97 + i)}) {o}")
    for p in q["pictures"]:
        print(f"  picture: {Q.folder(data_dir(), q['id']) / p['name']}  {p['caption']}")
    print(f"\nAnswers ({len(q['answers'])}):")
    for a in q["answers"]:
        final = "  [FINAL]" if q["final_answer"] == a["id"] else ""
        print(f"  #{a['id']} {a['name']} {when(a['time'])}: {chosen(q, a)}{final}")
        if a["comment"]:
            print(f"      “{a['comment']}”")
        for p in a["pictures"]:
            print(f"      picture: {Q.folder(data_dir(), q['id']) / p}")
    if q["processed"]:
        p = q["processed"]
        print(f"\nProcessed {when(p['time'])} by {p['by']}: {p['note']}")
    return 0


def _seen() -> float:
    f = data_dir() / SEEN_FILE
    try:
        return float(json.loads(f.read_text())["until"])
    except (OSError, ValueError, KeyError):
        return 0.0


def cmd_new(db: Any, args: argparse.Namespace) -> int:
    since = parse_time(args.since) if args.since else _seen()
    rows = Q.answers_since(db, since)
    if args.json:
        print(
            json.dumps(
                {"since": since, "now": time.time(), "answers": rows}, indent=1, ensure_ascii=False
            )
        )
        return 0
    print(f"{len(rows)} answers since {when(since) if since else 'the start'}")
    for a in rows:
        flags = " [replaced later]" if a["replaced"] else ""
        flags += " [FINAL]" if a["final"] else ""
        print(f"\n#{a['question_id']} {a['question']}  ({a['question_status']})")
        print(f"  {a['name']} {when(a['time'])}: {a['chosen'] or '(no option)'}{flags}")
        if a["comment"]:
            print(f"  “{a['comment']}”")
        if a["pictures"]:
            print(f"  pictures: {', '.join(a['pictures'])}")
    return 0


def cmd_ack(db: Any, args: argparse.Namespace) -> int:
    at = parse_time(args.at) if args.at else time.time()
    (data_dir() / SEEN_FILE).write_text(json.dumps({"until": at}) + "\n")
    print(f"seen until {when(at)}")
    return 0


def cmd_done(db: Any, args: argparse.Namespace) -> int:
    q = Q.mark_done(db, args.id, args.note, args.by)
    print(f"#{q['id']} processed: {args.note}")
    return 0


def cmd_reopen(db: Any, args: argparse.Namespace) -> int:
    q = Q.reopen(db, args.id, args.by)
    print(f"#{q['id']} is {q['status']} again")
    return 0


def add_one(db: Any, spec: dict[str, Any], by: str, base: Path | None = None) -> tuple[int, bool]:
    root = data_dir()
    qid, made = Q.add_question(db, spec, by, root / "models")
    if made:
        p = params()
        for pic in spec.get("pictures") or []:
            path = Path(pic["path"])
            if not path.is_absolute() and base is not None:
                path = base / path
            if path.is_file():
                Q.add_question_picture(
                    db, root, qid, path.read_bytes(), pic.get("caption", ""), by, p
                )
    return qid, made


def cmd_add(db: Any, args: argparse.Namespace) -> int:
    path = Path(args.file)
    spec = json.loads(path.read_text(encoding="utf-8"))
    qid, made = add_one(db, spec, args.by, path.parent)
    print(f"#{qid} {'added' if made else 'exists already (same key)'}")
    return 0


def _row_pictures(r: dict[str, Any], wt: Path) -> list[tuple[str, str]]:
    """A doubt row's pictures: the agent's before/after with Rens's marks and the plan and side
    views, else the staged cover."""
    m = r["model"]
    out = []
    if r.get("compare"):
        out.append(
            (
                str(r["compare"]),
                f"{m}: Rens' markering, de hoes ervoor en de klaargezette hoes, met aanzichten",
            )
        )
    staging = r.get("staging")
    if staging and not r.get("compare"):
        sd = Path(staging) if Path(staging).is_absolute() else wt / staging
        out.append((str(sd / "cover.png"), f"{m}: de klaargezette hoes"))
    return out


def doubt_questions(pattern: str) -> list[dict[str, Any]]:
    """The rejection agents' doubts as questions: one per distinct question, the covers that
    share it together; question 71 (vents on inner walls) left out, it was answered."""
    import questions_seed as seed

    rows: list[tuple[str, dict[str, Any], Path]] = []
    for f in sorted(glob.glob(pattern)):
        worktree = Path(f).parents[3]  # <worktree>/out/rejections/<group>/results.json
        for r in json.loads(Path(f).read_text(encoding="utf-8")):
            if r.get("status") != "doubt" or not r.get("question_nl"):
                continue
            text = str(r["question_nl"]).lower()
            options = [str(o) for o in r.get("options_nl") or []]
            if seed.SKIP_TEXT_MARK in text or any(seed.SKIP_OPTION_MARK in o for o in options):
                continue
            rows.append((str(r["model"]), r, worktree))
    same = {m: " ".join(str(r["question_nl"]).split()).lower() for m, r, _ in rows}
    groups: dict[str, dict[str, Any]] = {}
    for model, r, wt in rows:
        anchor = seed.JOIN.get(model, model)
        g = groups.setdefault(same.get(anchor, same[model]), {"lead": None, "rows": []})
        g["rows"].append((model, r, wt))
        if model not in seed.JOIN and g["lead"] is None:
            g["lead"] = (model, str(r["question_nl"]).strip(), list(r.get("options_nl") or []))
    for g in groups.values():
        if g["lead"] is None:  # only "same as …" rows: the first one speaks
            m, r, _ = g["rows"][0]
            g["lead"] = (m, str(r["question_nl"]).strip(), list(r.get("options_nl") or []))
        g["lead"], g["text"], g["options"] = g["lead"]
    out = []
    for g in groups.values():
        models = [m for m, _, _ in g["rows"]]
        lead = (
            g["lead"]
            if g["lead"] in seed.DOUBTS
            else next((m for m in models if m in seed.DOUBTS), g["lead"])
        )
        title, topic = seed.DOUBTS.get(lead, (g["text"][:80], "shape"))
        context = []
        pictures = []
        for m, r, wt in g["rows"]:
            if r.get("answer_nl"):
                context.append(f"{m}: wat er klaarstaat: {r['answer_nl']}")
            if r.get("what_changed"):
                context.append(f"{m} (technisch): {r['what_changed']}")
            for path, caption in _row_pictures(r, wt) + seed.EXTRA_PICTURES.get(m, []):
                p = Path(path) if Path(path).is_absolute() else wt / path
                if p.is_file() and len(pictures) < MAX_IMPORT_PICTURES:
                    pictures.append({"path": str(p), "caption": caption})
        models += [x for x in seed.EXTRA_MODELS.get(lead, []) if x not in models]
        out.append(
            {
                "key": f"doubt:{lead}",
                "title": title,
                "text": g["text"],
                "topic": topic,
                "options": g["options"][: Q.MAX_OPTIONS],
                "models": models,
                "context": "\n\n".join(context),
                "pictures": pictures,
                "source": "rejection agents' results.json (8 Oct 2026)",
            }
        )
    return out


def cmd_import(db: Any, args: argparse.Namespace) -> int:
    import questions_seed as seed

    specs = doubt_questions(args.results) + list(seed.FROM_QUESTIONS_MD)
    made = 0
    for spec in specs:
        if args.dry_run:
            exists = db.execute("SELECT id FROM questions WHERE key=?", (spec["key"],)).fetchone()
            n = len(spec.get("pictures") or [])
            print(
                f"{'exists' if exists else 'new   '}  {spec['topic']:<9} "
                f"{len(spec.get('models') or []):>2} covers {n} pics  {spec['title']}"
            )
            made += 0 if exists else 1
            continue
        qid, new = add_one(db, spec, args.by)
        made += int(new)
        print(f"{'added ' if new else 'exists'} #{qid:<4} {spec['title']}")
    word = "would be added" if args.dry_run else "added"
    print(f"\n{made} {word}, {len(specs) - made} there already ({len(specs)} in all)")
    return 0


def cmd_mail(db: Any, args: argparse.Namespace) -> int:
    from coverapi import mailer
    from coverapi.auth import Auth
    from coverapi.security import DEFAULT_PUBLIC_URL, PUBLIC_URL_KEY

    auth = Auth(data_dir() / "app.db")
    if not mailer.configured(auth):
        print("no mail server set (admin page, Mail)")
        return 1
    base = str(auth.setting(PUBLIC_URL_KEY, DEFAULT_PUBLIC_URL)).rstrip("/")
    sent = Q.question_mails(auth, params(), base, lambda to, s, t: mailer.send(auth, to, s, t))
    print(f"sent: {sent}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list")
    s.add_argument("--status", choices=Q.STATUSES)
    s.add_argument("--topic", choices=Q.TOPICS)
    s = sub.add_parser("show")
    s.add_argument("id", type=int)
    s = sub.add_parser("new")
    s.add_argument("--since")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("ack")
    s.add_argument("--at")
    s = sub.add_parser("done")
    s.add_argument("id", type=int)
    s.add_argument("note")
    s.add_argument("--by", default="Claude")
    s = sub.add_parser("reopen")
    s.add_argument("id", type=int)
    s.add_argument("--by", default="Claude")
    s = sub.add_parser("add")
    s.add_argument("file")
    s.add_argument("--by", default="Claude")
    s = sub.add_parser("import")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--results", default=RESULTS)
    s.add_argument("--by", default="Claude")
    sub.add_parser("mail")
    args = ap.parse_args(argv)
    db_path = data_dir() / "app.db"
    if not db_path.is_file():
        print(f"no {db_path} (set COVER_DATA_DIR)", file=sys.stderr)
        return 2
    fn = globals()[f"cmd_{args.cmd}"]
    try:
        if args.cmd == "mail":
            return int(fn(None, args))
        with Q.opened(db_path) as db:
            return int(fn(db, args))
    except HTTPException as exc:
        print(f"error: {exc.detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
