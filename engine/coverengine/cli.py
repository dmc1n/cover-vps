"""`cover` command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from coverengine import __version__
from coverengine.errors import CoverError
from coverengine.io.placement import SUGGESTED_UNITS
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


def _cmd_info(args: argparse.Namespace) -> int:
    from coverengine.io.info import format_info, format_model_info, is_model, mesh_info

    if is_model(args.mesh):
        print(format_model_info(args.mesh))
    else:
        print(format_info(mesh_info(args.mesh)))
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    from coverengine.io.model_io import import_model

    shortcuts = {
        "import.min_part_mm": args.min_part_mm,
        "import.up_axis": args.up,
        "import.front": args.front,
    }
    args.overrides = [f"{k}={v}" for k, v in shortcuts.items() if v is not None] + args.overrides
    params = resolve_params(args, None)
    result = import_model(
        args.file,
        args.out,
        params,
        exclude=args.exclude,
        units=args.units,
        forget_exclusions=args.forget_exclusions,
    )
    m = result.model
    parts = m["parts"]
    size = " x ".join(f"{v:.1f}" for v in m["size_mm"])
    src = m["source"]
    print(f"imported {src['file']} -> {result.out_dir}")
    print(f"units    {src['units_used']} (file declares {src['units_detected'] or 'no unit'})")
    print(f"size     {size} mm, {m['mesh']['triangles']} triangles")
    print(
        f"parts    {parts['kept']} kept, {parts['dropped_small']} dropped as smaller than "
        f"{parts['min_part_mm']:g} mm, {parts['excluded']} excluded by name"
    )
    if parts["exclude"]:
        print(f"exclude  {', '.join(parts['exclude'])}")
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def _cmd_hull(args: argparse.Namespace) -> int:
    from coverengine.hull.build import build_hull, write_hull

    shortcuts = {
        "hull.clearance_mm": args.clearance,
        "hull.bridge_gap_mm": args.bridge_gap,
        "hull.hem_height_mm": args.hem_height,
        "hull.resolution_mm": args.resolution,
    }
    args.overrides = [f"{k}={v}" for k, v in shortcuts.items() if v is not None] + args.overrides
    cover_json = args.model / "cover.json"
    params = resolve_params(args, cover_json if cover_json.is_file() else None)
    hull = build_hull(args.model, params)
    out = write_hull(args.model, hull, args.out)
    r = hull.report
    lo, hi = r["bbox_mm"]
    size = " x ".join(f"{b - a:.0f}" for a, b in zip(lo, hi, strict=True))
    dist = r["distance_to_model_mm"]
    p = r["parameters"]
    print(f"cover surface -> {out / 'hull.glb'} (view it with {out / 'preview.glb'})")
    settings = (
        f"clearance {p['hull.clearance_mm']:g} mm, bridge gap {p['hull.bridge_gap_mm']:g} mm, "
        f"hem {p['hull.hem_height_mm']:g} mm above the floor"
    )
    hem_m = r["hem"]["length_mm"] / 1000
    print(f"settings {settings}")
    print(f"size     {size} mm, fabric area {r['area_m2']:.2f} m2, hem length {hem_m:.2f} m")
    closest = f"{dist['min']:.1f} mm from the furniture (clearance {dist['clearance']:g} mm)"
    print(f"distance closest {closest}")
    print(f"ridges   {r['ridges']['chains']} sharp ridges (seam candidates for the next step)")
    for w in hull.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def _cmd_testsheet(args: argparse.Namespace) -> int:
    from coverengine.export.testsheet import write_all

    for path in write_all(args.out):
        print(path)
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

    p = sub.add_parser("import", help="turn a STEP, IGES, STL, OBJ, PLY or GLB file into a model")
    p.add_argument("file", type=Path)
    p.add_argument("--out", type=Path, required=True, help="model directory, e.g. models/chair-a12")
    p.add_argument(
        "--units",
        choices=SUGGESTED_UNITS,
        help="the unit the file is really in (STL, OBJ and PLY store none)",
    )
    p.add_argument("--min-part-mm", type=float, help="drop parts smaller than this (screws)")
    p.add_argument("--up", help="the file's up axis: z | y | x | -z | -y | -x (default auto)")
    p.add_argument("--front", help="side that is the front once upright: -y | y | -x | x")
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help='drop parts by name, e.g. --exclude "cushion*" (repeatable; remembered per model)',
    )
    p.add_argument(
        "--forget-exclusions",
        action="store_true",
        help="do not reuse the exclusions of the previous import into --out",
    )
    _add_param_args(p)
    p.set_defaults(handler=_cmd_import)

    p = sub.add_parser("hull", help="the cover surface (drape hull) of an imported model")
    p.add_argument("model", type=Path, help="model directory written by cover import")
    p.add_argument("--clearance", type=float, help="mm between furniture and fabric")
    p.add_argument("--bridge-gap", type=float, help="gaps narrower than this (mm) are spanned")
    p.add_argument("--hem-height", type=float, help="hem edge above the floor (mm)")
    p.add_argument("--resolution", type=float, help="grid size (mm); smaller is slower, finer")
    p.add_argument("--out", type=Path, help="output directory (default: the model directory)")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_hull)

    p = sub.add_parser("info", help="size, triangle count and area of a mesh file or model")
    p.add_argument("mesh", type=Path)
    p.set_defaults(handler=_cmd_info)

    p = sub.add_parser("testsheet", help="write the M0 machine test sheet DXF files")
    p.add_argument("--out", type=Path, default=Path("testdata/machine"))
    p.set_defaults(handler=_cmd_testsheet)

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
