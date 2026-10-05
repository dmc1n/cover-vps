# Plan: hosting, growth, GPU on demand, and matching the customer's sizes

The owner, 5 October 2026: "a learning mode, and come back with a solid plan. Where do we host
the website, here or for example Cloudflare? The covers keep running here on the server,
possibly with a GPU extension for the simulation, ideally through an API so we only pay for
what we use. The website must scale easily. People give their own sizes; we look for an
existing cover and show a match, for example 90 %. Below 90 % we make it custom."

## 1. The answer in short

| Part | Where | Why |
|---|---|---|
| The website (pages, images, 3D files of the catalogue) | **Cloudflare**: Pages + a Worker, content in KV, files in R2 | Served worldwide from the edge, scales without our effort, a traffic peak (a campaign) never reaches the server. Low fixed cost. |
| The shop's API (sizes → match, quote, rain check, orders, Mollie) | **Here**, behind a Cloudflare Tunnel (no open ports) | The engine is Python with compiled geometry (libigl, OpenCascade, Newton); Cloudflare Workers cannot run it. |
| Cover Studio (internal) | **Here**, as now (covers.suns.nu) | Internal, a handful of users. |
| The drape simulation | **Here on the CPU, plus a GPU on demand through an API** (Modal or RunPod Serverless) | Pay per second, nothing when idle. A sofa probably takes minutes instead of 40 minutes (to be measured). |

Why not everything here: one server is fine for the studio, but a public shop gets peaks. With
the front on Cloudflare, most requests (pages, images, the demo 3D) never reach the server; the
server only computes. Why not everything at Cloudflare: our engine does not run there, and
Cloudflare has no GPUs for our solver.

## 2. The website on Cloudflare

- **Pages** serves the shop's build (`apps/web/dist`, the `shop.html` entry).
- **A Worker** puts the content into the HTML (title, description, JSON-LD, the text) exactly as
  `install_pages` does now, so search engines and AI assistants keep reading the real text.
  It also serves `robots.txt`, `sitemap.xml` and `llms.txt`.
- **The AI CMS stays here.** **Publish** also writes `live.json` to Cloudflare KV. The site
  changes worldwide within seconds; the preview stays here, behind login.
- **R2** holds the catalogue's 3D files and photos, cached at the edge. We already use R2 for
  the backups.
- **`api.<domain>`** points through the Tunnel to this server. It needs rate limits, CORS for
  the shop domain only, and Turnstile (Cloudflare's captcha) on the order form.
- **Quotes are cached by their inputs.** The same sizes give the same answer without
  computing again.

### When the server itself gets busy

1. **First:** the cache and a queue for heavy requests. The rain check per quote is the
   heaviest part.
2. **Then:** a second Hetzner server with the same release, both behind the Tunnel. Cloudflare
   spreads the requests.
3. **Only if needed:** the quote workers as containers.

None of this changes the shop's code.

## 3. The GPU on demand (pay per use)

- **The job.** A container with the engine, Newton and Warp. It receives the model's pieces
  (`panels.npz`), the furniture, the balloons and the parameters, and returns `drape.bin` and
  `drape.json`.
- **How it is called.** This server sends the job over HTTPS and stores the result with the
  model as now. Only geometry goes out, never customer data.
- **Providers.**
  - **Modal:** per-second billing, scales to zero, Python-native.
  - **RunPod Serverless:** the same model, often cheaper.
  - Choose after one benchmark day.
- **Measure first.** One sofa (the Lucia) on a GPU. I expect minutes instead of 40 minutes, but
  that is to be measured.
  - The cost per sofa follows from the measured GPU minutes. At roughly €1 per GPU hour
    (indicative, to verify), 5 minutes is about €0.10.
  - A monthly cap is set at the provider.
- **What the GPU also opens up.**
  - **Self-contact:** the cloth touching itself, which the CPU version cannot do. That is
    the next step in realism.
  - **A drape of the customer's own cover** within minutes after the order.
- **The CPU queue stays as the fallback.** No GPU budget, or the provider down: it works as
  today, only slower.

## 4. Matching the customer's sizes to an existing cover

The catalogue holds 302 SUNS covers. Among them are 104 sofa sets, 58 tables, 31 lounge tables
and 29 chairs.

**The customer's side:**

1. Choose the kind of furniture: sofa, corner sofa (left or right), dining table, round
   table, lounge chair, lounger, and so on.
2. Enter the sizes asked for that kind, with a drawing of where to measure. For a sofa:
   length, depth, height, seat height, arm height and back height.
3. Get one of three answers:
   - **"Cover X fits you for 94 %."** The existing cover: stock price, short delivery time. The
     page shows where it fits: "2 cm roomier in length, exact in depth".
   - **80–90 %:** both are offered, the existing cover with its differences, or a custom cover
     at its price.
   - **Below 80 %, or nothing of the right kind:** custom. That flow is already built (the
     configurator, then the order, then production).

The 90 % threshold is a setting.

**How the percentage is computed:**

- **A size card per cover.** The cover's own inner sizes (not the furniture's), taken from the
  design (`hull.json`, the drawings) and written at every export into one index,
  `covers_index.json`.
