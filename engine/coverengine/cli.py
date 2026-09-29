"""`cover` command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from coverengine import __version__
from coverengine.errors import CoverError
from coverengine.params import (
    EffectiveParams,
    Registry,
    load_cover_definition_layer,
    load_yaml_layer,
    parse_set,
)

Handler = Callable[[argparse.Namespace], int]


def _add_param_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--defaults", type=Path, help="parameter file (default config/defaults.yaml)")
    p.add_argument("--preset", type=Path, help="family preset YAML (layer 2)")
    p.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="one-off trial override, e.g. --set hull.clearance_mm=15 (repeatable)",
    )


def resolve_params(args: argparse.Namespace, cover_definition: Path | None) -> EffectiveParams:
    registry = Registry.load(args.defaults)
    preset = load_yaml_layer(args.preset) if args.preset else None
    model = load_cover_definition_layer(cover_definition) if cover_definition else None
    return registry.resolve(preset=preset, model=model, trial=parse_set(args.overrides))


def _fmt(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _cmd_version(args: argparse.Namespace) -> int:
    print(f"coverengine {__version__}")
    return 0


def _cmd_params(args: argparse.Namespace) -> int:
    params = resolve_params(args, args.model)
    if args.json:
        doc = {
            "parameters": params.tree(),
            "parameter_sources": params.sources(),
            "parameter_hash": params.hash(),
        }
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0
    specs = params.registry.specs
    rows = [(k, _fmt(params[k]), params.source(k), specs[k]) for k in params.keys()]
    wk = max(len(r[0]) for r in rows)
    wv = max(len(r[1]) for r in rows)
    print(f"{'parameter':<{wk}}  {'value':<{wv}}  {'source':<7}  note")
    for key, value, source, spec in rows:
        note = "* to confirm" if spec.to_confirm else ""
        if spec.choices:
            note = (note + "  " if note else "") + "choices: " + " | ".join(spec.choices)
        print(f"{key:<{wk}}  {value:<{wv}}  {source:<7}  {note}".rstrip())
    print(f"\nparameter hash {params.hash()[:16]}   (* = assumption still to confirm)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cover", description="Cover pattern engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("version", help="print the engine version")
    p.set_defaults(handler=_cmd_version)

    p = sub.add_parser("params", help="effective parameters and where each value comes from")
    p.add_argument(
        "model", nargs="?", type=Path, help="CoverDefinition JSON, or a model dir with cover.json"
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_params)

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


if __name__ == "__main__":
    sys.exit(main())
