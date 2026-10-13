# ruff: noqa: E501  (the spec table: one barbecue per few lines, URLs whole)
"""Premium barbecues as catalogue models, built and checked in STAGING (ADR-119).

    uv run python scripts/bbq_models.py OUT [--only id,id] [--jobs 2] [--steps build,cover,check]

Per barbecue of the ranked list (docs/plans/bbq-covers.md):

- build: the barbecue from the manufacturer's published sizes (`coverengine.bbq` builders), or
  from a 3D Warehouse model scaled to those sizes where one exists and matches
  (OUT/warehouse/<entity>.glb, fetched with scripts/warehouse.py; public models, General Model
  Licence); written as OUT/src/<id>.stl (mm, Z up, front -y), then `cover import` into
  OUT/models/<id>/ with a cover.json: tags, notes with the sources, `match` (the configurator
  product it answers to and the customer-facing name) and the hull settings (a kamado or a round
  fire table: `hull.plan: round`, ADR-107);
- cover: hull, cut, flatten, export with the normal pipeline;
- check: `cover audit` and scripts/fewer_check.py (checked twice), the cover picture.

Writes OUT/results.json and OUT/results.csv. Never writes to the live models (the staging guard
refuses it); the main session imports approved ones live after review.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from coverengine import bbq
from coverengine.staging import guard_staging_output

ROOT = Path(__file__).resolve().parent.parent

# sources (docs/plans/bbq-covers-research.md): every size in mm, W x D x H lid closed
BGE = "https://www.biggreenegg.eu/en/products/models/large"
BGE_SIZES = "https://biggreenegg.com/pages/what-size-is-my-egg"
GREENEGGTOTAAL = "https://www.greeneggtotaal.nl/big-green-egg-large/"
GSV_XL = (
    "https://www.grillsportverein.de/forum/threads/"
    "big-green-egg-xlarge-zahlen-daten-fakten-gesammelte-infos.327211/"
)
GSV_MX = (
    "https://www.grillsportverein.de/forum/threads/"
    "big-green-egg-minimax-zahlen-daten-fakten-gesammelte-infos.327210/"
)
WH_BGE_L = "97a6af18-9953-4148-b088-93cfd888ad65"  # "Big Green Egg Large", Ryan Marko
WH_GENESIS2 = "48276b7b-2d98-49fd-8558-c78f4ce49d41"  # "Weber Genesis II EP-335 GBS", Fran L.

KAMADO = {"hull": {"top": "box", "plan": "round"}}
BOXY = {"hull": {"top": "box", "plan": "box"}}  # a straight box: BBQ covers are boxes

SPECS: list[dict[str, Any]] = [
    # ---- kamado: Big Green Egg -------------------------------------------------------------
    {
        "id": "bbq-bge-large-nest",
        "name": "Big Green Egg Large in nest",
        "kind": "bbq_kamado",
        "rank": 1,
        "brand": "big green egg",
        "build": ("kamado", {"egg_d": 560, "height": 1140, "egg_h": 840, "depth": 720}),
        "warehouse_egg": WH_BGE_L,
        "params": KAMADO,
        "sources": [BGE, GREENEGGTOTAAL],
        "estimated": ["nest geometry (drawn)"],
    },
    {
        "id": "bbq-bge-large-integgrated-nest",
        "name": "Big Green Egg Large in IntEGGrated Nest + Handler",
        "kind": "bbq_kamado",
        "rank": 1,
        "brand": "big green egg",
        "build": (
            "kamado",
            {"egg_d": 560, "height": 1140, "egg_h": 840, "depth": 720, "handler": 180},
        ),
        "warehouse_egg": WH_BGE_L,
        "params": KAMADO,
        "sources": [BGE, GREENEGGTOTAAL],
        "estimated": ["handler bar 180 mm out"],
    },
    {
        "id": "bbq-bge-large-egg-frame",
        "name": "Big Green Egg Large in Modular Nest (EGG Frame)",
        "kind": "bbq_kamado_table",
        "rank": 2,
        "brand": "big green egg",
        "build": (
            "kamado_table",
            {
                "egg_d": 560,
                "height": 1230,
                "table_l": 760,
                "table_w": 760,
                "table_h": 770,
                "egg_h": 840,
            },
        ),
        "params": BOXY,
        "sources": [
            "https://biggreenegg.com/products/large-egg-frame-with-stainless-grid-insert-for-modular-nest-system"
        ],
        "estimated": ["total height 1230"],
    },
    {
        "id": "bbq-bge-medium-nest",
        "name": "Big Green Egg Medium in nest",
        "kind": "bbq_kamado",
        "rank": 5,
        "brand": "big green egg",
        "build": ("kamado", {"egg_d": 475, "height": 990, "egg_h": 720, "depth": 595}),
        "params": KAMADO,
        "sources": [BGE_SIZES, "https://basbq.nl/shop/big-green-egg-medium-met-onderstel/"],
        "estimated": ["height in nest 990", "outer 475 x 595 (snippet)"],
    },
    {
        "id": "bbq-bge-xlarge-nest",
        "name": "Big Green Egg XLarge in nest",
        "kind": "bbq_kamado",
        "rank": 6,
        "brand": "big green egg",
        "build": ("kamado", {"egg_d": 670, "height": 1100, "egg_h": 780, "depth": 840}),
        "params": KAMADO,
        "sources": [GSV_XL, BGE_SIZES],
        "estimated": ["height in nest 1100"],
    },
    {
        "id": "bbq-bge-large-nest-mates",
        "name": "Big Green Egg Large in nest with two EGG Mates",
        "kind": "bbq_kamado",
        "rank": 7,
        "brand": "big green egg",
        "build": (
            "kamado",
            {
                "egg_d": 560,
                "height": 1140,
                "egg_h": 840,
                "depth": 720,
                "width": 1322,
                "shelf_depth": 533,
            },
        ),
        "warehouse_egg": WH_BGE_L,
        "params": BOXY,
        "sources": [
            GREENEGGTOTAAL,
            "https://biggreenegg.com/products/solid-acacia-egg-mates-21-x-15-for-large/",
        ],
        "estimated": ["width 560 + 2 x 381"],
    },
    {
        "id": "bbq-bge-minimax-carrier",
        "name": "Big Green Egg MiniMax in carrier",
        "kind": "bbq_kamado",
        "rank": 8,
        "brand": "big green egg",
        "build": (
            "kamado",
            {
                "egg_d": 390,
                "height": 530,
                "egg_h": 500,
                "depth": 530,
                "stand": "none",
                "carrier": 540,
            },
        ),
        "params": KAMADO,
        "sources": [GSV_MX, BGE_SIZES],
        "estimated": [],
    },
    {
        "id": "bbq-bge-large-acacia-table",
        "name": "Big Green Egg Large in acacia table",
        "kind": "bbq_kamado_table",
        "rank": 14,
        "brand": "big green egg",
        "build": (
            "kamado_table",
            {
                "egg_d": 560,
                "height": 1250,
                "table_l": 1524,
                "table_w": 635,
                "table_h": 787,
                "egg_h": 840,
            },
        ),
        "params": BOXY,
        "sources": [
            "https://bbq-authority.com/big-green-egg-solid-acacia-hardwood-table-for-large-eggs/"
        ],
        "estimated": ["dome height 1250", "egg in the middle (it sits off-centre in some tables)"],
    },
    {
        "id": "bbq-bge-2xl-nest",
        "name": "Big Green Egg 2XL in nest",
        "kind": "bbq_kamado",
        "rank": 24,
        "brand": "big green egg",
        "build": ("kamado", {"egg_d": 825, "height": 1200, "egg_h": 900, "depth": 1000}),
        "params": KAMADO,
        "sources": [
            "https://www.thestoveyard.com/products/2xl-big-green-egg",
            "https://waves-console-big-green-egg.s3.amazonaws.com/products/41048/2XL-EGG-BUILT-IN-SPECS-011218-1.pdf",
        ],
        "estimated": ["egg 825 (dealer approx)", "depth 1000", "height 1200"],
    },
    # ---- kamado: others ----------------------------------------------------------------------
    {
        "id": "bbq-kamado-joe-classic-iii-cart",
        "name": "Kamado Joe Classic III on cart",
        "kind": "bbq_kamado",
        "rank": 3,
        "brand": "kamado joe",
        "build": (
            "kamado",
            {
                "egg_d": 570,
                "height": 1258,
                "egg_h": 900,
                "depth": 762,
                "width": 1094,
                "shelf_depth": 420,
            },
        ),
        "params": BOXY,
        "sources": ["https://www.kamadojoe.com/products/classic-joe-iii"],
        "estimated": ["width: official 1094, retailers 1180-1194: measure", "shelf depth 420"],
    },
    {
        "id": "bbq-kamado-joe-big-joe-iii-cart",
        "name": "Kamado Joe Big Joe III on cart",
        "kind": "bbq_kamado",
        "rank": 13,
        "brand": "kamado joe",
        "build": (
            "kamado",
            {
                "egg_d": 720,
                "height": 1400,
                "egg_h": 960,
                "depth": 909,
                "width": 1310,
                "shelf_depth": 480,
            },
        ),
        "params": BOXY,
        "sources": ["https://www.kamadojoe.com/products/big-joe-iii"],
        "estimated": ["width: official 1310, retailers 1481-1483: measure", "egg height 960"],
    },
    {
        "id": "bbq-the-bastard-large-complete",
        "name": "The Bastard Large Complete",
        "kind": "bbq_kamado",
        "rank": 10,
        "brand": "the bastard",
        "build": (
            "kamado",
            {
                "egg_d": 575,
                "height": 1270,
                "egg_h": 870,
                "depth": 800,
                "width": 1490,
                "shelf_depth": 430,
            },
        ),
        "params": BOXY,
        "sources": ["https://www.bakkerbrandstoffen.nl/product/the-bastard-large-complete/"],
        "estimated": ["egg height 870", "shelf depth 430"],
    },
    {
        "id": "bbq-monolith-classic-two55-tables",
        "name": "Monolith Classic (TWO.55) with side tables",
        "kind": "bbq_kamado",
        "rank": 20,
        "brand": "monolith",
        "build": (
            "kamado",
            {
                "egg_d": 550,
                "height": 1200,
                "egg_h": 820,
                "depth": 710,
                "width": 1200,
                "shelf_depth": 400,
            },
        ),
        "params": BOXY,
        "sources": [
            "https://www.grillfuerst.de/Monolith/Two/Two-55-Keramikgrill-mit-Gestell-Seitentische.php"
        ],
        "estimated": ["egg 550 x 820"],
    },
    # ---- gas -----------------------------------------------------------------------------------
    {
        "id": "bbq-weber-genesis-e-335",
        "name": "Weber Genesis E-335",
        "kind": "bbq_gas",
        "rank": 4,
        "brand": "weber",
        "build": (
            "gas",
            {"width": 1560, "depth": 685, "height": 1220, "shelf_h": 915, "hood_w": 880},
        ),
        "params": BOXY,
        "sources": ["https://www.weber.com/NL/nl/gasbarbecues/genesis-series/-/1501249.html"],
        "estimated": ["shelf height 915", "hood width 880"],
    },
    {
        "id": "bbq-weber-genesis-e-435",
        "name": "Weber Genesis E-435",
        "kind": "bbq_gas",
        "rank": 9,
        "brand": "weber",
        "build": (
            "gas",
            {"width": 1730, "depth": 685, "height": 1220, "shelf_h": 915, "hood_w": 1050},
        ),
        "params": BOXY,
        "sources": ["https://www.weber.com/NL/nl/gasbarbecues/genesis-series/-/1501267.html"],
        "estimated": ["shelf height 915", "hood width 1050"],
    },
    {
        "id": "bbq-weber-genesis-ii-ep-335",
        "name": "Weber Genesis II EP-335",
        "kind": "bbq_gas",
        "rank": 4,
        "brand": "weber",
        "warehouse": WH_GENESIS2,
        "params": BOXY,
        "sources": ["3D Warehouse " + WH_GENESIS2],
        "estimated": ["a 3D Warehouse model (Fran L.), not the maker's CAD: its sizes as modelled"],
    },
    {
        "id": "bbq-napoleon-prestige-500",
        "name": "Napoleon Prestige 500",
        "kind": "bbq_gas",
        "rank": 11,
        "brand": "napoleon",
        "build": (
            "gas",
            {"width": 1670, "depth": 670, "height": 1300, "shelf_h": 915, "hood_w": 900},
        ),
        "params": BOXY,
        "sources": ["https://www.bbqexperiencecenter.nl/napoleon-prestige-500-rsib/"],
        "estimated": ["shelf height 915", "hood width 900"],
    },
    {
        "id": "bbq-broil-king-regal-s590-pro",
        "name": "Broil King Regal S590 Pro",
        "kind": "bbq_gas",
        "rank": 16,
        "brand": "broil king",
        "build": (
            "gas",
            {"width": 1590, "depth": 630, "height": 1250, "shelf_h": 915, "hood_w": 900},
        ),
        "params": BOXY,
        "sources": [
            "https://www.grillgoods.de/products/broil-king-regal-s-590-pro-ir-inkl-drehspiess"
        ],
        "estimated": ["shelf height 915", "hood width 900"],
    },
    {
        "id": "bbq-weber-summit-fs38",
        "name": "Weber Summit FS38",
        "kind": "bbq_gas",
        "rank": 18,
        "brand": "weber",
        "build": (
            "gas",
            {"width": 1800, "depth": 685, "height": 1330, "shelf_h": 915, "hood_w": 1000},
        ),
        "params": BOXY,
        "sources": [
            "https://www.weber.com/AT/de/gasgrills/summit/summit-fs38-e-gasgrill/1500057.html"
        ],
        "estimated": ["shelf height 915", "hood width 1000"],
    },
    {
        "id": "bbq-napoleon-prestige-pro-665",
        "name": "Napoleon Prestige PRO 665",
        "kind": "bbq_gas",
        "rank": 22,
        "brand": "napoleon",
        "build": (
            "gas",
            {"width": 1950, "depth": 650, "height": 1300, "shelf_h": 915, "hood_w": 1150},
        ),
        "params": BOXY,
        "sources": ["https://www.bbqkopen.nl/product/napoleon-prestige-pro-665-rsib-zilver"],
        "estimated": ["shelf height 915", "hood width 1150"],
    },
    {
        "id": "bbq-broil-king-imperial-s690-xl",
        "name": "Broil King Imperial S690 XL",
        "kind": "bbq_gas",
        "rank": 25,
        "brand": "broil king",
        "build": (
            "gas",
            {"width": 1930, "depth": 630, "height": 1250, "shelf_h": 915, "hood_w": 1200},
        ),
        "params": BOXY,
        "sources": [
            "https://www.grillfuerst.de/broil-king/gasgrill/broil-king-imperial-690-xl-pro.php"
        ],
        "estimated": ["shelf height 915", "hood width 1200"],
    },
    # ---- pellet --------------------------------------------------------------------------------
    {
        "id": "bbq-weber-searwood-xl-600",
        "name": "Weber Searwood XL 600",
        "kind": "bbq_pellet",
        "rank": 17,
        "brand": "weber",
        "build": (
            "gas",
            {"width": 1280, "depth": 585, "height": 1160, "shelf_h": 900, "hood_w": 860},
        ),
        "params": BOXY,
        "sources": [
            "https://www.weber.com/DE/de/zubehoer/grill-schuetzen/abdeckhauben-fuer-pelletgrills/3400170.html"
        ],
        "estimated": ["hood width 860 (hopper inside the width)", "shelf height 900"],
    },
    {
        "id": "bbq-traeger-ironwood",
        "name": "Traeger Ironwood",
        "kind": "bbq_pellet",
        "rank": 19,
        "brand": "traeger",
        "build": ("pellet", {"width": 1500, "depth": 640, "height": 1220, "barrel_l": 900}),
        "params": BOXY,
        "sources": ["https://grillstar.de/products/traeger-abdeckhaube-ironwood"],
        "estimated": ["lid length 900", "hopper side"],
    },
    {
        "id": "bbq-traeger-ironwood-xl",
        "name": "Traeger Ironwood XL",
        "kind": "bbq_pellet",
        "rank": 19,
        "brand": "traeger",
        "build": ("pellet", {"width": 1778, "depth": 635, "height": 1219, "barrel_l": 1150}),
        "params": BOXY,
        "sources": ["https://www.traeger.com/nl/nl/pellet-grills/ironwood-xl"],
        "estimated": ["lid length 1150", "hopper side"],
    },
    {
        "id": "bbq-traeger-timberline",
        "name": "Traeger Timberline",
        "kind": "bbq_pellet",
        "rank": 21,
        "brand": "traeger",
        "build": (
            "gas",
            {"width": 1500, "depth": 640, "height": 1300, "shelf_h": 950, "hood_w": 1000},
        ),
        "params": BOXY,
        "sources": ["https://www.grillfuerst.de/Traeger/Pelletgrill/Timberline-Pelletsmoker.php"],
        "estimated": ["lid width 1000", "shelf height 950"],
    },
    # ---- fire tables ---------------------------------------------------------------------------
    {
        "id": "bbq-ofyr-classic-85",
        "name": "OFYR Classic 85",
        "kind": "bbq_fire_table",
        "rank": 12,
        "brand": "ofyr",
        "build": ("fire_table", {"width": 850, "height": 1000}),
        "params": KAMADO,
        "sources": ["https://ofyr.com/nl/products/ofyr-classic-black-85"],
        "estimated": ["cone base drawn"],
    },
    {
        "id": "bbq-ofyr-classic-100",
        "name": "OFYR Classic 100",
        "kind": "bbq_fire_table",
        "rank": 12,
        "brand": "ofyr",
        "build": ("fire_table", {"width": 1000, "height": 1000}),
        "params": KAMADO,
        "sources": ["https://ofyr.com/nl/products/ofyr-classic-black-100"],
        "estimated": ["cone base drawn"],
    },
]


def _warehouse_mesh(out: Path, entity: str) -> trimesh.Trimesh:
    """A 3D Warehouse GLB (glTF: Y up, metres) as one mesh in mm, Z up, on the ground."""
    sc = trimesh.load(out / "warehouse" / f"{entity}.glb")
    m = sc.to_geometry() if isinstance(sc, trimesh.Scene) else sc
    assert isinstance(m, trimesh.Trimesh)
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (1, 0, 0)))
    m.apply_scale(1000.0)
    lo, hi = m.bounds
    m.apply_translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
    return m


def _egg(out: Path, entity: str, d: float, depth: float, h: float) -> trimesh.Trimesh:
    """A measured egg from 3D Warehouse, its handle-to-hinge axis along y, scaled to the
    published diameter, depth and height."""
    m = _warehouse_mesh(out, entity)
    ext = m.bounds[1] - m.bounds[0]
    if ext[0] > ext[1]:  # the long plan axis (handle to hinge) along y
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, (0, 0, 1)))
        ext = m.bounds[1] - m.bounds[0]
    m.apply_scale((d / ext[0], depth / ext[1], h / ext[2]))
    lo, hi = m.bounds
    m.apply_translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
    return m


def build(spec: dict[str, Any], out: Path) -> tuple[trimesh.Trimesh, str]:
    if spec.get("warehouse"):
        return _warehouse_mesh(out, spec["warehouse"]), "3D Warehouse model, as modelled"
    fn, kw = spec["build"]
    kw = dict(kw)
    how = "drawn from the published sizes (coverengine.bbq)"
    if spec.get("warehouse_egg"):
        kw["egg_mesh"] = _egg(out, spec["warehouse_egg"], kw["egg_d"], kw["depth"], kw["egg_h"])
        how = (
            "egg: 3D Warehouse model scaled to the published sizes; nest and tables drawn "
            "from the published sizes"
        )
    if fn == "fire_table":
        return bbq.fire_table(**kw), how
    return getattr(bbq, fn)(**kw), how


def _run(args: list[str], log: Path) -> int:
    with log.open("a", encoding="utf-8") as f:
        f.write("$ " + " ".join(args) + "\n")
        f.flush()
        return subprocess.run(args, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT).returncode


def one(spec: dict[str, Any], out: Path, steps: set[str]) -> dict[str, Any]:
    guard_staging_output(out)
    mid = spec["id"]
    dst = out / "models" / mid
    guard_staging_output(dst)
    res: dict[str, Any] = {"id": mid, "name": spec["name"], "kind": spec["kind"],
                           "rank": spec["rank"]}  # fmt: skip
    cover = [sys.executable, "-m", "coverengine.cli"]
    log = out / "logs" / f"{mid}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    if "build" in steps:
        mesh, how = build(spec, out)
        src = out / "src" / f"{mid}.stl"
        src.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(src)
        if dst.exists():
            shutil.rmtree(dst)
        log.write_text("")
        rc = _run([*cover, "import", str(src), "--out", str(dst), "--units", "mm", "--up", "z",
                   "--front=-y"], log)  # fmt: skip
        if rc:
            return {**res, "error": f"import exit {rc}"}
        doc = {
            "format_version": 1,
            "model_id": mid,
            "tags": ["bbq", spec["brand"].replace(" ", "-"), spec["kind"]],
            "notes": f"BBQ staging: {spec['name']} ({how}). Sources: "
                     + "; ".join(spec["sources"])
                     + (f". Estimated: {'; '.join(spec['estimated'])}" if spec["estimated"] else ""),
            "parameters": spec["params"],
            "family": "bbq",
            "category": "BBQ › " + {"bbq_kamado": "Kamado", "bbq_kamado_table": "Kamado",
                                    "bbq_gas": "Gas", "bbq_pellet": "Pellet",
                                    "bbq_fire_table": "Fire table"}[spec["kind"]],
            "status": "new",
            "match": {"kind": spec["kind"], "name": spec["name"],
                      "families": [spec["brand"]]},
        }  # fmt: skip
        (dst / "cover.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")  # fmt: skip
        res["how"] = how
    if "cover" in steps:
        for step in ("hull", "cut", "flatten", "export"):
            rc = _run([*cover, step, str(dst), "--force"], log)
            if rc:
                return {**res, "error": f"{step} exit {rc}"}
    if "check" in steps:
        _run([*cover, "audit", str(dst), "--out", str(dst / "audit-out")], log)
        au = dst / "audit.json"
        if au.is_file():
            checks = json.loads(au.read_text())["checks"]
            res["audit_ok"] = all(c["ok"] for c in checks)
            res["audit_failed"] = {c["check"]: c["detail"] for c in checks if not c["ok"]}
        f = subprocess.run([sys.executable, str(ROOT / "scripts/fewer_check.py"), str(dst)],
                           cwd=ROOT, capture_output=True, text=True)  # fmt: skip
        res["fewer_exit"] = f.returncode
        res["fewer"] = [ln for ln in (f.stdout + f.stderr).splitlines() if ln.strip()][-4:]
    model = json.loads((dst / "model.json").read_text()) if (dst / "model.json").is_file() else {}
    res["size_mm"] = [round(float(x)) for x in model.get("size_mm", [])]
    fin = dst / "finished.json"
    if fin.is_file():
        fd = json.loads(fin.read_text())
        pieces = fd.get("pieces") or fd.get("panels") or []
        res["pieces"] = len(pieces)
        res["fabric"] = {k: fd[k] for k in ("fabric_m2", "roll_length_mm", "cut_area_m2")
                         if k in fd}  # fmt: skip
    hj = dst / "hull.json"
    if hj.is_file():
        h = json.loads(hj.read_text())
        res["plan"] = h.get("plan") or (h.get("box") or {}).get("plan")
    res["picture"] = str(dst / "cover.png") if (dst / "cover.png").is_file() else None
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("--only", default="")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--steps", default="build,cover,check")
    a = ap.parse_args()
    guard_staging_output(a.out)
    steps = set(a.steps.split(","))
    only = {x for x in a.only.split(",") if x}
    specs = [s for s in SPECS if not only or s["id"] in only]
    with ThreadPoolExecutor(max_workers=max(1, min(a.jobs, 2))) as ex:  # at most 2 workers
        results = list(ex.map(lambda s: one(s, a.out, steps), specs))
    old = {}
    rj = a.out / "results.json"
    if rj.is_file():
        old = {r["id"]: r for r in json.loads(rj.read_text())}
    old.update({r["id"]: r for r in results})
    allr = sorted(old.values(), key=lambda r: (r["rank"], r["id"]))
    rj.write_text(json.dumps(allr, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (a.out / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "id", "kind", "size_mm", "pieces", "audit_ok", "fewer_exit", "error"])
        for r in allr:
            w.writerow([r["rank"], r["id"], r["kind"], r.get("size_mm"), r.get("pieces"),
                        r.get("audit_ok"), r.get("fewer_exit"), r.get("error", "")])  # fmt: skip
    for r in results:
        ok = r.get("audit_ok") and r.get("fewer_exit") == 0 and not r.get("error")
        print(f"{r['id']:<40} {'ok' if ok else 'CHECK'} {r.get('error', '')} "
              f"{r.get('audit_failed', '')}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
