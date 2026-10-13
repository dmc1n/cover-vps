# Finding your way in the studio

The studio has **four sections** in the dark bar at the top (ADR-122, ADR-124, ADR-126, ADR-128). Each has its
own pages in the light bar under it (the sub-menu). Every page, every tab of a cover and every
tab of a Desk card has its own address. So a link in a mail, a bookmark or this handbook opens
exactly that page, and the browser's Back button goes back one tab.

The index of the whole handbook, in the same order: [README.md](README.md).

## The map

```
Work        Desk · Questions · Workshop
Covers      All covers · Arrangements · New cover | Learning · Product list
Shop        Orders · Requests · B2B customers | Website (AI)
Settings    one page with vertical tabs (admins; editors: the three Prices & costs tabs)
Right side  Search (everything) · Guide · theme button · your name (My account) · Log out
```

**One cover, one page** (ADR-126): everything about one cover — its cost, prices, fixed price,
place in the shop, B2B prices, orders, its Desk status, fit and questions — is on that cover's
page. The general settings (prices and costs too) are in Settings. Nothing about one cover is
repeated elsewhere; lists (All covers, Orders, Requests) link to it.

A number beside **Work** and **Questions** counts the open questions; it is red when one waits
for you.

## The right side of the bar

- **Search** finds everything, not only covers. Type a few letters:
  - **covers** by name, tag, note or family (opens the cover);
  - **Desk** codes and product names (opens the Desk card);
  - **questions** by title or number (opens the question);
  - **orders** by number, customer or product (admins only; opens Shop → Orders with that
    order highlighted, `#/shop/orders/<n>`).

  **Ctrl+K** (**Cmd+K** on a Mac) puts the cursor in the search box. The arrow keys and
  **Enter** open a hit; **Escape** closes the list.
- **Guide**: the short tour of the studio ([how-it-works.md](how-it-works.md), `#/guide`, also
  readable without logging in).
- **The theme button** (the round button left of your name): the studio has a light and a dark
  theme. By default it follows your computer's setting. Each click goes one step further:
  **As the computer** (◐) → **Light** (☀) → **Dark** (☾). The choice is remembered in that
  browser only. Drawings, flat patterns and pictures stay on a white ground in both themes, and
  the 3D view keeps its light stage. The customers' configurator (`#/configure`) is always
  light.
- **Your name** opens **My account** (change your password).
- **Log out**.

## Where you start

- **The workshop login** starts on **Work → Workshop** (ADR-128).
- **Approvers** (users marked **may approve** and the user names in `desk.approvers`) start
  on **Work → Desk**.
- **An admin** starts on the page he was on last (remembered in that browser); the first time
  on Work → Desk.
- **Everyone else** starts on **Covers → All covers**.

(Open question for the owner, Q3: is this the right start page per person?)

## Who sees what

