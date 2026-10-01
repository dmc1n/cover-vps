# Cover pattern engine

Internal tool that turns a 3D model of a piece of outdoor furniture into machine-ready 2D
cutting patterns for a stitched or hot-air-welded acrylic cover. Users load a model in a web
dashboard, adjust the cover for that model (fit, seams, hem, features) and download a DXF for
the cutting table.

Why: Inventor's flat pattern only unfolds developable sheet-metal geometry and Blender's UV
unwrap optimises for texturing, not for weldable, dimensionally accurate panels. The 3D-to-2D
step is the bottleneck in our production today. We own the engine so we control the algorithms
and the direction.

## The business in numbers

- Product: covers for outdoor furniture (chairs, tables, lounge sets, loungers, ...).
  Tight-fitting by default, with a per-model option to loosen the fit.
- Catalogue: 200 to 300 furniture models, new ones arrive regularly. Production about 100
  covers per week, in house.
- Models: whatever the furniture manufacturer provides (STEP, Inventor exports, STL, ...), often
  very detailed assemblies with slats, screws and cushions. The engine must cope with dirty
  triangle soups, not just clean meshes.
- Fabric: 100 % acrylic canvas, roll width 1500 mm, no direction constraint on panel rotation.
- Construction: chosen per model (`construction.method`, ADR-020). Today panels are joined by
  double stitching; hot-air welded overlap seams (100 % waterproof) are the other option.
- Machine: CNC cutting table with its own nesting software. It imports DXF and has a pen for
  drawing on the fabric. We export panels, labels and weld guide lines; the machine nests.
- Fit tolerance: ±5 mm.
- Users: internal only, a handful of people. UI in English, units mm.
- Team: Claude Code is the only developer. The owner is product manager, machine operator and
  tester. Speed matters: aim for the earliest possible sewn or welded sample, then iterate.

## Success criterion for version 1

A new furniture model goes from imported 3D file to machine-ready DXF in under one hour of
operator time, and the first finished cover fits within ±5 mm with at most one correction round.
This target is ours; if reality differs, change it in docs/DECISIONS.md with the reason.

## Still to confirm with the owner (Claude Code asks when a milestone needs it)

Each assumption below is a key in `config/defaults.yaml`; confirming or changing it is a
one-line edit there.

- Double-stitched seam construction (`stitching.*`): seam type, allowance width (assumed
  15 mm), allowance on one or both panels, whether cut notches are acceptable for stitching.
- Weld overlap width (`welding.overlap_mm`), for models set to welded. Assumed 30 mm, carried
  entirely by the upper (outer) panel.
- Hem construction (`hem.*`, `hull.hem_height_mm`). Assumed a welded hem with a drawcord or
  elastic channel, 50 mm allowance, hem edge 50 mm above the ground.
- Standard features: drawcord hem, wind straps with buckles, handles: which are standard,
  which optional per model? Air vents are standard (owner, 2026-09-30): 25 x 22 cm (W x H), bottom
  edge 5 cm above the lower end of the cover, one per full metre of hem length, spread evenly,
  at least one. Built as a cut opening with a hood of extra fabric holding a plastic insert
  that keeps it open, and a membrane inside against dirt (`features.vent_*`, pieces in M5).
- Machine make and model, and its DXF conventions (layer names, whether it draws TEXT entities
  or needs stroked lines, arc support). Learned in M0 by cutting a test sheet.
- Sample models: 3 to 5 representative STEP or STL files in `testdata/models/` (git-ignored,
  because the repository is public). One so far: the Blocchi 2-seater, a mesh saved as STEP
  (ADR-023). More detailed CAD samples (curved tubes, bolts) still wanted.
- Tent support for tables (frame or balloon): its height and shape, and the minimum slope that
  lets water run off reliably.
- Cloudflare account and preferred Access login method. (GitHub: `dmc1n/cover-vps`, in use.)
- Measured fabric values (stretch, weld shrinkage) from swatch tests in M8. Placeholders until
  then, clearly marked.

