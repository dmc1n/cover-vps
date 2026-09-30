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

## Seam graph (M3)

```json
{
  "format_version": 1,
  "seams": [
    { "id": "left-corner",
      "anchors": [ { "face": 1234, "bary": [0.2, 0.3, 0.5] }, { "face": 2201, "bary": [1, 0, 0] } ],
      "closed": false, "lap_side": "auto" }
  ]
}
```

`lap_side` is `auto` (engine decides by height and front/side rule), or a patch id.

## PatternSet and Panel (M4–M5)

```json
{
  "format_version": 1,
  "model_id": "lounge-chair-a12", "revision": 3, "parameter_hash": "...",
  "parameters": { "hull": { "clearance_mm": 10, "bridge_gap_mm": 60, "...": "..." }, "welding": { "overlap_mm": 30 }, "...": "..." },
  "parameter_sources": { "hull.clearance_mm": "model", "welding.overlap_mm": "default" },
  "fabric_profile": "acrylic-300",
  "summary": { "panels": 6, "max_stretch_pct": 1.8, "fabric_length_mm_est": 3200 },
  "panels": [
    { "id": "P1", "name": "top", "quantity": 1, "mirror": false,
      "outline_mm": [[0,0],[1200,0],[1200,800],[0,800]],
      "edges": [
        { "range": [0,1], "kind": "seam", "mate": { "panel": "P2", "edge": 0 },
          "lap_side": "P1", "overlap_mm": 30, "length_3d_mm": 1200.4, "length_2d_mm": 1200.1, "ease_mm": 0.0 },
        { "range": [2,3], "kind": "hem", "allowance_mm": 50 }
      ],
      "pen": [ { "type": "label", "at": [600,400], "text": "P1 top  A12 r3" },
               { "type": "guide_line", "points": [[..],[..]], "for_mate": "P2" },
               { "type": "tick", "at": [300,0], "dir": [0,1], "pair": "P2:t1" },
               { "type": "arrow_up", "at": [600,700] } ],
      "stretch": { "max_pct": 1.2, "mean_pct": 0.4, "area_pct": 0.3 } }
  ]
}
```

`outline_mm` is the raw panel; export adds allowances from `edges`. `range` indexes outline
vertices. Ticks are paired across mates by id.

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
