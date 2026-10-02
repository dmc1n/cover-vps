# Decision log

Append new entries at the bottom. Format: context, decision, alternatives considered,
consequences. Keep entries short; link to code or reports for detail. Superseded entries stay
in place with a note.

## ADR-001 — Build our own engine

Context: Inventor flat pattern (sheet metal, developable surfaces only) and Blender UV unwrap
(texture-oriented, no real units, allowances or fabric model) do not produce weldable patterns;
the 3D-to-2D step is our production bottleneck.
Decision: build a custom 3D-to-2D pattern engine so we control algorithms and product direction.
Alternatives: ExactFlat (SolidWorks/Rhino plugin); Rhino + Grasshopper published via ShapeDiver
or Rhino.Compute. Both faster to a first result, neither ours.
Consequences: an engineering project of months; full ownership of the IP.

## ADR-002 — One C++ core compiled to WASM and natively (SUPERSEDED by ADR-008)

Original decision for a team with a C++ geometry engineer and a public product. Kept for
history; see ADR-008 for why it changed.

## ADR-003 — Length-preserving flattening

Context: fabric patterns must preserve lengths and areas; conformal maps scale panels
non-uniformly.
Decision: SLIM (symmetric Dirichlet) as the default solver, ARAP as alternative; conformal
methods only as initial guesses; explicit seam length matching between adjacent panels.
Consequences: golden tests on developable shapes must pass exactly; stretch metrics are part of
the output format.

## ADR-004 — Cover surface via SDF (refined by ADR-010)

Decision: generate the cover surface from a signed distance field with clearance and a
tightness-controlled smoothing, not by offsetting the model surface. Cloth simulation deferred.
Consequences: robust to dirty input because winding numbers work on triangle soups.

## ADR-005 — Cloudflare Workers, Containers and R2 as platform (SUPERSEDED by ADR-009)

Kept for history. R2 remains in use for backups.

## ADR-006 — Licence policy (RELAXED by ADR-013)

## ADR-007 — Units and coordinate system

Decision: millimetres everywhere in the engine; right-handed Z-up; ground plane at z = 0; the
web viewer converts to Y-up for display only; all exports 1:1 mm.
Consequences: loaders take explicit unit and up-axis flags; heuristics only warn.

## ADR-008 — Python engine on compiled libraries, not a C++ core

Context: Claude Code is the only developer, the tool is internal for a handful of users, and
the owner wants a welded sample as early as possible. The C++/Emscripten toolchain and
dependency management would cost weeks before the first geometry result.
Decision: Python 3.12 engine using compiled libraries (libigl, geometry-central via potpourri3d,
OpenCascade via cadquery-ocp, manifold3d, pymeshlab, shapely, ezdxf). Everything runs on the
server; the browser only renders and edits.
Alternatives: C++ core with WASM (original plan); Rust.
Consequences: no browser-side compute; interactive edits go through a WebSocket session that
keeps the hull in memory. If browser-side compute or a sellable product is ever needed, the
Python engine and its golden tests are the specification for a port.

## ADR-009 — One Hetzner VPS behind Cloudflare Tunnel and Access

Context: internal tool, few users, one developer, Cloudflare account already exists.
Decision: Docker Compose on the VPS (api, web, cloudflared). Exposed only through a Cloudflare
Tunnel with Cloudflare Access in front; firewall allows SSH only. Nightly backups to R2.
Alternatives: Cloudflare Workers + Containers (original plan; more moving parts than the use
case needs); a managed Kubernetes or ECS setup.
Consequences: single point of failure mitigated by backups and a documented restore; vertical
scaling by resizing the VPS; migration to Containers remains possible because the engine is a
plain Docker image.

## ADR-010 — Drape hull for furniture covers

Context: outdoor furniture covers hang from the widest point of the piece and bridge slat gaps;
they do not follow undercuts or individual slats. Fit must be tight with an option to loosen.
Decision: cover surface = occupancy grid of the model swept vertically down to hem height,
morphologically closed with `bridge_gap_mm`, offset by `clearance_mm`, marching cubes, smoothing,
isotropic remesh, open bottom at `hem_height_mm`.
Alternatives: shrink-wrap without the gravity sweep (fails on undercuts such as armrests);
cloth simulation (realistic, slow, harder to make deterministic; kept as a later check).
Consequences: three intuitive parameters for the operator (clearance, bridge gap, hem height);
the hem cord pulling the skirt inward is modelled by the hem feature, not by the hull.

## ADR-011 — Welded overlap seams and pen marks

Context: hot-air welded, 100 % waterproof, no stitching; the cutter has a pen.
Decision: the overlap allowance (default 30 mm, to confirm) goes on the lap-side panel only;
the upper panel laps over the lower one for run-off, front over side on vertical seams; the
under panel gets a weld guide line on the PEN layer; alignment marks, labels and fold lines are
pen marks, never cut notches; seams below `min_weld_radius_mm` are flagged.
Alternatives: sewing-style seam allowances on both panels with cut notches (wrong for welding
and a leak risk).
Consequences: export needs a CUT and a PEN layer whose names come from the M0 machine test.

## ADR-012 — Nesting is the machine's job

Context: the cutting machine ships with nesting software; fabric has no direction constraint.
Decision: export all panels of a pattern set on one virtual sheet with spacing; no nesting
inside the tool. Keep the roll-width check in the engine so every panel fits 1480 mm usable
width in some orientation.
Consequences: M8 of the first draft (nesting) removed; revisit only if fabric waste becomes a
problem.

## ADR-013 — Licence policy for an internal tool

Decision: any OSI licence acceptable, including GPL (pymeshlab, parts of CGAL if ever needed),
because the software is used internally and not distributed. docs/LICENSES.md lists every
dependency so a later decision to sell the tool can be evaluated.

## ADR-014 — Tolerance budget

Context: fit tolerance ±5 mm on the assembled cover.
Decision: per-panel dimensional error below 2.5 mm; seam tolerance 1.0 mm; hull grid resolution
5 mm with clearance applied on the continuous SDF so the grid does not eat the budget.
Consequences: golden thresholds in engine/tests; revisit after the M4 and M5 physical gates.

## ADR-015 — One parameter registry, layered overrides, no numbers in code

Context: the first months are a test loop: weld a cover, measure, change a value, re-run. The
owner must be able to change any value without a developer and without touching code.
Decision: every parameter lives in `config/defaults.yaml` with a comment; values layer as
defaults → family preset → model CoverDefinition → one-off trial override. `cover params`
shows the effective value and its source; every PatternSet embeds the full effective set and a
hash; `cover diff` attributes dimension changes to parameter changes. A test fails when engine
code contains a literal that duplicates a registered default. Golden tests pass parameters
explicitly so a change of company defaults cannot break them by accident.
Alternatives: constants in code with a config file for a few chosen values (rejected: every
value not exposed becomes a developer task later).
Consequences: some parameters will exist before anyone needs to change them; that is the
cheaper failure mode.

## ADR-016 — Tooling for the Python engine (M0)

