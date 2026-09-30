# Export for the cutting table

After the flat patterns (`patterns.md`):

```
uv run cover export models/<id>
```

writes the pieces as they are cut:

| file | what it is |
|---|---|
| `cut.dxf` | every piece at 1:1 for the CNC table. CUT layer: the cut line (with seam allowances and hem) and the air vent openings. PEN layer: the stitch line, the hem fold line, matching marks, "P5 SKIRT-RIGHT", "TO P2 WALL" at each seam, the UP arrow, where the vent hood goes, cord exits, and the pattern revision |
| `cut.svg` | the same, to look at or print at 100 % |
| `cutting-list.pdf` | every piece with its number, quantity, size and area, and about how much fabric it takes on the roll |
| `finished.json` | the same data for the web app |

`cover run` does this too, as its last step.

## The rules (settings in `config/defaults.yaml`)

- **Stitched seams** (today's practice, `construction.method: double_stitch`): 15 mm allowance
  on both pieces (`stitching.allowance_mm`, `stitching.sides`).
- **Welded seams** (`construction.method: welded`, per model in `cover.json`): 30 mm overlap on
  the piece that laps over (`welding.overlap_mm`); the other piece gets a pen line where the
  upper piece's edge must land.
- **Hem:** 50 mm (`hem.allowance_mm`), the fold line on the pen layer; cord exits as pen marks
  (`hem.cord_exits`).
- **Air vents:** 25 × 22 cm, 5 cm above the hem, one per full metre of hem, spread evenly, at
  least 10 cm from a vertical seam. The opening is cut out of the skirt piece; the hood and the
  membrane are separate pieces in the list. If the skirt is too low for a vent, you get a
  warning.

All of these are still to confirm (see `docs/QUESTIONS.md`); changing one is a one-line edit.
