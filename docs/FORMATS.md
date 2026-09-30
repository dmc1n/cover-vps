# Formats

Source of truth for every JSON structure and export format. Update this file in the same commit
as the code that changes a format. JSON Schemas live in `engine/schemas/`; this file explains
them.

## Conventions

- Lengths in mm, angles in degrees, coordinates right-handed Z-up, ground at z = 0, front of the
  furniture toward −Y.
- Every file carries `format_version` (integer) and `engine_version` (string).
- Ids are stable strings, never array indices.

## Parameters (M0)

`config/defaults.yaml` is the registry of every parameter with its default and a comment. The
effective value for a run is resolved in this order, later wins: defaults → family preset
(`config/presets/<family>.yaml`, M7) → the model's `CoverDefinition` → one-off `--set` or UI
trial override. Keys use dotted paths (`hull.clearance_mm`). Every `PatternSet` embeds
`parameters` (the full effective set) and `parameter_hash`, so any pattern can be reproduced and
`cover diff` can attribute a dimension change to the parameter that caused it.

Rules (ADR-017), implemented in `engine/coverengine/params/registry.py`:

- Every scalar leaf is a parameter; an override of a key that does not exist is an error.
- Types follow the default. Integers on keys ending `_mm`, `_pct`, `_deg` accept decimals;
  other integers (counts) do not; booleans are `true`/`false`.
- A comment with `a | b | c` that contains the default makes the key a choice (dropdown).
- A comment with "to confirm" or "TODO" marks an unconfirmed assumption (`*` in `cover params`).
- The comment (including indented continuation lines) is the tooltip text in the web app.
- `parameter_hash` = SHA-256 of `json.dumps(values, sort_keys=True, separators=(",", ":"))`
  over the flat dotted-key mapping.

`cover params --json` prints `{"parameters": <tree>, "parameter_sources": {key: default |
preset | model | trial}, "parameter_hash": ...}`.

## Model (M1)

`cover import <file> --out models/<id>/` writes three files. The model id is the directory
name. Output is deterministic: the same file and parameters give byte-identical files.

`model.glb`: the kept parts, one glTF node per part named by its part path. The meshes store
the canonical coordinates (mm, Z up, lowest point z = 0, bounding box centred on x = y = 0,
front toward −Y) as 32-bit floats. They hang under a root node `cover_model_mm_zup` whose
transform converts to glTF's metres and Y up, so a generic glTF viewer shows the model upright
at true size. The engine reads the mm values directly (`coverengine.io.model_io.load_model`).
Parts may overlap: the canonical mesh is a triangle soup (ADR-022).

`model.json`:

```json
{
  "format_version": 1,
  "engine_version": "0.1.0",
  "id": "chair-a12",
  "source": { "file": "chair_assembly.step", "format": "step", "sha256": "15334f0d…",
              "units_detected": "mm", "units_used": "mm" },
  "placement": { "up_axis": "z", "front": "-y", "scale_to_mm": 1.0,
                 "rotation": [[1,0,0],[0,1,0],[0,0,1]],
                 "translation_mm": [0.0, -64.023278, 0.0], "ground_offset_mm": 0.0 },
  "parts": { "total": 19, "kept": 6, "dropped_small": 12, "excluded": 1,
             "min_part_mm": 8.0, "exclude": ["cushion*"] },
  "mesh": { "vertices": 48, "triangles": 72 },
  "bbox_mm": [[-250.0, -314.023285, 0.0], [250.0, 314.023285, 942.962891]],
  "size_mm": [500.0, 628.04657, 942.962891],
  "import_parameters": { "import.min_part_mm": 8, "...": "..." },
  "parameter_sources": { "import.min_part_mm": "default", "...": "..." },
  "warnings": []
}
```

- `format`: `step`, `iges`, `stl`, `obj`, `ply`, `glb` or `gltf`. `units_detected` is the unit
  the file declares (STEP, IGES; `m` for glTF by definition) or `null` (STL, OBJ, PLY).
  `units_used` is what the import applied (`--units`, else the declared unit, else
  `import.default_units`).
