# Plan: milestones and acceptance criteria

Work top to bottom. A milestone is done when every acceptance criterion passes and
`docs/reports/M<n>.md` exists. PHYSICAL GATE means the owner cuts or welds a sample and reports
measurements before the next milestone starts; the physical gates set the pace more than the
coding does.

Order is chosen for the earliest possible welded cover: M0 to M5 produce machine-ready patterns
from the command line and template seams; M6 makes it a web tool; M7 to M9 make it fit 300
models and 100 covers a week.

---

## M0 — Bootstrap and machine smoke test

Goal: a working Python project, CI, procedural test shapes, and the DXF conventions of the real
cutting machine learned from a test sheet.

Tasks
- `uv`-managed Python 3.12 project. Package `engine/coverengine` with `cover` CLI (`cover
  version`, `cover info <mesh>`). Dependencies pinned in `pyproject.toml` and `uv.lock`.
- `testdata/generate.py`: deterministic procedural shapes written to `testdata/generated/`
  with a JSON sidecar of analytic dimensions: plate, open cylinder, open cone, sphere, sphere
  octant, saddle, torus segment; furniture primitives: box with four legs, slatted table (slats
  with 20 mm gaps on legs), simple chair (seat slab, tilted back slab, four legs), L-shaped
  lounge block.
- Test sheet DXF for the machine: three rectangles and one circle on layer CUT; text labels,
  short tick marks and a curved guide line on layer PEN; a second variant with layer names `0`
  and `1`; a third with text converted to line strokes. Units mm, closed LWPOLYLINEs.
- Parameter registry: load `config/defaults.yaml`, resolve the override layers (defaults →
  preset → CoverDefinition → `--set`), `cover params` printing each effective value with its
  source, and a test that fails when engine code contains a numeric literal equal to a
  registered default outside the registry itself.
- Makefile with the commands from CLAUDE.md (stubs where the target does not exist yet).
- GitHub Actions: `make test` on push. `ruff`, `mypy` (lenient), `pre-commit`.
- `docs/LICENSES.md` listing every dependency and its licence.
- `deploy/docker-compose.yml` skeleton with api, web and cloudflared services (not deployed yet).

Acceptance
- `make test` green locally and in CI.
- `cover info testdata/generated/cylinder.stl` reports the analytic dimensions within 1e-6 mm.
- Editing a value in `config/defaults.yaml` changes the output of `cover params` with no code
  change; `--set` overrides it for one run and is shown as the source.
- Owner has imported the test sheets into the machine software, cut and drawn them, and
  reported: which layer names work, whether TEXT is drawn or strokes are needed, arc handling,
  scale correct to 1 mm. Result recorded in docs/FORMATS.md.

---

## M1 — Import of detailed furniture models

Goal: any file the manufacturer sends becomes a canonical mesh on the ground plane in mm, even
if it is a dirty assembly with thousands of parts.

Tasks
- STEP and IGES via `cadquery-ocp`: assemblies, unit detection, tessellation with a deflection
  parameter, per-part bookkeeping (name, volume, bounding box).
- STL, OBJ, PLY, glTF/GLB via `trimesh`.
- Part filtering: drop parts below a volume or bounding-box threshold (screws, washers), keep an
  exclusion list per model. No requirement for watertight input: downstream works on triangle
  soups via winding numbers.
- Unit heuristics (warn, never guess silently), up-axis handling, placement with the lowest
  point at z = 0 and the front of the furniture toward −Y (owner confirms per model in the UI
  later; CLI flag now).
- Canonical output: `model.glb` plus `model.json` (source hash, units, parts kept and dropped,
  bounding box).
- CLI: `cover import <file> --out models/<id>/ [--units mm|inch|m] [--min-part-mm 8]`.

Acceptance
- All procedural shapes import; a detailed STEP sample (or a synthetic assembly of 2,000 parts
  until samples exist) imports in under 2 minutes with parts filtered as configured.
- Same file twice produces identical canonical output.
- Golden `cover info` output for each test model.

---

## M2 — Drape hull (cover surface)

Goal: compute the surface a tight fabric cover takes over the furniture: hangs from the widest
point, bridges slat gaps, keeps a clearance, stops at hem height.

Tasks
- Occupancy and signed distance grid from the triangle soup (`libigl` fast winding number),
  resolution parameter (default 5 mm), adaptive coarsening for large pieces.
- Vertical downward sweep: a cell is covered if any cell above it is occupied. Stops at
  `hem_height_mm` above ground. Optional flag to disable for fitted covers.
- Gap bridging by morphological closing with radius `bridge_gap_mm` / 2 (default 60 mm, so slat
  gaps are bridged and large recesses like the seat-to-back corner are followed).
- Clearance by shifting the iso-level by `clearance_mm` (default 10).
- Marching cubes, then smoothing with a tension parameter and isotropic remeshing to a target
  edge length (default 15 mm), then clipping the bottom open at hem height and orienting normals
  outward.
- Region masks: exclude features by box or by part (do not cover under a table apron, leave a
  cable gap); hard edges the cover must follow.
