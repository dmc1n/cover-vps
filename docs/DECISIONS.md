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

## ADR-101 — The website's 3D loads lean, and the rain on the scroll page keeps falling

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
