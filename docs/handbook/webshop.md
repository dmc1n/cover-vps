# The consumer webshop (B2C, public)

The shop for consumers is at **https://shop.s2dio.living** (ADR-066, ADR-103, ADR-128). Everyone can use
it without logging in. The business shop (B2B, Sunsit and dealers) is separate and has a login
under `/b2b`.

## Its pages

| Address | What |
|---|---|
| `/` | the home page (the scroll story only when `home_story` is on) |
| `/configure` | the configurator: sizes or a photo/link, the cover in 3D, the rain, the price, checkout |
| `/order/<code>` | the customer's order status (from the confirmation mail; never in Google) |
| `/terms` `/privacy` `/returns` `/cookies` `/contact` `/warranty` | the legal pages |
| `/en/…` `/de/…` `/fr/…` | the same in another language (Dutch is the first, without a prefix) |

An address the shop does not know shows "this page does not exist" (a real 404).

## Barbecues (ADR-119)

**Off on the live shop until you set their prices:** Settings → **Company & shop** →
`bbq_enabled`. While it is off, the shop, B2B and the public API show no barbecues; the preview
site (preview.<domain>) always shows them, so you can try them there.

Above the product cards the configurator has two choices: **Tuinmeubels** and **Barbecue**.
Under Barbecue: a kamado (egg) in a nest, with or without side tables; a kamado in a table; a
gas grill with side shelves; a pellet grill; a fire table or plancha (round or square). The
customer gives the barbecue's sizes with the lid closed; the 3D view shows a barbecue of that
shape under the cover. The cover is a round band with a cone on top (a kamado alone, a round
fire table) or a box with a hipped roof (all others): every part of the top slopes at least
`quote.bbq_slope_min_deg`, so water runs off. The page says plainly that a cover goes on a
**cold** barbecue only (the canvas is not heat-proof).

"We already make a cover for your Big Green Egg Large in nest": a BBQ cover of our catalogue
(a `bbq-…` model) is offered once Rens or Wout approve it at the Desk and its cover.json says
which product it answers to: `"match": {"kind": "bbq_kamado", "name": "Big Green Egg Large in
nest"}`. The B2B shop has the same products and lists the approved BBQ covers in its
catalogue. The products, their fields and ranges are in `config/quote_products.json`
(`"group": "bbq"`); the words in `config/shop_ui.json`.

## The legal pages: drafts until you approve them

Each legal page shows a draft that starts with a red **CONCEPT — TER GOEDKEURING** line, in
Dutch and English (German and French visitors see the English one until it is translated).

1. Fill in the company details: Settings → **Company & shop** → The company (name, legal
   name, street, postcode, city, KvK, VAT number, e-mail, phone). They appear in the texts at
   once; anything still empty shows as "[nog in te vullen: …]".
2. Have the texts read. The drafts are in `config/shop_legal.json`.
3. Publish your own text: Shop → **Website (AI)**, for example "zet als algemene voorwaarden
   (legal.terms.nl) deze tekst: …", check the preview, **Publish**. From then on that page
   shows your text and the draft is gone. A line starting with `## ` is a heading, `- ` a list
   item, an empty line a new paragraph.

Made to measure has no right of withdrawal; a cover from our standard range (chosen through
"we already have a cover that fits") keeps the 14 days by law. The checkout's checkbox says
which applies.

## Prices

The prices are the **B2C** list of the published price set (Settings → Prices & costs, and
each cover's own Price & shop tab; docs/handbook/prices.md), incl. VAT. While that set is marked **indicative**, the configurator
and the checkout say so plainly ("Indicatieve prijs — … je betaalt pas na bevestiging").
Publish a set with *indicative* off when the prices are final; the note disappears.
Delivery per country (Settings → Company & shop → Shipping per country) is added at the
checkout and shown before the order. The *indicative* switch is on
Settings → Costs, under Exchange rate.

The price shown is always the one for the sizes and options on screen (ADR-129): while a new
price is on its way the old one is not shown and cannot be ordered, and an older answer that
arrives late is dropped. One checkout makes one order: the order button is locked while the
order is on its way, and the page sends a key with it, so a double click or a retry gets the
order that was already made (a page without a key: the same proposal, e-mail and street, still
unpaid, within 15 minutes is the same order). When the payment link is still being made the
page says to try again in a moment; the retry finishes the same order.

## Payments (Mollie)

Settings → **Website & API keys** → Payment → Mollie key (shown masked; *Replace* to give a
new one):

- empty: orders are placed and wait for payment (bank transfer; mark paid, then **Send to production**);
- when Mollie does not answer or refuses, the customer sees "the payment could not be
  started; please try again" and we get one mail; the next try finishes the same order with
  the same payment (ADR-129);
- `test_…`: Mollie's test mode; the checkout says "Testbetalingen: er wordt geen geld
  afgeschreven";
- `live_…`: real payments.

To go live: finish the Mollie account, place one test order with the test key end to end
(pay, the customer sees **paid**, the studio sees **waiting for production**; press
**Send to production** on **Shop → Orders** or **Work → Workshop**, then approve at the Desk
before downloading the cutting-table DXF), then paste the live key.

## Safety and limits

- Every visitor (by address) may ask a few things a minute: 40 proposals and matches, 10 orders,
  10 photos with an order an hour; 10 photo/link suggestions an hour and 20 a day; and at most
  € 0.50 of AI cost a day (`suggest.visitor_eur_day` in config/defaults.yaml). Then they choose
  by hand. The month's AI budget still applies on top.
- Forms carry a hidden field that only robots fill in; such a request is refused.
- The website sends strict security headers on every page (no scripts from elsewhere, no
  framing, https only). Nothing of Cover Studio can be reached through the shop's address.
- No tracking and no cookies, so there is no cookie banner. The fonts still come from Google
  Fonts (the cookies page says so) until they are hosted by ourselves.

## Search engines and sharing

Every page has its own title and description (in every language; Shop → Website (AI) edits
them as `meta.pages.<page>`), its own address for Google, and links to its other languages.
`/sitemap.xml` lists every public page; `/robots.txt` keeps the API, the B2B shop and the
customers' own pages out. When the shop is shared (WhatsApp, LinkedIn, …) it shows
`/brand/og-shop.png`, or the share picture (`og_image`, Settings → Company & shop; 1200×630).
The preview (preview.s2dio.living) is never indexed.

## Checking it

`apps/web/e2e/b2c.py` opens every consumer page on a desktop and a phone (390 px), checks the
price note and the checkout, and saves screenshots (usage in its docstring). The Worker's own
tests: `cd apps/site && npm test`.