Decision: a uv workspace (root `pyproject.toml`, package in `engine/`, API joins in M6) with
`uv.lock` pinning every version; Python 3.12 is a uv-managed interpreter, so no system package
is needed. CLI on `argparse` (no extra dependency). Parameters read with `ruamel.yaml` in safe
mode (YAML 1.2: `on`/`no` stay strings). Lint `ruff`, types `mypy` in lenient mode, hooks via
`pre-commit` using the project's own locked tools. CI: GitHub Actions running `make test`.
Alternatives: Poetry (slower, no workspace); typer/click (nicer help, one more dependency).
Consequences: `make setup` is one `uv sync`; the same lockfile builds the Docker image in M6.

## ADR-017 — Parameter registry rules (M0)

Decision: every scalar leaf of `config/defaults.yaml` is a parameter addressed by its dotted
path. Overrides (preset, model, trial) may only set existing keys; an unknown key is an error
with a "did you mean" hint, never silently ignored. Types follow the default: booleans stay
booleans, integers on keys ending `_mm`, `_pct` or `_deg` accept decimals (measurements),
other integers (counts, iterations) do not. A comment containing `a | b | c` with the default
among the options makes the key a choice (a dropdown in the web app); a comment containing "to
confirm" or "TODO" marks an assumption, shown as `*` by `cover params`. The parameter hash is
the SHA-256 of the canonical JSON of all effective values.
The no-literals test scans `engine/coverengine` (not `params/` or tests) and exempts 0, 1, 2
and -1, which are indices, halves and pairs far more often than parameters. Anything else that
equals a default must go through the registry or carry `# param-ok: <reason>`. Fixture
geometry (test shapes, test sheets) lives in YAML under `testdata/`, not in code.
Consequences: if the owner changes a default to a value that happens to appear in code, the
test fails and the code is fixed or marked; that is intended.

## ADR-018 — One home for each number: registry versus fabric profile (M0)

Context: `max_allowed_stretch_pct` and the roll width were in both `config/defaults.yaml` and
the fabric profile JSON, and FORMATS.md grouped `min_weld_radius_mm` and `seam_tolerance_mm`
under `welding` while the registry has them under `seams`.
Decision: the fabric profile holds only measured material properties (stretch, weld shrinkage,
thickness). Limits and roll width are parameters and live only in the registry. A
CoverDefinition stores its per-model values as a sparse `parameters` tree using exactly the
registry keys; structural per-model data (masks, seam graph, feature list) sits beside it.
Consequences: one place to change each number; the fabric JSON and FORMATS.md were updated.

## ADR-019 — Test shapes and STL precision (M0)

Context: acceptance asks `cover info` to match analytic dimensions within 1e-6 mm, but STL
stores 32-bit floats (about 3e-5 mm resolution at 500 mm).
Decision: shape dimensions are whole numbers in `testdata/shapes.yaml`, round shapes use
segment counts that are multiples of 4 and exact quarter-turn sines and cosines, so every
extreme vertex is exactly representable. The sidecar lists values `cover info` can measure
exactly (bounding box, radius, height) separately from continuous-surface references (area).
The tilted chair back is the one shape with irrational extremes; it is checked at 1e-4 mm.
Furniture primitives are overlapping, un-merged boxes to behave like CAD triangle soups.

## ADR-020 — Joining method is a per-model choice; double stitching today (M0)

Context: the owner reported during M0 that covers are currently joined by double stitching,
and wants to choose the joining method per model. CLAUDE.md and ADR-011 assumed hot-air welding
only.
Decision: new parameter `construction.method` (`double_stitch` | `welded`, default
`double_stitch`), overridable per model and shown as a dropdown in the web app. Welding keeps its
own block (`welding.*`); stitching gets `stitching.*`, starting with `stitching.allowance_mm`
(15 mm, to confirm). ADR-011's lap side, guide line and pen-mark rules apply to welded seams;
the stitched seam construction (seam type, allowance on one or both panels, whether notches are
acceptable) is to be confirmed with the owner before M5.
Consequences: finishing (M5) implements both allowance rules behind one switch; flattening,
seam matching and the roll-width check are unaffected.

## ADR-021 — Machine test sheets and pen text (M0)

Decision: five test sheet variants generated from `testdata/machine/testsheet.yaml`: named
layers CUT/PEN (A), layers 0/1 (B), text as single-stroke lines (C), colour only on layer 0 (D)
and variant A in DXF R12. Each has a 1000 mm scale strip, a square with 10 mm ticks and a pen
line 20 mm inside (pen-to-knife offset), a rounded rectangle with bulge corners, and one circle
three ways (CIRCLE entity, bulge polyline, 72 segments). Stroked text uses our own
single-stroke font (`export/strokefont.py`): outline fonts drawn with a pen give hollow double
lines. DXF output is byte-deterministic (fixed ezdxf metadata, sorted CLASSES section).

## ADR-022 — Model import (M1)

Decision:
- STEP and IGES are read through OpenCascade's XCAF readers, keeping part names and nested
  assemblies. OpenCascade converts lengths to mm; the declared unit is read from the file and
  recorded. Each distinct part shape is meshed once and every placed copy reuses that mesh. All
  distinct shapes are meshed in one parallel `BRepMesh_IncrementalMesh` run over a compound
  (its parallelism is per face, so shapes one by one leave one-face parts on one core); the
  mesh was identical with 1, 2, 4 and 8 cores. Triangles come back through OpenCascade's binary
  STL writer, which keeps per-triangle work out of Python (1 million triangles: 13 s).
- IGES stores loose faces and no assembly tree, so IGES shapes are sewn
  (`import.sew_tolerance_mm`) before meshing; IGES imports carry no part names.
- Every loaded triangle set is split into edge-connected bodies. This lets a single STL of a
  whole chair, or a CAD compound of screws, be filtered per body. Bodies that only touch at a
  point (a leg under a seat corner) stay separate.
- Filter: a body is dropped when its largest dimension is below `import.min_part_mm`. That uses
  the bounding box, not the volume, because surface-only CAD has no volume. Name exclusions are
  case-insensitive glob patterns matched against the full part path or any segment of it. They
  are stored in `model.json` and reused on the next import into the same model directory.
- Units: STEP, IGES and glTF (metres by definition) declare their unit; STL, OBJ and PLY use
  `--units` or `import.default_units`. A model whose largest dimension is outside
  `import.min_plausible_size_mm` to `import.max_plausible_size_mm` gets a warning naming every
  unit that would fit. The unit is never changed automatically (ADR-007).
- Placement: `import.up_axis` (auto = y for glTF, z otherwise) is rotated to +Z by the smallest
  quarter turn. `import.front` is given once the model stands upright and is turned to −Y. The
  lowest point of the kept parts goes to z = 0, and the bounding box is centred on x = y = 0.
- `model.glb` stores the canonical mm Z-up coordinates as 32-bit floats in its meshes. They
  hang under one root node whose transform converts to glTF's metres and Y up, so any glTF
  viewer shows the model upright at true size while the engine reads exact mm values. One node
  per kept part.
