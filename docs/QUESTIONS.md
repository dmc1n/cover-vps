# Open questions for the owner and the team

One list, kept current. Each question says what the program does meanwhile (the default), so
work does not wait. Answers go into `config/defaults.yaml` (one line each) or a model's
`cover.json`, and are recorded in `docs/DECISIONS.md`.

Last updated: 2026-10-01. Answered today: 22 (balloons). New: 24–27 (balloons under table covers).

## Most important

1. **Is the Blocchi 3D file the sofa your cover fits?** *New:* the SUNS model on 3D Warehouse
   (GLB) fits your cover much better than the STEP we had: top of the cover 88.1 cm above the
   floor (your 88.0), depth 192.8 cm (192.4), hem 659 cm (668). Shall we use the SUNS models
   from now on? The earlier note, for the record: The model is 207 × 170 cm from above
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

## The SUNS catalogue (new, 1 October)

18. **Seam layout per family:** sofas and chairs need seams along their folds (the top
    stretches 8–35 % in one piece). For each kind (lounge sofa, lounge chair, dining chair,
    lounger), where do you put the seams? For example "a band along the top of the back, 30 cm
    wide; the arm tops as separate pieces; a seam along the front edge of the seat". One
    drawing per family, like your Blocchi drawing, is enough. *Meanwhile:* the program's own
    proposals (`cover improve`), which halve the stretch but do not reach 2 %.
19. **Round tables of 150–170 cm** are wider than the roll (148 cm) in one piece. Split along
    the diameter, or a round middle piece with a ring round it? *Meanwhile:* reported.
20. **44 SUNS products need a 3D Warehouse login** to download (list in
    `~/suns/needs_login.txt` on the server). A login for the program, or will you download them
    once (the GLB, "Download → glTF")?
21. **Sets** (99 entries: lounge sets, dining sets): a cover per product in the set (the
    products are also in the catalogue on their own), or covers for whole sets too?
    *Meanwhile:* single products only.
22. *Answered 1 Oct: balloons, under every table cover; the owner uploads the 3D model of the
    balloons and the AI proposes how many per table (questions 24–27).* **Tables: balloon or frame?** A ridge frame (a gable-roof cover) is now possible
    (`hull.support: frame`). On the test tables the balloon was as good or better. Which do you
    use? *Meanwhile:* balloon.
23. **Vents on low skirts** (question 4 again, with numbers): on almost all SUNS seating the
    skirt is 15–24 cm and the vents (28.5 cm with allowance) do not fit. Raise the skirt to at
    least 30 cm when there are vents, put vents on the back only, or make them smaller?


## Balloons under table covers (new, 1 October)

24. *Answered: one size, as the model.* **Balloon sizes:** one size or several? Diameter and height when inflated (the 3D model will
    show the shape; is it at the pressure you use)?
25. *Answered: a 340 cm table usually gets 3 to 4.* **Placement:** is there a largest distance between balloons, or from a balloon to the table
    edge, before the fabric sags and holds water? Do they lie loose on the table top or are they
    fixed (straps, a pocket sewn into the cover)?
26. *Answered: between balloons the fabric runs straight; the slope is round the balloons.* **Slope:** is 5° enough for the fabric between balloons, or what slope do you see on a good
    cover?
27. *Answered: every table gets at least one balloon.* **Round and square tables:** always one balloon in the middle for small tables (up to which
    size)?

## From the owner's 115 drawings (new, 1 October; docs/reports/DRAWINGS-2026-10-01.md)

28. *Explained to the owner, 1 Oct; waiting for the answer.* **Bottom band on box covers:** your drawings have a separate band at the bottom (17 to 20
    cm). Should the box covers get one too (one more piece, a straight seam all round)?
29. *Answered 1 Oct: one per metre, at least one on each side (built).* **Air pockets:** your drawings place about one per 170 cm, high on the cover; the rule you
    gave on 30 September is one per metre, 5 cm above the bottom edge. Which one is right now?
30. *Answered 1 Oct: the top may be several pieces; no roll wider than 150 cm.* **Round tables of 240 cm** (R1) are wider than the 150 cm roll: is the top disc made of
    several pieces, or is that fabric on a wider roll?

## Chairs under table covers (new, 1 October)

31. *Answered 1 Oct: the same as dining chairs, 87 cm; a low dining table gets the same cover as a dining table.* **Chair height for low dining tables** (68 to 70 cm, e.g. Basta low dining): how high do
    the chairs reach? *Meanwhile:* 85 cm.
32. *Answered 1 Oct: 123 cm, as R5, R6, R10.* **Chair height for low bar tables** (95 to 101 cm, e.g. Basta low bar): how high? *Meanwhile:*
    110 cm.
