# Open questions for the owner and the team

One list, kept current. Each question says what the program does meanwhile (the default), so
work does not wait. Answers go into `config/defaults.yaml` (one line each) or a model's
`cover.json`, and are recorded in `docs/DECISIONS.md`.

Last updated: 2026-09-30 (evening, owner offline).

## Most important

1. **Is the Blocchi 3D file the sofa your cover fits?** The model is 207 × 170 cm from above
   and 91 cm high; your cover is 197 × 192 cm and 88 cm high, with a hem 38 cm longer. Please
   measure the real sofa: length and depth from above, the length of the straight end, total
   height, height of the top edge at the front middle and at both ends, seat height at the
   front. *Meanwhile:* the Blocchi is calculated from the 3D file as it is.
2. **Skirt height:** now always one height all round (your rule). Should the default be
   automatic (just below the lowest point of the top edge; 23.6 cm on the Blocchi, 41 cm on the
   test chair) or a fixed company height (for example 40 cm for lounge furniture)? And for the
   Blocchi: 40.6 cm as on your cover? *Meanwhile:* automatic; set per model with
   `seams.skirt_height_mm`.
3. **Wall pieces:** where the top edge stands higher than the skirt (the back and sides of a
   chair, the middle of the Blocchi front), the upright part between is now a separate piece
   ("wall"), so the top does not have to wrap over the edge. That means one more seam there. Is
   that how you would make it, or would you rather have the skirt piece go up to the edge on
   that side (a skirt piece with a sloping top edge, still a straight line)? *Meanwhile:* wall
   pieces, from 2 cm higher over at least 30 cm.
4. **Air vents on a low skirt:** a vent needs 5 + 22 cm plus the seam allowance. On the Blocchi
   the automatic skirt is 23.6 cm, too low. Should the vent then cross into the piece above, or
   should the skirt be at least 30 cm high whenever there are vents? *Meanwhile:* a warning.

## Making the cover (M5)

5. **Stitched seams:** seam allowance 15 mm? On both pieces of a seam, or only one? Which seam
   type (flat-felled, overlocked and topstitched, ...)? *Meanwhile:* 15 mm on both pieces.
6. **Hem:** drawcord channel, elastic, or plain? Allowance 50 mm? Hem 5 cm above the floor?
   Where do the cord exits go (2, spread evenly)? *Meanwhile:* drawcord channel, 50 mm, 5 cm,
   2 pen marks.
7. **Air vent pieces:** the hood (extra fabric over the plastic insert): how deep, and what
   shape? The membrane inside: same size as the opening plus the allowance? Do vents go on every
   side (front too), and how far from a vertical seam at least? *Meanwhile:* hood 80 mm deep,
   membrane = opening + allowance, all sides, at least 10 cm from a seam, spread evenly.
8. **Longest piece in one go:** is 3 m right for a skirt piece? *Meanwhile:* 3 m.
9. **Fabric and roll:** your drawing says WeatherMax; the program assumes 100 % acrylic on a
   150 cm roll (148 cm usable). Which fabric and roll width? *Meanwhile:* acrylic, 150 cm.

## The machine (before the first CNC cut)

10. **The CNC table:** make and model, and the M0 test sheets
    (`docs/reports/M0-machine-checklist.md`): which layer names, text or stroked letters, arcs
    or polylines does it take? *Meanwhile:* layers CUT and PEN, text as TEXT, polylines.
11. **First CNC cut:** which piece and which fabric? A small piece first (the chair) is the
    quickest check of sizes.

## Water and tents

12. **Minimum slope** for water to run off (5° assumed), and the **balloon or frame** size for
    tables. *Meanwhile:* 5°, balloon automatic.
13. The Blocchi: the flat band on top of the back cushions holds water (about 0.11 m²) on the 3D
    model. Does your cover have that band flat, or does it slope?

## The web app (M6)

14. **Cloudflare:** an account for the tunnel and the login (Cloudflare Access), and who gets
    access (e-mail addresses or your company domain). *Meanwhile:* the app runs on the server,
    reachable over SSH only.
15. **Who uses it:** only you, or also colleagues? Do they need their own logins?

## Families and catalogue (M7)

16. **Families:** which furniture families do you have (lounge sofas, dining chairs, sun
    loungers, tables, ...) and a few models of each as 3D files?

## Fabric test (M8)

17. **Swatch test:** can you cut and weld the swatches from `docs/CALIBRATION.md` when we get
    there?