- **Per size, the difference d = cover − (furniture + ease):**
  - within the allowed band (e.g. 0 to +4 cm, to confirm): **100 %**;
  - **too small** drops fast: a cover that is too small does not go on;
  - **too large** drops slowly: it hangs loose and folds more.
- **Weights per size.** Length and depth count more than the back height.
- **The total** is the weighted score, capped by the worst size: one size far too small is
  never hidden by good others.
- **Hard filters.** A different kind of furniture, or a left corner against a right corner,
  scores 0.
- **Optional check with the drape (with the GPU).** The three best covers are dropped over
  furniture built from the customer's sizes, which we already build for the configurator.
  Their sag and folds refine the percentage: "checked in 3D".

## 5. The learning mode

"Learning" means the percentages earn our trust before customers depend on them.

- **Phase A, shadow.**
  - The customer enters sizes and gets "we will come back to you within one working day".
  - Internally the admin sees the request with the three best matches and their percentages.
  - A colleague confirms or changes the proposal, and that choice is stored. Every disagreement
    is a lesson.
- **Phase B, automatic above the threshold.**
  - Once (for example) 50 proposals were confirmed unchanged, matches above the threshold go to
    the customer directly.
  - Below it, a colleague still looks.
- **After delivery.**
  - Two weeks after delivery the customer gets one question by mail: "how does it fit?"
    (1–5, optional photo). Returns are recorded with their reason.
- **Calibration.**
  - A **Learning** page in the admin shows, per match band (95–100, 90–95, ...), the
    satisfaction, the returns and how often a colleague changed the proposal.
  - From that we set the threshold and the allowed bands: for example, if 88 % matches turn
    out to fit well, the bar goes down.
  - It is the same loop as the owner's corrections in the studio (ADR-055): a correction
    becomes a stored lesson and a check.

## 6. Order of work

| Phase | What | Needs from the owner | Cost |
|---|---|---|---|
| 1 (here, now) | Size cards for all 302 covers, the matching score, the "fits you for N %" answer in the shop, the shadow learning mode with the admin view, the fit question by mail | The allowed bands (question 57), which covers are sold off the shelf and at what price (58) | none |
| 2 | Website on Cloudflare (Pages, Worker, KV, R2), API through the Tunnel, Turnstile, cache | The domain in Cloudflare and an API token (59) | low fixed fee |
| 3 | GPU benchmark, then the drape on the GPU by API, self-contact | The provider and a monthly cap (60) | per use |
| 4 | Only if traffic asks for it: a second server, workers as containers | — | per server |

Phase 1 can start right away and needs no outside account. It runs on today's server and in
today's shop.

## 7. Questions (also in docs/QUESTIONS.md)

57. How much may an existing cover be **larger** than the furniture and still count as a good
    fit (e.g. up to +4 cm in length and depth, +3 cm in height)? Is anything smaller ever
    acceptable?
58. Which of the 302 covers are sold **off the shelf**, at what price, and with what delivery
    time against custom?
59. The shop's **domain**, and may it move to Cloudflare (DNS)? An API token with access to
    Pages, Workers, KV and R2.
60. **GPU:** Modal or RunPod (I will benchmark both if you want), and a **monthly cap** (e.g.
    €50)?
61. May we mail customers **two weeks after delivery** to ask about the fit, with an
    optional photo?