| section | viewer | editor | admin | workshop |
|---|---|---|---|---|
| Work: Desk, Questions | look | look (approving: approvers only) | everything | look; comments, pictures, fit measurements and its own questions |
| Work: Workshop | look (without the customers' fit answers) | look; Send to production | look; Send to production | look; approved files, no prices or customers' fit answers |
| Covers: All covers, Arrangements, Learning | yes | yes | yes | – |
| Covers: New cover, Product list | – | yes | yes | – |
| Shop: Website (AI) | – | draft and preview | also publish | – |
| Shop: Orders, Requests, B2B customers | – | – | yes | – |
| A cover's own page | yes | yes | yes | – |
| A cover's Price & shop tab | – (a note) | look (no orders, no B2B) | everything; set a fixed price in the draft, publish | – |
| All covers with prices | – | yes | yes | – |
| Settings → Prices & costs (Costs, Price rules, Publish & versions) | – | look | change and publish; Import (Excel) | – |
| Settings, every other tab (Photo test inside AI & spending) | – | – | yes | – |

A page that is not for your account says **Not for your account**. The workshop login sees
**Work** only: **Desk**, **Questions**, **Workshop**. Its cover pages and every other section
say **Not for your account**. It cannot approve, reject, mark Produced, Undo, correct covers,
start the AI or Send to production (ADR-128). The server checks the same rights on every
action, whatever the menu shows.

## One look

The whole studio uses one font (Work Sans), rectangular buttons and at most one main (dark)
button per view. There are four kinds of page:

- **a list with a filter row** (All covers, Workshop, Orders, …);
- **a queue with the detail beside it** (Desk, Questions);
- **an object page** (a cover);
- **a settings form** (Settings).

## The pages

### Work

- **Desk** (`#/work/desk`, a card `#/work/desk/<cover>`): the queue on the left, the card on
  the right in four tabs, each with its own address:
  - **Check** (`…/<cover>`): the latest rejection and what happened since, the drawing beside
    our cover in 3D, the products, what the program read and what the AIs say;
  - **Pieces & revisions** (`…/<cover>/pieces`): the pieces and the revisions ("cut this");
  - **Correct this cover** (`…/<cover>/correct`): seams, vents, sizes, shape, with pictures;
    the drawing and the 3D stay above it;
  - **History** (`…/<cover>/history`): everything that happened, with the pictures.

  The decision bar stays at the bottom of the screen: **Approve**, **Reject**, **Comment**,
  **After sewing ▾** (Produced, a note, Measured…, Fits, Does not fit) and **Undo**. The keys:
  `j` `k` move, `a` approve, `r` reject, `c` comment, `p` produced, `u` undo. **More** (top
  right of the card): Let the AI read it (costs about 1–5 cents), the check list, Edit
  arrangement, the cut pieces and DXF, the product list. The AI spend tile is shown to admins
  only (Settings → AI & spending has the details). Everything about the Desk:
  [desk.md](desk.md).
- **Questions** (`#/work/questions`, one question `#/work/questions/<n>`): the owner's and the
  workshop's questions, answered in the studio ([desk.md](desk.md), *Vragen beantwoorden*).
- **Workshop** (`#/work/workshop`): every cover the Desk approved or marked produced, with its
  files, the revision to cut and how it fitted. The Orders block at the top shows orders
  waiting for production or in production. Editors and admins can **Send to production**. See [workshop.md](workshop.md).

### Covers

- **All covers** (`#/covers/all`): every model and its cover, as a **Table** or as **Cards**
  (`#/covers/all?view=cards`). One filter row for both views, selection and the batch bar. In
  the Table, **Prices: live / draft** (editors and admins) adds cost, B2C, B2B, margin and
  source per cover (`?prices=live`); a price opens the cover's Price & shop tab. See
  [catalogue.md](catalogue.md) and [prices.md](prices.md).
- **Arrangements** (`#/covers/arrangements[/<arr-id>]`): furniture placed together under one
  cover, with *Send to the Desk* ([arrangements.md](arrangements.md)).
- **New cover** (`#/covers/new`): three uploads on one page: a 3D file, a drawing (PDF), and
  reference pairs (a zip) ([web-app.md](web-app.md), [learning.md](learning.md)).
- **Learning** (`#/covers/learning`): the uploaded reference batches and their results
  ([learning.md](learning.md)).
- **Product list** (`#/covers/products`): upload the workshop's product list (Excel); the Desk
  shows the products on each card ([desk.md](desk.md), *The product list*).

### A cover (`#/model/<cover>/<tab>`)

At the top: the picture, the name and sizes, a strip with the cover's grade, its status, its
Desk status (a link to its card), the Desk's approval, a lock when the DXF
waits for the Desk's approval, and "N changes since the run before". Under it **one summary
row**: the Desk (status, who approved, produced), the **fit** (fits / does not fit, sizes
measured, the largest difference), the **workshop** (pieces, vents, the revision to cut, files,
DXF lock) and the **open questions** about this cover (links). The buttons **Run again**,
**Edit details** (category, family, status, tags, notes) and **Desk card ↗**. Under it is the
Desk's approval card (ADR-128), with **Approved size drawing**, **Approved cutting list** and
**Its Desk card**. **Send to the Desk for approval** sends a built cover for review and mails
the approvers; editors and admins see it when the cover is not already waiting there. Old
definitive-drawing approvals remain as history. The stamped downloads disappear when a
change invalidates the approval. A running job, a rejection at the Desk and today's warnings
also stay above the tabs.

Seven tabs; the older tabs are one click away inside them, each with its own address:

| tab | inside | was |
|---|---|---|
| **3D** (`/3d`) | the 3D view | 3D |
| **Pieces** (`/pieces/cut`, `/flat`, `/sizes`, `/files`) | Cut pieces (DXF, cutting list, check list), Flat patterns, Size drawing, Files (every file to download) | Cut pieces, Patterns, Size drawing, Files (a tab of its own until ADR-126) |
| **Seams** (`/seams`) | the seam editor | Seams |
| **Adjust** (`/adjust`) | this cover's own settings | Settings |
| **Compare** (`/compare/drawing`, `/reference`, `/ai`) | Your drawing, Your reference, AI advice | the same three tabs |
| **History** (`/history/changes`, `/revisions`, `/log`) | Approval & changes (since the run before), Revisions, Warnings and log | Revisions, Warnings and log, the "Since the run before" card |
| **Price & shop** (`/price`) | its cost, prices per channel (live and draft), fixed price, margin; the shop; B2B prices; orders, quotes, match requests ([prices.md](prices.md)) | Prices → Costing, the fixed-price list, parts of Orders, Matches and B2B customers |

Another cover always opens on the tab in its own address. More: [web-app.md](web-app.md).

**The 3D toolbar** (on a cover and on a Desk card): **Show ▾** (the layers, with the ones on
named on the button; air vents, vent sizes, overall dimensions; the mouse hint), the quick
toggles **Vents** and **Dimensions**, which cover you look at — **Design · Rain · Drape ·
Unfold** — with **Water** beside it while you look at the drape, **Measure**, then
**Simulate ▾** (Rain again, about a minute; Drape again, about 40 minutes in its own queue; what
is running shows beside it) and **Check list (PDF)**. Your choices are remembered in the
browser.

### Shop (admins; editors: Website (AI) only)

Only what is about the shop as a whole: **Orders** (one order: `#/shop/orders/<n>`),
**Requests** (which existing cover fits a customer's sizes, the learning mode, and the quotes
asked in the configurator, on one page), **B2B customers**, **Website (AI)**. A cover's own
orders, quotes and requests are also on its Price & shop tab. See [admin.md](admin.md),
[webshop.md](webshop.md) and [b2b.md](b2b.md).

### Settings (`#/settings/<tab>`, admins; editors see Prices & costs)

One page with vertical tabs in five groups (a row of tabs on a tablet). Every setting is one
row: a plain name (its stored key small and grey), the control, one line of explanation and
where the value comes from — **default X**, **changed · default X**, **empty**, or for
matching **uses the company default: 90** when the field is empty. **Only changed values**
filters the rows; **Save** and **Undo changes** sit at the bottom of the screen; leaving with
unsaved changes asks first.

| group | tab | what |
|---|---|---|
| Business | **Company & shop** | the company, the shop (domain, languages, colours, barbecues, logo, share picture, delivery promise), support products, shipping per country (a table), *advanced:* film and story |
| | **Selling** | matching: mode (learning / automatic), the thresholds with the value that applies, the direct-order (stock) discount; how a match is scored (read-only); the **B2B terms**: minimum order, shipping, payment days |
| Prices & costs | **Costs** | materials, labour and the exchange rate on one page ([prices.md](prices.md)) |
| | **Price rules** | per channel: extra costs, markup or margin, rounding, VAT; the balloon's and frame's fixed prices; a configurator product's costing |
| | **Publish & versions** | the draft, preview, publish, discard; the versions with roll back; Import a price list (Excel) |
| People & work | **Users & rights** | the users, roles, *may approve*, invitations |
| | **Rules & defaults** | *Desk & approval* (`desk.*`, `questions.*`, `products.*`) and *Cover defaults* (construction, stitching, welding, hem, vents and features, seams), read-only: the developer changes them |
| Connections | **Mail & notifications** | who gets which mail in one list (requests, alerts and B2B, new orders, the fit question, approval requests, the question digests, AI spending warnings), the mail server, the login code, the public address |
| | **Website & API keys** | the website's key, the shop on this server only for the website, the scroll story, payment (Mollie key, masked; *Replace* to give a new one; bank transfer), the configurator in a webshop, API keys |
| | **AI & spending** | this month's spend, the budget and limits, which AI does what, the photo suggestion limits (read-only); the **Photo test** (was Shop → Tools) |
| Server | **System & logs** | release, engine, disk, backup, releases, the last alerts; who is logged in; the audit log |

Rules & defaults and AI & spending show the company defaults read-only. Whether
the owner will change some of them here himself is open owner question #93. More:
[admin.md](admin.md).

## Old addresses

Every old address still works and goes to its new place:

| old | new |
|---|---|
| `#/` | your start page |
| `#/desk`, `#/desk/<cover>` | `#/work/desk`, `#/work/desk/<cover>` |
| `#/questions`, `#/questions/<n>` | `#/work/questions`, `#/work/questions/<n>` |
| `#/models` | `#/covers/all` |
| any address the studio never had | your start page |
| `#/catalogue` | `#/covers/all?view=cards` |
| `#/arrangements[/<id>]` | `#/covers/arrangements[/<id>]` |
| `#/learning` | `#/covers/learning` |
| `#/prices`, `#/prices/materials`, `/labour`, `/rate` | `#/settings/costs` |
| `#/prices/channels`, `#/prices/costing` | `#/settings/pricing` (a cover's costing: its Price & shop tab) |
| `#/prices/import`, `#/prices/versions` | `#/settings/publish` |
| `#/shop/matches` | `#/shop/requests` |
| `#/shop/phototest` | `#/settings/ai` |
| `#/settings/matching`, `#/settings/b2b` | `#/settings/selling` |
| `#/settings/desk` | `#/settings/defaults` |
| `#/settings/activity` | `#/settings/system` |
| `#/website` | `#/shop/website` |
| `#/admin` | `#/settings/users` |
| `#/admin/<tab>` | orders, b2b, website → Shop; webshop, requests, matches → Shop → Requests; phototest → Settings → AI & spending; prices → Settings → Costs; shop → Settings → Company & shop; users, mail, system → Settings; sessions, audit → Settings → System & logs |
| `#/settings` | its first tab you may see (`#/settings/company`; an editor `#/settings/costs`) |
| `#/work`, `#/covers`, `#/shop` | the first page of that section you may see |
| `#/model/<cover>` | `#/model/<cover>/3d` |
| `#/model/<cover>/<old tab>` | `/downloads`, `/files` → `/pieces/files`, `/settings` → `/adjust`, `/patterns` → `/pieces/flat`, `/sizes` → `/pieces/sizes`, `/cut` → `/pieces/cut`, `/drawing`, `/reference`, `/ai` → `/compare/…`, `/revisions`, `/log` → `/history/…` |
| `#/guide`, `#/account`, `#/configure`, `#/welcome/…` | unchanged |

The mails (approval requests, question digests, the arrangements' digest) link to the new
addresses.

## New addresses (this round)

| address | page |
|---|---|
| `#/work/workshop` | Work → Workshop ([workshop.md](workshop.md)) |
| `#/shop/orders/<n>` | Shop → Orders with order `<n>` highlighted (from the search) |
| `#/covers/all?view=cards` | All covers as cards (the table: `#/covers/all`) |
| `#/covers/all?prices=live` (or `=draft`, `=1`) | All covers with every cover's cost and prices (ADR-126) |
| `#/model/<cover>/price` | the cover's Price & shop tab (ADR-126) |
| `#/settings/costs`, `/pricing`, `/publish` | Settings → Prices & costs (ADR-126) |
| `#/settings/selling`, `/defaults`, `/system` | the merged Settings tabs (ADR-126) |
