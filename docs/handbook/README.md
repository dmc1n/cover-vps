# The Cover Studio handbook

How to use Cover Studio (https://covers.suns.nu), for the owner, the approvers and the
workshop. It follows the studio's map: the four sections in the top bar, then a cover's own
page and the server. The map itself, with every address and who sees what:
[navigation.md](navigation.md). The short tour that the studio shows under **Guide**:
[how-it-works.md](how-it-works.md).

## Getting started

1. **Log in.** You get an invitation by mail with a personal link (valid 7 days); choose a
   password of at least 12 characters. The first time on a device you also get a 6-digit code
   by mail. See [admin.md — Logging in for the first time](admin.md#logging-in-for-the-first-time).
2. **Where you land** ([navigation.md — Where you start](navigation.md#where-you-start)):
   - approvers (who approve at the Desk) on **Work → Desk**;
   - an admin on the page he used last (in that browser);
   - the workshop login on **Work → Workshop** (ADR-128);
   - everyone else on **Covers → All covers**.

   These start pages are still to be confirmed with the owner (open question 3).
3. **Find anything** with the search box at the top right (**Ctrl+K**, **Cmd+K** on a Mac):
   covers, Desk codes, questions and, for admins, orders
   ([navigation.md — The right side of the bar](navigation.md#the-right-side-of-the-bar)).
4. **Light or dark:** the round button left of your name: As the computer (◐), Light (☀),
   Dark (☾).

The studio's buttons stay English (owner question #91, ADR-128).

## Work

- **Desk** — approve, reject or comment on covers, including orders; after sewing:
  produced, measured, fits: [desk.md](desk.md)
  - Correct this cover: [desk.md — Correct this cover](desk.md#correct-this-cover-adr-082)
  - Arrangements at the Desk: [desk.md — Arrangements at the Desk](desk.md#arrangements-at-the-desk-adr-115)
  - Measuring the sewn cover and entering it: [measuring.md](measuring.md)
- **Questions** — the owner's and the workshop's questions, answered in the studio:
  [desk.md — Vragen beantwoorden](desk.md#vragen-beantwoorden-voor-rens-adr-109)
- **Workshop** — orders waiting for production or in production; approved covers, files and fit:
  [workshop.md](workshop.md)

## Covers

- **All covers** — every model as a table or as cards, filters, batch runs, families, status:
  [catalogue.md](catalogue.md)
- **Arrangements** — furniture placed together under one cover: [arrangements.md](arrangements.md)
- **New cover** — a 3D file, a drawing (PDF), reference pairs (a zip):
  [web-app.md — Covers → New cover](web-app.md#covers--new-cover)
  - What the import does with a 3D file: [importing.md](importing.md)
  - Reference pairs: [learning.md — Upload](learning.md#upload-covers--new-cover-reference-pairs)
- **Learning** — your reference batches and their results:
  [learning.md — Results](learning.md#results-covers--learning)
- **Product list** — the workshop's product list (Excel), linked to the drawings:
  [desk.md — The product list](desk.md#the-product-list-adr-091)

## A cover

- **The cover's page and its seven tabs** (3D · Pieces · Seams · Adjust · Compare · History ·
  Files): [web-app.md — A cover's page](web-app.md#a-covers-page)
- **The Desk's approval and stamped PDFs:**
  [admin.md — Approving at the Desk](admin.md#approving-at-the-desk-adr-128)
- **3D:** the drape and the water on it:
  [web-app.md — The drape simulation](web-app.md#the-drape-simulation-3d-view); measuring:
  [measuring.md](measuring.md)
- **Pieces:** cut pieces and the DXF: [export.md](export.md); flat patterns and the size
  drawing: [patterns.md](patterns.md)
- **Seams:** [seams.md](seams.md)
- **Adjust:** a cover's settings: [parameters.md](parameters.md); the cover surface and its
  settings: [cover-surface.md](cover-surface.md)
- **Compare → Your reference:**
  [web-app.md — Your reference](web-app.md#your-reference-compare-the-program-with-your-own-drawing-or-model)
- **History → Revisions**, families and status:
  [catalogue.md — Revisions](catalogue.md#revisions)

## Shop

- **The Shop pages** (Orders, Requests, B2B customers, Website (AI)):
  [admin.md — The Shop pages](admin.md#the-shop-pages)
- **Orders:** [admin.md — The Shop pages](admin.md#the-shop-pages); B2B orders:
  [b2b.md — Orders](b2b.md#orders)
- **Requests** and the configurator in another webshop, the API:
  [webshop-api.md](webshop-api.md)
- **Matches** (a part of Requests): [admin.md — Matches](admin.md#matches-which-existing-cover-fits-learning-mode)
- **B2B customers:** [b2b.md](b2b.md)
- **Website (AI)**, languages, the website on its own domain:
  [admin.md — The Shop pages](admin.md#the-shop-pages),
  [admin.md — Languages](admin.md#languages),
  [admin.md — The website on its own domain](admin.md#the-website-on-its-own-domain-cloudflare)
- **Photo test** (Settings → AI & spending): [admin.md — Settings](admin.md#settings)
- **The public consumer shop** (pages, barbecues, legal pages, payments):
  [webshop.md](webshop.md)

## Prices (Settings → Prices & costs; one cover's: its Price & shop tab)

- **Costs, Price rules, Publish & versions:** [prices.md — The tabs](prices.md#the-tabs)
- **A cover's Price & shop tab:**
  [prices.md — A cover's Price & shop tab](prices.md#a-covers-price--shop-tab)
- **Import (Excel):**
  [prices.md — Prijslijst uit Excel importeren](prices.md#prijslijst-uit-excel-importeren-vaste-prijzen)
- **Publishing:** [prices.md — Changing a price](prices.md#changing-a-price)

## Settings

- **All the tabs** (Company & shop · Selling | Costs · Price rules · Publish & versions |
  Users & rights · Rules & defaults | Mail & notifications · Website & API keys · AI & spending
  | System & logs): [admin.md — Settings](admin.md#settings)
- **Users & rights, inviting people:**
  [admin.md — Inviting people](admin.md#inviting-people-for-example-for-a-kickoff),
  [admin.md — Roles and rights](admin.md#roles-and-rights)
- **B2B terms** (Settings → Selling): [b2b.md — B2B terms](b2b.md#b2b-terms-settings--selling)
- **Company defaults** (read-only in Settings; changed in `config/defaults.yaml`):
  [parameters.md](parameters.md). Whether the owner will edit some of them in Settings is an
  open owner question (#93).

## The server

- **Running, backups, alerts, releases, Tailscale, limits:** [server.md](server.md)
- **For the developer** (local app, the command line): [web-app.md — For the
  developer](web-app.md#for-the-developer), [importing.md](importing.md),
  [cover-surface.md](cover-surface.md), [seams.md](seams.md), [patterns.md](patterns.md),
  [export.md](export.md)
