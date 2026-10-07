# The web app

Everything the `cover` command does, in the browser: upload a 3D file, look at the furniture,
the cover and the panels in 3D, change settings and try them, look at the patterns and the size
drawing, and download `cut.dxf` for the cutting table.

## Open it

The app runs on the server. Until the Cloudflare address is set up (question 14 in
`docs/QUESTIONS.md`), open it through SSH. On your laptop:

```
ssh -L 8080:localhost:8080 dev@168.119.50.82
```

and leave that window open. Then go to **http://localhost:8080** in the browser.

## What is where

- **Catalogue** (top bar): every product as a card with its photo, a 3D picture of its cover,
  the grade, size, number of pieces, worst stretch and fabric. Search, filter by grade, family
  and tag, sort. Click a card to open the product.
- **Arrangements** (top bar): put catalogue products together (a sofa with a chaise longue)
  and build one cover over the whole. See [arrangements.md](arrangements.md).

- **Models:** all models with how far the cover is (**ready**: every piece within the stretch
  limit, smooth edges, seams matching within 5 mm; **to check**: hover to see why; **failed**),
  their progress (five dots: import, cover, seams, patterns, cut
  pieces), the number of panels, the worst stretch and the number of warnings. Upload a new 3D
  file at the top; choose the units and which way is up if the file does not say (the Blocchi
  STEP: units m, up y). Everything then runs by itself; a big model takes a few minutes.
- **A model:**
  - **3D:** switch the furniture, the cover surface (water spots red) and the panels on and
    off. Drag to turn, scroll to zoom, right-drag to move.
  - **Let the program add seams** (Seams tab): the program takes its own proposals round by
    round while the worst stretch goes down, and keeps them in `proposals.json`, apart from
    your seams. Delete that file (or use "Use automatic seams") to go back.
  - **AI advice:** "Ask the AI" sends the cover as text to the AI (DeepSeek), which says how
    many pieces it should have, what is wrong, and suggests steps (skirt in one piece, no wall
    pieces, remove the program's seams, a calmer surface, a skirt height). "Apply" carries out
    one and calculates the cover again; nothing changes without your click.
  - **Patterns:** the flat pieces and the stretch picture, with a table per piece.
  - **Size drawing:** `sizes.pdf`, with your reference cover's sizes where there is one.
  - **Cut pieces:** what the machine cuts, the cutting list, and the DXF download.
  - **Settings:** every setting with its explanation, the current value and where it comes
    from ("default" = the company value, "model" = this model's own, "changed" = changed here,
    not yet used). **Try without saving** runs with the changes but keeps nothing;
    **Save for this model** keeps them in the model's `cover.json` and runs again. "use
    default" takes a model's own value away again. Company defaults stay in
    `config/defaults.yaml`.
  - After a run, the line "Since the run before" shows which settings changed and which pieces
    changed size by more than 1 mm.
  - **Downloads:** every file, **Warnings and log:** what the program reported.

## For the developer

```
make api-dev     # builds the pages, serves app and API on http://127.0.0.1:8080
make web-dev     # live-reloading pages on :5173 (with api-dev running)
make deploy      # the app in Docker on 127.0.0.1:8080 (data in ../data)
```

On this server the app runs in the tmux session `cover`, window `web`, with the data in
`~/cover-data` (its `models` is the repository's `models/` folder, so the command line and the
web app share models).

## Complete product or cover surface only

Upload either the furniture or, when that is all there is, the cover surface itself (the outside
of the cover, open at the bottom). After the import the model page asks **Check: what is this
file?** with the program's guess and its reasons. Look at the 3D view and press **Yes** or
**No**; only then the cover is calculated. For a cover surface the program does not make a cover
round anything: the surface is the cover, and only its pieces are drawn (`hull.top: given`).
