"""`cover` command line interface."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from coverengine import __version__

Handler = Callable[[argparse.Namespace], int]


def _cmd_version(args: argparse.Namespace) -> int:
    print(f"coverengine {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cover", description="Cover pattern engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("version", help="print the engine version")
    p.set_defaults(handler=_cmd_version)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler = args.handler
    try:
        return handler(args)
    except CoverError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


class CoverError(Exception):
    """An error with a message meant for the operator; printed without a traceback."""


if __name__ == "__main__":
    sys.exit(main())