- `placement`: the file's coordinates, times `scale_to_mm`, rotated by `rotation`, then shifted
  by `translation_mm`, give the canonical coordinates. `ground_offset_mm` is the z shift.
- `parts.exclude`: name patterns in effect. The next import into the same directory reuses them
  (`--forget-exclusions` drops them). The bounding box and size cover the kept parts only.
- `warnings`: unit plausibility and unit overrides, in words for the operator.

`parts.json`: every body of the source file, kept or not, in canonical coordinates.

```json
{ "format_version": 1, "parts": [
  { "path": "chair/frame/seat", "status": "kept", "rule": null, "triangles": 12,
    "bbox_mm": [[-250.0, -314.023, 420.0], [250.0, 185.977, 460.0]],
    "size_mm": [500.0, 500.0, 40.0], "volume_mm3": 10000000.0 },
  { "path": "chair/hardware/screw M4", "status": "dropped_small", "rule": null, "triangles": 140,
    "bbox_mm": [[-242.0, -306.023, 414.0], [-238.0, -302.023, 420.0]],
    "size_mm": [4.0, 4.0, 6.0], "volume_mm3": 75.0 }
] }
```

- `path`: assembly names joined by `/`. A repeated name gets `#2`, `#3`, … (`chair/frame/leg#2`).
  A part made of several separate bodies gets `/1`, `/2`, … STL files are named after the file.
- `status`: `kept`, `dropped_small` (largest dimension below `import.min_part_mm`) or
  `excluded` (`rule` is the matching pattern).
- `volume_mm3`: only for closed bodies, else `null`.

## Hull (M2)

`cover hull models/<id>/` writes three files next to the model (or into `--out`).

`hull.glb`: the cover surface as one mesh named `hull`, same convention as `model.glb` (canonical
mm Z-up coordinates under the root node `cover_model_mm_zup`, whose transform converts to glTF's
metres and Y up). The surface is open at the bottom; the hem boundary lies exactly at
`hull.hem_height_mm`. Faces point outward, away from the furniture.

`preview.glb`: two meshes, `furniture` (grey, opaque) and `cover` (blue, see-through), for
looking at in any glTF viewer. Not read by the engine.

`hull.json`:

```json
{
  "format_version": 1, "engine_version": "0.1.0",
  "model_id": "blocchi-2seater-moon-right", "model_sha256": "e33986d6…",
  "resolution_used_mm": 5.0,
  "mesh": { "vertices": 40768, "triangles": 80955 },
  "area_m2": 6.494158,
  "bbox_mm": [[-1190.115, -716.182, 50.0], [1190.113, 715.99, 919.402]],
  "hem": { "height_mm": 50.0, "length_mm": 6302.4 },
  "distance_to_model_mm": { "min": 10.0, "mean_at_vertices": 15.511, "clearance": 10.0 },
  "clearance_repair": { "vertices_moved": 20226, "max_move_mm": 3.665 },
  "ridges": { "chains": 43, "length_mm": 806.1, "angle_deg": 40.0 },
  "top": "tensioned",
  "drainage": { "drains": false, "hollow_area_mm2": 0.0, "flat_area_mm2": 110000.0,
                "worst_location_mm": [114.0, 198.0] },
  "support": null,
  "masks": 0,
  "parameters": { "hull.clearance_mm": 10, "...": "..." },
  "parameter_sources": { "hull.clearance_mm": "default", "...": "..." },
  "parameter_hash": "…",
  "warnings": []
}
```

- `distance_to_model_mm.min`: exact minimum over vertices, face centres and edge midpoints.
- `clearance_repair`: how many vertices were pushed outward to keep the clearance, and the
  largest push.
- `ridges`: connected chains of edges sharper than `seams.ridge_angle_deg`, the seam
  candidates for M3.
