# Plan: the website's clips from real SUNS photos, Gemini + Veo (ADR-127)

The owner (13 October 2026), after the Kota test: "dit is stukken beter"; then "alleen even de
beste foto zoeken voor alle settings, mag ook een ander model zijn maar dan moeten we het
aanpassen" (find the best real photo for every scene; another SUNS model is fine, but then the
cover must be that model's).

**How it works.** A real SUNS photo is the start; `gemini-3-pro-image` puts **our** cover for that
model on it (the model's `cover.png` as the shape, our Kota canvas render as the fabric) and keeps
everything else; Veo 3.1 Fast adds the motion. Everything is in `scripts/film/veo_shots.json`.

```
uv run python scripts/film/veo.py cost                                    # prices, spent, cap
uv run python scripts/film/veo.py photo URL --name x-start --center 0.5,0.5  # a SUNS photo as a 16:9 frame (free)
uv run python scripts/film/veo.py frame portofino-end [--dry-run]         # our cover onto it (~EUR 0.15)
uv run python scripts/film/veo.py run --shots fit-portofino [--dry-run]   # one 8 s 1080p clip (~EUR 1.14)
uv run python scripts/film/veo.py fetch                                   # later, if a run stopped waiting
```

Default paths: `--out out/veo`, frames in `out/veo/frames/` (with `sources.json`: every SUNS
photo's file name and URL, every made frame's photo, references, prompt and cost), clips in
`out/veo/<shot>/<n>.mp4` with `<n>.json`. Ledger `out/veo/ledger.jsonl` plus the studio's AI
ledger; `--budget-eur` (default 30) is checked before every call.

## Choosing the photos (13 Oct)

All of hello-suns.com's product pages (217) and project pages (28): 987 mood and lifestyle
photos, as 768 px thumbnails with numbered contact sheets in `out/veo/suns-photos/` (`index.json`
maps each number to the file and its page). Judged on realism, light, one clear piece of
furniture, room for the cover, and whether we have a cover for that model in `models/`.

| Scene | Chosen photo | Why | Our cover (shape reference) |
|---|---|---|---|
| fit | `05_Portofino-SUNS-daybed-TK-NMW-Mood-23-1.jpg` (Portofino daybed, paved terrace, glass hall) | front-on, one piece, centred, hard sunlight, the whole cover's outline visible | `suns-daybed-portofino` |
| fit (2nd) | `05_Kota-Veneto-SUNS-Loungeset-TK-NG-Mood-25.jpg` (13 Oct's Kota) | the approved one; close, low angle | `suns-2-seater-kota` (our Blender render) |
| rain | the Portofino frame above, made rainy by Gemini | the whole sloped top and the front skirt in view: water visibly runs off | `suns-daybed-portofino` |
| rain (2nd) | the Kota frame, made rainy | close, the slope fills the frame | `suns-2-seater-kota` |
| villa | `Blocchi-Termoli-SUNS-Loungeset-WGB-Mood-24-1-2500.jpg` (two Blocchi sofas, terrace above a mountain valley), relit to golden hour | the most Mediterranean SUNS terrace with furniture we cover | `suns-lounge-blocchi-moon-part` |
| villa (2nd) | `04_Portofino_Daybed_SUNS_roof.jpg` (Marbella villa pool, palms, tile roof), golden hour | a real Spanish villa; but the covered canopy is a tall plain box | `suns-daybed-with-roof-portofino` |
| range | `Header_Basta_Loungers-1.jpg` (two Basta loungers by the pool, Basta bar set behind) | several pieces of different kinds, clear light, water | `suns-sunlounger-basta-aluminium`, `suns-low-bar-table-basta`, `suns-low-bar-chair-fiave` (chairs: the nearest bar-chair cover we have) |

Not used, and why: SUNS's only sea photo (Villa Maxima, Puglia: `SUNS_Villa-Maxima_Puglia_3.jpg`)
shows the Pesaro set, for which we have no cover (we build none in this round); the Kota sofa
set headers are good but two pieces side by side; the Lucia, Vento, Pico and Rios sets around
pools are big corner sets where the cover would hide the whole picture; Ibiza-style mood photos
are cut-outs ("Free") without a scene.

## The frames, as checked

| Frame | Judgement |
|---|---|
| `portofino-end-v1` | rejected: the cover is a low flat mattress, far below the back cushions (squashed) |
| `portofino-end-v2` | used: a wedge up to the back cushions, the ends hipped, level skirt hem just above the paving, two vent hoods on the front; the top is flatter than our cover's slope, sand colour right, background unchanged |
| `portofino-mid-v1` | used for the mid → end take: the cover hangs over the back cushions, the seat still bare |
| `portofino-rain-v1` | used: overcast, wet paving with reflections, beads on the cover, shape and vents kept |
| `kota-rain-v1` | used: wet tiles, reflections, beads; the cover kept |
| `blocchi-golden-v1` / `-v2` | rejected: a loose lumpy bag (v1, daylight) / bulging tent (v2) |
| `blocchi-golden-v3` | used: taut faceted panels with straight seams, level skirt, vents; the sun low behind the hills |
| `marbella-golden-v1` | rejected: the teak base showed under the cover (hem at the platform, not the ground) |
| `marbella-golden-v2` | used: the whole canopy in one box, hem just above the paving, two vents; in the backlight the sand reads khaki-grey |
| `basta-end-v1` | used: wedge covers on the loungers, box covers on the bar table and chairs, all sand, the pool and its reflections unchanged |

## The clips and how good they are

See ADR-127 and the comparison page (`/media/veo-compare.html`); each `<n>.json` has the prompt.
