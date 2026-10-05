# How Cover Studio works

Cover Studio is the S2DIO × SUNS system that turns a piece of outdoor furniture into the
cutting patterns for its cover. You give it a 3D model of the furniture (or one of our earlier
cover drawings); it gives back the pieces to cut, ready for the CNC cutting table, with a
cutting list and a size drawing. It runs at **covers.suns.nu**.

## From furniture to cover, in six steps

1. **Upload.** A 3D model in almost any format (STEP, OBJ, GLB, STL, …). The system checks
   whether it is the furniture itself or an already drawn cover surface, and asks you to
   confirm.
2. **Cover surface.** It builds the shape the fabric will take. A box cover with a sloping top
   for most furniture: water must always run off, so there are no flat areas and no hollows.
   Tables get balloons under the cover and room for the chairs beside them.
3. **Seams and pieces.** The surface is divided into as few pieces as possible, with smooth seam
   lines. No piece is wider than the 150 cm roll or longer than 3 m.
4. **Flat patterns.** Every piece is laid flat with its true lengths. The two sides of every seam
   are checked to be equally long, and any stretch is measured.
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
- **Rain simulation** in the 3D view (the *Rain* button): where water would stand or run,
  shown on the cover.
- **Show air vents** in the 3D view (a tick box, remembered in your browser): every air vent
  where it is cut in the cover, the opening dark with a red frame, its hood above it. They are
  the same vents as on the cutting list (after each export).
- **Approval.** Only users with approval rights can approve the definitive drawing. The approved
  PDFs are stamped. Any change after approval cancels it, so production always cuts what was
  approved.

## Covers from your drawings (ADR-072, ADR-075)

The program reads the drawing's own lines and pictures, not the AI:
- the views, with their exact outlines;
- every size, through its two arrows;
- the number of air vents ("4 Air Pocket", or the arrows from "Air Vents").

From the top view and the side or front view it builds the cover as a CAD drawer would. It
checks the result against the drawing's 3D view. Then Gemini (it looks at the drawing) and
DeepSeek (it reads all words and numbers) each judge the cover and check each other. When they
disagree, a person looks.

Where the program made the seams itself (free shapes), neighbouring pieces without a real
crease are joined into one, as long as the piece still lies flat and fits the roll (S43: from 37
pieces to 9). Covers whose seams follow the drawing keep them.

A drawing cover is only replaced when the new one fits the 3D view better **and** both AIs
find it better. It then becomes a new revision of the same cover, so nothing is lost.

## What you find where

- **Models:** every model with its state. Open one for the 3D view, the pieces, the files and
  the approval.
- **Catalogue:** the SUNS collection, sorted in the categories of hello-suns.com.
- **Learning:** our 115 earlier cover drawings, rebuilt by the system, to compare and learn from.
- **Search** in the header finds any model by name.

## Your account

- You log in with your user name and password. The first time on a device you also get a
  6-digit code by mail.
- Tick *Remember this device* and it is trusted for 14 days.
- **Roles:**
  - *viewer:* looks and downloads;
  - *editor:* also uploads, calculates and changes settings;
  - *admin:* also manages users;
  - *may approve:* approves definitive drawings.
- Change your password under your name (top right) → *My account*.

## Safe and recoverable

The site is only reachable over https. Logins are protected by a code by mail, and the server
can only be maintained over a private network. Everything is backed up every night, and the
server reports problems by mail itself. Every version that goes live has a number, so an
earlier version is back within seconds if needed.

## Still in progress

The first cover cut from these patterns is still to be made and measured on the furniture.
Several values (seam allowance, hem, vent size) are best guesses until then. Curved and
U-shaped drawings are being added.

*Questions: Rick, rick@s2dio.industries.*