- Quality report: minimum distance to the model (must be ≥ clearance), area, bounding box,
  number of sharp ridges (seam candidates for M3).
- CLI: `cover hull models/<id>/ --clearance 10 --bridge-gap 60 --hem-height 50 --out hull.glb`.

Acceptance
- Slatted table: top is flat at bridge gap 60, follows slats at bridge gap 10; skirt is vertical
  from the table edge to hem height.
- Chair primitive: hull follows seat and back, hangs vertically at the sides and rear.
- Minimum distance to the model ≥ clearance on every test shape (test).
- 500k-triangle soup processed in under 60 s on the VPS.

---

## M3 — Seams and patches

Goal: split the hull into weldable, disk-shaped panels no wider than the roll, first by
template and ridge detection, later by hand in the UI.

Tasks
- Seam graph format (docs/FORMATS.md): seams as anchor points on the surface plus geodesic
  paths between them (`potpourri3d` edge-flip geodesics), snapped onto mesh edges by local
  refinement so seams are exact edge paths.
- Ridge detection on the hull (dihedral angle threshold) as seam candidates: skirt corners,
  top edges, seat-to-back transitions.
- Templates for furniture families: box cover (top plus four skirt panels), table (top plus
  skirt, optional apron), chair (seat and back top panel, two sides, back, front skirt),
  lounger, L-shaped lounge set. A template picks ridges and adds seams so every patch is a disk
  within the roll width.
- Symmetry: mirror seams across the furniture's symmetry plane.
- Partition with `igl.cut_mesh`; verify every patch is a topological disk; roll-width pre-check
  on the 3D patch extent with a proposed extra seam when too wide.
- Seam attributes: `lap_side` from relative height (upper panel over lower; front panel over
  side on vertical seams), 3D length, minimum radius with a flag below `min_weld_radius_mm`.
- CLI: `cover cut hull.glb --template chair --out patches/` and `--seams seams.json`.

Acceptance
- Box template on the box primitive gives exactly five disk patches; chair template on the chair
  primitive gives the expected patch count; all patches disks; symmetric patches have equal
  areas within 0.1 %.
- Seams are exact edge paths; every seam knows both patches, its length and its lap side.

---

## M4 — Flattening — PHYSICAL GATE (paper or cheap fabric)

Goal: every patch becomes a 2D panel in true mm with measured stretch, and adjacent panels
agree on seam lengths.

Tasks
- Initial map (Tutte or LSCM), then SLIM (`igl.SLIM`, symmetric Dirichlet) iterations; ARAP
  behind a flag for comparison. Scale so the mean 2D/3D edge-length ratio is 1; rotate so the
  panel's UP direction (toward the top of the furniture) points to +Y; translate to origin.
- Stretch metrics per triangle (singular values) and per panel (max stretch %, mean stretch %,
  area distortion) plus heatmap data.
- Seam length matching: compare 2D lengths of shared seams; record `ease_mm` when above
  tolerance; second step, re-solve with soft boundary-length constraints where the fabric
  allows.
- Fabric compensation from the profile (anisotropic scaling for stretch and weld shrinkage;
  placeholder profile until M8).
- Roll-width check on the 2D panel (minimum width over rotations) with an automatic split
  proposal along a low-stretch straight line.
- Stretch limit check against `max_allowed_stretch_pct`; propose an extra seam where exceeded.
- Output `PatternSet` JSON including the full effective parameter set and its hash. CLI:
  `cover flatten patches/ --fabric acrylic-300 --out pattern.json`.
- `cover run <model> [--set key=value ...]` runs import → hull → cut → flatten → export in one
  command; `cover diff a.json b.json` lists panels whose dimensions changed by more than 1 mm,
  with the parameter differences that caused them. `make demo` is `cover run` on the chair.

Acceptance
- Plate, cylinder and cone flatten with under 0.05 % length error and zero seam mismatch.
- Sphere octant and saddle: max stretch equals the golden value within 0.5 percentage points.
- Byte-identical output on repeated runs; a 200k-triangle patch flattens in under 3 s.

Physical gate
- 1:1 SVG or DXF of one real chair or table cover (no allowances). Owner cuts paper or cheap
  fabric, tapes the panels together, puts the cover on the furniture and measures at five agreed
  points (docs/CALIBRATION.md). Results in docs/reports/M4.md; tolerance changes in
  docs/DECISIONS.md.
- Expected loop: measurements come back, one or two values change in `config/defaults.yaml`
  or the model's CoverDefinition, `cover run` produces the next version, `cover diff` shows what
  moved. No code changes during this loop unless the diff reveals an algorithm error.

---

## M5 — Welded finishing and machine export — PHYSICAL GATE (first welded cover)

Goal: production panels with weld overlaps, hem, pen marks and a DXF the machine imports
directly.

Tasks
- Overlap allowance on the lap-side panel only (`overlap_mm`, default 30), mitred corners where
  overlaps meet; hem allowance (default 50 mm) with the fold line on PEN; openings for cord
  exits, strap attachment marks, vent slits as configured features.
