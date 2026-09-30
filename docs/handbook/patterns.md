# Flat patterns

After the panels (`seams.md`), `cover flatten` lays every panel out flat, in true millimetres.

```
uv run cover flatten models/<id>
```

```
patterns -> models/<id>/pattern.dxf, pattern.svg, pattern-stretch.svg, pattern.json
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

## Comparing two runs

After a change of settings:

```
uv run cover diff old/pattern.json models/<id>/pattern.json
```

lists the panels whose size changed by more than 1 mm, and the settings that differ.