- Test assemblies: a STEP/IGES chair built with OpenCascade (named solids, instanced legs and
  screws), plus a 2,000-part variant for the timing test. Their time stamps, assembly-link ids
  and IGES author are fixed so the files and golden checksums are identical on every machine.
  IGES test files are written without names, because the IGES writer orders name entities
  differently on every run.
Better alternatives, not built yet: skip meshing parts whose B-rep bounding box is already
below `min_part_mm`; faster vertex welding than `np.unique(axis=0)` (most of the remaining time on
very large meshes); a per-model up/front choice saved in `cover.json` once the web app exists.

## ADR-023 — Faceted STEP files and unit definitions (M1, first real model)

Context: the owner's first real file, "Blocchi - 2 seater moon Right.stp" (208 MB, written by
"Spatial InterOp 3D"), is a mesh saved as STEP: 99,098 planar four-sided faces with straight
edges, one product, no curved geometry. OpenCascade needed 155 s and 4.3 GB to read it (122 s
of that converting facets into B-rep faces; disabling colours, layers or shape healing made no
difference). The file also names its length unit "METRE" but defines it as 1 mm, while the
coordinates are in metres (the sofa is 2.36 m wide) and the model is Y-up. The import read it as
a 2 mm sofa and dropped every part, and the unit hint was never shown, because the
all-parts-dropped error came first.
Decision:
- A fast reader (`io/faceted_step.py`) reads faceted STEP files straight from the text: points,
  vertices, edges, loops and planar faces. Each loop is fan-triangulated, reversed once for each
  of the bound and face orientation flags that disagrees with the plane. It only takes files it
  can read exactly: no curved surfaces or curves, no assemblies or transforms, one bound per
  face, one length unit. Anything else goes to OpenCascade. On the real file: 18 s and 1.5 GB.
  A test checks that it matches OpenCascade (bounds and signed volume per part) on a faceted
  chair.
- The STEP length unit comes from its definition in the file (`step_length_unit`), which is
  what OpenCascade converts by. When the name says otherwise, a warning says so. `--units`
  rescales relative to the definition. IGES uses the unit flag of its global section.
- The all-parts-dropped error includes the unit warnings and the size hint.
Consequences: fan triangulation assumes convex facets, which mesh exporters write; a non-convex
facet would be triangulated wrongly (none found so far). Faceted files carry no part names
beyond the product name; parts are the connected bodies (`Root/1` … `Root/10` here).

## ADR-024 — Drape hull from a height map (M2)

Context: PLAN.md M2 describes the drape hull on a 3D occupancy grid built with winding numbers.
With `hull.sweep_down: true` (the default: fabric hangs straight down from the widest point),
the covered solid is exactly the region under the model's height map `H(x, y)`, the highest
point above each spot of the floor.
Decision:
- Sweep, bridging and clearance are computed on that 2D height map. Closing or dilating the
  solid with a ball equals grey-scale closing or dilation of `H` with a hemisphere (umbra
  theorem). Bridging is a closing with radius `bridge_gap_mm / 2`; clearance is a dilation
  with radius `clearance_mm`, which gives rounded top edges of that radius and vertical skirts.
  It needs no inside/outside, so any triangle soup works. It is exact at the grid samples and
  2D, so a 510,000-triangle soup takes 34 s and the Blocchi sofa 44 s.
- The height map samples every triangle exactly at the cell centres. Triangles that cover no
  cell centre (thin or vertical) mark the cells nearest their vertices and edge samples, so
  thin tubes and boards are kept.
- Surface: marching cubes on `min(top - z, wall)`. `wall` is the clearance minus the exact
  floor-plane distance to the model's triangles (point-to-triangle distance with libigl), so
  skirts sit at the clearance to floating point rather than half a cell. Where bridging added
  footprint, the grid distance is used. Exact zeros in the field are nudged, because models in
  whole mm otherwise give zero-area and non-manifold triangles. Then Taubin smoothing, a plane
  cut at `hem_height_mm` (hem vertices snapped to it), and isotropic remeshing (pymeshlab,
  surface deviation at most `hull.remesh_max_deviation_mm`).
- Clearance guarantee: distances from every vertex, face centre and edge midpoint to the model
  triangles are measured exactly. Samples closer than the clearance push their vertices
  straight away from the nearest model point (`hull.clearance_passes` rounds); hem vertices
  stay at hem height. The report states the minimum, and a warning is given if it is below
  the clearance.
- Bridging uses a ball, so a gap narrower than `bridge_gap_mm` still dips slightly:
  R − √(R² − (g/2)²) for a gap g and R = bridge_gap/2 (1.7 mm for a 20 mm gap at 60 mm;
  remeshing flattens it to about 1 mm).
- `hull.sweep_down: false` (fitted shells for cushion-like objects) needs the 3D winding-number
  field and gives a clear "not available yet" error until a model needs it. Hard edges the
  cover must follow move to M3, where seams can hold them. Masks are boxes in `cover.json`
  (`exclude` ignores the furniture inside, `solid` adds the box).
- The grid is made coarser automatically when the 3D field would exceed `hull.max_grid_cells`,
  with a warning.
Consequences: skirts are exact and tops are exact at 5 mm samples; the clearance repair makes
covers at most slightly looser (at the Blocchi: at most a few mm, where the surface bends
around furniture edges). Remeshing is the slowest step (about 70 % of the time).

## ADR-025 — Water must run off: tensioned cover top (owner requirement, 2026-09-30)

Context: the owner supplied the fitting cover of the Blocchi 2-seater as a PDF
(`testdata/models/cover.pdf`, not in git). Its top runs as one straight slope from the front
edge of the base to the top of the back, with a 33 cm band along the back and a vertical skirt
all round. The owner: "we need to avoid places where the water can stay, the water always
needs to can get off; for tables we will use a frame or balloon to create a tent."
Decision: the cover top is a tensioned surface that spans seats and recesses and holds no
water (CLAUDE.md rule 12). This replaces "wider recesses are followed" from ADR-010: the
bridge gap no longer decides whether a recess is followed. Flat tops get a raised support
(frame or balloon) under the cover. The drape hull gets a drainage check (no hollows, no
areas flatter than a minimum slope). Details follow in the revised M2 plan.
Consequences: the M2 acceptance "chair hull follows the seat" is replaced by "spans the seat
and drains". The slatted-table tests change once the tent support exists.

