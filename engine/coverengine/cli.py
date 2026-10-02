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
    load_yaml_layer,
    parse_set,
    resolve_model,
)

Handler = Callable[[argparse.Namespace], int]
MM_PER_CM = 10  # param-ok: unit conversion
SHOW_REVISIONS = 5  # param-ok: CLI display
IMPROVE_ROUNDS = 4  # param-ok: CLI default, rounds of seam proposals
IMPROVE_GAIN = 0.1  # param-ok: CLI default, a round must lower the worst stretch by 10 %


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
    """Defaults, the family preset (`--preset`, or the family named in the model's cover.json),
    the model's cover.json, then `--set`."""
    registry = Registry.load(args.defaults)
    preset = load_yaml_layer(args.preset) if args.preset else None
    trial = parse_set(args.overrides)
    if cover_definition is not None:
        model_dir = cover_definition if cover_definition.is_dir() else cover_definition.parent
        return resolve_model(model_dir, trial, registry, preset)
    return registry.resolve(preset=preset, trial=trial)


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
    from coverengine.io.kind import write_guess
    from coverengine.io.model_io import load_model

    kind = write_guess(result.out_dir, load_model(result.out_dir), args.file.name)
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
    what = "the cover surface itself" if kind["guess"] == "cover" else "the furniture"
    sure = "" if kind["sure"] else " (not sure)"
    print(f"kind     looks like {what}{sure}: {'; '.join(kind['reasons'])}")
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
    from coverengine.export.preview import PREVIEW_PNG, write_preview

    write_preview(args.model, doc, params, out / PREVIEW_PNG)
    (out / FINISHED_JSON).write_text(
        _json.dumps(finished, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"export -> {out / 'cut.dxf'}, cut.svg, cutting-list.pdf, cover.png, {FINISHED_JSON}")
    for pc in finished["pieces"]:
        w, h = pc["size_mm"]
        print(f"  {pc['id']:<4} {pc['name']:<16} x{pc['quantity']}  {w:6.0f} x {h:6.0f} mm")
    length = finished["sheet"]["roll_length_mm"]
    print(f"fabric about {length / 1000:.2f} m of roll")
    if out.resolve() == args.model.resolve():
        from coverengine.catalogue import save_revision

        rev = save_revision(args.model, parse_set(args.overrides))
        print(f"revision {rev['number']}" + (" (trial settings)" if rev["trial"] else ""))
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def _cmd_model(args: argparse.Namespace) -> int:
    from coverengine.catalogue import info, revisions, set_info

    changes: dict[str, object] = {}
    if args.family is not None:
        changes["family"] = args.family
    if args.status is not None:
        changes["status"] = args.status
    if args.tags is not None:
        changes["tags"] = [t for t in args.tags.split(",")]
    if args.notes is not None:
        changes["notes"] = args.notes
    doc = set_info(args.model, changes) if changes else info(args.model)
    tags = ", ".join(doc["tags"]) or "-"
    print(f"{args.model.name}: family {doc['family'] or '-'}, status {doc['status']}, tags {tags}")
    if doc["notes"]:
        print(f"  notes: {doc['notes']}")
    for r in revisions(args.model)[-args.revisions :] if args.revisions else []:
        trial = " trial " + ",".join(r["trial"]) if r["trial"] else ""
        print(
            f"  revision {r['number']:>3}  {r['panels']} panels, stretch "
            f"{r['max_stretch_pct']:.1f} %, {r['warnings']} warnings{trial}"
        )
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    """Run steps on many models (one family, a list, or all) and report what changed."""
    from coverengine.catalogue import compare_files, info, revisions

    root: Path = args.models
    dirs = sorted(d for d in root.iterdir() if (d / "model.json").is_file())
    if args.ids:
        wanted = set(args.ids.split(","))
        dirs = [d for d in dirs if d.name in wanted]
    if args.family:
        dirs = [d for d in dirs if info(d)["family"] == args.family]
    if not dirs:
        raise CoverError("no models match")
    steps = args.steps.split(",")
    extra = [x for s in args.overrides for x in ("--set", s)]
    failed = 0
    for d in dirs:
        before = revisions(d)
        code = 0
        for step in steps:
            code = main([step, str(d), *extra])
            if code:
                break
        after = revisions(d)
        if code:
            failed += 1
            print(f"== {d.name}: FAILED at {step}")
            continue
        if before and after and after[-1]["number"] != before[-1]["number"]:
            prev = d / "revisions" / f"{before[-1]['number']:03d}" / "pattern.json"
            diff = compare_files(prev, d / "pattern.json", args.threshold)
            n = len(diff["panels"]) if diff else 0
            print(f"== {d.name}: {n} panel(s) changed by more than {args.threshold:g} mm")
            if diff:
                _print_diff(diff, args.threshold)
        else:
            print(f"== {d.name}: done")
    print(f"{len(dirs) - failed} of {len(dirs)} model(s) done")
    return 1 if failed else 0


def _cmd_improve(args: argparse.Namespace) -> int:
    """Take the program's seam proposals round by round while they lower the worst stretch."""
    import json as _json

    from coverengine.seams.build import PROPOSALS_JSON

    d: Path = args.model
    store = d / PROPOSALS_JSON
    extra = [x for s in args.overrides for x in ("--set", s)]

    def worst() -> float:
        doc = _json.loads((d / "pattern.json").read_text(encoding="utf-8"))
        return float(max(p["stretch"]["quantile_pct"] for p in doc["panels"]))

    def run(*steps: str) -> int:
        for st in steps:
            code = main([st, str(d), *extra])
            if code:
                return code
        return 0

    if not (d / "pattern.json").is_file() and run("cut", "flatten"):
        return 1
    best = worst()
    print(f"improve {d.name}: worst stretch {best:.1f} %")
    for round_ in range(1, args.rounds + 1):
        doc = _json.loads((d / "pattern.json").read_text(encoding="utf-8"))
        props = [p["points"] for p in doc.get("proposals", [])]
        if not props:
            print("  no more proposals")
            break
        before = store.read_text(encoding="utf-8") if store.is_file() else None
        taken = _json.loads(before)["top_seams"] if before else []
        store.write_text(_json.dumps({"top_seams": taken + props}, indent=1) + "\n")
        code = run("cut", "flatten")
        now = worst() if code == 0 else float("inf")
        if now > best * (1 - args.gain):
            print(f"  round {round_}: {now:.1f} % - not better, left out")
            if before is None:
                store.unlink()
            else:
                store.write_text(before)
            run("cut", "flatten")
            break
        print(
            f"  round {round_}: {len(props)} seam(s) taken, worst stretch {best:.1f} -> {now:.1f} %"
        )
        best = now
    return run("export") if args.export else 0


def _cmd_ai(args: argparse.Namespace) -> int:
    """AI advice on a cover's layout; with --apply, carry out one suggested action."""
    from coverengine.ai import ACTIONS, apply_action, review

    cover_json = args.model / "cover.json"
    params = resolve_params(args, cover_json if cover_json.is_file() else None)
    if args.learn:
        from coverengine.ai import LESSONS_JSON, learn

        lesson = learn(args.model, params, args.learn)
        print(f"cause  {lesson['cause']}")
        print(f"rule   {lesson['rule']}")
        print(f"check  {lesson['check']}")
        print(f"kept in {LESSONS_JSON} (given to the AI from now on, for {lesson['applies_to']})")
        return 0
    if args.apply:
        steps = apply_action(args.model, args.apply, args.value)
        print(f"applied {args.apply}; run again: {', '.join(steps)}")
        if args.run:
            for st in steps:
                code = main([st, str(args.model)])
                if code:
                    return code
        return 0
    doc = review(args.model, params)
    print(f"AI ({doc['model']}): {doc['summary']}")
    print(f"pieces now {doc['pieces_now']}, the AI's target {doc['target_pieces']}")
    for p in doc["problems"]:
        print(f"  problem: {p}")
    for i, sug in enumerate(doc["suggestions"], 1):
        val = f" ({sug['value']})" if sug.get("value") is not None else ""
        print(f"  {i}. {sug['action']}{val}: {sug.get('reason', '')}")
        print(f"     = {ACTIONS[sug['action']]}")
    return 0


def _cmd_categorise(args: argparse.Namespace) -> int:
    """Every model's category, with the SUNS names (ADR-050); tables join the table family."""
    from collections import Counter

    from coverengine.catalogue import info, set_info
    from coverengine.category import TABLES, categorise

    dirs = (
        [d for d in args.model]
        if args.model
        else sorted(d for d in args.models.iterdir() if (d / "model.json").is_file())
    )
    counts: Counter[str] = Counter()
    for d in dirs:
        current = info(d)
        if current["category"] and not args.force:
            counts[current["category"]] += 1
            continue
        params = resolve_params(args, d / "cover.json")
        got = categorise(d, params, use_ai=args.ai)
        if not got["category"]:
            print(f"{d.name}: no category ({got['why']})")
            counts["(none)"] += 1
            continue
        changes: dict[str, object] = {"category": got["category"]}
        if got["category"].split(" › ")[1] in TABLES and not current["family"]:
            changes["family"] = "table"
        set_info(d, changes)
        counts[got["category"]] += 1
        if got["by"] == "ai":
            print(f"{d.name}: {got['category']} (AI: {got['why']})")
    for cat, n in counts.most_common():
        print(f"{n:5d}  {cat}")
    return 0


def _cmd_rain(args: argparse.Namespace) -> int:
    """Where rain goes on the cover: ponds, flat parts, streams, drops, the AI's verdict."""
    from coverengine.rain import simulate

    cover_json = args.model / "cover.json"
    params = resolve_params(args, cover_json if cover_json.is_file() else None)
    r = simulate(args.model, params, use_ai=not args.no_ai)
    print(f"ponds   {len(r['ponds'])} ({r['pond_area_m2']:g} m2, {r['pond_volume_l']:g} l), "
          f"{r['growing_ponds']} keep growing under their weight")  # fmt: skip
    print(f"flat    {r['flat_area_m2']:g} m2 flatter than {params['hull.min_slope_deg']} degrees")
    print(f"off at  {', '.join(f'{k} {v}' for k, v in r['exits'].items() if v)} (drops)")
    for s in r["seams_along"]:
        print(f"seam    water runs along {s['seam']} for {s['run_mm'] / MM_PER_CM:.0f} cm")
    ai = r.get("ai") or {}
    if ai.get("verdict"):
        print(f"AI      {ai['verdict']}: {ai.get('summary', '')}")
    print("dry" if r["dry"] else "water stays on the cover")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    """Check calculated covers (and ask the AI for a second opinion): audit.json per model."""
    import csv

    from coverengine.audit import audit
    from coverengine.catalogue import info

    dirs = (
        [d for d in args.model]
        if args.model
        else sorted(d for d in args.models.iterdir() if (d / "model.json").is_file())
    )
    if args.tag:
        dirs = [d for d in dirs if args.tag in info(d)["tags"]]
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in dirs:
        params = resolve_params(args, d / "cover.json")
        try:
            doc = audit(d, params, args.ai)
        except Exception as exc:  # noqa: BLE001 - one broken model must not stop the audit
            print(f"{d.name}: audit failed: {exc}")
            rows.append({"model": d.name, "ok": False, "failed": "; ".join(["audit", str(exc)])})
            continue
        failed = [c["check"] for c in doc["checks"] if not c["ok"]]
        ai = doc.get("ai", {})
        rows.append(
            {
                "model": d.name,
                "ok": doc["ok"],
                "failed": "; ".join(failed),
                "details": " | ".join(c["detail"] for c in doc["checks"] if not c["ok"]),
                "ai_verdict": ai.get("verdict", ai.get("error", "")),
                "ai_problems": " | ".join(ai.get("problems", [])),
                "ai_disagrees": " | ".join(ai.get("disagree", [])),
            }
        )
        verdict = f"  AI: {rows[-1]['ai_verdict']}" if args.ai else ""
        print(f"{d.name:<50} {'ok' if doc['ok'] else 'NOT OK: ' + ', '.join(failed)}{verdict}")
    keys = ["model", "ok", "failed", "details", "ai_verdict", "ai_problems", "ai_disagrees"]
    with (args.out / "audit.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    good = sum(1 for r in rows if r["ok"])
    print(f"{len(rows)} models: {good} pass every check -> {args.out / 'audit.csv'}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    """A catalogue report: every model graded ready / check / failed (CSV and PDF)."""
    import csv

    from coverengine.catalogue import grade, info

    dirs = sorted(d for d in args.models.iterdir() if d.is_dir())
    if args.tag:
        dirs = [d for d in dirs if args.tag in info(d)["tags"]]
    rows = [grade(d) for d in dirs if (d / "model.json").is_file() or (d / "cover.json").is_file()]
    args.out.mkdir(parents=True, exist_ok=True)
    fields = ["id", "grade", "family", "status", "panels", "max_stretch_pct", "max_ease_mm",
              "max_wiggle_mm", "roll_length_mm", "proposals", "reasons"]  # fmt: skip
    with (args.out / "catalogue.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(fields)
        for r in rows:
            w.writerow([("; ".join(r[f]) if f == "reasons" else r.get(f, "")) for f in fields])
    from coverengine.export.report import write_report

    write_report(args.out / "catalogue.pdf", rows, args.title or args.models.name)
    counts = {g: sum(r["grade"] == g for r in rows) for g in ("ready", "check", "failed")}
    print(
        f"{len(rows)} models: {counts['ready']} ready, {counts['check']} to check, "
        f"{counts['failed']} failed -> {args.out / 'catalogue.pdf'}, catalogue.csv"
    )
    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    import json as _json

    from coverengine.export.preview import PREVIEW_PNG, write_preview
    from coverengine.flatten.pattern import PATTERN_JSON

    pattern = args.model / PATTERN_JSON
    if not pattern.is_file():
        raise CoverError(f"no {PATTERN_JSON} in {args.model} (run cover flatten first)")
    cover_json = args.model / "cover.json"
    params = resolve_params(args, cover_json if cover_json.is_file() else None)
    doc = _json.loads(pattern.read_text(encoding="utf-8"))
    out = write_preview(args.model, doc, params, args.out or args.model / PREVIEW_PNG)
    print(f"preview -> {out}")
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

    from coverengine.catalogue import compare

    a = _json.loads(args.a.read_text(encoding="utf-8"))
    b = _json.loads(args.b.read_text(encoding="utf-8"))
    _print_diff(compare(a, b, args.threshold), args.threshold)
    return 0


def _print_diff(d: dict[str, object], threshold: float) -> None:
    panels = d["panels"]
    settings = d["settings"]
    assert isinstance(panels, list) and isinstance(settings, list)
    for p in panels:
        if p["change"] == "size":
            (w0, l0), (w1, l1) = p["before_mm"], p["after_mm"]
            print(f"  {p['name']:<16} {w0:.0f} x {l0:.0f} -> {w1:.0f} x {l1:.0f} mm")
        else:
            print(f"  {p['name']:<16} {p['change']}")
    for st in settings:
        print(f"  setting {st['key']}: {st['before']} -> {st['after']}")
    print(f"{len(panels)} panel(s) changed by more than {threshold:g} mm")


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

    p = sub.add_parser("model", help="a model's family, status, tags, notes and revisions")
    p.add_argument("model", type=Path, help="model directory")
    p.add_argument("--family", help="family (a preset in config/presets/); '' for none")
    p.add_argument("--status", choices=["draft", "checked", "production"])
    p.add_argument("--tags", help="comma-separated tags ('' for none)")
    p.add_argument("--notes", help="notes for the machine operator")
    p.add_argument("--revisions", type=int, default=SHOW_REVISIONS, help="show the last N")
    p.set_defaults(handler=_cmd_model)

    p = sub.add_parser("batch", help="run steps on many models and report what changed")
    p.add_argument("--models", type=Path, default=Path("models"), help="models folder")
    p.add_argument("--family", help="only models of this family")
    p.add_argument("--ids", help="only these models (comma-separated)")
    p.add_argument("--steps", default="hull,cut,flatten,export", help="steps to run")
    p.add_argument("--threshold", type=float, default=1.0, help="report changes above (mm)")
    p.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE")
    p.set_defaults(handler=_cmd_batch)

    p = sub.add_parser("improve", help="take seam proposals while they lower the stretch")
    p.add_argument("model", type=Path, help="model directory (after cover flatten)")
    p.add_argument("--rounds", type=int, default=IMPROVE_ROUNDS, help="rounds at most")
    p.add_argument("--gain", type=float, default=IMPROVE_GAIN, help="least gain per round")
    p.add_argument("--no-export", dest="export", action="store_false")
    p.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE")
    p.set_defaults(handler=_cmd_improve)

    p = sub.add_parser("ai", help="AI advice on a cover's layout (ai_review.json)")
    p.add_argument("model", type=Path, help="model directory with a calculated cover")
    p.add_argument("--apply", help="carry out one action (see ai_review.json)")
    p.add_argument("--value", type=float, help="value for the action (skirt height in mm)")
    p.add_argument("--run", action="store_true", help="with --apply: calculate again")
    p.add_argument("--learn", metavar="COMPLAINT", help="why was this cover wrong? (a lesson)")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_ai)

    p = sub.add_parser("categorise", help="every model's category, with the SUNS names")
    p.add_argument("model", type=Path, nargs="*", help="model directories (default: all)")
    p.add_argument("--models", type=Path, default=Path("models"), help="models folder")
    p.add_argument("--ai", action="store_true", help="the AI places what the rules cannot")
    p.add_argument("--force", action="store_true", help="also models that have a category")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_categorise)

    p = sub.add_parser("rain", help="where rain goes on the cover (rain.json, rain.glb)")
    p.add_argument("model", type=Path, help="model directory with a cover surface")
    p.add_argument("--no-ai", action="store_true", help="without the AI's verdict")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_rain)

    p = sub.add_parser("audit", help="check calculated covers, optionally with an AI opinion")
    p.add_argument("model", type=Path, nargs="*", help="model directories (default: all)")
    p.add_argument("--models", type=Path, default=Path("models"), help="models folder")
    p.add_argument("--tag", help="only models with this tag")
    p.add_argument("--ai", action="store_true", help="ask the AI for a second opinion")
    p.add_argument("--out", type=Path, default=Path("out/audit"), help="where audit.csv goes")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_audit)

    p = sub.add_parser("report", help="catalogue report: every model ready / check / failed")
    p.add_argument("--models", type=Path, default=Path("models"), help="models folder")
    p.add_argument("--tag", help="only models with this tag")
    p.add_argument("--title", help="title of the report")
    p.add_argument("--out", type=Path, default=Path("out/report"), help="output folder")
    p.set_defaults(handler=_cmd_report)

    p = sub.add_parser("preview", help="3D picture of the cover for the catalogue (cover.png)")
    p.add_argument("model", type=Path, help="model directory with patterns (cover flatten)")
    p.add_argument("--out", type=Path, help="PNG file (default: cover.png in the model dir)")
    _add_param_args(p)
    p.set_defaults(handler=_cmd_preview)

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
