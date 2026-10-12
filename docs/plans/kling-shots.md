# Plan: the website's clips with Kling, from our own stills (ADR-125)

The owner (12 October 2026): the Blender animations on the website are far from realistic;
redo them with Kling (AI image-to-video). The key arrives on 13 October in `deploy/.env`.

**How it works.** Our Blender stills (`scripts/film/kling_frames.py`) fix what must be true: our
cover's real shape from our data (the Kota 2-seater's Style3D drape), the sand colour, the
woven canvas and the double stitching. Kling only adds what Blender did badly: motion that looks
filmed (cloth settling, rain running off, a slow camera, a breeze). For a transition (fit) we
give a first and a last frame, so Kling must end on our cover.

**Tomorrow is only "run"** (from the main checkout, after the key is in `deploy/.env`):

```
uv run python scripts/film/kling.py cost                       # the prices; nothing sent
uv run python scripts/film/kling.py run --shots sew --dry-run  # the request; nothing sent
uv run python scripts/film/kling.py run --shots sew            # one clip first (~€0.53), look at it
uv run python scripts/film/kling.py run --shots fit,rain,villa,cut,vent
uv run python scripts/film/kling.py status | fetch             # later, if a run stopped waiting
```

Clips land in `out/kling/<shot>/<n>.mp4`, with `<n>.json` beside it (prompt, parameters, task,
cost). Every submit is on `out/kling/ledger.jsonl` and on the studio's AI ledger
(`<data>/usage/ai-YYYY-MM.jsonl`, model `kling-3.0`), and the script refuses a clip whose
estimate would take `out/kling/ledger.jsonl` past `--budget-eur` (default 50) before sending
anything. Note: those euros also count towards the studio's monthly AI budget
(`spend.budget_eur_month`, €50, hard stop at 100 %); a full set of takes (~€11) leaves room, but
`--no-studio-ledger` keeps Kling out of it if the owner prefers.

## What a clip costs

Kling's list prices (kling.ai/document-api/pricing/base/video, read 12 Oct 2026), one unit =
$0.14; the ledger converts at a deliberately high $1 = €0.95 so the cap errs safe.

| Model | Mode (resolution) | 5 s clip | Last frame? |
|---|---|---|---|
| **kling-3.0** (our default) | **pro (1080p)** | **4 units, $0.56, ~€0.53** | yes |
| kling-3.0 | std (720p) | 3 units, $0.42, ~€0.40 | yes |
| kling-3.0-turbo | pro (1080p) | 5 units, $0.70, ~€0.67 | no (and always with audio) |
| kling-2.6 / 2.5-turbo | pro (1080p) | 2.5 units, $0.35, ~€0.33 | 1080p only |
| kling-2.6 / 2.5-turbo | std (720p) | 1.5 units, $0.21, ~€0.20 | no |

One take of all seven shots at kling-3.0 pro: ~€3.70. Three takes each, both aspects where it
matters: well under €15. The €50 cap is never near.