Implementation (M2 revision):
- `hull.top: tensioned` (default): the top is the upper convex envelope of the bridged,
  clearance-dilated height map, clipped to the planform (the Qhull upper hull of the grid
  points, interpolated on its triangles). This is a sheet pulled infinitely tight: straight
  lines between high points, vertical walls up to it, and concave, so it never has a hollow.
  A minimal-surface membrane with the edge held at the furniture was tried first; it sagged
  between the front edge and the back, because it was held at seat height along the sides
  (the owner's side panels rise with the slope).
- Run-off check (`hull/drainage.py`): a priority flood from the planform edge finds hollows
  deeper than 1 mm. The slope map finds flat patches (slope < `hull.min_slope_deg`, 5 to
  confirm) at least `hull.flat_patch_mm` across and not at the edge, so crests and edges do
  not count. The result is in `hull.json` (`drainage`), plus a CLI line and a warning.
- `hull.support: balloon`: a dome of `hull.support_radius_mm` (150, to confirm) under the
  centre of the largest flat patch. Its height is `hull.support_height_mm`, or when that is 0,
  the lowest that sheds water (bisection). The slatted test table needs 69 mm.
- `hull.top: draped` keeps the ADR-024 behaviour (recesses wider than the bridge gap are
  followed), for fitted cases.
- Blocchi against the reference (`testdata/reference/blocchi-2seater-moon-right.json`, seam to
  seam): height 870 vs 880 mm, a flat band on top 262 mm wide (reference band 330 mm), hem
  6.30 vs 6.68 m (first reported as 6.42 m: hairline cracks along the hem were counted twice;
  fixed in M3 by welding the remeshed hull). The flat band between the two back cushions (0.14 m2) is reported as
  holding water; the owner's cover has the same band. Open question to the owner. Skirt
  heights depend on the seam line and are compared in M3.

## ADR-026 — Seams as cuts along scalar fields; automatic seam rules (M3)

Decision:
- A seam is the zero set of a scalar field on the hull (a distance in mm), limited to a set of
  faces: the skirt seam is the inward distance to the outline minus `seams.skirt_seam_inset_mm`,
  a vertical seam is a vertical plane through an outline point normal to the outline, a top
  seam is the signed distance to a floor-plan polyline, and a level seam is `z − z0`. Faces the
  seam crosses are split; each new vertex lies on the seam and is shared by both faces of its
  edge, and neighbouring faces that share a cut edge are split too (no T-junctions). Vertices
  closer than `seams.snap_mm`, measured along the surface, are moved onto the seam along the
  surface, so no slivers form and every other vertex is clearly on one side. A seam's edges are
  recorded when it is cut (both ends on the seam, the faces beside it on opposite sides) and
  updated when a later seam splits them. Judging sides after the fact failed on tight curves and
  near snapped points.
- Panels are the pieces between seam edges; the surface is then "unzipped" along all seams
  (faces on opposite sides of a seam edge stop sharing its vertices), so a skirt ring cut once
  is one disk. Every panel must be a disk (one boundary loop, Euler characteristic 1). Slivers
  below 100 mm² where seams meet are merged into a neighbour.
- Region labels (top or skirt) come from the pieces the skirt seam makes and are inherited
  through later splits. Classifying faces by position near the skirt seam was ambiguous.
- Automatic seams: the skirt seam all round; vertical seams at outline corners (turn above
  `seams.corner_angle_deg` within `seams.corner_window_mm`, notches narrower than half the window
  smoothed out first, the seam at the middle of the bend where half the turn is done) and equal
  splits of stretches longer than `seams.max_skirt_panel_mm`; one seam at the back if there are
  no corners. A top panel wider than `roll.usable_width_mm` when flattened (quick LSCM, scaled
  to the true area, rotating calipers) is split. First a level seam `seams.band_drop_mm` below
  its highest point is tried (the band along a backrest), then one at half its area; level seams
  let the upper panel lap over the lower. If neither leaves only disks, the split is a straight
  seam along the panel's long axis. A seam along where the tensioned top leaves the furniture
  was tried for the band; on the Blocchi that strip is an island and did not give disks.
- Manual seams (`seams.json`): `skirt_seams` (floor-plan points on the outline) and `top_seams`
  (floor-plan polylines). This replaces the geodesic anchors of the original plan: every seam of a
  tensioned cover lies on a graph surface or a vertical wall, so floor-plan coordinates are exact
  and match a plan-view editor (M6). `seams.auto.json` writes the seams used in the same format.
- Lap side: the top over the skirt; the higher panel over the lower on top and level seams; on
  vertical seams the panel facing the front. Tight curves (radius below
  `seams.min_weld_radius_mm`, seam ends excluded) are listed in `panels.json` and warned about
  when `construction.method` is `welded`.
- Symmetric furniture (height map equal to its mirror image within 0.5 mm) gets a mirrored hull
  (the x ≥ 0 half and its mirror image, welded at x = 0, before the clearance repair), so
  mirrored panels are equal (box and chair 0.0 %, table 0.06 %).
- While building M3, the remesher's duplicate points turned out to leave hairline cracks along
  the hem that were counted as hem length. The hull is now welded after remeshing (Blocchi hem
  6.30 m, first reported as 6.42 m).
Better alternatives, not built yet: automatic band seams that follow the owner's Blocchi
layout; a geodesic seam editor on the surface.

## ADR-027 — Flattening, stretch and seam lengths (M4)

Decision:
- Each panel (from `panels.npz`, the unzipped cover written by `cover cut`) is flattened from the
  conformal map (LSCM, scaled to the true area). That map is exact for developable panels, and
  such panels are done with no further iteration. Otherwise the start is refined with SLIM on
  the symmetric Dirichlet energy until it improves by less than `flatten.slim_tolerance`.
  If the LSCM start folds, a Tutte map (boundary on a circle) is used instead. Panels above
  `flatten.max_triangles` are simplified first with their outline kept exactly (a 200k-triangle
  panel: 2.7 s). Up on the furniture points to +Y in the pattern; for a horizontal panel,
  the back does.
- Stretch per triangle comes from the singular values of the 3D-to-2D map. The limit
  (`fabric.max_allowed_stretch_pct`) applies to `flatten.stretch_quantile` (99.5 %) of each
  panel's area. Every tight cover has corner points where three surfaces meet (the back
  corners of a chair top); fabric cannot lie flat there without easing, and a few cm² at such
  points stretch far above the limit. The maximum is still reported.
- Seam lengths: both sides of every seam are compared in 2D; the difference is recorded as
  `ease_mm` and warned about above `seams.seam_tolerance_mm`. Matching marks every
  `pen.tick_spacing_mm` are placed by position along the seam in 3D, so both sides get marks
  at the same places, paired by id.
- Found while measuring seam lengths: the rounded rim that the ball-shaped clearance gives every
  top edge cannot lie flat where two rims meet. Putting the skirt seam 1 mm inside the outline
  (`seams.skirt_seam_inset_mm`, was 5) keeps the rim out of the skirt panels. The seam sides then
  agree within 1.1–1.9 mm on the test chair, box and L-lounge (were up to 6 mm). A sharp-edged
  clearance (`hull.edge: sharp`, a vertical cylinder instead of a ball, with the crease
  re-sharpened after meshing) is better on boxy furniture (box 0.3 mm). But it breaks on rounded
  tops, where there is no crease, such as the Blocchi base, so it is an option and not the
  default.
- Bridging also closes the outline seen from above along straight lines in four directions, so
  slat gaps that reach the edge of a table no longer leave notches in the skirt.
