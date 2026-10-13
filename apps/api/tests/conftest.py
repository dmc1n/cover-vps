"""The API tests: no drape after a calculation (it would take minutes per test).

The login code by mail is on by default and, without a mail server, refuses every login (fail
closed, ADR-123). The tests have no mail server, so a test's fresh data starts with the code off,
as a scratch copy does (`cover-users two-factor off`); the tests of the code switch it on.
"""

import os
from typing import Any

import pytest

os.environ.setdefault("COVER_AUTO_DRAPE", "off")
os.environ.setdefault("COVER_MAIL_WORKER", "off")  # the tests deliver the outbox themselves


@pytest.fixture(autouse=True)
def _login_code_off_unless_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from coverapi import auth as auth_module
    from coverapi.security import TWO_FACTOR_KEY

    original = auth_module.Auth.__init__

    def init(self: Any, db_path: Any) -> None:
        original(self, db_path)
        if self.setting(TWO_FACTOR_KEY) is None:
            self.set_setting(TWO_FACTOR_KEY, False)

    monkeypatch.setattr(auth_module.Auth, "__init__", init)