33. *Answered 1 Oct: yes, 87 cm for every dining table.* **Dining tables outside 74 to 77 cm** (Monte Vari 81 cm in the 3D file, Savona and Sorolo
    71 to 73 cm): also 87 cm high? *Meanwhile:* yes, every table named dining table.
34. *Answered 1 Oct: yes, chair space all round (R1 is for a 170 cm table).* **Round dining tables:** chairs stand all round a round table. Chair space of 33 cm all
    round (a 174 cm table gets a 240 cm cover, like your R1)?
35. *Answered 1 Oct: a short side must have a vent (built: centred, closer to the seams).*
    **Short sides:** a 34 cm side has no room for a vent with 10 cm from each seam.
28. *Answered 1 Oct: the band at the bottom is the strap or rope round the edge that the
    customer tightens.* See the follow-up in the reply: does the hem channel do the same?

## For the morning of 2 October (collected overnight)

36. **Logo on the air vents:** how big is the logo, and where on the hood? *Meanwhile:* a pen
    frame of 12 × 4 cm marked LOGO in the middle of the hood's front.
37. **Mirrored drawings** (L1 & L5, L2 & L6, …): one file stands for a cover and its mirror
    image. Should the program make the mirrored cover as a second model with its own cut file?
38. **The 3D files of your drawings:** the drawings were made in a CAD program. Do you still have
    the 3D files (STEP)? Then every cover can be taken over exactly, including the 17 curved and
    special ones the program cannot rebuild from the views (S24, S44, C26, …).
39. **Mail server:** for invitations, password links, approval requests and alerts we need an
    SMTP account (server, port, user name, password, sender address, for example
    noreply@s2dio.industries). Enter it on the admin page (Mail and address) or send it to me.
40. **Backup outside the server:** the nightly backup is on the same disk as the data. Where
    should a second copy go (a Hetzner Storage Box, Cloudflare R2, your own NAS)?
41. **SSH keys:** everyone, also root, logs in to the server with a password. Make an SSH key
    for each of you (I explain how) so passwords and root login can be switched off.
42. **Reboot:** a new kernel waits; the server needs one reboot (about a minute; the app and
    https start by themselves). When suits you?
    **Answered 2 Oct 2026:** rebooted at 14:30 on the owner's word; everything came back.
43. **The other users** (Rens, Patrick, Ed, Marcel, Jeffery, Kevin, Willard): e-mail addresses,
    role (viewer, editor, admin), and who may approve.
44. **Releases:** from tomorrow every version that goes live gets a number (v1.0, v1.1, …) and
    going back is one command (docs/handbook/server.md). Agree?
    **Answered 2 Oct 2026:** yes; v1.0.0 is live (ADR-053).
41b. **SSH over the internet** is closed since 2 Oct 2026 (Tailscale only), so the password
    risk of 41 is much smaller; switching off passwords and root login is still advised.
45. **Very low tables** (the Conico small, 25 cm): an air vent of at least 10 cm does not fit
    in the side of the cover. Leave the vent out, put it in the top, or make it smaller there?
46. **Round tables** (Sorrento, the Conico tables): their cover is now a box with a roof over a
    balloon. Should a round table get a round cover (a band and a round top, as your R
    drawings), or is the box fine?
47. **One piece with a fold instead of a seam on top** (docs/plans/fewer-top-pieces.md): where
    neighbouring faces of the top lie flat together on the roll, cut them as one piece with a
    fold line in pen, so there is no seam on top. Should this be the default for every cover, or
    only where you ask (as now for the Lucia)? As default it also joins the Kota's back strip to
    its slope.
    **Answered 2 Oct 2026:** only where the owner asks (`seams.fold_merge` off by default, on per
    model).
48. **Minimum piece width:** no piece narrower than 10 cm (now there are pieces of 3 to 8 cm on
    21 SUNS models). Is 10 cm right?
    **Answered 2 Oct 2026:** to be learned from our analyses; 10 cm for now (marked to confirm).
49. **Roll width:** Sunbrella Coverlast is 152 cm wide (Dickson). The program uses 148 cm
    usable (`roll.usable_width_mm`, from the 150 cm you named earlier). Is 148 still right, or
    150 of the 152?
50. **The hem cord in the drape:** is the bottom drawcord pulled tight when the cover is on (the
    bottom edge pulled in under the furniture), or does the cover hang loose? The drape
    simulation leaves it loose for now.
51. **Coverlast's stretch:** Dickson publishes no elongation. The rest of the fabric data is
    known: 250 g/m², 152 cm wide, tensile 195/104 daN per 5 cm. Can Vyva or Dickson give the
    elongation at a working load (for example at 10 % of the break load), lengthways and
    across? Otherwise the 1 kg strip test on Monday.