- `top`: `tensioned` (straight between high points, sheds water) or `draped`.
- `drainage`: does water run off (CLAUDE.md rule 12)? Hollows deeper than 1 mm and flat
  patches (slope below `hull.min_slope_deg`, at least `hull.flat_patch_mm` across, not at the
  edge), with the centre of the largest problem area.
- `support`: `null`, or the balloon used: `{"kind": "balloon", "centre_mm": [x, y],
  "radius_mm": 150, "height_mm": 69.4, "automatic": true}`. Height is above the cover top it
  lifts.
- `cover.json` may carry `hull_masks`: `{"type": "box", "min": [x, y, z], "max": [x, y, z],
  "mode": "exclude" | "solid"}` in canonical model coordinates.

## CoverDefinition (M2–M5)

`models/<id>/cover.json`. `parameters` is a sparse tree with exactly the registry keys; it holds
only the values this model changes (ADR-018). Structural per-model data sits beside it.

```json
{
  "format_version": 1,
  "model_id": "lounge-chair-a12",
  "parameters": {
    "hull": { "clearance_mm": 12, "bridge_gap_mm": 60 },
    "construction": { "method": "welded" },
    "hem": { "type": "elastic_channel" }
  },
  "hull_masks": [ { "type": "box", "min": [..], "max": [..], "mode": "exclude" } ],
  "seams": { "template": "chair", "graph": null, "symmetry_plane": { "point": [0,0,0], "normal": [1,0,0] } },
  "features": [ { "type": "strap_mark", "count": 4 }, { "type": "vent", "count": 2 } ]
}
```

`hull.sweep_down: true` is the drape hull (fabric hangs from the widest point); `false` gives a
fitted shell for cushion-like objects. `construction.method` selects the joining method per
model: `double_stitch` (current practice) or `welded` (ADR-020). The shape of the `features`
list and how it relates to the `features.*` counts is settled in M5.

### Catalogue fields and revisions (M7)

`cover.json` may also hold `"family"` (a preset `config/presets/<family>.yaml`, parameter layer
2), `"status"` (`draft` | `checked` | `production`), `"tags"` (list of strings) and `"notes"`
(text for the machine operator). Every `cover export` into the model folder keeps a revision:
`revisions/<nnn>/` with `pattern.json`, `finished.json`, `cut.dxf`, `cover.json`, `seams.json`,
listed in `revisions/index.json` (`number`, `time`, `parameter_hash`, `trial` = the keys set
with `--set`, `status`, `panels`, `max_stretch_pct`, `roll_length_mm`, `warnings`).

## Seams and panels (M3)

`cover cut models/<id>/ [--seams FILE]` writes `panels.glb`, `panels.json` and `seams.auto.json`.

`seams.json` (optional, in the model directory; written by hand or copied from
`seams.auto.json`) replaces the automatic seams it names. Floor-plan coordinates in mm (as in
`model.glb`: x across, y front to back with the front at −y):

```json
{
  "format_version": 1,
  "skirt_seams": [[731.8, -699.4], [1182.8, 325.7]],
  "top_seams": [[[-500.0, 0.0], [0.0, 40.0], [500.0, 0.0]]]
}
```

- `skirt_seams`: points; each gives a vertical skirt seam at the nearest point of the outline.
  Omit the key to keep the automatic ones, give `[]` for none (a ring then stays one piece,
  which fails as not a disk).
- `top_seams`: polylines across the top; each cuts the top along that line (extended a little
  so it reaches the edge). Omit the key for none.
- `seams.auto.json` also lists `level_seams_mm`, the heights of automatic level splits. They
  are not read back; to fix them, draw them as `top_seams`.

`panels.json`:

```json
{
  "format_version": 1, "engine_version": "0.1.0", "model_id": "blocchi-2seater-moon-right",
  "panels": [
    { "id": "P1", "name": "skirt-front", "region": "skirt", "area_m2": 0.8612,
      "flat_width_mm": 404.6, "flat_length_mm": 2611.2, "fits_roll": true, "triangles": 5402,
      "seams": ["skirt-front/skirt-back", "skirt-front/top-1"] }
  ],
  "seams": [
    { "id": "skirt-front/top-1", "kind": "skirt", "panels": ["skirt-front", "top-1"],
      "length_mm": 2588.1, "lap_side": "top-1", "min_radius_mm": 62.0 }
  ],
  "tight_seams": ["skirt-front/top-1"],
  "hem_length_mm": 6302.4, "area_m2": 6.0386,
  "parameters": { "seams.corner_angle_deg": 45, "...": "..." },
  "parameter_sources": { "...": "..." },
  "warnings": []
}
```

- Panel names: `top` (or `top-1`, `top-2`, … from front to back), `skirt` (one all round) or
  `skirt-<front|right|back|left>[-n]` by the direction the panel faces.
- `flat_width_mm` × `flat_length_mm`: the panel laid flat (quick estimate, the exact pattern is
  M4), width in its narrowest orientation; `fits_roll` compares it with `roll.usable_width_mm`.
- Seam `kind`: `skirt` (skirt to top), `corner` (vertical in the skirt), `top` (from
  `seams.json`), `level` (a roll split at constant height), `roll` (a straight roll split).
  `lap_side` is the panel that laps over the other. `min_radius_mm` is the tightest curve away
  from the seam's ends (null if straight).

`panels.glb`: the furniture (grey) and every panel as its own coloured mesh named after the
panel, same mm/Z-up convention as `model.glb`.

## PatternSet (M4) — `pattern.json`

`cover flatten models/<id>/` writes `pattern.json`, `pattern.dxf`, `pattern.svg` and
`pattern-stretch.svg`. M4 patterns have no seam allowances (paper test); M5 adds them.

```json
{
  "format_version": 1, "engine_version": "0.1.0",
  "model_id": "chair", "model_sha256": "…",
  "parameter_hash": "…", "parameters": { "hull": { "clearance_mm": 10, "...": "..." } },
  "parameter_sources": { "hull.clearance_mm": "default", "...": "..." },
  "fabric_profile": "acrylic-300", "fabric_compensation": false,
  "summary": { "panels": 5, "max_stretch_pct": 1.1, "fabric_area_m2": 1.97, "hem_length_mm": 2324.1 },
  "sheet": { "sheet_mm": [2915.0, 906.0], "placements": { "top": [0.0, 0.0] } },
  "panels": [
    { "id": "P3", "name": "top", "quantity": 1, "mirror": false,
      "outline_mm": [[0.0, 0.0], [521.3, 0.0], "..."],
      "edges": [
        { "range": [0, 57], "kind": "seam", "seam": "skirt-front/top", "mate": "skirt-front",
          "lap_side": "top", "length_3d_mm": 507.45, "length_2d_mm": 507.43, "ease_mm": 0.66 },
        { "range": [57, 60], "kind": "hem", "length_3d_mm": 12.1, "length_2d_mm": 12.1 }
      ],
      "pen": [ { "type": "label", "at": [260.0, 410.0], "text": "TOP" },
               { "type": "arrow_up", "at": [260.0, 447.5], "length": 60 },
               { "type": "tick", "at": [300.0, 0.0], "dir": [0.0, 1.0], "length": 10, "pair": "skirt-front/top:t1" },
               { "type": "seam_label", "at": [253.0, 25.0], "text": "TO SKIRT-FRONT" } ],
      "stretch": { "max_pct": 17.4, "quantile_pct": 1.06, "max_stretch_pct": 17.4,
                   "max_compression_pct": 8.2, "mean_pct": 0.2, "area_pct": 0.01 },
      "flat_width_mm": 521.3, "flat_length_mm": 826.0, "fits_roll": true, "solver_iterations": 0 }
  ],
  "warnings": []
}
```

