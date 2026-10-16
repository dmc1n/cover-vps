# How Cover Studio works

Cover Studio is the S2DIO × SUNS system that turns a piece of outdoor furniture into the
cutting patterns for its cover. You give it a 3D model of the furniture (or one of our earlier
cover drawings); it gives back the pieces to cut, ready for the CNC cutting table, with a
cutting list and a size drawing. It runs at **covers.suns.nu**.

## The studio in four sections

The dark bar at the top has four sections; the light bar under it shows the pages of the
section you are in. Every page has its own address, so a link in a mail opens exactly that
page.

1. **Work:** what waits for a person.
  - **Desk:** approve or reject covers and arrangements. The queue on the left, the card on the
    right with four tabs (Check, Pieces & revisions, Correct this cover, History). The bar at
    the bottom: Approve, Reject, Comment, After sewing (Produced, Measured, Fits, Does not
    fit), Undo.
  - **Questions:** the owner's and the workshop's questions, answered in the studio.
  - **Workshop:** every cover the Desk approved or marked produced, with its files (cutting
    list, size drawing, check list, cut pieces, and the DXF once the approval allows it), the
    revision to cut, and how it fitted. Read only: deciding stays on the Desk card.
2. **Covers:** every cover and how it is made.
  - **All covers:** every model and its cover, as a **Table** or as **Cards**, with one filter
    row (search, category, cover grade, status, tag, sort). Tick covers to run steps for many
    at once.
  - **Arrangements:** furniture placed together under one cover.
  - **New cover:** a 3D file, a drawing (PDF), or a zip with your own drawings and their 3D
    models.
  - **Learning:** your drawings beside the covers the program made from them.
  - **Product list:** the workshop's product list (Excel), linked to the drawings.
3. **Shop:** orders, requests (from the configurator, and which existing cover fits), business
   customers and the website's texts (Website, with AI). Mostly for admins;
   editors may draft the website.
4. **Settings** (admins; editors see the price tabs): one page with tabs on the left for
   everything that is set once: the company and the shop, selling (matching, B2B terms), prices
   and costs (materials, labour, the exchange rate, the price rules, publish and versions, a
   price list from Excel), users and rights, the Desk's rules and the cover defaults, mail, the
   website and API keys, AI and spending (with the photo test), the system and its logs.

Everything about **one cover** — its pieces, its cost and prices, its place in the shop, its
orders, its Desk status, fit and questions — is on that cover's own page (tab *Price & shop*
for the money and the shop).

## The right side of the bar

- **Search** finds everything: covers (name, tag, note, family), Desk codes and product names,
  questions (title or number), and for admins orders (number, customer, product). **Ctrl+K**
  (**Cmd+K** on a Mac) jumps to it; the arrow keys and **Enter** open a hit; **Escape** closes
  the list.
- **Guide** opens this page.
- **The theme button** left of your name switches between As the computer (half sun, half moon), Light (sun)
  and Dark (☾). It is remembered in that browser only. Drawings, flat patterns and pictures
  stay on white, and the 3D view keeps its light stage.
- **Your name** opens *My account* (your password); the arrow beside it is **Log out**.
- **The (i)** beside a title or a setting holds its explanation: click or tap it, or Tab to it
  and press Enter (ADR-130).

## Where you start

- **Approvers** start on Work → Desk.
- **An admin** starts where he was last.
- **Everyone else** starts on Covers → All covers.

These start pages are still to be confirmed with the owner.

## A cover's page

At the top: the picture, the sizes and a strip with the grade, the status, the Desk status and
the approval. Then seven tabs:
- **3D:** the furniture and the cover. The toolbar has Show (layers, vents, dimensions), quick
  Vents and Dimensions, the switch Design, Rain, Drape, Unfold, then Measure, Simulate and the
  Check list.
- **Pieces:** the cut pieces with the DXF and the lists, the flat patterns, the size drawing.
- **Seams:** the seam editor.
- **Adjust:** this cover's own settings; try them without saving, or save them for this cover.
- **Compare:** your drawing, your reference, the AI's advice.
- **History:** approval and changes, revisions, warnings and the log.
- **Files:** every file to download.

## From furniture to cover, in six steps

1. **Upload** (Covers → New cover). A 3D model in almost any format (STEP, OBJ, GLB, STL, …).
   The system checks whether it is the furniture itself or an already drawn cover surface, and
   asks you to confirm.
2. **Cover surface.** It builds the shape the fabric will take. A box cover with a sloping top
   for most furniture: water must always run off, so there are no flat areas and no hollows.
   Tables get balloons under the cover and room for the chairs beside them.
3. **Seams and pieces.** The surface is divided into as few pieces as possible, with smooth
   seam lines. No piece is wider than the 150 cm roll or longer than 3 m.
4. **Flat patterns.** Every piece is laid flat with its true lengths. The two sides of every
   seam are checked to be equally long, and any stretch is measured.
