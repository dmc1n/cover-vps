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

## The product list (ADR-091)

Link the workshop's product list to the drawing covers, so the Desk can show, search and sort
by product.

- **Upload:** "Upload product list (Excel)" at the top of the Desk. It takes an .xlsx, a .csv,
  or a .zip with one or more of them. A zip with the list and no drawings may also go through
  the studio's drawings-zip button; it ends up in the same place.
  - An old **.xls** file is refused: open it in Excel, Save As "Excel Workbook" (.xlsx).
  - Column names do not matter. The program finds the header row and the column that names
    the drawings (D1, C 23, s40, Cover 105, …) by what is in it.
- **The result** says how many rows were linked to how many drawings, and through which
  column. If it picked the wrong column, choose another and press "Apply again". It also lists:
  - rows it could not link (usually a drawing not uploaded yet);
  - drawings without a product;
  - codes that carry two different products;
  - the PDFs in a zip and whether their drawings already exist. PDFs are not imported here.
- **In the list** each cover shows its products under its name. The search finds them, and
  "Sort" orders by code, product, status or AI score.
- **On the card**, "Products" shows the rows of the list for this cover, and the SUNS models
  it fits:
  - a dark chip is a **link**: family and type agree (Portofino D-Bed → the Portofino daybed);
  - a dashed chip with "?" is only a **suggestion**: the family agrees, but the description
    names no type ("lounge set normal"). Check it by eye.

  A SUNS model's card shows the drawings it is linked to.
- Uploading again replaces the links; every upload is kept in `products/` in the data folder.

## Afkeuren: welke feedback helpt (voor Rens)

Hoe preciezer de afkeuring, hoe sneller de hoes goed is. Het programma leert ervan: na 5 gelijke
correcties wordt het een regel voor alle hoezen (ADR-082).

**Per afkeuring:**

1. **Soort fout:** kies de reden in de Desk: vorm, maat, naden, vents of stukken.
2. **Waar:** welke kant of welk deel, bijvoorbeeld "linker arm", "rugstrook", "binnenhoek" of
   de naam van het stuk ("skirt-front-2", zie de lijst met stukken op de kaart).
3. **Wat het moet zijn, het liefst met een getal:**
   - "rughoogte moet 90 cm zijn, nu 84";
   - "1 vent te veel aan de achterkant";
   - "naad moet op de vouw, niet 10 cm ervoor".
4. **Waarom**, als het niet uit de tekening blijkt: "zo naaien wij dat altijd", "past niet om de
   armleuning". Zulke regels gaan voor alle hoezen gelden.

**Ook handig:**

- **Twijfel over de tekening zelf:** zeg welke maat op de tekening fout of onduidelijk is
  (zoals C27: 235,1 cm tegen 96,5 inch).
- **Bijna goed:** keur dan af met een kleine opmerking, niet goedkeuren. Anders leert het
  programma niets.
- **Een plaatje zegt meer:** een screenshot met een pijl of cirkel mag naar Rick; die geeft het
  door.

**Minder handig:** alleen "klopt niet" of "vorm fout". Dan moet geraden worden wat er bedoeld is.

Eén zin met **waar, wat en een getal** is genoeg.
