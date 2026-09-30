# Calibration and measurement protocol

The engine is only as accurate as the numbers it is given and the measurements that check it.
This file has two parts: the fabric and weld swatch tests (M8) and the cover measurement
protocol used at every physical gate (M4, M5, M8).

## Fabric and weld swatch tests (M8)

Fabric: 100 % acrylic canvas from the production roll. Record the roll batch.

1. Stretch: cut three 300 × 50 mm strips each along warp, weft and 45° bias. Mark a 200 mm
   gauge length. Hang a load representative of the tension a fitted cover sees (start with 2 kg
   and record it). Read the gauge length after 60 s. Stretch % = (L − 200) / 200 × 100. Average
   the three strips per direction.
2. Relaxation: release the load, wait 10 minutes, read again. Record the permanent set.
3. Weld shrinkage: weld two 300 mm strips with the production overlap and settings, along the
   warp and, separately, across it. Measure the length of the welded assembly against a marked
   reference before welding. Shrinkage % along and across the seam.
4. Weld curvature: weld a curved seam at radii 300, 200, 150 and 100 mm on scrap. Note the
   smallest radius that welds flat without puckering. This becomes `min_weld_radius_mm`.
5. Thickness with a calliper at three points.
6. Record everything in a copy of `testdata/fabrics/measurements.template.json` (for example
   `testdata/fabrics/acrylic-300.measurements.json`), then run
   `uv run python scripts/fabric_profile.py testdata/fabrics/acrylic-300.measurements.json`.
   It writes the profile (`status: measured`) and prints the weld radius to put in
   `config/defaults.yaml`. Then switch on `flatten.fabric_compensation` and run the covers again.

## Cover measurement protocol (physical gates)

Prepare per gate: the export files, a printed checklist, and this measurement sheet filled in
with the five points for the specific piece of furniture.

1. Five measurement points chosen before cutting, marked on a photo of the model: typically two
   on the top (length and width at defined edges), one on the tallest vertical (hem to top), one
   across a corner or transition (seat to back), one at the hem circumference.
2. For each point: the target dimension from the engine (PatternSet metadata), the measured
   dimension on the fitted cover, and the difference. Target: every difference within ±5 mm.
3. Note qualitative issues with a photo: wrinkles (where, direction), gaps between fabric and
   furniture, seams off the intended edge, pen marks unreadable, panels that did not meet.
4. Time spent: import to DXF (operator time), cutting, welding, fitting.
5. Enter the results in `docs/reports/M<n>.md`. Every tolerance or parameter change that follows
   gets an entry in docs/DECISIONS.md with the measurement that caused it.

## Measurement sheet template

| Point | Where | Target mm | Measured mm | Difference mm | Within ±5? |
|-------|-------|-----------|-------------|---------------|------------|
| 1     |       |           |             |               |            |
| 2     |       |           |             |               |            |
| 3     |       |           |             |               |            |
| 4     |       |           |             |               |            |
| 5     |       |           |             |               |            |

Observations:

Times (import→DXF / cut / weld / fit):
