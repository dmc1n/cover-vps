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
