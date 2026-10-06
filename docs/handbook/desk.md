# The Desk: approve the drawing covers

**Desk** in the top bar. The AI sorts, people decide (ADR-079).

- **The queue** puts first what needs a person:
  1. covers where Gemini and DeepSeek disagree;
  2. covers they found poor;
  3. rejected ones;
  4. middling ones;
  5. covers not yet checked;
  6. covers both found right;
  7. approved and produced covers come last.

  Filter by status, by series (C, S, D, …) or search.
- **The card** puts the drawing (click to enlarge) beside our cover in 3D (tick "Show air
  vents"). It also shows:
  - what the program read from the drawing, with a green or red dot per line (vents, open
    bottom, pieces, DXF);
  - what both AIs say;
  - the pieces, the revisions and the history.
- **Who decides:** Rens, Rick and Wouter (setting `desk.approvers`) and admins.
- **The actions:**
  - **Approve** (key `a`): the catalogue status becomes "checked".
  - **Reject** (`r`): choose a reason (shape, size, seams, vents, pieces) and write what is
    wrong. It is kept in the history. To change the cover itself, use "Correct this cover".
  - **Produced** (`p`): the cover was really made; the catalogue status becomes "production".
  - **Fits / does not fit:** after sewing, with a note.
  - **Undo** (`u`) takes back the last step. Use `j` and `k` to go to the next or previous
    cover.
- **The cutting table's DXF** of a drawing cover downloads only once the cover is approved.
  Before that the model page shows a lock. An admin can force it with `?override=1`, which the
  history keeps.
- **The AI spend** of this month is shown in the top right (ADR-078).

## Correct this cover (ADR-082)

A correction changes the cover itself: it is saved on the cover, the cover is recalculated at
once, and the correction is kept as a test the program must keep passing.

- **Seams:**
  - **remove seam** joins the two pieces on either side (covers drawn in parts, and box covers);
  - **add a seam** to a piece: at a height above the hem, or across from its left end or its
    front;
  - **skirt seam at … cm**: only on covers whose seams follow the furniture.
- **Vents:** the right number, and the height of their bottom edge above the hem.
- **Sizes:** pick a size the program read (or type one) and give the right value. It is kept
  for the drawing reader.
- **Shape:** what is missing (round front, back profile, taper, wrong height, mirrored), with
  a few words. This is for the program's next improvement; the top of the Desk counts how often
  each problem comes back per series.

**Rules that are learned.** When the same correction is made on `desk.learn_after` (5)
covers of one series (or family), the top of the Desk proposes it: "Corrected the same way on
5 covers of drawing-s: vent height above the hem = 120". **Make it the rule** writes it as the
series' rule. Every cover of the series then uses it (its own settings still win) and is
recalculated.

**Do the corrections still hold?** `scripts/learned_check.py` checks every correction against
the covers as they are now; with `--recalc` it calculates them again first.