## Architecture (see docs/DECISIONS.md; ADR-008 onward supersede the first draft)

Python engine, server side, one VPS.

- `engine/` — Python 3.12 package `coverengine` containing all geometry. Heavy lifting happens
  in compiled libraries: `libigl` (SLIM and ARAP parameterisation, winding numbers, cut_mesh,
  decimation), `potpourri3d` (geometry-central geodesic paths), `trimesh` (mesh I/O),
  `cadquery-ocp` (OpenCascade for STEP and IGES), `manifold3d` and `pymeshlab` (repair,
  remeshing), `numpy`, `scipy` and `scikit-image` (SDF grids, marching cubes), `shapely` (2D
  offsets), `ezdxf` (DXF read and write).
- `apps/api/` — FastAPI: REST plus WebSocket sessions that keep a model in memory while the
  user edits, background jobs in a process pool, SQLite for metadata, files on local disk.
- `apps/web/` — React, TypeScript, Vite, Three.js: 3D viewer with drape-hull overlay, seam
  editing with geodesic preview, patch colours and stretch heatmap; SVG 2D pattern view;
  parameter panel generated from JSON schema; export downloads.
- Deployment: Docker Compose on the Hetzner VPS (api, web, cloudflared). Reachable only through
  a Cloudflare Tunnel protected by Cloudflare Access; the firewall allows SSH alone. Nightly
  backups of the data directory to Cloudflare R2. Cloudflare Workers and Containers are not
  used for now.

Why not the C++ / WebAssembly / Cloudflare Containers design of the first draft: with one
developer and an internal tool for a handful of users, Python on one server reaches a welded
sample many weeks earlier. The compiled geometry libraries are the same either way. If
browser-side compute or a sellable product is ever needed, the Python engine and its golden
tests become the specification for a port.

Pipeline: import → drape hull (cover surface) → seams and patches → flatten → finishing
(stitched or welded allowances, pen marks) → DXF export. Nesting is the machine's job.

## Repository layout

```
engine/coverengine/       io/ hull/ seams/ flatten/ finish/ export/ and cli.py (`cover` command)
engine/tests/             pytest unit tests and golden tests
engine/schemas/           JSON schemas: CoverDefinition, PatternSet, FabricProfile, SeamGraph
config/defaults.yaml      every default parameter, commented; the only place numbers are set
apps/api/                 FastAPI app, SQLite migrations, job runner, Dockerfile
apps/web/                 React app
deploy/                   docker-compose.yml, reverse proxy config, cloudflared, backup scripts
testdata/                 models/ (owner samples, git-ignored) fabrics/ golden/ generated/ machine/,
                          shapes.yaml, generate.py
docs/                     PLAN.md DECISIONS.md FORMATS.md CALIBRATION.md LICENSES.md reports/ handbook/
scripts/                  setup-vps.sh, licenses.py (regenerates docs/LICENSES.md) and utilities
```

## Domain rules the engine must respect

1. Units are mm, coordinates right-handed Z-up, ground plane at z = 0. Models are placed on the
   ground at import. The web viewer converts to Y-up for display only.
2. A cover is not the object's surface. The cover surface is the drape hull: the model swept
   vertically down to hem height (fabric hangs from the widest point above it), gaps narrower
   than `bridge_gap_mm` bridged, offset outward by `clearance_mm`, smoothed, open at the bottom.
3. Flattening preserves lengths (SLIM or ARAP); conformal methods only as an initial guess. A
   panel's dimensional error must stay below 2.5 mm so the assembled cover meets ±5 mm.
4. Adjacent panels have matching seam lengths within `seam_tolerance_mm` (default 1.0), or the
   difference is recorded as explicit ease on that seam. Never a silent mismatch.
5. No panel may be wider than `usable_width_mm` (default 1480) in its narrowest orientation.
   Panel rotation is free. Violations are reported together with a proposed split.
