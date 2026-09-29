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
