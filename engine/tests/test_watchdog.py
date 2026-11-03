"""The watchdog mails once per problem (ADR-153): a mail when it starts, at most one reminder a
day while it lasts ("nog steeds sinds"), one when it is resolved ("opgelost"), never on a swing
round a limit. The state survives in watchdog.json, the old format included."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/watchdog.py"
H = 3600.0


@pytest.fixture(scope="module")
def wd() -> Any:
    spec = importlib.util.spec_from_file_location("watchdog_mails", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Mails:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def __call__(self, event: str, subject: str, text: str, ref: str) -> str:
        assert ref.startswith("watchdog:")
        self.sent.append((event, subject, ref))
        return "mailed"


DISK = ("disk", "", "only 38 GB free of 161 GB")
BACKUP = ("backup", "", "the last backup failed")


def run(wd: Any, state: dict, found: list, now: float, mails: Mails) -> list[str]:
    return wd.step(state, found, now, mails, "host")


def test_one_mail_per_problem_a_reminder_a_day_and_one_when_solved(wd: Any) -> None:
    state: dict = {}
    mails = Mails()
    t0 = 1_793_000_000.0
    # every 10 minutes for 13 days, as from 21 Oct: 53 mails before, now 1 + 12 reminders
    t = t0
    while t < t0 + 13 * 24 * H:
        run(wd, state, [DISK], t, mails)
        t += 600
    events = [e for e, _, _ in mails.sent]
    assert events[0] == "start" and events.count("start") == 1
    assert events.count("remind") == 12  # day 2..13: never more than one per 24 h
    reminders = [s for e, s, _ in mails.sent if e == "remind"]
    assert all("nog steeds sinds" in s for s in reminders)
    assert wd._when(t0) in reminders[0]
    assert len({r for _, _, r in mails.sent}) == len(mails.sent)  # every outbox ref unique
    # gone for one check: not resolved yet; back again: no new "start"
    run(wd, state, [], t, mails)
    run(wd, state, [DISK], t + 600, mails)
    assert [e for e, _, _ in mails.sent].count("start") == 1
    assert state["disk"]["since"] == t0
    # gone for two checks in a row: one "opgelost"
    run(wd, state, [], t + 1200, mails)
    assert state["disk"]["clear_runs"] == 1
    run(wd, state, [], t + 1800, mails)
    assert mails.sent[-1][0] == "solved" and "opgelost" in mails.sent[-1][1]
    assert state == {}
    run(wd, state, [], t + 2400, mails)
    assert [e for e, _, _ in mails.sent].count("solved") == 1


def test_each_problem_has_its_own_key(wd: Any) -> None:
    state: dict = {}
    mails = Mails()
    found = [DISK, BACKUP, ("service", "caddy", "caddy down"), ("service", "fail2ban", "f2b")]
    run(wd, state, found, 0.0, mails)
    assert sorted(state) == ["backup", "disk", "service:caddy", "service:fail2ban"]
    assert len(mails.sent) == 4
    # the text may change (the GB count, the failure's date): still the same problem
    run(wd, state, [("disk", "", "only 37 GB free"), *found[1:]], 600.0, mails)
    assert len(mails.sent) == 4 and state["disk"]["text"] == "only 37 GB free"
    # one solved, the others go on
    run(wd, state, found[1:], 1200.0, mails)
    run(wd, state, found[1:], 1800.0, mails)
    assert mails.sent[-1][0] == "solved" and "disk" not in state and len(state) == 3


def test_disk_limit_follows_the_backups_and_has_a_margin(wd: Any, tmp_path: Path) -> None:
    archive = tmp_path / "cover-data-20261103-0230.tar.gz"
    with archive.open("wb") as fh:
        fh.truncate(4_400_000_000)  # sparse: 4.4 GB on paper
    limit = wd.disk_limit_gb(tmp_path)
    assert limit == pytest.approx(wd.BACKUP_MIN_FREE_GB + 4.4)
    assert wd.disk_problem(40, 161, limit, is_open=False) is None  # 3 Nov: 36-40 GB free is fine
    assert wd.disk_problem(36, 161, limit, is_open=False) is None
    assert "only 20 GB" in wd.disk_problem(20, 161, limit, is_open=False)
    # an open disk problem lasts until the margin above the limit: no flapping
    assert wd.disk_problem(limit + 1, 161, limit, is_open=True) is not None
    assert wd.disk_problem(limit + wd.DISK_CLEAR_MARGIN_GB, 161, limit, is_open=True) is None
    assert wd.disk_limit_gb(tmp_path / "none") == wd.BACKUP_MIN_FREE_GB + 5.0


def test_state_file_round_trip_and_the_old_format(wd: Any, tmp_path: Path) -> None:
    path = tmp_path / "watchdog.json"
    path.write_text(json.dumps({"disk": {"since": 100.0, "told": 200.0, "text": "only 38 GB"}}))
    state = wd.load_state(path)
    assert state["disk"]["since"] == 100.0 and state["disk"]["last_mail"] == 200.0
    mails = Mails()
    run(wd, state, [DISK], 300.0, mails)  # open before the switch: no new "start"
    assert mails.sent == []
    wd.save_state(path, state)
    raw = json.loads(path.read_text())
    assert raw["version"] == 2 and raw["problems"]["disk"]["since"] == 100.0
    assert wd.load_state(path) == state
    path.write_text("")
    assert wd.load_state(path) == {}
    path.write_text("[1, 2]")
    assert wd.load_state(path) == {}


def test_mails_go_through_the_outbox(wd: Any, tmp_path: Path, monkeypatch: Any) -> None:
    from coverapi import mailer

    monkeypatch.setattr(wd, "DATA", tmp_path)
    assert wd.outbox_mail("start", "s", "t", "watchdog:x:1:start") == "no mail server set"
    queued: list[tuple] = []

    def queue(auth: Any, to: str, subject: str, text: str, kind: str, ref: str) -> int:
        queued.append((to, subject, kind, ref))
        return 7

    monkeypatch.setattr(mailer, "configured", lambda auth: True)
    monkeypatch.setattr(mailer, "queue", queue)
    monkeypatch.setattr(mailer, "is_sent", lambda auth, oid: oid == 7)
    assert wd.outbox_mail("start", "Cover Studio: x", "t", "watchdog:x:1:start").startswith(
        "mailed"
    )
    assert queued == [(wd.ALERT_TO, "Cover Studio: x", "watchdog", "watchdog:x:1:start")]
