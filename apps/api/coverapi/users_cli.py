"""`cover-users`: users from the command line, for the first admin and for emergencies.

    COVER_DATA_DIR=~/cover-data uv run cover-users list
    COVER_DATA_DIR=~/cover-data uv run cover-users add rick --name Rick --email rick@... \\
        --role admin --approve
    COVER_DATA_DIR=~/cover-data uv run cover-users invite rick     # a new password link

The links are printed here; they are as good as a password until used (7 days), so pass them
on privately.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from coverapi.auth import ROLES, Auth, AuthError
from coverapi.security import DEFAULT_PUBLIC_URL, PUBLIC_URL_KEY


def main() -> int:
    ap = argparse.ArgumentParser(prog="cover-users")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = sub.add_parser("add")
    a.add_argument("username")
    a.add_argument("--name", default="")
    a.add_argument("--email")
    a.add_argument("--role", choices=ROLES, default="viewer")
    a.add_argument("--approve", action="store_true", help="may approve the definitive drawing")
    i = sub.add_parser("invite")
    i.add_argument("username")
    args = ap.parse_args()
    data = Path(os.environ.get("COVER_DATA_DIR", "data"))
    data.mkdir(parents=True, exist_ok=True)
    auth = Auth(data / "app.db")
    base = str(auth.setting(PUBLIC_URL_KEY, DEFAULT_PUBLIC_URL)).rstrip("/")
    try:
        if args.cmd == "list":
            for u in auth.users():
                flags = ("may approve " if u.can_approve else "") + ("" if u.active else "inactive")
                pw = "password set" if u.has_password else "no password yet"
                print(f"{u.username:<12} {u.name:<16} {u.role:<7} {pw:<16} {u.email or ''} {flags}")
            return 0
        if args.cmd == "add":
            u = auth.add_user(args.username, args.name, args.role, args.email, args.approve)
            auth.log("cover-users", "user added", u.public())
        else:
            found = next((x for x in auth.users() if x.username == args.username.lower()), None)
            if found is None:
                raise AuthError(f"no user {args.username!r}")
            u = found
        token = auth.invite(u.id)
        auth.log("cover-users", "invite", {"user": u.username})
        print(f"{u.username}: {base}/#/welcome/{token}")
        return 0
    except AuthError as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
