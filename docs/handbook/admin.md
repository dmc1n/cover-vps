# Users, approvals, Settings and the Shop pages

Cover Studio is on the internet at **https://covers.suns.nu**. Everyone logs in with their own
account; nothing can be seen or changed without one. This page is for admins: the people,
the approval of the definitive drawing, the **Settings** page and the **Shop** pages. The map
of the studio: [navigation.md](navigation.md).

## Logging in for the first time

An admin makes your account and sends you an invitation in English (by mail when the mail
server is set, or the link copied by hand). It says what Cover Studio is, gives your user name
and a personal link, valid for 7 days, that works once. Open it, choose a password of at least
12 characters (not your user name), and you are logged in. Forgot your password? Ask an admin
(Settings → Users & rights → Reset password, then confirm); the old password stops working.

Where you land after logging in: [navigation.md](navigation.md), *Where you start*.

## Inviting people (for example for a kickoff)

Settings → Users & rights:

1. Add everyone (user name, name, e-mail, role, may approve). Untick **send the invitation
   now** to add people first and invite them all at once later.
2. Optional: write a line for the top of the mail in **Invitations**, for example the date and
   time of the kickoff.
3. **Invite everyone not yet in** sends the invitation to everyone with an e-mail address and no
   password yet. **Send invitation** in the list sends it to one person; **Send again** gives a
   new link (the old one stops working).

The column **Access** shows who has a password, who is invited (and until when the link works)
and who is not invited yet. The invitation links to the short guide **How Cover Studio works**
(`#/guide`, readable without logging in).

After five wrong passwords your account waits 15 minutes **on that computer's address** (each
further wrong one doubles the wait, at most 4 hours); from anywhere else you can still log in, so
someone guessing cannot lock you out. Ten wrong tries from one address block that address for a
while. A user name that does not exist gets exactly the same answers (ADR-123).

**The login code by mail is on by default and fails closed** (ADR-123): if no mail server is set
(or its settings are removed), nobody can log in with a password alone; the login page says to
ask an admin. The way in, on the server:

```
COVER_DATA_DIR=~/cover-data uv run cover-users invite rick          # a link: new password, logged in
COVER_DATA_DIR=~/cover-data uv run cover-users two-factor status|off|on
```

A test copy of the data without mail needs `cover-users two-factor off` first. At most 8 login
codes an hour are mailed to one person; a password change, a reset link and switching a user off
end the codes still open.

## Roles and rights

| role | may |
|---|---|
| viewer | look at everything and download files |
| editor | also upload models, calculate, change a cover's settings and seams; draft the website; look at Prices |
| admin | also Settings (users, rights, mail, keys, system, logins, audit log), the Shop pages, and change and publish Prices |

