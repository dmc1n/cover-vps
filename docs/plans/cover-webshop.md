# Plan: our own cover webshop

The owner, 4 October 2026: "we need no public API. On this server, which can grow, we build a
webshop made purely for covers. We build our own 3D model from all the input, only for a cover,
with a rain simulation to upsell balloons or a frame. A very neat website that looks
hyper-modern: a fine welcome film on how it all works and how green we work, and then straight
to the configurator. Make a plan for how best to do this and what we need."

## The customer's journey

1. **The landing page.** A full-screen welcome film (60–90 s, muted, autoplay with subtitles):
   - the sizes go in;
   - the cover appears in 3D;
   - the rain runs off;
   - the CNC cuts;
   - the workshop sews;
   - the cover goes on.

   Then the green story: made to measure (no stock, no overproduction), nesting with little
   waste, a durable fabric, local production, repairs. One button: **Design your cover**.
2. **The configurator** (3D, the centre of the shop):
   - choose the furniture (dining set, round set, sofa, corner sofa, lounger, single item) and
     give rough sizes; the furniture appears in 3D at once, built from those sizes (table
     with legs, chairs, sofa with back and arms), with the cover over it;
   - choose the colour (the Coverlast colours, shown on the cover), vents, drawcord;
   - **the rain.** The rain falls on the cover, and the heatmap shows where water would stay.
     The shop then proposes, with the price: "add 2 balloons: no water stays", or "a frame:
     a sloping roof". This is the upsell, and it is honest: the customer sees why;
   - the price is updated live: cover, options, delivery.
3. **Cart and checkout:** contact and delivery address, payment (iDEAL, cards, Bancontact,
   Klarna and others by Mollie), confirmation by mail.
4. **After the order** (our side), automatically:
   - the definitive pattern through the full program (hull, cut, flatten, export);
   - the drape (Style3D) and the rain on it;
   - the approval by an approver;
   - the cut file;
   - production.

   The customer gets a status mail at each step: in production, sewn, shipped.

## How

| Part | Choice | Why |
|---|---|---|
| Website | its own front end on this server, React + Three.js (react-three-fiber), scroll and motion design; its own domain or subdomain | fast, fully ours, one stack with Cover Studio |
| Look | hyper-modern: large type, the 3D cover as hero, smooth transitions, dark and light, mobile first; NL, EN and DE | the owner's wish |
| 3D model | **our own**: the furniture made from the sizes (parametric table, chairs, sofa, lounger), the cover from `quote.py` and `drawn.py`; balloons and a frame as options | no external models needed; every size works |
| Rain | our rain simulation (`rain.py`) on the configured cover, a few seconds | the upsell |
| Drape | **after the order** (Style3D, ~40 min); in the configurator only the fast design view | Style3D is too slow for live |
| Payments | **Mollie** (Dutch; iDEAL, cards, Klarna, Bancontact) | the standard in NL, simple |
| Orders | in our own database: cart, orders, payments (webhooks), statuses, invoices (PDF with VAT), mails | everything in one place, next to production |
| Admin | Cover Studio gets an **Orders** page: new, paid, in production, shipped; one click from order to pattern | no second system |
| Security | the shop separate from Cover Studio (its own routes, no login to the studio); payments only through Mollie (we never see card data); rate limits; backups | GDPR and PCI kept small |
| Speed and SEO | static pages from the CDN cache of Caddy; the film as an HLS stream in several qualities; structured data for Google | fast on a phone |
| Analytics | Plausible (self-hosted, no cookies) | no cookie banner needed |

**What exists already** and is used:

- the proposal engine with prices (`quote.py`);
- the shapes from the owner's drawings;
- the rain simulation and the heatmap;
- the drape (Style3D);
- the full pattern route with approval and cut files;
- mail;
- the server's security and backups;
- the configurator page (#/configure) as a first version.

## The welcome film

There are three ways, best together:

1. **Real footage from the workshop**: the CNC cutting, the sewing, the cover going on a SUNS
   set outdoors, rain running off. A phone in 4K or a hired filmmaker for one day.
2. **Our own 3D animation**: sketch → pattern → cut → cover → rain, rendered from our own
   pipeline (like the login page, cinematic), in the house colours.
3. **AI video** (Runway, Veo, Sora) for the atmosphere shots (a garden in the rain, sunset),
   from prompts and brand pictures.

**Proposal:** 2 (I make it) plus 1 (the owner films, or a filmmaker), with 3 for the
transitions. Subtitles NL/EN/DE, music without rights issues.

## Phases

| Phase | What | Duration (rough) |
|---|---|---|
| 0. Decisions | name and domain, prices, payment account, legal texts, film footage | the owner, 1–2 weeks alongside |
| 1. Configurator v2 | our own furniture in 3D, cover over it, colours, rain + upsell of balloons and a frame, live price | ~1 week |
| 2. Shop | cart, Mollie checkout (test mode first), orders, invoices, mails, the Orders page, order → pattern | ~1 week |
| 3. Website | home with the film, how it works, green, FAQ, reviews, legal pages, NL/EN/DE, SEO | ~1 week |
| 4. Film | the 3D animation; editing with the workshop footage | alongside phases 2–3 |
| 5. Launch | test orders end to end, a real first customer, then live | after the physical test |

## What the owner needs to provide

1. **Name and domain** for the shop (a separate brand, or under SUNS or S2DIO).
2. **Prices** (QUESTIONS 52):
   - fabric per metre;
   - sewing time and rate;
   - parts;
   - margin;
   - delivery costs, and to which countries.
3. **Mollie account** (KvK, bank account, website; a few days for approval).
4. **The legal texts:**
   - terms, privacy and the imprint (KvK, VAT number);
   - made to measure: no 14-day return right (EU law, Art. 16(c)), which must be stated;
   - warranty.
5. **The green story in facts:** where it is made, the fabric (Coverlast: recycled share?
   PFAS-free: yes), the waste in cutting, packaging, transport.
6. **Film footage**, or a day with a filmmaker; logo files in vector; the brand colours (the
   house style S2DIO × SUNS, or a new look for the shop).
7. **Balloon and frame as products**: sizes, price, stock, a picture.
8. The first physical test (the cut Kota) **before** the first paid order.

## Not needed now

- A public API: dropped. The shop uses our own internal routes.
- Separate shop software (Shopify, WooCommerce): not needed. Everything is ours on this
  server, so nothing has to be kept in sync.
