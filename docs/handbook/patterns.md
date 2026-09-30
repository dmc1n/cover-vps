# Flat patterns

After the panels (`seams.md`), `cover flatten` lays every panel out flat, in true millimetres.

```
uv run cover flatten models/<id>
```

```
patterns -> models/<id>/pattern.dxf, pattern.svg, pattern-stretch.svg, pattern.json, sizes.pdf
  top                 521 x    826 mm   stretch 1.06 % (max 17.4 % in a small spot)   fits the roll
  skirt-left          646 x    900 mm   stretch 0.61 % (max 8.6 % in a small spot)    fits the roll
  ...
seams  largest difference between the two sides of a seam: 1.4 mm
fabric 1.97 m2 without allowances, sheet 2915 x 906 mm
```

## Everything in one go

```
uv run cover run testdata/models/<file>.stp --out models/<id> --units m --up y
```

does import, cover, panels and patterns. Settings for a trial run go on the end, for example
`--set hull.clearance_mm=15`.

## The files

| file | what it is |
|---|---|
| `pattern.dxf` | all panels at 1:1 for the cutting table: outlines on the cut layer; names, UP arrows, matching marks and "TO …" labels on the pen layer |
| `pattern.svg` | the same, to look at in a browser or print at 100 % |
| `pattern-stretch.svg` | each panel coloured by how much it had to stretch (red) or shrink (blue) to lie flat; white is exact, full colour is 2 % |
| `pattern.json` | every panel's outline, seams with their lengths, and all settings used |
| `sizes.pdf` | the size drawing, to check the sizes by hand (below) |

These patterns have **no seam allowances yet**; those come in M5. They are for the paper test:
cut them, tape them edge to edge, and put the cover on the furniture.

## Reading the numbers

- **stretch:** how much the flat panel differs from the cover's shape. Under 2 % is fine (the
  limit, `fabric.max_allowed_stretch_pct`). "max … in a small spot" is the worst point, often a
  corner of the cover where the fabric eases anyway.
- **difference between the two sides of a seam:** both panels along a seam should be the same
  length. A difference above 1 mm is recorded as ease on that seam. When sewing or taping, spread
  it evenly between the matching marks.
- **matching marks:** short pen lines every 30 cm along each seam. The same mark sits on both
  panels; tape mark to mark.
- **UP arrow:** points up on the furniture.

## The size drawing (`sizes.pdf`)

A drawing like a workshop drawing of the cover, to check the sizes yourself:

- **Page 1:** the finished cover from above, from the front, from the right and in 3D, with the
  overall sizes, the skirt height at both ends, the length of every seam on the top, and a title
  block (fabric, fit, hem, number of air vents).
- **Page 2:** all sizes as tables. The key sizes; when a reference exists (a cover that fits, in
  `models/<id>/reference.json` or `testdata/reference/<id>.json`), each next to the reference
  and the difference, green within the fit tolerance (±5 mm). Then every seam: its length on the
  cover and on both flat panels, and the difference. Then every panel: flat size, typical width,
  stretch, and whether it fits the roll.
- **One page per panel:** the flat pattern piece with the length of every edge ("to top-1
  102.6 cm" is the seam to panel top-1), its overall size, area and stretch.

All sizes are seam to seam, without seam allowances or hem, like a drawing of the finished
cover. The drawings are to scale on A4, but use the numbers; do not measure the print.

`cover flatten` writes it every time. To redraw it without flattening again (for example after
changing the reference):

```
uv run cover drawing models/<id>
```

The top view is drawn as the 3D model lies. To turn it so it matches your own drawing, set
`drawing.plan_rotation_deg` in the model's `cover.json` (the Blocchi: 24.1, so its straight end is
vertical as on your drawing).

## Comparing two runs

After a change of settings:

```
uv run cover diff old/pattern.json models/<id>/pattern.json
```

lists the panels whose size changed by more than 1 mm, and the settings that differ.