API notes (from Kling's docs, 12 Oct 2026):
- The current API takes **only the API key** (`KLING_API_KEY`): `POST /image-to-video/<model>`
  with `contents` (prompt, first_frame, last_frame as plain base64), `settings` (resolution,
  duration, `multi_shot: false`, `audio: off`); `GET /tasks?task_ids=…`. It has **no negative
  prompt, mode or aspect field**: the negative words go into the prompt as "Avoid: …" (Kling's
  docs say the prompt may hold both), the mode is the resolution (std 720p, pro 1080p), and the
  aspect follows the first frame.
- The access key + secret key JWT works only with the **legacy** API (`POST
  /v1/videos/image2video` with `model_name`, `image`, `image_tail`, `negative_prompt`, `mode`,
  `duration`). Kling's current docs no longer describe that API; the script speaks it from the
  earlier docs (`model_name` kling-v2-5-turbo etc.), so with only AK/SK: `--dry-run` first, then
  one clip, before a run.
- Results are kept 30 days on Kling's side; `fetch` downloads them at once.

## The shots

Frames: `~/opt/film2/kling/final/` (outside the repository; kling_shots.json's `frames_dir`).
Each at 16:9 1920 × 1080 and 4:5 1080 × 1350; the cards on the site are 4:5, the villa 16:9.
Model kling-3.0, mode pro (1080p), 5 s, for every shot.

The negative prompt for all shots:

> hands, fingers, people, text, letters, numbers, logos, labels, watermark, extra seams, new stitching, zips, buttons, warping or bending furniture, morphing shapes, melting fabric, colour change, flicker, camera shake, fast motion, cuts

| Shot (media key) | Start / end frame | Prompt | What to check in the result |
|---|---|---|---|
| **fit** (fit) | `fit-start-4x5.png` → `fit-end-4x5.png` | A sand-coloured canvas cover drops gently from above onto an outdoor sofa on a stone terrace and settles over it, the fabric sliding over the back and arms and coming to rest with its hem just above the stone. Slow steady push-in, camera otherwise still. Low warm late-afternoon sun, soft shadows. Realistic cloth physics, calm. | the cover arrives from above (no hands, nobody holding it), ends exactly as the last frame, the sofa does not change shape, no extra seams |
| **fit-b** (fit) | `fit-mid-4x5.png` → `fit-end-4x5.png` | A sand-coloured canvas cover that has just been pulled over an outdoor sofa slides the last few centimetres down and settles, the fabric relaxing into soft folds, the hem coming to rest just above the stone terrace. Slow steady push-in. Low warm late-afternoon sun. Realistic cloth physics, calm. | the second try for fit if the first invents hands: the cover only falls and settles; same checks as fit |
| **rain** (runoff) | `rain-start-4x5.png` | Steady rain falls on a sand-coloured canvas cover over an outdoor sofa on a stone terrace. Raindrops bead on the coated fabric and run down its slopes in thin streams, gather at the hem and drip onto the wet stone, where small splashes form. Grey overcast light, very slow push-in, camera otherwise still. Calm and realistic. | water runs downhill and off the cover (never pooling on top, never soaking dark), the drops fall straight, the fabric stays sand and dry-looking under the beads, no puddles on the cover |
| **villa** (villa) | `villa-start-16x9.png` | Golden hour on a whitewashed villa terrace on Ibiza above a calm sea. An outdoor sofa and a sun lounger stand under fitted sand-coloured canvas covers. The camera dollies slowly sideways to the right. A light sea breeze moves the leaves of the plants and barely stirs the fabric; sunlight glitters on the water; the warm low sun throws long soft shadows across the terracotta tiles. | both covers keep their shape and colour, the horizon stays level, the island stays put, no people, the motion is slow enough to loop with a dissolve |
| **cut** (cut) | `cut-start-4x5.png` | Close-up of an automatic cutting table in a workshop: the steel cutting head glides slowly and steadily along a straight line over sand-coloured canvas, its blade leaving a clean thin cut behind it. The drawn pen lines on the fabric stay still. Soft even workshop light, the camera follows the head very slightly. | the head moves along the line at an even speed and the cut grows behind it, the fabric does not ripple or change colour, the pen labels do not change or turn into new text |
| **sew** (sew) | `sew-start-4x5.png` | Macro close-up of a double-stitched seam on a sand-coloured canvas outdoor furniture cover: two parallel rows of even stitches run along the corner. The camera glides slowly along the seam; warm sunlight moves gently across the woven texture. Shallow depth of field, calm. | exactly two rows of stitches stay two rows (no third row, no zig-zag), the stitch length stays even, the weave stays fine |
| **vent** (vent) | `vent-start-4x5.png` | Close-up of an air vent on a sand-coloured canvas furniture cover: a small fabric hood held open by a grey plastic insert, a dark mesh membrane behind it. A light breeze makes the hood tremble very slightly; the camera slowly arcs a little to the side. Warm sunlight, soft shadows, calm. | the hood stays one hood with its insert, the membrane stays dark mesh behind it, nothing opens or tears, the cover around it stays smooth |

### The frames as rendered (12 Oct, 160 samples, ~15 minutes a picture), and how good they are

Rendered with `kling_frames.py`, looked at one by one at full size; earlier tries are kept in
`~/opt/film2/kling/first/` for comparison.

| Frame | Judgement |
|---|---|
| `fit-start-*` (bare sofa) | good: real light on the stone and plaster, the sofa reads as a product photo; its aluminium base still shows a few facets |
| `fit-end-*` (covered) | good: our drape, sand, soft folds at the hem, the same camera as the start, so Kling only has to bring the cover in |
| `fit-mid-*` (settling) | usable: the cover already on, its hem not yet down; for fit-b |
| `rain-start-*` | good after the second try: overcast, wet dark stone, the cover clean (the first try baked drops on the run paths; they read as white rivets and grey marks) |
| `villa-start-*` | the best of the set: low warm sun from the left lighting the covers' ends and the tiles, long shadows, the sea and the island in haze; the Sato lounger shows its designed surface (its drape sags). Third try: the first had a saw-tooth shadow along the Kota cover's front fold (Cycles' shadow terminator on the coarse mesh), fixed with the terminator offsets; the slope now lies in its own soft shade |
| `sew-start-*` | good: the double stitching stands up as thread, the weave is visible, a T where the skirt seam meets the corner; one dent shadow beside the corner could read as a mark |
| `cut-start-*` | fair: the head now hangs from a carriage on a beam, the pen lines and labels sit on the sand; the carriage is a plain block and the fabric reads pale in the workshop light |
| `vent-start-*` | weakest: the hood and its insert read, the membrane hardly shows (from the eye's height it is hidden under the hood, as on a real cover); the owner's phone clip would be better |

`range` (other covers from the catalogue) keeps its current clip: the Sato lounger's drape still
sags into its seat and the Savona set is a box (ADR-121), so a Kling take of it would show those
faults more convincingly, not fewer.

Every check also: the colour stays our sand (compare with the start frame), the cover's
outline stays ours (no invented seams, zips, straps, logos), nothing bends that is rigid, and
the last half second can dissolve into the first (hero_encode.py loops each clip with a 10-frame
dissolve).

Prompt rules we follow: one calm camera move, physical behaviour named plainly (beads run off,
fabric settles, light moves), no brand names, nothing the frame does not already show. If a
take fails a check, change one thing (shorter prompt, the alternative frame, std → pro) and
note it in `<n>.json`'s folder; never more than three takes of a shot without looking.

## Clips the owner can film himself instead

Real footage beats any render for the workshop. A phone (4K, 25 or 30 fps, the main lens, not
the wide one) on a small tripod or held against a fixed object; 8–10 s each; locked exposure
and focus (long press on the subject); no people's faces, hands are fine here because they are
real; daylight or the workshop's own light, no flash.

| Clip | How | Framing |
|---|---|---|
| cut | the cutting head along a straight edge of a sand piece; start a second before it enters the frame | 4:5 crop in mind: the head in the upper third, the cut line running diagonally |
| sew | the needle and presser foot along a double-stitched seam, close (20–30 cm), the machine at its normal speed | side-on, the seam running across the frame |
| vent | one finished vent on a cover on a sofa, the phone near the ground, slowly round from the front to the side | the hood, the insert and a glimpse of the membrane |
| fit | two people lower a cover over a sofa from behind it (their hands out of frame at the top) | the whole sofa, the phone at seat height, 3 m away |
| rain | a garden hose with a spray nozzle aimed up so it falls as rain on a covered sofa, 30 s, cloudy day | close on a slope of the cover and the hem; and one wide |
| villa | any customer's covered set in late-afternoon sun, a slow walk sideways | wide, horizon level |

Send the files as they are (no editing, no filters); they go through the same steps below.

## From a clip to the website (do not deploy before the owner has seen them)

1. **Choose the take**: watch `out/kling/<shot>/<n>.mp4` against the checks above; note the
   chosen `n` in the plan's shot table.
2. **Frames at 24 fps**, named for hero_encode.py's clip mode (one shot, the end dissolving
   into the start):
   ```
   mkdir -p out/kling/frames/fit
   ffmpeg -i out/kling/fit/1.mp4 -vf fps=24 out/kling/frames/fit/fit-%04d.png
   ```
   (the owner's own phone clips the same way, with `-ss 1 -t 5` to take 5 seconds and
   `-vf fps=24,scale=-2:1350,crop=1080:1350` for the 4:5 cut).
3. **Encode** (AV1 + H.264, two-pass, poster, strip), a new name for every take because the
   edge caches /media for a day:
   ```
   uv run python scripts/film/hero_encode.py out/kling/frames/fit out/kling/media \
       --name work-fit-2 --pattern 'fit-*.png' --av1-size 720:900 --h264-size 720:900 --max-mb 1.2
   uv run python scripts/film/hero_encode.py out/kling/frames/villa out/kling/media \
       --name villa-ibiza2 --pattern 'villa-*.png' --av1-size 1600:900 --h264-size 1280:720 --max-mb 3.0
   ```
   The names: `work-cut-2`, `work-sew-2`, `work-vent-2`, `work-fit-2`, `work-runoff-2` (from
   the rain shot), `villa-ibiza2`. Look at `strip.jpg` and the poster.
4. **Into the studio's media** (the owner's step, or with his go): copy the `.mp4`, `.jpg` and
   `.webp` files to `~/cover-data/media/`. Nothing there is replaced: the new names sit beside
   the `-1` files, so the live site does not change.
5. **The preview only**: in `apps/site/preview-overlay.json`, `settings.story_media`, point the
   keys at the new files, for example
   `"fit": "/media/work-fit-2-h264.mp4", "fit_av1": "/media/work-fit-2-av1.mp4",
   "fit_poster": "/media/work-fit-2.jpg"`, likewise `cut`, `sew`, `vent`, `runoff`, `villa`
   (and `pack`/`pack_av1`/`pack_poster`, which show the fit clip); then `make web-build` and
   `cd apps/site && npm run deploy:preview`. Only preview.s2dio.living changes.
6. **Check** in a real browser: `apps/web/e2e/site_perf.py` (the clips load lean) and a look at
   the cards on a phone width; the posters show for reduced motion.
7. **Live** only with the owner's go and a release (`scripts/release.sh`): the same keys in the
   live content's `story_media`. Going back is pointing the keys at the `-1` names again.
