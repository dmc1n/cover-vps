# The Workshop page: what to cut, and how it fitted

**Work → Workshop** (`#/work/workshop`, ADR-124). For the workshop and the owner: one list of
every cover the Desk has **approved** or marked **produced**, with the files to cut and sew it
and what we know about how it fitted.

**Nothing on this page changes anything.** It only shows. Approving, marking a cover produced,
and entering the measured sizes and Fits / Does not fit stay on the cover's Desk card, under
**After sewing ▾** (see [desk.md](desk.md) and [measuring.md](measuring.md)).

## Who sees it

Every login of the studio (viewer, editor, admin) can open the Workshop page for now. The
customers' fit answers are shown to editors and admins only; a viewer sees a note in their
place. A separate workshop login or right (for example: see this page and download, but not
approve) does not exist yet: that is open owner question #92.

## What each line shows

- **The picture and the code** of the cover.
- **The status:** *approved* or *produced*, by whom and when.
- **The files:**
  - the **cutting list** (PDF);
  - the **size drawing** (PDF);
  - the **check list** (PDF), to measure the sewn cover against
    ([measuring.md](measuring.md));
  - the **cut pieces** as a picture (SVG);
  - the **cutting table's DXF**, but only when the approval allows it. The DXF belongs to the
    approved cutting file (ADR-079, ADR-115, ADR-120): when the cover was built again after
    the approval and the cutting file changed, or an arrangement was changed, the line says
    the DXF **waits for (re)approval at the Desk** and links the Desk card. Once an approver
    approves it again, the DXF is back here.
- **The revision to cut:** the revision the Desk marked as "cut this" (on the card's *Pieces &
  revisions* tab).
- **The measured fit**, when someone entered it after sewing:
  - **Fits** or **Does not fit**, with the note;
  - how many sizes were measured, and the largest difference against the check list.
- **The customers' fit answers**, for covers sold from the shop: 1 to 5 stars, the
  customer's comment and photo (editors and admins; a viewer sees a note).

## Filters

One row at the top:

- **Search**;
- **approved / produced**;
- **fit:** any, fits, does not fit, or not yet (nothing entered after sewing).

## In practice

1. **Before cutting:** find the cover, check that it says *approved* or *produced* and that
   the DXF is there. If it says the DXF waits for (re)approval, do not cut: ask an approver to
   look at the Desk card first (the line links it).
2. **Cut the revision shown**, with the cutting list beside you.
3. **After sewing:** measure with the check list, then enter the sizes and **Fits** / **Does
   not fit** on the Desk card (**After sewing ▾ → Measured…**). The Workshop page then shows the
   result on that cover's line.
4. **The owner** can filter on *does not fit* to see which covers need a correction, and on
   *not yet* to see which sewn covers have not been measured.
