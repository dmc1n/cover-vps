# Dealer embed: our configurator on a dealer's own website (ADR-150)

The owner (Rick, 20 Oct 2026): B2B dealers and partners put the cover configurator on their own
website, fully customised by the dealer. Preview only until his go; nothing on the live shop.

His decisions the same day:

- **Who embeds it:** B2B dealers and partners. Each dealer has a key linked to its company (a
  B2B customer, ADR-104), and its domains are allow-listed.
- **Checkout, chosen per site:** either the end customer pays in *our* checkout under the
  dealer's look, or the order is *sent to the dealer* (the dealer sells and invoices, we make).
- **Prices:** the dealer sets its own: our B2B price (ex VAT) plus the dealer's margin %, or its
  own price list. Our B2B price never reaches the end customer, nor the page.
- **Fully customised:** colours, fonts, logo, texts and language, which furniture kinds and
  fabrics appear, the layout (compact or full), with or without 3D, and the end-of-flow action.

## The approach: a Web Component, with an iframe as the fallback

One script tag from the shop's domain and one element:

```html
<script type="module" src="https://shop.s2dio.living/embed/v1/configurator.js"></script>
<s2dio-configurator dealer="dpk_…" lang="nl"></s2dio-configurator>
```

For a site builder that refuses scripts (Wix, Squarespace, some WordPress hosts), the same
configurator in a frame:

```html
<iframe src="https://shop.s2dio.living/embed/v1/frame?dealer=dpk_…&lang=nl"
        style="width:100%;height:900px;border:0" title="Cover configurator"></iframe>
```

### Why a Web Component first

| | Web Component | iframe only |
|---|---|---|
| Looks like the dealer's site | inherits the page's font; CSS custom properties, `::part()` and attributes theme it from the dealer's own stylesheet | only what our settings page offers; the dealer's CSS cannot reach in |
| Height | grows with its content, no inner scroll bar | a fixed height, or a resize script on the dealer's page (which the script-less builders do not allow) |
| Hooking the dealer's cart | DOM `CustomEvent`s on the element, as any other element | `postMessage` only, a listener script on the dealer's page |
| SEO and accessibility | in the page's own document and focus order | a separate document, a second tab order |
| Isolation | shadow DOM: our styles do not leak out and theirs do not break ours; but our script runs in their page | strongest: a separate origin and document |
| Works without the dealer running scripts | no | yes |

The component is what a dealer with a normal site wants; the frame is for the builders that
do not let them add a script. Both are the same code (the frame page hosts the component), so
they never drift apart. A plain iframe would be simpler to secure but looks foreign on the
page, cannot grow, and makes a cart integration a postMessage exercise for every dealer.

### Theming

Three layers, later wins:

1. **The dealer's saved theme** (the studio's settings page, below): colours (primary, accent,
   text, background, surface, border), corner radius, font and heading font (default `inherit`:
   the page's own), logo, layout, 3D on/off, texts per language.
2. **Attributes on the element:** `lang`, `layout="compact|full"`, `view3d="off"`,
   `kinds="sofa,lounger"` and `colours="Navy,Taupe"` (only a subset of what the dealer's
   settings allow; never more).
3. **The dealer's own CSS:** custom properties (`--s2dio-primary`, `--s2dio-accent`,
   `--s2dio-text`, `--s2dio-bg`, `--s2dio-surface`, `--s2dio-border`, `--s2dio-radius`,
   `--s2dio-font`, `--s2dio-heading-font`) and parts (`s2dio-configurator::part(button)`;
   parts: root, header, logo, title, intro, kinds, kind, fields, field, label, input, colours,
   colour, viewer, price, button, primary, form, message, footer).

We never load fonts ourselves (no Google Fonts from our script: the dealer's page and its
privacy policy decide that); a named font must be on the dealer's page already.

## Security