52. **Webshop prices** (`quote.*`, now placeholders): the purchase price of Coverlast per metre,
    sewing minutes (per cover, per piece, per metre of seam, per vent) and the hourly rate, the
    parts (vent, cord per metre, balloon), and the markup. Until then the price shows as
    "indicative".
53. **Which webshop** (Shopify, WooCommerce, …) and its address(es), for the iframe and an API
    key.
54. **Colours** to offer in the configurator (now Charcoal, Navy, Light Grey, Taupe).
55. **Who gets the customers' requests** (now rick@s2dio.industries)?
56. **Should customers see the pieces and the fabric**, or only the 3D view and the price?

57. **Allowed size band for an existing cover** (docs/plans/hosting-scale-and-matching.md): how
    much larger than the furniture may it be and still count as a good fit (e.g. +4 cm in
    length and depth, +3 cm in height)? Is anything smaller ever acceptable?
58. **Off-the-shelf covers:** which of the 302 are sold as they are, at what price, and with
    what delivery time against custom?
59. **The shop's domain on Cloudflare** (DNS) and an API token for Pages, Workers, KV and R2.
    Found on 5 Oct: suns.nu's DNS is at Bunny (coco/kiki.bunny.net), registered at my.host;
    only covers.suns.nu is visible (no website or mail on suns.nu itself). Choose:
    (a) move suns.nu's name servers to Cloudflare (first export every record from Bunny DNS);
    (b) a separate shop domain, fully on Cloudflare;
    (c) stay on Bunny (Bunny also has a CDN and edge scripts).
    The shop's name and domain (question 53) decide which.
60. **GPU on demand:** Modal or RunPod, and a monthly cap (e.g. €50)?
61. **The fit question** by mail two weeks after delivery, with an optional photo: OK?
62. **The website's brand name and domain** (ADR-066): the website is another brand on its own
    domain, on Cloudflare. Which name and domain, and is there a Cloudflare account? I need an
    API token with Workers (edit) for that account, and the domain added as a zone.
63. **SUNS names on the other website:** the match shows covers from the SUNS range by name
    ("SUNS 2 Seater Evora alu fits you for 100 %"). Keep the names, show them as "our model
    for …", or show only the sizes?
    **Answered (owner, 5 Oct 2026): the SUNS names may be shown on the website.**

64. **S45, which size is right?** The drawing writes "[152.4] Length 141.1in circumference".
    141.1 in is 358.4 cm round the top; with the drawn kidney shape that makes it 125.8 cm
    long, not 152.4. The 3D view on the same drawing agrees with 358.4 (the program fitted the
    view: a match at exactly the isometric angle). The cover now follows 358.4 cm round,
    125.8 cm long, 45 cm high, 4 vents. Is that right, or is it 152.4 cm long (then 434 cm
    round)?
65. **The night of 5 October** (answered by the owner, 5 Oct 2026):
    - build phases 1–4 of docs/plans/drawings-own-reading.md;
    - a vent count on a drawing always wins over the rule;
    - a better cover replaces the old one live, with a mail saying what was replaced;
    - re-export all drawing covers;
    - about €50 for paid calls;
    - release when all tests are green;
    - Rens, Rick and Wouter may approve covers at the drawing desk.
66. **Vent position on the drawings:** many drawings write "4 Air Pockets at Middle" or "at
    Top" (R1–R3). The rule from 1 October puts every vent 5 cm above the lower edge. Does the
    drawing's position win here too, as the number now does?
67. **Learning, simplicity and two questions** (mailed to Wouter Bekkers on 6 Oct 2026, at the
    owner's request; working on with the current system until the answers come):
    - lessons today only steer the AI's advice, not the geometry;
    - the proposal: two routes (2D drawing → cover; 3D cover surface → cover), the rest on
      request only.
    - Q1 (seams): a reference set of 10–20 good covers with their seams, the seam rules in
      writing, and structured seam feedback at the Desk.
    - Q2 (2D drawings): the STEP behind each drawing, or a fixed drawing standard; a test set of
      20 drawings with the right answer; structured feedback.
68. **A real search by image for "start from a photo"** (ADR-092; asked 7 Oct 2026). Gemini
    can only search the web by words, so a SUNS or other less famous brand is rarely found from
    a photo alone; Google Lens finds it because it searches by image. Google Cloud Vision "web
    detection" (the engine behind Lens's visual matches) is built in and switched off. To turn it
    on: in the Google Cloud project of the Gemini key, enable the "Cloud Vision API" and create an
    API key restricted to it; put it in deploy/.env as `GOOGLE_VISION_API_KEY`, and set
    `suggest.reverse_search: true`. **Cost:** the first 1000 photos a month free, then $3.50 per
    1000 (about €0.0033 a photo); at 10 suggestions a day: free. (Alternative: SerpAPI's Google
    Lens, $75 a month for 5000 searches; not needed if Cloud Vision is allowed.) Shall we?