6. Seam allowances follow `construction.method` (per model). Stitched seams: rules to be
   confirmed with the owner before M5 (`stitching.*`). Welded seams: the overlap allowance is added to one panel only, the `lap_side`. For water
   run-off the upper panel laps over the lower one; on vertical seams the default is the panel
   facing the front of the furniture. The under panel receives a weld guide line on the PEN
   layer where the upper panel's raw edge must land.
7. Nothing is cut into the fabric except the outline and deliberate openings. Labels, mate
   references, alignment ticks, fold lines and UP arrows go on the PEN layer. No cut notches.
8. Seams, welded ones especially, prefer gentle curvature. Seams with a radius below `min_weld_radius_mm`
   (default 150, to confirm at the machine) are flagged in the UI and the report.
9. The fabric profile (stretch warp, weft and bias, weld shrinkage, thickness) is an input to
   flattening and allowances. `testdata/fabrics/acrylic-300.json` holds clearly marked
   placeholders until swatch tests exist.
10. Deterministic output: the same input and parameters produce identical files.
11. Golden tests on analytic shapes (plate, cylinder and cone flatten exactly; sphere octant and
    saddle within stored bounds) and on procedural furniture primitives (chair, slatted table,
    box with legs) protect every algorithm change.
12. Water must always run off (owner, 2026-09-30). The cover surface may hold no water: no
    hollows, no flat areas on top; from every point of the top there is a downhill path to
    the edge. Seats and recesses are therefore spanned, not followed (the reference cover of
    the Blocchi sofa runs straight from the front edge to the top of the back). Flat tops
    (tables) get a raised support under the cover, a frame or a balloon, so the fabric forms
    a tent.
13. Every seam is an easy, smooth line for clean stitching (owner, 2026-09-30, all covers): no
    zig-zag (`seams.max_wiggle_mm`, checked on every panel edge), and the skirt seam at one
    height all round so skirt panels are straight strips (`seams.skirt_seam: level`).
14. Physical gates in the plan are real. Claude Code prepares the exports and a measurement
    sheet, then stops until the owner reports results.

## Parameters: one file, layered overrides

Every number the engine uses lives in `config/defaults.yaml`, each with a comment and a "to
confirm" mark where it is still an assumption. No numeric literal in engine code may duplicate a
default; a test enforces this against the registry. Values layer in this order, later wins:

1. `config/defaults.yaml`: company defaults, edited by hand, one commit per change.
2. Family preset (M7): per furniture family.
3. The model's `CoverDefinition`: per model, edited in the UI.
4. One-off override for a trial run: CLI `--set hull.clearance_mm=15` or a UI slider marked
   "trial", not saved unless the user says so.

`cover params <model>` prints every effective value with its source. Every exported PatternSet
stores the full effective parameter set and its hash, so any pattern can be reproduced or
compared later. `cover diff a.json b.json` lists panel dimensions that changed by more than
1 mm between two runs. Changing a parameter after a physical test is therefore: edit one line
or move one slider, run `cover run <model>`, read the diff. The web app exposes the same keys
with the YAML comments as tooltips. Golden tests pass their parameters explicitly, so changing a
company default never breaks a test by accident.

## Data model (details in docs/FORMATS.md)

- `Model`: imported files, canonical mesh, metadata, unit and up-axis decisions.
- `CoverDefinition`: a sparse `parameters` tree with the registry keys this model changes
  (hull, construction method, hem, allowances, ...), plus hull masks, seam graph or template id
  and the feature list (hem channel, straps, vents, handles).
- `PatternSet`: panels plus metadata (model version, engine version, parameter hash, stretch
  summary, fabric estimate).
- `Panel`: id, name, quantity, mirror flag, outline (closed polyline in mm), edges (kind = seam
  | hem | opening, mate, lap_side, overlap_mm, length_3d, length_2d, ease_mm), pen marks
  (labels, guide lines, ticks, UP arrow), stretch metrics.

## Commands (contract; M0 creates them)

