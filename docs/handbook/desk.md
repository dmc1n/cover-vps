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
    wrong. Your words become a lesson for the AI.
  - **Produced** (`p`): the cover was really made; the catalogue status becomes "production".
  - **Fits / does not fit:** after sewing, with a note.
  - **Undo** (`u`) takes back the last step. Use `j` and `k` to go to the next or previous
    cover.
- **The cutting table's DXF** of a drawing cover downloads only once the cover is approved.
  Before that the model page shows a lock. An admin can force it with `?override=1`, which the
  history keeps.
- **The AI spend** of this month is shown in the top right (ADR-078).