- PEN layer content: panel id and name, mate reference at each seam ("→ P3"), weld guide line on
  the under panel, alignment ticks at matched positions along shared seams, UP arrow, hem fold
  line, model name and pattern revision. Text as TEXT entities or stroked lines, whichever M0
  showed the machine needs.
- DXF export per pattern set: all panels on one virtual sheet with spacing (the machine software
  nests), closed LWPOLYLINEs on CUT, lines and text on PEN, units mm, layer names from M0.
- SVG preview (1:1 mm) and a PDF cutting list: panel table with id, quantity, bounding box,
  area, total fabric estimate at 1500 mm roll width.
- CLI: `cover export pattern.json --fabric acrylic-300 --out export/`.

Acceptance
- Offsets and tick positions covered by unit tests on simple polygons; SVG dimensions equal panel
  bounding boxes exactly.
- Machine imports the DXF, cuts and draws a test panel; measured outline within 1 mm.

Physical gate
- First welded cover from the DXF, fitted on the real furniture, measured at the five points.
  Target ±5 mm. Results in docs/reports/M5.md.

---

## M6 — Web app and deployment

Goal: the owner (and colleagues) run the whole flow in a browser on the VPS without Claude Code
present.

Tasks
- FastAPI: models, cover definitions, pattern sets, exports; upload; background jobs in a
  process pool with progress over WebSocket; per-session in-memory hull for interactive edits;
  SQLite metadata; data directory on disk.
- React app: model upload with unit and up-axis confirmation; 3D viewer with model and hull
  overlay, hull parameter sliders with live recompute; template choice and manual seam editing
  (click anchors, geodesic preview, drag to adjust); patch colours and stretch heatmap; roll-width
  and weld-radius warnings; 2D panel view with allowances and pen marks toggled; export
  downloads; pattern revisions per model.
- Parameter panel generated from the parameter registry: same keys and grouping as
  `config/defaults.yaml`, YAML comments as tooltips, each field showing its current source
  (default, preset, this model, trial). A "trial" toggle lets the operator move sliders and
  recompute without saving; "save for this model" writes them into the CoverDefinition;
  "propose as new default" opens a diff for the owner to commit into `config/defaults.yaml`.
- Every pattern revision page shows the exact parameters used and a diff against the previous
  revision (`cover diff` in the browser).
- Deployment: Docker Compose (api, web behind a reverse proxy, cloudflared) on the VPS,
  Cloudflare Tunnel with a token from the Zero Trust dashboard, Cloudflare Access policy for the
  company's users, nightly `rclone` backup of the data directory to R2, restore procedure tested
  once.
- Operator handbook: docs/handbook/getting-started.md.

Acceptance
- Owner imports a STEP in the browser, gets a hull, applies a template, adjusts one seam,
  flattens and downloads a DXF in under 15 minutes for a known family, without help.
- Playwright end-to-end test of that flow against the procedural chair.
- Reachable only through Access; `nmap` shows SSH as the only open port; a restore from backup
  works.

---

## M7 — Model families, presets and batch

Goal: 300 models and 100 covers a week without repeating work.

Tasks
- Family presets: a `CoverDefinition` template applied to a new model of the same family in one
  click; per-model overrides. Presets are layer 2 of the parameter registry, stored as YAML in
  `config/presets/<family>.yaml`, so a change to a family applies to every model that has no
  own override.
- Model status (draft, validated, production) and revision history with diffs of parameters and
  panel dimensions.
- Batch: re-import, re-hull and re-export a selection of models when a preset or the engine
  changes; report what changed beyond 1 mm.
- Search and tagging of the catalogue; per-model notes for the machine operator.

Acceptance
- 20 models of one family processed with one preset; changed panels highlighted; total operator
  time per new model under the success criterion.

---

## M8 — Fabric and weld calibration

Goal: replace placeholder fabric numbers with measurements so the ±5 mm target holds across
sizes.

Tasks
- Swatch protocol from docs/CALIBRATION.md for the acrylic: stretch warp, weft, bias under a
  representative load; relaxation; weld shrinkage along and across a welded seam; thickness.
- `scripts/fabric_profile.py` converts measurements to `testdata/fabrics/acrylic-300.json`.
- Validation on three covers of different size classes.

Acceptance
- Measured profile in place; the three covers fit within ±5 mm; report with numbers.

---

## M9 — Hardening and later options

- Robustness pass over the full catalogue: every model imports and hulls, failures produce
  actionable messages.
- Performance on the largest detailed assemblies; caching of hulls; resource limits per job.
- Monitoring and error reporting; upgrade and rollback procedure.
- Options to evaluate only if needed: nesting inside the tool (if the machine software wastes
  fabric), browser-side WebAssembly engine (if server latency hurts editing), cloth simulation
  as a realism check, migration to Cloudflare Containers (if the single VPS becomes a limit).

---

## Cross-cutting

- docs/FORMATS.md is the source of truth for JSON and file formats; update it with the code.
- Every report is written for a non-developer and ends with a "try it yourself" section.
- Golden tests are updated only with a DECISIONS.md entry explaining why the numbers changed.
