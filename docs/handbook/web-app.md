# The studio (the web app)

Everything the `cover` command does, in the browser: upload a 3D file or a drawing, look at the
furniture, the cover and the pieces in 3D, change a cover's settings and try them, look at the
flat patterns and the size drawing, and download `cut.dxf` for the cutting table. Plus the Desk,
the shop's work, the prices and the settings.

## Open it

The studio runs at **https://covers.suns.nu**; everyone logs in with their own account (see
[admin.md](admin.md)). For the developer it also answers on the server itself at
`localhost:8080`; from a laptop with Tailscale on:

```
ssh -L 8080:localhost:8080 dev@cover-server
```

then **http://localhost:8080** in the browser (see [server.md](server.md)).

## The pages, along the map

The four sections and their pages, with who sees what, the search, the theme button and every
address: [navigation.md](navigation.md). In short:

- **Work → Desk**: approve or reject covers and arrangements ([desk.md](desk.md)).
- **Work → Questions**: the owner's and the workshop's questions ([desk.md](desk.md)).
- **Work → Workshop**: what the Desk approved or marked produced, with the files and the fit
  ([workshop.md](workshop.md)).
- **Covers → All covers**: every model and its cover, as a table or as cards
  ([catalogue.md](catalogue.md)).
- **Covers → Arrangements**: catalogue products put together (a sofa with a chaise longue)
  under one cover ([arrangements.md](arrangements.md)).
- **Covers → New cover**: the three uploads (below).
- **Covers → Learning**: your reference pairs and their results ([learning.md](learning.md)).
- **Covers → Product list**: the workshop's product list ([desk.md](desk.md)).
- **Shop**: orders, requests (and matches), business customers, the website
  ([admin.md](admin.md), [webshop.md](webshop.md), [b2b.md](b2b.md)).
- **Settings** (admins; editors see Prices & costs): everything that is set once, the prices
  and costs among them ([admin.md](admin.md), [prices.md](prices.md)).

## Covers → New cover

Three uploads on one page (`#/covers/new`, editors and admins):

- **A 3D file** (STEP, IGES, STL, OBJ, PLY, GLB). Choose the **units** and which way is **up**
  if the file does not say (the Blocchi STEP: units m, up y). Everything then runs by itself; a
  big model takes a few minutes. More about the import: [importing.md](importing.md).
- **A drawing (PDF)**, as a new drawing cover. The program reads the drawing itself (the views,
  the sizes by their arrows, the number of air vents) and builds the cover in about 10 seconds.
  When it is not sure, it builds nothing and says why; such a drawing waits at the Desk for a
  person (ADR-081).
- **Reference pairs**: one zip with your own drawings and their 3D models, the same name per
  pair (`1.step` + `1.pdf`). The results are on Covers → Learning ([learning.md](learning.md)).
  A zip with only the product list goes to the product list.

### Complete product or cover surface only

Upload either the furniture or, when that is all there is, the cover surface itself (the
outside of the cover, open at the bottom). After the import the cover's page asks **Check: what
is this file?** (above the tabs) with the program's guess and its reasons. Look at the 3D view
and press **Yes** or **No**; only then the cover is calculated. For a cover surface the program
does not make a cover round anything: the surface is the cover, and only its pieces are drawn
(`hull.top: given`).

## A cover's page

Open a cover from All covers, the search, or a Desk card (`#/model/<id>/<tab>`).

**At the top:** the picture, the name and sizes, and a strip with the grade, the status, the
Desk status, the approval of the definitive drawing, a lock when the DXF waits for the Desk,
and "N changes since the run before". The buttons **Run** (run again), **Edit details** (the
pencil: category, family, status, tags, notes; see [catalogue.md](catalogue.md)) and **Desk
card** (the tray). Above the
tabs stay the approval of the definitive drawing ([admin.md](admin.md)), a running job (with the
time one step may take at most; a job the server left behind at a restart says **Interrupted**
and has **Run again**, ADR-129), a
rejection at the Desk and today's warnings. Under the head one summary row: the Desk, the fit,
the workshop (revision to cut, files) and the open questions about this cover (ADR-126).

**The seven tabs:**

- **3D:** the furniture, the cover surface (water spots red) and the pieces. Drag to turn,
  scroll to zoom, right-drag to move. The toolbar: **Show ▾** (the layers; air vents, vent
  sizes, overall dimensions), the quick toggles **Vents** and **Dimensions**, the switch
  **Design · Rain · Drape · Unfold** (with **Water** beside it on the drape), **Measure**
  ([measuring.md](measuring.md)), **Simulate ▾** (rain again, about a minute; drape again,
  about 40 minutes) and **Check list (PDF)**. The drape and the water: below.
- **Pieces:**
  - **Cut pieces:** what the machine cuts, the cutting list, the check list and the DXF
    download ([export.md](export.md)). The DXF of a drawing cover or an arrangement waits for
    the Desk's approval ([desk.md](desk.md)).
  - **Flat patterns:** the flat pieces and the stretch picture, with a table per piece
    ([patterns.md](patterns.md)).
  - **Size drawing:** `sizes.pdf`, with your reference cover's sizes where there is one.
  - **Files:** every file to download (a tab of its own until ADR-126).
- **Seams:** the seam editor. **Let the program add seams**: the program takes its own
  proposals round by round while the worst stretch goes down, and keeps them in
  `proposals.json`, apart from your seams. Delete that file (or use "Use automatic seams") to
  go back. Proposed seams: [seams.md](seams.md).