Besides the role, an admin sets per user **may approve**: only those users can approve the
definitive drawing of a cover. Who approves at the **Desk** is a separate list, the setting
`desk.approvers` (plus every admin; see [desk.md](desk.md)). Whether these become one list and
one approval is still open with the owner (#83, #84). There is no separate workshop role yet
(open owner question #92); the Workshop page is open to every role
([workshop.md](workshop.md)). Exactly which page each role sees: [navigation.md](navigation.md).

## Approving the definitive drawing

On every cover with cut pieces there is a block at the top of its page (above the tabs; its
state is also in the cover's status strip):

- **not approved yet**: an approver presses *Approve the definitive drawing* (with a note if
  wanted). The approval belongs to the current revision. *Approved size drawing* and *Approved
  cutting list* are copies with "APPROVED name date revision" on every page.
- **approved by … on …**: the cover may be cut. Its status is *production*.
- **changed after the approval**: the cover was calculated again and the files are different;
  approve again before cutting.

An editor who may not approve presses *Ask for approval*: the approvers get a mail with the
link. Status *production* can only be set with a valid approval.

This approval is separate from the Desk's **Approve** (open owner question #83/#84: one
approval or two steps).

## Settings

**Settings** in the top bar (admins only, `#/settings/<tab>`): one page with vertical tabs in
four groups. Every row has a plain name, one line of help and where the value comes from
(default, changed, empty). **Only changed values** filters the rows; **Save** and **Undo
changes** sit at the bottom; leaving with unsaved changes asks first. The shop's settings are
the same stored values as before; nothing moved in the data.

**Business**

- **Company & shop**: the company (name, legal name, address, Chamber of Commerce and VAT
  number, e-mail, phone, IBAN), the website's domain, languages, colours offered, barbecue
  covers on or off (`bbq_enabled`), logo, share picture (`og_image`), the delivery promise per
  language, the balloon and frame products, shipping per country (a table) and, under
  *advanced*, the film and the scroll story (below, *The film*).
- **Selling**: *Matching and direct orders*: mode (learning or automatic), the thresholds
  with the value that applies, the discount on an existing cover; how a match is scored
  (read-only), see *Matches* below. *B2B terms*: minimum order, shipping per order, payment
  term, into production at once ([b2b.md](b2b.md)).

**Prices & costs** (editors see these three, to look): **Costs**, **Price rules**, **Publish &
versions** ([prices.md](prices.md)). One cover's cost and prices are on its Price & shop tab.

**People & work**

- **Users & rights**: add, change role, may approve, active (an inactive user is logged out at
  once), e-mail (who approves at the Desk is matched on the **user name** in `desk.approvers`,
  never on the display name); *New link* / *Reset* makes a password link (shown to copy, and
  mailed when possible); the invitations (above).
- **Rules & defaults**: *Desk & approval* (`desk.*`, `questions.*`, `products.*`) and *Cover
  defaults* (construction, stitching, welding, hem, vents and features, seams): the company defaults
  from `config/defaults.yaml`, read-only here. Whether the owner will change some of them here
  himself is open owner question #93.

**Connections**

- **Mail & notifications**: who gets which mail, in one list (configurator requests, server
  alerts and B2B, new orders and shop messages, the fit question to customers and after how
  many days, approval requests, the question digests, AI spending warnings), the outgoing
  mail server (SMTP: server, port, security, user name, password, sender), a test mail, the
  login code by mail, the public address used in links.
- **Website & API keys**: the website's key (*New website key*, shown once), the shop on this
  server only for the website (`website_link.closed`), the scroll story as the home page
  (`home_story`), payment (the Mollie key, masked, with *Replace* to give a new one; bank
  transfer), the configurator in a webshop and the API keys ([webshop-api.md](webshop-api.md)).
- **AI & spending**: this month's spend, the budget and limits, which AI does what, the photo
  suggestion limits (read-only); the **Photo test**: a photo suggestion step by step (image
  search, identification, searches, scores; each test costs about € 0.03).

**Server**

- **System & logs**: version, engine, disk, last backup, the releases, mail and AI state, open
  problems and the last alerts (the alert address itself is under Mail & notifications);
  **Mail**: the outbox (mails waiting for another try and failed ones, with the last error and
  **Send again**) and the last send attempts, without their texts (ADR-129, [server.md](server.md));
  who is logged in, since when and from where; every login, failed login, change and approval,
  with who and when.

## The Shop pages

**Shop** in the top bar: only what is about the shop as a whole (ADR-126). Orders, Requests
and B2B customers are for admins; **Website (AI)** is also for editors (they draft, an admin publishes). The shop itself is
at **/shop/** (the landing page, the configurator, checkout and the order status) and on the
website's own domain; the public consumer shop: [webshop.md](webshop.md).

- **Orders** (`#/shop/orders`): every order with its customer, cover, total and status. The
  search in the top bar finds an order by number, customer or product and opens this page with
  that order highlighted (`#/shop/orders/<n>`).
  - A paid order goes into production by itself: its pattern, then the drape. **Into
    production** does it by hand (for a payment by bank transfer).
  - Changing the status mails the customer.
  - B2B orders have a green **B2B n · PO …** mark ([b2b.md](b2b.md)).
- **Requests** (`#/shop/requests`): what customers asked, on one page: *which existing cover
  fits* (the match requests, learning mode, below; was its own page Matches) and the *quotes
  from the configurator*. Who gets them by mail is under Settings → Mail & notifications; the
  embed addresses and API keys under Settings → Website & API keys. One cover's orders, quotes
  and match requests are also on its Price & shop tab.
- **B2B customers** (`#/shop/b2b`): companies, their logins and orders ([b2b.md](b2b.md)).
- **Website (AI)** (`#/shop/website`): type what should change on the site, in plain words, for
  example "add a question about delivery time: about three weeks". The AI changes the draft in
  Dutch and English. Open the preview, then **Publish** (or **Discard**). Earlier versions can
  be brought back. The same works on the server: `cover-site "…"`, `cover-site --publish`.
  Editors draft and check the preview; an admin publishes.
- **Tools → Photo test** (`#/shop/phototest`, ADR-112): try the shop's "start from a photo or a
  link" yourself and see every step: what Google's search by image found (its best guess, the
  pages that show your photo, the names of the matching pictures), what Gemini recognised
  (brand, model, sizes), the web searches, each found picture held against your photo with its
  score, which one was picked and the final answer, plus the time and the cost (about €0.03).
  Nothing is kept: the photo is only used for the test and the result only shows on your
  screen. Use it when a customer says a photo was read wrongly: try the same kind of photo and
  read where it went wrong. A photo found on the web (a shop's picture) is recognised almost
  always; a photo taken at home is found by Google's search by image only when a similar
  picture is online.

The prices the shop uses are under **Prices** (versioned, B2C and B2B;
[prices.md](prices.md)).

### The film

Settings → Company & shop, *advanced*: **film_url** (H.264), **film_av1** (the same film in
AV1, smaller and sharper where the browser plays it) and **film_poster** (its first frame). For
the scroll story the same three are `story_media.hero`, `hero_av1` and `hero_poster`. The film
files go in the data folder's `media/`; a new film gets a new name (`hero-kota2-…`), because the
website keeps `/media` files for a day. How the film is made: ADR-108 (`scripts/film/`).

## Matches: which existing cover fits (learning mode)

- **The customer enters their sizes in the configurator.**
  - **Learning mode** (Settings → Selling, mode *learning*, stored as `shadow`; the default):
    the customer leaves an e-mail address. You get a mail, and the request appears under
    Shop → **Requests** with the best covers, their percentage and the difference per size in
    cm (+ is roomier).
  - Press **Take N %** for the proposal, **Custom**, or type another cover (`suns-…` or
    `drawing-…`) and press **Choose**. A note for the customer is optional.
  - The customer gets a link to the proposal, in their own language, and can order the existing
    cover or a custom one.
- **Every change you make is a lesson.** The table **What we learn** shows, per match band,
  how often the proposal was changed, the fit answers of customers (1–5) and the returns.
  When a band fits well, set the threshold (Settings → Selling, *Offer the existing cover
  from*, `threshold_pct`) and, when you trust it, mode *automatic* (`auto`): customers then see
  the match at once.
- **Drawing covers are offered too** (ADR-114): every drawing cover approved or produced at the
  Desk, as the kind of furniture the price list says (Settings → Publish & versions → Import keeps your list;
  its column "Type nr." is the drawing code), else the product list's name, else its shape. The
  customer sees the price list's name, never "drawing-t1"; it sells at its fixed B2C price, or
  at the configurator's price minus the stock discount. Reject a cover at the Desk and it is no
  longer offered.
  - **The review list:** `COVER_DATA_DIR=~/cover-data uv run python scripts/matchcards.py`
    writes `out/matchcards/review.csv`: every drawing cover, its kind, how that was decided,
    the sizes, left or right, and why a cover is held back.
  - **Doubtful covers are held back** (sources disagree, the list's sizes differ, a U or curved
    shape, Ibiza style, one code on two covers). To confirm or correct one, add to its
    cover.json `"match": {"kind": "corner_sofa", "side": "left"}` (kinds: dining_set,
    round_set, sofa, corner_sofa, lounger, item; `"none"` keeps it out; `"chairs": true` for
    tables).
- **The fit question:** Settings → Mail & notifications, *Ask customers whether the cover
  fits* (`fit_mail`). Switch it on and set the days. It needs the domain and the mail server. A
  shipped order then gets one question by mail; the answers appear under Requests, and for
  covers sold from the shop also on Work → Workshop ([workshop.md](workshop.md)).

## Languages

- Settings → Company & shop, *Languages* (`languages`): for example `nl,en,de,fr`. The first is
  the main language.
- Shop → Website (AI), **Translate missing languages**: DeepSeek fills them into the draft.
  Check the preview (switch the language at the top right), then **Publish**.
- Every text, buttons included, can be changed by an instruction in the command line, in all
  languages at once.

## The website on its own domain (Cloudflare)

The website is a different brand on its own domain. It shows the shop, and everything about
covers comes from this studio (ADR-066).

1. **Settings → Company & shop:** set the website's domain (`domain`, for example
   `example.com`) and, optionally, the logo (`logo_url`).
2. **Settings → Website & API keys:** make the website key (*New website key*, or
   `POST /api/admin/shop/link-key`). It is shown once.
3. **On the server, in `apps/site/`:**
   - `npx wrangler login` (or set `CLOUDFLARE_API_TOKEN`);
   - `npx wrangler secret put LINK_KEY` and paste the key;
   - in `wrangler.toml`, the `routes` line with the domain;
   - then `npm run deploy` (after `make web-build`).
4. **Check the website.** Then switch on *The shop here only for the website*
   (`website_link.closed`, Settings → Website & API keys): the studio's `/shop/` is then only a
   preview for colleagues, and visitors go to the website.

## The website's look

The website has one design system (ADR-105): warm paper, sand and a warm ink, Work Sans.
Colours, sizes and spacing are set once, at the top of `apps/web/src/shop/shop.css`
(`--paper`, `--sand`, `--ink`, `--fs-h1`, `--gutter`, ...); change a value there and every page
follows. Texts are not in that file: they stay in the AI CMS (Shop → Website (AI)). The font is
served by our own site, so no visitor's browser asks Google for it.

### Is the website fast, and does the rain fall? (ADR-106)

Three browser checks look at the website's pages the way a visitor's browser does. They run
against the preview, or against a fresh build on this machine (`make web-build`, then
`node apps/web/e2e/site_serve.mjs --port 18300`, which shows this build with the preview's data):

- `apps/web/e2e/site_rain.py`: in the rain chapter of the scroll story the rain keeps falling,
  also after standing still, scrolling back and forth, another tab, and on a phone;
- `apps/web/e2e/site_3d.py`: the 3D's code (three.js) loads only on the pages that show 3D, the
  configurator's model fades in without the page jumping, and a new size never empties the view;
- `apps/web/e2e/site_perf.py`: load times, sizes and frame rate on a desktop and on a mid-range
  phone over slow 4G, with a screenshot of each page.

How to start each is at the top of the file. The pictures go to `out/sitepolish/`.

## From the command line (the server)

```
COVER_DATA_DIR=~/cover-data uv run cover-users list
COVER_DATA_DIR=~/cover-data uv run cover-users add <name> --name "Full Name" --email … \
    --role editor [--approve]
COVER_DATA_DIR=~/cover-data uv run cover-users invite <name>      # a new password link
```

The drape simulation, the water on the draped cover and *Your reference* (compare with your
own drawing or model) are on a cover's page: [web-app.md](web-app.md).
