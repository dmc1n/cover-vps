"""`cover-site`: change the shop's website from the command line, with the AI (ADR-062).

    cover-site "make the homepage title shorter and mention the summer offer"
    cover-site --show          the draft against the live site
    cover-site --publish       the draft goes live (the old live site is kept)
    cover-site --discard       the draft back to the live site
    cover-site --history       the published versions; --restore 20261005-073000
    cover-site --translate     every language of the shop filled in by the AI (the draft)

Every instruction changes the draft only; see it at the preview address (admin page, Website)
before publishing. Uses COVER_DATA_DIR (default ./data).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    from coverapi.auth import Auth
    from coverapi.shop import Site, cms_apply, shop_params, site_languages, translate

    ap = argparse.ArgumentParser(prog="cover-site", description=__doc__.split("\n")[0])
    ap.add_argument("instruction", nargs="?", help="what to change, in plain words")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--discard", action="store_true")
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--restore")
    ap.add_argument("--translate", action="store_true")
    args = ap.parse_args(argv)
    data = Path(os.environ.get("COVER_DATA_DIR", "data"))
    site = Site(data / "site")
    auth = Auth(data / "app.db")
    if args.instruction:
        out = cms_apply(site, shop_params(auth), args.instruction, site_languages(auth))
        print(out["summary"])
        for c in out["changes"]:
            print(f"  {c['path']}: {json.dumps(c.get('value'), ensure_ascii=False)[:120]}")
        print("This is the draft; check the preview, then: cover-site --publish")
    if args.translate:
        t = translate(site, shop_params(auth), site_languages(auth))
        print(f"{t['translated']} texts translated into {', '.join(t['languages'])}; "
              "check the preview, then: cover-site --publish")  # fmt: skip
    if args.show:
        draft, live = site.read("draft"), site.read("live")
        print("draft differs from live" if draft != live else "draft = live")
    if args.publish:
        print(
            "published; the previous live site is kept as",
            site.publish(os.environ.get("USER", "cli")),
        )
    if args.discard:
        site.discard()
        print("the draft is the live site again")
    if args.history:
        print("\n".join(site.history()) or "no versions yet")
    if args.restore:
        site.restore(args.restore)
        print("the draft is now version", args.restore, "- publish to make it live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
