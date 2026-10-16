# The Desk: approve the covers

**Work → Desk** (`#/work/desk`; the start page of an approver, see
[navigation.md](navigation.md)). The AI sorts, people decide (ADR-079, ADR-128). What the Desk approved
or marked produced is listed for the workshop, with its files and how it fitted, on
**Work → Workshop** ([workshop.md](workshop.md)); nothing can be approved there.

- **The queue** puts orders waiting for approval first, whatever the sort or AI scores.
  They have an **ORDER #n** tag, with **B2B** for a business order. An approver can press
  **Approve** in the queue once the cutting file is built. Before that it says
  **being calculated…**. A catalogue cover keeps its approval if its current cut is unchanged.
  Then come the other covers that need a person:

  1. covers where Gemini and DeepSeek disagree;
  2. covers they found poor;
  3. rejected ones;
  4. middling ones;
  5. covers not yet checked;
  6. covers both found right;
  7. approved and produced covers come last.

  Filter by status, by series (C, S, D, …) or search. Two filters answer "has anything
  happened since my remark?" (Rens, 14 Oct 2026; ADR-135):
  - **Waiting for us** (with its number): every cover with a remark (a rejection, a comment
    or a fit) newer than the studio's last change. The studio still has to answer it; the
    daily round lists the same covers (`scripts/desk_open_remarks.py`).
  - **2nd round**: only covers the studio changed after a remark and that now wait for a look
    again (new or AI checked). Approved or rejected-again covers are not in it.

  On each row and on the card's head a small chip says it: **Changed 12 Oct** (the studio
  changed it after the last remark; the date is the change) or **Not changed yet** (orange:
  your last remark is newer than the studio's last change). No chip: nobody left a remark.
- **The card** (`#/work/desk/<cover>`) has four tabs, each with its own address:
  - **Check**: the latest rejection and what happened since; the drawing (click to enlarge)
    beside our cover in 3D (the **Vents** toggle shows the air vents, Show ▾ → **Logo** each
    vent's logo on its hood, from the cutting file: check it before you approve, ADR-146);
    the products; what the
    program read from the drawing, with a green or red dot per line (vents, open bottom,
    pieces, DXF); what both AIs say;
  - **Pieces & revisions**: the pieces and the revisions ("cut this": the revision the
    workshop cuts);
  - **Correct this cover** (below);
  - **History**: everything that happened, with the pictures.

  **More** (top right of the card): Let the AI read it (costs about 1–5 cents), the check
  list, Edit arrangement, the cut pieces and DXF, the product list. **Open cover** (the arrow out of a box) opens the
  cover's own page.
- **Who decides:** admins, users marked **may approve**, and the user names in
  `desk.approvers` (Rens, Rick and Wouter). See Settings → Rules & defaults → Desk & approval.
  The workshop login never approves, even if its name is in that list (ADR-128).
- **One approval:** the Desk is the only approval. The cover page's separate
  definitive-drawing approval is retired. Old approvals stay visible as history. A Desk
  approval stamps the size drawing and cutting list, when available, with
  `APPROVED <name> <date> revision <n>` on every page. Download **Approved size drawing**
  and **Approved cutting list** from the cover's approval card above the tabs. These stamped
  downloads disappear when a change invalidates the approval. Review it at the Desk and
  approve again.
- **The workshop login** can use **Comment**, with pictures, and **After sewing ▾ → Fits /
  Does not fit / Measured…**. It cannot Approve, Reject, mark Produced, Undo, correct a cover
  or start the AI.
- **The actions** (the decision bar at the bottom of the card; the after-sewing ones under
  **After sewing ▾**):
  - **Approve** (key `a`): the catalogue status becomes "checked". The approval stamps the
    size drawing and the cutting list, which can take from a few seconds to a minute: the
    button says **Approving…** and every action waits until it is done. Then a message at
    the top right says **Approved: <cover>**, the counts and the list follow, and the next
    cover of the list opens. Approving a rejected cover works the same way. A cover that is
    already approved for its current cutting file is not approved twice: the message says
    who approved it and when (ADR-135).
  - **Every action says how it went.** A refusal (for example "nothing to undo", "approve
    the cover before marking it produced", "already approved by …") shows in red at the top
    right and next to the buttons, with the server's reason. It never fails silently.
  - **Reject** (`r`): choose a reason (shape, size, seams, vents, pieces) and write what is
    wrong. It is kept in the history. To change the cover itself, use "Correct this cover".
  - **Comment** (`c`): a remark for the history; the status stays as it is.
  - **Pictures** with a reject or a comment: a snapshot of the 3D view or the drawing, a file,
    a drop or a paste (Ctrl+V), marked with red arrows, circles and lines (ADR-096). The
    history shows them as thumbnails; click one to enlarge it.
  - **Produced** (`p`): the cover was really made; the catalogue status becomes "production".
  - **Measured…** (After sewing ▾): enter what was measured on the sewn cover against the
    check list (in the 3D toolbar and under More); the differences are kept for the learning
    step. See [measuring.md](measuring.md) (ADR-111).
  - **Fits / does not fit** (After sewing ▾): after sewing, with a note. The result shows on
    Work → Workshop.
  - **Undo** (`u`) takes back the last step. Use `j` and `k` to go to the next or previous
    cover.
- **The cutting-table DXF** of every cover downloads only once the current cut is approved
  at the Desk (ADR-128; `desk.gate_scope: all`). This includes drawings, arrangements, SUNS,
  barbecues and shop orders. Setting the catalogue status by hand does not unlock it.
  Every DXF waits for approval, including the flat pattern DXF.
  A rebuild that changes the cutting file puts it back to waiting with “changed after approval”
  in the history. Review it and approve again. A saved revision downloads only if its cutting
  file was approved at some point. Earlier approvals keep working: their current file is
  recorded once with “fingerprint recorded for an earlier approval” in the history.
  Before that the cover's page shows a lock in its status strip, and Work → Workshop says the
  DXF waits for (re)approval. An admin can force it with `?override=1`, which the history
  keeps.
- **The AI spend** of this month is shown at the top of the Desk to admins only (ADR-078); the
  details are on Settings → AI & spending.

**For the admin:** the developer runs `scripts/desk_definitive.py` and
`scripts/desk_gate_all.py` only on the server, with `--dry-run` first, then `--apply`
(ADR-128). They carry matching old approvals and covers already in use into the Desk,
record earlier approvals' cutting files, and send the other built covers for approval.
Rejected covers and approvals for another cut stay closed.

## The cutting file in the browser (ADR-147)

You can look at the cutting file while you decide, without downloading it. On a Desk card it
is at the top of **Pieces**; on a cover's page under **Pieces → Cutting file** (also the
*Cutting file* button next to the DXF on Cut pieces).

- **What you see is the cutting table's file.** The studio reads the cover's own `cut.dxf`
  and draws it: red is cut (outlines and the vent openings), blue is drawn by the pen (stitch
  lines, ticks, the LOGO frames, TOP/UP arrows, labels). It never shows the separate
  `cut.svg`, so the picture and the file cannot differ.
- **PREVIEW – NOT FOR CUTTING.** Until the Desk approves this very cutting file, those words
  run across the drawing and over its top, and the chip says *Preview*. A screenshot or a saved
  picture keeps them. After approval the chip says *Approved* and the words go. The DXF itself
  stays locked until approval, exactly as before: looking is not downloading.
- **Layers:** *Cut*, *Pen*, *Texts* and *Names* switch each layer off and on (the browser
  remembers your choice). *Names* are the big piece names drawn over the sheet when zoomed out;
  they step aside once the file's own labels are readable.
- **Moving around:** drag to move; scroll, use + and −, or pinch with two fingers on an iPad to
  zoom; the square button (or the 0 key) fits the whole sheet. The bar at the bottom left is the
  scale in cm.
- **A piece's size:** click (tap) a piece. Its box (width × height on the sheet), area, outline
  length and each edge from corner to corner (E1, E2, …, in cm) appear under the drawing and on
  the piece. Tiny edges, such as an allowance's cut-off corner, are counted in the edge next to
  them.
- **Measuring:** the tape button, then two clicks; a click near a corner snaps to it. The
  distance is shown in cm and mm.
- **Compare with an older revision:** choose it under *Compare with* (or *compare* in the
  Revisions list). Both drawings appear side by side (one above the other on an iPad) with a
  list of what changed: new pieces (green), pieces gone (red), a size or outline change
  (orange), and changes on the pen layer only (purple), for example the new vent logo
  (ADR-146): then it says *Pen marks only: every cut line the same*. Click a row to zoom both
  drawings to that piece.
- **Who sees it:** admins, the Desk's approvers and editors, for every cover. The workshop
  login sees it only once the cover is approved (then it can download the DXF anyway).
  Viewers do not see it.

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

- **Upload:** **Covers → Product list** (`#/covers/products`, editors and admins), "Upload
  product list (Excel)"; the card's **More** links there. It takes an .xlsx, a .csv, or a .zip
  with one or more of them. A zip with the list and no drawings may also go through the
  reference-pairs upload on Covers → New cover; it ends up in the same place.
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
- **Een plaatje zegt meer:** voeg het zelf toe, in het venster van Reject of Comment, onder
  "Pictures":
  1. **Snapshot 3D** neemt de 3D-hoes zoals je hem nu draait; **Snapshot drawing** de
     tekening. Of **Upload…** een foto (JPG, PNG, WebP), sleep hem erin, of plak met Ctrl+V.
  2. Teken in rood: **Arrow** (sleep naar waar de pijl moet wijzen), **Circle** of **Line**.
     **Undo** of Ctrl+Z haalt de laatste weg, **Clear** alles.
  3. **Use this picture**, dan **Reject** of **Save comment**. Het plaatje staat in de
     geschiedenis van de hoes (klik om te vergroten); het programma en Claude zien het daar.
  4. Het werkt ook bij **Correct this cover** ("Pictures with the correction").
  5. Lukt iets niet, dan staat er in rood onder "Pictures" waarom. Probeer dan Chrome of
     Firefox, of maak een schermafdruk en kies **Upload…**.

**Minder handig:** alleen "klopt niet" of "vorm fout". Dan moet geraden worden wat er bedoeld is.

Eén zin met **waar, wat en een getal** is genoeg.

## Vragen beantwoorden (voor Rens, ADR-109)

De vragen over hoezen, de werkplaats, de shop en de prijzen staan in de studio, onder
**Work → Questions** (`#/work/questions`). Je hoeft er niet meer voor te mailen.

1. **Work → Questions.** Het getal naast Work en Questions in het menu is het aantal open
   vragen. Is het rood, dan wachten er vragen op jouw antwoord. Die hebben in de lijst een rood
   stipje. Het zoekvak bovenaan de studio vindt een vraag ook op titel of nummer.
2. **Kies een vraag.** Filter bovenaan op Open, Answered of Processed, of op onderwerp (vents,
   shape, seams, webshop, prices, …). Zoeken kan ook, met `/`.
3. **Lees de vraag.** Daaronder staan:
   - de hoezen waar het over gaat (klik om de kaart op de Desk te openen);
   - de plaatjes (klik om te vergroten);
   - "Context" met wat er al is klaargezet;
   - wat anderen al antwoordden.
4. **Antwoord:**
   - kies een optie (of druk `1`, `2`, `3` …), of **Anders, namelijk…** (`0`) en schrijf wat;
   - wil je iets aanwijzen, gebruik dan **Pictures**, net als bij Reject: **Mark picture 1**
     (een plaatje van de vraag) of **Mark S45** (de hoes), of **Upload…**, slepen of plakken.
     Teken in rood en kies **Use this picture**;
   - een opmerking erbij mag altijd: waarom, een maat, wat er nog ontbreekt;
   - **Send answer** of `Ctrl+Enter`.
5. **Van mening veranderd?** Antwoord opnieuw; je nieuwe antwoord vervangt het oude.
6. **Wat er daarna gebeurt:**
   - elke dag rond 18:00 verwerkt Claude de antwoorden;
   - Rick kan een antwoord als definitief markeren;
   - een verwerkte vraag gaat naar "Processed", met wat er is gedaan. Dat zie je bij de vraag
     en in de mail van de volgende dag.

Nieuwe vragen komen hooguit één keer per dag per mail, nooit per klik. Werkt het plaatje niet in
Edge, dan staat er in rood waarom; kies dan **Upload…** met een schermafdruk.

## Arrangements at the Desk (ADR-115)

An arrangement (furniture placed together under one cover, see
[arrangements.md](arrangements.md)) is approved at the Desk like a drawing cover.

- **ARR** in the series chips shows only the arrangements, with the number beside it. Each is
  named by its own name ("portofino 2 + c"), with an **ARR** tag instead of AI scores.
- **Status:** "Not sent yet" (built, its maker has not sent it), **Ready for approval** (sent;
  the list says by whom), Approved, Rejected, Produced.
- **The card** has, instead of the drawing, the arrangement seen from above: each piece in
  its own colour with its number, the cover's plan (follow, box or smoothed) as a red line,
  the front at the bottom. Below: each piece with its picture, size, place (cm), turn and
  mirror, a link to its own model and to its own Desk card. The bar above the card says where
  it stands: waiting (sent by whom, when), approved by whom, rejected and why, or "waiting
  again" after a change. Then the 3D cover (Measure, Show ▾ → Vent sizes, Check list), and
  on the other tabs the pieces, the revisions and the history. **More → Edit arrangement**
  opens it on Covers → Arrangements.
- **The DXF** of an arrangement downloads only once it is approved, whatever
  `desk.gate_scope` says (`desk.gate_arrangements: true`).
- **An approved arrangement never changes silently.** If its plan or pieces change on the
  Covers → Arrangements, or its cut file changes at all (built again from the cover's page, a
  correction), it goes back to "Ready for approval" with "changed after approval" in the
  history, and the DXF is locked again.
- **Mail:** the approvers get the arrangements sent that day in the daily digest of the
  Questions (`questions.digest_hours`), never one mail per click.

### Opstellingen goedkeuren (voor Rens en Wout)

1. **Work → Desk → ARR.** Je ziet alle opstellingen. "Ready for approval" wacht op jou; erbij staat
   wie hem stuurde. Je krijgt ze ook één keer per dag in de mail met de vragen.
2. **Open de kaart.** Links de opstelling van bovenaf: elk meubel met een nummer, de rode lijn
   is de hoes. Onder de tekening de meubels zelf, met een link naar hun eigen model. Rechts de
   hoes in 3D; met **Measure** meet je, met **Show ▾ → Vent sizes** zie je de maten van de
   vents, met **Show ▾ → Logo** waar het logo op elke kap komt (midden langs de onderkant van
   de vent, rechtop).
3. **Klopt het?** **Approve** (`a`). Dan pas kan de werkplaats de DXF downloaden (ook op
   Work → Workshop).
4. **Klopt het niet?** **Reject** (`r`) met een reden en eventueel een plaatje. Wie hem maakte
   past hem aan onder Covers → Arrangements; na opnieuw bouwen staat hij vanzelf weer bij jou.
5. **Later veranderd?** Verandert iemand een goedgekeurde opstelling (andere plattegrond,
   meubel verschoven, ander meubel), dan staat hij weer op "Ready for approval" met
   "changed after approval" in de geschiedenis, en is de DXF weer op slot.
