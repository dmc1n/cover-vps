# M0 machine test — checklist (one page)

**Goal:** learn how the cutting table reads our DXF files: layer names, text, arcs, scale and
pen position. Use paper or scrap fabric. Sheet size about 1100 × 560 mm.

**Files** (in `testdata/machine/` on GitHub or on the server):

| File | What is different |
|------|-------------------|
| `testsheet-A-named-layers.dxf` | layers named **CUT** (red) and **PEN** (blue), normal text |
| `testsheet-B-layers-0-1.dxf` | layers named **0** (cut) and **1** (pen) |
| `testsheet-C-stroked-text.dxf` | as A, but all text is made of pen lines |
| `testsheet-D-colours-only.dxf` | everything on layer 0; **red = cut, blue = pen** |
| `testsheet-A-R12.dxf` | as A, old DXF format (R12). Set import units to **mm** by hand |

## At the computer

1. Import **A**. Note: does it open? Which layers or colours does the software offer to map to
   knife and pen? Does it show the size about 1100 × 560 (not 43 × 22, which would be inches)?
2. Import **B**, **C**, **D** and **A-R12** the same way. Only note what is different from A.
3. Pick the variant that needed the least manual setup. Map cut → knife and pen → pen.

## At the table (chosen variant)

4. Cut and draw it. Watch whether the pen draws the text, or skips or garbles it.
5. If text was not drawn properly, also run **C** (text as lines).

## Measure (steel ruler or tape, to 1 mm)

| # | What | Target | Measured |
|---|------|--------|----------|
| 1 | R1 strip, long side | 1000 mm | |
| 2 | R1 strip, short side | 100 mm | |
| 3 | R2 square, both sides | 200 × 200 mm | |
| 4 | O1, O2, O3 diameter | 200 mm each | |
| 5 | Pen line inside R2 to the cut edge, left / right / bottom / top | 20 mm each | |
| 6 | Pen scale bar (top left) | 100 mm | |

## Report back (copy, fill in, paste to Claude Code)

```
Machine / software name and version:
Variants that imported cleanly: A? B? C? D? A-R12?
Layer names / colours that worked for knife and pen:
TEXT drawn by the pen? (yes / no / garbled)      Stroked text (C) OK?
O1 circle entity: smooth? O2 bulge arcs: smooth? O3 72 segments: smooth or faceted?
G1 arc (pen): drawn? G2 segmented: drawn?
R3 rounded corners cut round?
Measurements 1-6:
Anything odd (warnings on import, wrong scale, sheet mirrored, pen offset):
Photo of the cut sheet: yes / no
```
