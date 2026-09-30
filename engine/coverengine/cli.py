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
MM_PER_CM = 10  # param-ok: unit conversion


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
    runs_off = r["drainage"]["drains"]
    stays = "would stay on the top: red in preview.glb (see warning)"
    print(f"water    {'runs off' if runs_off else stays}")
    if r["support"]:
        s = r["support"]
        how = "automatic" if s["automatic"] else "as set"
        x, y = s["centre_mm"]
        print(
            f"support  {s['kind']} {s['height_mm']:.0f} mm high ({how}), "
            f"radius {s['radius_mm']:g} mm, centred at x {x:.0f}, y {y:.0f}"
        )
    for w in hull.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def _cmd_cut(args: argparse.Namespace) -> int:
    from coverengine.seams.build import cut_cover, write_cut

    cover_json = args.model / "cover.json"
    params = resolve_params(args, cover_json if cover_json.is_file() else None)
    result = cut_cover(args.model, params, args.seams)
    out = write_cut(args.model, result, args.out)
    r = result.report
    print(f"panels -> {out / 'panels.glb'} (each panel in its own colour)")
    for p in r["panels"]:
        fits = "fits the roll" if p["fits_roll"] else "TOO WIDE for the roll"
        print(
            f"  {p['name']:<16} {p['area_m2']:6.3f} m2   flat {p['flat_width_mm']:6.0f} x "
            f"{p['flat_length_mm']:6.0f} mm   {fits}"
        )
    print(f"seams  {len(r['seams'])}, hem {r['hem_length_mm'] / 1000:.2f} m")
    for s in r["seams"]:
        print(f"  {s['id']:<34} {s['length_mm'] / MM_PER_CM:7.1f} cm   {s['lap_side']} laps over")
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    import json as _json

    from coverengine.export.cut import write_export
    from coverengine.finish.finish import FINISHED_JSON, finish, finished_set
    from coverengine.flatten.pattern import PATTERN_JSON

    pattern = args.model / PATTERN_JSON
    if not pattern.is_file():
        raise CoverError(f"no {PATTERN_JSON} in {args.model} (run cover flatten first)")
    cover_json = args.model / "cover.json"
    params = resolve_params(args, cover_json if cover_json.is_file() else None)
    doc = _json.loads(pattern.read_text(encoding="utf-8"))
    pieces, warnings = finish(doc, params)
    finished = finished_set(doc, pieces, warnings, params)
    out = args.out or args.model
    out.mkdir(parents=True, exist_ok=True)
    finished["sheet"] = write_export(out, pieces, finished, params)
    (out / FINISHED_JSON).write_text(
        _json.dumps(finished, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"export -> {out / 'cut.dxf'}, cut.svg, cutting-list.pdf, {FINISHED_JSON}")
    for pc in finished["pieces"]:
        w, h = pc["size_mm"]
        print(f"  {pc['id']:<4} {pc['name']:<16} x{pc['quantity']}  {w:6.0f} x {h:6.0f} mm")
    length = finished["sheet"]["roll_length_mm"]
    print(f"fabric about {length / 1000:.2f} m of roll")
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def _cmd_drawing(args: argparse.Namespace) -> int:
    import json as _json

    from coverengine.export.drawing import SIZES_PDF, write_drawing
    from coverengine.flatten.pattern import PATTERN_JSON

    pattern = args.model / PATTERN_JSON
    if not pattern.is_file():
        raise CoverError(f"no {PATTERN_JSON} in {args.model} (run cover flatten first)")
    cover_json = args.model / "cover.json"
    params = resolve_params(args, cover_json if cover_json.is_file() else None)
    doc = _json.loads(pattern.read_text(encoding="utf-8"))
    out = write_drawing(args.model, doc, params, args.out or args.model / SIZES_PDF)
    print(f"size drawing -> {out}")
    return 0


def _cmd_flatten(args: argparse.Namespace) -> int:
    import json as _json

    from coverengine.export.pattern import write_all
    from coverengine.flatten.pattern import PATTERN_JSON, build_patterns, pattern_set

    cover_json = args.model / "cover.json"
    params = resolve_params(args, cover_json if cover_json.is_file() else None)
    patterns, cut_report = build_patterns(args.model, params)
    doc, warnings = pattern_set(args.model, params, patterns, cut_report)
    out = args.out or args.model
    out.mkdir(parents=True, exist_ok=True)
    doc["sheet"] = write_all(out, patterns, params)
    (out / PATTERN_JSON).write_text(
        _json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    from coverengine.export.drawing import SIZES_PDF, write_drawing

    write_drawing(args.model, doc, params, out / SIZES_PDF)
    print(
        f"patterns -> {out / 'pattern.dxf'}, pattern.svg, pattern-stretch.svg, pattern.json, "
        f"{SIZES_PDF}"
    )
    for p in doc["panels"]:
        fits = "fits the roll" if p["fits_roll"] else "TOO WIDE for the roll"
        print(
            f"  {p['name']:<16} {p['flat_width_mm']:6.0f} x {p['flat_length_mm']:6.0f} mm   "
            f"stretch {p['stretch']['quantile_pct']:4.2f} % (max {p['stretch']['max_pct']:.1f} % "
            f"in a small spot)   {fits}"
        )
    sheet_w, sheet_h = doc["sheet"]["sheet_mm"]
    worst = max(
        (e["ease_mm"] for p in doc["panels"] for e in p["edges"] if "ease_mm" in e), default=0.0
    )
    print(f"seams  largest difference between the two sides of a seam: {worst:.1f} mm")
    print(
        f"fabric {doc['summary']['fabric_area_m2']:.2f} m2 without allowances, "
        f"sheet {sheet_w:.0f} x {sheet_h:.0f} mm"
    )
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """import -> hull -> cut -> flatten in one go."""
    out = args.out or Path("models") / args.file.stem.lower().replace(" ", "-")
    steps = [
        ["import", str(args.file), "--out", str(out)]
        + (["--units", args.units] if args.units else [])
        + (["--up", args.up] if args.up else []),
        ["hull", str(out)],
        ["cut", str(out)],
        ["flatten", str(out)],
        ["export", str(out)],
    ]
    extra = [x for s in args.overrides for x in ("--set", s)]
    for step in steps:
        print(f"== cover {step[0]}")
        code = main([*step, *extra] if step[0] != "import" else step)
        if code:
            return code
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    import json as _json

    a = _json.loads(args.a.read_text(encoding="utf-8"))
    b = _json.loads(args.b.read_text(encoding="utf-8"))
    pa = {p["name"]: p for p in a["panels"]}
    pb = {p["name"]: p for p in b["panels"]}
    changed = 0
    for name in sorted(set(pa) | set(pb)):
        if name not in pa or name not in pb:
            print(f"  {name:<16} {'new' if name in pb else 'gone'}")
            changed += 1
            continue
        da = (pa[name]["flat_width_mm"], pa[name]["flat_length_mm"])
        db = (pb[name]["flat_width_mm"], pb[name]["flat_length_mm"])
        move = max(abs(x - y) for x, y in zip(da, db, strict=True))
        if move > args.threshold:
            print(f"  {name:<16} {da[0]:.0f} x {da[1]:.0f} -> {db[0]:.0f} x {db[1]:.0f} mm")
            changed += 1
    flat_a = _flatten_tree(a.get("parameters", {}))
    flat_b = _flatten_tree(b.get("parameters", {}))
    for key in sorted(set(flat_a) | set(flat_b)):
        if flat_a.get(key) != flat_b.get(key):
            print(f"  setting {key}: {flat_a.get(key)} -> {flat_b.get(key)}")
    print(f"{changed} panel(s) changed by more than {args.threshold:g} mm")
    return 0


def _flatten_tree(tree: dict[str, object], prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in tree.items():
        if isinstance(v, dict):
            out.update(_flatten_tree(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


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

    p = sub.add_parser("cut", help="divide the cover surface into panels with seams")
    p.add_argument("model", type=Path, help="model directory with hull.glb (cover hull)")
    p.add_argument("--seams", type=Path, help="seam file (default: seams.json in the model dir)")
    p.add_argument("--out", type=Path, help="output directory (default: the model directory)")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_cut)

    p = sub.add_parser("flatten", help="flat patterns of every panel (DXF, SVG, pattern.json)")
    p.add_argument("model", type=Path, help="model directory with panels (cover cut)")
    p.add_argument("--out", type=Path, help="output directory (default: the model directory)")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_flatten)

    p = sub.add_parser("export", help="finished pieces for the cutting table (cut.dxf, list)")
    p.add_argument("model", type=Path, help="model directory with patterns (cover flatten)")
    p.add_argument("--out", type=Path, help="output directory (default: the model directory)")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_export)

    p = sub.add_parser("drawing", help="size drawing of the cover and its panels (sizes.pdf)")
    p.add_argument("model", type=Path, help="model directory with patterns (cover flatten)")
    p.add_argument("--out", type=Path, help="PDF file (default: sizes.pdf in the model dir)")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_drawing)

    p = sub.add_parser("run", help="import, cover, seams and patterns in one go")
    p.add_argument("file", type=Path, help="3D file (STEP, IGES, STL, ...)")
    p.add_argument("--out", type=Path, help="model directory (default: models/<file name>)")
    p.add_argument("--units", choices=SUGGESTED_UNITS)
    p.add_argument("--up")
    p.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE")
    p.set_defaults(handler=_cmd_run)

    p = sub.add_parser("diff", help="panels whose size changed between two pattern.json files")
    p.add_argument("a", type=Path)
    p.add_argument("b", type=Path)
    p.add_argument("--threshold", type=float, default=1.0, help="mm (default 1)")
    p.set_defaults(handler=_cmd_diff)

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
