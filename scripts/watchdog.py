"""The server's watchdog (ADR-048): every 10 minutes from cron. Mails the admin on critical
problems, once per problem per REMIND_HOURS, and again when it is solved.

    COVER_DATA_DIR=~/cover-data uv run python scripts/watchdog.py

Checks: the app answers (locally and over https), the cover-web and caddy services run, disk
space, the certificate's remaining days, the age of the last backup, failed systemd services,
errors of the automatic updates, a reboot that waits too long. The mail goes through the SMTP
server set on the admin page, to `alert_email` (rick@s2dio.industries). Without a mail server
the problems are written to <data>/alerts.log (the admin page shows the last ones).
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
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

DATA = Path(os.environ.get("COVER_DATA_DIR", Path.home() / "cover-data"))
STATE = DATA / "watchdog.json"
LOG = DATA / "alerts.log"
PUBLIC_HOST = "covers.suns.nu"
ALERT_TO = "rick@s2dio.industries"
DISK_FREE_MIN = 0.15  # share of the disk
CERT_DAYS_MIN = 14
BACKUP_HOURS_MAX = 26
REBOOT_DAYS_MAX = 7
REMIND_HOURS = 6


def _get(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310 - fixed addresses
            return int(r.status)
    except Exception:  # noqa: BLE001
        return 0


def _active(unit: str) -> bool:
    r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
    return r.stdout.strip() == "active"


def checks() -> dict[str, str]:
    """Problem name -> description, for every problem found now."""
    bad: dict[str, str] = {}
    if _get("http://127.0.0.1:8080/api/health") != 200:
        bad["app"] = "the app does not answer on 127.0.0.1:8080"
    if _get(f"https://{PUBLIC_HOST}/api/health") != 200:
        bad["https"] = f"https://{PUBLIC_HOST} does not answer"
    for unit in ("cover-web", "caddy", "fail2ban"):
        if not _active(unit):
            bad[f"service-{unit}"] = f"the service {unit} is not running"
    disk = shutil.disk_usage(DATA)
    if disk.free / disk.total < DISK_FREE_MIN:
        bad["disk"] = f"only {disk.free / 1e9:.0f} GB free of {disk.total / 1e9:.0f} GB"
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((PUBLIC_HOST, 443), timeout=15) as s:
            with ctx.wrap_socket(s, server_hostname=PUBLIC_HOST) as t:
                cert = t.getpeercert()
        end = datetime.strptime(str(cert["notAfter"]), "%b %d %H:%M:%S %Y %Z")
        days = (end.replace(tzinfo=UTC) - datetime.now(UTC)).days
        if days < CERT_DAYS_MIN:
            bad["certificate"] = f"the https certificate ends in {days} days"
    except Exception as exc:  # noqa: BLE001
        bad["certificate"] = f"the https certificate cannot be read: {exc}"
    last = DATA / "last_backup.txt"
    age = (time.time() - last.stat().st_mtime) / 3600 if last.is_file() else 1e9
    if age > BACKUP_HOURS_MAX:
        bad["backup"] = f"the last backup is {age:.0f} hours old"
    failed = subprocess.run(
        ["systemctl", "--failed", "--no-legend", "--plain"], capture_output=True, text=True
    ).stdout.split()
    units = [u for u in failed if u.endswith((".service", ".timer", ".mount"))]
    if units:
        bad["failed-units"] = f"failed services: {', '.join(units)}"
    upgrades = "/var/log/unattended-upgrades/unattended-upgrades.log"  # root only: via sudo
    r = subprocess.run(
        ["sudo", "-n", "tail", "-n", "200", upgrades], capture_output=True, text=True
    )
    if r.returncode == 0:
        if any(" ERROR " in line for line in r.stdout.splitlines()):
            bad["updates"] = "the automatic updates report errors (unattended-upgrades.log)"
    reboot = Path("/var/run/reboot-required")
    if reboot.is_file() and (time.time() - reboot.stat().st_mtime) / 86400 > REBOOT_DAYS_MAX:
        bad["reboot"] = "a reboot for security updates has been waiting for more than a week"
    return bad


def notify(subject: str, text: str) -> str:
    from coverapi import mailer
    from coverapi.auth import Auth

    auth = Auth(DATA / "app.db")
    to = auth.setting("alert_email", ALERT_TO)
    if not mailer.configured(auth):
        return "no mail server set"
    try:
        mailer.send(auth, to, subject, text)
        return f"mailed {to}"
    except Exception as exc:  # noqa: BLE001
        return f"mail failed: {exc}"


def main() -> int:
    state = json.loads(STATE.read_text()) if STATE.is_file() else {}
    now = time.time()
    bad = checks()
    host = socket.gethostname()
    lines = []
    for name, text in bad.items():
        seen = state.get(name)
        if seen is None or now - seen.get("told", 0) > REMIND_HOURS * 3600:
            how = notify(f"Cover Studio: {text}", f"On {host}: {text}\n\nTime: {time.ctime()}\n")
            state[name] = {"since": seen["since"] if seen else now, "told": now, "text": text}
            lines.append(f"{time.ctime()} PROBLEM {name}: {text} ({how})")
    for name in [n for n in state if n not in bad]:
        how = notify(f"Cover Studio: solved: {state[name]['text']}", f"On {host}: solved.\n")
        lines.append(f"{time.ctime()} SOLVED {name}: {state[name]['text']} ({how})")
        del state[name]
    STATE.write_text(json.dumps(state, indent=1))
    if lines:
        with LOG.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
