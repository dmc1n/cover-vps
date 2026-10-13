"""Workshop logins from the user CLI never approve at the Desk."""

import sys
from pathlib import Path

import pytest
from coverapi import users_cli


def test_workshop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        sys,
        "argv",
        ["cover-users", "add", "werkplaats", "--name", "Werkplaats", "--role", "workshop"],
    )
    assert users_cli.main() == 0
    monkeypatch.setattr(
        sys, "argv", ["cover-users", "add", "bad", "--role", "workshop", "--approve"]
    )
    assert users_cli.main() == 1
    assert "the workshop role never approves" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["cover-users", "add", "viewer"])
    assert users_cli.main() == 0
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", ["cover-users", "list"])
    assert users_cli.main() == 0
    lines = capsys.readouterr().out.splitlines()
    assert all(line.index("no password yet") == 39 for line in lines)
    assert any("workshop" in line for line in lines)