- `outline_mm`: the panel laid flat, counter-clockwise, in mm, starting at the origin; +Y is up
  on the furniture. `edges[].range` indexes outline points (first and last point of the run).
- `edges[].kind`: `seam` (with `seam`, `mate`, `lap_side`, `ease_mm`) or `hem`. `ease_mm` is
  the difference between the 2D lengths of the seam's two sides.
- `pen`: `label` (panel name), `arrow_up`, `tick` (matching mark; the other side of the seam has
  the same `pair`), `seam_label` (the panel to join along that seam).
- `stretch`: `quantile_pct` is the stretch not exceeded over `flatten.stretch_quantile` of the
  area (the value checked against the limit); `max_pct` is the absolute maximum.
- `pattern.dxf`: panels on one sheet, `export.sheet_spacing_mm` apart, cut outline as closed
  LWPOLYLINE on the cut layer, labels, arrows and marks on the pen layer, M0 conventions
  (`export.*`). `pattern.svg` is the same at 1:1 mm; `pattern-stretch.svg` colours each triangle
  by stretch (red) or compression (blue), full colour at 2 %.

Seam allowances, hem, vents and final panel data (M5) extend this format.

Every edge also has `wiggle_mm`: how far it strays from itself smoothed over 30 mm (single
corners and steps left out); above `seams.max_wiggle_mm` a warning says the edge is not a smooth
line. `panels.json` has `skirt_height_mm` (lowest and highest skirt seam height above the hem;
equal for the level skirt) and panels with `region` `top`, `skirt` or `wall`.

`sizes.pdf` (`export/drawing.py`, `cover drawing`) is the size drawing built from `panels.npz`,
`panels.json`, `hull.json` and `pattern.json`: overview views, size tables and one page per flat
panel, in cm, seam to seam. The PDF has no creation date, so the same input gives the same file.

### Reference cover (`testdata/reference/<id>.json` or `models/<id>/reference.json`)

Sizes of a cover that fits, measured seam to seam, for comparison in `sizes.pdf`:

```json
{
  "model_id": "blocchi-2seater-moon-right",
  "dimensions_mm": { "total_height": 880, "bottom_circumference": 6679.7 },
  "compare": {
    "total_height": { "label": "Total height (hem to top)", "measure": "total_height" },
    "bottom_circumference": { "label": "Hem length", "measure": "hem_length" }
  }
}
```