- **Two keys per dealer site.**
  - The **public key** `dpk_…` sits in the snippet and only names the site. It is not a secret:
    everything it opens (the theme, the texts, the dealer's end prices) is public on the dealer's
    own site anyway.
  - The **secret key** `dsk_…` (shown once, rotatable, stored as SHA-256) is for the dealer's own
    server: it reads a quote's details back to check what a browser claimed (`GET
    /api/embed/v1/verify/<quote>`), so a cart never trusts a price from a browser event. It
    never goes into a page.
- **Domains, the allow-list.** A site lists its origins (`https://www.dealer.nl`). Every API
  call carries the public key in its path, so even a CORS preflight is checked per dealer: the
  API answers with `Access-Control-Allow-Origin: <that origin>` only for a listed origin (and
  for our own website, which hosts the frame and the checkout); any other `Origin` is a 403
  before anything runs. A POST without `Origin` is refused (browsers always send it). A
  non-browser can forge `Origin`, so the allow-list stops other *websites* from showing a
  dealer's configurator, not scrapers; that is why nothing behind the public key is secret.
- **Frames.** The frame page sends `Content-Security-Policy: frame-ancestors` with exactly the
  site's listed origins (no `X-Frame-Options`, which cannot list several); the rest of the shop
  stays `frame-ancestors 'self'`. The frame talks to its parent with `postMessage` addressed to
  the listed origin it is framed by (never `*`).
- **No B2B price in any answer.** The dealer's price is computed on the server: `b2b.unit_price`
  (the company's list, its fixed prices) × (1 + margin %) + VAT, rounded; or a price list. The
  B2B price, the margin, the cost and the costing stay in the quote file on the server. Answers
  are built from a whitelist (amount, currency, VAT included, VAT %), and a test walks every
  answer, the config, the 3D file and the hosted pages for the B2B amount and for the words
  cost, margin, b2b, net and costing. A dealer's own list may never be the company's purchase
  list (`b2b` or the company's `price_list`): refused when saved and when priced.
  (Arithmetic remains: whoever knows the margin can divide. The margin itself is never sent.)
- **Below cost of purchase.** In our-checkout mode an end price below the dealer's B2B price
  (ex VAT) is refused at checkout: we would sell under our own B2B price.
- **Limits** (all `limits.embed_*`, server-only, defaults.yaml): per address per site a minute;
  per site a day (quotes); order and checkout attempts per address an hour and per site a day;
  the shared `limits.quotes_per_minute` for every proposal. Over a limit: 429 with
  `Retry-After`.
- **Spam on orders.** The hosted checkout has Turnstile (our domain). The dealer-mode form on
  the dealer's domain cannot use our Turnstile key, so it has a honeypot, the per-address and
  per-site limits, and the dealer confirms each order before it becomes a B2B order.
- **Preview only.** Everything answers only where `dealer_embed_enabled` is on (a shop setting,
  off), on the preview website (`preview.<domain>` with the Worker's key) or for a logged-in
  colleague. The Worker passes `/embed/*` and `/api/embed/*` only on the preview or with
  `DEALER_EMBED = "1"`; on live they are a 404 at the edge.

## Events (hooking the dealer's own cart)

The element dispatches `CustomEvent`s (they bubble and cross the shadow root), and the frame
posts the same to its parent as `{source: "s2dio-configurator", type, detail}`:

| Event | When | `detail` |
|---|---|---|
| `s2dio:ready` | config loaded | `{dealer, lang}` |
| `s2dio:priced` | a price is on screen | `{quoteId, product, sizes, colour, support, price: {amount, currency, vatIncluded}}` |
| `s2dio:added-to-cart` | end action "cart" | the same as priced: the dealer's script puts it in its cart and checks it server-side with the secret key |
| `s2dio:checkout-started` | our checkout opened | `{quoteId, checkoutUrl}` |
| `s2dio:order-sent` | dealer mode, the customer's order sent | `{reference, quoteId}` |
| `s2dio:error` | an API error | `{code, message}` |

`event.preventDefault()` on `s2dio:checkout-started` stops the component from opening the
checkout itself (the dealer opens it where it wants).

## The dealer settings page in the studio

Shop → Dealer embeds (admins). One card per dealer site, linked to a B2B company:

- **Domains** (origins, one per line), **active** on/off.
- **Look:** colour pickers, radius, fonts, logo URL (https), layout, 3D, with a **live
  preview**: the real component on the page, its draft theme and texts applied as you type
  (prices from the saved settings).
- **Texts and languages:** the default language, which of nl/en/de/fr, a title, intro, button
  and thank-you text per language (empty: ours).
- **Range:** which furniture kinds and which fabric colours.
- **Prices:** margin % over the company's B2B price (with per-kind margins), or a price list
  (a channel in the published price set, Settings → Prices; never the company's purchase list);
  rounding; shown incl. or ex VAT. An example line shows what the dealer buys at and what the
  customer sees (only here, to us).
- **Checkout:** ours (under the dealer's look) or the dealer's; the end action ("checkout",
  "send order to the dealer", "add to the dealer's cart" by event); the return address after
  payment; shipping (the customer pays our rate, or it is in the price); whether the dealer
  confirms each order first; where the dealer's orders are mailed.
- **Snippet:** the script tag and element, and the iframe, ready to copy; the public key; the
  secret key (made or rotated here, shown once).
- **Analytics:** per day for 30 days: loads, prices, checkouts started, orders sent, carts,
  paid orders and their value.

Phase 2: the same editor for the dealer itself in the B2B shop (its own login), with our
admin's approval of the domains.

## Order flow

**Our checkout (`checkout: ours`).** The customer prices a cover; "Order" asks the API for a
checkout (`POST /api/embed/v1/<dpk>/checkout`) and opens our hosted checkout
(`/embed/v1/checkout/<token>`, 2 hours) in the same tab. That page has the dealer's colours,
font and logo and our terms; the customer gives name and address, accepts the terms, passes
Turnstile and pays with Mollie as in our shop. The order is a normal shop order (`orders`,
`awaiting_payment` → paid → waiting for Send to production, ADR-128) carrying `dealer`
(site, company, the end price, the B2B price, the margin for settlement). After paying, our
status page in the dealer's look links back to the dealer's return address (only a listed
domain). We invoice the customer; the dealer's margin is settled with the dealer (owner's
question: how and when).

**Sent to the dealer (`checkout: dealer`).** "Send" shows a short form (name, e-mail, phone,
address, a note) in the component; `POST /api/embed/v1/<dpk>/order` stores it
(`dealer_orders`, status `sent`), mails the dealer (the configuration, the customer's details,
the customer's price and the dealer's B2B price ex VAT) with a confirm link, and the customer a
short "sent to <dealer>" mail in its language. The dealer confirms (or declines) on
`/embed/v1/confirm/<token>`: confirming makes a B2B order on account at the dealer's B2B price,
exactly as in the B2B shop, waiting for Send to production. With `dealer_confirms` off the order
is on account at once. The dealer invoices its customer.

**Add to the dealer's cart (`end_action: cart`).** No form: `s2dio:added-to-cart` carries the
quote; the dealer's cart checks it with the secret key and orders from us later (B2B shop, API).

**Shipping** in our checkout: the customer pays our shop's rate (default) or it is in the price
(the dealer's setting). In dealer mode the B2B terms hold (Settings → Selling). Owner's question.

## Languages

nl, en, de, fr. The component's texts come from the server (`config/embed_texts.json`, the
dealer's own texts per language on top); the kinds' and sizes' names from the shop's own
translated content. The language: the element's `lang`, else the site's default, else the
browser's, within the site's chosen languages. The hosted checkout, the status page and the
mails follow the customer's language; the dealer's mail and confirm page are in the dealer's.

## Analytics per dealer

`dealer_usage` (day, site, event, count; nothing else: no addresses, no cookies, no visitor
ids): `load`, `quote`, `checkout`, `order`, `cart`. Paid orders and their value come from the
orders themselves. Shown on the settings page; the dealer's own view comes with phase 2.

## Phase 1 (this branch)

1. The settings (API + studio page) and the dealer pricing (B2B + margin, a price list).
2. The component (`apps/web/src/embed/`, its own Vite build into `dist/embed/v1/`), with 3D
   loaded only when on, served by the Worker.
3. Both checkout modes (hosted checkout; dealer orders with confirm), and the cart event.
4. The iframe fallback (`/embed/v1/frame`).
5. `preview.s2dio.living/embed-demo`: two made-up dealer sites, themed differently, with the
   built-in demo dealers (`config/embed_demo.json`; they answer only on the preview or for a
   colleague, price at the B2B list plus their margin, and never make an order).

Later: existing covers (the match) in the embed; the dealer's own editor in the B2B shop; a
signed webhook to the dealer's server for orders; per-dealer limits; the dealer's analytics
view; a settlement report of margins (after the owner's answer).

## Open questions for the owner

1. Our checkout: how is the dealer's margin settled (monthly credit note, payout, invoice)?
2. Shipping in dealer mode and in our checkout: who pays, the customer or the dealer?
3. Do dealers pay a fee for the embed (a monthly fee, a share per order, free)?
4. Must the dealer confirm each sent order before it becomes a B2B order (default: yes)?
5. Who edits a dealer's look: only us (phase 1) or the dealer itself in the B2B shop?
6. May a dealer sell below our consumer price in its own shop (a minimum price)?
