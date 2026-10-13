# The Workshop page: what to cut, and how it fitted

**Work → Workshop** (`#/work/workshop`, ADR-124, ADR-128). For the workshop and the owner: one list of
every cover the Desk has **approved** or marked **produced**, with the files to cut and sew it
and what we know about how it fitted.

**Editors and admins can Send to production here.** Approving, marking a cover produced,
and entering the measured sizes and Fits / Does not fit stay on the cover's Desk card, under
**After sewing ▾** (see [desk.md](desk.md) and [measuring.md](measuring.md)).

## Who sees it

Every studio role can open the Workshop page. The **workshop** login starts here. It sees
Work only: Desk, Questions and Workshop. It can answer its own questions and download files
for approved covers. On a Desk card it can **Comment**, with pictures, and enter **Fits /
Does not fit / Measured…** under **After sewing ▾**. It cannot approve, reject, mark Produced,
Undo, correct covers, calculate, start the AI or Send to production. It sees no prices,
e-mail addresses or Settings. A cover's own page says **Not for your account**.

The customers' fit answers are shown to editors and admins only; viewers and the workshop
login see a note in their place.

The **Orders** block at the top lists orders **waiting for production** and **in production**,
without prices. Paid orders and B2B orders on account wait for the studio's click. Editors
and admins press **Send to production** here, or an admin does it on **Shop → Orders**.
The cover then goes to the Desk as an order, first in the queue. The cutting-table DXF
follows the Desk's approval. A catalogue cover whose current cut is already approved is
ready to cut at once.

## What each line shows

- **The picture and the code** of the cover.
- **The status:** *approved* or *produced*, by whom and when.
- **The files:**
  - the **cutting list** (PDF);
  - the **size drawing** (PDF);
  - the **check list** (PDF), to measure the sewn cover against
    ([measuring.md](measuring.md));
  - the **cut pieces** as a picture (SVG);
  - the **cutting-table DXF**, but only when the approval allows it. The DXF belongs to the
    approved cutting file (ADR-079, ADR-115, ADR-120, ADR-128): when the cover was built again after
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

Beside the ordinary **Size drawing** and **Cutting list**, a line shows **Approved size
drawing** and **Approved cutting list**: the copies the Desk's approval stamped with
`APPROVED <name> <date> revision <n>` on every page. They go away when a change invalidates
the approval (and come back with the next approval).

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
