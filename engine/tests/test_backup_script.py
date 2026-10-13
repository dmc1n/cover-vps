"""Backup status must distinguish local success from remote failure."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/backup.sh"


@pytest.mark.parametrize("mode", ["unset", "unknown", "copy-fails", "success", "missing"])
def test_remote_status(tmp_path, mode):
    data, backups, bins = (tmp_path / name for name in ("data", "backups", "bin"))
    data.mkdir()
    bins.mkdir()
    (data / "model.txt").write_text("local data")
    # A controlled PATH also proves missing-rclone behavior on hosts that have it.
    for name in (
        "bash",
        "date",
        "mkdir",
        "chmod",
        "mktemp",
        "rm",
        "df",
        "awk",
        "ls",
        "head",
        "du",
        "cut",
        "wc",
        "tail",
        "tar",
        "gzip",
        "mv",
        "xargs",
        "grep",
        "basename",
        "python3",
    ):
        executable = shutil.which(name)
        assert executable, name
        (bins / name).symlink_to(executable)
    if mode != "missing":
        fake = bins / "rclone"
        fake.write_text(
            "#!/bin/bash\n"
            'if [ "$1" = listremotes ]; then\n'
            + ("echo other:\n" if mode == "unknown" else "echo r2:\n")
            + "exit 0\nfi\n"
            + ("exit 9\n" if mode == "copy-fails" else "exit 0\n")
        )
        fake.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bins),
        "COVER_DATA_DIR": str(data),
        "BACKUP_DIR": str(backups),
        "BACKUP_MIN_FREE_GB": "0",
    }
    env.pop("COVER_BACKUP_REMOTE", None)
    if mode != "unset":
        env["COVER_BACKUP_REMOTE"] = "r2:bucket"
    result = subprocess.run(
        [str(bins / "bash"), str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    status = (data / "last_backup.txt").read_text()
    archives = list(backups.glob("*.tar.gz"))
    assert len(archives) == 1
    assert subprocess.run([str(bins / "gzip"), "-t", str(archives[0])], check=False).returncode == 0
    assert not list(backups.glob("*.partial"))
    if mode in ("unset", "success"):
        assert result.returncode == 0, result.stderr
        assert ("not set" if mode == "unset" else "succeeded") in status
        assert "FAILED" not in status
    else:
        assert result.returncode != 0
        assert "FAILED" in status and "off-server copy:" in status
        assert {
            "unknown": "unknown remote",
            "missing": "rclone missing",
            "copy-fails": "rclone copy failed",
        }[mode] in status


def test_watchdog_remote_failure(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("watchdog_test", SCRIPT.with_name("watchdog.py"))
    watchdog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(watchdog)
    last = tmp_path / "last_backup.txt"
    last.write_text("FAILED: off-server copy: rclone copy failed; local archive retained")
    assert "off-server copy" in watchdog.backup_status(tmp_path)["backup"]
    last.write_text("archive.tar.gz; off-server copy: succeeded")
    assert watchdog.backup_status(tmp_path) == {}
