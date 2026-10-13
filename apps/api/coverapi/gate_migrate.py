"""Read-only plans and explicit applications of the Desk gate migrations (ADR-128)."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from coverengine.catalogue import no_cover

from coverapi import approval, desk


@dataclass(frozen=True)
class Row:
    model_id: str
    action: str
    reason: str
    desk_status: str
    catalogue_status: str


def _covers(models: Path) -> list[Path]:
    return sorted(d for d in models.glob("*") if (d / "cover.json").is_file() and not no_cover(d))


def _status(d: Path) -> str:
    status = str(desk._read(d / "desk.json").get("status") or "new")
    return desk.WAITING if status == "new" and (d / "check.json").is_file() else status


def _row(d: Path, action: str, reason: str) -> Row:
    return Row(
        d.name, action, reason, _status(d), str(desk._read(d / "cover.json").get("status", "draft"))
    )


def plan_definitive(models: Path) -> list[Row]:
    """Report definitive approvals without normalising or writing Desk state."""
    rows = []
    for d in _covers(models):
        if not (d / "approval.json").is_file():
            continue
        old = approval.legacy(d)
        if d.name.startswith(("drawing-", "arr-")):
            # gated before ADR-128 too: a definitive approval never opened their DXF
            action = "already gated"
        elif _status(d) in desk.DONE:
            action = "keep"
        elif _status(d) == "rejected":
            action = "keep (rejected)"  # a person said no at the Desk: never overruled
        else:
            action = "grandfather" if old and old["valid"] else "stale"
        rows.append(_row(d, action, "definitive approval"))
    return rows


def _orders(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='orders'"
        ).fetchone():
            return {}
        rows = db.execute("SELECT id, status, model_id FROM orders ORDER BY id").fetchall()
    out: dict[str, str] = {}
    for ident, status, model in rows:
        if status in ("in_production", "sewn", "shipped", "returned"):
            out.setdefault(str(model), f"order {ident} {status}")
    return out


def plan_gate_all(models: Path, orders_db: Path | None) -> list[Row]:
    """Which previously ungated covers need approval, preserving covers already in use."""
    orders = _orders(orders_db)
    rows = []
    for d in _covers(models):
        st = desk._read(d / "desk.json")
        cut = desk.cut_fingerprint(d)
        catalogue = desk._read(d / "cover.json").get("status")
        action, reason = "send", "newly locked"
        if d.name.startswith(("drawing-", "arr-")):
            action, reason = "already gated", "previous Desk gate"
        elif cut is None:
            action, reason = "not built", "no cut.dxf"
        elif (
            _status(d) in desk.DONE
            and not (st.get("approved") or {}).get("cut")
            and desk.cut_newer(d, st.get("approved") or {})
        ):
            # the cut file was written after that approval: it reopens, never blessed
            action, reason = "send", "cut file newer than its Desk approval"
        elif _status(d) in desk.DONE and not (st.get("approved") or {}).get("cut"):
            action, reason = "fingerprint", "earlier Desk approval"
        elif _status(d) in desk.DONE and (st.get("approved") or {}).get("cut") == cut:
            action, reason = "keep", "current Desk approval"
        elif _status(d) in desk.DONE:
            # approved for another cut file: it reopens by itself (ADR-120); never blessed here
            action, reason = "send", "changed after its Desk approval"
        elif _status(d) == "rejected":
            action, reason = "keep (rejected)", "rejected at the Desk"
        else:
            old = approval.legacy(d)
            if old and old["valid"]:
                action, reason = "grandfather", "definitive approval"
            elif catalogue in ("production", "checked"):
                action = "grandfather"
                reason = "produced" if catalogue == "production" else "in active use"
            elif d.name in orders:
                action, reason = "grandfather", orders[d.name]
            elif _status(d) == desk.WAITING and st.get("sent"):
                action, reason = "keep (waiting)", "already at the Desk"
        rows.append(_row(d, action, reason))
    return rows


def grandfather(d: Path, by_reason: str, *, who: str = "the studio", note: str) -> bool:
    """Preserve an existing cutting permission with its provenance, once per cut."""
    with desk._lock:
        st = desk._read(d / "desk.json")
        cut = desk.cut_fingerprint(d)
        if cut is None:
            return False
        if st.get("status") in desk.DONE and (st.get("approved") or {}).get("cut") == cut:
            return False
        if st.get("status") in (*desk.DONE, "rejected"):
            return False  # a rejection, or an approval of another cut: a person decides
        old = approval.legacy(d) if by_reason == "definitive approval" else None
        if by_reason == "definitive approval" and not (old and old["valid"]):
            return False
        now = time.time()
        before = {k: v for k, v in st.items() if k != "history"}
        produced = by_reason == "produced" or (
            by_reason.startswith("order ")
            and by_reason.split()[-1] in ("shipped", "sewn", "returned")
        )
        st["status"] = "produced" if produced else "approved"
        st["approved"] = {
            "by": old.get("name", who) if old else who,
            "time": old.get("time", now) if old else now,
            "cut": cut,
            "grandfathered": by_reason,
        }
        stamped = {
            name: hashlib.sha256(p.read_bytes()).hexdigest()[:20]
            for name in approval.STAMPED
            if (p := d / approval.APPROVED_DIR / name).is_file()
        }
        if stamped:
            st["approved"]["stamped"] = stamped
        if produced:
            st["produced"] = {"by": who, "time": now}
        st["approved_fingerprints"] = list(
            dict.fromkeys([*st.get("approved_fingerprints", []), cut])
        )
        st.pop("rejected", None)
        entry = {
            "action": "grandfathered approval",
            "by": "the studio",
            "time": now,
            "text": note,
            "cut": cut,
            "before": before,
        }
        st.setdefault("history", []).append(entry)
        desk._write(d / "desk.json", st)
        desk._log(d.parent.parent / "learning", d, entry)
        return True


def send_to_desk(d: Path, who: str, note: str) -> None:
    desk.send(d, SimpleNamespace(name=who, username=who), d.parent.parent / "learning", note)


def apply_definitive(models: Path, rows: list[Row]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        d = models / row.model_id
        if row.action != "grandfather":
            continue
        old = approval.legacy(d)
        if not old or not old["valid"]:
            continue
        name = old.get("name", "the studio")
        date = time.strftime("%d %b %Y", time.localtime(old.get("time", 0)))
        note = f"grandfathered from the definitive drawing approval by {name} on {date} (ADR-128)"
        if grandfather(d, row.reason, note=note):
            counts["grandfather"] += 1
    return dict(counts)


def apply_gate_all(models: Path, rows: list[Row], who: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        d = models / row.model_id
        if row.action == "grandfather":
            note = (
                f"grandfathered when every cover's DXF went behind the Desk ({row.reason}; ADR-128)"
            )
            if grandfather(d, row.reason, who=who, note=note):
                counts[row.action] += 1
        elif row.action == "fingerprint":
            with desk._lock:
                st = desk._read(d / "desk.json")
                if desk.grandfather_fingerprint(d, st):
                    desk._write(d / "desk.json", st)
                    counts[row.action] += 1
        elif row.action == "send":
            st = desk._read(d / "desk.json")
            if _status(d) in desk.DONE and (st.get("approved") or {}).get(
                "cut"
            ) == desk.cut_fingerprint(d):
                continue
            if _status(d) == desk.WAITING and st.get("sent"):
                continue
            send_to_desk(
                d,
                who,
                "put at the Desk for approval when every cover's DXF went behind it (ADR-128)",
            )
            counts[row.action] += 1
    return dict(counts)