- Fabric compensation (`flatten.fabric_compensation`) stays off until the fabric profile is
  measured (M8).
Consequences and open points: domes (the sphere test shape) and the back of the Blocchi sofa are
curved in two directions; a single panel there stretches far beyond the limit (15 % on the
Blocchi's back half, a 150 mm seam mismatch). They need more seams. The Blocchi needs the owner's
seam layout (the band along the back); an automatic stretch-driven seam proposal is a later
step.

## ADR-028 — Size drawing as a PDF (M4)

Status: accepted, 2026-09-30.

The owner checks a calculated cover against covers that fit by their sizes, from a workshop
drawing (top view, side view, 3D view, dimensions seam to seam, title block). `sizes.pdf` gives
the same for every calculated cover, plus size tables and one page per flat panel, and is the
printable view the dashboard will offer.

- Drawn with matplotlib (already a dependency): vector lines, text and dimensions; the shaded
  surfaces are rasterised inside the PDF (200 dpi) to keep the file small (about 1.2 MB for the
  Blocchi). Hidden seams are left out by face orientation (the cover's faces point outward); a
  full hidden-line pass is not needed for these near-convex shapes.
- Built only from files on disk, so the web app can redraw it without recomputing. No creation
  date in the PDF (deterministic output).
- Sizes are measured by named rules (`measure()` in `export/drawing.py`); a reference cover's
  `compare` map names the rule for each of its sizes, so a new reference needs no code.
- The top view can be turned per model (`drawing.plan_rotation_deg`) to match the owner's drawing.

Found with it: on the Blocchi, the skirt seam is not at a constant height (25–41 cm above the hem
along the front) and zig-zags by 2–4 cm where the rounded top meets the vertical skirt. That
explains most of the seam differences between panels on the skirt seams.

## ADR-029 — Level skirt, wall panels and a zig-zag check (M4)

Status: accepted, 2026-09-30 (owner: "all parts need to be straight", "easy lines so clean
stitching", "for all future covers").

- The skirt seam is a level line at one height all round (`seams.skirt_seam: level`), by
  default just below the lowest point where the top starts to round over (5th percentile of the
  edge height along the outline, so the rounded corners of a box do not set it), 3 mm up the
  rounding (`seams.skirt_below_rim_mm: -3`). The skirt panels are straight strips.
- The top edge height along the outline comes from the vertices where the upright part ends,
  median per 10 mm, a running median (outliers go, kinks stay), a short average, and lowered
  where that would lie above the edge.
- Where the edge stands more than `seams.wall_min_mm` (20) above the level skirt over at least
  `seams.wall_min_length_mm` (300), the upright part between becomes a wall panel. Its seam with
  the top follows the true edge (1 mm into the rounding), with everything more than 5 mm below
  the edge line counted as wall so a slightly leaning wall gives no zig-zag. Past a wall's end the
  seam field rises steeply, so the wall ends in a short upright line. Vertical bands lie flat
  exactly, even round corners, so walls need no corner seams.
- Tried and rejected: a level-only wall seam on the smoothed edge (the top then reaches down onto
  upright parts at steps of the edge; chair top 7.5 % stretch), an upper-envelope seam (breaks on
  narrow ridges), smoothing with a lower envelope over 20 cm (drops the seam at kinks of the
  edge, box-lid corners in the top).
- Every panel edge gets `wiggle_mm` (distance from itself smoothed over 30 mm; clusters of fewer
  than four sharp turns, i.e. corners and steps, left out) and a warning above
  `seams.max_wiggle_mm` (2). Tests require it on the test furniture.
- Fixed on the way: a seam's length counted only its first part when it came in pieces, or when
  two seam lines shared edges (the Blocchi diagonal: 1.9 cm instead of 109 cm); two seams between
  the same panels got the same id; seam ends running past the seam they meet are no longer cut
  open.

Also tried later (same night): a level wall seam on an edge-preserving line (running median of
where the upright part ends, 2 mm above it). Chair top 3.8 %, and on the Blocchi a top panel no
longer in one piece (walls dropped by the fallback). Rejected; the Blocchi's back edge, where the
steep back face meets the skirt at a very shallow angle over 4 cm, stays an open point.

Results: box, chair and slatted table: stretch 0.1–1.5 %, seam sides within 0.9–3.3 mm, no
zig-zag. The Blocchi: skirt pieces 0.3 % and straight; three wall pieces; but its cover surface
has stepped edges on gentle slopes (the 5 mm height grid), which the wall seams follow (the
zig-zag check reports them), and its top pieces still stretch 2.6–7.5 % (the model's rounded
cushion ends). Next: smoother cover surface edges (M2 surface), and extra seams on the top.

## ADR-030 — Finished pieces and the machine export (M5)

Status: accepted, 2026-09-30 (built while the owner was offline; the rules marked "to confirm"
are in docs/QUESTIONS.md).

- Allowances per edge: stitched seams `stitching.allowance_mm` on both panels (or the lap side
  only, `stitching.sides`), welded seams `welding.overlap_mm` on the lap side only with a weld
  guide on the under panel, the hem `hem.allowance_mm` with the fold line on PEN. Each edge is
  grown by a one-sided shapely buffer, run on past its ends by the neighbour's allowance so the
  corners are square, and united with the panel.
- Air vents: count and size from the owner's rule; placed evenly along the hem in the order of
  the skirt panels round the cover, kept 10 cm from vertical seams; the opening on CUT, the
  hood's edge on PEN; hood and membrane as separate rectangular pieces (sizes to confirm). A vent
  that does not fit in its skirt is reported, not moved into the panel above.
- The roll length in the cutting list is a first-fit shelf estimate across the usable width; the
  machine's nesting is expected to do better.
- The M4 files (`pattern.*`, seam to seam) stay; the export adds `cut.*` beside them.

## ADR-031 — The first web app (M6)

Status: accepted, 2026-09-30 (built while the owner was offline; plan in docs/plans/M6.md).

- One process serves the API (FastAPI, `apps/api`, package `coverapi`) and the built pages
  (`apps/web/dist`), on one port. Simpler to run and to put behind a tunnel than separate web
  and API containers.
- The data directory holds `models/<id>/` exactly as the command line writes it; the web app
  reads the same files. No database yet: model state is the folder, jobs are JSON files. SQLite
  comes with users and revisions.
- Jobs run the `cover` steps as subprocesses, one job at a time (memory: a big model needs
  several GB), with per-step status and log. The page polls every 1.5 s; a WebSocket is not
  needed for this.
- Pages: React, TypeScript, Vite, Three.js; hash routes, no router library.
- Settings in the browser use the registry (`GET /api/parameters`): the YAML comments are the
  help texts, `to confirm` is shown, sources are default / model / changed. Trial runs pass
  `--set`; saving writes only values that differ from the default into `cover.json`.
- Access until the Cloudflare account exists: SSH tunnel to 127.0.0.1:8080. The compose file
  publishes only 127.0.0.1:8080; the Cloudflare tunnel is an optional profile.
- Headless browser checks run in the official Playwright Docker image (the server lacks the
  browser's system libraries and we have no root).

## ADR-032 — Families, status, revisions and batch (M7)

Status: accepted, 2026-09-30 (built while the owner was offline).

- A model's family is a field in its `cover.json`; the preset `config/presets/<family>.yaml`
  is parameter layer 2 for every command and the web app (`resolve_model`). An explicit
  `--preset` still wins. Unknown families are an error, not ignored.
- Status, tags and notes live in `cover.json` too: the model folder stays the one place that
  describes a model, for the command line and the web app alike.
- Revisions are copies of the small result files (pattern, finished pieces, DXF, settings,
  seams) per export, not of the meshes: about 100 kB per revision. Comparing two revisions uses
  the same rule as `cover diff` (panels changed by more than 1 mm, settings that differ), now in
  `catalogue.compare`.
- Batch runs are the same steps per model, one after the other (CLI `cover batch`, web: select
  models, "Run these"); the report per model is the comparison with its previous revision.
- The first preset is `table` (balloon under the cover, owner's rule). Other families wait for
  the owner's list (question 16).

## ADR-033 — Fabric compensation (M8, prepared)

Status: accepted, 2026-09-30; off until the fabric is measured.

- With `flatten.fabric_compensation`, every flat piece is scaled by 1 / (1 + the mean of the
  warp and weft stretch in a fitted cover), from the fabric profile. The mean, not per
  direction, because the pieces may be turned any way on the roll (CLAUDE.md) and the machine's
  nesting decides. If the owner later fixes the grain direction per piece, the scale can become
  per direction.
- The reported stretch stays that of the shape (without the compensation); `compensation_scale`
  is recorded in the PatternSet. A warning says so when the profile is still a placeholder.
- Weld shrinkage is measured and stored but not yet applied: it only matters for welded covers,
  and how it adds up along a seam needs the first welded sample.
- `scripts/fabric_profile.py` turns the swatch sheet (`testdata/fabrics/measurements.template.json`)
  into the profile.

## ADR-034 — Seam proposals, and seam ends inside a panel (M9)

Status: accepted, 2026-09-30.

- A top piece above the stretch limit gets a proposed seam in `pattern.json` (`proposals`): a
  straight plan line through the area-weighted centre of its worst faces, across its longer
  plan extent, clipped to the piece's boundary seen from above. It is shown in the seam editor
  and applied only when the owner takes it (owner: clean, deliberate seams). Not yet
  automatic: the owner decides where seams go on production covers.
- A top, wall or roll seam that lies inside one panel (both sides the same panel) is a leftover
  of a line that ran on past the seam it meets; it is no longer cut open. Only a vertical skirt
  seam may close a panel onto itself (a round skirt cut once).

## ADR-035 — Lessons from real models (FreeCAD library, SUNS catalogue)

Status: accepted, 2026-09-30/10-01 (night run, owner offline).

- Splayed legs put the lowest top edge at the floor: the automatic skirt is at least
  `seams.min_skirt_height_mm` (150, to confirm) high.
- A frame that encloses an empty area seen from above (a folding chair) left a tube in the
  cover: holes in the footprint are filled, the top spans them.
- Corners closer together than `seams.min_skirt_panel_mm` (300, to confirm) get one seam half
  way between them (no strips of a few cm).
- A wall a millimetre out of plumb, or a faceted model, makes the true-edge wall seam jitter
  (4–7 mm): when it zig-zags more than `seams.max_wiggle_mm`, its points are smoothed in place
  along the seam and put back on the surface (faces may turn by at most acos 0.8); a clean seam
  keeps its real corners.
- Meshing small gaps could leave loose fragments of a few mm2 in the cover surface; they
  became "panels" that could not be flattened. The cover surface is now its largest connected
  part.
- A vertical corner seam took its direction from the outline just after its point; at a sharp
  corner (a square table) its plane then ran along the side instead of across the corner, and
  the skirt stayed a closed ring. The direction now comes from before to after the corner, and
  the seam reaches the skirt faces on its plane up to three corner windows away (a skirt that
  climbs over a low, rounded corner).
- `hull.support: frame` (a ridge beam along the long axis, gable-roof top) is available; on the
  test tables it did not beat the balloon (3.2–3.4 % against 0.3–4.2 %), because the ridge ends
  meet the rounded table edges. Tables keep the balloon; the frame may need a seam along the
  ridge (question for the owner).

## ADR-036 — AI advice on cover layouts (DeepSeek)

Status: accepted, 1 Oct 2026 (owner: "first the AI integration, then the upload field").

- The program describes a calculated cover as JSON text (product, size, every piece with flat
  size, area and stretch, the seams between pieces, why it needs checking) and asks a language
  model (`ai.provider: deepseek`, `ai.model: deepseek-flash`, the owner's choice) how to make it
  simpler. The model may only choose actions from a fixed list the program can carry out
  (`coverengine/ai.py` ACTIONS); unknown actions are dropped. It changes nothing itself: the owner
  applies a suggestion (web app: AI advice tab; CLI `cover ai --apply`), which writes settings to
  the model's cover.json or removes the program's added seams, and the cover is calculated again.
- The key lives only in `deploy/.env` (git-ignored, mode 600) or the environment. The AI test
  calls DeepSeek for real when the key is there and is skipped where it is not (GitHub).
- DeepSeek takes text only, no images: drawings are read by the program itself (vector PDFs).
- First result, SUNS Kota 2-seater: the AI named the owner's own complaints (30 pieces, scraps,
  skirt in four, wall pieces) and proposed target 6. Its first three actions brought the cover
  from 30 to 4 pieces; the top in one piece then stretches 43 %, so the extra seams must come from
  the owner's drawings (the upload of drawing + model pairs, next).

## ADR-037 — Learning from the owner's covers: drawing + model pairs

Status: accepted, 1 Oct 2026 (owner: "an upload field so I can upload 1 zip, numbered like
1.step 1.pdf").

- One zip, pairs by name (`1.step` + `1.pdf`; any 3D format the import reads), folders ignored,
  files without a partner listed. Each pair becomes `models/ref-<batch>-<name>/` (tags
  `reference`, `batch-<id>`), calculated like any model, with `reference.pdf`, a picture of its
  first page (`reference.png`) and what was read from it (`reference.json`: every word with its
  place on the page, every size with its unit converted to mm, and the number of vector paths;
  0 means a scan, which only an image-reading AI could interpret).
- PDFs are read with PyMuPDF (AGPL; fine for this internal tool, listed in LICENSES.md).
- Read correctly from the owner's Blocchi drawing: all eight sizes in cm.
- Next: read the seam lines from the vector drawings, compare piece counts and sizes with the
  calculation, and derive a seam layout per family from several pairs, with the AI comparing.

## ADR-038 — Box covers: the tightest box with N flat faces, N chosen by the AI

Status: accepted, 1 Oct 2026 (owner: "the box needs to be more boxy, so we don't make so many
strange panels"; "we need AI input to have not so many panels").

- `hull.top: box`: the cover surface is the tightest convex box with flat faces round the
  furniture down to the hem, `hull.clearance_mm` clear. It starts as the smallest rectangle seen
  from above with a top, and gains one face at a time: each time the cut that removes the most
  empty volume. Every face is one panel (exactly flat: 0 % stretch, matching seams) and every
  seam a straight box edge.
- How many faces: `hull.box_pieces`, or (0) the AI chooses from the options (pieces, typical
  room, room within which 95 % of the cover lies, extra volume), or without AI the fewest pieces
  within `hull.box_volume_slack_pct` of the tightest box. Kota 2-seater: 6 pieces 41 mm typical
  room / 10 % extra volume, 7 pieces 24 mm / 7 %; more barely helps; the AI chose 7.
- Water: a face flatter than `hull.min_slope_deg` is tilted outward; a flat face over the middle
  (a table top) becomes a low gable of two faces.
- Vents go on the skirt pieces tall enough for them; their number still follows the whole hem.
- A box spans bays seen from above (an L sofa, the Blocchi's curve): a warning says so; those
  keep the tensioned cover.


## ADR-039 — Uploads: the complete product or only the cover surface, confirmed by the owner

Status: accepted, 1 Oct 2026 (owner: for some products there is only a drawing of the cover
surface; "show after the upload what you think it is, complete product or cover surface only, so
we can give the final confirmation").

- One upload field. After the import the program guesses what the file is (`coverengine/io/
  kind.py`, `kind.json`) from three measures: closed sides (horizontal lines of sight low down
  all hit it), no floor (no flat area at the bottom), one skin (area about that of its envelope).
  All three: a cover surface; otherwise the furniture. On 25 SUNS products and their 25 cover
  surfaces: 50 of 50 right.
- The web app shows the guess with its reasons and waits: the owner confirms or corrects it, and
  only then does the rest run. Through the API, `kind` on the upload skips the question.
- A cover surface is used as the cover (`hull.top: given`): cleaned, faced outward, split into
  small triangles; seams, flattening, allowances and export as usual.
- Not yet: 2D contour drawings (DXF or PDF with the flat pieces). They need no flattening, only
  allowances and marks, and which edges join must be known. Built when the owner's samples show
  their form. Seam lines drawn in a cover surface (separate faces per piece) are not used yet.

## ADR-040 — Balloons under table covers

Status: accepted, 1 Oct 2026 (owner: balloons under every table cover so the fabric slopes; one
balloon size, the uploaded model `table-baloon`, 52 × 51 × 20.6 cm; a 340 cm table gets 3 to 4;
between balloons the fabric runs straight and the slope is all round them; every table gets at
least one).

- `hull.support: balloons` puts the balloon model on the table top in the evenest grid for 1, 2,
  ... balloons (`hull.balloon_max`), never overlapping. How many: `hull.balloon_count`, or (0)
  the AI chooses with the owner's practice in its instructions, or without AI about one per
  `hull.balloon_spacing_mm` of table length, at least one.
- With the tensioned cover the program measures each option (flat spots, hollows); the balloon's
  flat top counts as pressed round by the fabric. With a box cover (`hull.top: box`) the box is
  made round table and balloons: upright sides and a roof of flat faces, every piece exactly
  flat. Told that it is a balloon table, the AI chooses the fewest roof pieces.
- Tried: SUNS tables 60 × 60 (1 balloon, 6 pieces), 210 × 90 (2, 7), 340 × 100 (4, 6): 0 %
  stretch, seams equal. The tensioned tent over the same balloons follows the slopes down to the
  table edge, but gives 8 to 11 pieces with 2 to 5 % stretch and seams up to 10 cm apart.

## ADR-041 — Learning from rejected covers; symmetric furniture gets a symmetric cover

Status: accepted, 1 Oct 2026 (owner, on the Vento daybed: "one side slopes down neatly, the
other stays straight; analyse it with the DeepSeek API, we must learn from our mistakes").

- `cover ai <model> --learn "<complaint>"` sends the complaint and the cover's facts (each flat
  face with its direction, area and centre) to the AI, which states the cause, a general rule
  and a check. The lesson is kept in `config/ai_lessons.json` (in the repository) and its rule
  goes into every later AI question (layout review, box pieces, balloons).
- The first lesson (Vento daybed): the box grew one face at a time, so with 8 pieces one front
  corner was sloped and the other not. Rule: a left-right symmetric product gets a symmetric
  cover. Now the box checks whether the furniture's outside is mirror-symmetric (in 2000
  directions it reaches as far as mirrored, within 25 mm; loose cushions do not count) and adds
  faces in mirror pairs; a face almost square to the mirror plane is made exactly square.
  Vento daybed: 9 pieces, every slope with its mirror image. Kota 2-seater: unchanged, 7.
- Box faces are now flat regions (neighbours turning less than 1°, slivers merged), not equal
  rounded normals: 11 of 15 SUNS products that stopped at the cut now pass.

## ADR-042 — The audit: fixed checks on every cover, and the AI's second opinion with pictures

Status: accepted, 1 Oct 2026 (owner, on the Basta 340: "the table legs come outside the cover,
and I miss the balloons; check all models, cover surface and panels, with a double check by
DeepSeek").

- Cause of the Basta: its legs are long single triangles from the floor up; the box cover took
  only the corner points above the hem, so the slanting legs between 5 and 60 cm were not seen
  and the cover was 4 cm short at each end. The furniture is now cut at hem height first. The
  balloons were missing because the table had not been recalculated yet.
- `cover audit [--ai]` measures each model: steps complete and newer than the cover surface;
  furniture above the hem inside the cover (20 000 points, 3 mm); a table has balloons; a
  symmetric piece of furniture has a symmetric cover; water runs off; the grade and no scrap
  pieces. `audit.json` per model, `audit.csv` for all.
- With `--ai` DeepSeek V4.1 Flash (it reads pictures) gets three straight views (furniture grey,
  cover see-through blue, furniture outside the cover red), the product photo and the measured
  checks, and gives its verdict (good / doubt / wrong) and where it disagrees with the program.
  The oblique cover.png misled it (it called the symmetric daybed asymmetric), hence the
  straight views. On the old Basta both found the legs; on the fixed daybed both said good.

## ADR-043 — The owner's drawings as the reference for cover shapes

Status: accepted, 1 Oct 2026. 115 drawings of earlier covers, read by `scripts/drawings.py`
(texts by the program, pictures by the AI; `out/drawings/covers-and-all/`). They confirm the box
cover for sloped and plain boxes, and show two shapes the program lacks: L shapes (39 of 115, a
sloped box along each arm with a 45° seam at the corner) and round tables (a disc and a band).
Both are the next engine work. Report: `docs/reports/DRAWINGS-2026-10-01.md`.

## ADR-044 — Table covers include the chairs; lower air vents on low sides

Status: accepted, 1 Oct 2026 (owner).

- Chairs: every cover for a dining table, low dining table or low bar table also covers the
  chairs pushed in along the two long sides (not the short ends): `hull.chair_room_mm` 330 beyond
  the table top on each side (a 100 cm table: 166 cm). Height fixed per kind: dining tables (74
  to 77 cm) 87 cm as the owner's cover T1; low dining tables the same (owner: the same cover);
  low bar tables 123 cm (owner: as the round covers R5, R6, R10). Round tables have chairs
  all round, the same 33 cm beyond the edge (owner; R1 is 240 cm for a 170 cm table). Bar tables, lounge and side tables, fire pits, picnic tables: none.
  `hull.chairs: auto` decides by the name and the height. The box cover is made round table,
  chair space and balloons; the 3D view shows the chair space (`chairs.glb`), the audit checks
  the width. Palermo 240 (114 cm wide): cover 182 cm wide, 3 balloons, 5 + 1 pieces.
- Air vents (question 29): one per metre of hem, at least one on each side. A side too low for
  the full opening gets a lower one, same 25 cm width, whole cm, at least 10 cm
  (`features.vent_min_height_mm`), measured where the vent goes and lowered a cm at a time on
  curved or sloping pieces; the plastic insert, hood and membrane stay the same size. A
  side lower than 16.5 cm gets none, with a warning. Kota front (22.4 cm): 25 × 15 cm. A short
  side still gets one (owner): centred, closer to the seams than 10 cm, at least the seam
  allowance away; a side under 28 cm of hem has no room (warning).

## ADR-045 — A cover drawing translated to production: the owner's C6

Status: accepted, 1 Oct 2026 (owner: "make a model based on the cover of C6, to see if you can
translate this correctly to a production ready model").

- `scripts/c6_surface.py` builds the cover surface from the drawing's sizes (L shape 290 × 380
  cm, arms 110 cm, back 85 cm, front 37 cm, a flat strip 30 cm along the back measured on the
  top view, 45° seams at the corner); it runs through `hull.top: given` as model `drawing-c6`.
- Three program changes came out of it, for every uploaded cover surface: the upload guess
  looks along whole lines (an L has its middle in the open corner); a flat piece that turns a
  corner is split from its inside corner along the line halving it (the 45° seam); the water
  check is real (the top faces flatter than the minimum slope), no longer assumed.
- Result: 10 pieces as drawn (2 strips, 2 slopes, 2 back walls, 2 inside walls, 2 ends), 0 %
  stretch, seams equal, every piece within the roll; 13 air vents by the owner's rule against 7
  air pockets in the drawing; the flat strip holds water (1.92 m²). DeepSeek, given the drawing
  and the result, found the vent difference; its other four remarks were misreadings (slope
  length taken as width, allowance corners taken as size), checked one by one.
- Owner, 1 Oct 2026: the strip is 30 cm; a cover from the owner's drawing is replicated
  exactly, flat strip included (the audit notes a flat top on a `given` cover, it does not fail
  it). Air vents: one per full metre of each side separately, at least one per side (2.10 m:
  2, 2.90 m: 2, 3.10 m: 3, 1.40 m: 1); C6: 10 vents.

## ADR-047 — Users, rights and the approval of the definitive drawing

Status: accepted, 1 Oct 2026 (owner: reachable from the internet, a well secured user
structure, approval of the definitive drawing only by chosen users; users Rick and Wout first,
both admin).

- Users in `<data>/app.db` (SQLite, mode 600): role admin / editor / viewer, and per user
  `can_approve`. Passwords as scrypt hashes; at least 12 characters, not the user name. One-time
  links (3 days) for the first password and resets, by mail or copied by an admin.
- Sessions: a random token in an HttpOnly, SameSite=Strict cookie, Secure over https, 14 days;
  kept as a hash. Five wrong passwords lock the user for 15 minutes; ten from one address lock
  the address. The same work is done for unknown users (no timing hint).
- Every /api request needs a login (except health, login and the one-time links); a change
  needs editor, the admin API admin, approving `can_approve`; changes must come from the app's
  own pages (Origin = Host). Security headers (CSP, no framing, nosniff, HSTS over https). The
  API's own documentation pages are off. Every change goes to the audit log.
- Approval: of one revision, with a sha256 fingerprint of the production files; stamped copies
  of the size drawing and the cutting list; status production only with a valid approval; any
  change to the files makes it "changed after approval". Editors can ask the approvers by mail.
- Admin page: users, rights, links, the SMTP server (password never shown again), the public
  address, who is logged in, the audit log, system state. `cover-users` for the first admin.

## ADR-048 — The server: https on covers.suns.nu, the app as a service, hardening

Status: accepted, 1 Oct 2026.

- Caddy (deploy/Caddyfile) serves covers.suns.nu with an automatic Let's Encrypt certificate and
  passes everything to the app on 127.0.0.1:8080; the firewall (ufw) allows SSH, 80 and 443
  only. Opened only after the logins were in place and tested.
- The app runs as the systemd service cover-web (deploy/cover-web.service): restarts by
  itself, starts at boot, no extra privileges, the system read only.
- Updates: unattended security upgrades on; installed by hand on 1 Oct. A reboot is waiting
  (new kernel and libc), to be done when it suits the owner.
- SSH: everyone still logs in with a password (also root), so passwords stay on until keys are
  set; meanwhile fail2ban bans after 4 wrong tries (an hour, growing to a week for repeat
  offenders), 4 tries per connection, no X11 or agent forwarding.
- Backups: every night at 02:30 a tar of the data folder (models, users, settings) in
  ~/backups on the same disk; an off-site copy is still to be chosen (question).

## ADR-049 — Rain on the cover: computed physics, the AI's verdict

Status: accepted, 2 Oct 2026 (owner: an AI-driven rain simulation in the 3D view, as real as
possible). Research and plan: docs/plans/rain-simulation.md.

- `cover rain` (and the Rain buttons in the 3D view): the cover surface on a 15 mm grid seen
  from above; hollows by priority flood (ponds deeper than 2.5 mm, with area, depth, volume);
  flat parts from the faces' true slope (under the minimum slope less half a degree; a grid
  reads a 5° face as 4 to 5°); streams by flow accumulation; 240 drops traced down the steepest
  way for the animation, counted where they leave the cover; seams between top pieces that
  water runs along for more than 25 cm.
- Sag: a pond weighs on the fabric; between supports (where the cover rests on the furniture or
  a balloon) it sags by water load × span² / (8 × tension), iterated: a pond whose volume grows
  by more than half keeps growing (ponding). The tension (`rain.fabric_tension_n_per_m`, 800
  N/m) is a placeholder until the swatch tests.
- The AI (DeepSeek) gets the numbers and a top view with streams and ponds and gives the
  verdict (dry / risk / wet), the risks and what would help; it computes nothing itself.
- Not done (on purpose): water moving in time (shallow-water equations) and fabric finite
  elements; the static answer is what matters for a cover, and the fabric is not measured yet.
- First results: Kota 2-seater and Palermo 240 dry; C6 1.75 m² flat (its drawn strip); T1 5.8
  m² flat (its flat top); the reference Blocchi 0.17 m² flat.