`compare` maps a reference size to a measurement of the calculated cover:
`total_height` (top above the hem), `plan_extent_a` / `plan_extent_b` (top view across and
depth, after `drawing.plan_rotation_deg`), `hem_length`, `hem_length:<panel>`, `straight_hem`
(longest straight run of the hem in plan), `skirt_height:<panel>` (middle of the panel's hem),
`skirt_lowest:<panel>`, `skirt_highest:<panel>`, `panel_width:<panel>` (median width of the flat
panel across its length), `seam_length:<seam id>` (on the cover).

## Finished PatternSet (M5) — `finished.json`

Written by `cover export` from `pattern.json`. One entry per piece to cut: the panels with their
allowances, and the extra pieces (vent hoods and membranes).

```json
{
  "format_version": 1, "model_id": "chair", "construction": "double_stitch",
  "pattern_parameter_hash": "…", "parameter_hash": "…",
  "pieces": [
    { "id": "P5", "name": "skirt-right", "quantity": 1,
      "cut_mm": [[x, y], …], "net_mm": [[x, y], …], "openings_mm": [[[x, y], …]],
      "edges": [{ "kind": "seam", "seam": "…", "mate": "…", "lap_side": "…",
                  "allowance_mm": 15, "length_mm": 645.4 }],
      "size_mm": [676, 479], "area_m2": 0.324, "note": "" }
  ],
  "sheet": { "sheet_mm": [w, h], "roll_length_mm": 3050 },
  "warnings": []
}
```

`cut_mm` is the cut line (allowances included, counter-clockwise), `net_mm` the seam-to-seam
outline (the stitch line) in the same coordinates, `openings_mm` the vent openings. `cut.dxf`:
CUT layer = `cut_mm` and `openings_mm`; PEN layer = stitch and hem fold lines, weld guides on
under panels (welded), matching marks, UP arrows, "P5 SKIRT-RIGHT", "TO P2 WALL", the pattern
revision (model id and parameter hash), vent hood outlines, cord exit marks.

## Fabric profile (M4 placeholder, M8 measured)

```json
{
  "format_version": 1,
  "id": "acrylic-300",
  "name": "100% acrylic canvas, approx. 300 g/m2",
  "status": "placeholder",
  "stretch_pct": { "warp": 0.5, "weft": 1.0, "bias": 3.0 },
  "weld_shrinkage_pct": { "along": 0.2, "across": 0.5 },
  "thickness_mm": 0.6,
  "source": "placeholder values, replace after swatch tests (docs/CALIBRATION.md)"
}
```

`status` must be `measured` before a pattern set is marked production. The profile holds only
measured material properties; limits such as `fabric.max_allowed_stretch_pct` and the roll width
are registry parameters (ADR-018).

## Exports (M5)

- DXF, one file per pattern set: all panels placed on a virtual sheet with 20 mm spacing (the
  machine software nests). Closed LWPOLYLINEs on the cut layer; lines and text on the pen layer.
  Units mm (`$INSUNITS` = 4), DXF version R2010. Layer names, TEXT versus stroked text, and arc
  handling follow the result of the M0 machine test; record the findings here:
  - cut layer name: TODO (M0)
  - pen layer name: TODO (M0)
  - text: TODO (TEXT entity or strokes via `ezdxf.addons.text2path`)
  - arcs: TODO (allowed, or flatten to polylines)
- SVG preview at 1:1 mm (`width="...mm"`), groups `cut` and `pen`.
- PDF cutting list: table of panels (id, name, quantity, bounding box, area), total fabric
  estimate, model name, revision, date.

## Procedural test shapes (M0)

`testdata/generate.py` (`make shapes`) writes `testdata/generated/<name>.stl` (binary STL, fixed
80-byte header `coverengine testshape <name>`) and `<name>.json`:

```json
{
  "format_version": 1, "engine_version": "0.1.0", "name": "cylinder", "units": "mm",
  "exact": { "radius_mm": { "value": 250.0, "measure": "half_size_x" },
             "bbox_min_x_mm": { "value": -250.0, "measure": "bbox_min_x" }, "...": {} },
  "reference": { "area_mm2": 942477.796 },
  "notes": {},
  "mesh": { "vertices": 832, "faces": 1536 }
}
```

`exact` values are measured by `cover info` from the mesh with the named measure
(`bbox_min_<axis>`, `bbox_max_<axis>`, `size_<axis>`, `half_size_<axis>`) and must match within
1e-6 mm. `reference` values belong to the continuous surface; the mesh only approximates them.
Dimensions come from `testdata/shapes.yaml` (ADR-019).

## Machine test sheets (M0)

`cover testsheet` (`make testsheets`) writes `testdata/machine/testsheet-*.dxf` from
`testdata/machine/testsheet.yaml`: variants A (layers CUT/PEN, TEXT), B (layers 0/1), C (text
as single-stroke lines), D (all on layer 0, red = cut, blue = pen, colour per entity), A-R12
(variant A as DXF R12; R12 has no unit header). Cut: 1000 × 100 strip R1, 200 × 200 square R2,
120 × 60 rounded rectangle R3 (bulge corners, r 10), circle Ø200 as CIRCLE (O1), two bulge arcs
(O2) and 72 segments (O3). Pen: labels at 15/12 and 8 mm, 10 mm ticks every 50 mm on R2, a pen
line 20 mm inside R2, a guide arc as ARC (G1) and as 32 segments (G2), a 100 mm scale bar.
Sheet about 1100 × 560 mm. The results of cutting them decide `export.*`.
