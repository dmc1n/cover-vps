# The consumer webshop (B2C, public)

The shop for consumers is at **https://shop.s2dio.living** (ADR-066, ADR-103). Everyone can use
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

## The legal pages: drafts until you approve them

Each legal page shows a draft that starts with a red **CONCEPT — TER GOEDKEURING** line, in
Dutch and English (German and French visitors see the English one until it is translated).

1. Fill in the company details: Admin → **Shop settings** → company (name, legal name, street,
   postcode, city, KvK, VAT number, e-mail, phone). They appear in the texts at once; anything
   still empty shows as "[nog in te vullen: …]".
2. Have the texts read. The drafts are in `config/shop_legal.json`.
3. Publish your own text: Admin → **Website (AI)**, for example "zet als algemene voorwaarden
   (legal.terms.nl) deze tekst: …", check the preview, **Publish**. From then on that page
   shows your text and the draft is gone. A line starting with `## ` is a heading, `- ` a list
   item, an empty line a new paragraph.

Made to measure has no right of withdrawal; a cover from our standard range (chosen through
"we already have a cover that fits") keeps the 14 days by law. The checkout's checkbox says
which applies.

## Prices

The prices are the **B2C** list of the published price set (Admin → **Prices & costing**,
docs/handbook/prices.md), incl. VAT. While that set is marked **indicative**, the configurator
and the checkout say so plainly ("Indicatieve prijs — … je betaalt pas na bevestiging").
Publish a set with *indicative* off when the prices are final; the note disappears.
Delivery per country (Shop settings → shipping) is added at the checkout and shown before the
order.

## Payments (Mollie)

Shop settings → payment → Mollie key:

- empty: orders are placed and wait for payment (bank transfer; **Into production** by hand);
- `test_…`: Mollie's test mode; the checkout says "Testbetalingen: er wordt geen geld
  afgeschreven";
- `live_…`: real payments.

To go live: finish the Mollie account, place one test order with the test key end to end
(pay, the order turns *paid*, it goes into production), then paste the live key.

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

Every page has its own title and description (in every language; the Website (AI) tab edits
them as `meta.pages.<page>`), its own address for Google, and links to its other languages.
`/sitemap.xml` lists every public page; `/robots.txt` keeps the API, the B2B shop and the
customers' own pages out. When the shop is shared (WhatsApp, LinkedIn, …) it shows
`/brand/og-shop.png`, or the picture set as `og_image` in Shop settings (1200×630).
The preview (preview.s2dio.living) is never indexed.

## Checking it

`apps/web/e2e/b2c.py` opens every consumer page on a desktop and a phone (390 px), checks the
price note and the checkout, and saves screenshots (usage in its docstring). The Worker's own
tests: `cd apps/site && npm test`.