- **Adjust:** this cover's own settings, each with its explanation, the current value and where
  it comes from ("default" = the company value, "model" = this model's own, "changed" =
  changed here, not yet used). **Try without saving** runs with the changes but keeps nothing;
  **Save for this model** keeps them in the model's `cover.json` and runs again. "use default"
  takes a model's own value away again. Company defaults stay in `config/defaults.yaml`
  ([parameters.md](parameters.md)).
- **Compare:**
  - **Your drawing:** your drawing beside the calculated cover, with the sizes from your
    drawing next to the calculated ones ([learning.md](learning.md));
  - **Your reference:** upload a 3D model or PDF you know is right and compare (below);
  - **AI advice:** "Ask the AI" sends the cover as text to the AI (DeepSeek), which says how
    many pieces it should have, what is wrong, and suggests steps (skirt in one piece, no wall
    pieces, remove the program's seams, a calmer surface, a skirt height). "Apply" carries out
    one and calculates the cover again; nothing changes without your click.
- **History:**
  - **Approval & changes:** after a run, which settings changed and which pieces changed size
    by more than 1 mm ("since the run before");
  - **Revisions:** every saved cut; pick two to see what changed ([catalogue.md](catalogue.md));
  - **Warnings and log:** what the program reported.
- **Price & shop:** this cover's cost line by line, its B2C and B2B price, margin and where
  each comes from, its fixed price (admins change it in the draft and can publish from here),
  whether the shop offers it as an existing cover, its B2B companies, orders, quotes and match
  requests ([prices.md](prices.md)). Editors look; viewers see no prices.

## The drape simulation (3D view)

The drape simulation sews the cut pieces virtually and drops them over the furniture (and the
balloons and chairs of a table), with Newton's Style3D garment solver. It takes about 40
minutes for a sofa, in a queue of its own, so other work goes on meanwhile. Every new model
gets it by itself after its calculation; **Simulate ▾ → Drape again** runs it once more. The
result is kept with the model and in the nightly backup. **Drape** in the switch then plays
the fall and shows the cover as it lies.

The fall is followed by a short settling phase: the cover comes to rest, so what you see is the
shape it keeps, not a moment in the fall. Sewn seams bend less easily than the plain fabric, as
on a real cover.

- **Red** shows folds: there the piece has more fabric than the shape needs.
- The card below gives:
  - the fold area;
  - the tightest spot;
  - how far the top sags below the designed surface;
  - how much of the cover lies on the furniture.

**Design** in the switch shows the designed surface again. The fabric values are estimates
until the fabric has been measured.

## Water on the cover as it lies (heatmap)

After the drape simulation the rain falls on the cover as it really lies.

- In the 3D view, choose **Drape** in the switch, then switch **Water** on (beside it). The
  cover is coloured:
  - **sage**: water runs off;
  - **amber**: water streams past;
  - **orange**: flat, water stands;
  - **red**: a pond (darker is deeper).
- The card gives the number of ponds, the litres and the deepest point, and whether a pond
  keeps growing under its own weight.

The rain on the designed surface (**Rain** in the switch) stays, to compare.

## Your reference: compare the program with your own drawing or model

On a cover's page, **Compare → Your reference**, upload what you know is right:
- **a 3D model of the cover** (STEP, IGES, STL, OBJ, GLB). You get how far the program's cover
  lies from yours in mm, the share within ±5 mm, and a 3D view in colour: green within ±5 mm,
  sand where ours is roomier, red where it is tighter;
- **a PDF** (your drawing or pattern). You get which of its sizes are found in the program's
  pieces, the AI's list of differences, and lessons. Press **Accept** on a lesson and the AI
  follows it for every cover from then on.

Every comparison is kept, as material for improving the program.

**What the program did with your upload.** At the top of the tab, per upload, a report in plain
words with one verdict:
- **Your reference agrees with the program's cover**, **differs: see below**, or **a person must
  look** (the checks do not agree, or one could not be done).
- The steps, each marked ✓ (fine), ! (look at it), ✗ (failed) or · (for your information):
  1. **Received:** the file, its size, who uploaded it and when.
  2. **Read:** a 3D model with its triangles, the unit and up axis the program chose, and how far
     it was turned and moved to lie over the program's cover (never scaled or mirrored); a PDF
     with its pages and the sizes found on it.
  3. **Compared:** for a 3D model, the share within ±5 mm (it agrees from 90 %), the mean, 95 %
     and largest deviation, roomier and tighter, the sizes side by side; for a PDF, which sizes
     are found in the program's pattern and which are not.
  4. **Double check by two AIs:** for a PDF, Gemini looks at your drawing beside the program's
     cover, DeepSeek reads every word and number, and they check each other (when they disagree
     Gemini looks once more with DeepSeek's points). For a 3D model, DeepSeek says in plain
     words what the deviation means. Their answers are advice: when they disagree with the
     numbers, the verdict is "a person must look".
  5. **What changed in the program:** nothing by itself. The lessons the AI proposes wait for a
     person; the ones accepted for this model are listed with who and when.
- **Earlier uploads** are listed below the report (when, file, who, verdict); open one to read
  its steps.

## For the developer

```
make api-dev     # builds the pages, serves app and API on http://127.0.0.1:8080
make web-dev     # live-reloading pages on :5173 (with api-dev running)
make deploy      # the app in Docker on 127.0.0.1:8080 (data in ../data)
```

The live studio runs as the service `cover-web` from `~/releases/current`
([server.md](server.md)), with the data in `~/cover-data` (its `models` is the repository's
`models/` folder, so the command line and the web app share models).
