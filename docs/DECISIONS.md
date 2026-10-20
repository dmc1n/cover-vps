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

## ADR-050 — Categories with the SUNS names

Status: accepted, 2 Oct 2026 (owner: categorise all models automatically, with the names on
hello-suns.com).

- The site's categories: Dining (Tafels, Stoelen, Low dining tafels, Low dining stoelen,
  Barsets), Lounge (Sofasets, Loungestoelen), Relax (Ligbedden, Daybeds), Styling
  (Bijzettafels, Poefs). Lounge tables, hockers and fire pits have no category of their own on
  the site: Lounge › Loungetafels, Lounge › Hockers, Overig › Vuurtafels, marked "not on the
  SUNS site"; Barsets is split into Bartafels and Barstoelen.
- `cover categorise [--ai]`: rules on the model's name (a table lower than 55 cm is a lounge
  table); the owner's drawings by the furniture type read from them; the AI (name and photo,
  only from the list) for the rest. The category is kept in cover.json; tables without a family
  join the table family. Editable per model; filters in the model list and the catalogue.
- 1 October data: 410 models, 407 by the rules, 3 by the AI (the D8 cover as a hocker is
  doubtful).

## ADR-052 — The curved Blocchi (S44 / Cover 110) from its vector drawing

Status: accepted, 2 Oct 2026 (owner, on blocchi-2seater-moon-right: "this one is still not
good").

- The owner's Blocchi cover drawing (testdata/models/cover.pdf) is drawing S44 of the 115. It
  is a vector drawing: the outline (pink) and the seams (black) are read as they are, scaled by
  the drawn 197.0 cm (`scripts/s44_cover.py`). Every piece is made of flat triangles between
  its drawn edges, with the heights from the drawing (back and strip 88.0 cm, front and the
  bottom of the nose 40.6 cm, the diagonal seams running down between); piecewise flat pieces
  lie flat exactly. Result `drawing-s44`: 4 top pieces (strip, slope, nose, tip) and 6 walls,
  0.00 % stretch, every seam equal on both sides, 197.0 × 192.4 × 88.0 cm as drawn.
- Tried first and dropped: a curved cover from the SUNS 3D model's outline (height by
  distance: 11 % stretch; ruled: 0.08 %, but the SUNS sofa's straight end is 89 cm where the
  drawing has 141 cm, so it did not match the owner's cover).
- Open: the drawn outline measures 642 cm, the drawing states a bottom circumference of 668 cm
  (the walls are upright here; the drawing's side view shows the back leaning). Reading vector
  drawings is the way for the other curved drawings too (S43, S46, C26, ...).

## ADR-053 — Releases with version numbers, and going back in seconds

The owner, 2 October 2026: "we must be able to go back to an earlier version if we make a
mistake"; "start with version numbers in git so that we can go back".

- A release is a tag `vMAJOR.MINOR.PATCH` on a tested `main` (`scripts/release.sh v1.0.0
  "what is new"`: `make test`, tag, push, then the release is built in its own folder
  `~/releases/v1.0.0`: a git worktree of the tag with its own Python environment and web pages).
- The app runs from `~/releases/current`, a link to the live release (`deploy/cover-web.service`).
  Switching is changing the link and restarting the app; if the app does not answer within
  60 s the switch is undone at once. `~/releases/history.log` records every switch, the admin
  page shows the live release and the last switches.
- Back: `scripts/rollback.sh` (the release before), `scripts/rollback.sh v1.0.0` (a chosen
  one), `scripts/rollback.sh --list`. The data (models, users, uploads, the drawings' results)
  is outside the releases (`models`, `out` and `deploy/.env` are links into the working copy
  and `~/cover-data`), so going back changes the program, never the data. Going back past a
  change of the data's format is not supported; such a change gets a new MAJOR number.
- Numbers: MAJOR for a change that existing models or files do not survive, MINOR for new
  features, PATCH for fixes. Development goes on in `~/cover-pattern-engine` (main); the
  nightly scripts and `cover` on the command line use that working copy.
- Why not `git checkout <tag>` in the working copy: that stops development while the old
  version runs, and a half-finished change would go live with any restart.

## ADR-054 — Invitations in English, and the guide

The owner, 2 October 2026: "a kickoff on Monday: invite all users, in English; a button with
an invitation mail"; "a short write-up in English of how the system works".

- The invitation mail (`coverapi/invitation.py`) is plain text plus the same in a simple layout
  in the house colours: what Cover Studio is, the three steps to get in (choose a password,
  log in, the code by mail with "remember this device"), the user name and a button with the
  personal link. An admin can put a line of their own at the top (the kickoff's date).
- Links are valid for 7 days instead of 3: invitations sent on a Friday must still work after
  the weekend. Once only, as before.
- Admin → Users: **Invite everyone not yet in** (active users with an address and no password),
  **Send invitation** / **Send again** per person, **Reset password** only after a second
  click (it stops the old password), and "send the invitation now" on adding a user, so people
  can be added first and invited together. The list shows who is invited and until when.
- The guide **How Cover Studio works** is `docs/handbook/how-it-works.md`, shown in the app at
  `#/guide`, also without logging in. The invitation links to it. There is one source, so the
  handbook and the app cannot drift apart.

## ADR-055 — No slivers; a fold instead of a seam on request; learning from every remark

The owner, 2 October 2026, on the Lucia 2-seater right: "the top can be cut in one piece"; "we
must learn from these mistakes and make sure this does not happen again" (plan:
docs/plans/fewer-top-pieces.md). Questions 47 and 48 are answered: the fold only on request; the
minimum width is to be learned (10 cm for now).

- `seams/facets.py`:
  - Two flat faces that share an edge unfold exactly into one flat piece. A group of faces is
    laid flat face by face, each turned about its shared edge, which gives its size on the roll.
  - A face narrower than `seams.min_piece_width_mm` (100, to confirm) always goes into its
    neighbour on the same side, if the two fit the roll and the longest piece.
  - With `seams.fold_merge` (off; on per model on request) the top faces are joined while they
    fit.
  - The joined edges are folds: a pen line `FOLD` in the pattern, the cut file and the size
    drawing.
- The box's choice of pieces sees, per option, the number of top pieces and the narrowest face.
  The AI is told to prefer the fewest top pieces and never a sliver; the rule without AI skips
  options with a sliver. The lesson is stored in `config/ai_lessons.json`.
- The audit gets a check, *slivers*, and a note, *top pieces*: a top that would fit the roll in
  one piece.
- The owner's drawings keep their pieces as drawn.
- **Working rule from now on.** An owner's remark on one model becomes four things in the same
  commit:
  - a stored lesson;
  - a check in the audit;
  - a test;
  - a line here.

  Then it is swept over all models (the scan of 2 October: 21 SUNS models with a piece under
  8 cm, 168 with a top that would fit the roll in one piece).

## ADR-056 — The drape simulation

The owner, 2 October 2026: "a simulation button where the cover really falls over the product
... lifelike, where you also see folds where there is too much fabric" (plan:
docs/plans/drape-simulation.md).

- **The cloth:**
  - The pieces of `panels.npz` (the cut), each with its flat shape from the flattening as rest
    shape, sewn over their seams (the two sides of a seam are one point).
  - It starts where it lies in the designed cover, a fabric's thickness outward. The support is
    then gone.
- **The solver:** projective dynamics (Bouaziz et al. 2014), in numpy and scipy, deterministic,
  no new dependency.
  - Each step is `drape.iterations` rounds.
  - Local step: every triangle's stretch projected into `1 ± drape.max_stretch_pct`.
  - Global step: one sparse solve, factorised again only when contacts change.
  - Bending: the quadratic energy of the flat rest shape (cotangent Laplacian), within each
    piece. A seam is a free hinge.
- **Contact:**
  - A point that would go through the furniture or the balloons, or come closer than the
    fabric's thickness, is held on the surface, on the side it came from. That is a constraint
    in the global solve (`drape.contact_stiffness`), not a push afterwards.
  - The closest points are exact (libigl), not from a grid. Pushing afterwards, and a 12 mm
    grid, both tore the cloth at thin parts.
- **Tuning on a tablecloth over a box** (the standard cloth test, `engine/tests/test_drape.py`):
  - With a high stretch weight the solver itself damps the fall: the cloth hung like cardboard.
  - At `drape.stretch_stiffness` 3000 with 20 rounds, the sides hang straight down the box
    (30 cm overhang, 50 cm box), the corners fold, and the stretch stays under 3 %.
  - The fabric values (weight, stretch, bending) are placeholders until the fabric is
    measured. The places of the folds are geometry; their size is an estimate.
- **Outputs:**
  - `drape.glb`: the cover as it lies, the folds in the house red;
  - `drape.bin`: the fall in 16-bit frames;
  - `drape.json`: the folds, tension, sag and contact.
- **Interface:** the command `cover drape`, and the 3D view's **Drape simulation** / **Drape**
  buttons, which play the fall and then show the cover as it lies, with the report.
- **Run time** without a graphics card: minutes for a sofa (the Kota: 13,500 points). It runs as
  a background job and the result is kept.
- **Next:** self-contact; the hem cord's pull; the AI's verdict; the audit check; the night run
  over the catalogue; fitting the fabric values to photos of the first sewn cover.

### ADR-056, addendum (2 October 2026, evening)

- **The fabric.** It is **Sunbrella Coverlast** (the owner):
  - 100 % polyester with an acrylic coating on the top side;
  - 250 g/m² ±5 %, roll 152 cm (Dickson);
  - tensile 195/104 daN per 5 cm (MBS Fabrics).

  It is `testdata/fabrics/coverlast.json`, and `fabric.profile` now points to it. The drape
  uses its weight and a lower bending stiffness (it folds easily). Its stretch is still a
  placeholder; no elongation is published (QUESTIONS 51).
- **DeepSeek's verdict.** Every drape writes `drape.png` (the cover as it lies, from the front
  and the back, next to the design) and asks DeepSeek for a verdict (good / doubt / wrong, the
  problems, advice). It is shown in the 3D view's drape card.
- **The audit check *drape*.** It fails above `drape.max_fold_share_pct` (35 %, to confirm) in
  folds, or where the top sags deeper than `drape.max_sag_cm` (24, to confirm).
- **The first results.**
  - The Kota: 26 % folds, 18 cm sag.
  - The Basta 340, with its balloons and the chair space under the cover: 19 %, 18 cm.
  - The Lucia 2-seater right: 35 %, 42 cm. The design spans the seat, but the real fabric sinks
    into it and water would stand there. DeepSeek: "wrong".
  - That is the use of the simulation: the designed surface promised run-off that the sewn
    pieces do not give. The remedy is a question of design: something under the cover on the
    seat, or a tighter cut.


## ADR-057 — Rain on the cover as it lies, with a water heatmap

The owner, 3 October 2026: "after the fit is known we must do the rain simulation, and with a
heatmap find where water would collect".

- **The rain runs on the draped cover.** `cover rain --on drape` (and every `cover drape`,
  right after the fall) runs the rain simulation on `drape.glb`, the sewn cover as it lies,
  instead of on the designed surface. The method is the same:
  - a top-view grid;
  - priority flood for ponds;
  - flat parts;
  - flow;
  - the sag of a pond under its weight.

  The seams' places are left out on the draped cover, because they have moved.
- **The files:**
  - `drape_rain.json`: ponds, litres, depth, flat area, growing ponds;
  - `drape_rain.png`: the top view;
  - `drape_rain.glb`: the heatmap;
  - `drape.json` gets a short `wet` summary.

  The rain on the design (`rain.*`) stays, to compare.
- **The heatmap.** Every point of the draped cover seen from above gets the state of its grid
  cell:
  - pond: red, darker with depth;
  - flat, water stands: orange;
  - water streams past: amber, by the share of the cover draining through it;
  - runs off: sage.

  Points under the top (the sides) are dry. The 3D view's drape mode shows it with the
  **Water** switch and a legend; the drape card gives the rain numbers.
- **The audit check *drape*** also fails when more than `drape.max_pond_l` (0.33 l, to confirm)
  stays on the cover as it lies.
- **The first case.** The Lucia 2-seater right: the design is dry; as it lies, 23 ponds
  (0.5 l, up to 1.5 cm deep) and 0.31 m² flat, in the hollow over the seat and along the back.
  DeepSeek: "risk".
- **Limits:**
  - The smallest ponds depend on the drape's resolution (about 2 cm) and the 20 mm rain grid.
    Large ponds are sure; the smallest are an indication.
  - The water's weight is not fed back into the drape yet (a pond deepening the hollow it
    lies in, then a new fall). The analytic sag estimate stands in for it.

## ADR-058 — Newton's Style3D as a second drape engine

The owner, 3 October 2026: "first try option 1" (docs/plans/realistic-drape-engine.md):
Newton's Style3D solver on this server's CPU, before a GPU is considered.

- `drape.engine: own | style3d`, with `own` the default.
- `coverengine/drape_style3d.py` gives Style3D the sewn cover in 3D, with every triangle's flat
  shape (`panel_verts`), and the colliders: furniture, balloons, chair space and the ground.
  Everything after the fall stays the same: playback, rain, heatmap and audit.
- **The grain.** It is not known before nesting. The long side of every piece is taken along
  the warp.
- **The fabric**, all to confirm:
  - stretch: warp 10,000 and weft 5,000 N/m (Coverlast's weft is about half as strong), shear
    800;
  - bending per direction.
- **The tablecloth test:** on the box, the sides down, under 1 % stretch (own solver: 2.6 %).
- **Kota 2-seater, Style3D against own:**
  - folds 1 % against 26 %;
  - stretch 0.7 % against 31 % (single triangles);
  - sag 6.6 cm against 18;
  - no ponds;
  - 42 minutes against 5.

  The cover lies smooth and taut with rounded edges, like a tensioned canvas.
- **Lucia 2-seater right:** folds 12 %, stretch 0.6 %.
- **The cost.** Warp runs its kernels on one CPU core, about 9 s per frame for a sofa (13,500
  points). A night run over the catalogue would take days here. On a GPU it is many times
  faster, with self-contact (VBD) as well: option 3 of the plan.

## ADR-059 — Style3D as the standard drape, made once per model and kept

The owner, 4 October 2026: "40 minutes is no problem for us, as long as it is saved; if we
add new models, it takes 40 minutes and then they are kept, that is fine".

- `drape.engine` is now `style3d` by default. The 3D view has one **Drape simulation** button
  (Style3D). The own solver stays for tests and quick batch checks (`--set drape.engine=own`).
- **A queue of its own.** A drape-only job runs in a second queue. A 40-minute drape never holds
  up uploads or other calculations.
- **After a full calculation.** A job that ends with `export` (a new model, or "Run again") is
  followed by a drape job on its own. The drape, the rain on it and the heatmap are stored with
  the model (`drape.*`, `drape_rain.*`) and go into the nightly backup. Not after a trial run,
  which is not saved. `COVER_AUTO_DRAPE=off` switches this off (the API tests do).
- **Four drapes side by side** (`COVER_DRAPE_WORKERS`, 4). Style3D works on one CPU core, so
  20 new models take about 3.5 hours instead of 13 (the owner, 4 October 2026: "upload
  everything").


## ADR-061 — The webshop: a configurator and a public API

The owner, 4 October 2026: "customers make their own cover through a webshop, by an API or a
3D interface in an iframe; from rough sizes a proposal with all options, the volumes and the
cost price" (plan: docs/plans/webshop-configurator.md; handbook: docs/handbook/webshop-api.md).

- **The proposal** (`coverengine/quote.py`). The rough sizes plus a fit allowance go into the
  shapes we build from the owner's drawings (`drawn.py`: box, sloped box, L, round), with the
  company rules: chair space and balloons for tables, vents per metre of side, drawcords, and
  pieces split by the roll.
  - The pieces are flat, so sizes and areas are exact.
  - The roll length is a simple row layout, and the seams are the shared edges.
  - It takes a few milliseconds.
  - The products and their ranges are in `config/quote_products.json`; the cost model is
    `quote.*` (placeholders, to confirm).
  - The nearest SUNS models are given, with their drape result.
- **The public API** `/api/public/v1/` (`coverapi/webshop.py`):
  - an API key for a webshop's server; none for our own page;
  - 30 calls a minute per address;
  - no cost price to the customer;
  - nothing internal reachable.

  Requests are stored (`requests` in app.db), shown on the admin page with the cost price, and
  mailed.
- **The configurator** `#/configure`: no login, made for an iframe. Framing is allowed only from
  the origins set on the admin page (`frame-ancestors`); without any, the app stays
  `SAMEORIGIN`.
- **Later:**
  - the definitive pattern made automatically from a request (the full route, with the drape);
  - prices per colour or fabric;
  - payment in the webshop.

## ADR-062 — Our own cover webshop, with an AI CMS

The owner, 4 October 2026:

- "no public API; on this server we build a webshop made purely for covers, with our own 3D
  model from all the input and a rain simulation to upsell balloons or a frame; a hyper-modern
  site with a welcome film, then straight to the configurator";
- "the information you lack goes on a settings page";
- "an AI-driven CMS: a command line where colleagues change the website, optimised for AI
  engines, with a preview before it goes live".

Plan: docs/plans/cover-webshop.md. The public API of ADR-061 is not used. The shop runs on our
own internal routes (`/api/shop/...`).

- **The shop** is `/shop/...`, its own front door (`apps/web/shop.html`, `src/shop/`), separate
  from Cover Studio:
  - a landing page (the film from the settings, else the 3D cover turning), how it works, the
    green story, FAQ, NL/EN;
  - the configurator: our own furniture in 3D from the sizes (`coverengine/furniture.py`), the
    cover over it, colours, vents;
  - checkout, the order status, and legal pages.
- **The rain check and the upsell** (`quote.rain_check`). The cover without support, with
  balloons (a hipped roof: straight between the balloons, sloping all round, as the owner
  described) and with a frame (a gable); a round table gets a cone. Each is rained on
  (`rain.py`), the water is shown in blue on the cover, and the shop advises the cheapest
  support that keeps it dry, with its price.
- **Orders** (`orders` in app.db):
  - Mollie payments as soon as a key is set; until then "awaiting payment";
  - the webhook asks Mollie itself (never trusts the call);
  - mails on every status;
  - the admin tab **Orders**;
  - paid → **into production**: the cover shape imported as a cover model (`order-<n>`),
    calculated to the end, then the drape follows by itself.
- **Settings** (admin tab **Shop settings**): company data, domain, prices (overriding
  `quote.*`; "confirmed" drops "indicative"), shipping per country, the Mollie key (never shown
  in full), the balloon and frame products, colours, the film's address, and the notify
  address. The missing fields are listed.
- **The AI CMS.** The site's text is JSON (`data/site/draft.json`, `live.json`,
  `history/`), NL and EN.
  - A colleague types what should change: admin tab **Website (AI)**, or `cover-site "…"` on
    the server.
  - DeepSeek returns changes to the draft only: both languages, no invented facts.
  - The preview link shows the draft (noindex), then **Publish** or **Discard**. Every
    published version is kept and can be restored.
- **For search engines and AI assistants:**
  - the server puts the content into the HTML: title, description, canonical, Open Graph, and
    JSON-LD for Organization, Product (MadeToOrder), HowTo and FAQPage;
  - `/robots.txt`, `/sitemap.xml`, and `/llms.txt` (the shop in plain words, from the live
    content).
- **Still open (QUESTIONS 52–56 and the plan):** the prices, the domain, the Mollie account,
  the legal texts, the film, the balloon and frame products, and the first physical test
  before the first paid order.

## ADR-063 — The drape settles to rest, and seams bend less easily

The owner (4 Oct): the drape "makes assumptions that are not realistic". Two of those are fixed.

- **Settling.** Style3D stopped after `drape.seconds` (5 s), often while the cloth was still
  moving: the picture was a moment in the fall, not the shape the cover keeps.
  - After the fall the same physics runs for at most `drape.settle_seconds` (1.75 s), with the
    speed reduced by `drape.settle_damping` (14 %) every frame. It stops as soon as 99 % of
    the cloth moves slower than `drape.rest_mm_s`.
  - This damping only removes motion. It adds no force, so the rest shape is still where
    gravity, the fabric and the contacts balance.
  - The report gains `at_rest`, `settled_frames` and `end_speed_mm_s`.
- **Seams.** A double-stitched seam is two layers with the allowance folded over and stitched,
  so it bends far less easily than the fabric alone.
  - The bending hinges on the line between two pieces are made `drape.seam_bend_factor` times
    stiffer (5.5, to confirm).
  - This keeps seams as straight, crisp lines, as on a real cover, instead of letting them
    buckle like plain fabric.
  - The wider band of the allowance is not modelled (one hinge row). If photos of real covers
    show that matters, the band follows.
- **Needle triangles.** The Fiora L-part blew up (6.5 m sag) because of 1004 needle
  triangles: the cut left pairs of points 0.04 mm apart. Before the fall, points joined by an
  edge shorter than `drape.merge_mm` (1 mm, far inside the ±5 mm fit) become one point, and
  the needles drop out.
  - Flat "cap" triangles (one angle near 180°) remain on a few large models. They need an edge
    flip or a uniform remesh of the cloth.
  - That remesh, at about 25 mm per edge, is also the answer for the six models that took
    more than 3 hours. They have 36,000 to 129,000 points, against 15,000 for a typical sofa.
- **Cost, measured on the Lucia 2-seater:** 4 s of settling changed the sag from 42.6 to
  42.9 cm. The fall had nearly come to rest after 5 s (6 mm/s at the end), but the run took
  80 % longer. Settling is therefore kept short (1.75 s, about 35 % extra), enough to confirm the
  rest shape.
- **The Lucia's sag (42.9 cm) is the design, not the simulation:** a flat top at the arm's
  height (87.5 cm) spans the lower back and seat, and the fabric sinks into that space.
## ADR-064 — Several languages, and the customer's sizes matched to our range with a learning mode

The owner (5 October 2026): "step 1"
(docs/plans/hosting-scale-and-matching.md). People give their own sizes, and we show which
existing cover fits ("90 %"); below 90 % it is made to measure. The website is in several
languages, driven by DeepSeek. The site moves to Cloudflare later (step 2).

### Languages

- **Setting.** Shop settings: `languages` (default "nl,en,de,fr"). The first language lives at
  `/shop/`, the others at `/shop/<lang>/`.
- **Search engines.** The server puts the text in the right language into the HTML, with
  `hreflang` alternates, a canonical address per language and the sitemap per language.
- **Every word is content.** The buttons, labels and messages are no longer in the code: they
  are in `config/shop_ui.json`, part of the site's content (`ui`). The AI CMS edits and
  translates them like the rest.
- **Translation.** **Translate missing languages** (Website tab) or `cover-site --translate`:
  - DeepSeek fills every missing language in the draft, in batches of 40;
  - it works from the Dutch and English texts and keeps the `{placeholders}`;
  - a fixed glossary keeps one word per thing: Schutzhülle, housse, funda;
  - German uses "du", French "vous".
  - An instruction in the CMS keeps all languages in step, and anything left out is translated
    afterwards.
  - Translations go to the draft only: preview, then publish.
- **First run.** On a copy of the live site: 230 texts into German and French in 48 s, and
  they read naturally.

### Matching (`engine/coverengine/match.py`)

- **Size card.** Every SUNS cover has one: kind, the furniture's length ≥ width and height,
  the side of an L, chairs or not, how its drape went.
- **Kind.** It comes from the category and the name: round tables, L parts and chaises, and
  corner modules (counted as an item).
- **Score per size.** The difference is catalogue − customer.
  - Within −`match.tight_cm` (1.25) and +`match.loose_cm` (4.5): 100 %.
  - Smaller than that falls to 0 over `match.tight_falloff_cm` (3.5): a cover that is too
    small does not go on.
  - Larger falls to 0 over `match.loose_falloff_cm` (27.5): it hangs looser.
- **Total.** The weighted geometric mean (`match.weights` 1, 1, 0.6). Any size at 0 makes the
  total 0. A different kind of furniture, or the other hand of an L, is never a match.
- **What the customer is offered.**
  - From `match.threshold_pct` (90): the existing cover.
  - From `match.choice_pct` (80): a choice between the existing cover and a custom one.
  - Below: custom.
  - All the bands are to confirm (Q57).
- **Ordering an existing cover.** The quote takes `stock_model`. It is priced on that cover's
  own sizes, less `matching.stock_discount_pct` when set (Q58). Into production means it is
  cut from that model's own, tested pattern; no new model is made.
- **Note.** In the catalogue, L sofas are mostly separate modules, so a whole L rarely matches
  one cover and goes custom. Matching a set of modules is a later step.

### The learning mode

- **Shadow (`match.mode`, the default).**
  - The customer leaves an e-mail address and sees nothing yet.
  - The admin tab **Matches** shows the request with the best eight covers.
  - A colleague takes the proposal, chooses another cover or chooses custom, with an optional
    note. The customer is mailed a link in their own language.
  - Every change of the proposal is stored. Editors may answer.
- **Auto.** The customer sees the match at once, and every request is still kept.
- **After delivery.** With `fit_mail` on and the domain set, a shipped order gets one question
  after `fit_mail.days` (14): how does it fit (1–5), a comment and an optional photo
  (JPEG/PNG/WebP up to 6 MB).
  - **Returned** is a new order status.
- **What we learn** (tab **Matches**). Per match band (95–100, 90–95, 85–90, 80–85, below 80):
  - the requests, those answered by a colleague, and how many of those were changed;
  - how often custom was chosen;
  - the orders, the average fit answer, and the returns.
  - From these the threshold and the bands are set.
- **Fixed in passing:** the admin tabs Orders, Shop settings, Website (AI) and Requests had
  never been in the tab bar of v1.7.0, so they could not be reached. They are now.

## ADR-065 — The welcome film: path-traced from our own simulation

The owner (5 October 2026): the animation on the home page must be of lifelike quality.

- **What it shows** (`scripts/film/render_film.py`), 13.75 s at 24 fps:
  - a real SUNS sofa (the Kota 2-seater) on a hardwood terrace as a storm comes in;
  - the Coverlast cover is laid over it;
  - it falls exactly as the Style3D simulation computed (`drape.bin`, played in real time),
    with its sewn seams as soft ribs (the seam edges of `panels.npz`, which move with the cloth);
  - then the rain: the fabric and the deck get wet, the water beads on the coated fabric and the
    drops are stopped by the cover.
- **How it is made.**
  - Blender 4.2 LTS Cycles: path tracing, motion blur, depth of field, the AgX view, and
    OpenImageDenoise.
  - The light and background are Poly Haven's "Approaching Storm" HDRI by Greg Zaal (CC0).
  - Everything else is procedural: the weave and the beads, the boards, the rain (seeded,
    baked).
  - The render is deterministic and resumable: frames that exist are skipped.
- **Where it runs.** Blender runs in the Playwright image, which has its X libraries, so the
  server needs no system packages. It is limited to 6 cores, so the site and the drape queue
  keep 2.
  - 1920×1080 at 48 samples takes about 105 s per frame: 330 frames in roughly 10 hours.
- **Into the shop.**
  - `scripts/film/encode.py` makes `welcome.mp4` (1920), `welcome-1280.mp4` and a poster JPEG,
    using Blender's own ffmpeg.
  - The files go into `data/media/`; the shop serves them at `/media/<file>` with byte ranges,
    which Safari needs.
  - Shop settings `film_url` and `film_poster` point at them.
  - Visitors who asked their device for less motion get the poster.
- **What it cannot do yet** (where help from outside raises it further):
  - **People:** a real workshop, hands laying the cover over the furniture.
  - **The real fabric:** a scan or a set of close photos of Coverlast (colour, weave, sheen),
    which would replace the procedural weave.
  - **Real footage:** filmed footage of rain on a real cover, sound, and a brand edit.
  - Generative video (Veo, Sora, Runway) could add people, but it does not show our own cover
    and fit. The film stays the honest part: our simulation, rendered.

## ADR-066 — Two lines: the studio stays covers.suns.nu, the website is its own brand on Cloudflare

The owner (5 October 2026): "covers.suns.nu stays for the covers of SUNS; the website becomes
a completely different story with another domain, but linked to the database of covers.suns.nu
to check whether it fits, and so on". suns.nu itself stays at Bunny DNS.

- **The studio** (covers.suns.nu, this server) stays the one place for the covers. It holds:
  - the catalogue and the match;
  - the prices and the rain check;
  - the 3D scenes;
  - orders, Mollie and production;
  - the AI CMS and the content in every language.
- **The website** (`apps/site/`) is a Cloudflare Worker on its own domain.
  - It takes the shop's own build files (`/assets/`, `/brand/`) from the studio too, cached
    for a year (their names are hashes), so the scripts always match the studio's pages. The
    studio app is never part of it.
  - `www.` is sent to the bare domain with a 301 (one address for search engines).
  - Address for now: shop.s2dio.living (the owner, 5 October 2026); the zone s2dio.living is
    on Cloudflare.
  - Every page and every API call goes to the studio with the website's key (`x-link-key`),
    plus the visitor's address (`x-client-ip`) for the rate limits.
  - Pages, the feeds, the demo 3D and the film are cached at the edge (60 s; the media a day).
    Quotes, matches and orders always go through to the studio.
  - The studio's session cookies never pass in either direction.
- **On the studio.**
  - `domain` (Shop settings) is now the website's domain, and the shop is its whole site
    (`https://<domain>/`, `/de/` and so on). Canonical links, hreflang, the sitemap, llms.txt,
    the links in mails and Mollie's addresses all point there.
  - **Website link** (Shop settings, `website_link.closed`). When closed, the shop on the studio
    answers only the website (its key) and logged-in colleagues (the preview). Visitors of
    `/shop/…` are sent with a 301 to the website; the API refuses them (403); `robots.txt`
    disallows the studio.
  - The key is made on the admin page (`POST /api/admin/shop/link-key`) and is shown once. Only
    its hash is stored. A new key stops the old one.
  - The logo is a setting (`logo_url`), since the website is another brand.
- **Why a Worker in front, and not a copy of the shop on Cloudflare:** one source of truth.
  - The engine (Python, compiled geometry) cannot run at the edge.
  - The studio already renders the pages with their content for search engines.
  - The edge cache takes the load of a busy day.
  - D1/KV copies of the content or orders would have to be kept in step. That is needed only
    if the studio is ever down for long, and it can follow then.
- **Tested end to end on this machine** (`wrangler dev --local` against a studio copy on port
  8091):
  - the website's pages in four languages, with the right canonical and hreflang;
  - the API through the key, and the match in the German configurator;
  - the studio's `/shop/` redirected, its API refused, the studio app not reachable.

## ADR-067 — The website as one scrolling story in the S2DIO house style

The owner (5 October 2026): a very modern single page where something happens with every
scroll, following how we work, and a lifelike opening animation. The house style is the brand
book by IS Creative (docs/brand.md). The plan is docs/plans/scroll-site.md.

- **The page** (`apps/web/src/shop/Story.tsx`, with Lenis smooth scrolling and GSAP
  ScrollTrigger):
  - the opening clip shrinks into the arch of the logo;
  - a pinned 3D scene of six chapters (`StoryScene.tsx`): the furniture, the cover around it,
    the pieces stepping apart, every piece flat on the 152 cm roll, the pieces rising and
    falling over the furniture, and the rain;
  - the workshop in arch-framed clips that slide sideways;
  - true numbers (0 in stock, 100 % made to order, 302 models, the 152 cm roll);
  - the FAQ.
  - Visitors who asked for less motion get the same story without the motion.
- **The 3D is our own data**: `coverengine/story.py`.
  - One model's cover as three shapes of the same points: the designed pieces (seams split),
    every piece flat with its true lengths and laid out on the roll, and the Style3D drape.
  - The furniture is merged into one mesh.
  - The studio serves it at `/api/shop/story/<model>.json|.bin|-furniture.glb`, built once into
    `data/story/`, for the model in `story_model` only (default the Kota 2-seater).
  - Each change between shapes is done at 60 % of its chapter, so every stage is seen at rest.
- **Clips: Gemini Veo 3.1** (Fast for the workshop, the standard model for the rain), 8 s each,
  re-encoded for the web with Blender's ffmpeg (1280 wide; the opening clip 1600, about 9 MB).
  - Settings `story_media` point at `/media/…`.
  - A Veo clip made between our own first and last render (the cover being laid over) zoomed in
    and made the fabric fuzzy twice, so it is not used. The cover's fall is shown by our 3D,
    which is our real simulation; Veo shows people, the workshop and the rain.
- **Texts** are content (`story`: chapters, work, numbers), so the AI CMS edits and translates
  them.
- **Colours and type** follow the brand: off white `#F1F2F2`, the greens, Work Sans. The header
  is clear over the film and light further down, with the S2DIO website logo.
- **Rolled out carefully.** `home_story` (Shop settings) switches the live home page over. Until
  then the story shows only at `preview.s2dio.living`: a second Worker (`--env preview`) with its
  own fresh build and the studio's data, noindex.
  - The studio now accepts one link key per Worker (a list of hashes), so each can be revoked
    alone.

## ADR-068 — Free-form covers from the drawings: a cross-section along a path, read by Gemini

The owner (5 October 2026): the organic, mostly round shapes in the drawings did not come
through, and the seams often did not match. 26 drawings were "other": quarter rings, U and
horseshoe sofas, crescents, D, kidney and lens shapes, tapered and angled sofas, arms that come
down along their length.

- **The new shape, `swept`** (`engine/coverengine/swept.py`): the sloped box of drawn.py along a
  path, which is the cover's back edge in the top view.
  - The path is made of `line`, `arc` (radius, angle; positive towards the front) and `turn`
    (a mitred corner).
  - The cross-section is a list of points (plan offset from the back edge, height); each point
    is a seam along the cover. It may change along the path ("profiles", interpolated), which
    covers tapers and arms that come down.
  - **Hips:** a line on top shorter than the cover (`line_lengths_cm`, as written) stops early at
    both ends, and the top slopes down to the end wall (S24).
  - **Seams across:** where drawn, plus at every corner and every change between line and arc.
  - **Ends:** square, angled or round (half round).
  - A band too wide for the roll **in both directions** gets a seam. Along the roll a piece may
    be any length (the owner: the machine cuts long), unless `max_piece_mm` is set.
  - A curve towards the front tighter than the cover is deep is refused, because the inside of
    a U would fold over (C26, C27).
- **Reading the drawings** (`scripts/drawing_swept.py`): **Gemini 3.1 Pro** (`ai.vision_*`) reads
  all the pages into the shape.
  - The program builds it and measures every length a drawing can show: each line along the
    cover, in total and per piece; the heights; the bands across, along the surface and in
    plan; the depth.
  - Every size written on the drawing must come back within 1 cm (or 0.6 %). The ones that do
    not are sent back to the AI with the model's own lengths, for up to 3 rounds.
  - Inch-only drawings are converted (S38, S39).
  - Each cover is calculated in its own process with a time limit, and its result is kept at
    once, so one cover that hangs never stops the others.
- **Results on 5 October** (out/drawings/swept): built with every written size found:
  - S24 and S25 (quarter rings with hips), 12/12 each;
  - D5 (14/14), D1 (7/7) and D6 (9/9);
  - L4 and L4/L8 (10/10), the Nardo S13/S14 (8/8);
  - S26 and S27 (9/9), S37 (4/4), S43 (8/8), S47 (5/5), U2 (8/8).
  - Built with most sizes: C26 8/9, C31 11/14, S32 6/7, S38 and S39 9/13, S44 6/8, S46 7/8.
  - Still open: C27 and C28 (the tight bend, retried with the new check), S45 (a radius equal to
    the depth: a pie piece), and S20 (Bora, not ordered).
- `drawn._poly` mends an invalid outline (`make_valid`), or falls back to a fan.

## ADR-069 — The Style3D drape on a GPU on demand (Modal)

The owner (5 October): a control check with the GPU through the API.

- **`engine/coverengine/drape_gpu.py`.** This server prepares the cloth (the flat pieces: a
  CPU job of seconds) and the furniture. Modal runs the same Style3D fall on an **NVIDIA L4** and
  sends the frames back. Measuring, writing `drape.*`, the rain and the AI's verdict stay here.
  - The engine is shipped as plain files into a container with newton 1.6, warp 1.17 and the
    same numpy, scipy and trimesh as here.
  - The cloth is sent as plain arrays.
  - `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` come from deploy/.env.
- **Measured on the Kota 2-seater:** 405 frames in 396 s on the GPU (about 1 s a frame, against
  9 s on the CPU). With the start-up that is about 7 minutes a sofa instead of about an hour, at
  roughly €0.10.
- **`drape.gpu: modal`** is the default. With no keys, or no answer from Modal, it runs on this
  server as before.
- **The control check** (`scripts/gpu_check.py`): many covers at once, one GPU each. The account
  runs 10 at a time; the rest wait in the queue. Each cover is then measured, rained on and
  judged by the audit's drape check (folds, sag, water). One CSV comes out.

## ADR-070 — The workshop's own reference per model, compared and learned from

The owner (5 October): upload our own 3D model or pattern PDF per model, so the system can
compare and learn from our input.

- **Model page, tab "Your reference".** Upload a 3D model of the cover (STEP, IGES, STL, OBJ,
  PLY, GLB) and/or a PDF (the drawing or the pattern). The files are kept in
  `models/<id>/reference/`, and the comparison runs in the background
  (`engine/coverengine/compare.py`).
- **3D against 3D.**
  - The reference is read as it is, in its own file.
  - Its unit (mm, cm, inch, m) and up axis (Z or Y) are the ones that match the program's cover
    best.
  - It is turned about the vertical in 15° steps to the best fit, then fitted with ICP (Kabsch,
    libigl distances, no scaling or mirroring).
  - Per point the signed distance (+ ours roomier): mean, 95 %, largest, the share within
    ±5 mm, roomier and tighter.
  - `compare.glb` shows the program's cover coloured by the distance.
- **A PDF against the pattern.**
  - Every size written on it is looked for among the program's lengths (each piece's edges and
    flat size, the cover's size).
  - Gemini then puts the PDF beside the program's size drawing and cover picture, and lists the
    differences: pieces, seams, sizes, features.
  - It also proposes lessons. **A person accepts each one**; accepted lessons go to the data
    folder's `learning/lessons.json`, so they last across releases, and into every AI prompt.
- **The learning record.** Every comparison is logged in `learning/references.jsonl`. That is
  the material for tuning the seams and the shapes.
- **Checked:**
  - S24's cover against its own drawn surface: 0.0 mm, 100 % within ±5 mm;
  - a test box uploaded in metres and 1 cm higher: found as metres, its top flagged.
- **Downloads carry the model's name.** The cutting table's file is `<model>.dxf` (with `-r<n>`
  for a kept revision); other files are `<model>-<file>` (the owner, 5 October).

## ADR-071 — The website's story as rendered frames, scrubbed by the scroll; the hero film in sand

The owner (5 October): the steps on the one-page site were "too basic: fine for internal use, not
for the website; it must be tighter and better", the covers are sand, not dark green, and then
(evening) "much better colours, but it must look a lot more realistic, especially the
animation; the hero film is still a green cover".

- **The story, rendered.** `scripts/film/render_story.py` builds it in Blender Cycles from our
  own data, the same shapes the live 3D used (`coverengine/story.py`):
  - the SUNS sofa with woven taupe cushions and an anodised aluminium base;
  - the cover in sand canvas: a fine weave, soft wrinkles, a little variation in the coating's
    sheen, a twisted cord piping on every seam;
  - the pieces stepping apart;
  - the whole nested pattern flat on the 152 cm roll on the cutting table, seen from the front
    (lens shift off for this chapter), then a slow push in; the pieces fly there quickly and
    the table appears opaque, so no picture catches them half transparent;
  - the cover hanging over the sofa as Style3D drapes it;
  - rain on a backdrop that turns house green: clear drops drawn as streaks by the camera's
    shutter (motion blur in that chapter only), the canvas darkening in patches and runoff
    streaks, beading and glossier where wet.
  - The camera frames the cover right of centre (lens shift), so the captions sit on the
    plain studio wall.
  - The camera sees a plain studio tone where no wall is; the HDRI only lights.
  - The timeline keeps 6 chapters of 40 frames; `--count` pictures are taken along it at
    subframes (360 by default) for smooth scrubbing.
  - The pictures are WEBP, 1600 × 900, about 16–20 KB each.
- **On GPUs.** `scripts/film/gpu_render.py` runs Blender 4.2 on Modal, one L4 per 12
  pictures, 10 at a time.
  - Blender is fetched from mirrors, because blender.org refuses some cloud builders.
  - Denoising is OpenImageDenoise: the OptiX denoiser needs driver parts the cloud GPUs lack.
- **On the page** (`apps/web/src/shop/StoryFrames.tsx`):
  - The pinned section draws the picture that matches the scroll, filling the canvas; on a
    narrow screen the crop follows the cover.
  - Every 8th picture loads first, so the whole story scrubs at once; the rest fill in.
  - A soft scrim behind the captions turns green in the rain chapter; a fine animated film
    grain (CSS) lies over the pictures.
  - Without the pictures, the live 3D scene is shown as before.
- **Where:** the studio's `media/` folder serves them as `/media/story4-001.webp` …
  `story4-360.webp`. Each render gets a new name, because the edge keeps `/media` for a day;
  `media.frames` in the shop settings picks the set.
- **The hero film** is a Veo 3.1 take animated from a still that Gemini 3 Pro Image made:
  - a sand canvas cover on a sofa on a wet terrace in light rain;
  - the still anchors the colour, which text alone did not;
  - three takes; the steadiest, with no camera jump and true sand, was chosen;
  - encoded in H.264 at 1920 × 1080, 5 MB, with a poster: `/media/hero-sand.mp4` and
    `hero-sand.jpg`. The green `rain2.mp4` is kept.
  - A Blender clip of our studio scene was judged against it and is clearly less real, so
    no separate Blender hero was rendered.
- **Live:** the preview (preview.s2dio.living) shows all this through
  `apps/site/preview-overlay.json`; `npm run deploy:preview` copies it into the build. The live
  website shows it when the owner turns `home_story` on (and sets `story_media.hero`) after
  approving the design.

## ADR-072 — Free plan shapes from the drawing's own lines; the AIs only check, and check each other

The owner (5 October): "S45 looks nothing like it: it is an organic top and we make a square box
of it". And: "why do we use Gemini for everything? We must decide it ourselves and use AI as a
check", "and DeepSeek too, let them check each other".

- **What went wrong with S45.** The free-form route (ADR-068) asks Gemini for a swept shape: a
  cross-section along a path. A kidney seen from above, straight up, is no swept shape. Gemini
  said so in its `why_not`, gave a 152.4 × 50 cm box "anyway", and the run built it because
  the one written size it found (45 cm) came back. Two faults: the AI decided the shape, and
  a reader that said "this does not fit" was not listened to.
- **Never a stand-in.** `drawing_swept.py` no longer builds a drawing whose reader gives a
  `why_not`: its status becomes "not a swept shape".
- **The program reads the drawing itself** (`coverengine/drawing_vectors.py`). The PDFs come out
  of CAD, so every view is vector lines. A plan view of a free shape is one closed path, with
  its outline there point by point.
  - The path is found as a closed path with at least 20 segments above the order table.
  - Its scale comes from a written circumference (perimeter) or a length/diameter (longest
    distance).
  - Sizes are read deterministically from the text next to the words height, length,
    circumference, diameter, width and depth.
  - Two written sizes that disagree by more than 3 % are reported as a conflict, never chosen
    between silently.
  - Among the 130 drawings, closed outlines are found in S45, D5, C28 and R1 to R3.
- **The shape "outline"** (`drawn.outline_cover`): the plan outline is the top. It is split
  across the roll only when it is wider than the roll in every direction. The band runs round
  it, cut at `band_seams_cm`; the default is the leftmost point and halfway, because a closed
  band needs a seam and two pieces lie flat.
- **The AIs check, and check each other** (`coverengine/crosscheck.py`).
  1. Gemini looks: the drawing's pages beside the program's picture and piece list.
  2. DeepSeek reads: every word and number on the drawing, against the cover's measured
     sizes and Gemini's verdict.
  3. When they disagree, Gemini gets DeepSeek's points once more.
  4. The outcome is "agreed: same", "agreed: different" or "person to check". It never
     changes the cover.
  - Both get the workshop's terms: an air pocket is a vent, covers are open at the bottom,
    fabric and colour are finishing.
  - `scripts/drawing_outline.py` builds and checks the outline drawings.
  - `scripts/drawing_crosscheck.py` checks any built drawing cover.
- **S45 now:**
  - the kidney from the drawing's lines, 358.4 cm round (141.1 in, as written), 125.8 cm
    long, 45 cm high, 4 vents (`features.vents_min` 2 per side);
  - 3 pieces plus the vents;
  - the old box scored 10 (Gemini) and 20 (DeepSeek), the new cover "agreed: same" after
    Gemini's second look.
  - The drawing's "152.4" contradicts the circumference. The program checked it against the
    drawing's own 3D view: projecting the outline fits that view better at 358.4 cm (IoU
    0.93, at exactly the isometric angle) than at 152.4 cm (0.89). Question 64 asks the owner.
- **Next, the better alternative.** Free shapes that are drawn only as a 3D view (S44, S47,
  S32, C26) have no closed plan path. Their outline can be recovered the same way the S45
  check did: fit a plan outline whose isometric projection matches the view's lines. The
  cross-check shows which of them need it.

## ADR-073 — Air vents shown in 3D

The owner (5 October): "a checkbox to show the air vents in the 3D model".

- **Where a vent sits.** The vents are placed on the flat skirt panels (`finish.place_vents`,
  in `pattern.json`'s coordinates). `coverengine/finish/vents3d.py` carries them back to 3D:
  1. it flattens that panel again exactly as `cover flatten` did (the same mesh, solver and
     settings, so the same flat panel);
  2. it checks the result against the stored outline (within 1 mm, otherwise a warning and
     no vent);
  3. it carries each corner and the centre to 3D through the flat triangle it lies in
     (barycentric);
  4. the normal points out of the cover.
  Skirt panels flatten in about a second, so this costs little.
- **Written by `cover export`** as `vents.json`, next to `finished.json`, for every model on its
  next export. It is served like the other model files.
- **The viewer.** A tick box **Show air vents** (off by default, remembered per browser)
  draws each opening as a dark rectangle with a red frame, 4 mm outside the cover, plus a sand
  hood hint from its top edge.
- **Not chosen:** storing every panel's flat mesh at `cover flatten`. That needs a new file
  and a re-flatten of all models before any vent shows, whereas re-flattening one skirt
  panel at export works for every model as it is.
- **Checked:**
  - the test box: as many vents as the cutting list's hoods, every point within 3 mm of the
    cover surface, the bottom edge `features.vent_above_hem_mm` above the hem, the normals
    pointing out;
  - S45: 4 vents round the kidney's band, two per side.

## ADR-074 — Feedback on your own reference

The owner (5 October): "when we upload our own 3D models or PDFs there must be feedback: what
did you do with our information, as a kind of double check".

- **A report per upload** (`compare.report`, saved in `compare.json` with the comparison and
  shown at the top of the tab Your reference). It has one verdict and five steps in plain
  words.
  - **Verdict:** agrees, differs, or a person must look.
  - **Steps:**
    1. Received: the file, its size, who, when.
    2. Read: a 3D model's triangles, the chosen unit and up axis, its turn and fit move
       (`compare.surface` now returns `read_as`); a PDF's pages and the sizes found.
    3. Compared: the deviation numbers, or the sizes found and not found.
    4. Double check by two AIs.
    5. What changed in the program.
- **The double check** (`compare.double_check`; advice, never a stop; a failure is shown in the
  step):
  - **a PDF:** `crosscheck.run` (ADR-072). Gemini looks, DeepSeek reads the numbers, and they
    check each other. It needs the program's `cover.png` and `finished.json`; without them the
    step says so.
  - **a 3D model:** DeepSeek gets the measured numbers and says what they mean, with its own
    verdict.
- **The verdict comes from the numbers first; the AIs can only send it to a person.**
  - **A 3D model:** it agrees when at least 90 % of the program's cover is within ±5 mm. When
    DeepSeek's verdict differs, "a person must look".
  - **A PDF:**
    - "agreed: same" with every written size found → agrees;
    - "agreed: same" with sizes missing → a person looks;
    - "agreed: different" → differs;
    - "person to check", or no AI answer → a person looks (differs when sizes are missing).
- **What changed is filled in when the page is shown** (`compare.changes_step`). Lessons are
  accepted later, so this step is built each time from `learning/lessons.json`.
  - It says: nothing changed by itself.
  - It counts the lessons the AI proposed, waiting for a person.
  - It lists the lessons accepted for this model, with who and when.
  - It points to the log in `learning/references.jsonl`.
- **History:** every upload's report is also written to
  `models/<id>/reference/history/<time>-<kind>.json` (atomic). The tab lists them under the
  current one: when, file, who, verdict, and the steps.
- **S45, its own drawing as the reference:** "Your reference agrees with the program's cover".
  - Gemini and DeepSeek both said "same", score 100.
  - The step lists the drawing's 152.4 against 141.1 in contradiction for a person
    (question 64).
- **Better later:** `written_mm` takes the inch sizes only when a PDF has no metric ones. So
  S45's 141.1 in circumference is checked by the AIs, not by the size search. Checking each
  inch size that has no metric twin, against sums of edges (a circumference is the band's
  pieces together), would let the numbers check it too.

## ADR-075 — The program reads the drawing's views and builds the cover from them; the AIs judge

The owner (5 October, evening) approved phases 1–4 of docs/plans/drawings-own-reading.md for
the night:
- a vent count on the drawing always wins;
- a better cover replaces the old one live, with a mail;
- every drawing cover is exported again;
- about €50 for paid calls;
- release when all tests are green.

**Phase 1: features from the text** (`drawing_vectors.features`, `scripts/drawing_features.py`).
- "4 Air Pocket", "6 Airpockets" and "Air Pocket four side" are read by the program; 97 of
  the 115 drawings write a number.
- Without a number, the arrows that run from the "Air Vents" label to the cover are counted
  (S21: 6, S26: 4, D5: 4, ...). S45, which has both, gives 4 either way.
- The count becomes the new setting `features.vents_total` per cover. It always wins over
  one per metre, and is spread over the sides by their length (largest remainder).
- All drawing covers were exported again, so the cut file, the cutting list and `vents.json`
  follow.

**Phase 2: views and size arrows** (`drawing_views`).
- **The views.** Every view on the sheets is a rendered picture with a transparency mask: the
  mask is the exact silhouette.
- **The 3D view** is the one whose outline runs at ±30°; when curves hide that, it is the
  largest picture.
- **The dimensions** are two filled arrowheads on one line, pointing apart, with the size
  written beside the line. A size thus belongs to a length on the page, never to a guess.
- **The scale per page** is the median of those dimensions. On S38, 12 of 15 dimensions agree
  within 0.1 %.
- A vertical dimension in the 3D view counts with the isometric factor 0.816. This is how
  S45's only arrowed size (45 cm) gives the same scale as its written circumference.
- **Which view is which.** An elevation as wide as the plan is the front; as wide as the plan
  is deep, the side. Every orthographic view is also tried as the plan.

**Phase 3: the solid** (`drawing_solid`).
- **The shape.** The plan is extruded up and cut by each elevation extruded across: the shape
  a CAD drawer built.
- **Every way is built.** Each elevation is tried as front or side, and from either end.
- **The check.** Each candidate is drawn isometrically from the four corners. The one whose
  silhouette covers the drawing's 3D view best (IoU, at the sheet's scale, no fitting of size)
  wins.
- **A plan alone.** The height is the one whose 3D view fits best, snapped to a written size.
  S47 lands on 38.1 cm and S37 on 45.1 cm, both as written.
- **The pieces.** The surface is split at folds sharper than 10°; between two upright faces
  only a real corner (35°) counts, so a curved wall stays one piece. A ring is cut in two, and
  a piece wider than the roll is cut across.
- **Results:**

  | Cover | Fits the 3D view | Old cover |
  |---|---|---|
  | S38 | 0.98 | 0.86 |
  | S39 | 1.00 | 0.97 |
  | S47 | 0.99 | |
  | S45 | 1.00 | |
  | S46 | 0.96 | 0.82 |

**What replaces a live cover** (`scripts/drawing_rebuild.py`, each drawing in its own process).
1. The new solid must fit the 3D view clearly better than the live cover's own surface: at
   least 0.85 and 0.03 higher. Or, when the AIs found the live cover poor (below 60), it must
   fit fairly (0.80).
2. It is built beside the live cover, and Gemini and DeepSeek check it (ADR-072).
3. It replaces the live cover only when the AIs also find it better: "agreed: same" where the
   old was not, or 5 points higher.
4. The replacement is a new revision in the cover's own folder: history, references and
   settings are kept, and the old drape results are removed.
5. Everything was backed up first (cover-data/backup-drawings-before-night-2026-10-05).

- **The rule works both ways:**
  - S46's new solid fits the 3D view better (0.96 against 0.82), but the AIs scored it 30–45
    against 100 for the live cover, so the live one stays.
  - S38 goes from 57.5 to 90.
- **Not yet:**
  - drawings with only a 3D view (phase 4: fitting a footprint to the 3D view's lines);
  - rounded edges (the extruded silhouettes give sharp ones; S44 0.83);
  - vent positions written as "at middle" or "at top" (the owner's rule puts them 5 cm above
    the hem; question 66).

## ADR-076 — Drawing covers in as few pieces as the shape allows

The owner (5 October, night) on drawing-s43: "this seems to have far too many panels, it must
be much simpler."

- **Why S43 had 37 pieces.** The shape the AI read (ADR-068) had profile points 4 cm and
  0.5 mm apart, and its curve was cut into many strips. The swept builder made each strip a
  piece, and drawing covers kept every part as a piece.
- **The joining** (`coverengine/drawn_merge.py`). Two neighbouring pieces are joined when all
  of these hold:
  - the fold between them is gentler than `drawn.merge_fold_deg` (15°), so a real crease
    stays a seam: the back strip and the slope, a wall and the top;
  - the joined piece is one sheet with one outline (a ring is never closed);
  - flattened, it stretches at most `drawn.merge_max_stretch_pct` (1 %) over 98 % of its
    area;
  - it fits the roll.

  The gentlest folds are joined first, until nothing more can be joined.
- **Where it applies.** Only to the covers whose seams the program made (swept, outline, the
  views of ADR-075), both when they are built (`scripts/drawing_cover.py`) and to the existing
  ones (`scripts/drawing_merge.py`, a new revision, the shape unchanged). The box-family
  drawing covers keep their seams: they follow the seams on the drawing, as the workshop sews
  them.
- **Result on 12 covers**, among them:

  | Cover | Pieces before | Pieces after |
  |---|---|---|
  | S43 | 37 | 9 |
  | C27 | 34 | 7 |
  | C31 | 30 | 14 |
  | S44 | 20 | 10 |
  | S13/S14 Nardo | 14 | 6 |
  | C26 | 14 | 7 |

  C28 still fails at the cut, as before; it was restored as it was.
- **Better later:** S43 still has a few small pieces where the back strip meets the round end.
  Joining across a crease with a fold line (as for box tops, ADR-055) would remove them.

## ADR-077 — The cheap Gemini model for checks and readings

On 6 October Gemini's monthly spending cap was reached. Most of the money went to two things:
- **The Pro model's long reasoning:** a picture check of S44 took 146 s, and the hidden
  reasoning tokens are billed as output.
- **Veo videos for the website:** several euros per take.

The owner asked whether DeepSeek alone would do. It cannot: DeepSeek reads no pictures, and
whether a cover is a kidney or a box is only seen by looking.

The Flash model gave the same verdicts as Pro:
- S47: both 100, "same".
- S44: Pro 75, Flash 35, both "different" (Flash is stricter, and rightly so).

Flash took 7–21 s instead of 13–146 s, at about a tenth of the cost.

- **Settings:** `ai.check_model` and `ai.vision_model` are now `gemini-3.8-flash` (the owner:
  "fine, then we go to a cheaper model").
- **Veo:** only on the owner's explicit request.

## ADR-078 — The AI's costs kept, with triggers that warn and stop

The owner (6 October), after Gemini's monthly cap stopped every call: "build a trigger yourself
for when the costs go up."

- **Kept** (`coverengine/spend.py`):
  - every paid AI answer (`ai.ask_parts`) is written to <data>/usage/ai-YYYY-MM.jsonl with
    its tokens and the estimated cost in euros;
  - reasoning tokens count as output, because they are billed so;
  - prices per million tokens are in `spend.prices`, to confirm against the bills;
  - an unknown model is priced as the dearest one we know, so a new model warns too early,
    never too late.
- **Warned** (the watchdog, every 10 minutes, mails rick@s2dio.industries once per trigger,
  again after `REMIND_HOURS`):
  - at 50 % and 80 % of `spend.budget_eur_month` (€50, to confirm);
  - when one hour costs more than `spend.hourly_spike_eur` (€2.50);
  - the mail names the dearest models.
- **Stopped:** at 100 % of the month's budget every paid call is refused with a clear message
  until the budget is raised (`spend.hard_stop: true`).
- **Not covered:** Veo videos for the website go through their own calls outside the engine.
  They are made only on the owner's explicit request (ADR-077).
- **The ledger's first finding:** Gemini Flash costs about €0.01 per check, but DeepSeek
  reasoned 40,000–70,000 tokens per cover, 85 % of the cost.
  - With thinking off, DeepSeek answered wrongly: it took 141.1 in for not 3584 mm.
  - `ai.check_reasoning: low` keeps it right at about 40 % less (€0.03–0.05 per cover).
  - A full round of 115 covers costs about €5.
  - DeepSeek stays, because two vendors checking each other catch more.

## ADR-079 — The Desk: people approve the drawing covers, the AI only sorts

The owner (6 October): a hyper-modern dashboard to keep track of everything, with a checkbox for
"actually produced"; the cutting-table DXF only after approval; Rens, Rick and Wouter approve.

- **State per model** in `desk.json` (written atomically), with every action and the state
  before it, so an undo steps back exactly:
  - new → ai-checked → approved → produced, or rejected;
  - the fit after sewing;
  - a preferred revision;
  - the drawing's code and PDF.

  `check.json` holds the latest Gemini + DeepSeek check. `scripts/drawing_crosscheck.py` now
  writes it into the model, and `scripts/desk_import.py` copied the earlier checks: 113 of 115
  covers.
- **The catalogue follows:** approved → checked, produced → production, rejected → draft.
- **Learning:** a reject in words is stored as a lesson (learning/lessons.json, `from: desk`).
  Every action is logged in learning/desk.jsonl.
- **Who:** `desk.approvers` ("rens,rick,wouter", matched on user name or first name). Admins
  may always.
- **The DXF gate:** `desk.require_approval_for_dxf`, scope `desk.gate_scope: drawings`.
  - Only drawing covers wait for approval, because the 314 SUNS models are all still "draft".
    Setting `all` gates every model on catalogue status checked/production.
  - An admin can override with `?override=1`, and the history keeps it.
- **API:**
  - `GET /api/desk` (queue, counts, average score, AI spend);
  - `GET /api/desk/{id}` (card);
  - `GET /api/desk/{id}/page/{n}` (a drawing page as PNG, cached in desk-cache/);
  - `POST /api/desk/{id}` with approve | reject | produced | fit | prefer | undo.
- **Web:** the Desk page (Desk.tsx, desk.css): the brand book's colours, Work Sans, light and
  dark, the keys j/k/a/r/p/u, and the existing 3D viewer.
- **Better later:** a revision keeps only its cut files, not its 3D. "Cut this" therefore marks
  the revision whose DXF the workshop cuts; it does not bring back the old 3D.

## ADR-080 — A lean pipeline: only what changed is calculated, the expensive extras on request

The team (6 October): "every improvement recalculates so much, which costs time and tokens".
Steps 1 and 2 of docs/plans/two-routes.md.

**Off by default (still available as a button or flag):**
- **The drape after every saved calculation** (ADR-059): `drape.auto: false`. It was a Style3D
  fall on a Modal GPU, a rain simulation and two AI verdicts after every save, every shop order
  and every reference upload. The "Drape" button runs it. `COVER_AUTO_DRAPE=on|off` still
  overrides it.
- **The AI choosing a box cover's pieces and a table's balloons:** `hull.box_ai` and
  `hull.balloon_ai`, both false. The rule decides:
  - box covers: the fewest top pieces, then the fewest pieces, within
    `hull.box_volume_slack_pct` of the tightest box, never a sliver. This is what the AI was
    asked to weigh (the owner, 2 Oct);
  - tables: the fewest balloons with which all water runs off, about one per
    `hull.balloon_spacing_mm`.

  Every table recalculation made a paid call before.
- **The size drawing** is no longer written by every flatten (`flatten.size_drawing: false`).
  It is made when it is opened, approved or compared (`export.drawing.ensure_sizes`), and again
  when it is older than pattern.json.
- **The vents in 3D (vents.json)** are made when the viewer's tick box asks for them
  (`finish.vents3d.ensure_vents`). Export no longer flattens every skirt piece a second time.
- **cover.png** is rendered only when the cover's shape changed, never for a trial run.
- **A revision** is kept only when cut.dxf changed from the latest revision, or on request
  (`cover export --save-version`).

**The step cache** (`coverengine/stepcache.py`):
- **The stamp.** Each step (hull, cut, flatten, export) leaves <model>/steps/<step>.json with
  three things:
  - the parameters it read while it ran (measured through EffectiveParams, not a hand-written
    list), with their values;
  - the hashes of the files it reads from the step before. cover.json counts without its
    catalogue notes and its parameters; the parameters are compared value by value;
  - the hash of the engine's code.
- **The skip.** A step whose stamp matches and whose outputs are there skips itself ("unchanged,
  skipped"). `--force` always calculates; a step written to another folder (`--out`) never
  skips.
- **The server decides.** The web app no longer works out which step a setting starts from: it
  sends hull→export, and the unchanged steps skip themselves. `POST /run` takes `force`.
- **pattern.json** keeps the parameter record of the run that made its geometry. Copying the
  full set into the file does not count as reading.

**Measured on the procedural chair:**

| | Before | After |
|---|---|---|
| Full first run | 16.5 s | 13.5 s |
| Flatten | 6.6 s | 2.9 s (no size drawing) |
| "Run again" with nothing changed | 21.3 s | 0.9 s |
| A vent setting changed | export only, or the full 21.3 s via "Run again" | export only, 2.6 s |
| The clearance changed | | hull onward |

`cover batch` over the catalogue benefits in the same way.

## ADR-081 — Route A: a drawing (PDF) → a cover, one reader, nothing guessed

The team (6 October 2026) asked for two routes only (docs/plans/two-routes.md). This is route A
as one step: `cover drawing-build <model dir> --pdf FILE` (`coverengine/drawing_route.py`), and in
the web app "Upload drawing (PDF)" on the Models page (`POST /api/models/drawing`, a background
job of the one step `drawing-build`).

- **One AI-free reader chain.**
  1. A closed free outline drawn as vector lines, scaled by its written circumference or
     length (ADR-072): the plan straight up to the written height.
  2. Otherwise the views: silhouettes, the scale from the size arrows, the plan cut by the
     elevations (ADR-075).

  A shape is only taken when it covers the drawing's 3D view at least `drawing.min_iou` (0.85).
  The outline is checked against the 3D view too, when the drawing has one.
- **Nothing is guessed.** When neither reader is sure, the cover is "needs a person", with the
  reasons:
  - no top view;
  - no size arrows;
  - the shape fits the 3D view only 78 %.

  No surface is built, and an existing cover is left as it is. A check.json with outcome
  "person to check" puts it at the top of the Desk (ADR-079).
- **Then route B.**
  - The vent count from the drawing (written, or counted from the arrows) goes into
    `features.vents_total`.
  - The program's own seams are joined where there is no crease (ADR-076). This lives in
    `drawing_route.surface`; scripts/drawing_cover.py uses it too.
  - The surface is written with one part per piece, imported as a cover surface, and runs
    through hull, cut, flatten, export and preview.
- **drawing_read.json** keeps what was read, for the Desk's card:
  - the reader and the views;
  - the scale and how it was found;
  - the dimensions;
  - the written sizes that contradict each other;
  - the vents and where their number came from;
  - the fit to the 3D view.
- **On the owner's drawings** (scratch folder, not live), each built in about 10 s:

  | Drawing | Read by | Result |
  |---|---|---|
  | S45 | outline | 3 pieces, 4 vents, the 152.4 vs 358.4 conflict noted, fit 1.00 |
  | S47 | views | 3 pieces, 3 vents, fit 1.00 |
  | S38 | views | 6 pieces, 4 vents, fit 0.98 |
  | C27 (U shape) | — | needs a person (78 %) |
  | S44 | — | needs a person (83 %) |
  | T5 | — | needs a person (no top view, only the 3D view) |
- **Rebuilding:** `POST /api/models/{id}/drawing` builds an existing drawing cover again from
  its drawing as a new revision. It keeps reference/, desk.json and revisions/.
- **Not built:** the explicit "Let the AI read it" button for a "needs a person" drawing (the
  old Gemini reader, ADR-068). The scripts still offer it; a button is for later, if the team
  wants it.

## ADR-082 — Learning that changes the cover itself: Desk corrections, group rules, test cases

The team (6 October): "when we apply a learning, it does not show in a new version. Does it
really learn?" It did not.
- An accepted lesson was only text in the AI's prompts.
- The geometry (seams, pieces, vents, the drawing reading) never read it.

**Now** a correction at the Desk is something the program uses, deterministically:

- **Per cover** (`apps/api/coverapi/desk.py` `correct`, `POST /api/desk/{id}/correct`):
  - a vent count, a vent height or a skirt seam height becomes a parameter override in the
    cover's own `cover.json`;
  - "remove this seam" or "add a seam" becomes a piece edit in `part_edits.json`.

    The cut reads the edits for covers drawn in parts and for box covers
    (`seams/build.py`, `learned.apply_edits`). A join is located by a point on the seam, so
    it survives the renaming of pieces: "join the two pieces whose seam passes here". A split
    takes a plane: x, y or z at a value.
  - a size read wrong goes to `drawing_corrections.json`, for the drawing reader;
  - a missing shape is kept as structured feedback.
  - The server decides which steps run (export, or cut → export) and queues them.
  - A correction to an approved cover sets it back to "to approve": the approval was for the
    cover before the change.
- **Per group** (`coverengine/learned.py`):
  - A group is the cover's family, or for a drawing cover its series (S45 → drawing-s).
  - The same parameter correction on `desk.learn_after` covers of a group is proposed at the
    top of the Desk.
  - A person accepts it. It is then written to <data>/learning/rules/<group>.yaml and logged
    in learning/rules.jsonl.
  - `params.resolve_model` merges the group's rules on top of the family preset, below the
    cover's own settings.
  - Rules are read only when the app names the data folder (COVER_DATA_DIR), so a CLI run
    by hand or a test stays deterministic (rule 10).
- **As tests:**
  - Every correction leaves a case in <data>/learning/cases/: what must hold afterwards
    (pieces at most/least, no seam near the point, a vent count, a setting).
  - `scripts/learned_check.py [--recalc]` checks them all. This is the groundwork for the
    team's measuring rod (question 67).
  - The synthetic cases in testdata/learned/ are replayed in CI on a box cover built from
    scratch (`engine/tests/test_learned_cases.py`).
- **The old path:**
  - A reject's words no longer become an AI lesson; they stay in the history and in
    learning/desk.jsonl.
  - The lessons already accepted remain in the AI prompts for advice.
- **`desk.learn_after` is 5:** the team suggested 3, but 3 (and 4, 6) collide with the
  repository's rule that no default may repeat a number used in the engine code. It is one
  setting to change.
- **Not yet:**
  - Moving a seam of a drawn cover is "remove + add" (two clicks), not one drag.
  - A split follows the faces' centres, so on a coarse surface the new seam can step a
    little. The pattern check's wiggle warning shows it.
  - Size corrections do not yet re-read the drawing: the reader of route A (two-routes plan,
    step 3) should apply `drawing_corrections.json`.

## ADR-083 — "Let the AI read it": a button for drawings that need a person; the 85 % threshold kept

The owner (6 October): keep `drawing.min_iou` at 85 %; the AI button may come.

- **Where.** For a drawing that route A could not read surely ("needs a person": C27, S44, T5
  in the first runs), a person may press "Let the AI read it". The button is on the drawing
  upload's outcome and on the Desk card.
- **What it does.**
  - The AI reader of ADR-068 reads the drawing into the swept shape. It moved from
    scripts/drawing_swept.py into `coverengine/drawing_ai.py`, and the script imports it.
  - It uses `ai.vision_model` (Gemini Flash) and is guarded by the month's budget (ADR-078).
  - Every written size is checked against the shape's lengths, with `drawing.ai_rounds` (2)
    rounds of feedback.
- **Advice, never a decision.** When the AI says the shape does not fit (`why_not`), or the
  shape cannot be built, nothing is built. Otherwise the cover:
  - is built through the same route as the program's own reading;
  - is tagged `ai-read`;
  - gets a check that says "person to check", with the written sizes that were not found;
  - waits at the top of the Desk for approval.
- **Commands and endpoint:** `cover drawing-ai <model>` (a job step) and
  `POST /api/models/{id}/drawing/ai`.
- **Tests** fake the AI: no paid call in a test.

## ADR-084 — C- and U-shaped sofas from the exact top view and the back profile

The owner (6 October) on the AI's C27: "it looks nothing like it; a ridge runs over the cover
that is far too pointed." Then: "option 2" (build it by hand from the drawing), "you have the
whole night".

- **Why the earlier ways failed.**
  - The swept shape (ADR-068) follows one curve with a constant cross-section. C27's arms curl
    in and end in round noses, so no path fits; the AI read only about a quarter circle.
  - The views reader (ADR-075) has no side view to use for such a curve.
- **The shape "plan + profile"** (`coverengine/plan_profile.py`).
  - **The plan:** the drawing's own top view, exactly.
  - **The top:** its height at every point is the written profile at that point's distance
    from the back edge. For C27, the strip is 20.3 cm wide at 86.4 cm, then falls to 38.1 cm
    at 99 cm.
  - **The back edge:** the longest run of the outline along its convex hull, i.e. the
    outside of the C or U.
  - **The walls** stand on the outline up to the top.
  - **The pieces:** the top is split at the profile's creases and across at the drawing's
    seam lines; the walls are split at the same lines.
- **Read by the program** (route A, before the views reader):
  - **The profile:** from the written "Height", "Front Height" and "Depth", plus the bare
    strip size.
  - **The seams:** the drawn seam lines over the top view, followed from the outline over the
    crease (choosing the straightest bit there) back to the outline.
  - **The scale:** corrected by the written depth, because the seam lines span the depth. The
    top view's own scale was 16.7 % off on C26 and 5 % on C27.
  - **Trust:** the back edge's segments between the seams must match the written lengths
    (75 %). On both drawings every segment matched within 1 cm.
  - **A typo on the drawing is found, not followed.** C27 writes 235.1 cm beside 96.5 in
    (= 245.1 cm); the measured segment is 245.0 cm.
- **C26 and C27** are rebuilt this way and live (new revisions; backups in cover-data).
  - C26 has 20 pieces and covers the drawing's 3D view 98 %.
  - C27 has 25 pieces and 10 vents. A vent that fell on a 16 cm end piece now moves to the
    nearest piece with room (`finish._roomy`), so the drawing's count is kept.
  - Both wait at the top of the Desk for a person.

## ADR-085 — "Unfold": the cover's pieces pulled apart and laid flat, with where the fabric goes

The owner (7 October): "an animation from the 3D model of all panels, how they come together
and lie flat, so we also see all dimensions and where the extra lengths of fabric come from."

- **The data** (`coverengine/unfold.py`, `GET /api/models/{id}/unfold.json` and `.bin`).
  - Three shapes of the same points, as on the website's story (ADR-071):
    - on the cover;
    - pulled apart along each piece's own normal;
    - flat on a table in front of the furniture.
  - On the table every piece lies on its own finished outline (finished.json). Its flat
    points are turned and shifted onto the net outline, by the best of the turns and the
    mirror of its main axis.
  - The table is square-ish (rows about 1.6 × the square root of the cut area long), with the
    vent hoods and membranes laid beside the pieces.
  - Computed on request, never in the standard run (ADR-080). It is kept in the model's
    `unfold/`, keyed by panels.npz and finished.json: C27 takes 6 s the first time, then comes
    from the cache.
- **Per piece:**
  - the net size and the cut size (cm), and the net and cut areas;
  - the extra between the cut and net outlines, split over seam allowances and the hem in
    proportion to each edge's length times its allowance;
  - the ease along its seams (cm);
  - the vent openings.
- **Totals:**
  - the net surface;
  - plus the seam allowances, the hem, and the vent hoods and membranes, which together make
    the cut pieces;
  - plus what is left on the roll between the pieces (the export's simple layout; the machine
    nests tighter), which makes the fabric used (roll length × roll width).
- **In the 3D view (button "Unfold")**:
  - play/pause and a scrubber: on the cover, then pulled apart, then laid flat;
  - the camera moves from the cover to straight above the table;
  - on the table: the net outline (solid), the cut outline (dashed), the seam band (orange),
    the hem band (blue), the vent openings, and a label per piece (net and cut size);
  - below: the table per piece and the totals, with each as a share of the net surface.
- **S45:**
  - net 2.59 m², seam allowances 0.14, hem 0.18, vents 0.63, so 3.54 m² of cut pieces;
  - 3.73 m of roll, 5.59 m² of fabric.
- **C27:**
  - net 18.61 m², seam allowances 1.09 (6 %), hem 1.21 (6 %), vents 1.58 (8 %), so 22.50 m²
    of cut pieces (+21 %);
  - the export's layout uses 25.1 m of roll (37.6 m²). It leaves 15.1 m² between the pieces,
    which the machine's nesting reduces.


## ADR-086 — Start from a photo or a link: the configurator's sizes suggested, the customer checks

The owner (7 October): customers should be able to upload a photo of their furniture, or share
a link to its page, and get a proposal from that.

- **Where:** above the product choice in the configurator, the button "Have a photo or a link to
  your furniture?". Behind it:
  - **Photos:** up to 3. On a phone it opens the camera. JPG, PNG and WebP are accepted; an
    iPhone's HEIC is refused with the setting that avoids it.
  - **A link:** to the product page of a webshop.
- **The link is fetched safely** (`apps/api/coverapi/shop_suggest.py`). Only http and https.
  - **Public addresses only:** every host is resolved, and every address it has must be
    public: never private, loopback, link-local or the cloud metadata address (SSRF).
  - **Redirects:** at most 3, each one checked again.
  - **No second lookup:** the connection goes to the address that was checked.
  - **Limits:** `suggest.fetch_timeout_s` (8 s) and `suggest.fetch_max_bytes` (2 MB). A page
    must be HTML and an image an image.
- **What the page says** is read by the program itself: the title, the og/meta tags, a JSON-LD
  Product (name, image, sizes) and the text around the words for sizes (afmetingen, dimensions,
  Maße, cm …). The page's main image is fetched with the same rules.
- **The AI only reads.** Gemini Flash (`ai.vision_*`) gets the photos and/or those facts and
  says which configurator product it is, with its sizes in cm.
  - **The source of each size:** every size says whether it was written on the page, or only
    judged from a picture with a confidence.
  - **Written beats estimated:** a size written on the page wins over a picture.
  - **Cost:** about €0.001 per suggestion. It counts towards the month's budget (ADR-078), and
    when the budget is used up the customer gets a friendly "please choose by hand".
- **Checked by the program:**
  - the product must be one of the configurator's;
  - every size is held to its range in config/quote_products.json (clipped and flagged);
  - estimates, clipped sizes and missing ones are marked "please measure" and highlighted in
    the configurator until the customer touches them;
  - an existing cover that fits these sizes is offered as well (ADR-064).
- **Privacy:** nothing is stored. A photo lives only for the request, and at most
  `suggest.per_hour` (10) suggestions are made per visitor per hour (the Worker's x-client-ip).
  When the customer orders, the link and the summary go with the order (`source_url`,
  `source_summary`). The photos are then sent to `/api/shop/order/{token}/source` and kept as
  `order_sources/order-<id>-<n>.png` for the workshop.
- **First real try** (SUNS Terme, hello-suns.com):
  - **From the link:** "Breedte 197 cm, Diepte 77 cm, Hoogte 82.5 cm" was read off the page,
    giving a sun lounger of 197 × 77 × 82 cm with nothing to check. The AI noted that the back
    was raised, and that the flat seat is 39.5 cm high.
  - **From the photo alone:** 195 × 65 × 80 cm, all marked as estimates.
  - Each took about 9–11 s.

## ADR-087 — A photo alone starts from a comparable product found on the web

The owner (7 October), after trying photo uploads: "uploading works but little happens; we
should find a comparison via Google image search and use that as the basis."

- **What happened before.** A photo alone gave only estimates from the picture (all "please
  measure").
- **Google's reverse image search** (Cloud Vision web detection) cannot be used with the
  Gemini API key: it needs a service account.
- **Gemini with Google Search** works with the same key.
  - The AI identifies the furniture and searches for its product page, or the most similar
    products for sale, and reads their written sizes.
  - With `thinkingLevel: low` it answers in about 18 s, and the whole suggestion takes about
    40 s. At the default level it took over 90 s.
- **Real pages first.** The program tries to read each page itself (the safe fetcher of
  ADR-086). Many shops refuse robots (403/429) or build their sizes in JavaScript; then the
  sizes the search read from that page are used.
- **Never the customer's own sizes.** The proposal names the comparable product with its link,
  and every field it gave is flagged "comparable" and must be checked.
- **Cost:** about €0.04 per photo (the search fee `suggest.search_eur`, to confirm, plus the
  tokens), recorded in the cost ledger (ADR-078). Tests fake the search, so they make no paid
  calls.
- **AVIF** images are accepted: many shops serve them, SUNS among them.
- **Tried for real** on a SUNS lounge photo: Westwing "Naomi" 2-seater module, a sofa
  120 × 100 cm, back 70 cm, front 40 cm, all flagged.

## ADR-088 — Air vents shown on the outside of L, U and C shapes

The owner (7 October) on C23: "why are two vents on the inside? It is rejected because we do
not see two of them." Then: "it is like this on many more models."

- **The cause.** `vents_3d` (ADR-073) turned each vent's normal "away from the middle of the
  cover". On the inner walls of an L, U or C shape that direction points into the cover, so the
  vent was drawn 4 mm inside it and could not be seen. The vents themselves (in the cut file)
  were right; only the 3D picture was wrong.
- **The fix.** Out is where no cover lies overhead. A point 50 mm beside the wall is tested
  against the cover's footprint seen from above; if the cover covers it, the normal is turned
  round. This is right for any plan shape.
- **Remade for every model:** 39 drawing covers had 2 to 5 vents pointing inwards (the C, L and
  S series and the corner sets). The old files are kept in
  cover-data/backup-vents-2026-10-07.
- **Test:** an L-shaped cover's six vents all face the open side.

## ADR-089 — Arrangements: furniture placed together, one cover over the whole

The owner (7 October): "put products together, e.g. the SUNS Portofino 2-seater with its
chaise longue. We first place the products in the arrangement we want, then make a cover, so
we can also make larger covers for fixed arrangements."

- **An arrangement is an ordinary model** `arr-<name>`. `coverengine/arrange.py` places each
  member's `model.glb` (mirror, turn about z, move to its plan position, stand on the ground),
  joins them into one mesh (`arrangement.glb`, mm, Z up, centred) and the normal job imports
  and builds it: import → hull → cut → flatten → export. So the arrangement has everything a
  model has (3D, size drawing, cut files, revisions, Unfold, the Desk) without new code paths.
  It is marked furniture at once (`kind.json` confirmed).
- **`arrangement.json`** keeps the name, the members with their places and, per member, the
  hash, revision and size of the `model.glb` it was made from. The list and the page say when a
  member changed since ("stale"): build again. Nesting arrangements is refused.
- **Placing** happens in the studio page **Arrangements**: a top view of each member's footprint
  (from the API, the union of its triangles seen from above), drag on a grid, turn in steps,
  mirror, and **Snap** (one member against another's side, lined up at the back, front or middle;
  computed by the engine so the page and the cover agree). New settings `arrange.*`: grid,
  turn step, gap, and the hull for arrangements.
- **Hull: box, 8 pieces** (`arrange.hull_top`, `arrange.box_pieces`), as the SUNS sets. The
  tensioned route failed at the cut on the Portofino corner ("not a disk"); kept for later.
- **Tried for real** on copies of the two Portofino models (never the live data): the corner
  is 346.0 × 201.8 × 84.6 cm, 8 pieces and 4 vents, built in 25 s. Open points, in
  docs/plans/arrangements.md: the box's top spans the L as one slope and is 1658 mm in its
  narrowest direction, over the roll (the size drawing warns); no vent on the low back of the
  chaise longue; one cover or several that zip together; a top that follows each member.
- **Better later:** a top per member joined by seams (an L-shaped top), and zip-together covers.

## ADR-090 — Length and depth of the sloped-box drawing covers read from the size arrows

The owner (7 October) on drawing-s40: "x and y are swapped; this happens more often. Check how
this can happen and how to fix it."

- **How it happened.** These covers were read by the AI earlier (ADR-046). In a 3D view it
  had to guess which size is the length (along the back) and which the depth (along the side
  that shows the slope):
  - S40 and S31 had them swapped;
  - S36 took the 30 cm strip for the depth;
  - S29 took the front height (72) for the depth.
- **Read, not guessed** (`scripts/drawing_axes_check.py`).
  - The size arrows (ADR-075) tell each size's direction: one of the two isometric axes
    (±30°), or upright.
  - The flat strip on top is sized along the depth, so the axis carrying the strip's size is
    the depth axis. The longest size along it is the depth, and the longest along the other
    axis is the length.
  - A first rule, "from the back height to the front height", failed on S41, where the front
    height is drawn at another corner.
- **Fixed** (new revisions; backups in cover-data/backup-drawing-s*-axes-2026-10-07):

  | Cover | Before | After |
  |---|---|---|
  | S40 | 105 × 92 | 92 × 105 |
  | S31 | 105 × 95 | 95 × 105 |
  | S36 | 115 × 30, no strip | 115 × 112, strip 30 |
  | S29 | 95 × 72 | 95 × 95 |

- **Checked:** 12 sloped-box drawings with readable size arrows; the other 8 were right.
  Drawings without arrows or without a strip cannot be checked this way.

## ADR-091 — The workshop's product list linked to the drawing covers

The owner (7 October): "we have an Excel sheet in which all products are linked to the drawings
we uploaded; please link these products to the right drawings so we can sort easily", "I'd like
to upload it", "it has to be a zip".

- **Upload** at the Desk ("Upload product list (Excel)", `POST /api/desk-products`): an .xlsx
  or .csv, or a .zip holding them. An old .xls is refused with "save it as .xlsx". Editors and
  the Desk's approvers may upload. The studio's drawings-zip button (`POST /api/references`)
  hands a zip that holds a sheet and no drawings to the same import, with the same summary;
  zips with drawings behave as before.
- **A zip is read with care:** one entry with an absolute path or ".." refuses the whole zip;
  at most `products.max_files` entries and `products.max_bytes` unpacked; __MACOSX and hidden
  files are skipped. PDFs in it are only listed and matched to existing drawing covers by
  code ("PDFs in the zip: N, matched: M, new: …"); no model is made from them.
- **Read by content, not by header names.** Every sheet's header is its first row with two
  text cells. The link column is the one whose values match the most drawing covers, by
  - the cover's code or folder name (S40, C23);
  - the order number on its PDF ("Cover 105", cached in `order_number.txt`);
  - a code inside a combined name: "cover 39 & 46 - L1 & L5 mirror" answers to L5, while L1
    stays with drawing-l1, which has it as its own code.

  Matching ignores case, spaces, dashes and leading zeros. A person may pick another column
  and apply again. The description is the column with the longest text; a short number
  column ("Cover 1") is the second label. The owner's sheet heads its description column
  with a fabric colour, so header names could not be trusted.
- **SUNS models** are linked from the description: its families ("Portofino/ Aspen/ Kota",
  words that occur in SUNS names and are not type words) and its type (daybed, chaise "CL",
  lounge chair, N-seater including "2,5" and "searter", bench, corner/"hoek"/L-part,
  table/side table/dining table, hocker, middle, moon).
  - A family and a type in common, the same shape (angled, moon), and no left/right
    crossing: **linked**.
  - A family in common, but the description names no type ("lounge set normal"):
    **suggested**, never a link, and tables are not suggested for a lounge set.
- **Stored** as `products.json` per drawing cover (the rows, the labels, the SUNS links and
  suggestions) and `drawings.json` per linked SUNS model. Uploading again replaces both;
  covers no longer in the list lose theirs. Every upload is kept in `products/` in the data
  folder.
- **At the Desk:** the products are in the list row, in the search and in a new sort (needs a
  person first, code, product, status, AI score), and in a "Products" table on the card. A
  SUNS card shows "Drawings for this product", linked and suggested.
- **The owner's sheet** (namecode.xlsx, 138 rows, on a copy of the data): linked through
  "Code", 121 rows on all 115 drawing covers. The 17 rows not linked are S49–S62 and D8–D10,
  drawings not uploaded yet. Codes D5, S21, S22, S23 and S24 each carry two products (the
  Blocchi and Vento blocks share their codes), shown as "one code, two products". SUNS: 60
  models linked, 27 more only suggested.
- **Better later:** a person confirms or removes a suggested SUNS link on the card; SUNS
  names that differ in spelling ("Victoria" vs "vittoria") need an alias list.

## ADR-092 — A photo alone: recognise the brand and model, compare pictures, drop what is unlike

The owner (7 October) uploaded a photo on the preview configurator: what it recognised "made no
sense", while Google Lens found far better matches. Then: recognising the brand and model "is
really a good idea"; show it to the customer.

- **The cause** (ADR-087's flow, reproduced on 12 SUNS photos and renders; the owner's photo
  itself is not kept, by design):
  - one Gemini call looked at the photo, guessed a famous design (Kettal Cala, Tribù, Talenti,
    Vondom, Knoll) and searched for that name: a search by words, not by image;
  - the program took the first page that had sizes, without checking it looked like the photo;
  - the final AI then wrote "your Kettal CALA sofa". A round SUNS Marolo daybed became a
    "round dining set" from a Talenti page; a Vivaro sofa an "Atmosphera Loto module".
- **Now, for a photo alone** (`apps/api/coverapi/shop_suggest.py`, `find_comparable`):
  1. **Identify** (vision, JSON): product type, brand and model with an honest confidence,
     materials, colours, distinctive features, estimated sizes, and up to `suggest.queries`
     search queries by look (no brand).
  2. **Two searches side by side** (Gemini with Google Search): the recognised brand and model
     (the manufacturer's page first), and the look alone, so a wrong brand guess cannot steer
     everything. Results are taken in turns, at most `suggest.search_pages`.
  3. **Each result made ready** in parallel: its page read by the safe fetcher (or the sizes the
     search read, when a shop refuses robots) and its main picture, `suggest.compare_px` small.
  4. **Compare** (one vision call): the customer's photo beside every picture; per candidate
     "the same product and size variant?" and a similarity 0–1 for a cover's shape.
  5. **The program decides:** the same product at `suggest.same_min` or more is **recognised**
     (shown as "Herkend: <name>" with its link, its sizes the start, flagged to check); else
     the most alike with sizes at `suggest.similar_min` or more is a **comparable** start (as
     before); else **nothing is taken over** and the photo's own estimates are asked to measure.
     A page without a picture counts only if it carries the brand and model recognised with
     `suggest.brand_min` confidence.
  6. The final AI is told whether the page is "the same product" or "a SIMILAR product" and may
     never name a similar product's brand as the customer's.
- **Measured** on 6 photos from hello-suns.com (before → after):
  - Basta low bar table (SUNS logo visible): found → **recognised "SUNS Basta low bar tafel"**,
    256.5 × 96 × 95 cm;
  - Marolo daybed: "round dining set 180 cm from Talenti Slam" → a sofa from the photo's own
    estimates (the Talenti pages judged unlike: 0.65);
  - Vivaro sofa: "Atmosphera Loto module, 180 cm" → estimates (Talenti Moon judged 0.5);
  - Venosa, Blocchi: "Vondom Suave", "Soho Noelle" → the photo's own estimates (the best
    results judged 0.7 and 0.55 alike);
  - Dolce chair: 502 (no answer) → estimates; Tosca render: "your Kettal CALA" → "4SO Calma"
    as a comparable (0.8), 214 × 81 cm against the real 231 × 85.
  - Each takes 30–60 s (was 17–78 s); the AI work now runs off the event loop, so the rest of
    the app keeps answering meanwhile (before, one suggestion blocked the API for a minute).
- **The limit:** a search by words rarely finds a brand like SUNS from the look alone. Google
  Lens finds it because it searches by image. **Ready but off:** `suggest.reverse_search`
  (Google Cloud Vision web detection, the engine behind Lens's visual matches): its pages that
  show the very picture come first and its best-guess label becomes the first query. It needs an
  API key for the Cloud Vision API (`GOOGLE_VISION_API_KEY` in deploy/.env); question 68.
- **Cost** (ADR-078, every call in the ledger as "suggest identify / search / compare"): about
  €0.035 per photo, measured (4 Flash calls ≈ €0.006, 1–2 searches with about 1.3 queries each at
  `suggest.search_query_eur`, Google's fee per search query for Gemini 3, to confirm on the
  bill). If Google bills per grounded request instead (€0.03 each), about €0.07.
- **Tests** fake every paid call: an autouse fixture fails a test that would call Gemini, the
  search or the image search for real; the decisions are tested on faked identify, searches,
  pictures and comparison scores.

## ADR-093 — Air vents only on the outside, never on an inner wall

> **Superseded by the owner's answer of 9 Oct 2026** (QUESTIONS 71, ADR-110): on 7 Oct he
> meant vents drawn *inside the fabric* (the 3D display bug, ADR-088), not the inner walls of an
> L. Vents now go round every side, the front walls in the inner corner of L, U and C covers
> included (`features.vent_inner_walls: true`). The inner-wall test below stays: it finds those
> walls for the switch and for the checks.

Owner, 7 Oct 2026 (C23): "er horen nooit airvents aan de binnenkant te zitten, alleen aan de
buitenkant". The drawing of C23 points two of its six vents at the inner walls of the L; the
owner's rule wins over the drawing's positions, the drawing's number still wins (ADR-075), so
all six now go on the outer walls.

- A skirt piece is on an inner wall when half of it or more lies `features.vent_inner_mm`
  (300 mm) or more inside the footprint's convex hull (`finish.inner_skirts`, from
  `panels.npz`). This catches the inner walls of L, U and C shapes and the concave front of a
  curved sofa, and leaves round and D-shaped pieces alone (their walls lie on the hull).
- `cover export` and `vents.json` both use it, so the cut file and the 3D view agree.
- Swept over all models: 43 covers had vents on inner walls and were exported again.

## ADR-094 — Route A fits the heights of a corner sofa to the drawing's 3D view (drawings plan, phase 4)

The owner rejected C4, C8, C9, C10, C31 and S33 (and C3, C29, C30) on shape. These drawings show
a top view and a shaded 3D picture, and no front or side view. With no elevation to cut it, the
views reader (ADR-075) stood the top view straight up into a flat block. The block's outline
covers the 3D view about 97 %, so the IoU check passed a cover that is plainly wrong: these
sofas' backs are higher than their seats, and their arms end in a hip.

- **The shape family** (`coverengine/drawing_isofit.py`):
  - the top view's footprint, its scale set by the written lengths;
  - the back edge: the longest run of the outline on the convex hull, without the arms' ends;
  - over it, the height by the distance from the back edge (plan_profile, ADR-084): a flat
    strip at the back height, then a straight slope to the front height at the arm's depth;
  - an arm may end lower: the top falls to the end wall over the hip's length;
  - seams where the arms' slopes meet (the corner's bisector), walls split at the outline's
    corners, a piece wider than the roll cut along its length.
- **Only written sizes.**
  - Back, front, strip, end height and hip length are each a size written on the drawing, a
    different one each: C31 writes 40.6 for its front, so 40.6 is not also its strip.
  - Vent counts are no sizes: "8 Air Pockets" was being read as 8 in = 20.3 cm.
  - The footprint's lengths along the back and its depth must be written (2/3 of them).
- **The 3D view decides.**
  - Each candidate is drawn as the CAD program draws its 3D view: an isometric projection from
    one of the four corners, a z-buffer in numpy.
  - Its silhouette is compared with the picture's transparency mask (IoU, the owner's
    `drawing.min_iou` 0.85, unchanged).
  - Its creases (faces meeting at more than 9.5°) are compared with the picture's shading steps,
    as a soft F-score of distances.
  - The heights are found group after group: back, then strip and front, then the arm ends.
    This takes 2-45 s per drawing.
  - The fit is taken only when its creases score at least `drawing.isofit_min_crease` (0.65) and
    it beats the views' shape by `isofit_min_gain`. This is the guard the IoU alone could not
    give: S27's wrong fit had IoU 0.91 and creases 0.19.
  - Drawings with real elevations keep the views reader: D5, D6, S21, S26, S38, S39 (checked).
- **Results** (staging builds in out/drawings/phase4/, compare sheets in
  out/drawings/phase4/compare/):
  - every written height came back for C4, C8, C9, C10 and S33;
  - C31 keeps the written 33 cm strip, although its picture suggests nearer 40 along the arms;
  - creases match 0.77-0.91 against 0.35-0.72 for the live covers and the block.
- **Water.** The drawings draw the back strip flat, and the hull's water check flags it, as it
  does on the live C8 and C27. `drawing.isofit_strip_fall_deg` (0, as drawn) tilts it towards
  the seat; its value is the owner's to choose.
- **Not covered:**
  - wireframe drawings (no picture to compare with): the next step, reading the 3D view's own
    vector lines;
  - curved footprints without a top view (S32, C28, S43, S44, S25);
  - shapes outside the family: S19's arm block, S27's chair. These stay with the views reader or
    "needs a person".
- **Better alternative, not built:** fit continuous heights and snap them to written sizes
  afterwards; the discrete search is simpler, deterministic and cannot invent a size.

## ADR-095 — An arrangement's cover follows its pieces; the plan is chosen before building

The owner, 7 Oct 2026, on `arr-portofino-chaise-2seater` (a chaise longue and a 2-seater as an
L): "you drew a sloping side instead of an L shape with a sharp corner. When generating these
big covers the cover must follow the product and not draw diagonal lines. Think about an
intermediate step where we can choose, so this doesn't go wrong automatically."

- **Cause.** Not the drape hull: arrangements are built as box covers (ADR-089), and the box of
  ADR-038 is an intersection of half-spaces, so always convex. Growing it to 8 pieces added, as
  the face that took away the most room, a near-vertical wall (normal 0.41, -0.91) straight
  across the L's open corner; the top was one slope over the whole L (1.66 m across, over the
  roll). No setting of the convex box can make an inner corner.
- **The plan comes first** (`coverengine/hull/plan.py`). Each member's plan rectangle (stored
  in arrangement.json as `plan_mm`; older files: from the members' sizes); sides of neighbours
  within `arrange.align_mm` (30) lined up outward (the chaise's back is 5 mm behind the
  sofa's: no 5 mm jog); gaps closed up to the arrangement's gap plus `arrange.close_mm` (50);
  offset by the clearance with mitred corners. Walls stand straight down on every edge, the
  inner corner is a right angle, corner seams at every corner.
- **The top per member.** Flat faces tangent to that member only, sloping down to its own front
  (`arrange.top_slopes: front`; `any` also allows back and side slopes, which give diagonal
  hip seams): the flat top, then the slope that takes away the most room, at most
  `arrange.top_faces` (2), each worth `arrange.top_gain_pct` (5 %) of the room. A face flatter
  than `hull.min_slope_deg` is tilted towards an outside edge of the member; neighbours' faces
  that agree within `align_mm` become one plane (the Portofino's back strip is one 300 x 3480
  piece). Each member's part of the plan is pushed up, cut by its faces (manifold3d), and the
  parts are joined: where the chaise's long slope is higher than the sofa's short one, the
  chaise's inner wall runs on up as a step. Rule 12 is checked on a grid (`arrange.cell_mm`).
- **Pieces.** Every flat face is a piece (`hull_parts.npy`, so the cut keeps them; slivers under
  `seams.min_piece_width_mm` are folded into a neighbour). A top wider than the roll is cut into
  strips whose seams run downhill (the "one rectangle" plan of the Portofino: 3 strips of 116
  cm).
- **Chosen before building.** The Arrangements page asks `POST /api/arrangements/footprints`
  and shows three top views with their sizes in cm and the floor they cover that no piece
  stands on: **Follow the products (sharp corners)** (default, `arrange.footprint: follow`),
  **One rectangle around everything** (`box`) and **Smoothed outline** (`smooth`, the convex
  box of ADR-089). The choice is stored in arrangement.json (`footprint`), which is now an
  input of the hull step; choosing another plan for a built arrangement builds it again.
- **Learned** (ADR-055): an AI lesson for box covers, the audit's new `plan` check (an
  arrangement meant to follow its pieces may not cover more than 0.02 m2 of empty floor), and
  tests: an L of three boxes gives an L with its corner within 2 mm of the members' corner, no
  outline point more than 3 mm outside the members plus clearance, walls vertical, pieces on the
  roll, vents off the inner walls, identical files on a second run.
- **Portofino, staging** (out/arrangements/, pictures in out/arrangements/compare/): 348.0 x
  204.3 cm, 9 pieces, widest in its narrow direction 137.8 cm with allowances (the chaise's
  slope; was a 166 cm top), 7 vents, all on outer walls (back 3, left 2, the chaise's front 1,
  the sofa's end 1); the two inner walls get none. `arr-portofino-2-c`, the mirror image, the
  same. Both live arrangements are to be rebuilt (they have no `footprint` yet, so they get the
  default, follow).
- **Better later:** each member's own footprint rather than its plan rectangle (a rounded arm
  is covered square today), and tops that blend across members instead of a step.

Owner's answers (7 Oct 2026, QUESTIONS 69): the step where a longer top meets a shorter one is
right (no blending); covering each piece as its plan rectangle is fine; an arrangement gets one
cover over the whole, never covers zipped together (closes that question from ADR-089).

**Side slopes (Rens, 15 Oct 2026, QUESTIONS 59: "ja, ook naar de zijkanten").** New key
`arrange.side_slopes: true` (`top_slopes` stays `front`: no slopes to the back). For
arrangements only (`arr-*`; a model built from its parts' plan, `plan_members.json`, keeps its
approved roofs). After the front faces, each member's roof may also slope down to each of its
*outside* sides (no other member within 2 x clearance + `align_mm` beyond it), never to a side
a neighbour stands against, so no valley forms between two members (rule 12). The side face
keeps the side a wall at least as high as the member's front: either a face resting on the
furniture (an arm's top) that meets the side line above that height, or the face hinged on
the side line at exactly that height and tipped up until it clears the furniture
(`plan._hinged`: the least tip angle that clears, sampled from flat to upright and halved
between two samples; Codex's review showed a fixed-point solution giving up on valid faces and
refusing a low point just beyond the side line); a first version without this let the chaise's side face run down to the hem
and its whole left wall vanished, rejected. A side is added when it takes away
`top_gain_pct` (5 %) of the room, each side weighed against the same front-only top, so two
outside sides of a member come out alike; a hip seam runs where a side face meets the front
slope. Water still runs off (the drainage grid). Tests: engine/tests/test_arrange_sides.py.
The live Portofino arrangements rebuilt in staging (out/q59/, checked twice, compare pictures,
Codex's second look): unchanged. The Portofino has no arms; the chaise's best wall-keeping side
face takes away 4.1 % (< 5 %), and the 2-seater's back cushions reach its outside end. Their
hull pieces are identical and cut.dxf differs only in its revision label, so nothing was
replaced live. A set with high arms or a back lower at its ends gets the side slopes.

## ADR-096 — Pictures at the Desk: the approver attaches and marks them himself

The owner (7 October): "make an option so Rens can add a screenshot himself". Until now a
picture with an arrow or circle went by mail to Rick, who passed it on; it was not kept with the
cover, and the learning step never saw it.

- **Where:** the Reject dialog, and a new **Comment** (key `c`, action `note`): words and
  pictures in the history, the status unchanged. A correction (`POST /api/desk/{id}/correct`)
  takes pictures too through the API; its form has no picture buttons yet.
- **Sources** (apps/web/src/DeskPictures.tsx): "Snapshot 3D" (the viewer renders and reads its
  canvas in the same task, so `preserveDrawingBuffer` and its per-frame cost are not needed),
  "Snapshot drawing" (the drawing page shown), "Upload…" (JPG, PNG, WebP), drag-and-drop and
  Ctrl+V.
- **Marking:** every picture opens a small editor: red arrows, circles (ellipses) and freehand
  lines, Undo (also Ctrl+Z), Clear. The marked picture is drawn into a canvas at the picture's
  own size and sent as PNG.
- **Storage:** `POST /api/desk/{id}/pictures` (multipart, only `desk.approvers` or an admin, as
  for approve/reject) checks each file with Pillow (JPEG, PNG or WebP only; a picture that
  unpacks to an enormous size is refused), turns it upright by its EXIF, re-encodes it as a new
  PNG with no metadata (EXIF, text, ICC dropped), scales it to at most
  `desk.picture_max_side_px` (2400), and keeps it as `models/<id>/desk/<yyyymmdd-hhmmss>-<n>.png`.
  Limits: `desk.picture_max_mb` (15) per picture, `desk.pictures_max` (8) per request and per
  action. The action then names them (`pictures`); names that are not this model's pictures
  are refused.
- **Served** by the existing logged-in file route, `/api/models/{id}/files/desk/<name>`; only
  names the Desk made itself (a fixed pattern) are served from desk/, so no path leads out.
- **Linked:** the history entry in desk.json carries `pictures` (file names), the card shows
  them as thumbnails (click to enlarge). learning/desk.jsonl adds `picture_paths` (relative to
  the data folder), and so do a correction's feedback.json entry and its test case
  (learning/cases/); `scripts/learned_check.py` lists them under a case "to do by hand". A
  future fix, or Claude, opens them from there (ADR-082).
- **Uploaded once:** the pictures go up when Reject or Save comment is pressed; if the action
  is then refused (no reason given), the second try reuses them.
- **Not yet:** a picture uploaded for an action that never succeeds (refused, then cancelled)
  stays in desk/ unlinked; it costs little and a clean-up can come later. Undo takes back the
  history entry, not its files.

**8 October 2026: Rens could not add a picture on live (v1.23.0).** The server logs showed his
rejects (reasons and words) but not one picture upload. The owner learned that it failed in
Microsoft Edge and worked in another browser. Checked in real Chromium, Edge 154, WebKit and
Firefox, 1440 and 820 px wide, on copies of C2 and C18 with the v1.23.0 build:

- **The cause found: the Pictures row was below the screen.** `.d-card` had `overflow: hidden`.
  That made the card its own scroll container, so the action bar did not stick to the window,
  and the open Reject dialog grew downwards past the bottom edge. Focusing the text box
  scrolled only that far. With a 900 px window the picture buttons sat 0 to 30 px above the
  edge, under the browser's own bars. Rens chose a reason, wrote his words and pressed Reject
  without ever seeing the buttons. The size of the window decides this, not the browser
  engine, which fits "Edge failed, another browser worked". With the window scrolled to the
  buttons, all five sources worked in all four browsers, Edge too.
- **Fixed** (apps/web: desk.css, Desk.tsx):
  - The card clips with `overflow: clip`, which is not a scroll container, so the bar sticks
    again.
  - The bar is at most the window's height and scrolls inside itself.
  - Opening Reject or Comment scrolls the whole dialog into view.
  - The Pictures row now comes before the text box, so it is seen before Reject is pressed.
- **Never silent** (DeskPictures.tsx, Viewer.tsx). Every step that a browser can refuse now
  says so in the Pictures block, with "use Chrome or Firefox, or attach a screenshot with
  Upload…":
  - a canvas that cannot be read back (privacy settings, policies): checked when the block
    opens;
  - an empty or refused 3D copy;
  - a picture that cannot be read;
  - a marked picture that cannot be saved (toBlob, then toDataURL as a second way);
  - an upload the server refuses.
- **WebGL off:**
  - A browser without WebGL (graphics acceleration off, blocked by a policy; Firefox in the
    test container) used to blank the whole page. The viewer now catches it, explains it on
    the card, and the 3D snapshot says why it cannot copy the view.
  - Large photos are drawn at most `desk.picture_max_side_px` on a side, because Safari on an
    iPad refuses very large canvases.
  - A photo with no file type (some Windows set-ups) is taken by its name; the server checks
    it anyway.
- **"Correct this cover"** has the same Pictures block. A correction sends its pictures, and
  they reach the test case. Only the tray of the open dialog listens to Ctrl+V.
- **Test:** `apps/web/e2e/desk_pictures.py` runs this per browser (chromium, msedge, webkit,
  firefox) and width. It checks:
  - the Pictures row is on the screen without scrolling;
  - every source makes a marked picture, and a POST to `.../pictures` happens;
  - the reject names the pictures, and a correction carries one;
  - the thumbnails load;
  - a browser that blocks canvas reading gets the message.

  Run against v1.23.0 it fails on the first point. Edge comes from a local image with
  `playwright install msedge`.

## ADR-097 — C- and U-shaped drawing covers in the pieces the drawing draws; no slivers

The owner (7 Oct 2026, twice): "some drawings like C27 still have too many panels"; "look very
carefully at C27 again". Live C27 had 25 pieces (13 on top, 12 walls), and C26 20; both also
broke the rules: C27 stretched 3.5 % and C26 5.4 % (limit `fabric.max_allowed_stretch_pct` 2 %),
with up to 8.5 mm of ease on a seam.

**Survey** (all 115 drawing covers against their drawings; staging out/drawings/fewer/): the box
family and the views/isofit covers have the panels their drawings draw, or need a split only
because two halves together are wider than the roll (D1, D2, D6: 2 x 971, 895, 858 mm). The
extra pieces were on the plan-profile covers (C26, C27) and as slivers (S43, S44).

What was wrong, and the fix (each general, not per model):
- **A drawn seam cut the other arm** (`plan_profile._cuts`). A seam line square to the back
  edge ran 4 m across the plan, so on a C it also cut the opposite arm: C27's extra seam across
  the middle of the top. A seam now runs from the back edge to the first outline it meets.
- **The noses could not lie flat** (`plan_profile.height_edge`, `zof`). The heights were the
  profile at the distance from the back edge: where the back edge curls round a nose tighter
  than the cover is deep, the slope got a ridge (the nearest back point jumps), and where the
  cover is deeper than the drawn depth the slope ran out flat. Both join surfaces along a curve
  no flat piece can follow. Now the heights are measured from the back edge without its tightly
  curled ends (a cone past them), and past the last crease the slope is spread over what is left
  to the front edge, so it reaches the front height on the whole front edge. C27 0.65 %, C26
  0.62 %.
- **The hidden back wall is one band** (`plan_profile.build(..., wall_max_mm)`). The outer wall
  is behind the cover on every view; it was a piece per section. It is now joined into runs no
  longer than `seams.max_skirt_panel_mm`, cut only at drawn seams so its seams meet the top's.
  The inner walls keep a piece per section: the drawings draw those lines.
- **Slivers** (`drawn_merge.absorb_slivers`). A piece narrower than `seams.min_piece_width_mm`
  flattened goes into the neighbour it shares the longest edge with, when the two lie flat
  within `drawn.merge_max_stretch_pct` and fit the roll, on every route-A cover, whoever made the
  seams. The flattening for this measure now leaves out triangles without area and turns all
  triangles one way: S43's half-millimetre strips made the solver blow up, so they were never
  joined.
- Kept as drawn: the back strip's crease (a strip joined to its slope does not lie flat: the
  crease is curved and the two sides curve differently) and the drawn seams across the top.

**Results**, each checked twice — `cover audit` and the engine's warnings, and a separate
re-measure from the exported files (`scripts/fewer_check.py`: widths from cut.dxf, both sides
of every seam and its 3D length, flat against 3D area, stretch flattened again with ARAP, the
vents' count and that none is on an inner wall) — and by looking at the compare sheets
(`scripts/fewer_compare.py`, out/drawings/fewer/compare/):

| Cover | Pieces before | after | Worst stretch before → after | Largest seam ease |
|---|---|---|---|---|
| C27 | 25 | 20 | 3.54 → 0.65 % | 8.5 → 2.3 mm |
| C26 | 20 | 16 | 5.37 → 0.62 % | 6.1 → 2.2 mm |
| S43 | 9 | 5 | 0 → 0 % | — |
| S44 | 10 | 9 | 0 → 0 % | — |

The live covers of C26, C27 and S43 fail `cover audit` (pieces); the new ones pass. Vent counts
kept (10, 8, 4, 4), none on an inner wall.

- **Not fixed:** C28 (the mirror of C27) is not read by route A: its drawing has the heights
  and depth without the words "Height", "Front Height", "Depth". drawing-cover-39-46-l1-l5-mirror
  has 7,846 pieces from a broken AI shape (6 Oct) and route A cannot read its drawing (no top
  view); it is the same drawing as drawing-l1 (10 pieces).
- **For the owner** (open questions): is the flat back strip sewn as its own piece (as drawn) or
  folded from the slope? Is the hidden back wall one band (as now) or a piece per section?

## ADR-098 — Prices and costing: a versioned price set per channel, shaped for Odoo

The owner (7–8 Oct 2026): "an admin page where I easily fill in prices and make costings; later
it must link to our Odoo in Indonesia." A fixed IDR→EUR rate entered by hand, both currencies
shown; two channels (B2C webshop, B2B Sunsit and dealers) with their own price lists; shipping,
duties and packaging as lines of their own; all admins may edit. Plan and Odoo mapping:
docs/plans/prices-costing.md; handbook: docs/handbook/prices.md.

- **One price set**, a JSON document (`coverengine/costing.py`): exchange, fabrics, components,
  labour (rate and operations), channels (extras, method, rounding, VAT, fixed prices). Every
  component and operation is counted `per` a fact of the cover (cover, piece, seam_m, hem_m,
  vent, cord_m, elastic_m, fabric_m, balloon, frame), so a bill of materials follows from the
  facts and the owner can add lines without code.
- **The facts come from the real cut pieces:** `finished.json` (panels, seam and hem edges,
  vent hoods, the cut plan's roll length) and `hull.json` (balloons, frame); the configurator's
  proposal gives the same facts. Metres of fabric = the cut plan's roll length + waste, scaled
  when a fabric's roll is narrower.
- **Prices:** markup (base × (1 + p)) or margin (base ÷ (1 − p)) on the landed cost (cost +
  extras, the default) or on cost alone; rounded up to .95 / .99 / whole / 5 / 10 on the shown
  price (incl. VAT for B2C, ex VAT for B2B); a fixed price per product wins in its channel.
  Duties as a % are taken of cost + shipping (customs value).
- **Versioned in app.db**, not the yaml: table `price_sets` (append only; a rollback is a new
  version pointing at the old one) and the setting `prices_draft`. Draft → preview (every
  price that moves) → publish; audit log entries `prices published` and `prices rolled back`.
  Until the first publish the set is the yaml defaults with the old Shop settings prices on
  top, so nothing changes in the shop until the owner publishes. "Indicative" is part of the
  set.
- **The yaml keeps the defaults:** `quote.minutes_base` is split into `minutes_cut_setup`,
  `minutes_pack` and `minutes_per_hem_m`; new `fabric_name`, `elastic_eur_per_m`,
  `b2b_markup_pct`, `b2c_/b2b_rounding`, `b2c_/b2b_shipping_eur`, `duties_pct`, `packaging_eur`,
  `idr_per_eur`, `idr_rate_date` (all to confirm).
- **Who reads it:** the shop's quote, the rain check's upsell, the support price, the public
  API and `shop/info`'s "indicative" (`prices.current(auth)`). The Shop settings' prices block
  is hidden (it only feeds the defaults now).
- **A fix on the way:** the configurator counted the table balloons in the cover's own cost and
  then charged them again as the support upsell. The balloons are now only sold next to the
  cover (accessory price per channel).
- **Rights:** admins edit and publish; editors see prices and costings (`#/prices`); viewers
  get 403.
- **Odoo seam:** `coverapi/odoo.py` maps the set and a cover's costing onto res.currency.rate,
  product.template, mrp.bom (+ lines and operations), mrp.workcenter and product.pricelist,
  with external ids `cover_studio.<code>`. No connection; step 2 uses Odoo's XML-RPC/JSON-RPC
  against their own server.
- **A page that explains itself** (owner, 8 Oct: "very basic, add more information so I know
  what I fill in"): an intro per tab, a unit and a help line per field, "terms explained"
  that open on a tap (tablet: no hovering), and a "placeholder — please confirm" mark with a
  counter. A field is a placeholder while its yaml key says "to confirm", its value equals the
  yaml default (`costing.FIELD_KEYS`, `placeholders()`) and it is not in the set's
  `confirmed` list ("keep this value"). Live examples cost one real cover with the unsaved
  numbers: `POST /api/prices/check` {data, model | product + sizes} returns the errors, the
  placeholders and that costing; nothing is saved. The example is the middle (by fabric metres)
  of the catalogue's 2-seaters, or any cover the owner picks. The maths did not change.
- **Better later:** price per colour/quality in the configurator, separate workcenters, shipping
  per country and box size, duties per HS code, the B2B storefront.

## ADR-099 — A gentle fold is no seam: box faces that lie flat together are one piece

Rens (approver), 8 October 2026, on 11 SUNS box covers (bar chairs Virenze and Fishbone, bar
tables 80x80 HPL and teak, chair Vittoria, corners Aspen, Avero and Emar, Monte Vari dining
table, Sato bench, Vento daybed): "crossed-out panels can become one panel"; Monte Vari: "2
panels on the top instead of 4".

- **Why the engine split them.** Not the roll, not the stretch: every crossed pair was two flat
  box faces meeting at a gentle fold. A flat table or stool top is drained into a gable of two
  faces at `hull.min_slope_deg` each (rule 12), a 10 degree fold; the box's greedy face choice
  added near-parallel faces (3 to 7 degrees: Vittoria, Fishbone, Monte Vari, Sato). Each flat
  face was its own piece (ADR-038), and joining was only done for slivers or on request
  (`seams.fold_merge`, ADR-055).
- **The rule.** `seams.fold_join_max_deg` (15, to confirm): neighbouring faces on the same side
  (both top or both skirt) whose fold is at most this are one piece with a FOLD pen line, the
  gentlest fold first, while the piece fits the roll (`roll.usable_width_mm` minus the
  allowances) and is no longer than the longest piece. Two flat faces unfold exactly (0 %
  stretch), so the fit does not change; the shape of the cover does not change either.
  Measured on the rejected covers: every crossed pair is 3 to 10 degrees; the pairs Rens left
  alone are 23 degrees and more (Vittoria's back slope 33, the daybed's front halves 23).
  Monte Vari: the two 7 degree pairs join first, then the 10 degree ridge would make the top
  1.6 m wide, over the roll, so it stays a seam: 2 top pieces, as Rens asked.
- **Check.** The audit's new *gentle folds* check fails a box cover with a seam between two
  same-side pieces at a fold of at most the limit whose widths together fit the roll. Tests in
  `engine/tests/test_facets.py`; an AI lesson for box covers.
- **Sweep (8 Oct, live covers, read only).** 148 box covers get fewer pieces when rebuilt
  (mostly one or two fewer: gable tops of tables, stools and hockers); the list is in the
  rejections run's `sweep.json`. Covers are not rebuilt by this change; the Sorrento 3-seater
  with corner, where Rens asked for more pieces, must be kept out of a mass rebuild until the
  owner decides. Given covers cut on their creases: S53, S60 and D8.
- **Not done.** The cross-side case (a top face onto a wall) stays a seam: the skirt is where
  the vents and the hem go.

## ADR-100 — A cover surface of its own is cut along its own creases

Rens, 8 October 2026, on S53 and S60 (customer cover models, `hull.top: given`): "for the cut
pieces please follow the lines of the original model", "follow the seams of the original
model as shown by the red lines".

- **Why.** A given cover surface went through the usual seams step: a level skirt seam and a
  roll split across the top. The surface's own creases (the top's front and back edges, 25 to
  90 degrees) were ignored, so the seams ran beside them.
- **The rule.** `seams.given_crease_deg` (20): a given surface not drawn in parts is cut into
  the pieces its creases sharper than this enclose (scrap bits from meshing go to their
  neighbour), seams on the creases; a smooth surface (one piece) keeps the usual seams, and a
  surface of a few flat faces keeps one piece per face with its 45 degree corner splits
  (ADR-045). The red
  lines were mapped onto the 3D cover by fitting the Desk snapshot's camera (silhouette and
  flat-colour match, IoU 0.99 on S53) and lie on those creases.
- **Clash, for the owner.** The front crease of S53 and S60 is not level (45 to 79 cm), so the
  skirt is no longer cut at one height (rule 13, `seams.skirt_seam: level`). The covers are
  built in staging and put to the owner; they are not replaced live until he chooses.
- **Furniture part lines.** "The original model" could also mean the furniture's own parts
  (model.glb). Not usable as a general seam source: the SUNS furniture files are thousands of
  tiny parts (Sorrento 2-seater: 11,302 kept parts, the weave and cushions), so their
  boundaries are no lines a cover could follow. The red lines on the SUNS box sofas ask for a
  different box (a straight front-wall edge, a roof seam from the apex), which is an owner
  question, not a seams file: a box cover's seams are its edges.

## ADR-101 — Air vents round every side, one in the middle of each piece, never upside down

Rens (approver) rejected 49 covers on their vents on 8 Oct 2026 (group A of
docs/plans/rejections-2026-10-08.md). His words: "the right number of vents, but too many at
the back (the side not seen on the drawing): per back panel move one to the front, at the
circles"; "circles: add, crosses: remove"; "the same height on the skirt, in the middle of the
panels"; the Portofino daybed "2 per side, 8 in total". Read from his 64 marked pictures (each
twice by the vision model, and by eye against the covers' own vents.json):

- **The cause.** `per_side` spread the drawing's count over the sides *by length*: the long back
  walls got two or three, the short ends one, and every front (seen) wall of an L, U or C none,
  because ADR-093 skips inner walls. Every circle on the C, L and S33 covers lies on such a front
  wall; every cross is the second or third vent of a back wall.
- **The rule now** (`finish.place_vents`, `vent_bases`, `_spread`): a vent goes on any piece
  with a bottom edge long enough; first one per piece, a side not served yet (pieces facing
  within `features.vent_wall_angle_deg` of each other) before a second piece facing the same
  way, the longest first; each further vent to the piece with the most length per vent (the
  longest walls get two). Each piece's vents sit at the middles of equal shares of its bottom
  edge, so one vent is in the middle of the piece. The drawing's number is kept; without one,
  one per full metre of each side (owner, 1 Oct) where a side is the pieces that join and face
  the same way. The way a piece faces comes from panels.npz (`vent_walls`), out of the cover.
- **Never upside down** (C24's vent at 63–85 cm, S25 "upside down"): a free top edge is a hem
  too, and a vent hung from it. `cover flatten` now writes each edge's height (`z_mm`); a vent
  goes only on a hem at the cover's lower end (within `vent_min_height_mm`). Old pattern.json
  files without heights keep the old behaviour until flattened again.
- **A skirt too low for a vent** (a box cover's 12 cm band: Kota, Evora, Portofino chaise and
  daybed, 2-seater) hands its vents to the piece above, placed over the seam
  (`features.vent_above_low_skirt`, default on); before, those sides had none (the warning
  "no air vent on the back: lower than 16.5 cm").
- **Front (inner) walls** (`features.vent_inner_walls`): Rens's circles on 30 covers are
  exactly the walls excluded on 7 Oct (C23). The owner answered on 9 Oct 2026 (QUESTIONS 71):
  **yes**, vents go there too; the default is now **true** (ADR-110, ADR-093 superseded).
- **By hand** (`features.vent_positions`, "piece@fraction, ..."): where a person's marks differ
  from the rule; wins over the count.
- **Height on the skirt** (`features.vent_align` bottom | middle | top, `vent_below_top_mm`):
  bottom stays the default (owner, 30 Sep: 5 cm above the hem); R1–R3 say "at Top"
  (QUESTIONS 66): staged with top, to the owner.
- **Checks:** `cover audit` has a "vents" check (the count asked for, no side without a vent
  while another side has two, none high up a wall); `scripts/fewer_check.py` fails a vent high
  up a wall and accepts front-wall vents only where the cover asks for them;
  `scripts/vents_compare.py` draws before/after with the marked pictures. Tests in
  test_finish.py. Lesson in config/ai_lessons.json.
- **Better later:** read the circles' positions off the picture onto the 3D cover
  automatically (the camera of a Desk picture is not stored; the vision reading names the wall
  only).

## ADR-102 — Drawing shapes Rens rejected: read by a person where the reader cannot, and four reader fixes

Rens (approver) rejected 27 drawing covers on shape, size or pieces (7-8 Oct 2026, group G), and
the SUNS Portofino daybed with roof as "no cover needed" (H). Most had been built in the first
days from the AI's sizes (sloped box, L shape, swept); route A (ADR-081) said "needs a person"
for half of them. Looking at each drawing next to its cover, the causes were few:

- **An arm block** at one end with a ramp from the seat (S4/S5, S6/S7, S6, S19) and a **corner
  seat** with its back along two sides (S35, built as a plain box): shapes no builder had.
- **The Blocchi family** (D6, S26, S27): a back chamfer, a flat strip, a long slope and ends
  that lean in. It is the **lowest of the edges' profiles** (a hip roof): each outline edge
  carries a profile from it (rising, then level or falling, so it is the lowest of straight
  lines), the top is their minimum, and each piece is where one plane is lowest, so every seam
  is a straight line. The written sizes then come out by themselves (S26's back top 152.66 cm,
  its strip 121.6 cm); the live covers had the back full width. `drawing_given.hip`.
- **D1, D2**: an 18 cm skirt and side strips of even width: the sides are twisted quads (a
  ruled patch, 0.13 % stretch); "faces" pieces.
- **Level skirt** (Rens on S43: "keep the skirt height level all round"; the domain rule 13):
  `skirt_cm` on any drawing shape cuts every upright wall at one height into one skirt band
  and the upper parts. The band is cut where one wall meets the next (Rens's short vertical
  lines on S43, at the nose and the inner corner), whole walls packed into runs no longer than
  `seams.max_skirt_panel_mm`, at least two. A swept shape's own seams are joined first
  (ADR-076), so the skirt seam stays.
- **Mirrors**: S44 is S43 mirrored ("the side at the red circle should be round as on the
  drawing"; both drawings have the same sizes, S43's top view reads 18 % small); "24 & 24B are
  mirrored of each other". `"mirror": true` on any shape.

**How (`coverengine/drawing_given.py`, `scripts/given_build.py`).** Where the reader cannot read
a drawing, a person writes the shape once in the model's `drawing_shape.json`: the kind (any
drawn.py shape, `plan-profile`, `hip`, `faces`, `revolve`), its sizes from the drawing, and
`read`: how each size was read. `cover drawing-build` then builds it as reader "given", like any
route-A cover (vents from the drawing's text, hull, cut, flatten, export). No drawing is a
special case in the code. The 18 files are kept in `testdata/drawing_shapes/` (a test builds
them all).

**Reader fixes (general, with tests):**
- **Heights without names** (C28, S32: "86.4cm", "38.1cm", "99.0cm", "20.3cm" with no
  "Height"/"Depth"): sizes written upright beside vertical arrows are heights (the highest the
  back, the lowest the front), the slanted or level ones close by give the depth (largest) and
  the strip (smallest); the top view's own upright width and depth are left out (S44's 192.4).
  C28 now builds by route A (plan-profile, the mirror of C27: 20 pieces, 0.54 %). A plan filling
  up to 95 % of its hull (was 85 %) is tried as plan-profile, so a kidney (S32, 91 %) is too;
  it is still only taken when its seams match the written lengths.
- **The angle of an angled sofa** (S21, "now a 90 degree L, the wanted angle is 30"):
  `drawing_vectors.back_angle` reads it from the two longest lines of the top view that meet.
  S21's arms meet at 140 degrees (a 40-degree bend; Rens writes 30: to the owner, both built).
  The shape is the new `angled` kind: each arm a hip shape on its own plan, open on the mitre,
  so the arms meet at the same heights; the profile and hipped ends from the side view (59 /
  84 / 59 / 40 cm, the front edge 149.78 cm as written). swept.py's sharp turn cannot do it:
  with the front on the inside of the bend its stations next to the corner reach past the
  mitre and the pieces fold over (the AI's 90-degree turn on the L1/L5 mirror). The audit
  (`drawing_checks`) fails a drawing whose arms meet at 100-175 degrees but is built as a
  90-degree L, and any drawing cover in more than 60 pieces (the 7,846-piece L1/L5 mirror).
  Swept over the live drawing covers: only these two fail.
- **A side view alone is round** (U2, "should be cylindrical; the drawing is a side view"):
  drawing_views calls a lone picture the 3D view; when it has no 3D slant lines it is a side
  view, and route A turns its outline about the axis (scaled by the largest written size, the
  height; taken when its width is a written size too): a cylinder in two gores, the cone, the
  rounding band, a top disc.
- **A sloped top narrower than the roll across is one piece** (S16 was cut in two along its
  250 cm slope although it is 114 cm across).

**Results** (staging `out/rejections/G/`, compare sheets in `out/rejections/G/compare/`): 18
covers rebuilt (and S21 twice, for the owner to choose), every one checked twice (`cover audit` ok; `scripts/fewer_check.py` PASS: roll,
seam pairs within 1.7 mm except S32 2.5 mm, stretch at most 0.76 %, vents as drawn) and looked
at against the drawing. The water check flags the flat strips as drawn, as on the live covers
(ADR-094, `drawing.isofit_strip_fall_deg` is the owner's). Ten go to the owner: D5 (its sizes do
not make one surface), S20 and S48 (following the seat between arms holds water, rule 12), S21
(40 vs 30 degrees), S37 (the drawing contradicts itself), S38/S39 (the shape matches the drawing;
only the drawstring opening at the front corner is missing: what does Rens mean?), S45 (one
358 cm band is over the 300 cm skirt panel default), S47 (matches the drawing; what is wrong?),
Portofino (no "retired" status yet). A half-plane in the hip builder was drawn too small when
its line lay far from the origin (a never-binding side): fixed, with the S21 test.

**Not done:** the vertical drawstring openings (D5, S38, S39) and U2's zippers and fibreglass
pocket are not in the patterns; a reader for the arm-block and hip shapes (they are given by a
person for now, the better alternative is to fit them to the 3D view like ADR-094).

## ADR-103 — The consumer shop is public: legal drafts, SEO, limits and headers at the edge

The owner (8 Oct 2026): two shops; the business shop (B2B) gets a login of its own under /b2b
(built separately), the consumer shop (B2C) is public. Handbook: docs/handbook/webshop.md.

- **What was public before** (checked on shop.s2dio.living, 8 Oct): every page already answered
  without a login (no Cloudflare Access, no password; the studio's own `/shop/` sends a 301 to
  the website and its API refuses the public, ADR-066); robots allowed `/` and disallowed
  `/api/`; preview.s2dio.living is `noindex` with `Disallow: /`. But: the legal pages were empty
  ("this text follows"), company details empty, no Mollie key (orders stay "awaiting payment"),
  shipping prices not set (€ 0), the price set "indicative", `home_story` off; any unknown
  address (`/studio`, `/index.html`) answered 200 with a copy of the home page; the security
  headers came only from the studio; "indicative" was a few small words after the price; the
  checkout total left out delivery.
- **Legal pages** (`coverapi/shop_legal.py`, texts in `config/shop_legal.json`): terms
  (algemene voorwaarden), privacy, returns (herroepingsrecht), cookies, contact (imprint) and
  warranty, NL and EN. A page shows our draft, opening with **"CONCEPT — TER GOEDKEURING" /
  "DRAFT — TO APPROVE"**, until the owner publishes his own text through the AI CMS
  (`legal.<page>.<lang>`). Company details are placeholders filled from Shop settings → company,
  "[nog in te vullen: KvK-nummer]" while empty. Written for Dutch law: prices incl. VAT; no right
  of withdrawal for made-to-measure (art. 6:230p sub f BW); **but a cover from our standard range
  (a stock model chosen by the match, ADR-064) is not made to the consumer's specification, so
  it keeps the 14-day right**: the checkout's checkbox says which applies, and the returns page
  has the model withdrawal form. The order button names the obligation to pay ("Bestellen met
  betaalverplichting" / "Bestellen en betalen", art. 6:230v lid 3 BW).
- **Prices:** the B2C channel of the published price set, incl. VAT, as before (ADR-098). While
  the set is indicative, the configurator and the checkout show a plain note ("Indicatieve prijs
  — onze prijzen worden nog vastgesteld; je betaalt pas na bevestiging"); the owner switches it
  off by publishing a set without it. The checkout shows cover + delivery to the chosen country
  = total, before the order (the server already charged delivery; the page now shows it).
- **Search engines and sharing:** a title and a description per page and language
  (`meta.pages`, content the CMS edits and translates); canonical and hreflang (with
  x-default) per page; Open Graph (url, site_name, locale `nl_NL` + alternates, an image
  1200×630 `/brand/og-shop.png` or the setting `og_image`) and a Twitter card. The sitemap lists
  every public page in every language with `xhtml:link` alternates. The website's robots.txt
  allows `/` and disallows `/api/`, `/b2b`, the customers' own pages (`/order/`, `/match/`,
  `/fit/`, also under a language) and `?preview=`. An unknown address is a **real 404** with
  `noindex` (the shop around it); an order's, match's or fit question's page is `noindex` and has
  no canonical. `/b2b…` is left to the business shop.
- **Limits:** each public endpoint counts per visitor (the Worker's `x-client-ip`) on its own:
  quote and match 40/min, order and fit 10/min, Mollie's webhook 60/min (each call makes us ask
  Mollie), an order's photo uploads 10/h; idle visitors are forgotten. Suggestions from a photo
  or link: `suggest.per_hour` (10) and now `suggest.per_day` (20), and a **spend guard per
  visitor per day** (`suggest.visitor_eur_day`, € 0.50): every paid call writes the visitor's
  tag on its ledger line (`spend.for_visitor`, a SHA-256 of the day + address, never the
  address; it is carried into the search threads), and `spend.guard_visitor` refuses the
  visitor's next suggestion once today's sum reaches the cap ("please choose by hand"). The
  month's budget (ADR-078) still stops everything.
- **Bots:** no Turnstile key exists (deploy/.env), so a honeypot: a field `website` people never
  see (off-screen, not focusable, no autofill) in the checkout and the match form, and accepted
  by the order, match and suggest endpoints; filled means 400. With the rate limits that is
  enough for now; Turnstile is a small step later (question 71).
- **Security headers at the edge** (`apps/site/src/security.ts`): CSP (self only; Google Fonts
  for styles and fonts; no frames; `upgrade-insecure-requests`), HSTS, nosniff,
  X-Frame-Options, Referrer-Policy, Permissions-Policy (no camera, microphone, location,
  payment API, USB), COOP; set on every answer the Worker gives (the studio's, the preview's own
  files, its own 404s and redirects), keeping a header the studio already sent. In a module of
  its own because a Worker's main module may export only handlers (wrangler refused an exported
  constant). The Worker still answers 404 to every `/api/` path but the shop's, and pages only as
  `/shop/<path>` on the studio, so no studio route is reachable through the shop's domain.
  Tests: `apps/site/test/worker.test.ts` (node's test runner on the sources; `npm test`, and in
  `make test` through `apps/api/tests/test_site_worker.py`).
- **Cookies:** the shop sets none (the studio's session cookie is stripped by the Worker);
  local storage keeps the language and the 3D view (functional). No consent banner is needed.
  **But the fonts come from Google Fonts**, which shows Google the visitor's address; the
  cookies page says so until they are self-hosted (to the design work, question 71).
- **Mollie:** unchanged (no key on live: orders wait for payment by hand). The shop now tells
  the mode from the key's prefix (`payment_mode`: none, test, live; never the key) and shows
  "test payments: no money is charged" in test mode. Going live is the owner's (question 71).
- **Checked in a real browser** (`apps/web/e2e/b2c.py`, the Worker under `wrangler dev` in front
  of a scratch studio): 13 addresses on a desktop and at 390 px; all 200 (the unknown one 404),
  titles per page, no sideways scrolling on the phone after the footer's six links wrap, the
  price with the indicative note, the checkout with delivery. Pages load in 0.05–0.3 s locally;
  the shop's own script is 170 kB (62 kB gzipped), the 3D (Scene, 758 kB / 204 kB) only where
  the 3D is shown.
- **Better later:** Turnstile on the order and suggest forms; the fonts self-hosted (then drop
  Google from the CSP and the cookies page); Cloudflare's rate-limiting binding in the Worker
  as a first line before the studio; a catalogue page of our standard covers (today they are
  reached through the match in the configurator).

## ADR-104 — The B2B shop: business accounts with their own login, prices ex VAT, orders on account

The owner (8 October 2026): "two separate shops: the B2B shop gets a login; the consumer shop
is public." Handbook: docs/handbook/b2b.md; open questions: QUESTIONS 72.

- **Where:** `/b2b` on the website's domain (shop.s2dio.living/b2b), served by the same Worker
  (`apps/site/src/b2b.ts`); on the studio `/shop/b2b/` (the colleagues' preview). Its own page
  (`apps/web/b2b.html`, `src/shop/b2b/`), never indexed, never cached at the edge.
- **Business accounts are not studio users** (`coverapi/b2b.py`, tables `b2b_companies`,
  `b2b_users`, `b2b_sessions`, `b2b_tokens`, `b2b_failures`, `b2b_orders` in app.db): a company
  (name, VAT number, contact, invoice address, delivery addresses, price list, its own fixed
  prices, reverse charge yes/no, status requested → invited → active, or blocked / rejected)
  with one or more people who log in.
  - **Admin → B2B customers:** invite a company (a mailed link to choose a password, 7 days;
    the link is shown when no mail server is set), approve or reject a request, block (every
    session ends at once), add people, a new password link, its orders, the B2B settings.
  - **No self sign-up:** "request an account" lands there, and the alert address is mailed.
- **Logins follow the studio's standard** (auth.py, security.py): scrypt hashes, the same
  password rule, a lock after 5 wrong passwords per person (15 min) and 10 per address, one-time
  links for the first password (7 days) and for a reset by mail (2 hours; the same answer for
  an unknown address), every login, failure and change in the audit log as `b2b:<e-mail>`.
  - **Its own cookie,** `b2b_session`: HttpOnly, SameSite=Strict, Secure over https, path
    `/api/b2b/` only. A studio session opens nothing in the B2B shop, and a B2B session opens
    nothing in the studio. `/api/b2b/` is open in the studio's front door and does its own
    checks.
  - **CSRF:** every change needs the session's token (an HMAC of the session secret, given by
    the login and `/api/b2b/me`) in `x-b2b-csrf`, and an Origin from our own hosts (the
    website's domain, its preview, the studio). The studio's own Origin check cannot serve
    here: behind Caddy the forwarded host is the studio's, not the website's.
  - **The Worker** passes only `b2b_*` cookies, both ways; the studio's cookies never pass, as
    before (ADR-066). Tested with `wrangler dev --local` against a scratch studio.
  - With the website link closed, `/api/b2b/` answers only the website and colleagues.
- **Prices** (ADR-098): the company's price list (`b2b` by default; any channel of the
  published set), always ex VAT, from the same costing as the consumer price. For a catalogue
  cover a fixed price in the list wins, and the company's own fixed price (ex VAT; a catalogue
  cover, balloon or frame) wins over both. VAT is the list's rate, 0 when reverse-charged.
- **The same configurator and catalogue:** the configurator (sizes, colours, vents, the rain
  check with the support advice at the company's price) and the SUNS catalogue covers (size
  card, photo, "show the price"), with quantities and an order list.
- **Orders on account:** a PO number, a delivery address (the invoice address or one the
  company manages itself), a note; a minimum order and a shipping line per order (B2B settings,
  both 0 now).
  - Each line becomes an order of the studio's own (`orders`, status `on_account`, flagged
    `data.b2b` with PO, quantity and unit price ex VAT): Admin → Orders shows it, and it goes
    into production at once through the same `produce()` as a paid consumer order (a setting).
  - The B2B order (`b2b_orders`) is what "previous orders" shows, with each line's status;
    "order again" prices every line anew at today's prices.
  - A confirmation goes to the buyer (in their language), the company's e-mail and the alert
    address.
- **Checkout reliability (11 October 2026):** the client keeps one `idempotency_key` per
  checkout in session storage and resends it after a failed response. A unique company/key
  index returns the original order, even if quotes or settings have since changed. The B2B
  order, studio rows, links and per-line dispatch outbox commit in one SQLite transaction.
  Additive app.db migrations use the existing PRAGMA/ALTER approach; old orders have no key
  and are not automatically re-dispatched. Production starts after commit, serially per app,
  marking each line dispatched only on success. Startup retries pending lines; `produce()`
  already returns an existing model for a completed production order. A crash during external
  production work can retry that work: this outbox gives recoverable delivery, not an atomic
  transaction across SQLite and filesystem/job side effects. A transactional job queue would
  close that remaining window if needed later.
- **Online payment for B2B:** a switch is kept (`b2b.online_payment`, off); the order API
  refuses "online" until it is built (one Mollie payment for several order rows needs a
  webhook that handles a group).
- **Languages:** the new words are in `config/shop_ui.json` under `b2b` (NL, EN, DE, FR), part of
  the site's content, so the AI CMS edits and translates them. Server errors stay English, as in
  the shop.
- **Tests:** `apps/api/tests/test_b2b.py`; browser: `apps/web/e2e/b2b.py` (19 screens).
- **Better later:** a mailed login code (as the studio's), roles within a company (who may
  order), PDF invoices and Odoo invoicing, per-company payment terms, VIES checks of VAT
  numbers, B2B online payment.

## ADR-105 — The website's look: one design system in sand and warm ink, Work Sans self-hosted

The owner (8 October 2026): "the website may get a professionalising touch so it looks slicker",
in all calm. Only the look of the consumer pages changed; content, languages and structure did
not, and `home_story` stays as it is (off on the live site).

- **One set of tokens** at the top of `apps/web/src/shop/shop.css`; every rule is built from them.
  - Colour, from the covers themselves rather than the greens: a warm paper ground `#F3F1EC`
    (the brand's off white, warmed), stone `#EBE7DF`, sand `#C8B593` (the sand canvas) with a
    deeper sand for numbers and accents, and a warm ink `#26241F` for type and the primary
    buttons. Dark sections (the classic hero, "how green we work", the workshop clips) are a
    warm near-black `#1F1D1A`; they swap the same tokens, so a button or a list looks right on
    either. The logo keeps its own colour on paper and turns white over the film.
  - Contrast: body text ≥ 7:1, secondary text 5:1 on paper, 8:1 on the dark ground. The rain
    chapter's scrim keeps the tone of the rendered frames, so the captions do not show a seam.
  - Type: Work Sans throughout (the brand book's face), the variable font, so the display can
    be lighter (250–300) and the labels exactly 450–600. One fluid scale: display, h1, h2, h3,
    lead, body 16 px, small, and a spaced small-caps label for eyebrows ("Total incl. VAT",
    "Rain test", the panel's questions). Numerals tabular wherever they change.
  - Space on a 4-point scale; one side gutter (20 px on a phone, up to 96); radii 10/14/22 and
    the pill; two soft shadows; the arch for media.
- **Components**: one button (ink on paper, light on dark; 52 px, 38 px small), inputs of 50 px
  at 16 px (phones do not zoom) with a sand focus ring, a drawn chevron for selects, drawn
  check boxes, sliders whose track fills up to the value (`--p`, set by the page), chips with a
  dry/wet dot, product cards with a radio mark, swatches with a ring, a price card, the match
  card, an order track as dots on a line (vertical on a phone, the present step ringed), a FAQ
  as a hairline list with a turning plus, a richer footer. Emoji replaced by line icons
  (`Icons.tsx`).
- **States**: a skeleton while an order or a proposal loads; "we cannot find this page" with a
  way back when a link leads nowhere (it showed "€NaN" before); a thin running line on the 3D
  stage while the quote is recalculated. New words `not_found` and `loading` in
  `config/shop_ui.json`, in all four languages.
- **The configurator on a phone**: the 3D on top, the rain test under it (it covered the cover),
  then the panel. On a wide screen the stage and the panel stay in place while the panel scrolls.
- **Motion**: only transform and opacity; 160/280/700 ms on one easing; reveals staggered
  80 ms; the header turns to dark glass as soon as the page moves over the film, to paper
  below it. `prefers-reduced-motion` turns every transition and animation off.
- **No layout shift from the font**: Work Sans is self-hosted from the build
  (`@fontsource-variable/work-sans`, OFL), the Latin file preloaded (a small Vite plugin), and
  the fallback has Work Sans's metrics. No request to Google Fonts any more: one less third
  party for the privacy statement. The studio's CSP may drop `fonts.googleapis.com` /
  `fonts.gstatic.com` for the shop.
- **The server-rendered copy** (for search engines) no longer flashes unstyled before the page
  draws: it fades in only when the script is late (after 1.5 s) or missing.
- **Checked** at 1440 and 390 px in a real browser: `out/sitedesign/before|after/` (not in git).
- **Better later**: labels above the checkout fields instead of placeholders only (the
  checkout's logic, another agent's area this week); the full wordmark in the header once the
  website's name is settled; a sticky price bar on a phone.

## ADR-106 — The website's 3D loads lean, and the rain on the scroll page keeps falling

The owner (8 October 2026): "the 3D model loads slowly; the rain on the scroll page stops
moving". Measured first, in a real browser (Playwright, software WebGL) on a desktop and on a
mid-range phone (390 px, CPU 4x slower, slow 4G: 150 ms, 1.6 Mbit/s), against this build served
locally with the preview's data (`apps/web/e2e/site_serve.mjs`, `site_perf.py`).

- **Why the 3D was slow.**
  - Every shop page fetched and parsed three.js and React as one 758 kB chunk (204 kB packed),
    preloaded from the HTML, also the scroll story, which shows no live 3D at all.
  - React drew nothing until `/api/shop/info` came back, and that request started only after
    all the scripts had run: the server's text in the HTML vanished in between.
  - The view was rebuilt (a new WebGL context) for every new size in the configurator, drew
    every frame even when nothing moved, and drew 3 pixels per CSS pixel on a phone.
  - The story page fetched every workshop clip (14 MB) and all 360 frames at once.
  - The models travel unpacked: the edge packs no model types (demo 131 kB, packed 39 kB).
  - The configurator's model waits for the quote, which is mostly the rain check (0.7 s of
    0.8 s on this machine, 2.6 s through the edge).
- **What changed.**
  - three.js and React each in their own chunk (`vite.config.ts`); the 3D view, the story's
    live 3D and the scroll story (GSAP, Lenis) are loaded only on the page that shows them.
    The configurator asks for three.js at once, alongside the info; a link to it warms it.
  - The info is asked for from the HTML (`<link rel=preload>`), and React takes over only once
    it is there, so the server's text stays on screen until then.
  - `Scene.tsx`: one renderer per view; a new model swaps in it (the camera keeps the angle the
    visitor turned to); a frame is drawn only when something moved; nothing while off screen;
    at most 1.5 pixels per CSS pixel on a phone; the canvas fades in on the first model. Until
    then the box is there at its final size (`data-state="loading"`, a neutral shimmer the
    design can restyle), so nothing shifts.
  - The story's workshop clips load when they come near and pause out of sight; the frames
    after the first coarse set load once the visitor scrolls.
  - The studio sends the 3D files gzip-packed when the browser takes it (`model_response`):
    the demo 131 → 39 kB, the story's furniture 488 → 147 kB and points 835 → 391 kB. The edge
    keeps the demo, the story's files and a quote's scene (named by a random id) for a day
    (`MEDIA_TTL`); the preview Worker tells the browser to keep `/assets/` for a year.
- **Measured** (two runs each; the machine was shared, so the spread is wide):

  | page, profile | first paint | first 3D / frame | JS | other |
  |---|---|---|---|---|
  | scroll story, phone | 2.4–2.5 s → 0.9–1.0 s | 4.4–5.1 s → 2.3 s | 238 → 101 kB | |
  | scroll story, desktop | | | 238 → 101 kB | 378 requests, 24–27 MB → 59, 6–11 MB |
  | landing with 3D, phone | 2.6–2.9 s → 1.0 s | 3.9 s → 3.3–3.7 s | 238 → 189 kB | |
  | configurator, phone | 2.3–2.5 s → 0.9 s | 6.4 s → 5.5–5.7 s | 238 → 189 kB | idle frame rate 3 → 49 fps |
  | configurator, desktop | | 4.1–4.5 s → 4.2–4.3 s | | idle frame rate 3 → 35 fps |

  Layout shift stayed at 0 to 0.01. The configurator's first 3D is now bound by the quote.
- **The rain.** The rain chapter is rendered frames (ADR-071) with the rain baked into each
  picture, and a picture changes only when the scroll does: standing still, the rain stood
  still (and scrolling up, it rose). `RainLayer.tsx` draws rain over that chapter in time, not
  with the scroll: three depths of thin streaks in the look of the rendered ones (leaning with
  the wind, steeper further down), small splashes where they land, from a fixed pool, fading in
  with the chapter. It runs only while on screen and the page is visible, and restarts its
  clock after any pause, so it neither stops nor jumps. Less motion asked: the frames' own still
  rain. `apps/web/e2e/site_rain.py` checks it (before: 0.00 % of the pixels moved in every case;
  after: 0.7–0.8 % on a desktop and 2.9–3.0 % on a phone, after standing still 8 s, scrolling
  back and forth and a background tab).
- **Better later:**
  - the quote in two steps (the scene first, the rain check after it), which brings the
    configurator's 3D about a second sooner;
  - Work Sans served from our own domain: the Google Fonts stylesheet blocks the first paint,
    and once took 5 s in these measurements;
  - the opening clip (5 MB, `preload="auto"`) as a smaller first take, which is the landing
    animation's own work;
  - meshopt-packed GLBs, when the models grow.

## ADR-107 — A box cover's plan comes from the furniture seen from above: round, follow or box; no chair space round a chair

Rens at the Desk, 8 Oct 2026 (groups D, E, F of `docs/plans/rejections-2026-10-08.md`, 42
covers): 18 round tables (Grado, Sorolo, Nova): "make the cover round in top view, not square /
octagonal"; 12 organic lounges (Casto, Feroli, Fiora, Pienza, Vento hocker, Vivaro, Aspen, Pico):
"follow the (round) outline from the top view better"; 12 chairs, lounge parts and picnic tables:
"empty space, cover too roomy". All 26 marked pictures were read twice by Gemini Flash (the marks
and where they are; the change asked per mark); the two readings agreed on every picture, and
with what I saw myself (out/rejections/{E,F}/vision.json).

**Causes.**
- *Round and organic:* all 30 are box covers (ADR-038), an intersection of half-spaces, so the
  plan is a convex polygon with a few straight sides: a round table and its ring of chair space
  (ADR-044) became a square (5 pieces) or an octagon (Nova 140, 9 pieces); a kidney sofa's bay
  was spanned by a straight wall; round corners became chamfers over empty floor.
- *Six dining chairs (Antas, Pemba, Santorini, Sato, Tosca, Vado):* "dining" is in their names, so
  `hull/chairs.py` took them for dining tables and added 33 cm of chair space before and behind
  them, 87 cm high: covers about 1 m deep over 0.6 m chairs. The catalogue has 29 such chairs.
- *Lucia, picnic tables:* the box piece count remembered in cover.json (an AI choice, ADR-080)
  left the slope Rens drew uncut.

**The rules** (`hull/outline.py`, `config/defaults.yaml`).
- `hull.plan: auto | box | round | follow`. The footprint: the furniture above the hem seen from
  above (height map on `hull.plan_cell_mm`, gaps under `hull.bridge_gap_mm` closed, holes filled),
  plus the chair space of a table.
- **Round** when the footprint fills at least `hull.round_fill` (0.93) of its smallest circle (a
  regular octagon 0.90, a square 0.64): a cylinder skirt and a cone on top, every furniture,
  chair-space and balloon point the clearance under it, the slope at least `hull.min_slope_deg`
  (of those the one with the least room): water runs off everywhere (rule 12), the skirt's top
  edge is level (rule 13). The top is cut into equal sectors whose seams run straight down from
  the apex, as few as fit the roll (`hull.round_top_pieces`; at least 2, a cone is no flat disc);
  the skirt into strips, a multiple of the sectors so the seams line up, at most
  `seams.max_skirt_panel_mm`, the front in the middle of a strip. Built ring by ring, so every
  seam is on mesh edges; cone sectors and cylinder strips are developable (stretch < 0.1 %).
- **Follow** when a side or corner of the box's plan stands more than `hull.plan_follow_mm` (24
  mm; the hocker's chamfers stood 31 mm out) beyond the footprint plus the clearance: the walls
  stand straight down on that outline; grid steps are shaved off and grown back, bays and inner
  corners rounded to `hull.plan_round_mm` (500), so the seams along it are smooth (rule 13); the
  top is the box's own top faces, which span seats (rule 12). The outline extruded is cut by those
  faces (manifold3d); its long triangles are halved edge by edge (a remesher rounded the shallow
  creases between top faces off: 7 mm zig-zag seams; triangle-by-triangle subdivision left
  T-joints: pieces that were not one sheet). Pieces: each top face, the wall cut at its corners
  (a net turn over `seams.corner_angle_deg` within `seams.corner_window_mm`; a jog out and back
  is no corner) and where longer than `seams.max_skirt_panel_mm` (or the roll width when the wall
  is higher); slivers join a neighbour of their own kind and never close a ring; tops wider than
  the roll are cut in strips downhill (a cut that would tear the sheet is moved a hair); on request
  (`seams.fold_merge`) top faces join with a fold, as on box covers. The box's mirror lines come
  from its convex outside, so the plan is mirrored only where it really is symmetric (a kidney's
  bay would have been filled by its mirror image). Arrangements keep the plan chosen on their
  page (ADR-095).
- **Chair space only round tables:** never round furniture named chair, stool, sofa or bench, and
  only when the top is at least `hull.table_top_min_mm` (400) deep both ways.
- **Audit:** `chairs` (chair space round furniture that is no table fails) and `outline` (a box
  over furniture that is round from above fails; one that would follow is noted). The `furniture
  inside` measure now signs each point by the nearest face, the angle-weighted normal and the
  winding number of the cover capped at its hem together: the nearest face's normal alone called
  points deep inside a bay "outside" (next to an inner corner of the wall).
- **Learned** (ADR-055): two AI lessons (`config/ai_lessons.json`), the audit checks above, tests
  `engine/tests/test_outline.py` (round table: round hem, level skirt, pieces in the roll; kidney
  sofa: bay kept, walls upright, water runs off; chairs are no tables; roundness tells a circle
  from an octagon and a square).

**Results** (staging `out/rejections/{D,E,F}/`, before/after pictures in `compare/`, per cover in
`results.json`; every cover `cover audit` ok, no engine warnings, `scripts/fewer_check.py` PASS,
looked at against Rens's picture): 18 round tables round (fabric -23 to -24 %, Nova 140 -9 %;
4 or 6 pieces instead of 6 or 10); 6 chairs without chair space (fabric -23 to -37 %); 11 lounges
and the Aspen side table follow their outline (0 to -13 %); the Ferla picnic tables -17 %; Lucia gets the back slope Rens drew
(cover.json `hull.box_pieces` 8), the Ferla picnic tables the roof slopes to the benches (the
rule's piece count, plan kept straight: `hull.plan: box`); the Vento hocker is 3 pieces, its top
one panel with a fold (`seams.fold_merge`). Doubt, to the owner: Fiave L-part (Rens's line
follows the cushions over the seat: water, rule 12), Nuna (the egg-shaped back in side view needs
a curved cover), Vento angled 2-seater (asks for a seam layout, group C).

**Sweep** (`out/rejections/sweep.json`, the 294 live box covers that are not arrangements): 29
round (18 rejected + 11 lounge tables: Farzi, Ronda, Nova lounge, Sorolo 140/160), 152 follow
(129 not rejected), 113 stay a box; 29 chairs lose their chair space (23 not rejected). Nothing
is rebuilt live by this change; the covers change when they are built again.

**Better later:** a box chooser that weighs the plan's walls (its faces are chosen for the convex
box, then the walls are swapped); folds as pen lines also for covers with their own plan through
the cut's join (now passed through hull.json); a curved cover for egg-shaped chairs.

## ADR-108 — The home page's film: our own cover, path-traced from our own data, no generated video

The owner (8 October 2026): "the animation on the start page does not show our quality"; before
that, "the first animation still shows a green cover instead of sand". The live home page showed
the turning 3D dining set (a see-through box with balloons, on dark green); the preview showed a
Veo take of a cover that is not ours (ADR-071). Paid video generation is off unless the owner
asks for it.

- **What the film shows** (13.6 s loop, 24 fps, soft dissolves, the end dissolving into the
  start), all of it the SUNS Kota 2-seater and its real cover in sand Coverlast:
  1. the covered sofa on a stone terrace against a lime-plaster wall, a low hazy sun from the
     left, a slow dolly;
  2. close on the front corner: the double-stitched seams, the hem and the soft pleats its cord
     gathers;
  3. the cutting table: the cover's own pieces (cut.dxf) cut in one sheet, the machine's pen
     labels ("P7 TOP-1 …") and the vents cut out;
  4. the cover lowered over the sofa by its ridge and settling;
  5. rain: drops run down the paths our rain check computed on the draped cover
     (drape_rain.json), gather at the hem and fall; the coating beads; the stone gets wet.
- **Our data, nothing modelled by hand:** the drape is Style3D's (drape.bin, ADR-059); the sewn
  pieces carry their flat positions as UV, so the weave follows the fabric's grain; the
  stitching is baked into a picture in the flat pieces (`seams.png`, 0.35 mm a pixel): two rows
  4 and 10 mm from each seam on the panel that laps over (the higher one; on an upright seam the
  front one — domain rule 6), the hem row 32 mm up, the folded allowance as a soft ridge, a
  faint pucker. The lowering (shot 4) is Blender's cloth solver on the same sewn mesh, held by
  the ridge, blended into the Style3D drape as it comes to rest.
- **How it is made** (`scripts/film/`):
  - `hero_assets.py` fetches CC0 scans from Poly Haven (a fine plain weave's normals and
    roughness, stone, plaster, an HDRI, a plant);
  - `hero_data.py MODEL OUT` writes cover.npz, seams.png, pieces.json (needs ~7 GB RAM for the
    0.35 mm picture);
  - `hero_fall.py` (Blender) the lowering, `fall.npz`;
  - `render_hero.py` (Blender 4.2 Cycles, CPU, OpenImageDenoise, AgX): 376 frames at 1600×900,
    32 samples, about 75 s a frame (rain 105 s) on 6 cores at nice 19 here: one night. Frames
    that exist are skipped.
  - `hero_encode.py FRAMES OUT --name hero-kota1`: dissolves, AV1 (libaom, 1600×900) and H.264
    (1280×720, High 4.1), both two-pass under 3.8 MB, fast start; a JPEG and WebP poster; a
    strip.
- **Result:** `hero-kota1-av1.mp4` 3.5 MB, `hero-kota1-h264.mp4` 3.65 MB, poster 135 KB (WebP
  52 KB). In Chromium, WebKit and Firefox (Playwright) the AV1 file plays; the first frame shows
  about 0.75 s after navigation on the local studio; 0–1 dropped frames over a loop on desktop
  and phone sizes.
- **On the page** (`HeroFilm.tsx`): `<video muted autoplay loop playsinline>` with an AV1 and an
  H.264 `<source>` and the poster; muted is set before play (iOS); it plays only while on screen
  and the tab is visible; reduced motion, Save-Data or a 2G connection get the poster only; if
  the device refuses to play (iOS Low Power Mode) the poster stays. The cover sits right of
  centre; narrow screens crop to it. Used by the scroll story (`story_media.hero`, `hero_av1`,
  `hero_poster`) and the classic home page (`film_url`, the new `film_av1`, `film_poster`).
- **Why a film and not live three.js:** path tracing (soft sun, the sheen, the stitches, rain
  with motion blur) is far beyond what a mid phone draws at 60 fps, and a 3.5 MB loop starts as
  fast as a 3D scene loads. The live 3D stays where it earns its place: the configurator.
- **Not yet as good as a photograph:** the weave is not visible at the wide shots (the coated
  fabric reads smooth), the wide terrace and the table look rendered rather than shot, and the
  sofa's base shows its model's facets in shot 4. A real Coverlast scan (or close photos) and
  a few seconds of real workshop footage would lift it most (ADR-065's list still holds).
- **Rejected:** Veo/Sora takes (not our cover, paid); the dark green set of ADR-065 (it hid the
  sand colour).

## ADR-109 — Questions at the Desk: the owner's and the workshop's questions answered in the studio

The owner (9 October 2026): "for Rens it's easier if we put the questions in a tab in the Desk so
he can answer there; I (Rick) am the only one with SSH access. Can we make a questions form? And
every day around 18:00 check and process the answers." Until now the open questions lived in
docs/QUESTIONS.md and in the rejection agents' results (the "doubt" rows), which only Rick could
read on the server; answers came back by mail or by word of mouth.

- **Where:** a second tab on the Desk, **Questions** (`#/questions`, `#/questions/<id>`), beside
  **Covers**. The tab carries a badge with the number of open questions (red when some wait for
  your own answer).
- **Kept in app.db** (`coverapi/questions.py`), not in a JSON file: three tables, like the price
  sets (ADR-098):
  - `questions`: the question, its context, options and state;
  - `question_answers`: every answer, never deleted. A new answer by the same person replaces
    the earlier one by pointing at it (`replaced_by`), so the trail stays;
  - `question_log`: every change, who and when (add, answer, final, processed, reopen).

  Writes go in one `BEGIN IMMEDIATE` transaction under a lock. The audit log of app.db also
  notes each answer.
- **A question** has:
  - a title and the question itself, in Dutch (the studio around it stays English);
  - a topic (vents, shape, seams, sizes, drawings, workshop, webshop, b2b, prices, film, other);
  - context;
  - the covers it is about, as links to their Desk cards with their picture;
  - its own pictures with a caption (an agent's before/after with the plan and side views);
  - 2 to 5 options plus "anders, namelijk…", or none for a free answer;
  - who may answer: the Desk's approvers (`desk.approvers`) by default, or named people. Admins
    always may.
- **The state:** open → answered (someone answered) → processed. Processed carries a note, who
  and when; the answerer sees it on the question and in the next digest. Several people may
  answer and all answers show. The owner (`questions.owners`, "rick") can:
  - mark one answer final;
  - mark the question processed;
  - reopen it.

  Answering a processed question is refused until it is reopened.
- **Rights:** every logged-in user reads. Only the question's answerers (approvers) and admins
  answer, a viewer-role approver too: `/api/questions` passes the front door for viewers, and
  the route decides. Adding a question, `answers?since=`, final and processed are the owner's or
  an admin's.
- **Pictures:**
  - The answer form has the Desk's Pictures block (ADR-096): Upload…, drop, paste, plus "Mark
    picture n" for the question's own pictures and "Mark <code>" for the covers' pictures. There
    is no 3D on a question, so no "Snapshot 3D".
  - `desk.save_picture` checks each one and keeps it as a PNG without metadata in
    `questions/<id>/` (it takes a folder now); `GET /api/questions/{id}/pictures/{name}` serves
    only names it made.
  - The block comes after the options and before the comment and Send, in the normal flow of
    the card, never under a sticky bar. "1"–"5" bring the form into view with the block on the
    screen.
- **Keyboard and tablet:**
  - keys: `j`/`k` next/previous, `1`–`5` an option, `0` "anders", `Ctrl+Enter` send, `/`
    search, `Esc` closes a picture;
  - the options are real radio buttons, 44 px high;
  - below 1100 px the list sits above the question.
- **Mail, quietly:** an hourly loop in the app, the first look two minutes after start.
  - New questions go to the people who may answer, in one digest per `questions.digest_hours`
    (24). The digest also lists what was done with their answers.
  - New answers go to the owners in one digest per `questions.answer_digest_hours` (8).
  - Never a mail per click; 0 switches a digest off; without a mail server nothing is sent.
- **The daily processing** (the main session, 18:00), with `scripts/questions.py`, straight on
  app.db:
  - `new [--since T] [--json]` lists the answers since the last `ack`;
  - `ack` remembers "seen until now";
  - `done ID "note"` marks a question processed;
  - also `list`, `show`, `reopen`, `add FILE.json` (a new question with pictures) and `mail`.
- **The import** (`scripts/questions.py import [--dry-run]`, data in `scripts/questions_seed.py`)
  makes the open questions of 9 October:
  - the rejection agents' doubts. Rows with the same question are one question with all their
    covers; "zelfde vraag als S38" rows join their leader. Question 71, vents on the inner
    walls, is left out: it was answered yes on 9 October. Each doubt carries the agent's compare
    picture or the staged cover;
  - the questions of docs/QUESTIONS.md still open for the owner or the workshop: webshop (73),
    prices (70), B2B (72), the film (ADR-108), drawings, arrangements (69) and the workshop's
    construction questions (5–7, 36, 49, 50, 57). Each is rewritten as a short Dutch question
    with options.

  Every question has a fixed key, so running it again adds nothing. On the data of 9 October:
  23 from the doubts plus 43 from QUESTIONS.md, 66 in all.
- **Tests:**
  - `apps/api/tests/test_questions.py`: rights (viewers read-only; a viewer-role approver
    answers), answering and replacing, final and processed by the owner only, pictures, digests
    (one mail per person, nothing twice within the interval), the import run twice, the CLI;
  - `apps/web/e2e/questions.py`: Chromium, WebKit, Firefox and Edge, 1440 px and an 820 px
    tablet. Edge runs with office policies from `apps/web/e2e/edge-policies.json` (no hardware
    acceleration, clipboard blocked, strict tracking prevention).
- **Not yet:**
  - the studio has no form to write a new question; it comes from the CLI or the API;
  - a picture uploaded for an answer that is never sent stays unlinked, as at the Desk;
  - docs/QUESTIONS.md is not updated from the answers by itself; the daily processing does that.

## ADR-110 — Air vents on the front walls in the inner corner of L, U and C covers (owner, 9 Oct 2026)

The owner's answer to QUESTIONS 71 ("may vents go on the front walls in the inner corner of L, U
and C covers?"): **yes**. His remark of 7 Oct on C23 ("never vents on the inside, only on the
outside") was about vents drawn *inside the fabric* (a 3D display bug, ADR-088), not about the
inner walls of an L; ADR-093 misread it.

- `features.vent_inner_walls: true` is the company default (config/defaults.yaml). The vents go
  round every side (ADR-101), the front (inner) walls included; the drawing's count is kept.
- The switch stays: false skips the inner walls (ADR-093's rule) for a cover that needs it.
  `features.vent_inner_mm` still says what an inner wall is.
- `cover audit` (vents check) and `scripts/fewer_check.py` accept vents on the inner walls
  whenever the cover's effective switch is on; fewer_check reads it through `resolve_model`
  (defaults, preset, cover.json), no longer only from cover.json.
- The AI lesson of 8 Oct (config/ai_lessons.json) and CLAUDE.md say the same. Tests:
  test_finish.py `test_vents_on_an_inner_wall_by_the_switch` (off: none, on/default: vents).
- Swept: every cover with inner walls rebuilt in staging (out/innerwalls/), with the per-cover
  `vent_positions` from Rens's circles carried over where the vents agent had set them.

## ADR-111 — Measuring on the 3D cover, the vents' sizes and a check list for the sewn cover

The owner (9 October 2026): "for the system we need a measuring tool on the 3D model; we have
sewn some covers, and for checking it's easier if we have sizes in the 3D part, for example the
height of the air vents and their placement."

- **Measure** (3D view, studio and Desk card): click or tap two points; a point snaps (14 px,
  26 px for a finger) to a vent corner or a seam's end first, then a mesh vertex, then a point on
  a seam or the hem, else the surface; a snap point hidden behind the cover is skipped. Shown:
  the straight distance, the height difference and the distance **along the fabric**, in cm
  with one decimal. The fabric distance is the exact shortest path on the cover's triangle mesh
  (geometry-central's edge-flip geodesics via potpourri3d, `POST .../measure/geodesic`); the
  cover is first made a manifold, oriented surface for it (vertices split per fan, faces glued
  only along consistently oriented two-face edges; lengths unchanged) and the two points are
  inserted as vertices. Measurements live in the 3D scene, so turning and zooming keep them;
  labels are screen-constant sprites. Several stay; remove one or all; Esc drops a first point.
  The snap lines come from `GET .../measure.json` (seams and free edges from panels.npz, the
  vents).
- **Vent sizes** (toggle beside "Show air vents"): per vent, from `vents.json` (format 2), which
  takes the numbers off the flat piece the opening is cut in, as `place_vents` cut it: the
  opening W × H; its bottom edge above the hem (the lift on the flat piece; over a skirt too low
  for a vent the skirt's height is added); the distance along the piece's bottom edge from each
  side of the opening to the seam there, or to a corner of the cover inside the piece (the
  bottom edge turns ≥ 45° within 100 mm), left and right as seen from outside; the piece; the
  bottom's height above the ground. Drawn as dimension lines on the cover and listed under it.
  An older vents.json (no `format`) is made again on the next request.
- **Check list** (`checklist.pdf`, made when opened like sizes.pdf, `coverengine/export/
  checklist.py`): page 1 landscape: front, back, left and right at one scale (two by two for a
  long low cover) with numbered vents; overall L × D × H, the hem all round (the free edges at
  the lowest point only, not a drawing cover's open inner edges), skirt heights, every vent's
  numbers, each with a box for the measured value and an OK box. Then the pieces (hem seam to
  seam, flat size) and every seam's length. Links: viewer toolbar, Desk card, Cut pieces,
  Downloads.
- **Measured after sewing** (Desk, "Measured…" beside Fits / Does not fit): the check list's
  points as cm fields; the fit stores per point expected, measured and the difference in
  desk.json (`fit.measured` and the history entry, so learning/desk.jsonl too).
  `learned.measured_deviations` groups them per cover group and kind of size (vent.above_hem,
  skirt, seam, ...); a mean beyond `tolerance.cover_mm` on `desk.learn_after` covers is marked
  systematic (`/api/desk-rules` → `measured`). Turning a systematic deviation into a parameter
  change stays a person's decision, as the other learned rules.
- **Not done (simpler first):** measuring on the draped (Style3D) cover; snapping to the
  furniture's own features; the check list in the PDF reader's form fields.

## ADR-112 — A photo alone: read Google's search by image properly; the photo box stays in its panel

The owner (9 October 2026): "Google Vision recognises the photo I upload badly, while with
Google image search (Lens) I get a 100 % match. Also the box for uploading photos sticks out of
the browser." The ledger shows his run at 09:57: the image search ran, then identify, one
search (by look only: no brand recognised) and the comparison.

- **The cause, measured** (15 photos: 5 SUNS cut-outs and 6 mood pictures from hello-suns.com,
  4 "phone" photos made from them: cropped, tilted, mirrored, re-coloured; raw Vision answers in
  five variants, about 90 Vision calls, €0.28):
  - we asked Vision for `maxResults = suggest.search_pages` = 5. Google lists the pages about
    its best-guess label first ("studio couch", "club chair", "swimming pool", "tree": Pinterest,
    YouTube; none shows the photo) and only after them the pages that really show it. With 5
    we got only the label's pages: in **0 of 15** photos did anything we used name the
    product;
  - that label was put first among the search queries ("swimming pool", "tree", "patio");
  - what Vision did find was thrown away: its matching pictures (`fullMatchingImages`,
    `partialMatchingImages`) carry the product in their file names
    ("Marolo-SUNS-Daybed-BZ-CR-PDB-Free-26.png", "suns-tuinmeubelen-suns-basta-lage-bar-tafel")
    in **12 of 15** photos, already with 5 results; with 50 the pages showing them come too.
  - `webEntities` rarely name the model (a shop name, once a wrong product);
    `visuallySimilarImages` are generic (other sofas): both kept for the diagnostics only.
  - Variants: PNG 1600 px or JPEG 2048 px, `includeGeoResults`: the same answers. **Cropping to
    the furniture first** (OBJECT_LOCALIZATION, then web detection) is worse: 7 of 15 instead of
    12 (the crop is no longer the picture on the web, and phone photos gained nothing). Not
    built.
  - **Lens** searches Google's product index as well as the web's pictures; Cloud Vision only
    the latter. Photos that exist online are found by both; a photo taken at home only when a
    similar picture is online (1 of the 4 phone photos). That gap is a service question
    (QUESTIONS 74).
- **Now** (`shop_suggest.py`):
  1. the search by image runs **first** (a second or two), with `suggest.reverse_max` (50,
     same fee) and the photo as JPEG; `read_web_detection` keeps only pages that show the photo,
     full matches first, and collects the **names** of the matching pictures (file names made
     readable by `image_name`) and pages;
  2. those names go to the **identification** ("a name that recurs is very likely this
     product's brand and model"): it now says "SUNS Marolo" with 0.95 where it said "Talenti
     Cliff" or "Tribù Mood";
  3. the best-guess label is **no query** any more;
  4. the image search's pages that name the recognised model go first among the candidates;
     when one does, the search by look is skipped (one search fee less);
  5. a candidate whose only picture is the one the image search matched (a category page shows
     it too) counts as "recognised" only when its title or address names the model;
  6. a picture's address is no product page: a search result that is a .jpg is dropped (it was
     shown to the customer as the recognised link);
  7. a recognised name loses the shop's suffix ("Marolo daybed - SUNS Outdoor Lifestyle" →
     "SUNS Marolo daybed").
- **Measured** on the 15 photos, whole flow (before → after):
  - the right SUNS product recognised: **2 → 8–11** (two runs; Gemini's same/not-same for a
    set in a mood picture varies); plus 2 recognised as another SUNS piece in the same mood
    picture (the Nova table with Dolce chairs, the Fiavè stool at the Basta table) and 2 offered
    as a "comparable" of the same collection; a wrong brand recognised: **1 → 0**;
  - the 4 phone photos: 0 → 1 (Marolo); the others stay on the photo's own estimates;
  - time: median 28 → 25 s; **cost**: €0.028 → €0.026 per photo for the search part, about
    €0.028 per suggestion with the final answer (ledger, 15 photos each).
- **Admin → Photo test** (`POST /api/admin/shop/photo-test`, admins only; `PhotoTest.tsx`):
  the customer's flow with every step's own result (Vision's labels, entities, names, pages,
  pictures and similar ones; the identification; the searches; each candidate's picture as a
  small thumbnail with its score; the pick; the final answer), the time and the cost. Nothing
  is kept: the photo lives only for the request, the result goes only to the admin's browser;
  the ledger gets the cost on a line of its own.
- **Final sizing settings** (11 October 2026): `suggest.final_model` and
  `suggest.final_thinking` independently configure the final configurator answer. The model
  stays Gemini Flash and thinking defaults to low; previously this call omitted reasoning
  effort and used Gemini's default. Its ledger entry is tagged `suggest final`. Global AI
  defaults and drawing reading keep their existing settings. Fake network tests check both
  the default and overridden settings and the ledger tag.
- **The box that stuck out:** while the customer waits (30–60 s) the button says "We zoeken je
  meubel op… (dit kan een minuut duren)". Buttons do not wrap (`.s-btn { white-space: nowrap }`)
  and the box was a grid whose one column grew to that line: the photo field, the link field
  and the button stretched past the panel and the screen at 1440, 1024 and 390 px, in
  Chromium, WebKit and Firefox (at 820 the line fits). Now the box's column is
  `minmax(0, 1fr)`, its button wraps, its answer card breaks long links, and the invisible
  file field lies over the photo box instead of beside it. `apps/web/e2e/suggest_layout.py`
  checks the three moments (photo chosen, waiting, answer) in the three engines at four widths;
  screenshots before/after in out/suggestfix/.
- **Tests** (no paid call): reading a raw web detection answer, picture file names, the order
  and the skipped search, a category page that only shows the photo, a picture as a page, the
  request (maxResults, JPEG) and its fee, the photo test's rights, steps and that no photo is
  written.
- **Not done:** Lens-quality matching of home photos needs another service; options with costs
  in QUESTIONS 74 (Vision Product Search over our own catalogue recommended to try first).

## ADR-113 — A price list from Excel as fixed prices in the draft

The owner (9 Oct 2026): "I have a price list in Excel; these are retail prices incl. VAT. Can I
upload this Excel somewhere so you set these prices as fixed prices for the current covers?"
(Numbered 113: ADR-112 went to the photo search on main while this was built.)

- **Where:** Admin → Prices & costing → Channels & price lists → **Import prices (Excel)**,
  admins only (`POST /api/prices/import` to look, `POST /api/prices/import/apply` to write;
  editors 403, viewers 403). Code: `apps/api/coverapi/prices_import.py`, the endpoints and
  `import_draft()` in `prices.py`, the page `apps/web/src/PriceImport.tsx`.
- **Reading** reuses the product list's careful reader (ADR-091: .xlsx/.csv/.zip, openpyxl,
  zip path and size limits, `products.max_files`/`max_bytes`, header = first row with two text
  cells). Every upload is kept as `prices/imports/<stamp>-<name>`; looking again with other
  choices reads the kept file by its name (no paths from the client).
- **Money as people write it:** "€ 1.234,95", "1,234.95", "1234,95", "€ 459,-", "EUR 249" and
  number cells; the last of "." and "," is the decimal mark, a single separator before three
  digits in a valid grouping is thousands. Prices are taken to the cent.
- **Columns by content:** the price column is the one most cells of which read as money, with a
  head start for a header saying prijs / price / retail / verkoop / incl and a penalty for
  code / number / size headers and for 1, 2, 3 row numbers. Incl. or ex VAT: incl. by default
  (the owner's case); a header saying "excl" / "ex BTW" turns it to ex; a person can switch.
  The identification columns are those naming a cover in ≥ 10 % of the rows. All three are a
  person's choice on the page (`--price-column`, `--id-column` in the CLI).
- **Matching, conservative:** *exact* = a drawing cover's code, folder name or drawing order
  number ("Cover 66", through `products_sheet.drawing_keys`), a cover's own name or id ("SUNS
  2 Seater Kota"), a drawing cover's product name from its products.json, an arrangement's
  name, the balloon or the frame. *Probable* = SUNS models named by a description with a family
  and a type in common, same shape, left never for right (`products_sheet.suns_for`), and the
  SUNS models the product list links to a drawing cover matched by code (only when that cover
  carries one product: a code shared by two products links both, which says nothing).
  *Ambiguous* = the columns name different covers, or a family without a type (candidates are
  offered). Rows naming a configurator product are reported, never priced: their price follows
  from the sizes. One cover, two prices from two rows: an exact match beats probable ones;
  otherwise the cover is left out until a person picks the row. The page sends only what to
  leave out and what was picked; the server matches the list again.
- **Exact VAT conversion:** a fixed price is stored in the channel's own unit (B2C incl. VAT,
  B2B ex VAT, `show_vat`). A price given incl. VAT into an ex-VAT channel is stored as
  given ÷ (1 + VAT) with six decimals, and `costing._price` no longer rounds a fixed price to
  cents *before* adding VAT, so the price incl. VAT comes back as the sheet's to the cent (a
  test runs a thousand prices both ways). No channel rounding on a fixed price, as before.
- **Draft only:** the prices are added to the draft (or to a new draft from the live set) with
  the note "Imported from <file> (N prices, B2C)"; the draft keeps the note through later
  saves and Publish uses it when no other note is written. Audit log: `prices imported to
  draft`. Never published automatically; the published set is untouched until Publish.
- **The shop follows:** the consumer shop sold an existing (stock) cover at its configurator
  price minus the stock discount and ignored a B2C fixed price for that model. A fixed B2C price
  for the stock model now wins (no discount on top), as ADR-098 meant (`costing.fixed_price`).
- **CLI:** `scripts/prices_import.py FILE [--channel] [--incl-vat|--ex-vat] [--json] [--apply]`
  prints the same report (a table, JSON with --json) and writes the draft only with --apply.
- **Speed:** `prices.Facts` reads the yaml once instead of once per cover (a list of a hundred
  covers took 0.16 s per cover only to read the defaults).
- **On the way:** an unclosed rule in desk.css (`.q-owner .d-btn {`, from the ADR-111 merge)
  nested the whole studio stylesheet inside it, so the built studio showed unstyled pages; it
  is closed. The channel cards on a phone could not shrink below their content (536 px wide
  page); `min-width: 0` lets their tables scroll inside.
- **Better later:** a per-row confirmation memory (aliases learned from hand picks), the
  supplier's article numbers once the covers carry them, price lists per colour or quality.

## ADR-114 — Approved drawing covers offered as existing covers

The owner (9 Oct 2026), option a: every drawing cover whose Desk status is approved (or
produced) is also offered by the configurator as "we already make a cover that fits", with the
kind of furniture from the product list. Later the same day: the retail price list he uploaded
(Import prices, ADR-113; sheet "SUNS Covers", column "Type nr." = our drawing code) is the main
source for the kind, before products.json and the shape.

- **Which covers:** drawing-* folders with Desk status in `match.drawing_statuses`
  (default `approved,produced`). A cover rejected later drops out at once: the card cache
  (`match.cards`) is stamped with the newest change of every drawing cover's desk.json,
  cover.json, products.json and model.json, and with the price list's file and time.
- **The kind, first that says something** (`engine/coverengine/match_drawings.py`):
  1. a person's word: `"match": {"kind": ..., "side": ..., "chairs": ...}` in the cover's
     cover.json (`"none"` keeps it out); it also confirms a doubtful cover;
  2. the price list (`apps/api/coverapi/match_list.py`): the newest kept list in
     `prices/imports/` with a drawing-code column. One-cell rows are headings: a section
     ("Corner sets", "Dining tables": words like sets/tables/items) or a family ("Kota / Aspen/
     Evora"); a one-cell row with a colon continues the row above's "Suitable for". `#VALUE!`
     cells are ignored. The kind comes from the item name ("corner set left", "loungechair",
     "2-seater sofa bench", "Ibiza style", "dining tables" + Ø → round), else from "Suitable
     for" and the section;
  3. the product names linked from the uploaded product list (products.json labels, ADR-091);
  4. the shape: an L is a corner sofa, a round one a round set, a sloped box a sofa (a chair
     below 150 cm), a flat box at chair height as wide as a table with chairs a dining set.
  Nothing says it: unknown, not offered. The category in the live cover.json is not touched;
  the derived kind lives in the card and the review list.
- **Doubtful, not offered until confirmed:** sources that disagree (price list, product names,
  a clear shape); the price list's sizes that are not the cover's (that row is then not used:
  the list's D6 is the Blocchi hocker, drawing-d6 the Blocchi daybed); left/right disagreeing
  between the item name, the product names and the plan; a U/C shape (Rios) or a curved/free
  shape for a sofa; Ibiza style (a corner and a sofa in one row); one code on two approved
  covers (S10 box and plain, L4).
- **Sizes as the SUNS cards (the furniture, not the cover):** the drawing's cover minus
  `hull.clearance_mm` on each side and on top. A dining or round cover over table and chairs
  gets the table's own size (from the list's "Tables 340 x 100 cm" / "Ø 170" or the product
  name, else the cover minus `hull.chair_room_mm` per side) and its height is a ceiling
  (`height_max`): any table lower than the cover fits under it (no score lost on height). The
  price list's size check allows `match.drawing_size_tol_cm` (3.2) and, for tables, a table
  size smaller than the cover by the chair room.
- **Left and right:** the item name ("corner set left"), else the product names, else the plan:
  every drawing named left is longer along x (C12, C15, C18, C21, C25 …). "Suitable for" is not
  used for the hand (it names the modules' hands). Left and right in one folder (a mirrored
  pair) fits either hand.
- **Families:** "Suitable for"'s families (Kota, Aspen, Evora) are on the card, with the SUNS
  models of those families and the same kind (`suits`). `match.match(hint=...)` puts a drawing
  cover of the named family first among equal scores; the photo/link suggestion passes the
  recognised product's name.
- **Shop:** `stock_model` is `^(suns|drawing)-…` (shop and B2B; the admin's Matches choice too).
  The customer sees the price list's name ("SUNS cover corner set left – Savona with arms /
  Siena : …"), else the product list's name, never the folder name. Price: the published B2C
  fixed price for that model when set, otherwise the configurator's price for its sizes minus
  `stock_discount_pct`, as SUNS covers. The configurator's sizes for pricing are clamped to its
  field ranges (a 420 cm table is priced as 400). The B2B catalogue lists offered drawing covers
  too.
- **Review list:** `scripts/matchcards.py` writes `out/matchcards/review.json`, `review.csv`
  (model, kind, how it was decided, sizes, side, chairs, doubts) and `listing.json` (the price
  list as read, and the rows it could not place: no cover, not approved, other sizes,
  umbrellas). Read-only.
- **First run (9 Oct, live data read-only):** 76 approved, 62 offered: 20 corner sofas, 13
  sofas, 12 chairs/side tables/hockers, 7 dining sets, 7 round sets, 3 loungers. 14 doubtful.
- **A row the list gets wrong (15 Oct 2026, QUESTIONS 74):** Rens: "D6: hocker of daybed? →
  Onze hoes is goed: daybed (prijslijst aanpassen)". The uploaded Excel stays as it is;
  `prices/list_corrections.json` corrects a row by its code (`coverapi.match_list.correct`:
  section, item, suitable, size; `was` names what the row must still say, so a newer list that
  fixed it wins; `why`; an optional `doubt` keeps the cover off the shop until a person
  confirms with `match.kind`). Every reader of the list follows: the match cards, Links' names
  (no "hocker" type for D6), a cover's Price & shop, the agent API. D6 now reads "Suns cover
  daybed – Blocchi daybed", kind lounger (the configurator's daybed), category Daybeds. Its
  published fixed B2C price, €249, came from the hocker's row (ADR-113 import): the doubt
  keeps D6 unsold until the daybed's own price is set. Test:
  `test_a_corrected_price_list_row_makes_d6_a_daybed`.
- **Better later:** the customer's own hand for Ibiza-style and U-shaped sets in the
  configurator; a family question in the configurator itself; the customer-facing name per
  language (the list is in English).

## ADR-115 — Arrangements are approved at the Desk; an approved one never changes silently

The owner (9 October 2026): "set the arrangements ready in the Desk; that must be the workflow,
so that Rens or Wout approve them." Arrangements (ADR-089) already appeared at the Desk as
models with status "new", unnamed and without a way to send them or to see what was placed.

- **The workflow:** built on the Arrangements page → **Send to the Desk**
  (`POST /api/arrangements/{id}/send`, the `edit` right; refused while its cover is building or
  when nothing is built) → status `ai-checked`, shown for arrangements as **Ready for approval**,
  with `sent` = who, when, `announced` in desk.json and a history entry "sent to the Desk" →
  approved / rejected at the Desk by the approvers, as any cover. No new status: the queue's
  counts, the pipeline bar and the undo work unchanged. A second click changes nothing.
- **Never silently changed:** an approval of an arrangement records the cut file's fingerprint
  (sha256 of cut.dxf) and its placement (members, places, gap, plan; `arrange.placement`).
  - Building it again from the Arrangements page with another plan, moved, added or removed
    members, or a member whose furniture changed puts it back to waiting with "changed after
    approval: …" (from rejected: "changed after rejection"; while waiting: "changed while
    waiting", a note only). A new name alone is not a change.
  - Any other change of the cut file (a rebuild from the model page, a Desk correction) is
    found by the fingerprint: the queue, the card and the Arrangements page reopen it with
    "changed after approval" by "the studio", and the DXF gate refuses it at once.
  - Reopening clears approved/produced/rejected, marks it sent again (so the digest lists it
    again) and sets the catalogue status back to draft.
- **The DXF gate:** `desk.gate_arrangements: true` (new key) gates every `arr-*` model on its
  approval whatever `desk.gate_scope` says; false: arrangements follow gate_scope like any
  model.
- **At the Desk:** the series chip **ARR** (with a count), the arrangement's own name as its
  code, an ARR tag instead of AI scores, `GET /api/desk?scope=arrangements`. The card shows,
  in place of the drawing, the plan from above (`arrange.plan_view`: each member's rectangle
  and the chosen footprint's outline; follow and box exactly as the cover is built, smooth as
  the convex hull plus the clearance), the members with picture, size, place, turn, mirror, a
  link to their own model and Desk card, "changed since" per member; a status bar (waiting,
  approved by, rejected and why, waiting again after a change); "The arrangement" facts in
  place of what the program read; no AI panel and no "Let the AI read it". The 3D viewer
  (Measure, Vent sizes), pieces, check list and history as for every cover.
- **Mail:** the arrangements sent and not yet announced go to the approvers in the Questions
  digest (`questions.question_mails`, once per `questions.digest_hours`), one section
  "opstelling(en) wachten op je goedkeuring" with links; never a mail per click.
  `desk.approvers` gains "wout" (Wout logs in as wout; "wouter" did not match him).
- **The existing arrangements:** `scripts/desk_arrangements.py` (dry run by default,
  `--apply`, `--only`, `--by`) puts every built `arr-*` that is new or waiting without a
  sender into "ready for approval", keeping desk.json and its history; approved, rejected and
  already sent ones are left alone.
- **Tests:** `apps/api/tests/test_desk_arrangements.py` (queue filter and names, the card's
  plan, send rights and repeats, the gate and its switch, reopening on a changed cut file and
  on a change after approval or rejection, the change words, the digest once);
  test_arrangements.py builds, sends, approves and rebuilds with another plan through the API.
  Browser: `apps/web/e2e/arrangements_desk.py` (send, ARR filter, card, approve, DXF, change
  after approval, phone width).
- **Also fixed:** on a phone the Desk overflowed by 8 px (its margins assumed the desktop
  gutter, and the fit row did not wrap).
- **Better later:** the smooth plan drawn from the built cover's own outline; a per-member
  check that the arrangement's pieces still match the member's latest cover.
- **Approval safety (2026-10-11):** approving an arrangement without `cut.dxf` returns HTTP
  400 before saving any approval. A missing or null approved cut fingerprint counts as a
  changed cut file, including before the first build; legacy approvals require fresh approval
  before the DXF can be downloaded. Regression tests cover both cases.

## ADR-116 — Rens's answers on the drawing covers (9 Oct 2026): shapes read again, a person's vent count kept

Rens answered the drawing questions at the Desk (Questions tab, ~/cover-data/answers-2026-10-09.json).
Each cover was rebuilt in staging (`out/answers/<model>/`), checked twice (`cover audit`,
`scripts/fewer_check.py`) and looked at against the drawing (`out/answers/compare/`).

- **Shapes, per model** (`testdata/drawing_shapes/*.json`, built by `scripts/given_build.py`):
  - D5 (Q4, "the outline does not match the drawing at all"): read again view by view. A 198 x 94 cm
    rectangle with a half round of radius 99 cm (the full width) centred 94 cm from the back; one
    slope from the strip (84 cm, 30 cm from the back) to the 40.01 cm front; ends leaning in 10.01 cm
    from 59 cm walls. Every written size comes back: 193.99 (the back wall's top), 177.98 (the
    strip), 195.32 at 110.22 cm and 62.35 cm there. Yesterday's "the sizes do not make one surface"
    was a misreading (the round's centre is at 94 cm, not its start).
  - S20 (Q5) and S48 (Q11): the arms followed, the seat between them one panel falling from the top
    of the back (84 / 89 cm) to the seat's front edge (40 / 43 cm), as the Blocchi reference; the
    arm insides meet it in a line that falls to the front, so water runs off (rule 12). `faces`.
  - S21 (Q6): the 30-degree bend Rens chose (the drawing's lines measure 40; its 149.78 cm front
    edge belongs to 40, with 30 the front edge is 159.9 cm).
  - S37 (Q7): depth 102.1 cm, the straight part 50.65 cm.
  - S38/S39 (Q8): the front wall's top falls from 59.9 cm to 40.1 cm at the slanted side (the
    36.4 in line and the 15.80 in on the side view), so the top panel tilts out two ways: one ruled
    panel, 0.11 % stretch.
  - S25 (Q14): the profile from the side view (back 62.99, chamfer to 88.6, a 31.02 cm strip, a
    slope to 62.99 at 95.52 cm, a steeper front face to 40.01 at 120 cm; the live cover had a flat
    top to 95.52 cm and one slope), hipped ends from the written line lengths, 10 pieces; 5 vents.
- **General causes, each with a test:**
  - *A word number inside another word* (`drawing_vectors.VENTS`): "Max Height Air Pocket" was read
    as "eight air pocket", 8 vents on S20 (the drawing draws 4 arrows). A number before the label
    must be a word of its own. Swept over the 120 drawings: only S20 changes.
  - *A join that breaks a seam* (`drawn_merge.merge(..., seam_mm)`): S25's slope and front face, two
    cone bands at a 13 degree fold, were joined at 0.8 % stretch, which made the front seam 7.5 mm
    longer than the wall (over the 5 mm fit, the audit failed). A join is now refused when any
    stretch of the joined piece's outline between two corners changes length by more than
    `tolerance.cover_mm` flattened (`rim_change`). S43 keeps its joins.
  - *A count a person decided is kept* (`drawing_route.person_vents`): `vents_total` in
    drawing_corrections.json or in the shape a person read wins over the reader on every rebuild
    (C24/C25 9, Q67: the drawings read 7; S25 5); the reader's count stays as `vents_read`. The
    audit's new *decided vents* check fails a cover asking for another number.
  - *A free edge in a hip shape* (`drawing_given`, `free`): an outline edge with a wall but no
    profile of its own, whose rim follows the other planes (D5's round front).
- **Vents only:** R1–R3 (Q13) `features.vent_align: top` in cover.json (60–82 cm, the top 5 cm under
  the top seam); C24/C25 (Q67) 9 each, by the rule (ADR-101/110) they land on Rens's circles (two on
  the long front wall, one in the middle of the short one; C25 the mirror).
- **Not changed:** S47 (Q10, "leave as it is"); S45 (Q9 "152.4 cm, not 358" against Q57 "358.4 cm
  round, as now": contradictory, to the owner).
- **Not done:** the vertical drawstring openings (D5, S38, S39); S25's end walls slope from 63 to
  40 cm under the hip (the drawing draws them level at 40 cm with the hip rising from there) —
  the swept builder's hip keeps the back and front edges full length; R1–R3 still fail the audit's
  balloons check (a table without a balloon, as live).


## ADR-117 — Rens's answers of 9 Oct on the SUNS covers: box tops cut to the roll, straight wall tops, a no-cover mark

Rens answered the Desk questions about the SUNS covers rejected on 8 Oct (questions 1–3, 12,
15–23; ~/cover-data/answers-2026-10-09.json, the latest answer per question). Each cover was
built again in staging (`out/answers/<model>/`, `scripts/answers_stage.py`), checked twice
(`cover audit`, `scripts/fewer_check.py`) and looked at next to Rens's marked picture
(`out/answers/compare/`). Results per cover, with the answer to Rens in Dutch, in
`out/answers/results.json`. Nothing is replaced live by this change.

**General rules (ADR-055: a rule, a test, an audit check and an AI lesson each).**
- **A box top wider than the roll is cut into strips** (question 16, the Portofino daybed's
  1.85 m top). The arrangements and the follow covers already did this; a plain (convex) box
  cover only reported it. Now the hull step draws lines across every too-wide top face's slope
  (`hull.json` box.roll_cuts) and the cut splits the piece there after its gentle-fold joins, so
  the seams run downhill and a join never undoes a split. Test:
  `test_a_box_top_wider_than_the_roll_is_cut_in_strips`.
- **Gentle folds on follow covers too** (the Nuna's 10 degree gable stayed two pieces). The
  ADR-099 join now also runs on a follow cover's flat top faces (and on a model built from its
  parts' plan, below); its walls, curved round the outline, keep their seams. The audit's
  *gentle folds* check leaves out pieces that bend more than the limit within themselves (a
  follow cover's rounded corner is no pair of flat faces: the Fiave L-part was flagged falsely).
- **A join made at the Desk is a fold in pen** (ADR-082's `part_edits.json`): two flat pieces a
  person joins get the same FOLD line as the engine's own joins (the Sato bench, question 18).
- **Creases as seams only for organic covers** (question 19, S53 and S60: "for covers with an
  organic shape like these, which have curved seams, follow the drawing; not for all covers").
  `seams.given_crease_deg` is 0 by default; the new family preset `organic`
  (`config/presets/organic.yaml`) sets 20 and S53/S60 join it with `"family": "organic"`.
  The rule-13 clash (their front seam is not level) is thereby accepted for this shape type
  only.
- **No cover** (question 12, the Portofino daybed with roof): `"no_cover": true` (and
  `"no_cover_reason"`) at the top of a model's cover.json. The model stays, but the shop's
  matching (cards, existing covers, similar covers, B2B, photo suggestions, drawing covers)
  never offers it and the Desk leaves it out of its queue and refuses approve/reject/produced
  (409); `cover report` counts it as "no cover". Set with `cover model DIR --no-cover yes
  --no-cover-reason TEXT` or `PUT /api/models/{id}/info`; the studio's list shows a badge.
  Marking does not make any step run again (stepcache). Tests: `engine/tests/test_no_cover.py`,
  `apps/api/tests/test_no_cover_api.py`.

**Per model, by hand (the owner's answers "only for these models"):**
- `seams.straight_wall_tops` (questions 22 and 23, Sorrento 2-seater, Avero 2-seater, Sorrento
  3-seater with corner): every wall's top edge one straight line from corner to corner. The
  box's shape stays; the part of a wall above that line goes to the roof pieces as flaps folded
  down, split by an upright seam under each kink (`hull/hand.py` `straight_tops`). Every piece is
  flat faces joined along edges, so it lies flat exactly. A real straight top edge with a ridge
  meeting the wall in its middle cannot be made of flat faces (two planes that meet a wall in
  one line are one plane), so the ridge stays the box's own.
- `hull.box_extra_faces` (question 3, the Nuna: "a chamfer instead of a bulge"): faces added by
  hand to the box as outward directions ("0 1 1" = a 45 degree chamfer at the back), each just
  clear of the furniture, mirrored on a symmetric cover.
- `plan_members.json` (question 21, the Vento lounge: "redo it, like the other L covers"): one
  model built like an arrangement (ADR-095) from its parts' plan rectangles, given by hand in the
  model's frame: an L with a square inner corner, each arm's top sloping to its own front.
- `box_shape.json`: a box cover given piece by piece, corner by corner (twisted quads become
  ruled patches), checked like any cover (furniture inside, water on a height grid, the roll);
  for an approver's layout no rule can make. Not used live yet; tested.
- Plain per-model settings: Portofino 2-seater `features.vents_total: 4` (question 15: one vent
  per long side for this cover; the company rule stays one per full metre); Sato bench
  `part_edits.json` joining the 10 cm strip to the top (question 18: "one top panel of about 94
  cm with a fold line"; `seams.fold_join_max_deg` 30, the option's wording, would also have
  joined the 24 degree back slope, so the join is made by name instead).

**Doubt, to the owner:** the Vento angled 2-seater (question 1). Rens's sloped seam from the
back ridge down to the front corner makes a hip at the angled end; a flat face through those
lines passes 15 to 20 cm inside the end's back cushion (82–86 cm high right next to the end
wall), so it cannot be built as drawn without the cover cutting into the furniture.

**Better later:** a ridge that meets a wall's straight top edge in its middle (twisted roof
pieces, `box_shape.json`) where a person draws it; the gentle-fold join for arrangements too
(their approved covers would change, ADR-115); an angled member in `plan_members.json`
(rectangles only today).

## ADR-118 — An existing cover is ordered directly: its own name, price and delivery promise

The owner (9 Oct 2026, preview): "I chose an existing cover, 'SUNS cover dining tables – Table
240x100', it fits 100 %, but it still shows the price of making it custom. It should say ORDER
DIRECTLY! with the right price; in this test version it may also say 'ordered today, delivered
tomorrow'." (Numbered 118: two branches already claim 116.)

- **Why he saw the custom price:** the stock choice did reach the server and took the stock
  path (his quotes `44118ff3…` and `d9dce5dd…`, 18:57 and 18:58, carry `stock_model:
  drawing-t10`). But the price list was only in the draft (published at 18:59), and
  `stock_discount_pct` was not set, so the stock price was the configurator's price for that
  cover's own sizes: € 1 368,95, to the cent the custom quote for 240 × 100 with chairs (the
  chairs' height decides the cover, not the table's 86 cm ceiling). And the page showed both
  the same way: "Total", pieces, m², "Order". After publishing, the same quote gives € 849 (the
  fixed B2C price; checked on a scratch copy of the live data). Also found: a custom quote still
  on its way could overwrite the stock one (no abort), and while the stock quote loaded the old
  custom price stayed on screen; both fixed.
- **The existing-cover state:** with a stock model chosen, the configurator shows a green card
  instead of the size sliders and the made-to-measure price: the badge "Bestaande hoes uit ons
  assortiment", the cover's own name, "Past op 240 × 100 cm, tafelhoogte tot 86 cm", "Prijs van
  deze hoes, incl. btw" with its price (a "with N % off" line only when the discount made it),
  the delivery promise, a large **Bestel direct** button and "← Op maat laten maken". Nothing
  about pieces, m² or made to measure; the vents box is hidden (the cover comes as it is made;
  the quote is asked with vents on). The price is shown only for a quote that belongs to the
  current choice (`quote.stock.model_id === stock`); a stale answer is aborted.
- **The quote** (`/api/shop/quote`) returns `stock.size_cm`, `height_max`, `price_source`
  (`fixed`: the published B2C fixed price; `stock`: the configurator's for its sizes minus
  `stock_discount_pct`), `discount_pct` and `price_eur`. A published fixed price is not
  indicative (`price.indicative` false). A fixed price only in the draft is never sold.
- **Delivery promise:** shop setting `stock_delivery_note` (text per language, Admin → Shop
  settings; empty = hidden, the default on the live shop). Public settings carry only the
  languages that have a text. Shown only for existing covers (configurator, checkout, thanks),
  never for made-to-measure ones, which have a production time. The preview sets it in
  `apps/site/preview-overlay.json`: "Vandaag besteld, morgen in huis" / "Ordered today,
  delivered tomorrow" / "Heute bestellt, morgen geliefert" / "Commandé aujourd'hui, livré demain".
- **Checkout and order:** the checkout is titled "Bestel direct" with "Bestaande hoes: <name>"
  and the promise; the order stores `stock` (model, name, sizes, price and its source), the
  answer and the status page name the existing cover, the thanks says it is an existing cover
  from our range, and the staff mail says "EXISTING COVER <name> (<model>)".
- **Tests:** `apps/api/tests/test_shop_stock_order.py` (stock quote = fixed price, custom quote
  differs; draft price not sold; the setting; the order); `apps/web/e2e/stock_order.py` in a
  real browser at 1440 and 390 px (screenshots in out/stockorder/).
- **Better later:** a stock count per cover (the promise only while it is on the shelf); the
  furniture's photo on the card; the customer's colour checked against what is in stock.

## ADR-119 — Covers for premium barbecues: the configurator's BBQ option and BBQ catalogue covers

The owner (11 Oct 2026): "in the new version, also an option for covers for BBQs; research the
best-selling luxury BBQs (Big Green Egg etc.) — we are a premium cover, so premium products;
load all these models and make a proposal for a cover." Research and the ranked list:
docs/plans/bbq-covers.md (Dutch summary) and docs/plans/bbq-covers-research.md (sizes, sources).

- **Off on the live shop until the prices are set** (the coordinator, 11 Oct 2026: the provisional
  costing gives about €475 for a kamado cover and €880 for a gas-grill cover, the makers' own cost
  €45–240). Shop setting `bbq_enabled` (default off, Admin → Shop settings): off, the shop's and
  B2B's options, quotes, matching, the B2B catalogue and the public API (ADR-061) have no
  barbecues; a BBQ product is refused as unknown. The preview website always has them: a
  request through the Worker's key from a `preview.` host (`shop.bbq_on`), and
  apps/site/preview-overlay.json sets `bbq_enabled` for the page. The photo suggestion offers
  furniture only (`quote.FURNITURE`).
- **A cover goes on a cold barbecue.** Acrylic canvas is not heat-proof; the shop says so in
  every language (`bbq_cold`), the proposal carries `cold_only`. The room under the cover is for
  handles, thermometers, hinges and the top vent, not for heat.
- **The configurator (shop and B2B):** five products with `"group": "bbq"` in
  config/quote_products.json, shown under their own chip ("Barbecue") above the cards
  (`apps/web/src/shop/ProductCards.tsx`): kamado in a nest (egg diameter, height lid closed,
  depth handle to hinge, optional side tables and their width), kamado in a table, gas grill
  with side shelves (width, depth, height, shelf height, hood width), pellet grill (width, depth,
  height, lid length), fire table or plancha (diameter or width, height, optional square/oblong
  with its depth). Defaults are the best sellers (BGE Large in nest, BGE Large acacia table,
  Weber Genesis E-335, Traeger Ironwood, OFYR Classic 85).
- **The barbecue in 3D** (`coverengine/bbq.py`): one builder per kind from the sizes (egg on a
  nest with handle, hinge, top vent, EGG Mates; cart, hood, handle bar, shelves; barrel, hopper,
  shelf; plate on a cone or a square table). The same builders make the catalogue models.
- **The cover:** a round band with a cone on top (a kamado alone, a round fire table; drawn shape
  `cone round`: cone sectors laid flat exactly, as many band strips under their seams, ADR-107's
  round logic) or a box with a hipped roof (all others; `hip box`, all eight pieces flat). Its
  sizes come from the barbecue's own points plus `quote.ease_cm`; of the roof slopes between
  `quote.bbq_slope_min_deg` (12.5) and `quote.bbq_slope_max_deg` (30) the one with the least
  fabric, the walls at least `quote.bbq_wall_min_cm` (35) high for the vents. Every point of the
  top slopes: water runs off (rule 12; the rain check confirms it, no balloons offered).
  Vents, drawcord and price by the existing rules and costing.
- **Matching:** catalogue covers `bbq-<brand>-<model>` (`match.bbq_card`): offered once their
  Desk status is in `match.drawing_statuses` and cover.json says `"match": {"kind": "bbq_…",
  "name": "Big Green Egg Large in nest", "families": [...]}`. Their size card is the barbecue's
  bounding box, and the customer's sizes are measured the same way (the configurator builds the
  barbecue and takes its box: `bbq.plan_cm`). The shop's `stock_model` accepts `bbq-…`.
- **The family preset `config/presets/bbq.yaml`:** box top, `hull.clearance_mm` 20 (to confirm),
  no chair space, no support. Kamados and round fire tables `hull.plan: round`; the others
  `hull.plan: box` per model (a BBQ cover is a straight box; following the shelves' outline gave
  a curved hem for 3 cm of fabric).
- **Two engine fixes found on the way, each covered:**
  - *Gentle folds on a "follow" plan* (`hull/outline.py`): faces meeting at a fold of at most
    `seams.fold_join_max_deg` were joined only on box plans, while the audit asks it of every box
    cover; the follow plan now joins them too. None of the 18 live follow covers fails the
    audit's check, so none changes.
  - *A cone's sectors* (`audit.fold_checks`): two sectors of a round top meet at a near-zero fold
    but never lie flat as one piece; the audit no longer asks to join them (a small round cover,
    the BGE Large's, fits the roll in one and was flagged).
- **Staging (`scripts/bbq_models.py`, out/bbq/):** 27 barbecues of the top 25 built, covered and
  checked twice (audit and fewer_check); BGE Large's egg is a 3D Warehouse model scaled to the
  published sizes, the Weber Genesis II EP-335 a 3D Warehouse model as modelled, the rest drawn
  from the published sizes (estimates listed per model in its notes). Not imported live: the main
  session does that after review.
- **Better later:** lid-open and folded-shelf variants; a kettle (Weber Master-Touch) and the
  OFYR Island; measuring the Kamado Joe carts (the maker and the shops differ by 10–17 cm);
  pricing BBQ catalogue covers from their own pattern rather than the configurator's shape.

## ADR-120 — Drawing approvals belong to the cutting file

A drawing cover's Desk approval now records `cut_fingerprint()` in `approved.cut` and retains
an `approved_fingerprints` list. Current DXF downloads require the approved fingerprint to
match. A changed or missing cut after a recorded approval reopens the cover to waiting, with
history and catalogue status draft, as for arrangements (ADR-115). Revision downloads require
that revision's fingerprint to have been approved at some point, independently of current status.

Earlier approved/produced drawing covers are grandfathered with their current cut fingerprint,
once, on first read or through `scripts/desk_fingerprints.py --dry-run|--apply`. The history says
“fingerprint recorded for an earlier approval”; older different cuts are not inferred approved.
A missing current cut cannot be grandfathered. New approvals require a built cut. Gate settings
and the logged admin override still apply. Migration validation uses temporary fixtures only.

2026-10-11: On-demand size drawings are published atomically after PDF completion and branding; definitive approval refuses PDFs with no pages with HTTP 400 before recording approval (ADR-080).

## ADR-122 — The studio's new layout: five sections, every page and tab in the address, one Settings area

The owner (9 Oct 2026): "the backend is messy; too much information in too many places; it
must be tighter and clearer; sub-menus can help, and an admin page where most settings are, on
tabs with more explanation." The audit and proposal (docs/plans/studio-ui.md, prototype in
out/uiaudit/prototype/) were made on 11 Oct; that night the owner said to build the logical
layout now, decide what I can decide, keep business choices as they are, and consult Codex.
(Numbered 122: 120 and 121 are taken on other branches.) Built: steps 1, 2, 5 and 6 of the plan.

- **The map (`apps/web/src/nav.ts`):** one table of sections, pages, who sees them, the
  Settings tabs, a cover's and a Desk card's tabs; `redirect()` and `parse()` are pure
  functions, so the browser check and the code use one list. Five sections in a one-line header
  (Work · Covers · Shop · Prices · Settings) and a sub-menu bar under it; Admin and Website left
  the user menu. Hash routes stay (no server change, the old links are hash links too).
- **Every old address redirects** (`#/`, `#/desk[/id]`, `#/questions[/n]`, `#/catalogue`,
  `#/arrangements[/id]`, `#/learning`, `#/prices`, `#/website`, `#/admin[/tab]`, `#/model/<id>`
  and its old tab names) with `history.replaceState`, so Back does not bounce. The mails
  (approval request, question and answer digests, the arrangements' digest) link to the new
  form. Table: docs/handbook/navigation.md.
- **Start page per person, existing roles only:** an approver at the Desk (`desk.approvers` or
  an admin, now in `/api/auth/me` as `desk_approver`) or a user with *may approve* starts on
  Work → Desk; an admin on the section page he used last (remembered in the browser, Codex's
  advice); the rest on Covers → All covers. Open owner question 3 stays open.
- **Tabs in the address:** a cover `#/model/<id>/<tab>[/<sub>]`; the bug where the next cover
  opened on the tab of the one before is gone because the tab is no longer component state.
  A Desk card `#/work/desk/<id>/<tab>`; the Prices tabs `#/prices/<tab>`; Settings
  `#/settings/<tab>`. Moving between a card's tabs keeps the queue's filters (the Desk stays
  mounted).
- **Settings (step 2):** Users & rights, Mail & notifications, Logins & audit log, System and
  Website & API keys moved in unchanged in function; the raw Shop settings form (49 bare keys,
  `0 / 1 / 2`, a free-text enum) is rebuilt from a small schema (label, one line of help, kind,
  unit, the company default that applies while empty) over the **same stored keys** (PUT
  `/api/admin/shop/settings` with only the tab's top-level keys; no data migration): Company &
  shop, Matching, and parts of Mail and Website. B2B terms moved from the B2B page (same API).
  Every row shows default / changed / empty, or the company default that applies; *Only changed
  values*; one sticky Save + Undo per tab. Every mail recipient is in one list (request mail,
  alert address, new orders, the fit question, approval requests, digest timings). The Mollie
  key is shown masked with *Replace* and sits with the other connections. Desk & approval, Cover
  defaults and AI & spending show `config/defaults.yaml` read-only (owner-editable defaults are
  step 4, which needs the owner's list, Q5).
- **The Desk card (step 5):** four tabs (Check · Pieces & revisions · Correct this cover ·
  History), a sticky bar (Approve, Reject, Comment, *After sewing ▾* with Produced, the note,
  Measured…, Fits, Does not fit; Undo), *More* (Let the AI read it, the check list, Edit
  arrangement, the cut pieces, the product list). Keys unchanged. The Check tab opens with the
  latest rejection and what happened since. The drawing and the 3D stay mounted on every tab
  (visible on Check and Correct), so *Snapshot 3D* works from any tab: the viewer now follows
  its box with a ResizeObserver and a snapshot of a never-shown viewer renders at 960 × 720
  (ADR-096's pictures, tested in e2e/desk_pictures.py). The product-list upload moved to Covers
  → Product list; the AI spend tile is for admins only.
- **The cover page (step 6):** one head (picture, facts, a status strip: grade, status, Desk,
  approval, DXF lock, "N changes since the run before"), Run again, Edit details (the catalogue
  info, folded), Desk card; the approval card (both approvals as they are: owner question 2),
  a running or failed job, a Desk rejection and today's warnings stay above the tabs. Seven
  tabs (3D · Pieces · Seams · Adjust · Compare · History · Files) with the old twelve as
  addressable sub-views. "Since the run before" moved to History without the `null → value`
  noise of new defaults. The 3D toolbar: Show ▾ (layers, named on the button; vents, vent
  sizes, dimensions; the hint), quick Vents and Dimensions, one Design · Rain · Drape · Unfold
  switch (Water beside it on the drape), Measure, Simulate ▾ (rain ≈ 1 min, drape ≈ 40 min, what
  runs shown beside it), Check list. Every old control is still there.
- **The look:** `studio.css` after `styles.css`: Work Sans everywhere, 8 px corners, 32 px
  controls (40 px on a touch screen), the near-black header, page heads; the Desk keeps
  desk.css. A full design system and dark mode for the whole studio (step 7) are not done:
  not cheap with the many fixed colours in styles.css.
- **Unsaved edits:** a form with changes (a Settings tab, shipping, B2B terms, Prices) asks
  before a link leaves it and warns on closing the tab; moving between the Prices tabs keeps the
  draft and does not ask.
- **Rights are the server's:** nothing in the API changed except the extra `desk_approver` in
  `/api/auth/me`; the menu only hides what the server refuses anyway, and a page for another
  role says "Not for your account".
- **Checks:** `apps/web/e2e/uinav.py` walks every section and sub-menu item for an admin, an
  approver, an editor and a viewer, every Settings tab, every old address, a cover's 13 views
  and a card's 4 tabs, the header on one line, at 1440 and 820 px, with screenshots
  (out/uinew/). desk_pictures, questions, measure, prices, priceimport, arrangements_desk, b2b
  and flow follow the new addresses.
- **Codex:** a second opinion on the plan (taken: an admin's remembered start page, Photo test
  under Shop → Tools, nothing buried above the tabs, quick Vents/Dimensions toggles, 40 px touch
  targets, secrets masked with Replace, unsaved-edit guards; not taken: Users & rights and Logins
  & audit log as one tab, since the owner named two) and an adversarial review of the branch
  (fixed: the Mollie key's Keep after a first save, a correction lost on a card tab change,
  Back/Forward past unsaved edits).
- **Not done (owner questions or later steps):** one approval (Q2), the workshop role and page
  (Q4), owner-editable defaults (Q5, step 4), one approver list (step 3), Dutch UI (Q1: stays
  English), Covers merged into one filter row and the search over everything (steps 8–9).


## ADR-121 — The scroll page all our own: rain drawn in time, the chapters and clips rendered from our data

The owner (9 October 2026): "the website looks much better, only when scrolling we still have
the static rain; the animation is much better — please make the animations further down
yourself too, so everything is based on our own material; then we can also make animations for
the scroll steps." Later that day: one more film, the cover at a villa on Ibiza over the sea.
(Numbered 121: 109–120 were taken on main meanwhile.)

- **The static rain, the cause.** The rain chapter is rendered pictures (ADR-071) that the
  scroll scrubs. Its falling drops were baked into the pictures (a particle system with motion
  blur), so they moved only with the scroll: standing still they froze, scrolling up they rose.
  RainLayer (ADR-106) only added rain on top, so the baked rain still showed under it.
- **The fix.** Nothing that falls is baked any more:
  - `render_story.py --no-drops` renders the chapter's pictures 300–360 again without the
    particles and without motion blur; the wet look stays (the canvas darkening in patches,
    beads on the coating, the backdrop turning green), because it follows the scroll plausibly.
    `story_frames.py` makes the set `story5-` from `story4-` with those 61 pictures replaced
    (the others byte for byte), plus `story5m-`: the upright 600 × 900 cut a phone shows.
  - `RainLayer.tsx` draws all the falling rain, by the clock, in the start film's look: near
    upright streaks the length a drop falls while a 1/48 s shutter is open, brightest at the
    head, three depths (the near one wide and soft, as out of focus), from three pre-rendered
    sprites; never backwards (a clock that steps back cannot lift a drop).
  - `site_rain.py` checks it in a real browser: no streaks in the pictures (a thin-bright-line
    detector: the old pictures 0.2–0.3 %, the new under 0.1 %), the rain moving while standing
    still, after scrolling away, after a background tab and on a phone, and — on a clock the
    test steps 16 ms at a time — each short streak's head found lower a frame later while
    scrolling up and while scrolling down (about 110 lower, 9–12 higher from meeting a
    neighbour's head; a rising rain would turn that round). Green against `story5`.
- **Storyboard 2** (docs/plans/scroll-site.md): the six chapters, the workshop cards and the
  closing film, all from the start film's scene parts (render_hero.py) and our data;
  `scripts/film/render_reel.py --shot NAME`, one shot a call, through `scripts/film/blender.sh`
  (Blender in the Playwright image, nice 19, a memory cap, a named container).
  - `reel_data.py` lays cut.dxf's pieces on the 152 cm roll (a bottom-left nest) and matches
    each sewn piece's flat pattern to its cut outline by the label inside it and by shape, so the
    pieces land exactly where the knife then cuts round them; it carries the vents onto the
    draped cover and reads the furniture's size for the dimension lines.
  - Memory: Blender's exact limit surface on the sewn cover took 5.4 GB per cover
    (OpenSubdiv's patch tables); without it (`lean()`) 0.8 GB, the look the same. Wide shots
    use the stitching picture at half size.
- **What was made** (CPU, nice 19, one render at a time; ~48 s a story picture, ~35 s a clip
  frame, ~63 s an Ibiza frame):
  - `story6-001…360.webp` (12.2 MB, 34 KB each) and `story6u-` (the 960 × 900 cut for upright
    screens, 7.0 MB): the six chapters of storyboard 2. `story5-`/`story5u-`: the old studio set
    with the rain chapter re-rendered without drops (the interim fix).
  - Clips, 720 × 900, AV1 + H.264 about 1.1 MB each, posters: `work-cut-1`, `work-sew-1`,
    `work-vent-1`, `work-fit-1`, `work-runoff-1`, `work-range-1`; the closing film
    `villa-ibiza1` (1600 × 900 AV1 2.8 MB, 1280 × 720 H.264 2.9 MB, 6.6 s).
  - The preview reads them from `apps/site/preview-overlay.json` (`story_media`). Until the
    studio's next release the live content still lists the old work items (measuring, cutting,
    sewing, delivering): cutting, sewing and delivering show our clips, measuring keeps the old
    clip; the new items (vents, made to measure, rain, our range) and the villa's words come
    with the release (content defaults).
- **On a phone** the story drew the wide picture filled, which showed a hand's breadth of the
  cover; it now shows the cut round the cover across the width above the caption, on a soft blur
  of itself (`StoryFrames.tsx`).
- **Checks:** `site_rain.py` green against `story5` and `story6`; `site_3d.py` green; the
  Worker's tests and typecheck, the web typecheck, prettier, `make test`.
- **Not yet as good as photographs:** the knife head in the cutting clip is a simple shape and
  out of focus; the vent's hood reads as a soft flap; the catalogue covers other than the Kota
  (the Sato lounger's drape sags into the seat, the Savona set is a box); the Ibiza light is
  flat and the sea pale. Real footage of the cutting table, the sewing machine, a vent and a
  fitted cover at a customer's would lift these most.

2026-10-12: The disk filled up: each nightly archive was 8.5 GB because it also packed the local
safety copies (cover-data/backup-*), and 14 were kept; the backup of 12 Oct failed. Now
`scripts/backup.sh` leaves out backup-* and logs (4.2 GB), keeps 5, writes to a .partial file,
first frees room for the new archive plus 20 GB (never removing the newest 2) or stops and writes
FAILED in last_backup.txt; the watchdog mails a failed backup and warns at 25 % free disk.
`scripts/housekeeping.sh` (cron 03:30) removes safety copies older than 14 days and release folders
beyond the newest 8 (never the current one).

## ADR-123 — Security fixes from the audit of 12 Oct 2026

A Claude + Codex audit found ten holes; the owner approved fixing them all. Each fix is the
smallest change that closes the hole without changing anything for a legitimate user, and each
has a test (`apps/api/tests/test_hardening.py`, `engine/tests/test_server_only.py`, and in the
B2B, Desk and security tests).

1. **Server-only settings.** A comment mark `[server-only]` in `config/defaults.yaml` (on a key
   or a whole section) makes a key settable only by the program itself
   (`Registry.resolve(server=...)`): the AI's `base_url`/`vision_base_url`, `spend.*`, the
   visitor limits and fees of `suggest.*`, and the new `limits.*`. A family preset, a learned
   rule, a model's `cover.json`, `--set`, a trial or the web app get a ParamError (400). The
   AI key is sent only to its provider's own https host (`ai.KEY_HOSTS`: api.deepseek.com,
   generativelanguage.googleapis.com), whatever the setting says.
2. **Learned rules**: the group is a strict slug (`learned.GROUP_SLUG`) and a known family
   preset or a group some cover has; the rules file resolves inside `learning/rules/`; the
   value is coerced by the registry (server-only keys refused).
3. **Request sizes**: Caddy has three walls (2 MiB default; 2 GiB for the logged-in upload
   routes; 40 MiB for the shop's photo routes); the app's pure-ASGI `bodylimit.BodyLimit`
   refuses a Content-Length over the route's own limit with 413 before anything parses it, and
   counts a chunked body. A test keeps the Caddyfile's routes and the app's upload routes equal.
   The access log drops X-Link-Key, X-Api-Key and Referer and redacts link tokens. Caddy 2.6.2
   has no log `mode` (it ignores unknown subdirectives silently), so the file mode is set once
   by hand.
4. **Decompression bombs**: `coverengine.safeimage.open_image` reads the size from the header,
   refuses over `limits.image_max_mp` (40 MP), makes Pillow's bomb warning an error and decodes
   a JPEG at 1/2–1/8 scale where that keeps it under the cap (a 48 MP phone photo works).
   Uploaded drawings: at most `limits.pdf_max_pages` pages, each page within the pixel cap at
   `limits.pdf_render_dpi`; renders in the API use `safe_dpi`.
5. **The old webshop API** (`/api/public/v1`) needs a valid X-Api-Key or a colleague's
   session; the Origin/Referer substring check is gone (any script can send those). The iframe
   configurator for anonymous visitors is therefore retired (no key, no embed address and no
   request were ever recorded on the server). With the website link closed the API is behind
   the website gate unless a key is sent.
6. **Old proposals** go after `limits.quotes_keep_days` (60) unless an order or a request
   names them (a B2C order keeps its own copy of the proposal in orders.data; its files stay
   too): `scripts/quotes_clean.py`, run by `scripts/housekeeping.sh` (DRY_RUN=1 supported).
   Every per-visitor limit counts an IPv6 address as its `/64` (`limits.ipv6_prefix`), and all
   visitors together write at most `limits.quotes_per_minute` proposals a minute.
7. **The login code fails closed**: with the code on (the default) and no mail server, a login
   is refused (503) instead of letting the password alone through. The way in is on the server:
   `cover-users invite <name>` (a link that sets a password and logs in) or
   `cover-users two-factor off|on|status`. The live server has a mail server set and the code
   on, so nothing changes there.
8. **Codes and links**: a password change, a reset or new invitation and switching a user off
   delete the open login codes; a code's try is counted before it is compared and the right
   code is used up by one `DELETE ... WHERE` (one code, one session); a password link (studio
   and B2B) is taken by one `UPDATE ... WHERE used=0` before the password is set.
9. **Parsers and jobs**: a reference zip is refused over `limits.zip_max_files` entries and
   stops at `limits.zip_max_mb` written (counted, not the zip's claim); a sheet (Excel read-only,
   CSV) over `limits.sheet_max_rows`/`sheet_max_cells`. Each job step runs through
   `coverapi.limited` (address space `limits.job_memory_mb`, CPU time the wall limit times the
   cores) in its own process group, ended after `limits.job_timeout_s` (4 h; the longest
   finished drape took 4400 s). The 207 MB Blocchi STEP ran import → export under the limits
   (peak 1.4 GB resident), and Warp/Newton (the local drape) starts fine under them.
10. **Smaller ones**: Desk approvers and question owners are matched on the user name only (a
    display name is free text). Wrong passwords lock per (account, address) with a doubling
    lock up to `limits.login_lock_max_minutes`; an unknown name is counted and answered exactly
    as a known one, with the same single scrypt (a dummy hash); at most
    `limits.login_codes_per_hour` codes are mailed to one person. A B2B 3D scene is shown only
    to the company whose proposal it is. A Mollie "paid" is acted on only when the payment's
    amount (cents), currency, order in its metadata and live/test mode match the order.

Codex's adversarial review found two holes in the first version, both closed: an .xlsx is a zip
whose shared strings openpyxl unpacks whole even read-only, so the workbook's unpacked size is
checked from its zip directory first (`limits.sheet_max_unpacked_mb`); and PyMuPDF's `dpi=`
takes whole numbers only, so a page rendered smaller goes through a scaling matrix
(`safeimage.render_page`).

Better, later: a per-route limit table that FastAPI derives from the routes themselves; Caddy
2.8's log `mode`; Mollie's own webhook signature once Mollie offers it for payments.

## ADR-124 — The studio's look, Covers and Workshop, and the tidy-up (steps 7, 8 and 9)

The owner asked (12 Oct 2026) to continue the studio's layout (docs/plans/studio-ui.md §9) after
steps 1, 2, 5 and 6 (ADR-122). Built: steps 7, 8 and 9. Business choices stay as they are: no
workshop right (open question 92), English (91), approvals unchanged (83, 84), defaults read-only
and applied as before (step 4 waits for 93).

- **One stylesheet (step 7):** `apps/web/src/studio.css` replaces styles.css, studio.css's
  first version, desk.css, desk-products.css and b2b-admin.css. It starts with the tokens
  (page, surface, sunken, stone, lines, ink, muted, sand, accent, primary and its ink, the
  header, status ok/warn/bad/info, code, stage, shadows, type, radius, 32 px controls) and builds
  everything from them; the Desk's own green palette (`--d-*`) and its own dark block are gone,
  the Desk and the Questions use the studio's tokens. Every hard-coded colour left is a picture's
  (the 3D markers, the arrangement plan, the login page's backdrop, which stays on its dark
  ground). Rectangular buttons and fields (chips and badges stay round), 8 px corners.
- **Work Sans everywhere, self-hosted:** the studio's page no longer asks Google for Poppins,
  Fraunces, DM Sans, Caveat or Work Sans; it uses `@fontsource-variable/work-sans` like the
  shop (ADR-105), preloaded by the same Vite plugin. The canvas labels (3D, Measure, Unfold)
  use Work Sans too. The public shop and the B2B shop keep their own design (b2b.html untouched).
- **Dark mode for the whole studio:** a second set of token values, used when the computer asks
  for dark (`prefers-color-scheme`) unless the person chose Light, or when he chose Dark. The
  choice is a button left of the name (◐ as the computer → ☀ light → ☾ dark), stored per browser
  (`studio.theme`, `apps/web/src/theme.ts`) and set on `<html data-theme>` before the first
  paint. Drawn things stay on a white "stage" (drawings, flat patterns, the seam plan, Desk
  pictures, the marker) and the 3D viewer keeps its light scene in both themes: a Desk picture
  and its red marks look the same whoever took it (ADR-096, ADR-100). The customers' configurator
  (#/configure) is always light (`.theme-light`), as it sits inside other websites.
- **Four page templates (`layout.tsx`):** list (a head, one filter row, a table with a sticky
  head or cards, a selection bar: All covers, Workshop, Orders, Requests, Matches, B2B customers,
  Learning), queue (Desk, Questions), object (a cover), form (Settings, Prices, New cover,
  Product list, Website, Photo test, My account). Every page in App.tsx's router is wrapped in
  one; each has one page head.
- **All covers (step 8):** Models and Catalogue are one component (`Covers.tsx`) with one filter
  row for both views: search (name, tag, note, family; the old table's and cards' rules
  together), category with its groups and counts, cover grade, status, tag, sort (name, ready
  first, stretch, size), "select all shown", a box on every card, and the batch bar; the filters
  and the selection stay when switching Table / Cards (the view is in the address). Nothing the
  two pages had is lost: the table's columns and the cards' facts are unchanged (the cards also
  show the status and tags now).
- **New cover:** the three uploads on one page: a 3D file, a drawing (PDF), reference pairs (the
  zip that was on Learning, `ReferenceUpload`). Learning shows the batches only.
- **Work → Workshop:** `GET /api/workshop` (any logged-in person, as GET /api/desk; no new right)
  lists covers the Desk approved or marked produced: who and when, the files (cutting list, size
  drawing, check list, cut pieces SVG), the cutting table's DXF only when `dxf_allowed` says so
  (the same gate as the download, ADR-079/115/120; the server checks again on download, and the
  admin override is not offered), the revision the Desk marked to cut (behind its own
  fingerprint gate), and the fit (Fits / Does not fit, the note, how many sizes were measured and
  the largest difference). The customers' fit answers (1–5, comment, photo) are joined to the
  cover through the order's model, from the existing editor APIs; viewers see a note instead.
  The page has no buttons: approving, Produced and the measured sizes stay on the Desk card.
- **Search everything (step 9):** the header's box (`Search.tsx`, Ctrl+K / Cmd+K) searches
  covers (name, tag, note, family, category, Desk code), the Desk's codes and product names, the
  questions (number, title, covers) and, for admins, the orders (number, customer, mail,
  product); a hit opens the cover, the Desk card, the question or `#/shop/orders/<n>` (the order
  marked and scrolled to). The lists are fetched on first use with the person's own rights.
  Not "/" as the plan said: the Questions page uses "/" for its own search.
- **Tidy-up:** Gallery.tsx and QuickSearch.tsx, the old Models list in App.tsx and the CSS of
  pages and tabs that no longer exist (the Desk's Covers/Questions tabs and their badge, the old
  button tabs, the rain buttons, the old header) are removed. Every address the studio never
  had now goes to the person's start page rather than "Not for your account". Every redirect
  stays (uinav.py checks them), `#/models` included: it was a shim of ADR-122, but the handbook
  has named it since v1.36.0, so a bookmark may hit it (Codex).
- **Handbook:** rewritten around the map (docs/handbook/README.md as the index, workshop.md new,
  navigation.md, how-it-works.md, catalogue.md, admin.md, web-app.md, learning.md rewritten,
  the rest's page names fixed), in English.
- **Checks:** apps/web/e2e/uinav.py runs every pass light and dark (the browser's colour scheme)
  with a WCAG contrast check of every visible text on every screenshot, and checks All covers'
  filters and selection across the switch, the three uploads, Learning without one, the
  Workshop's DXF links against the gate, the search and the theme button. test_desk.py checks
  the Workshop API (approved and produced only, the DXF link gone once the cut changes, nothing
  changed by reading). Screenshots: out/uinew2/.
- **Codex's adversarial review** found three things: the Workshop joined the customers' fit
  answers to covers through the latest 300 orders only, so older answers vanished (fixed: the
  feedback API joins the order's model on the server; a failed read now says so instead of "no
  answers"); `#/models` should keep its redirect (restored); and seam-plan labels unreadable in
  dark mode (not taken: the plan carries the light tokens, `svg.plan` beside `.theme-light`,
  and the dark screenshots show dark labels on white).

Better, later: a workshop login with its own right (question 92); the Workshop's fit history per
revision; server-side search when the lists grow past a few thousand.

## ADR-125 — The website's clips by Kling image-to-video, from our own stills

(Numbered 125: 124 is the studio's look on main, 12 Oct.)

The owner (12 October 2026): our Blender animations on the website are far from realistic;
redo them with Kling. This reverses ADR-108's "no generated video" for the clips, on one
condition that keeps ADR-108's reason: every clip starts from **our own still** (and, for a
transition, ends on one), so the cover's shape, its sand colour and its stitching are ours; Kling
adds only the motion. Plan, prompts and checks: docs/plans/kling-shots.md.

- **The stills** (`scripts/film/kling_frames.py`, Blender 4.2 Cycles on the CPU through
  `blender.sh`, nice 19, one at a time): the start film's and the reel's scene parts, 160
  adaptive samples (5× the films'; 384 took 40 minutes a picture here, too long for one night),
  16:9 1920 × 1080 and 4:5 1080 × 1350. The fabric is closer to the canvas: a
  procedural plain weave at the real yarn pitch (0.7 mm) in each piece's flat UV, heathered yarns,
  a soft mottle and fine creases, a matt roughness; the thread rows of seams.png get their own
  relief and a glossier thread. The villa's sun is low from the left (it was behind, the covers
  in shade), the island smaller, the sea deeper; the Sato lounger shows its designed surface
  (its drape sags into the seat, against domain rule 12). The cutter's head hangs from a
  carriage on a beam, as on the machine, instead of floating.
- **The client** (`scripts/film/kling.py`): `submit`, `status`, `fetch`, `run --shots`, `cost`;
  `--dry-run` prints the request with the key masked. Kling's current API (path-versioned,
  `/image-to-video/kling-3.0`, `/tasks`) takes only an API key and has no negative prompt or
  mode field: the negative words go into the prompt as "Avoid: …", the mode is the resolution.
  The AK/SK JWT (HS256, 30 min) works only with the legacy API (`/v1/videos/image2video`,
  `model_name`, `image_tail`, `negative_prompt`), which the script also speaks. Default
  kling-3.0 at 1080p, 5 s, no audio: 4 units, $0.56, ~€0.53 a clip.
- **Money**: every submit is written to `out/kling/ledger.jsonl` and the studio's AI ledger
  (spend.py) before it is sent; a submit whose estimate would pass `--budget-eur` (default 50)
  is refused before anything goes out; a bill in Kling's answer replaces the estimate. The
  conversion errs high ($1 = €0.95).
- **Tests** (`engine/tests/test_kling.py`): a fake HTTP layer only; the JWT, the request
  shapes of both APIs, the budget refusal, a run polling to the download and the bill, no key in
  any output, and the shot file's prompts equal to the plan's.
- **To the site**: frames at 24 fps → `hero_encode.py` (AV1 + H.264, poster) under new names
  (`work-<key>-2`, `villa-ibiza2`) beside the old ones → the preview's `story_media` only; live
  with a release and the owner's go.
- **Rejected**: text-to-video (not our cover); Kling's 3.0 Turbo (no last frame); paying for
  4K (the cards are 720 × 900).

## ADR-126 — One cover, one page: its price and its shop on the cover; general settings in Settings

The owner (12 Oct 2026): "we have to many different tabs, like the pricelist, why is this not
vissable in the item settings, all settings related to a covers should be visseble in the cover,
like cost, sales price etc, now there is to much information all over the place, it needs to be
less and more together"; that evening: "dat mag alles in de settings page komen, maar product
gelateerde informatie bij het product houden niet overal plaatsen". Inventory and design:
docs/plans/studio-ui.md §12; handbook: prices.md, navigation.md.

- **Four sections** (Work · Covers · Shop · Settings). Prices is no longer a section: its seven
  tabs became three tabs of Settings, group **Prices & costs**: *Costs* (materials, labour, the
  exchange rate on one page), *Price rules* (per channel extras, markup or margin, rounding,
  VAT; the balloon's and frame's fixed prices, and folded the fixed prices of products without
  a calculated cover so nothing set before is unreachable; a configurator product's costing)
  and *Publish & versions* (the draft bar, the versions with roll back, the Excel import).
  Editors see these three tabs read-only, as they saw Prices; every other Settings tab stays
  admin-only (`nav.ts` `SETTINGS_WHO`); the same `Prices` component, so the numbers typed stay
  while moving between the three (unsaved guard with several kept addresses, `a|b|c`).
- **A cover's seventh tab, Price & shop** (`#/model/<id>/price`, `CoverPrice.tsx`,
  `GET /api/prices/cover/<id>` in `coverapi/cover_commerce.py`): the costing (live or draft;
  CSV, PDF), per channel the live price, fixed or calculated, the margin and the draft's price;
  the shop (offered as an existing cover or why not — the same `match.card` /
  `match_drawings.review` the shop uses — kind, sizes, the price list's rows, how its
  direct-order price is made and the delivery note); for admins its B2B companies with an own
  price, its orders (consumer and B2B), recent stock quotes and the match requests that proposed
  or chose it. Read-only gathering; no price is computed differently. Files moved into Pieces
  (`/pieces/files`) so a cover keeps seven tabs.
- **One summary row** under a cover's head: Desk status, who approved, produced, the measured fit,
  the workshop's revision to cut and files, the open questions about the cover
  (`/api/models/<id>` now carries its Workshop line, `desk.workshop_item`).
- **A fixed price from the cover** is `PUT /api/prices/draft/fixed {model, channel, price|null}`
  (admins only): it writes `channels.<ch>.fixed.<model>` of the same draft the whole-set editor
  writes (the draft starts from the live set when there is none; the import's note kept),
  never publishes. A test proves the draft equals the one the old Channels table produced, row
  for row; editors and viewers get 403. Publishing from the cover is the same `POST
  /api/prices/publish`, after the preview's count and a confirmation naming the whole draft.
- **No lost update, no surprise publish:** `PUT /api/prices/draft`, `PUT /api/prices/draft/fixed`
  and `POST /api/prices/publish` take an optional `since`: the `revision` the page was given
  (`v<live version>:<draft time>`, from `GET /api/prices`, the cover endpoint and every save).
  It changes with every save, fixed price, import, publish, discard and rollback (Discard
  draft checks it too), so prices
  changed elsewhere (a cover price, an import, a publish that cleared the draft) are refused
  with 409 and the page offers to load them; a page publishes exactly the draft it saved. Old
  clients without `since` behave as before. Codex found the holes of the first two versions (a
  publish that fetched the newest draft after saving; cover edits without the token; a
  time-only token that a publish-and-clear elsewhere made look current again); each has a
  regression test. Later passes, also fixed: the revision is derived from the very records an
  answer shows and every check-then-write holds one lock; Discard draft carries the revision;
  saving one channel keeps a price typed in the other (and leaving asks); the cover names the
  draft's VAT unit and drops a typed price whose unit changed on reload; All covers ignores a
  slower answer for the other set and names its columns after the shown set's units.
- **All covers' optional price columns** (`?prices=live|draft`, `GET /api/prices/list`, editors
  and admins): cost, B2C, B2B, margin, source; sort by B2C price or margin; a price opens the
  cover's Price & shop. No separate price page.
- **Shop keeps only shop-wide pages:** Orders · Requests (the match requests and the configurator
  quotes on one page) · B2B customers · Website (AI). The Photo test moved to Settings → AI &
  spending. **Settings merged:** Matching + B2B terms → *Selling*; Desk & approval + Cover
  defaults → *Rules & defaults*; System + Logins & audit log → *System & logs*. Tabs and pages
  in Prices + Shop + Settings: 24 → 15.
- **Every old address redirects** (`#/prices[/<tab>]`, `#/shop/matches`, `#/shop/phototest`,
  `#/settings/matching|b2b|desk|activity`, `#/admin/prices|matches|phototest|sessions|audit`,
  `#/model/<id>/files|downloads`); uinav.py checks each.
- **Unchanged:** the pricing maths, VAT, rounding, draft → preview → publish → versions and
  rollback, rights (admins edit and publish, editors look, viewers none), B2B scoping, the
  approval gate (ADR-079/115/120), server-only settings (ADR-123).
- **Better later:** inline editing in All covers' price columns (now: one click to the cover);
  a per-cover price history (who set its fixed price when) from the versions.

## ADR-127 — The website's clips from real SUNS photos: Gemini puts our cover on, Veo moves it

The owner (13 October 2026), after one test on the Kota photo: "dit is stukken beter", then
"alleen even de beste foto zoeken voor alle settings, mag ook een ander model zijn maar dan
moeten we het aanpassen". Kling (ADR-125) has no API credit; Google's Gemini API does, through
the key we already have (`GEMINI_API_KEY`). This keeps ADR-125's rule that the cover is ours, but
the scene is now a real photograph instead of our Blender stills, which never looked filmed.

- **The recipe.** (1) The start frame is a real SUNS product or mood photo from hello-suns.com
  (the brand whose covers we make, the owner's partner), cropped to 16:9 1920 × 1080. (2) The end
  frame is that photo with our cover on the furniture, made by `gemini-3-pro-image`
  (generateContent, image out, 16:9 at 2K, then fitted to 1920 × 1080) from the photo plus the
  model's own `cover.png` as the shape reference (its colours only mark the pieces) and our
  Kota canvas render as the fabric reference; the prompt names the sloped top, the level skirt
  with its hem ~5 cm above the ground and the vent hoods, and asks to keep everything else.
  (3) `veo-3.1-fast-generate-preview` (predictLongRunning, 8 s, 1080p, 16:9, a negative prompt)
  animates from the first frame, with a last frame for a transition (fit). Every frame is looked
  at before it is used; a frame that invents logos, text, a wrong shape or a changed background
  is made again (`-v2`, `-v3`, the first kept).
- **The photo per scene** (from 1,000 SUNS photos: all product pages and all project pages,
  contact sheets in `out/veo/suns-photos/`; only models we have a cover for in `models/`):
  fit = the Portofino daybed on the paved terrace (front-on, one piece, room above it);
  rain = the same daybed, the Kota sofa as second; villa = the Blocchi sofas on the mountain
  terrace at golden hour, the Portofino daybed with roof at the Marbella villa pool as second
  (SUNS has one sea photo, Villa Maxima in Puglia, but its sofa is the Pesaro, which we have no
  cover for); range = the two Basta loungers by the pool with the Basta bar set behind.
  Sources (file names, URLs) in `out/veo/frames/sources.json`. Plan, prompts and judgements:
  docs/plans/veo-shots.md.
- **The client** (`scripts/film/veo.py`, shots and frames in `scripts/film/veo_shots.json`):
  `photo`, `frame`, `submit`, `run`, `fetch`, `cost`; `--dry-run` prints the request with the key
  as `***` and sends nothing. The key goes only into the `x-goog-api-key` header (also for the
  download), never into a URL, a log or a record.
- **Money.** Every paid call is written to `out/veo/ledger.jsonl` and the studio's AI ledger
  (spend.py) before it is sent; a call whose estimate would pass `--budget-eur` (default 30) is
  refused before anything goes out; a Gemini image answer's token count replaces its estimate.
  Prices (ai.google.dev/gemini-api/docs/pricing, read 13 Oct 2026): Veo 3.1 Fast $0.10/s 720p,
  $0.12/s 1080p, $0.30/s 4K; Gemini 3 Pro Image $0.134 an image (1K/2K). The ledger uses
  $0.15/s (the brief's figure, above list) and $1 = €0.95: a clip ~€1.14, a frame ~€0.13 to
  €0.16. Veo bills no usage in its answer, so its estimate stays.
- **Tests** (`engine/tests/test_veo.py`): a fake HTTP layer only; the request shapes of both
  calls, the polling to the download with the key header, a failed operation, the budget
  refusal before any call, frames and clips counted together, no key in any output, the crop.
- **To the site**: `hero_encode.py` (AV1 1920 × 1080 + H.264 1280 × 720, poster, no sound,
  the end dissolving into the start) under new names `veo-<scene>-<n>` in the media folder,
  next to the current clips on `/media/veo-compare.html`; the owner picks there, then the
  preview's `story_media` and a release (not done by this round).
- **Rejected**: Veo 3.1 (non-Fast, $0.40/s) before Fast has shown a flaw that it would fix;
  Gemini's image model for motion; making covers for models without one (the Puglia sea photo
  waits for a Pesaro cover).


## ADR-128 — One approval (the Desk's), every cover's DXF behind it, orders by a click, a workshop login

The owner answered four questions in the Questions tab (12–13 Oct 2026): #83 "Goedkeuring: één of
twee?" **a) only the Desk**; #84 "Moet elke snijfile goedgekeurd zijn?" **b) all covers,
catalogue and custom** (Rens), with a quick approval for custom covers; #86 "Wanneer gaat een
bestelling naar productie?" **b) after a click by someone in the studio**; #92 "Een
werkplaats-login?" **a) yes**. (#91: the buttons stay English; #90: a stability round, done
elsewhere.) This settles docs/plans/studio-ui.md open questions 2 and 4 and step 3's approver
list.

- **One approval.** The cover page's "Approve the definitive drawing" (approval.py's
  approve/withdraw, ADR-047) is retired: `POST|DELETE /api/models/<id>/approve` answer 410 and
  name the Desk. A Desk approval now stamps `sizes.pdf` and `cutting-list.pdf` with "APPROVED
  <name> <date> revision <n>" into `approved/`: the stamped copies are made before the Desk's
  lock (a size drawing takes a moment) into temporary files and moved in with `os.replace`, so a
  reader never sees half a PDF; a PDF without pages refuses the approval with 400 and leaves
  nothing behind; a PDF that does not exist yet is skipped and the history says which were
  stamped. `approved.stamped` keeps each stamped copy's fingerprint; `/approved/<name>` is
  served only while that approval holds (approved or produced, the same cut file, the same
  bytes). `approval.json` files stay readable as history (`approval.legacy`, shown on the cover
  page). The cover page's card shows the Desk's approval, the stamped PDFs, a link to the Desk
  card and *Send to the Desk for approval* (`/approval-request` now puts the built cover on the
  Desk and mails the Desk's approvers with a link to its card).
- **Who approves**: admins, users marked *may approve* (the flag that approved definitive
  drawings) and the names in `desk.approvers`; never the workshop role. On live every user with
  *may approve* is an admin already, so nobody gains the right.
- **Every cover's DXF behind the Desk.** `desk.gate_scope: all` in config/defaults.yaml (a
  company default): drawing-*, arr-*, suns-*, bbq-*, order-* and any other cover. The gate no
  longer looks at the catalogue status (anyone with edit rights could set "checked" by hand); it
  asks the Desk: approved or produced, for the cut file it has now. Every approval records the
  cut file's fingerprint (ADR-120 for drawings, now for all); a later change of the cut reopens
  the cover to waiting with a history line; earlier approvals without a fingerprint are
  grandfathered once with the current cut, as ADR-120 did for drawings. Every `.dxf` a cover
  serves is gated, `pattern.dxf` too (it could be cut by mistake). The admin's logged override
  stays.
- **Orders by a click.** A paid order (the Mollie webhook) becomes `waiting_production`, not
  "paid and into production": the webhook only marks it, once (`AND status='awaiting_payment'`),
  and mails the studio. A B2B order on account writes its lines as `waiting_production` and its
  outbox rows (`b2b_dispatch`) in the same transaction as before; `auto_produce` is gone.
  *Send to production* (Shop → Orders, Work → Workshop; editors and admins; `POST
  /api/admin/orders/<id>/produce`) sets `released`/`released_by` once with a conditional update
  (paid, waiting_production or on_account only), then makes the cover under one lock: a shop
  order's own cover (`order-<n>`, calculated by a job) or the catalogue cover of a stock order,
  sends it to the Desk as an **order** (`order` in desk.json) and sends the production mail.
  `produce` refuses an order that was not released (409). The B2B outbox drains released lines
  only, so a restart still finishes a line that was sent but not made, and a waiting line stays
  in the outbox; a second click returns the same cover and dispatches nothing twice. A status
  set by hand to `in_production` is refused before the click. The customer sees "paid" (B2C) or
  "on account" (B2B) while the order waits.
- **The quick approval.** An order on the Desk is first in the queue whatever the AIs said or the
  sort, tagged ORDER #n (B2B), with an *Approve* button in the queue itself once its cutting file
  exists; a catalogue cover whose approval holds for its current cut stays approved (ready to
  cut at once). The approval marks the order approved.
- **The workshop login** (role `workshop`, `cover-users add <name> --role workshop`, Settings →
  Users & rights): starts on Work → Workshop; sees Work only (Desk read-only, its questions,
  Workshop with the orders to make, without prices or e-mail addresses). On the Desk card it adds
  a fit with measured sizes, comments and pictures; it never approves, rejects, marks produced,
  undoes, corrects or starts the AI. It downloads the DXF of approved covers. Enforced in the API
  by an allow-list (`security.WORKSHOP_READ/WRITE`: a route added later stays closed to it until
  named), the Desk's `may_act` (note and fit only), `approver()` (never, whatever its name or
  flag), `User.may("approve")`, the questions (only those it may answer; never an owner) and
  auth (a workshop user cannot be *may approve*). The menus follow (`nav.ts`
  `WORKSHOP_PAGES`, `isEditor`), and uinav.py walks the role.
- **Migration** (dry run first; only the main session applies on live):
  `scripts/desk_definitive.py --dry-run|--apply` turns a definitive approval that still matches
  its cut file into a Desk approval with a history note ("grandfathered from the definitive
  drawing approval by X on D"), keeping its stamped PDFs served; never for a drawing (gated
  before), a rejected or an already approved cover. `scripts/desk_gate_all.py --dry-run|--apply`
  for the newly gated covers: grandfathers those already cut or produced or in active use
  (a valid definitive approval, catalogue status production or checked, an order in production,
  sewn, shipped or returned), records the fingerprint of earlier Desk approvals, and sends the
  rest to the Desk as ready for approval (ai-checked + sent), like desk_arrangements.py; a
  rejected cover or one approved for another cut is never blessed. Both are idempotent and
  read-only in a dry run (tested byte for byte), in `coverapi/gate_migrate.py`.
- **Live, 13 Oct 2026 (read-only dry runs)**: 1 cover has an approval.json and it is approved on
  the Desk too, so 0 covers have only a definitive approval. Newly locked by the gate: 208 built
  covers that are not drawings or arrangements and have no Desk approval for their cut: 174
  would be sent to the Desk, 23 are waiting there already (barbecues), 11 were rejected (2 more
  are not built: nothing to cut); 0 would be grandfathered (no catalogue cover is checked or in production
  without a Desk approval, and there are no orders). 127 approved covers get their fingerprint
  recorded on first read. Paid orders in flight: 0 (the orders table is empty).
- **Tests**: the gate on every cover kind and its revisions, the catalogue status never opening
  it, the stamped PDFs (atomic, an empty PDF refused without side effects, served while the
  approval holds), the retired routes, the order not in production before the click (webhook,
  status by hand, B2B outbox, restart recovery, two clicks), the quick approval and the queue's
  order, the workshop role's allowed and denied routes, its questions and its rights in auth,
  the migrations (dry run byte for byte, apply, apply again changes nothing).
- **Codex's adversarial review** (branch, focus on the gate, the role, the click and the
  grandfathering) found one thing, fixed: `pattern.dxf` was gated on the cut file's approval
  only, so a flatten-only run after an approval (it rewrites pattern.dxf, not cut.dxf) would
  have served an unapproved flat DXF. An approval now records `approved.pattern` and the flat
  DXF is served only with those bytes (an older approval without it: locked, admin override).
  Earlier, in my own review: an approval without a fingerprint whose cut file is newer than the
  approval is not grandfathered but reopened (0 such covers on live).
- **Not done**: the approvers' daily digest still names arrangements only (an order's production
  mail goes to the studio's address); whether the workshop may press *Send to production* or
  mark a cover *Produced* is for the owner to say (now: editors and admins, approvers).

## ADR-129 — Stability round: live folders, interrupted jobs, mail, releases, shop, cache, backup, 3D memory, test time

The owner answered question #90 ("Waar gaat de komende week het werk heen?") with b): a
stability round first. The open findings of the Codex analysis of 11 October
(`~/cover-data/reports/codex-analysis-2026-10-11.md`) were checked against ADR-120 to ADR-127
first. Already fixed there and not done again: the drawing approval tied to its cut fingerprint
(ADR-120), the step time and memory limits (`coverapi.limited`, ADR-123), the staging guard on
given_build, fewer_build, innerwalls_sweep, answers_stage and bbq_models, and dropping an
aborted quote answer when the stock cover changes (ADR-118). ADR-128 is the parallel round on
desk.py, approval.py, order-to-production and roles; nothing here touches those.

1. **Live model folders** (Codex did this, reviewed). Every script in scripts/ that writes model
   folders calls `coverengine.staging.guard_staging_output` on its output root and each model
   destination before anything is written: drawing_cover(s), drawing_features,
   drawing_crosscheck, drawing_outline, drawing_axes_check `--fix`, c6_surface, s44_cover,
   catalogue_page, desk_marks, fewer_check, matchcards, film/hero_data, warehouse `fetch`/`photos`,
   gpu_check, learned_check `--recalc`. The in-place rebuilders refuse a live run:
   drawing_rebuild and drawing_merge only with `--dry-run`, drawing_swept only with
   `--no-build`; the message points to the staging builders (fewer_build, given_build). Left as
   they are, on purpose: the live-metadata tools that are dry-run first (desk_fingerprints,
   desk_arrangements, desk_import, questions, prices_import, quotes_clean).
   `engine/tests/test_scripts_staging.py` runs each script against a synthetic live tree and a
   symlink alias of it and proves nothing was written; it also keeps the list complete.
2. **Interrupted jobs.** A job names its server process (`owner`: pid and a per-process id) and
   each running step its process group. On start-up `Jobs.recover()` marks the jobs of a server
   that is gone, queued or running, as `interrupted` with the reason ("the server stopped while
   the step cut ran (a restart or a crash); run it again"), and ends a step's process group that
   outlived its server (only when its command line is our `coverapi.limited`). `POST
   /api/jobs/<id>/rerun` (and **Run again** on the cover's job bar) starts the same steps and
   trial again, for an interrupted or failed job. The job carries `timeout_s`
   (`limits.job_timeout_s`); the bar shows it while the job runs. The pages that follow a job
   stop following at `interrupted` too.
3. **Mail.** `mailer.send` logs every attempt in app.db (`mail_log`: time, kind, recipient,
   subject with a login code masked, sent or the error without the password; never the text).
   A mail is sent only when the SMTP server accepted it: refused recipients are a failure.
   `mailer.queue` (order notices, the fit question, requests, B2B order mails, the Desk's
   digests) keeps the text in `mail_outbox` until accepted, tries at once and then after
   1, 2, 4 ... minutes (at most 6 h apart) up to 8 times (`limits.mail_*`), then `failed`. The
   text goes when sent, a failed one's after 14 days. One worker thread per process walks the
   outbox; each mail is claimed (a token and a 200 s lease) just before its own try and its
   result is written only while the claim is still that try's, so a long backlog never sends
   a mail another worker took over (Codex's review). Settings → System & logs → Mail lists waiting and failed mails and has **Send again**
   (`/api/admin/mail/outbox`). Mails with a secret (login code, password and invitation links)
   are never queued: sent once, logged without text. The fit question's `feedback_sent` is set
   only when its mail was accepted (`mailer.ON_SENT`), and a queued one is not queued again.
   Background loops (fit mails, question mails, the outbox) log their errors to the journal.
4. **Releases.** `release.sh --switch` (and so `rollback.sh`): when `sudo -n systemctl restart
   cover-web` fails, or `/api/health` does not answer as the expected release within a minute,
   it switches `~/releases/current` back, restarts, checks that one, and says "switched back to
   vX automatically" (or that the one before does not answer either), also in history.log. Only
   that sudo command is used. When the service does not run from `~/releases/current` yet (the
   first install, which needs `sudo cp` and `daemon-reload`), it changes nothing and prints the
   commands for a person (exit 2). Tested with stand-in sudo, systemctl and curl
   (`engine/tests/test_release_script.py`).
5. **The consumer shop.** The configurator's quote request has a number and the quote
   remembers the choices it was made for; only the newest answer is shown, and a price is shown
   and orderable only while it belongs to exactly the choices on screen. The checkout is locked
   while its request runs and sends an `idempotency_key` (a random key per order content);
   `orders.idempotency_key` is unique, so a double click, a retry or two requests at the same
   moment get the order the first one made (`repeat: true`, its payment link once Mollie gave
   it); a key used for another e-mail or proposal is 409. A page without a key (an old cached
   page) is protected by the same proposal, e-mail and street, unpaid, within 15 minutes.
   Everything after the order row is safe to run again (`finish_order`, Codex's review): the
   payment is made by the request that claims the order with a token (a claim older than
   40 s is taken over; a result is written only while the claim is still that token's),
   with Mollie's `Idempotency-Key` per order, and the "new order" mail has a fixed outbox
   reference. So the retry of a checkout whose first request stopped after the order row
   finishes it; a payment still being made elsewhere answers 409 "try again" (the page
   keeps its key); and a Mollie error or timeout lets the claim go and answers 502 "try
   again" (mailed to us once), where it used to end the checkout without a payment link:
   the next try asks Mollie again with the same key, so it stays one payment (Codex's two
   reviews). Send again in the outbox moves a mail only from failed, in one step.
6. **The step cache.** A step's stamp now lists every file the run created or changed in the
   model folder (`outputs`: cut.svg, cutting-list.pdf, pattern.svg, ...), not only the main
   ones. A step is skipped only while all of them exist and are not empty; a stamp from before
   (no `outputs`) is calculated once more.
7. **Backup** (Codex did this, reviewed). With `COVER_BACKUP_REMOTE` set, a missing rclone, an
   unknown remote or a failed copy keeps the local archive but writes FAILED and the reason to
   last_backup.txt (the watchdog mails it) and exits non-zero; unset says "off-server copy: not
   set"; a good copy says so. R2 itself is owner question #89.
8. **3D memory** (Codex did this, reviewed). `apps/web/src/dispose3d.ts` disposes every
   geometry, material and texture of a tree; the cover's 3D view (also on the Desk card), the
   configurator, Unfold and the shop's scenes dispose their scene, controls and renderer on
   unmount and the objects they replace. `window.__three` counts live renderers and their
   geometries and textures; `apps/web/e2e/memory3d.py` opens 20 covers in a row and fails when a
   renderer stays or the heap grows.
9. **Test time.** Measured on the server on 13 October (8 cores, other agents' work running
   too, so both numbers are on a busy machine): before, `make test` took 26 min 31 s (lint
   55 s, then pytest 25 min 29 s, 800 tests); after, 7 min 39 s (lint and 6 pytest processes
   side by side 6 min 2 s for 875 tests, then the 3 timing tests alone 1 min 35 s), 878 tests in
   all (the 800 and this round's new ones). The longest file (test_hull.py, 4 to 5 min alone)
   now sets the floor. `make test` runs the lint next to pytest, pytest
   in 6 processes (pytest-xdist, `--dist loadfile`: one file per process, so a module's
   fixtures are built once), then the three tests that assert a duration on their own
   (`-m timing`). Nothing is left out: the same tests run. `make test-serial` is the old way,
   `make test-fast` leaves out the 30 tests of 15 s or more (`-m slow`) while developing, never
   for a release. The marks live in the root `conftest.py`, which fails when a listed test is
   gone.

Better, later: a durable job queue that resumes instead of interrupting; per-model locks for
all writers; an outbox for the approval and invitation mails' audit trail in one place; a
transactional promotion for drawing rebuilds instead of refusing them.

## ADR-130 — Studio 2.0: "A · iOS light", our own icons, the (i) instead of loose text

The owner chose direction **A · iOS light** of the Studio 2.0 proposal (13 Oct 2026,
docs/plans/studio-v2.md), "with icons etc.", and later the same day asked for **icons of our
own** ("maak zelf unieke icons voor de backend"). Built on v1.42.0 (after ADR-128 and ADR-129),
from the proposal's tokens, audit and icon map; its mock-up patch was a reference only.
Decided with the choice, not asked again: iOS blue as the one accent, a light header and
sub-menu, the system font with Inter as the web fallback, 14 px cards and grouped inset lists,
Settings with coloured icon tiles, the status colours below, field borders of at least 3:1,
icons on every menu item, tab, toolbar action and status chip, and the text reduction.

1. **Tokens** (`apps/web/src/studio.css`, first block; same names as before plus `--wait`,
   `--made`, `--count`, `--tile-*`, `--radius-lg`, `--radius-sm`, `--icon-stroke`). Light: a
   grouped grey ground `#f2f2f7`, white cards, ink `#1c1c1e`, muted `#636366`; dark: true black,
   grey cards `#1c1c1e`. One accent, iOS blue (links `#0062cc`/`#5eb0ff`, buttons
   `#0068d6`/`#0a6cdb`, white text 5.3 / 5.0:1). States: **approved green** (`--ok`),
   **waiting blue** (`--wait`), **rejected red** (`--bad`), **a warning orange** (`--warn`),
   **produced purple** (`--made`), each on its own tint. A field's border (`--line-strong`)
   `#848489` light, `#757579` dark: at least 3:1 against the surface, the ground, the sunken
   and the stone tone (WCAG 1.4.11; was 1.7:1). `apps/api/tests/test_web_tokens.py` keeps every
   text pair at 4.5:1, borders, counts and the Settings tiles at 3:1, in light and both dark
   blocks. Type: `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter Variable", Inter,
   system-ui`: SF on a Mac and an iPad, Inter self-hosted (`@fontsource-variable/inter`,
   preloaded by the Vite plugin for index.html) elsewhere. Shape: 10 px controls, 14 px cards,
   34 px controls (40 on a touch screen), pills for chips and the sub-menu.
2. **The shell.** The header is light and translucent (no black bar), 56 px: the mark, the four
   sections as pills with their icon (the current one tinted blue), the search with its glass,
   Guide, the theme and Log out as icons (named "Guide", "Log out"), the name with a person
   icon. The sub-menu: pills with icons, the current page a solid blue pill. Settings: iOS
   Settings, a coloured tile with a white glyph before each tab, and each setting a row of name
   (its help behind an (i), its key in the name's tooltip), value and source chip.
3. **Our own icons** (`apps/web/src/icons/glyphs.tsx`): 69 glyphs drawn for the studio on a
   24-px grid, one stroke with round caps and joins, no fills, `currentColor`: the four
   sections, Search and Guide; Desk (a tray with a tick), Questions, Workshop (scissors at the
   cutting line); All covers, Arrangements (an L-shaped set from above), New cover, Learning,
   Product list; a cover's tabs (3D, pattern pieces, a stitched seam, sliders, compare,
   history, euro); the 3D toolbar (the vent hood, dimensions, the tape, the size drawing,
   design, rain on a cover, fabric draping from a bar, unfold, simulate, the check list); the
   actions (approve, reject, comment, needle and thread for After sewing, the cutting table
   with an arrow for Send to production, run again, DXF, cutting list); the statuses (each its
   own shape so they read without colour: a tick, a clock, a cross, a triangle, the cover with
   a tick for produced, a pause for interrupted); the Settings tiles; the shop (a receipt, a
   request, a building). The cover's silhouette (a lounge chair under its cover, the hem
   flaring) is shared by Covers, New cover, Produced and the requests. Optical sizes: the stroke
   is about 1.5 px at 16, 1.65 px at 20 and 1.75 px at 24 (`strokeFor`). Lucide (`lucide-react`
   1.56.0, ISC/MIT, imported icon by icon) only for generic glyphs: chevrons, close, the (i),
   copy, an external link, more, undo, delete, theme, table/cards. The sheet:
   `node apps/web/e2e/iconsheet.mjs OUT.html` (16/20/24 px, light and dark), looked at, eight
   glyphs redrawn after the first look (covers, all covers, new cover, arrangements, simulate,
   send to production, sewing, requests: the drape read as a hut, the L-set as a book); `~/cover-data/media/studio2-own-icons.jpg`.
4. **The (i) and the components** (`apps/web/src/icons/index.tsx`): `Info` is a button (named
   "About …", `aria-expanded`, `aria-controls`) whose text sits right after it in the page, so
   Tab reaches a link inside it; Enter, Space, a click or a tap opens it, Escape (focus back on
   the button), a tap elsewhere or the button closes it, a mouse also opens it by pointing. In
   the browser's top layer (popover API) so no table or scrolling box clips it; without the API
   a fixed card. The card is in the page only while open (a closed (i) adds no text, so a word
   is found once), never taller than the screen (it scrolls inside) and placed below, else
   above, else as low as the screen allows (Codex's review). Never inside a heading, label or button: `Heading` puts it beside the title.
   `StatusChip` maps a state to its colour and icon; `IconButton`/`IconLink` show an action as
   an icon with its words as tooltip and accessible name. `PageHead`'s intro, the Settings
   rows' help, the tab intros and group intros are (i)s by construction.
5. **Loose text** (the proposal's audit, `out/studio2-work/textaudit.py` re-run on the code):
   of the 525 audited items, 458 still stood as visible text on v1.42.0; after: 79, of which 25
   are empty states and "loading" lines kept on purpose, and the rest errors, live status ("The
   AI is reading…", "Comparing…"), role notes shown instead of a control ("An admin changes
   prices"), states that change a number's meaning ("over the low skirt", "not used") and short
   action labels. The rules for new pages (§3 of the plan): a page explains itself in an (i);
   a field's help is its (i); a repeated label is the column head; a toolbar action is an icon
   with its words as name; empty states, errors, live status and numbers stay visible.
   Explanations already behind a click ("Terms explained", "What the lines mean") stay plain.
6. **Pages**: Desk and its card (KPI tiles with icons, the pipeline and pills in the status
   colours, counts as icon + number, Open cover and More as icons, Approve / Reject / Comment /
   After sewing with icons, Undo as an icon, the keys in the title's (i)), Workshop (files as
   tinted icon buttons with their word under them on a touch screen and a tick on an approved
   copy, the DXF a blue button, states as chips, Orders with Send to production),
   Questions, All covers (Table/Cards as icons, counts as chips), New cover, a cover's head (the
   strip as chips, Run, Edit details and Desk card as icons, the rejection as a red banner) and
   its seven tabs, Shop (Orders, Requests, B2B customers with the shop's link and its (i),
   Website), every Settings tab, the login and invitation pages (a white card on the light
   ground; the backdrop's story drawn in greys and blue). The public shop and the B2B shop keep
   their own design; the customers' configurator keeps the first studio's colours, Work Sans
   and shape (`.theme-light`).
7. **Codex** did, reviewed here: the conversion of the price, admin and cover-tab files from the
   audit lists (Prices, PriceImport, CoverPrice, Admin, B2BCustomers, PhotoTest, Settings,
   MailOutbox, Viewer, Measure, Catalogue, Reference, SeamEditor, AiAdvice, Learning,
   DeskCorrect, DeskPictures, DeskMeasured, DeskProducts, Unfold, DrawingUpload, Arrangements,
   Questions) and the LICENSES rows. Corrected in review: definitions inside a disclosure kept
   plain; units ("cm above the hem") and states kept visible; the main actions (Save, Save
   draft, Preview, Add …, Approve, Apply, Accept) keep their words beside the icon; one icon
   per meaning (not one generic gear on every heading); an (i) that stood alone under a block
   moved into its heading.
8. **Checks** (scratch copies of the data, never live: mail, public URL, shop domain, Mollie
   and the link key cleared, `cover-users two-factor off`, test users; Playwright in Docker
   with `--user $(id -u):$(id -g)`): `uinav.py` all good (2,328 checks: every role including
   the workshop login, light and dark, 1440, 1024 as a touch screen and 820, strict contrast,
   field borders, the (i)s, named icon controls); `desk_pictures.py` in Chromium, WebKit,
   Firefox and Edge with the office policies; `questions.py` (the three and Edge);
   `measure.py`, `prices.py`, `priceimport.py`, `arrangements_desk.py`, `stock_order.py`,
   `b2b.py`, `memory3d.py` and `make e2e`; `make test` (pytest, ruff, mypy, the stylesheet
   test, the new token test), `tsc`, prettier. Found and fixed on the way: WebKit dropped a
   picture pasted right after the marker closed (the paste listener now reads the marker from
   a ref; main has the same race, rarely); a closed (i)'s text matched a test's search for a
   visible word, so the card is now rendered only while open; tests that named a button by its
   old words (✓ Approve, ✕ Reject, Pieces & revisions, the 3D file input) by the new ones.
   Codex's adversarial review ("nothing lost when text moved to popovers; contrast;
   keyboard/touch access; roles unchanged") found two points, both fixed: a long (i) could run
   off a small or zoomed screen; the Workshop's file icons said what they were only in a
   tooltip, which a tablet does not show (now a short word beside each, and a tick on an
   approved copy). Roles: no condition, route or API call changed; the workshop login's checks
   in uinav pass unchanged.

Better, later: the Desk card's tabs as a segmented control on a phone; the glyphs as an SVG
sprite if their number grows; a design-token export for the website (ADR-105) so both share
the status colours.


## ADR-131 — Rens's second round on pieces (9 Oct 2026): flat walls in one piece, a whole back strip, seams where he draws them

Rens rejected eight covers on their pieces on 9 Oct 2026 (the remarks were processed on 14 Oct;
staging out/rejections2/panels/, each built again, `cover audit` and `scripts/fewer_check.py`,
a compare picture with his marked picture, looked at).

- **D1, D2** ("doorgekruiste panelen reduceren tot één paneel"; the owner on D2: "some faces are
  still split"): the front and back walls were cut at the 18 cm skirt line though each is one
  plane, and the drawing's front view draws the front wall in one piece. The person-read shapes
  (`testdata/drawing_shapes/drawing-d1/d2.json`) drop `skirt_cm`: the 18 cm seam stays on the
  sides only, where the wall meets the leaning side strip. 11 → 9 pieces each; the slope stays
  in two halves (222 and 186 cm across, wider than the roll both ways).
- **S32** (strip struck through; "2 vents from the front to the sides"; "overall shape closer to
  the drawing"): `plan_profile` takes `"strip_whole": true` — the drawn seams stop at the back
  strip, as on the drawing, and the level strip is one piece (3.3 m by 42 cm, fits the roll).
  Vents by hand (`features.vent_positions`): 2 front, 1 on each round end, 2 back, as the
  drawing's 6 arrows. The overall shape: every written size matches (bottom 878.5 cm against
  877.3, back 556.7 against 557.2, front 321.8 against 320.5, depth 98.3 against 99.1), so what
  Rens means is asked (Questions).
- **S43** ("shape and pieces exactly as on the drawing"): read again view by view. The side view
  draws the back upright to 40.64 cm and then leaning in 9.4 cm to 88.01 cm (the dark band along
  the back in the top view); the round nose is a piece of its own whose wall is 40.64 cm all
  round, its top falling to it from the end of the strip and the slope; no seams across the strip
  or the slope. Two swept options: `round_end_apart` (drawing_given: the round end is not joined
  into the strip) and `round_rim_cm` (swept: the round wall at one height). 8 pieces as drawn:
  back band, strip, slope, nose, end wall, front wall, nose wall, back wall; 0.0 % stretch.
  S44 (S43 mirrored) still has the 8 Oct shape: the same change applies, not made.
- **Lucia lounge chair, Feroli corner** (crossed panels one panel): the engine already joins
  them (ADR-099/117, a 3 and a 10 degree fold); the live covers were built before. Rebuilt as
  they are now: 7 → 6 pieces each.
- **Aspen corner** ("a seam along the drawn line", back corner to front corner): the live box's
  own faces given by hand (`box_shape.json`, ADR-117), the shape unchanged, the roof cut from
  where the back chamfers meet, through the roof's kink, to the low front corner. 8 → 10 pieces.
  The audit's gentle folds check now accepts pieces given by hand (that seam is in one plane).
- **Avero corner** ("corners like this divided as the arrows show"): arrows from the high back
  corner to both ends of the back and to the front corner. The Avero's ridge runs along one axis,
  not the diagonal, so those seams cut across its faces and change the roof: asked (Questions),
  not changed.

**Rule and check (ADR-055).** A drawing cover's flat wall that the drawing draws in one piece is
one piece: `cover audit` (gentle folds) now also looks at given covers' walls and fails two wall
pieces in one plane (`seams.flat_split_max_deg`, 1 degree) that fit the roll together. The top's
seams of a drawing cover are the drawing's own (ADR-097) and are not looked at. Swept over the
live covers (read only): D1, D2 (fixed here) and **S18** (its front wall in two, not changed).
Tests: test_facets.py, test_drawing_given.py; an AI lesson in config/ai_lessons.json. Not
generalised (no clear rule from Rens yet): a level back strip split at the corners of C and L
covers (about 35 live drawing covers have two strip pieces in one plane, which `strip_whole`
or its like would join), and the corner layout of the Avero.

## ADR-132 — Links: a drawing cover and a 3D-model cover of the same product, proposed, decided by a person

The owner, 14 Oct 2026: many products are in the range twice, as a drawing cover (drawing-*) and
as a cover computed on the manufacturer's 3D model (suns-*); "link them so we can learn from
them; propose what belongs together, we confirm it, and correct it by hand when it is wrong; use
everything you have." The same day, the example: D2 showed as "sunlounger evora", because the
product list import (ADR-091) turned the word "Evora" in "Evora normal D- Bed" into the SUNS
Evora sunlounger and showed it as a fact. Plan and numbers: docs/plans/drawing-model-links.md.

1. **A link is a proposal until a person decides.** app.db `model_links` (drawing, model,
   status proposed / confirmed / rejected / manual, score, strength, signals, reasons, doubts,
   both covers' facts, mirror, source sheet / proposer / person, note, stale, who and when, a
   version) and `model_link_log` (every change, never deleted). Confirmed, rejected and manual
   (chosen by hand) are a person's decision: `scripts/link_proposals.py` never changes them (not
   the status, score, reasons or version); proposals it no longer makes are marked stale, never
   deleted. Every decision names the version it saw (required); a stale page gets 409. "Choose
   another" also checks the replaced link's version, keeps a target someone already confirmed,
   and refuses a target someone rejected unless the person says so (`override`); bulk
   confirmation sends each row's version and skips stale (withdrawn) proposals, so nothing the
   proposer took back becomes a learning pair (Codex's adversarial review). One row per pair;
   many-to-one both ways (one drawing for both hands, one table drawing for three 340 tables).
2. **Mirror** is a flag on the link (the drawing is the other hand of the model), from the
   names or the hand of the L in plan; a mirror pair is proposed and flagged, never refused, and
   anything that compares or learns mirrors the drawing first (`link_compare.py` swaps its left
   and right skirt sides).
3. **The score** (`coverapi/link_score.py`, weights `links.*` in config/defaults.yaml): names
   (families, types; a D-bed is not a sunlounger), the two covers' boxes, the plan shape read
   from hull.glb from above (straight, L, U, round; the L's hand), the ADR-114 kind, the hand,
   the cover.png silhouettes; the product list's link adds a bonus; a name that says "pair"
   against a size, plan or type that says no multiplies the score by 0.57 and says why. Doubts
   (another family, a type, size, plan or kind that disagrees, the two lists naming different
   hands) make a proposal "unsure" whatever its score. High (≥ 0.85, no doubt) may be confirmed
   in bulk after a confirmation step; the server checks each again. Gemini looks only at tied
   proposals (`--gemini-ties`), as a reason and +0.03, ledger, at most €5 (8 calls, €0.01 on 14
   Oct).
4. **The product list's links are proposals.** Every pair namecode.xlsx linked is in the queue
   whatever its score (93 on live; 41 high, 51 unsure, D2's at 0.34). The Desk card's Products
   block shows them as "proposed by the product list" until confirmed; a rejected or replaced
   link disappears from it, from the SUNS model's Desk label and from the price import's
   `linked_suns` (ADR-113). products.json and drawings.json are never changed. The shop's
   direct order (ADR-118) never read these links (kind and size, the price list's families as a
   tie-break), so nothing changes there.
5. **Learning reads confirmed and manual links only** (`links.learning_pairs`); a proposal never
   teaches anything. The first use: `scripts/link_compare.py`, the box, each skirt side's hem and
   height, each top piece (matched by size), pieces, vents, hem, seams and fabric per pair.
6. **Rights in the API**: viewers and up read `GET /api/links…`; `decide`, `choose` and
   `bulk-confirm` need `edit` (editors, admins); the workshop login is not on its allow-list
   (security.py) and the routes refuse it too. Page: Covers → Links (own glyph), and a
   "Linked to …" chip on a cover's page.

Tests: apps/api/tests/test_links.py (Codex: scoring, D2, mirror, plan shapes, never overwriting a
person, stale, versions, choose/replace, learning only from people, the Desk card and price
import following decisions, rights per role, bulk floor, the script's dry run writing nothing);
test_products_sheet follows the new meaning; the staging test lists the three scripts;
apps/web/e2e/links.py and uinav's Links checks on a scratch copy (fresh app.db, test users).

Better, later: arrangements for the whole corner sets (the 19 drawings without a partner);
products_sheet.kinds telling a D-bed from a sunlounger and a new upload feeding the queue; the
weights fitted on the people's decisions; per-family rules (ADR-082) from the compare report.

## ADR-133 — A fitted drawing cover is true to the drawing's written sizes; mirror-equal skirts one size

Rens rejected five corner covers on their sizes in the second round (9 Oct 2026): C4 "the main
size 343.6 cm becomes 344 cm", C8 "356 cm should be 357 cm", C10 "357 x 357 cm; skirt right and
skirt front not equal, both 92 cm", C29 and S33 "the side skirts and the back skirts do not match
each other nor the drawing; the rest is good". All five are built by the isofit reader (ADR-094),
whose footprint was the traced top view: every edge a few mm off its written size and a hair out
of square, so walls that are each other's mirror image differed by up to 1.2 cm.

- **True to the written sizes** (`drawing_isofit.true_sizes`, before the heights are fitted):
  each outline edge within `drawing.isofit_size_tol` of a written size gets exactly that size;
  an edge within `drawing.isofit_square_deg` (2.5) of a multiple of 45 degrees to the outline's
  frame is turned onto it; the edges without a written size take up the rest (a least-squares
  fit over the corners; refused when a corner would move more than a reading error). A curved
  outline is left as traced. `drawing_read.json` isofit.true_to_written says what changed.
- **Mirror-equal edges are one size**: on an outline that is its own mirror image, mirrored
  edges get one size and mirrored directions, the larger of their written sizes when the drawing
  writes them at most `drawing.isofit_same_cm` (0.5) apart (S33: 244.1 and 243.8 → both 244.1).
  Written further apart they stay as written (C29: 247.7 and 243.3, the drawing's own top edge
  runs 2 degrees off level): the drawing's sizes win over symmetry.
- **The drawing's own number** (`drawing_views.written_cm`): a size converted from inches (C8
  "111.00" = 281.94 cm) is left out when the drawing writes a cm value within 0.5 cm ("282 cm");
  the order's number ("cover 86", "cover 89") is no size (it made C29's 85.9 cm read as 86.0).
- **The hip is cut on the strip's line** (C4, C8, C10, as the drawings draw it): over the strip it
  is one plane; in one piece with the part over the slope its seams were 8-12 mm off flattened.
  Now 5-6 mm; the audit's pieces check still fails these three (the part over the slope is a
  twisted quad; better, later: two flat triangles with a fold line, to be decided).
- Zero-width spikes that exact edges leave in the top's regions are removed before they are
  triangulated (they made 3 x 61 mm slivers, and C8 failed to triangulate).
- **Audit** `written sizes`: a fitted cover whose back lengths are off their written size by more
  than 1.5 mm fails. Lesson in config/ai_lessons.json; tests in test_drawing_isofit.py,
  test_drawing_views.py, test_drawing_given.py.

Results (staging out/rejections2/sizes/, compare pictures in its compare/): C29 and S33 pass the
audit and `scripts/fewer_check.py` (seam pairs 0.4 / 0.0 mm) and go live; C4, C8, C10 have their
written sizes but fail the pieces check on the hip ends (as the live covers do, by more): to the
owner. The rule changes the other isofit covers when rebuilt: C3, C9, C30, C31 (all approved; not
swept live).

## ADR-134 — No air vents on rounded corners; Rens's second-round remarks of 9 Oct on vents and smoothing

Rens at the Desk, 9 October 2026 (round 2, processed 14 Oct; staging `out/rejections2/vents/`):
on the Casto daybed "geen vents op afgeronde hoeken, verder prima hoes!"; on C27 "vents
verdelen zoals eerder aangegeven op tekening"; on C26 "vents herpositioneren zoals aangegeven op
de afbeelding"; on the Vado dining chair "deze hoes specifiek volgt de outline wel heel precies,
mag meer gesmooth worden"; on the Pico bended 2-seater and the Pico corner "achterzijde iets
minder strak omvangen, mag één doorlopende curve zijn. Meer smooth".

- **The rule (ADR-055), for every cover:** `features.vent_on_corners: false`. The vents are placed
  as before (ADR-101), then a vent whose bottom edge with `features.vent_seam_clearance_mm`
  either side (a corner is kept clear like a seam) turns more than
  `features.vent_corner_max_deg` (25: a curve tighter than about 1 m radius) in plan, its turns
  added up, moves along its piece to the nearest straight stretch, clear of the piece's other
  vents (`finish._off_corners`). The plan of each piece's bottom edge and the pieces at its two
  ends come from panels.npz (`Walls.hems`); the flat bottom edge is matched to it by its end
  seams (both ways round when they cannot tell). A piece that is round all along (a round
  cover's strip, a chair's curved back) keeps its vents; places a person set
  (`features.vent_positions`) are kept. The audit's vents check fails "on a rounded corner"
  with the same measure (only where the piece has a straight stretch); test_finish.py
  `test_no_vent_on_a_rounded_corner`, `test_a_round_wall_keeps_its_vents`; an AI lesson.
- **C27:** the drawing draws its "10 Air Pocket" with ten arrows; Rens's marks of 8 Oct (circles
  on four front walls and the left arm's end, crosses on the back) agree with them. Placed by
  hand (`vent_positions`): two on the long left arm's outer wall (its side and its rounded end,
  as the drawing's arrows and Rens's circles), one each on the left back, the back and the
  four front walls Rens circled, two on the right arm's outer wall (its end and the back
  corner). The two short front walls he did not mark (skirt-right-3, skirt-front-1) have none.
- **C26:** Rens approved it on 14 Oct, after his remark of 9 Oct, with the same cut file (made
  9 Oct 09:40): his approval stands, nothing changed.
- **Vado:** `hull.plan_round_mm: 3000` in its cover.json (the closing that rounds bays): the
  waisted sides and the front become gentle curves over the chair; 6 pieces instead of 7.
  Only this cover ("deze hoes specifiek").
- **Pico bended 2-seater and Pico corner: to Rens (Questions).** Their back in plan is already one
  convex curve within 1–2 cm (closing the dents, or smoothing the outline and pushing it out
  again where it would come too close, changed it by under 1 % or put ears on the corners), so
  what "minder strak, één doorlopende curve" should change is not clear from the plan; a
  question with the pictures. Not changed.
- **Not swept live:** 19 of the 446 live covers have a vent (placed by the rule) on a rounded
  corner today (read-only sweep, `out/rejections2/vents/corner_sweep.json`): S53, S60, D5, R3,
  S37, S43, S44, S45, the Sato dining chair, Blocchi 2-seater moon right, Casto sofa bench,
  Feroli chaise longue and corner, Fiora daybed, Pico corner, Pienza moonshape left, Vento
  angled, Vento hocker, Vivaro L-part. They change when they are built again.
- Literals 25 elsewhere (compare.py's ICP rounds, drawing.py's width stations) became named
  constants, so the registry test tells them from the new default.

## ADR-139 — The website for AI agents: an open API with limits, discovery, a CLI; a person always pays

The owner (14 Oct 2026): "AI passes the sizes and the best cover's result comes straight back
into the CLI." He approved a strategy in four layers (API, MCP server, discovery, CLI) and
decided: the API is open to everyone without a key, with limits (about 60 requests an hour per
address, IPv6 per /64, and 1,000 a day for all anonymous use together); anonymous use gets no
photo or AI recognition; a free partner key gives higher limits and photo recognition with a
daily budget per key; paying is always done by a person (an agent gets an order link, never
pays); no personal data in any answer. Later the same day: B2B too ("beide"): a partner key
linked to a business customer, or that customer's B2B login, gets its own prices ex VAT and
links into the B2B shop; one company's prices never reach another caller. This is **phase 1,
on the preview only**. Plan: docs/plans/agent-access.md; handbook: docs/handbook/agent-api.md.

- **The API** (`coverapi/agent_api.py`) is a FastAPI sub-app mounted at `/api/v2`, with its own
  OpenAPI (`/api/v2/openapi.json`, descriptions written for models) and server-rendered docs
  (`/api/v2/docs`: no scripts, so the CSP holds; Swagger UI would need a CDN). Endpoints:
  `GET /kinds`, `POST /match`, `POST /quote`, `POST /order-link`, `GET /go/<token>` (the link a
  person opens), `GET /covers`, `GET /covers/<code>` (+ `picture.jpg`, `preview.glb`),
  `GET /preview.glb`, `POST /suggest` (key only). Stable English field names; sizes in cm (or
  `"unit": "mm"`), answers in cm and mm. The same sub-app is mounted at `/api/b2b/v2`, where the
  B2B session cookie (path `/api/b2b/`) arrives.
- **Kinds** (`config/agent_kinds.json`, owner-editable): sofa, corner_sofa, chair, side_table,
  footstool, lounger, daybed, dining_set, round_dining_set and the five barbecues (only while
  barbecues are offered, ADR-119), each with aliases ("L-shape", "table", "sunbed") and its
  sizes mapped onto a configurator product's fields: required or optional, the range from
  config/quote_products.json, what it means and how to measure it (drafted from the
  configurator's fields; the owner checks the texts). An optional size not given takes the
  configurator's default and the answer lists it under `assumed`.
- **Matching and prices are the shop's own**: `coverengine.match` (ADR-064, ADR-114: SUNS,
  approved drawing covers, barbecues) and `quote.proposal`. The consumer price of an existing
  cover (the published fixed B2C price, else its own sizes minus the stock discount, ADR-118)
  moved into `shop.b2c_cover_price`, used by the shop's quote and the API alike; a business
  caller's price is `b2b.unit_price` (its list, the list's fixed price, its own fixed price;
  ex VAT, its VAT rate or 0 when reverse-charged). Results: existing covers with a fit of at
  least `match.choice_pct`, "good" from `match.threshold_pct`, else "possible"; the
  made-to-measure cover after the good ones and before the possible ones; notes say what is
  unsure (no hand given for a corner sofa, matching in shadow mode, a table that holds rain,
  no lead time set). Never a cost, labour, margin or the costing: the answers are built from a
  whitelist, and a test walks every answer for those keys.
- **Errors an agent can act on**: `{"error", "message", "hint", "field", "docs"}`, e.g.
  `missing_size` "depth missing for kind sofa" with how to measure it and the range;
  `unknown_kind` with the list; `unknown_size`, `out_of_range`, `conflicting_sizes`,
  `unknown_colour`, `kind_mismatch`, `unknown_cover`, `rate_limited`, `daily_limit`,
  `unknown_key`, `company_inactive`, `key_needed`. Request models forbid unknown fields: a
  name, e-mail, phone or address is refused ("this API takes no personal data").
- **Callers and limits** (all `limits.*`, `[server-only]`, defaults.yaml): anonymous
  `agent_per_hour` 60 per address (the Worker's `x-client-ip`, IPv6 as its /64,
  `limits.ipv6_prefix`) and `agent_anon_per_day` 1,000 together; a partner key
  `agent_key_per_hour` 600 and `agent_key_per_day` 5,000; a B2B login counts like a key, per
  company. Headers `RateLimit-Limit/Remaining/Reset` (+ `X-RateLimit-Scope`), a 429 with
  `Retry-After`. Every proposal still counts against `limits.quotes_per_minute` (ADR-123).
  The hourly window is in memory; the daily counts are the usage table (below), so a restart
  keeps them.
- **Partner keys** (`agent_keys` in app.db: a name, the SHA-256 of the key, its first 8
  characters, who made it, an optional B2B company, revoked): made and revoked by an admin in
  Settings → Website & API keys (`/api/admin/agent-api`), shown once (`cvk_…`), sent as
  `X-Api-Key` (dropped from Caddy's log) or `Authorization: Bearer` (redacted by Caddy). A wrong
  or revoked key is refused, never taken as anonymous; a key whose company is not active is
  refused. The old webshop API's keys (`/api/public/v1`, ADR-123) are separate and unchanged.
- **Photo and page recognition only with a key**: `POST /api/v2/suggest` runs the shop's
  suggestion (`shop_suggest.run_suggestion`, moved out of the shop's route so both share it)
  with every paid call on the key's own ledger line (`spend.for_visitor("agent:key:<id>")`):
  at most `agent_key_photos_per_day` (20) a day and `agent_key_eur_day` (€1) of AI a day per
  key; the month's budget (ADR-078) still stops everything. Codex's adversarial review found
  that parallel requests could all pass the same checks: now one recognition runs at a time
  per key (a second gets 429 `busy`, so the euro check sees every earlier call's cost) and the
  day's slot is taken in one SQLite write transaction before any await. Its second round: a
  B2B login alone may not start a paid recognition (a partner key only, individually
  revocable), and a cover page (which computes a price) counts against the anonymous limits
  and answers 429, not 404, over them. Round 3: a new 3D preview counts on the agents' work
  cap and only the product's own sizes make its cache key. Round 4: the pipeline's paid
  stages check only the month's budget, so a recognition starts only while a whole run's
  worth (`limits.agent_key_eur_per_recognition`, €0.10; a run costs €0.03-0.05) of the key's
  day is left. Round 5: a run can cost more than that estimate (grounded searches bill per
  query), so the key's day cap now holds at every paid stage: `spend.for_visitor(who,
  cap_eur)` makes `spend.guard` (called before every paid call) refuse once the key's day is
  reached; only stages already in flight (the parallel searches) can still finish. Round 6:
  that residue stays (a per-stage cost reservation inside the shop's recognition pipeline is
  for later; it is bounded by the stages in flight, the 20 recognitions a day per key and the
  month's budget); and every agent page (the guide, the covers, llms-full.txt) now counts
  like an anonymous call.
  Anonymous: 401 `key_needed`, and
  `product_url` in a match is read as text only, never fetched. Its route has the shop's photo
  body limit (bodylimit and the Caddyfile).
- **A person always pays.** `order_url` opens the configurator with the product, the sizes,
  the colour and (for an existing cover) `stock=<code>`; `POST /order-link` stores that address
  behind a token for `limits.agent_link_hours` (24) and adds `checkout=1`: the configurator
  goes to the checkout once its price for exactly those choices is on screen (ADR-129's fresh
  quote). Opening it creates nothing; the person gives name and address, accepts the terms and
  pays with Mollie as before. An expired link is a 410 page with a link to the configurator.
  For a business caller the link is `/b2b/?…#configure` (the B2B configurator reads the same
  address now, `stock_model` included): the person logs in and orders on account. No endpoint
  writes an order, a request or a payment. Caddy's log redacts `/go/<token>`.
- **Usage** (`agent_usage` in app.db: day, `anonymous` | `key:<id>` | `b2b:<company>`, endpoint,
  count; nothing else) shown per day for 7 days in Settings → Website & API keys.
- **Discovery** (`coverapi/agent_pages.py`, `agent_ld.py`): `/llms.txt` gets a "For AI agents"
  section (API, OpenAPI, kinds, guide, covers, CLI, rules) where the API is on; `/llms-full.txt`
  (who we are, the API, the measuring guide per kind, every existing cover with the furniture
  sizes it fits, the rules); the measuring guide `/measure` and `/measure/<kind>` (schema.org
  `Product` with the size ranges as `additionalProperty`, an `AggregateOffer` without a price,
  and a `HowTo`); the covers `/covers` (`ItemList`) and `/covers/<code>` (`Product` with
  `size`, the fitting sizes as `additionalProperty`, an `Offer` with the price as text, VAT
  flag, `MadeToOrder`, the delivery promise as `shippingDetails` only when set; no invented
  delivery time). Plain HTML without scripts. These cover pages are the "product pages" and
  the sizes feed (the shop had no catalogue page yet, ADR-103's "better later").
- **Preview only**: everything answers only where `agent_api.agent_on`: the new shop setting
  `agent_api_enabled` (off; Settings → Website & API keys), or the preview website (its host
  `preview.<domain>` and the Worker's key, as `bbq_enabled`), or a logged-in colleague. The
  Worker (`apps/site/src/agent.ts`) passes `/api/v2/*`, `/api/b2b/v2/*`, `/llms-full.txt`,
  `/measure*` and `/covers*` only on the preview or with `AGENT_API = "1"`; on the live site
  they are a 404 at the edge, and the live `/llms.txt` is unchanged. Never cached at the edge,
  no cookies through, the security headers on every answer, `noindex` on the preview. CORS:
  `*` for GET and the POSTs, no credentials; the B2B mount has no CORS (its own pages only).
  With the website link closed the studio answers these paths only through the website, as
  the shop (ADR-066).
- **Which code answers (15 Oct)**: the preview's `/api/v2/kinds` was the studio's 404 ("not open
  on this address") although the source sent `x-site-host`: the preview still ran the bundle of
  15 Oct 09:08 UTC, from before that header (da0deaa, 10:19 UTC), and the LINK_KEY rotation at
  11:07 UTC had made a new version from that old bundle (a secret change never rebuilds). Without
  `x-site-host` the studio reads X-Forwarded-Host, which Caddy rewrites to covers.suns.nu, so
  `preview_site` was false; the key itself was fine. Now every Worker answer carries
  `x-site-build` (`git describe` of the deployed source, `--var BUILD:` in both deploy scripts,
  "unknown" when deployed without them), so one `curl -I` shows a stale Worker.
- **The CLI** (`clients/cli/covers.py`, standard library, `uv tool install ./clients/cli`):
  `covers find|quote|kinds|link|cover`, a table or `--json`, `--api` (default the preview),
  `--key`; exit codes 0, 2 (the input), 3 (429), 1.
- **Lead time**: a new shop setting `custom_lead_time` per language; empty (now): "confirmed
  after the order". The delivery promise of an existing cover is ADR-118's
  `stock_delivery_note` (empty on live; the preview's overlay sets it only for the shop's own
  pages, so the API on the preview states none either).
- **Security** (ADR-123 holds): the body limits apply (2 MiB for JSON; the photo limit for
  `/suggest`), all new numbers are server-only, the workshop role is unaffected (`/api/v2/` is a
  public path like `/api/shop/`; the key admin is admin-only), no studio data (no model files
  but a cover's product photo and a 3D preview built from its sizes, no patterns, people or
  orders), `Cache-Control: no-store` and `Vary: X-Api-Key, Authorization, Cookie` on the answers.
- **Tests**: `apps/api/tests/test_agent_api.py` (match on known covers, errors with hints,
  limits, keys, no personal data or costs, B2B scoping between two companies and anonymous, a
  B2B login, order links and their expiry, nothing ordered, pages and JSON-LD, preview-only),
  `test_agent_ld.py`, `apps/site/test/worker.test.ts` (preview vs live), `clients/cli/test_covers.py`
  (a fake server and the real app).
- **Better later** (phase 2, 3): an MCP server over the same API; agent payments (ACP, AP2/UCP)
  once Mollie supports them (what to verify: docs/plans/agent-access.md); the guide's texts in
  every language through the CMS; per-key limits set per partner; a price per B2B key in the
  cover pages' JSON-LD is never wanted (public pages are B2C).
- **Fix (15 Oct 2026): the preview said "not open on this address".** Caddy 2.6 trusts no
  proxy, so it replaces the Worker's `X-Forwarded-Host: preview.s2dio.living` with its own host
  (`covers.suns.nu`; reproduced with a local Caddy and an echo server). The key arrived, the
  host did not, so `agent_on` (and `bbq_on`, which only looked right on the preview because of
  the build's overlay) never saw the preview. The Worker now also sends `x-site-host` (the host
  it answered for, set by the Worker whatever a visitor sends; Caddy passes it), and the studio
  reads it first (`shop.site_host`, `shop.preview_site`), trusted only with the Worker's key.
  The live shop's host stays closed. Tests: `test_preview_gate_behind_caddy`, the Worker's
  "x-site-host" test. Both the studio release and the preview Worker's deploy are needed.

## ADR-136 — The Questions answered 11–14 Oct 2026, processed (QUESTIONS 27–101)

Twenty-four questions in Work → Questions (ADR-109) were answered but never processed. Each
answer below is what was done with it; the Dutch note on the question says the same.

- **BBQ covers with side tables (QUESTIONS 81, owner 12 Oct):** "one vent fewer on that side,
  the rest by the rule". `features.vent_short_piece_ok` (default false; on in
  `config/presets/bbq.yaml`): a piece whose bottom edge is too short for a vent plus a seam
  allowance each side has none, and that is no warning (elsewhere it still warns "check").
  Test `test_a_too_short_piece_may_simply_go_without_a_vent`; an AI lesson. The Kamado Joe
  Classic III on cart, Monolith Classic with TWO.55 tables and The Bastard Large Complete
  (each a 24–25 cm strip beside the front) were rebuilt in staging, pass the audit and the
  re-measure, five vents each; the BGE Large with EGG Mates' problem is a scrap piece at a 3°
  fold, not a vent, and stays out.
- **Pico bended 2-seater and Pico corner (QUESTIONS 101, Rens 14 Oct):** "the back wall plus
  the two back corners as one roomy arc from above, a few cm looser round the cushions, no
  kink at the corners". `hull.plan_back_arc` (per model, default off) with
  `plan_back_ease_mm` 30, `plan_back_round_mm` 150 and `plan_back_taper_mm` 400 (to confirm):
  behind the plan's widest points the follow outline is filled out to its convex hull, grown
  by the ease, its corners rounded where that stays outside the plan, the side walls leaning
  out over the taper so there is no step; never smaller than the plan. `outline.back_arc`,
  test `test_the_back_is_one_roomy_arc_on_request`; an AI lesson. Per model on request, so no
  sweep: no other cover's plan changes.
- **B2B terms (QUESTIONS 44–53, owner 11 Oct):** the payment term is 14 days
  (`b2b.DEFAULTS["payment_days"]`, the studio's B2B terms form; no stored setting on live, so
  the release carries it); everyone with a login may order (as built); no minimum order (as
  built); dealers may order made-to-measure (the B2B configurator, as built) and "straight
  into production" is the click of ADR-128 (QUESTIONS 86, 12 Oct, the later answer); fixed
  prices per dealer (as built, per company in Shop → B2B customers; Sunsit's prices are the
  owner's to enter); later online payment by Stripe (QUESTIONS 52).
- **Delivery cost (QUESTIONS 28/29, owner 11 Oct):** "a link with the carrier (DHL), the cost
  from weight and box". `coverapi/shipping.py`: a carrier interface with the fixed amount per
  country (Shop settings → shipping) as the fallback; the parcel from the cover's cut fabric
  (`shipping.fabric_g_per_m2`, `pack_g`, `folded_l_per_m2`, `boxes_cm`, all to confirm);
  `shipping.carrier: fixed | dhl`. DHL gives no rate until the owner's account keys are in
  deploy/.env, so nothing changes for orders today. The order records where its delivery cost
  came from. Plan and the owner's steps (the account, the fixed amounts, the € 18.50 cost line
  in the price set): docs/plans/shipping-carrier.md. Tests: apps/api/tests/test_shipping.py.
- **Stripe or Mollie (QUESTIONS 30, 31, 52):** compared in docs/plans/payments-stripe.md
  (Codex, public price pages of 14 Oct). Advice: Stripe for the consumer shop and dealers
  later, behind a small provider interface that keeps Mollie's code; nothing is live with
  Mollie, so there is nothing to migrate. Not built yet: it needs the owner's Stripe account
  and test keys (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`).
- **Turnstile (QUESTIONS 32, owner 11 Oct: "yes, I make the keys"):** built by Codex,
  reviewed: `shop.turnstile_ok` verifies a token at Cloudflare only when
  `TURNSTILE_SECRET_KEY` is set (environment or deploy/.env, `security.env_value`); then no
  token, a refusal or no answer is "please try again". It guards the order, the "ask us"
  match form (an e-mail given; the configurator's own automatic look-up stays free) and the
  photo/link suggestion. A token works once, so a retry of the same checkout (its
  idempotency key, ADR-129) is not asked again. The page shows the widget ("interaction-only")
  only when `TURNSTILE_SITE_KEY` is set; the Worker's CSP and the studio's CSP for /shop/
  allow https://challenges.cloudflare.com. The honeypot and the limits stay. Without keys
  nothing changes. The owner's steps: docs/handbook/webshop.md.
- **VIES (QUESTIONS 50, owner 11 Oct):** built by Codex, reviewed: `coverapi/vies.py` asks
  the EU's VIES REST API when an admin adds a company or changes its VAT number or country,
  and with "Check VIES" on the company; the result is kept on the company (`vies`). Reverse
  charge then follows the rule (an EU country other than NL and a valid number); a change of
  the switch in the same save overrides it and is noted; VIES unreachable leaves the switch
  as it was and records the error. The checkout never calls VIES. Tests: test_vies.py.
- **Cooling-off (QUESTIONS 27):** 14 days for a cover from our range, none for made-to-measure:
  already so in the checkout's checkbox and the terms and returns pages (ADR-103). No change.
- **Share picture (QUESTIONS 34):** `/brand/og-shop.png` is now a still of our own film (the
  Kota 2-seater, ADR-108) with "Hoezen op maat. Made to measure.", made by
  `scripts/film/og_image.py`. Live with the next release (the setting `og_image` stays empty).
- **Balloons and frame (QUESTIONS 42):** always sold separately, as now. No change.
- **The film's setting (QUESTIONS 54):** the owner is already making a film in an Ibiza setting;
  the terrace film stays until then. No change here.
- **Drawcord (QUESTIONS 65):** pulled tight: already `drape.hem: held` (4 Oct); the comment says
  it is confirmed.
- **A measured size is good within 0.5 cm (QUESTIONS 70):** `tolerance.cover_mm` 5, confirmed.
- **S45 (QUESTIONS 79, Rens 13 Oct):** 358.4 cm round (141.1 in), as now. No rebuild.
- **Defaults in Settings (QUESTIONS 93, Rens 14 Oct):** none editable, stay read-only.
- **S32 (QUESTIONS 100, Rens 14 Oct):** "good as it is, with the strip and the vents changed";
  the vents agent owns S32's rebuild; nothing done here.
- **Usable roll width (QUESTIONS 64, owner 11 Oct: "b) 150 cm"):** the question read "Coverlast
  is 152 cm wide; the program uses 148 usable. Is it 148, or 150 of the 152?", so the answer
  most likely means `roll.width_mm` 1520 and `roll.usable_width_mm` 1500 (today 1500 and
  1480). Not changed: it decides which pieces fit the roll, and CLAUDE.md's "roll width
  1500 mm" says otherwise; the owner confirms first. Today no live cover has a piece between
  1440 and 1500 mm wide, so the change would only matter for covers built afterwards.

## ADR-137 — Sizes are measured from the cover's own lower edge; Rens's third round on C4, C8, C10 and the Nardo pair

Rens at the Desk, 14 Oct 2026 (round 3, after ADR-133 made the plan sizes exact): C4, C8, C10
"hoofdmaten komen niet overeen met de tekening"; cover 44 & 45 (S13 & S14 Nardo) "beter de vorm
volgen zoals in de tekening". Staging `out/rejections3/sizes/`; every size checked by me and,
independently, by Codex.

- **The cause (C4/C8/C10).** The covers were right (pieces, 3D, cut file, check list: C8 357 x 282,
  back 84, inner front walls 44, arm ends 31, arms 92 deep, strip 30, end run 40, as written). The
  size drawing (`sizes.pdf`) and the cover's Sizes tab measured every height from hull.json's
  `hem.height_mm`, the hem *parameter* (5 cm); a drawing cover (`hull.top: given`) ends at the
  ground, so every height they showed was 5 cm short (C8/C10 79/39/26 for 84/44/31, C4 85/38/21.4
  for 90/43/26.4), and "5.0 cm above ground". The round-2 plan sizes (344 x 344, 357 x 282,
  357 x 357) hold.
- **The rule (ADR-055), every cover:** `export.drawing.hem_height` takes the lowest point of the
  cover's own hem; hull.json of a plain (box/given) cover records the lower edge as built. A
  sizes.pdf carries its format (`SIZES_FORMAT`, PDF subject); an older one is made again when
  opened, even when newer than its pattern (the approved/ stamped copies stay as approved). Read-only
  sweep: 118 live covers (115 drawing covers, D8/S53/S60 cover surfaces) end below the hem
  parameter, so their size drawings change; no pattern or cut file changes.
- **Check:** the audit's `written heights` (an isofit drawing cover's shown height and lowest
  skirt against the written back and end heights; all 9 live isofit covers pass with the fix).
  Test `test_size_drawing_measures_from_the_covers_own_lower_edge`; a lesson in
  config/ai_lessons.json. Not changed: C4's bracketed "(17 cm)" is 43 − 26.4 = 16.6 on the cover
  (the drawing's own rounding). C3, C9, C30, C31 still fail `written sizes` (ADR-133, not rebuilt).
- **Live:** the fixed sizes.pdf put in C4/C8/C10 (no rebuild); C8/C10 back to Rens; C4 he approved
  after his remark, so it stays approved with a note. The Sizes tab shows the right heights only
  after the release.
- **Nardo (S13 & S14):** the AI had built one 260 cm wedge with 88.6 as depth. Read again corner by
  corner from the drawing's vector lines (every corner within 0.2 pt; Codex the same within 0.06):
  two covers of one shape, mirror images (one seen from the front, one from behind): 260 x 80, back
  87 with a 25 cm strip, an arm block 25 cm wide at 87, the seat to a 42 cm front over 145 cm, a
  55 cm ramp to the arm, a 27 cm low end rising over 35 cm with a hip (88.6 = the hip edge,
  sqrt(35²+55²+60²); 225 = the back's top edge). `faces`, 10 pieces, 0.0 % stretch, vents by hand
  in the middle of the front wall and the arm end (2 per cover). Whether the second cover's long
  vent goes on its back as drawn: question #102.

## ADR-135 — Every Desk action says how it went; a second approval is refused; "Waiting for us"

14 Oct 2026, v2.0.0: the owner reported that **Approve** on the Desk "seems to do nothing".
Root causes, from a reproduction on a scratch copy and the live log:

1. **An approval is slow and the button gave no sign.** `desk.apply` stamps `sizes.pdf` and
   `cutting-list.pdf` (ADR-128) and makes the size drawing first when it is missing
   (`approval.prepare` → `ensure_sizes`): 8 s on a drawing cover, 40 s for three overlapping
   ones. `CardView.act` cleared its message, showed nothing busy and left every button live
   for that time, so the click looked lost and people clicked again (a rejected cover
   included: the server approves it like any other; a browser check that waited 2.5 s saw
   no answer yet).
2. **Nothing refused a second approval.** Each extra click re-stamped the PDFs and added an
   approval to the history.
3. **The next card was chosen from the list as it was when the button was rendered**, by a
   timer 900 ms after the answer, whether or not the person was still on that card; the
   queue reload was not awaited, and a failed reload replaced the whole Desk with an error.
4. **Refusals were easy to miss and Undo was offered with nothing to undo.** On live (09:37)
   the cover's history holds a fit, an undo, then three `409 nothing to undo`: the Undo icon
   stays while the history is not empty. The message was a grey line beside the buttons.
5. The `401` in the console is the session probe (`GET /api/auth/me`) before the login:
   harmless.

No element covers the action bar (`elementFromPoint` on the Approve button is the button,
Chromium, WebKit, Firefox, 1440 and 1024).

Decision:
- One action at a time per card (`busyRef`): the clicked button says **Approving…** (a
  spinner), every other action and key waits; when the answer comes a message at the top
  right (**Approved: <cover>**, kept while the next card opens), the next card opens at once
  and the queue (the Desk's own state, which outlives the card) refreshes its list and counts;
  a Comment reloads its card. The next card is chosen **before** the action (the list changes
  after it) and opened only while the person is still on that card; after the last card the
  message says so. `desk_pictures.py` now waits for that move before it reloads the page
  (WebKit reports a fetch cut off by a reload as an error).
- A refusal (409, 400, 403) shows the server's reason in red, as a message at the top right
  (`role=alert`) and beside the buttons ("Approve D2 refused: already approved by Wout …"),
  and the card and the queue are reloaded (someone else may have acted).
- `POST /api/desk/<id>` `approve` on a cover whose approval holds for its current cut is a
  `409` naming who approved it and when, checked before stamping and again under the lock.
  A new cut can be approved again as before; an order on an approved catalogue cover is
  noted by `mark_order` (ADR-128).
- The card answers `can_undo`; the Undo icon and the key `u` follow it.
- The keys do what the buttons do: not while a dialog, a zoomed picture or an action is
  open, not with Ctrl/Cmd/Alt or a held key; `a` on an approved cover says so.
- The order's quick approval in the queue: busy, its own message, the queue and the open card
  refreshed.

Rens asked the same day: "if a cover is not under 2nd round, does that mean it hasn't been
changed since my last comment?" Each queue item now carries `last_remark_time` (a person's
reject, comment, note or fit, not undone), `last_change_time` (the studio's last action) and
`open_remark` (the remark is newer). Rows and the card head show **Changed <date>** or
**Not changed yet** (orange). **Waiting for us** lists the covers with an open remark, the
rule of `scripts/desk_open_remarks.py` (which now takes its names from `desk.STUDIO_NAMES` and
`desk.REMARK_ACTIONS`); **2nd round** lists only covers changed after a remark that wait
again (new or AI checked).

Checked by `apps/web/e2e/desk_actions.py` (Chromium, WebKit, Firefox at 1440 and 1024 touch:
approve an AI-checked and a rejected card by the button, by the key, reject, comment, a
refusal, an order's quick approval; counts, list and next card each time; the filters) and
`apps/api/tests/test_desk.py`. Not done: making the approval itself faster (the size drawing
could be made when the cover is built instead of at the approval).

## ADR-138 — The Desk shows a cover's current files; Rens's third round on vents (14 Oct 2026)

Rens rejected C27, C28 and S32 again on 14 Oct 2026 on their vents ("kruisjes weg, cirkels erbij";
staging `out/rejections3/vents/`, each picture mapped with `scripts/desk_marks.py`, the live
vents projected on it, read twice: by us and independently by Codex).

- **The cause on C27 and S32 was not the vents.** Both were rebuilt and reopened at 14:44 and
  14:35; Rens marked them at 14:49 and 14:43 on pictures that show the vents (and on S32 the
  split back strip) of 9 Oct. The Desk's 3D asked for a cover's files with a fixed `?v=0` and the
  API sent no Cache-Control, so the browser kept its cached `vents.json` and panels. **Fix:**
  `/api/models/{id}/files/*` answers with `Cache-Control: no-cache` (the browser asks again every
  time; a 304 when nothing changed), and the Desk's viewer asks with the time the card was
  loaded (`Desk.tsx`, also its cover.png). Test: test_api.py (no-cache on vents.json).
  `scripts/desk_marks.py` now draws the cover's current vents (green facing, grey away,
  numbered) on the picture and lists them in its JSON, so a picture of an older state shows at
  once (test_desk_marks.py). An AI lesson. Any cover reopened after a rebuild may have been
  judged on its old 3D the same way; not swept (the Desk keeps no record of what a browser drew).
- **C27** (marks read on the 9 Oct state): the two vents of each inner wall pair (left arm
  `skirt-right-2`/`-3`, right arm `skirt-front-1`/`-2`) crossed, one circle between them; circles
  on both arm ends; the vents on `skirt-right-1` and `skirt-front-3` kept. Against the live
  cover: the vent on skirt-right-2 moves from its middle to the circle (84 cm along, the seam
  clearance stops it 6 cm short), the one on skirt-front-2 to the circle (23 cm from front-1),
  the two arm-end vents onto the circles (15–23 cm). 10 vents, as the drawing.
- **C28** (the picture shows the live vents): crosses on front-2, front-1 (the middle front) and
  left-3; circles on both arm ends. 9 vents; the drawing writes 10: Rens is asked (Questions #103).
- **S32** (marks read on the 9 Oct state, four front vents): all four crossed, one circle between
  each pair, circles on both round ends. The two front vents move to the circles (from the
  middles of the long front pieces, 1.0 m from the centre, to 0.7–0.8 m), the end vents onto the
  circles (25 cm). 6 vents, as the drawing.
- **C26:** not changed (approved 14 Oct 09:21 with the cut file of 9 Oct, after his remark of
  9 Oct asking to move the inner vents to the arm ends, which that file does not do): asked on
  the card and in Questions (#104) whether the approval stands.
- All by hand (`features.vent_positions`), so a rebuild keeps them. Checked twice (audit, fewer_check;
  Codex read the marks and the staged result independently and agreed); live 14 Oct, reopened.
- **C28, 15 Oct 10:06** ("op de plekken van kruisjes lopen de seams van de skirt niet goed over
  in de seams van de top panelen"): a general fault of `plan_profile`. A front wall was put in
  the stretch of the back edge it projects onto, so where the front is not parallel to the back
  (the curled arms of a C) its vertical seams stood 10–40 cm beside the ends of the top's seams.
  Now the outline gets the points where the top's seam lines cross it (`_ring_with`) and each
  front wall bit belongs to the top section it stands under. C28 rebuilt from its drawing
  (`fewer_build --codes C28`): the top unchanged, the wall pieces split at the top seams (front
  116 → 96, 51 → 66, 127 → 130 cm, the other arm 89 → 91, 71 → 89, 123 → 105 cm), the 9 vents
  mapped onto the new pieces (two middle ones 9–12 cm to the middle of their new piece). Read
  and checked by Codex too; live 15 Oct, reopened. Test: test_plan_profile.py
  `test_the_front_walls_continue_the_top_seams` (fails on the old code). **Not swept:** the other
  plan-profile covers have the same fault until built again: C27 (front walls up to 40 cm off;
  waiting for Rens's round), C26 (approved; a rebuild needs a new approval), S32.

## ADR-140 — Rens's third round on pieces and seams (14 Oct 2026): a flat bag, S43/S44's seams as drawn, a stale 3D view

Rens rejected six covers again on 14 Oct 2026 (staging `out/rejections3/panels/`; each read with
`scripts/desk_marks.py` and by looking, a second reading by Codex before building, `cover audit`
and `scripts/fewer_check.py`, compare sheets and a size table in `compare/`, Codex again on those).

- **D1, D2** ("doorgekruiste panelen reduceren tot 1 paneel per afbeelding", two pictures each): his
  crosses straddle the 18 cm line on the front wall and on the back wall, but those walls have been
  one piece each since 14 Oct 14:04 (ADR-131): the pictures show the 9 Oct cover, the Desk's 3D
  view cached in his browser (the cause and fix of ADR-138, found here independently). Nothing
  rebuilt; the cards reopened with the sizes (front 266/230 x 40 cm, back 266/230 x 82 cm, both on
  the roll) and "reload with Ctrl+F5". The owner's "these faces must fit on a roll" and question
  64's 150 cm change nothing: the crossed walls fit 148 already; the slope (not crossed) is
  222 x 194.6 cm (D1) and 186 x 179 cm (D2), wider than 150 cm both ways. `roll.usable_width_mm`
  stays 1480 (the questions round owns #64).
- **S43, S44** ("seams beter volgen zoals op tekening"): the drawing ends the strip on a slanted
  line A-B before the nose, runs the leaning back band on round the back of the nose to C on the
  rim, the slope on to D on the front of the nose (A-D), and cuts the walls below C and D, where the
  straight front turns into the curve and where the concave curve meets the nose. The swept builder
  cannot do this (it ends both square at the arc's end), so `scripts/s43_shape.py` writes the pieces
  as a "faces" shape: the same body as ADR-131, cones from A and B where the strip, band and slope
  run on (every piece flat triangles and ruled quads, 0.0 % stretch); B where the written 185.94 cm
  cushion circumference ends. 10 pieces (8 and 9 before), 4 vents placed by hand (end, back, round
  front, nose wall; the 27 cm concave piece has none: `features.vent_short_piece_ok` per model).
  Open: S43 writes the bottom circumference 252.88 in (642.3 cm), S44 262.98 in (668.0 cm) for
  the same sizes; the cover measures 654.7 (question #112).
- **U1, U2** ("de hoes moet gewoon 2x het paneel zijn ... rondom aan elkaar gestikt op de onderste
  lijn na"): a new drawing shape `flat-bag` (`drawing_given.flat_bag`): two equal panels of one
  outline (`outline_cm`, `round_cm` per corner), sharing every point of the stitched edges, standing
  off each other inside by at most 5 mm so the 3D cover has an inside and a mouth (under 0.1 %
  length); the lowest line is the open hem; `no_vents` in the shape (or the reader) sets
  `features.vents_min`/`vents_per_metre` to 0. The route-A reader's lone side view (ADR-102, U2
  turned round) now builds this flat bag too: U1 and U2 both read themselves this way. 2 pieces each,
  63.0 x 275.5 / 250.5 cm cut. The pocket, zipper and rope are not in the pattern (question #113).
- **Rule and check (ADR-055):** the audit's new `open seams` check fails two pieces whose free
  edges lie in one place above the hem (from panels.npz, joined back by `original_vertex`): S43's
  first faces left a 163 cm gap between the back band and the back wall that every other check
  passed. Swept read-only over the live covers: C1, C2, C3, C9, C24, C26, C27, C28 and S32 have such
  unjoined edges (plan-profile and isofit covers); not changed here, for the next round. Tests:
  test_drawing_given.py (flat bag, rounded corner, side view, S43 seams, open seams); lessons in config/ai_lessons.json.


## ADR-141 — L1, L2, L3 are chaise longues: the workshop's STEP files give the shape, the drawing the sizes

Rens at the Desk, 15 Oct 2026, on L1, L2 and L3 (covers 39, 40, 41: Portofino, Evora and Aspen CL
right): "ter referentie heb ik een STEP file geupload die de tekening zou moeten matchen, probeer op
basis van die info een betere vorm hoes te genereren". The STEP files are in each model's
`reference/surface.step` (the Desk's reference upload; SolidWorks, one closed solid each).

- **What was wrong.** The L-shape reader built the short arm as a second sofa arm with its back
  strip along the outer side: the chaise top fell sideways, its outer front corner stood at the
  back height (83.8 / 83.8 / 81.3 cm) and the outer side was a full-height wall. The drawings write
  the front height at the chaise's outer front corner too and a small size at the foot of the
  outer side (7 in / 7 in / 3 in), which the reader dropped as a "band/hem detail".
- **What the STEP shows** (imported in staging with `cover import`, `out/rejections4/step/step-lN`):
  the chaise top is level and low along its front and inner side and rises to the back height only
  at the outer back corner, a twisted (bilinear, ruled) surface between the mitre and the outer
  edge; the outer side is a chamfer (8 / 10 / 7 in wide in plan) down to a vertical band; the
  back strip and the seat as before. The faces shape below built with the STEP's own sizes lies
  within 1.1 mm (mean, 1.8 mm p95) of the STEP's vertices.
- **The STEP's sizes are not the drawing's.** Measured by me and, independently, by Codex: rounded to
  1 cm and up to 3 cm off (L3 2240 deep for 221 cm, its band 10 cm for 7.6, L2's front 43 cm for
  40.6, every back strip 30 cm for 27.9). Same products (names, plan, hand), not swapped or mirrored.
  The drawing wins: the covers are the STEP's shape at the drawing's written sizes.
- **How.** A `faces` shape per cover (`testdata/drawing_shapes/drawing-l1..l3.json`, ADR-102),
  built by `scripts/given_build.py`: back strip, seat, chaise top (ruled), chamfer, the chamfer's
  back end, band, back, end, front, chaise inner and chaise front walls, as the drawing draws them.
  The band of L3 (7.6 cm) is joined to the chamfer by the usual join rule (`drawn.merge_fold_deg`).
  Vents as before (6, the drawing's count); the outer side's vent on L1/L2 sits on the 17.8 cm band
  as a lower opening (`features.vent_min_height_mm`, owner 1 Oct); page 2 of the drawing draws it on
  the chamfer just above: asked.
- **Checks.** `cover audit` ok, `scripts/fewer_check.py` PASS (seam pairs 2.4 / 3.3 / 3.1 mm as ease,
  stretch at most 0.38 %); every written size within 1.1 mm (out/rejections4/step/sizes.txt);
  compare pictures in out/rejections4/step/compare/. Test
  `test_a_chaise_longue_is_low_at_its_front_and_chamfered_to_a_band_outside`; a lesson in
  config/ai_lessons.json (a corner the drawing writes at the front height is never built at the
  back height; a workshop 3D file of the same product gives the shape, the drawing the sizes).
- **Links (ADR-132).** No catalogue model holds the STEP files (they are reference uploads), and a
  `manual` link is a person's decision in links.py, so nothing was written to app.db; the pairs are
  proposed in the report. **Not done:** `drawing-cover-39-46-l1-l5-mirror` (the same product as L1,
  waiting at the Desk) still has the chaise falling to 17.8 cm at its end; it should be rebuilt from
  drawing-l1.json mirrored.

## ADR-143 — Rens's fourth round on shape and pieces (15 Oct 2026): S43/S44's nose without a fold, their front skirt in one piece; the Nardo was the cached 3D

Rens at the Desk, 15 Oct 2026 (staging `out/rejections4/shapes/`; each remark read with
`scripts/desk_marks.py` and by looking, a second reading by Codex before building, `cover audit`
and `scripts/fewer_check.py`, compare sheets and a size table in `compare/`, Codex again on those).

- **S43, S44** ("rare knik in paneel top 1 wijzigen. Ook de front skirts terugbrengen naar 1
  paneel", one picture: a cross over the nose top by the slope seam, a cross over the front
  skirts). The kink was a construction error in `scripts/s43_shape.py` (ADR-140): the nose top is
  the hull of the line A-B and the rim (a fan from B, the triangle A-B-P, a fan from A), with P
  where the rim runs parallel to A-B; the side test took P on the strip's side, so B fanned over
  the whole rim and a sliver B-D-A stood 62 degrees against it, the line Rens saw. P is now at 29.0
  degrees on the nose (Codex found the same): no fold, facets meet at 3.5 degrees at most. The
  front wall (straight 41.24 + concave 27.24 + the nose's front to D 70.11 cm) is one piece again,
  over the drawing's vertical lines, as he asks: 138.6 x 40.64 cm net, 141.6 x 47.1 cm cut, on the
  roll. 10 → 8 pieces; every written size unchanged; the 4 vents where they were
  (`skirt-front@0.747`, S44 `@0.253`: the middle of the former nose-front piece, not on the
  concave curve). Live, back to Rens. Question #112 answered with every skirt measured: back
  240.84 + front 138.59 + nose 133.44 + end 141.86 = 654.72 cm per cover (the drawings write
  642.3 and 668.0 for one shape).
- **Cover 44 & 45 (Nardo S13 & S14)** ("volgt nog steeds totaal niet de vorm ... seams en paneel
  verdeling", 10:23): Rens approved it at 10:46. The server's log shows why: at 10:18-10:23 his
  browser drew the card without asking for panels.glb (last fetched 14 Oct 13:39, before the
  16:19 rebuild; the no-cache fix of ADR-138 went live at 11:06), so he judged the old wedge; at
  10:42 it fetched the new panels and he approved. Codex read the drawing independently: 10
  panels and 19 seams, "no difference within 1 cm" with the live faces. Not rebuilt; #102 (vents
  front and arm end, answer a) kept and marked done. Its drape.glb/drape.png are still the
  5 Oct wedge (the Drape view, not the default): to drape again.
- **Rule and check (ADR-055):** the audit's new `kinks` check fails a drawing cover (hull.top
  given) whose top piece folds inside itself sharper than `seams.piece_kink_max_deg` (25) along
  at least `seams.piece_kink_min_mm` (120) together; triangles under the fit tolerance squared
  and walls folded round a corner are left out. Swept read-only over the 118 live given covers:
  S43/S44 before this fix, and **C27** (top-4, 37 degrees over 28 cm) and **C30** (top-6, 66
  degrees over 32 cm), isofit covers with traced, twisted top pieces (ADR-133); not changed here,
  for the next round. Tests: test_drawing_given.py (S43: one front wall, no fold in the nose; the
  audit's kink check); a lesson in config/ai_lessons.json.

## ADR-142 — Rens's fourth round on vents and seams (15 Oct 2026): walls joined to the top point for point, a vent by hand one panel up

Rens at the Desk and in Questions, 15 Oct 2026 (staging `out/rejections4/vents/`; each picture read
with `scripts/desk_marks.py` and by eye, read independently by Codex before building, `cover audit` and
`scripts/fewer_check.py`, compare pictures and a size table in `compare/`, a Codex pass on those
before live).

- **C28** ("op de plekken van de kruisen lopen de seams van de skirt nog niet door in de seams van de
  panelen op de top"), after ADR-138's fix: at his three crosses the wall seam's top and the two top
  seams' end were already one point (0.0 cm, his picture shows the current cover). What was wrong
  along that rim: the walls were **not joined** to the top. `plan_profile` sampled the outline for
  the walls on its own (`_ring_with`, every 6 cm from the outline's start) while each top piece's
  outline was sampled from its own start; their points fell between each other, `conform` joins
  only points on a straight edge, so the cut left the rim free in stretches (ADR-140's open seams on
  C26/C28: 11 and 16 piece pairs) and the walls' top edges were cut as hems (5 cm allowance) instead
  of seams (1.5 cm). **Fix (general):** the walls stand on exactly the points the top pieces have on
  the outline (`_ring_of`), so a wall's top edge is a top piece's edge point for point. C28 and C26
  rebuilt (`fewer_build --codes`): open seams pass, wall cut heights 2-3.5 cm smaller, the cover the
  same (444 x 366.6 x 86.4 / 439.3 x 241.1 x 86.4, front 38.1). Test `test_plan_profile.py`
  `test_the_walls_meet_the_top_point_for_point` (fails on the old ring). If Rens means something
  else by "doorlopen" (the top seam square to the front edge), the card asks him to draw it.
- **C28, Q103** ("een 10e erbij, ik teken waar"): his cross on the long arm's inner wall near the tip
  (skirt-left-1), circles in the middle of the central inner wall (skirt-front-1) and on the long
  arm's inner wall between its upper vent and the tip (skirt-left-4): 10 vents, as the drawing.
- **C26, Q104** (b: "vents verplaatsen zoals op mijn tekening van 9 okt, daarna opnieuw
  goedkeuren"): the vents on the short inner walls beside the middle removed, one on each arm end at
  his circles (front of the nose, 31 cm from the inner wall's seam); 8. Its approval of 14 Oct ends
  with the new cut (reopened for a new one).
- **D1, D2** ("vents aan de zijkanten een paneel omhoog, op de schuin aflopende panelen"): the 18 cm
  side wall had its vent shrunk to 25 x 11 cm by the rule (owner, 1 Oct: a low side gets a lower
  opening). `features.vent_positions` may now name a piece without a bottom hem whose seam is the
  top of a piece standing on the hem (`finish._above_by_hand`; never a free edge, never a slanting
  side seam): the vent goes over that seam like a low skirt's (ADR-101). D1/D2: full 25 x 22 cm in
  the middle of top-4/top-3, 5 cm over the seam (bottom at 22.5 cm). The rule itself is unchanged
  (only by hand). The audit's and fewer_check's "high up a wall" now measure a vent over a seam from
  that seam (`vents3d.seam_under`). Test `test_finish.py`
  `test_a_vent_by_hand_one_panel_up_over_the_low_wall`.
- The audit's picture snaps its outline (`VIEW_GRID_MM`) when GEOS trips on near-coincident slivers
  (C28 after the fix).
- **Not swept:** C27 and S32 (plan-profile) keep their unjoined rims until built again; the isofit
  covers of ADR-140's sweep (C1, C2, C3, C9, C24) have another cause, not looked at here. Whether a
  low side wall should hand its vent up by the rule instead of shrinking it is the owner's (1 Oct
  rule), not changed.

## ADR-144 — Rens's fifth round on the L family (15 Oct 2026): the outer vent onto the chamfer, a vent's height by hand, the mirror pairs from L1–L3

Rens at the Desk, 15 Oct 2026, 13:44–14:09 (staging `out/rejections5/lfamily/`). Each picture was mapped
with `scripts/desk_marks.py` and checked by eye, and Codex read it independently before the build.
Checks: `cover audit` and `scripts/fewer_check.py`, compare pictures and size tables in `compare/`, and
Codex again on those before live.

- **L1, L2, L3** ("vent verplaatsen naar aangegeven positie", one picture each: an arrow from the
  outer-side vent straight up onto the chamfer; the pictures show the current vents). That is answer b
  of question #114 and what page 2 of the drawings draws. L1/L2: the vent leaves the 17.8 cm band
  (a 25 x 11 cm lower opening by the 1 Oct rule) for the chamfer `top-2`, full 25 x 22 cm, in the
  middle of its bottom seam, 5 cm over the band (22.3 / 22.1 cm above the floor; ADR-142's vent one
  panel up). L3: the 7.6 cm band and the chamfer are one piece (a 7.6 cm band alone would be a sliver
  under `seams.min_piece_width_mm`), so its vent crossed the fold. `features.vent_positions` now takes
  a height, "piece@fraction@cm": the vent's bottom sits that far above the piece's bottom edge, and a
  height given by hand wins over `vent_align`. L3: "top-2@0.5@12.6" (7.6 + 5 cm), 12.3 cm above the floor. Other
  vents and every piece unchanged. #114 done. Test `test_finish.py`
  `test_a_vent_by_hand_at_a_height_off_the_fold`; a lesson in config/ai_lessons.json.
- **The pairs 39 & 46 (L1 & L5), 40 & 47 (L2 & L6), 41 & 48 (L3 & L7)** ("match shape to L1", "L6,
  straks matchen met L2", "L7, ... met L3"). Each pair drawing is its L drawing page for page (the same
  written sizes, hand and 6 airpockets) plus "Cover N & M are mirror of each other". No size differs.
  Rens names the cards L6 and L7, so each pair card is built as its L shape mirrored (`"mirror": true`,
  `testdata/drawing_shapes/drawing-cover-*-mirror.json`; one pattern, cut once each way) with the L's
  corrected vents mirrored. Every piece is the same size as the L's (0.0 mm difference) and every vent is its mirror.
- **Open:** the audit's `kinks` check (ADR-143) fails L3 and the L3/L7 pair: `top-2` folds 32 degrees
  over 48 cm where the joined 7.6 cm band meets the chamfer at the front (14 degrees at the back). It
  was already in the live L3 (built before that check) and is kept for now (Rens: L3 "bijna goed");
  asked in Questions (#115) whether to keep one piece or sew a separate 7.6 cm band. A release older than
  this branch does not read "@cm": L3 and the L3/L7 pair must not be exported again on it.

## ADR-145 — The MCP server for AI agents (phase 2 of ADR-139): /mcp over the same API, preview only

The owner approved the four-layer agent strategy (ADR-139); phase 2 is the MCP server, so Claude,
ChatGPT and other agents can use the shop as tools. Built on the preview only, behind the same
two switches as `/api/v2` (the shop setting `agent_api_enabled`, the Worker's `AGENT_API`); the
preview is recognised the same way (`x-site-host` + the Worker's key), live stays off.

- **Protocol and SDK.** The official MCP Python SDK (`mcp` 2.3.0, MIT, added to coverapi): its
  lowlevel `Server` with explicit tool schemas and `StreamableHTTPSessionManager` in stateless
  mode with JSON answers (no SSE streams, no sessions, no GET stream: GET/DELETE answer 405).
  It speaks the current spec, **2026-07-28** (stateless: no initialize, per-request `_meta`,
  `server/discover`, `resultType`, `ttlMs`/`cacheScope` on tools/list), and the handshake
  versions 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25 for today's clients. The SDK
  needs a running task group; a fresh manager per request (`async with manager.run()`) gives
  that without an app lifespan (TestClient and uvicorn alike) and keeps nothing between
  requests. Writing the JSON-RPC by hand was the alternative; the 2026 protocol's envelope and
  header rules made the SDK the safer choice.
- **Where.** `/mcp` on the studio (`coverapi/agent_mcp.py`, a Starlette route before the static
  files), passed by the Worker like `/api/v2` (`apps/site/src/agent.ts`: `/mcp` and `/mcp/…`
  are a 404 at the edge on live; the caller's `Authorization` passes, cookies never). With the
  website link closed the studio answers `/mcp` only through the website (`website_gate`).
  Body limit: the default 2 MiB (Caddy's `@small` and `BodyLimit`; the SDK's own cap set to the
  same).
- **Tools** (always these six, in this order, the same for every caller as the 2026 spec asks):
  `list_kinds` (optionally one kind or alias), `find_cover`, `get_quote`, `get_cover`,
  `create_order_link`, `suggest_from_photo`. Their input schemas are the v2 request models'
  own JSON schemas made plain (`MatchIn`, `QuoteIn`, `LinkIn`; `additionalProperties: false`);
  the descriptions are written for models: sizes of the furniture in cm (or `unit: mm`), the
  sizes per kind from config/agent_kinds.json, "never guess sizes", "a person orders and pays",
  "partner key only". Annotations: the readers read-only; `create_order_link` additive, not
  destructive. The server's `instructions` give the flow and the rules.
- **Thin wrappers, one code path.** Each tool call is exactly one `/api/v2` request made
  in-process (httpx's ASGI transport into the v2 sub-app) with the caller's own headers and
  address: the gate, the per-address and daily limits, the partner key (`Authorization:
  Bearer cvk_…` or `X-Api-Key`), the B2B company's prices ex VAT, the refusal of unknown
  (personal) fields, the key-only photo recognition and its budgets all hold unchanged. A v2
  error becomes a tool error (`isError`, text "code: message Hint: …", `structuredContent`
  with error, message, hint, field, status and `retry_after_s`); an unknown tool is JSON-RPC
  -32602. Success: the v2 JSON as `structuredContent` and as text, the rate-limit headers in
  `_meta.ratelimit`. `suggest_from_photo` takes a product page and/or up to 3 base64 photos
  (within the 2 MiB body); larger photos go to `POST /api/v2/suggest`.
- **Limits.** A tool call counts once, on the v2 limits. The protocol's own messages
  (initialize, tools/list, server/discover) are free like the API's docs but count on an
  in-memory window per address, `limits.agent_mcp_per_hour` (600, server-only); over it an
  HTTP 429 with `Retry-After` before the SDK runs.
- **Keys and connectors.** Partner keys are a header, not OAuth: anonymous use needs no login,
  and connectors that cannot send headers (claude.ai, ChatGPT) are simply anonymous. OAuth for
  partner keys in connectors is for later.
- **Origin.** The spec's DNS-rebinding rule holds: a request without `Origin` (every MCP client,
  which runs server side) passes; with one, only our own configured sites (the website the
  Worker answered for, its `x-site-host` trusted with its key, or the studio's public address,
  `public_url`) are accepted and echoed in `Access-Control-Allow-Origin`; any other origin is a
  403 before anything runs. Never the request's own Host: in DNS rebinding that is the
  attacker's.
- **Codex.** Codex wrote the protocol tests (reviewed: its fixtures were a copy of
  test_agent_api's, now imported from there). Adversarial review, round 1: (a) Origin was not
  validated at all (my first version accepted every origin like `/api/v2`'s open CORS) — fixed
  as above; (b) the protocol window never forgot idle addresses (the clean-up only removed
  empty windows, and scanned every caller on each request past 20,000) — now idle addresses
  are swept at most once a minute and the window holds at most `MAX_CALLERS`, the least recent
  going first. Round 2: the Origin check trusted the request's Host, which a rebinding attacker
  controls — now configured addresses only (test with a matching attacker Host and Origin).
  Round 3: approved, no material findings. After it: the gate runs before the Origin check, so
  on live `/mcp` is a 404 whatever is sent (a foreign Origin no longer reveals it with a 403).
- **Discovery.** `/llms.txt`, `/llms-full.txt` and `/api/v2/docs` name the endpoint and the
  tools. No `/.well-known` entry: the 2026-07-28 spec defines none for servers (only OAuth
  metadata), and the server card (SEP-2127) is an extension whose path is not settled yet.
- **Tests.** `apps/api/tests/test_agent_mcp.py` (raw JSON-RPC, written by Codex and reviewed:
  both eras, every tool, errors with hints, the shared hourly window, the protocol window,
  partner and revoked keys, two B2B companies and anonymous, no personal data, preview-only,
  GET and CORS); `test_agent_mcp_client.py` (the official `mcp.Client` in both eras);
  `apps/site/test/worker.test.ts` (`/mcp` on the preview, 404 on live); llms.txt/docs mention.
  A real check on a scrubbed scratch copy (no mail, domain, Mollie or link key; two-factor
  off): the SDK client and the MCP Inspector CLI found, for a 230 × 90 × 85 cm sofa, drawing-s12
  (95.3 %, €599), suns-sofa-bench-tagia (90.6 %), made to measure (€1,043.95) and the Rios
  bended 2-seater as "possible".

## ADR-146 — The vents' logo along the hood's lower edge, upright, and shown in 3D (16 Oct 2026)

The owner (16 Oct 2026, T1): "for T1 the logo on the airvent is in the wrong position, can we
make an option so we can see the logo as well on the 3d model so we can check before we
accept", and then what was wrong: "het logo zit nu aan de korte kant van de airvent maar moet
aan de lange kant aan de onderkant van de airvent met het logo omhoog, graag implementeren".

- **What was wrong** (T1's cut.dxf read twice, once by Codex independently): the LOGO frame
  (12 x 4 cm) sat on the hood piece P7 (28 x 31.5 cm) at y 24–28 cm, 3.5 cm under its top
  edge: the short side sewn to the cover. It was centred across the hood and not mirrored,
  but the hood carried no mark of which edge is sewn on (no UP arrow, no stitch line), and the
  word LOGO started at the frame's middle (PEN text is placed by its baseline's start). The
  same hood is on all 444 covers with logo vents; the code dated from 1 Oct 2026.
- **The rule now** (`finish.logo_frame`, `features.vent_logo_above_edge_mm: 35`, to confirm
  against the insert's channel): the frame centred along the hood's open lower edge, the 28 cm
  edge that spans the vent's 25 cm long bottom side, upright, its bottom 3.5 cm above that edge
  (Codex's proposal: the inset it had from the other edge). The hood also gets its stitch lines
  (top and sides, open at the bottom), "TOP: SEW TO COVER", an UP arrow towards it and "OPEN
  EDGE, INSERT"; "P7 VENT-HOOD" moves to the middle, out of the logo's way; every hood text is
  centred on its place (`finish.centred`). Panels and CUT lines do not change.
- **One frame for the DXF and the 3D.** `cover export` writes the hood's frame as `logo_mm`
  and, per vent opening of a panel, where it lies on the cover once the hood is sewn on as
  `logos_mm` (`finish.logo_on_cover`; finished.json format 2). On the cover the hood hangs
  from its stitch line (the PEN ring a seam allowance above the opening), centred on the
  opening; its sides are sewn down the ring, so its length shares out over the ring's height
  and the logo lands in the opening's lower part. `vents.json` format 3 carries each vent's
  `logo` (corners, centre, how far under the stitch line) and `hood` (the stitch line, down,
  its reach) to 3D through the same flat triangles as the opening; a cover exported before has
  `logo: "missing"` and the viewer says "Logo position not computed yet: run again". The 3D
  never computes the logo itself, so it cannot disagree with the cutting file. After Codex's
  adversarial review: the logos are taken only when finished.json is the export of this
  pattern.json with these settings (`pattern_parameter_hash`, `parameter_hash`), else
  "missing"; vents.json is made again when finished.json, pattern.json, panels.* or cover.json
  is newer; the hood's reach and the logo's distances are measured on the 3D surface (the flat
  pattern may be compensated); the audit fails malformed logo data instead of crashing.
- **The viewer.** Show ▾ → **Logo** (on by default when Vents is on, remembered per browser):
  the hood drawn see-through from its stitch line, the frame in blue on it with the word LOGO,
  readable from outside. The cover page's 3D tab and the Desk card share the one viewer.
- **Audit.** The check "vent logo" fails a frame in the hood's upper half (the old place), one
  standing on its short side, one off the middle, and an export without `logo_mm`.
- **Not rebuilt live.** A re-export changes cut.dxf of every cover with vents (the hood's PEN
  marks), so each returns to the Desk: all 454 covers with vent hoods (444 with the logo, 10
  without, which get the new marks). Which ones, and when, is the owner's decision. T1 is
  rebuilt in staging (checked twice: the DXF entity by entity, only the six hoods' PEN marks
  changed, and the re-measure; Codex's pass on the comparison); putting it live waits for a
  person (the write to the live model was refused by the session's safety check).
- **Not chosen:** a separate logos.json (finished.json already carries the pieces the DXF is
  drawn from); a sewing simulation of the hood's bulge (the 3D shows where, not how it folds).

## ADR-147 — The cutting file in the browser: cut.dxf drawn on the server, viewing is not downloading (16 Oct 2026)

The owner (16 Oct 2026): "we can now only download the DXF after approval, but Rens, Wout and I
would like to see the DXF in the browser during the approval process".

- **Where:** the Desk card's **Pieces** tab (full width, above the pieces and revisions) and
  the cover page's **Pieces → Cutting file** (`#/model/<id>/pieces/cutfile`; a *Cutting file*
  button beside the DXF on Cut pieces). One component, `apps/web/src/CutView.tsx`.
- **Drawn from the DXF itself.** `coverengine/export/cutview.py` reads cut.dxf's bytes with
  ezdxf (every modelspace entity, blocks exploded, arcs and bulges flattened within
  `desk.preview_flatten_mm`, `$INSUNITS` scaled to mm) and writes its own SVG: the layers CUT,
  PEN and other as separate groups, the pen texts as text (left-aligned TEXT fitted to the
  stroke font's width, so it lands where the export placed it). An entity it cannot draw is
  counted and named under the drawing, never silently left out. It never reads cut.svg or
  finished.json, so the picture cannot differ from the file. Our own renderer rather than
  ezdxf's drawing add-on: we need the layers as switchable groups, the pieces as clickable
  shapes and stable output for the cache; the add-on draws text as glyph paths and gives
  neither.
- **Pieces from the file:** closed CUT rings nested by containment (a ring inside a piece is
  its opening, a vent); PEN lines and texts belong to the piece around them; the name is the
  largest "P<n> …" label inside it (a label at a thin piece's middle can fall just outside its
  outline: then the clearly nearest piece without a label takes it). Edges run from corner to
  corner (`desk.preview_corner_deg`), an edge under `desk.preview_min_edge_mm` (an allowance's
  cut-off corner) joined to its shorter neighbour so the list shows the sides a person
  measures; the lengths add up to the outline.
- **The viewer:** toggles Cut, Pen, Texts and Names (remembered per browser); zoom (buttons,
  wheel, a trackpad pinch, two fingers on an iPad: pointer events with `touch-action: none`),
  pan, fit, keys + − 0 Esc; a scale bar in cm; a click or tap on a piece shows its box, area,
  outline and each edge in cm, also on the drawing; a measuring tool (two clicks, corners snap).
  The colours are tokens (`--cv-*`, 3:1 on the stage, in test_web_tokens.py).
- **Revisions:** *Compare with* (or *compare* in the Revisions list) puts an older revision's
  drawing beside the current one (stacked on an iPad). `compare()` matches pieces by name and
  copy and marks each: added, removed, size (box moved more than `desk.preview_changed_mm`),
  outline (same box, outline or openings moved), pen (every cut line the same, the pen marks or
  texts changed), same; the export's revision stamp is not a change. On T1 r7 → now it says
  "Pen marks only: every cut line the same", the six hoods with "+ OPEN EDGE, INSERT, TOP: SEW
  TO COVER" (ADR-146's logo). A row zooms both drawings to the piece.
- **Viewing is not downloading.** `GET /api/models/<id>/cutview` (the meta: sheet, names, boxes,
  corners and edge lengths, never an outline), `/cutview.svg` (the drawing) and
  `/cutview/diff?a=&b=`. The DXF's bytes are never sent; its download gate is unchanged. Until
  the Desk approved this very fingerprint (the bytes read once: the fingerprint, the drawing
  and the watermark agree; a revision: its fingerprint in `approved_fingerprints`), the
  drawing carries **PREVIEW – NOT FOR CUTTING**: a red band above the sheet with the cover,
  revision and fingerprint, the words across the sheet, the SVG's title, and the header
  `X-Cutview-Watermark: 1`. The SVG is served inline with a sandboxing CSP.
- **Rights:** admins, the Desk's approvers (`desk.approver`) and editors; the workshop login
  only where `desk.dxf_allowed` (an approved cover, so the DXF is downloadable anyway; the
  route added to `security.WORKSHOP_READ`, the check in the route); viewers never (403 before a
  byte is read).
- **Cache:** `<data>/cutview-cache/<fingerprint>-v<renderer>-<settings>.svg|json` (never in a
  model folder), written atomically, at most two drawings made at a time, the oldest beyond
  `desk.preview_cache_keep` removed; a DXF over `desk.preview_max_mb` is refused (413).
  Measured on the server: the 1.5 MB cut.dxf of suns-lounge-blocchi (23 pieces, 699 PEN lines)
  drawn in 0.5 s, 296 kB of SVG; T1 in 0.07 s; in the browser the big cover is on screen in
  about 1.3 s.
- **Codex** wrote the API tests (30, reviewed: rights matrix, the gate, no DXF bytes, the
  watermark before and after an approval and after a changed cut, revisions and their
  approval, the diff, 404s, the cache, 413, the workshop with the gate off, the allow-list).
  Its adversarial review (focus: leaks before approval, rights, the watermark, big covers),
  verdict *needs-attention*, one finding: "Unapproved SVG exposes the complete cutting
  geometry … deleting that group yields the unobscured geometry, which can be imported or
  converted for cutting." Held in part, fixed: the words across the sheet now lie inside the
  CUT layer itself (a drawing converted for a cutter as it is would cut them), and an
  unapproved SVG has no millimetre size (opened elsewhere it is not at the table's scale);
  the workshop login no longer gets cut.svg (`files/cut.svg`, `pattern.svg`) before approval —
  that was open before this change. Not taken: rasterising the preview. The owner asked for an
  SVG that a screenshot or a saved copy cannot be confused with; the people who see it
  (editors, approvers, admins) could already open cut.svg, pattern.json and finished.json with
  the same outlines, and a raster would lose the sharp zoom the check needs. The gate is
  against cutting an unapproved file by mistake, not against a deliberate copy by an editor.
- **Tests:** `engine/tests/test_cutview.py` (a test model exported as `cover export` does:
  every piece, name and size, the openings, a rectangle's edges, the layers' counts against
  the DXF, the texts, determinism, the watermark in the cut layer and the band, a circle added
  to the DXF by hand drawn as a piece, another layer, centimetre units, stroked texts, the
  comparison: the logo moved is pen-only, a wider allowance a size change, a piece removed or
  added; 60 wavy pieces in under 6 s); `apps/api/tests/test_cutview_api.py`. Browser:
  `apps/web/e2e/dxf_view.py` on a scrubbed scratch copy (Chromium, 1440 with a mouse and 820 as
  an iPad touch screen, light and dark; cover page and Desk card; watermark exactly on the
  unapproved cover; each layer off and on; zoom, fit, wheel, drag, two-finger pinch; a piece's
  size; measuring; T1 r7 beside the current; the workshop refused before and shown after
  approval; a viewer refused): all good.
- **Better later:** a server-rendered PNG at a bounded resolution for people outside the
  studio, should the cutting file ever be shown to them; snapping the measuring tool to any
  point of an outline, not only corners.

## ADR-148 — Rens's vent round of 20 Oct 2026: the Nardo pair four per cover, three covers asked first

Rens in Questions (#116) and at the Desk, 20 Oct 2026 (staging `out/vents-2026-10-20/`; each picture
mapped with `scripts/desk_marks.py` and read by eye, Codex read every remark, picture, drawing and the
current cover independently before anything was built; after the build `cover audit`, a compare
picture and a size table, and Codex again on those before live).

- **Nardo S13 & S14** (`drawing-cover-44-45-s13-s14-nardo`, #116 b: "Elke hoes moet 4 vents hebben
  (2 extra per hoes): ik geef aan waar", his circles in the middle of the back and of the low end):
  the drawing's "4 Air pocket" for the pair (1+1) had been read as 2 per cover. Now 4 per cover, one
  in the middle of every wall (`features.vent_positions` by hand: skirt-front, skirt-right = the arm
  end, skirt-back, skirt-left = the 27 cm low end, where the rule gives a 25 x 20 cm opening); 8 for
  the pair. Every piece the same size; the export also placed the vent logo (ADR-146, it predated
  it). `vents_total` 4 in `testdata/drawing_shapes/drawing-cover-44-45-s13-s14-nardo.json`, so a
  rebuild keeps it (ADR-116). Codex read the same and passed the result. Live, the Desk card reopened.
  Swept: the other pair covers (24/24b, 25/25b, the L pairs) already have a vent on every wall (the
  L pairs' outer one on the chamfer, ADR-144); nothing else to change.
- **S22** ("zowel voor als achter airvents toevoegen", two circles on the long front wall), **S48**
  ("meer airvents toevoegen zowel voor als achter", two circles) and **S45** ("airvents rondom
  evenwichtiger plaatsen", no picture): **not live**. S22: Claude and Codex both read 8 (3 per long
  wall, 1 per end) but Codex found the extra vents' places uncertain (his circles at about 1/4 and
  4/5, evenly spread is 1/6 and 5/6): question #117. S48: Claude reads 8 (the middle one kept, two
  added front and back), Codex 10 (one per full metre, 4 per 415 cm wall): question #118. S45: both
  read 4 evenly round, 90 cm apart, but where the first goes is open: on the four rounded corners
  (the proposal; only the front-left vent moves back from where the corner rule of ADR-134 pushed it,
  which bunched two at the front) or as the drawing at front, back, left and right (the band's seams
  are at left and right): question #119. Each question carries the staged proposal's compare
  picture; each card a note by Claude.
- **Not changed:** the rules. For S45 the corner rule (ADR-134) and the even spread pull apart on a
  free outline that is round all along but has short straighter stretches; whether a free-form
  pouf's vents ignore the corner rule is Rens's answer to #119, then a rule if he says so.

## ADR-149 — S25: the walls 40 cm high all round as drawn, one skirt piece per wall (Rens, 20 Oct 2026)

Rens at the Desk (20 Oct 2026, S25, a curved sofa): "Panelen op tekening komen niet overeen met
het model", with a red line across the end wall at the front wall's height. The drawing draws a
seam at 40.01 cm all round: the front, both ends and the back are 40 cm walls; above the back
wall an upright band to 62.99 cm whose ends lean in; the ends are hipped from 40 cm up. The live
cover had end walls sloping from 40 cm at the front to 63 cm at the back and the back in one
piece to 63 cm (ADR-116's note had already named the difference). Codex read the same from the
drawing independently, before the rebuild.

- **The shape** (`testdata/drawing_shapes/drawing-s25.json`, a person's reading): a profile
  point at the back at 40.01 cm below the 62.99 one, the 62.99 line 202.6 cm long (not written:
  measured from the drawing's top and side views, where the 40 cm line runs the full 237.91;
  the written 164.22 checks within 0.2 cm the same way), `skirt_cm: 40.01`.
- **`skirt_per_wall`** (new, a drawing shape's params): the level skirt below `skirt_cm` is one
  piece per wall, a seam at every corner as the drawing draws it. Without it whole walls are
  packed into runs up to `seams.max_skirt_panel_mm` (S43's band), which on S25 wrapped the
  front wall round the corner into an end wall.
- **A fix in the same place:** a wall face's upper triangle (no floor edge) went to the skirt
  run whose face shares most corners; at a corner the next wall's face shares as many, so the
  back wall's first triangle went to the end wall and the corner seam ran slanted 5 cm. On a
  tie it now stays with its own wall. No other shape uses `skirt_cm` today (S25 only), so no
  live cover changes by it.
- **Result:** 11 pieces instead of 10 (the back in two, 40 cm and 23 cm), the end walls
  40 cm rectangles, the hips and the back chamfer band changed accordingly, the rest the same;
  5 vents, same positions. Tests: `test_drawing_given.py` (one skirt piece per wall, straight
  corner seams; S25's walls 40 cm and the back split).
- **Learned (ADR-055):** when a drawing draws a line round the walls at one height, that line
  is a seam and the walls stop there; a hip starts above it. Swept with hipped ends: check
  whether the end walls are as high as the lowest wall (then `skirt_cm`) before letting them
  follow the profile. No other swept shape with hipped ends has walls of different heights
  (S25 was the only one).
- **Better later:** the end hip's fold follows the fan from the back corner; the drawing folds
  it along the line from the 62.99 back corner to the crease. One piece either way, flat within
  0.0 % stretch; a fan from a chosen tip when a drawing needs the fold drawn.

## ADR-150 — The dealer embed: our configurator on a B2B dealer's own website, in its look, at its prices (preview only)

The owner (Rick, 20 Oct 2026): B2B dealers put the configurator on their own sites, fully
customised by the dealer. His decisions: a key per dealer linked to its company with
allow-listed domains; checkout chosen per site (our checkout in the dealer's look, or the order
sent to the dealer, who sells and invoices); the dealer's own prices (our B2B price ex VAT plus
its margin, or a price list), our B2B price never in the page; colours, fonts, logo, texts and
language, kinds and fabrics, layout, 3D and the end action all the dealer's. Preview only until
his go. Plan: docs/plans/dealer-embed.md; handbook: docs/handbook/dealer-embed.md.

- **A Web Component, an iframe as the fallback.** `<s2dio-configurator dealer="dpk_…">` from one
  module script (`/embed/v1/configurator.js`, vanilla TS in `apps/web/src/embed/`, its own Vite
  build `vite.embed.config.ts`; 18 kB, three.js only as a chunk where 3D is on). Shadow DOM;
  themed by the saved theme, then attributes (a subset only), then the dealer's CSS
  (`--s2dio-*` custom properties, `::part()`). The frame (`/embed/v1/frame`) hosts the same
  component for site builders without scripts. Chosen over iframe-only: it inherits the page's
  font, grows with its content, and hooks a cart with ordinary DOM events; one code path for both.
- **Keys and origins.** `dealer_sites` (app.db): company, public key `dpk_…` (in the page; opens
  only public things), secret key `dsk_…` (SHA-256; `GET /api/embed/v1/verify/<quote>` for the
  dealer's server, with its purchase price), origins, settings. The public key is in every API
  path, so CORS (and the preflight) is decided per dealer: `Access-Control-Allow-Origin` only
  for a listed origin or our own website (frame, demo); any other Origin is a 403; a POST needs
  an Origin; errors carry CORS for an allowed page. The frame's CSP lists exactly the site's
  origins in `frame-ancestors` and has no X-Frame-Options (studio and Worker); everything else
  stays unframeable.
- **Prices on the server only** (`dealer_embed.dealer_price`): `b2b.unit_price` for the company
  × (1 + margin %, per kind if set), or a channel of the published price set (never `b2b` or the
  company's own list: refused on save and on pricing), the B2C VAT, the dealer's rounding,
  incl. or ex VAT. The browser gets amount, currency, VAT included, VAT % and indicative, built
  from a whitelist; purchase, net, gross and margin stay in `embed_quotes/<qid>.json`. Our
  checkout refuses a price below the purchase price.
- **Checkout.** Ours: `POST …/checkout` makes a 2-hour token; `/embed/v1/checkout/<t>` is a
  server-rendered page in the dealer's look (its CSP: the logo's host, Turnstile, the form to
  Mollie), the order is a normal shop order (`orders`, flagged `dealer` with the purchase price
  and margin for settlement) paid through the shop's own `finish_order` (exposed as
  `app.state.shop_finish_order`; an order's `status_url` now sends Mollie back to our status
  page in the dealer's look, which links to the dealer's return address). Dealer's:
  `POST …/order` stores `dealer_orders`, mails the dealer (with its purchase price) and the
  customer (without); the dealer confirms or declines on `/embed/v1/confirm/<t>` (14 days),
  which makes a B2B order on account at the purchase price, waiting for Send to production as
  every order (ADR-128); with `dealer_confirms` off at once. Or the dealer's cart: an event only.
- **Events**: `s2dio:ready|priced|added-to-cart|checkout-started (cancelable)|order-sent|error`,
  bubbling out of the shadow root; the frame posts them to its parent's listed origin only.
- **Limits** (`limits.embed_*`, server-only), analytics per site and day (`dealer_usage`:
  load, quote, checkout, order, cart; paid orders from `orders`), no addresses, no cookies.
- **Studio**: Shop → Dealer embeds (admins): domains, look with a live preview of the real
  component (`preview` property: the draft look over the saved one), texts per language, range,
  prices with an example (the purchase price shown only here), ordering, snippets, secret key,
  30 days of counts, the orders sent to the dealer.
- **Preview only**: the shop setting `dealer_embed_enabled` (off), the preview website or a
  colleague; the Worker (`apps/site/src/embed.ts`) passes `/embed/*` and `/api/embed/*` only on
  the preview or with `DEALER_EMBED = "1"`. Demo dealers (`config/embed_demo.json`, two made-up
  sites) answer only on the preview or for a colleague and never order, mail or count;
  `preview.<domain>/embed-demo` shows them (`apps/web/public/embed-demo.*`).
- **Tests**: `apps/api/tests/test_dealer_embed.py` (gate, settings checks, CORS and preflight,
  price = B2B + margin and no leak in any answer, the 3D file or the hosted pages, price list
  and ex VAT, kinds/colours/languages, our checkout with a double click, dealer mode with
  confirm and decline, the cart event and counts, verify with the secret, the frame's CSP,
  inactive site and blocked company, order limits, the demo dealers), `apps/site/test/embed.test.ts`,
  `apps/web/e2e/dealer_embed.py` (a real browser: the studio page and its preview, the demo,
  a dealer's own origin through CORS, an unlisted origin).
- **Codex's adversarial review**, round 1 ("not safe to merge … as written"), all fixed with
  tests (`test_codex_round1`): (a) the dealer's confirm page showed the purchase price to anyone
  holding the link: now only in the dealer's mail, and a decided or expired link shows neither
  the customer nor a price; (b) a replayed `/order` made another order (and, with confirmation
  off, another B2B order): an `idempotency_key` is required, unique per site, a retry gets the
  first order; (c) dealer mode skipped the below-purchase check: now on submit and on confirm;
  (d) a price still on its way could land after the choices changed: the component drops it;
  (e) a confirm link still worked after the site was switched off: the site must be active and
  in dealer mode; (f) the script answered with only the Worker's switch: the studio's gate
  covers `/embed/v1/*.js` too (the Worker keeps the entry 5 minutes).
- **Better later**: existing covers (the match) in the embed; the dealer's own editor in the B2B
  shop; a signed webhook to the dealer's server; the margin settlement report; per-dealer limits.