5. **Finishing.** The seam allowances are added, along with the hem with its bottom drawcord
   (tables also get one in the middle), and the air vents: one per full metre of every side,
   each with a logo. Marks and labels for sewing go on the pen layer, not cut.
6. **Exports.** `cut.dxf` for the cutting table, plus a cutting list and a size drawing as PDF
   with both logos.

## How we know a cover is right

- **Checks on every cover:**
  - the cover is complete;
  - the furniture is inside;
  - tables have balloons and chair space;
  - a symmetric piece has a symmetric cover;
  - water runs off;
  - the cover has few pieces.
- **A second opinion by AI (DeepSeek)** on every cover, with the picture. Where the AI and the
  checks disagree, a person looks.
- **Rain simulation** in the 3D view (Rain in the switch): where water would stand or run,
  shown on the cover.
- **Air vents** in the 3D view (the Vents toggle, remembered in your browser): every air vent
  where it is cut in the cover, the opening dark with a red frame, its hood above it. They are
  the same vents as on the cutting list (after each export). Show ▾ → **Logo** adds each
  vent's logo where it sits on the sewn hood: centred along the bottom of the vent, upright
  (owner, 16 Oct 2026), the cutting file's own frame (ADR-146).
- **The Desk.** Rens, Wout and the other approvers approve or reject every drawing cover and
  arrangement. The cutting table's DXF of such a cover is only available once its current cut
  is approved; a change after the approval puts it back at the Desk.
- **Approval of the definitive drawing.** Only users with approval rights can approve it. The
  approved PDFs are stamped. Any change after approval cancels it, so production always cuts
  what was approved. (Whether this and the Desk's approval become one step is still open with
  the owner.)
- **After sewing.** The workshop measures the sewn cover against the check list and enters the
  sizes and Fits or Does not fit on the Desk card; the Workshop page shows the result.

## Covers from your drawings

On **Covers → New cover**, choose the drawing (PDF). The program reads the drawing's own lines
and pictures, not the AI:
- the views, with their exact outlines;
- every size, through its two arrows;
- the number of air vents ("4 Air Pocket", or the arrows from "Air Vents").

From the top view and the side or front view it builds the cover as a CAD drawer would, in
about 10 seconds. It places the vents by your rule and splits the pieces to fit the roll. It
checks the result against the drawing's 3D view. Then Gemini (it looks at the drawing) and
DeepSeek (it reads all words and numbers) each judge the cover and check each other. When they
disagree, a person looks.

When the program is not sure, it builds nothing and says why: no top view, no size arrows, or
the shape does not match the 3D view on the drawing. Such a drawing waits at the Desk for a
person.

Where the program made the seams itself (free shapes), neighbouring pieces without a real
crease are joined into one, as long as the piece still lies flat and fits the roll (S43: from
37 pieces to 9). Covers whose seams follow the drawing keep them.

A drawing cover is only replaced when the new one fits the 3D view better **and** both AIs find
it better. It then becomes a new revision of the same cover, so nothing is lost.

## Only what changed is calculated

When you save a setting or press **Run** (run again), every step checks whether anything it depends
on changed. A step with no changes skips itself, so a vent setting recalculates only the
export, in seconds. The size drawing and the air vents in 3D are made when you open them.

Two things are not run automatically and have their own button: the drape check (the cover
falling over the furniture, with rain) and the AI's choice of pieces or balloons. The rule
decides those by default.

## Unfold: the pieces flat, and where the fabric goes

In the 3D view, Unfold in the switch plays the cover coming apart and lying flat on a table. On
the table, each piece shows:
- its net outline (the sewn size) and its cut outline (dashed);
- the seam allowance (orange), the hem (blue) and the vent openings;
- its net and cut size in cm.

Below the view, a table shows where the fabric goes: the surface, the seam allowances, the hem,
the vent hoods, and what is left on the roll.

## Your account

- You log in with your user name and password. The first time on a device you also get a
  6-digit code by mail.
- Tick *Remember this device* and it is trusted for 14 days.
- **Roles:**
  - *viewer:* looks and downloads;
  - *editor:* also uploads, calculates and changes a cover's settings;
  - *admin:* also manages users, Settings, the shop and the prices;
  - *may approve:* approves definitive drawings.
- There is no separate workshop login yet; the workshop uses one of these roles.
- Change your password under your name (top right), *My account*.

## Safe and recoverable

The site is only reachable over https. Logins are protected by a code by mail, and the server
can only be maintained over a private network. Everything is backed up every night, and the
server reports problems by mail itself. Every version that goes live has a number, so an
earlier version is back within seconds if needed.

## Still in progress

The first cover cut from these patterns is still to be made and measured on the furniture.
Several values (seam allowance, hem, vent size) are best guesses until then. Curved and
U-shaped drawings are being added. The studio's language stays English for now (an open
question for the owner).

*Questions: Rick, rick@s2dio.industries.*
