"""The server's watchdog (ADR-048, ADR-153): every 10 minutes from cron. One mail per problem,
not one per check:

    COVER_DATA_DIR=~/cover-data uv run python scripts/watchdog.py

Each distinct problem has a key, its kind plus its subject (`disk`, `service:caddy`,
`failed-unit:x.service`, `ai:budget_80`). For each key the admin gets one mail when it starts,
at most one reminder per REMIND_HOURS (24) while it lasts ("nog steeds sinds <datum>"), and one
mail when it is resolved ("opgelost"). A problem counts as resolved only after CLEAR_RUNS checks
in a row without it, and the disk only once it is DISK_CLEAR_MARGIN_GB above its limit, so a
value hovering round a limit does not mail on every swing. The open problems live in
<data>/watchdog.json; the studio shows them to admins as a red banner (GET /api/admin/problems).

Checks: the app answers (locally and over https), the cover-web, caddy and fail2ban services
run, disk space, the certificate's remaining days, the age of the last backup, failed systemd
services, errors of the automatic updates, a reboot that waits too long, the AI's spend. Mails go
through the outbox (`coverapi.mailer.queue`, ADR-129: retried until the SMTP server accepts
them) to `alert_email`. Every event is also written to <data>/alerts.log.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

DATA = Path(os.environ.get("COVER_DATA_DIR", Path.home() / "cover-data"))
BACKUPS = Path(os.environ.get("BACKUP_DIR", Path.home() / "backups"))
STATE = DATA / "watchdog.json"
LOG = DATA / "alerts.log"
PUBLIC_HOST = "covers.suns.nu"
ALERT_TO = "rick@s2dio.industries"
# The disk (ADR-153): a problem once the next nightly backup no longer fits next to the ones
# kept: backup.sh's own floor (BACKUP_MIN_FREE_GB, 20) plus the newest archive (4.4 GB on
# 3 Nov 2026), so about 25 GB. The share of 25 % used until then (40 GB of 161) fired with
# 36-40 GB free, which is plenty for archives of 4.4 GB: 53 mails from 21 Oct.
BACKUP_MIN_FREE_GB = float(os.environ.get("BACKUP_MIN_FREE_GB", "20"))
DISK_ARCHIVE_GB_DEFAULT = 5.0  # no archive yet: assume one of about this size
DISK_CLEAR_MARGIN_GB = 5.0  # resolved only this far above the limit
CERT_DAYS_MIN = 14
BACKUP_HOURS_MAX = 26
REBOOT_DAYS_MAX = 7
REMIND_HOURS = 24
CLEAR_RUNS = 2  # checks in a row without the problem before it is resolved
STATE_VERSION = 2

Problem = tuple[str, str, str]  # kind, subject ("" when the kind is the whole story), text


def key(kind: str, subject: str = "") -> str:
    return f"{kind}:{subject}" if subject else kind


def backup_status(data: Path) -> dict[str, str]:
    """Report both stale backups and failed off-server copies without side effects."""
    bad: dict[str, str] = {}
    last = data / "last_backup.txt"
    age = (time.time() - last.stat().st_mtime) / 3600 if last.is_file() else 1e9
    if age > BACKUP_HOURS_MAX:
        bad["backup"] = f"the last backup is {age:.0f} hours old"
    elif "FAILED" in last.read_text(encoding="utf-8", errors="replace"):
        bad["backup"] = "the last backup failed: " + last.read_text(encoding="utf-8").strip()
    return bad


def disk_limit_gb(backups: Path = BACKUPS) -> float:
    """Free space the next backup needs without removing an older archive (backup.sh)."""
    archives = sorted(backups.glob("cover-data-*.tar.gz"), key=lambda p: p.stat().st_mtime)
    newest = archives[-1].stat().st_size / 1e9 if archives else DISK_ARCHIVE_GB_DEFAULT
    return BACKUP_MIN_FREE_GB + newest


def disk_problem(free_gb: float, total_gb: float, limit_gb: float, is_open: bool) -> str | None:
    """Below the limit is a problem; an open one lasts until DISK_CLEAR_MARGIN_GB above it."""
    if free_gb < limit_gb + (DISK_CLEAR_MARGIN_GB if is_open else 0.0):
        return (
            f"only {free_gb:.0f} GB free of {total_gb:.0f} GB; the next backup needs "
            f"{limit_gb:.0f} GB"
        )
    return None


def _get(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310 - fixed addresses
            return int(r.status)
    except Exception:  # noqa: BLE001
        return 0


def _active(unit: str) -> bool:
    r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
    return r.stdout.strip() == "active"


def ai_costs() -> dict[str, str]:
    """The AI's spend this month (ADR-078): mail at 50 % and 80 % of the budget, at a spike in
    one hour, and when paid calls have stopped because the budget is used up."""
    try:
        from coverengine import spend
        from coverengine.params import Registry

        s = spend.status(Registry.load(None).resolve())
    except Exception as exc:  # noqa: BLE001 - a broken ledger is a problem to report too
        return {"ledger": f"the AI cost ledger cannot be read: {exc}"}
    out: dict[str, str] = {}
    top = ", ".join(f"{k} €{v}" for k, v in list(s["by_model"].items())[:3])
    if s["stopped"]:
        out["budget_stop"] = (
            f"AI calls STOPPED: €{s['month_eur']} of the €{s['budget_eur']} "
            f"month budget used ({top}); raise spend.budget_eur_month"
        )
    elif s["passed_pct"]:
        out[f"budget_{int(s['passed_pct'])}"] = (
            f"AI costs this month €{s['month_eur']}: {s['pct']} % of the €{s['budget_eur']} "
            f"budget ({top})"
        )
    if s["spike"]:
        out["spike"] = f"AI costs €{s['hour_eur']} in the last hour ({top})"
    return out


def checks(open_keys: set[str] | None = None) -> list[Problem]:
    """Every problem found now, as (kind, subject, text)."""
    open_keys = open_keys or set()
    bad: list[Problem] = []
    if _get("http://127.0.0.1:8080/api/health") != 200:
        bad.append(("app", "", "the app does not answer on 127.0.0.1:8080"))
    if _get(f"https://{PUBLIC_HOST}/api/health") != 200:
        bad.append(("https", "", f"https://{PUBLIC_HOST} does not answer"))
    for unit in ("cover-web", "caddy", "fail2ban"):
        if not _active(unit):
            bad.append(("service", unit, f"the service {unit} is not running"))
    disk = shutil.disk_usage(DATA)
    text = disk_problem(disk.free / 1e9, disk.total / 1e9, disk_limit_gb(), "disk" in open_keys)
    if text:
        bad.append(("disk", "", text))
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((PUBLIC_HOST, 443), timeout=15) as s:
            with ctx.wrap_socket(s, server_hostname=PUBLIC_HOST) as t:
                cert = t.getpeercert()
        end = datetime.strptime(str(cert["notAfter"]), "%b %d %H:%M:%S %Y %Z")
        days = (end.replace(tzinfo=UTC) - datetime.now(UTC)).days
        if days < CERT_DAYS_MIN:
            bad.append(("certificate", "", f"the https certificate ends in {days} days"))
    except Exception as exc:  # noqa: BLE001
        bad.append(("certificate", "", f"the https certificate cannot be read: {exc}"))
    for name, desc in backup_status(DATA).items():
        bad.append((name, "", desc))
    failed = subprocess.run(
        ["systemctl", "--failed", "--no-legend", "--plain"], capture_output=True, text=True
    ).stdout.split()
    for unit in [u for u in failed if u.endswith((".service", ".timer", ".mount"))]:
        bad.append(("failed-unit", unit, f"the systemd unit {unit} failed"))
    upgrades = "/var/log/unattended-upgrades/unattended-upgrades.log"  # root only: via sudo
    r = subprocess.run(
        ["sudo", "-n", "tail", "-n", "200", upgrades], capture_output=True, text=True
    )
    if r.returncode == 0:
        if any(" ERROR " in line for line in r.stdout.splitlines()):
            bad.append(
                ("updates", "", "the automatic updates report errors (unattended-upgrades.log)")
            )
    reboot = Path("/var/run/reboot-required")
    if reboot.is_file() and (time.time() - reboot.stat().st_mtime) / 86400 > REBOOT_DAYS_MAX:
        bad.append(
            ("reboot", "", "a reboot for security updates has been waiting for more than a week")
        )
    for subject, desc in ai_costs().items():
        bad.append(("ai", subject, desc))
    return bad


# ---- state and mail --------------------------------------------------------------------------


def load_state(path: Path) -> dict[str, dict[str, Any]]:
    """The open problems by key. Reads the format before ADR-153 too ({name: {since, told,
    text}}), so a problem open at the switch is not mailed again as new."""
    try:  # an empty or broken state (the full disk of 12 Oct 2026 left 0 bytes) starts afresh
        raw = json.loads(path.read_text()) if path.is_file() else {}
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    if raw.get("version") == STATE_VERSION:
        return {k: v for k, v in raw.get("problems", {}).items() if isinstance(v, dict)}
    out: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, dict) and "since" in v:
            out[k] = {
                "kind": k.split(":", 1)[0],
                "subject": k.split(":", 1)[1] if ":" in k else "",
                "text": v.get("text", k),
                "since": float(v["since"]),
                "last_mail": float(v.get("told", v["since"])),
                "clear_runs": 0,
            }
    return out


def save_state(path: Path, problems: dict[str, dict[str, Any]]) -> None:
    tmp = path.with_suffix(".tmp")  # written whole, then swapped in: never half a file
    tmp.write_text(json.dumps({"version": STATE_VERSION, "problems": problems}, indent=1))
    tmp.replace(path)


def _when(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d-%m-%Y %H:%M")


Mail = Callable[[str, str, str, str], str]  # (event, subject, text, ref) -> how it went


def step(
    state: dict[str, dict[str, Any]],
    found: list[Problem],
    now: float,
    mail: Mail,
    host: str,
) -> list[str]:
    """One check round: update `state` in place, mail what changed; returns the log lines."""
    lines: list[str] = []
    stamp = time.ctime(now)
    seen: set[str] = set()
    for kind, subject, text in found:
        k = key(kind, subject)
        if k in seen:
            continue
        seen.add(k)
        p = state.get(k)
        if p is None:
            ref = f"watchdog:{k}:{int(now)}:start"
            how = mail(
                "start",
                f"Cover Studio: {text}",
                f"On {host}: {text}\n\nSince: {_when(now)}\n",
                ref,
            )
            state[k] = {
                "kind": kind, "subject": subject, "text": text,
                "since": now, "last_mail": now, "clear_runs": 0,
            }  # fmt: skip
            lines.append(f"{stamp} PROBLEM {k}: {text} ({how})")
            continue
        p.update(text=text, clear_runs=0)
        if now - float(p.get("last_mail", 0)) >= REMIND_HOURS * 3600:
            since = _when(float(p["since"]))
            ref = f"watchdog:{k}:{int(p['since'])}:remind:{int(now)}"
            how = mail(
                "remind",
                f"Cover Studio: nog steeds sinds {since}: {text}",
                f"On {host}: {text}\n\nNog steeds, sinds {since}.\n",
                ref,
            )
            p["last_mail"] = now
            lines.append(f"{stamp} STILL {k} since {since}: {text} ({how})")
    for k in [k for k in state if k not in seen]:
        p = state[k]
        p["clear_runs"] = int(p.get("clear_runs", 0)) + 1
        if p["clear_runs"] < CLEAR_RUNS:
            continue
        since = _when(float(p["since"]))
        ref = f"watchdog:{k}:{int(p['since'])}:solved"
        how = mail(
            "solved",
            f"Cover Studio: opgelost: {p['text']}",
            f"On {host}: opgelost (open sinds {since}).\n\n{p['text']}\n",
            ref,
        )
        lines.append(f"{stamp} SOLVED {k}: {p['text']} ({how})")
        del state[k]
    return lines


def outbox_mail(event: str, subject: str, text: str, ref: str) -> str:
    """Through the outbox (ADR-129): queued, tried at once, retried by the app until the SMTP
    server accepts it. `ref` keeps a repeated round from queueing the same mail twice."""
    from coverapi import mailer
    from coverapi.auth import Auth

    auth = Auth(DATA / "app.db")
    to = auth.setting("alert_email", ALERT_TO)
    if not mailer.configured(auth):
        return "no mail server set"
    try:
        oid = mailer.queue(auth, to, subject, text, kind="watchdog", ref=ref)
    except Exception as exc:  # noqa: BLE001
        return f"mail failed: {exc}"
    if oid is None:
        return "already in the outbox"
    return f"mailed {to}" if mailer.is_sent(auth, oid) else f"queued for {to} (outbox #{oid})"


def main() -> int:
    state = load_state(STATE)
    now = time.time()
    lines = step(state, checks(set(state)), now, outbox_mail, socket.gethostname())
    save_state(STATE, state)
    if lines:
        with LOG.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