```
make setup      uv sync, npm install, pre-commit hooks
make test       pytest (unit and golden), ruff, mypy
make demo       full pipeline on the procedural chair, DXF and SVG written to out/
cover run <model> [--set key=value ...]     import → hull → cut → flatten → export in one go
cover params <model>                        effective parameters and where each comes from
cover diff a.json b.json                    panel dimensions that changed by more than 1 mm
cover import <file> --out models/<id>/      STEP/IGES/STL/OBJ/PLY/GLB → model.glb, model.json, parts.json,
                                             kind.json (furniture or cover surface, ADR-039)
cover hull models/<id>/ [--clearance N ...]  drape hull → hull.glb, hull.json, preview.glb
cover cut models/<id>/ [--seams FILE]        seams and panels → panels.glb, panels.json
cover flatten models/<id>/                   flat patterns → pattern.dxf, pattern.svg, pattern.json, sizes.pdf
cover drawing models/<id>/                   size drawing of cover and panels → sizes.pdf
cover export models/<id>/                    finished pieces → cut.dxf, cut.svg, cutting-list.pdf, finished.json
                                             (and a revision in revisions/<n>/)
cover model models/<id>/ [--family F --status S --tags a,b --notes ...]   catalogue info, revisions
cover batch [--family F | --ids a,b] [--steps hull,cut,flatten,export] [--set ...]  many models, what changed
cover improve models/<id>/ [--rounds 4]      take seam proposals while they lower the worst stretch
cover report [--models DIR --tag T --out DIR]  catalogue report: every model ready / check / failed
cover ai models/<id>/ [--apply ACTION [--value N] --run]   AI advice on the layout (ai_review.json)
cover preview models/<id>/                   3D picture of the cover (cover.png; export makes it too)
uv run python scripts/warehouse.py list|fetch|photos   products from 3D Warehouse (GLB, photos)
make e2e        the web app flow in a real browser (Playwright in Docker)
cover info <mesh | model dir>               size, triangles, area; analytic check for test shapes
cover testsheet --out DIR                   M0 machine test sheet DXFs
make shapes     procedural test shapes into testdata/generated/
make testsheets regenerate testdata/machine/*.dxf (a test checks they are current)
make golden     regenerate testdata/golden/info/ and hull/ (golden outputs), then review the diff
make api-dev    web app and API on :8080     make web-dev   Vite dev server on :5173
make web-build  build the pages (apps/web/dist)
make deploy     build the app image and `docker compose up -d app` (127.0.0.1:8080)
make backup     push the data directory to R2 with rclone
```

## How to work in this repo (instructions for Claude Code)

- You are the only developer. Decide technical matters yourself (libraries within the stack,
  algorithms, code structure) and record them in docs/DECISIONS.md. Ask the owner only about
  domain and business questions: fabric and welding values, what a good cover looks like, UX
  preferences, priorities.
- Follow docs/PLAN.md in order. Start each milestone in plan mode, show the plan, wait for a go.
  Finish each milestone with `docs/reports/M<n>.md` written for a non-developer: what works
  now, how to try it, what was measured, what comes next. Then stop.
- `main` always works. Small commits, `make test` before every commit, push at the end of every
  session. Deploy only from tagged commits and never leave the deployed app broken.
- At a physical gate produce the files, a printed checklist and a measurement sheet, then wait.
  Record results and every tolerance change in docs/DECISIONS.md.
- A parameter change after a test is an edit to `config/defaults.yaml` or to the model's
  `CoverDefinition`, never a change in code. If a test shows that a value needs to exist that is
  not yet a parameter, make it one first.
- Prefer the simplest approach that meets the acceptance criteria; write the better alternative
  into docs/DECISIONS.md instead of building it early.
- Licences: this is an internal tool, so any OSI licence is acceptable, GPL included. Keep
  docs/LICENSES.md current so a later decision to sell the software stays possible.
- Secrets live only in environment variables or `deploy/.env` (git-ignored). Never in code,
  logs or reports.
- Write the operator handbook in docs/handbook/ as features land; the owner is the first user.
- Keep this file current in the same commit as the change it describes.
