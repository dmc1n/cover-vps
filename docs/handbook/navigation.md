# Finding your way in the studio

The studio has **five sections** in the dark bar at the top (ADR-122, ADR-124). Each has its
own pages in the light bar under it (the sub-menu). Every page, every tab of a cover and every
tab of a Desk card has its own address. So a link in a mail, a bookmark or this handbook opens
exactly that page, and the browser's Back button goes back one tab.

The index of the whole handbook, in the same order: [README.md](README.md).

## The map

```
Work        Desk · Questions · Workshop
Covers      All covers · Arrangements · New cover | Learning · Product list
Shop        Orders · Requests · Matches · B2B customers | Website (AI) | Tools: Photo test
Prices      Materials · Labour · Exchange rate · Channels & price lists · Import (Excel) | Costing · Versions
Settings    one page with vertical tabs (admins)
Right side  Search (everything) · Guide · theme button · your name (My account) · Log out
```

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

- **Approvers** (Rens, Wout, and whoever may approve at the Desk or approve definitive
  drawings) start on **Work → Desk**.
- **An admin** starts on the page he was on last (remembered in that browser); the first time
  on Work → Desk.
- **Everyone else** starts on **Covers → All covers**.

(Open question for the owner, Q3: is this the right start page per person?)

## Who sees what

| section | viewer | editor | admin |
|---|---|---|---|
| Work: Desk, Questions | look | look (approving: approvers only) | everything |
| Work: Workshop | look (without the customers' fit answers) | look | look |
| Covers: All covers, Arrangements, Learning | yes | yes | yes |
| Covers: New cover, Product list | – | yes | yes |
| Shop: Website (AI) | – | draft and preview | also publish |
| Shop: Orders, Requests, Matches, B2B customers, Photo test | – | – | yes |
| Prices | – | look | change and publish; Import (Excel) |
| Settings | – | – | yes |

A page that is not for your account says so ("Not for your account"). The server checks the
same rights on every action, whatever the menu shows. A separate login or right for the
workshop does not exist yet (open owner question #92): today the workshop uses one of the
roles above.

## One look

The whole studio uses one font (Work Sans), rectangular buttons and at most one main (dark)
button per view. There are four kinds of page:

- **a list with a filter row** (All covers, Workshop, Orders, …);
- **a queue with the detail beside it** (Desk, Questions);
- **an object page** (a cover);
- **a settings form** (Settings, Prices).

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
  files, the revision to cut and how it fitted. Read only. See [workshop.md](workshop.md).

### Covers

- **All covers** (`#/covers/all`): every model and its cover, as a **Table** or as **Cards**
  (`#/covers/all?view=cards`). One filter row for both views, selection and the batch bar. See
  [catalogue.md](catalogue.md).
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
Desk status (a link to its card), the approval of the definitive drawing, a lock when the DXF
waits for the Desk's approval, and "N changes since the run before". The buttons **Run again**,
**Edit details** (category, family, status, tags, notes) and **Desk card ↗**. Under it the
approval of the definitive drawing (Approve / Ask for approval / Withdraw, the approved PDFs),
a running job, a rejection at the Desk and today's warnings: these stay above the tabs.

Seven tabs; the older tabs are one click away inside them, each with its own address:

| tab | inside | was |
|---|---|---|
| **3D** (`/3d`) | the 3D view | 3D |
| **Pieces** (`/pieces/cut`, `/flat`, `/sizes`) | Cut pieces (DXF, cutting list, check list), Flat patterns, Size drawing | Cut pieces, Patterns, Size drawing |
| **Seams** (`/seams`) | the seam editor | Seams |
| **Adjust** (`/adjust`) | this cover's own settings | Settings |
| **Compare** (`/compare/drawing`, `/reference`, `/ai`) | Your drawing, Your reference, AI advice | the same three tabs |
| **History** (`/history/changes`, `/revisions`, `/log`) | Approval & changes (since the run before), Revisions, Warnings and log | Revisions, Warnings and log, the "Since the run before" card |
| **Files** (`/files`) | every file to download | Downloads |

Another cover always opens on the tab in its own address. More: [web-app.md](web-app.md).

**The 3D toolbar** (on a cover and on a Desk card): **Show ▾** (the layers, with the ones on
named on the button; air vents, vent sizes, overall dimensions; the mouse hint), the quick
toggles **Vents** and **Dimensions**, which cover you look at — **Design · Rain · Drape ·
Unfold** — with **Water** beside it while you look at the drape, **Measure**, then
**Simulate ▾** (Rain again, about a minute; Drape again, about 40 minutes in its own queue; what
is running shows beside it) and **Check list (PDF)**. Your choices are remembered in the
browser.

### Shop (admins; editors: Website (AI) only)

**Orders** (one order: `#/shop/orders/<n>`), **Requests** (quotes asked in the configurator),
**Matches**, **B2B customers**, **Website (AI)**, and under *Tools* the **Photo test**. See
[admin.md](admin.md), [webshop.md](webshop.md) and [b2b.md](b2b.md).

### Prices (`#/prices/<tab>`)

The tabs are the sub-menu: Materials, Labour, Exchange rate, Channels & price lists, Import
(Excel), then Costing and Versions. Moving between the tabs keeps what you typed; leaving
Prices with unsaved numbers asks first. See [prices.md](prices.md).

### Settings (`#/settings/<tab>`, admins)

One page with vertical tabs in four groups (a row of tabs on a tablet). Every setting is one
row: a plain name (its stored key small and grey), the control, one line of explanation and
where the value comes from — **default X**, **changed · default X**, **empty**, or for
matching **uses the company default: 90** when the field is empty. **Only changed values**
filters the rows; **Save** and **Undo changes** sit at the bottom of the screen; leaving with
unsaved changes asks first.

| group | tab | what |
|---|---|---|
| Business | **Company & shop** | the company, the shop (domain, languages, colours, barbecues, logo, share picture, delivery promise), support products, shipping per country (a table), *advanced:* film and story |
| | **B2B terms** | minimum order, shipping, payment days, into production at once |
| | **Matching** | mode (learning / automatic), the thresholds with the value that applies, stock discount; how a match is scored (read-only) |
| People & work | **Users & rights** | the users, roles, *may approve*, invitations |
| | **Desk & approval** | `desk.*`, `questions.*`, `products.*` (read-only: the developer changes them) |
| | **Cover defaults** | construction, stitching, welding, hem, vents and features, seams (read-only) |
| Connections | **Mail & notifications** | who gets which mail in one list (requests, alerts and B2B, new orders, the fit question, approval requests, the question digests, AI spending warnings), the mail server, the login code, the public address |
| | **Website & API keys** | the website's key, the shop on this server only for the website, the scroll story, payment (Mollie key, masked; *Replace* to give a new one; bank transfer), the configurator in a webshop, API keys |
| | **AI & spending** | this month's spend, the budget and limits, which AI does what, the photo suggestion limits (read-only) |
| Server | **System** | release, engine, disk, backup, releases, the last alerts |
| | **Logins & audit log** | who is logged in, every login, change and approval |

Desk & approval, Cover defaults and AI & spending show the company defaults read-only. Whether
the owner will change some of them here himself is open owner question #93. More:
[admin.md](admin.md).

## Old addresses

Every old address still works and goes to its new place:

| old | new |
|---|---|
| `#/` | your start page |
| `#/desk`, `#/desk/<cover>` | `#/work/desk`, `#/work/desk/<cover>` |
| `#/questions`, `#/questions/<n>` | `#/work/questions`, `#/work/questions/<n>` |
| any address the studio never had (e.g. `#/models`) | your start page |
| `#/catalogue` | `#/covers/all?view=cards` |
| `#/arrangements[/<id>]` | `#/covers/arrangements[/<id>]` |
| `#/learning` | `#/covers/learning` |
| `#/prices` | `#/prices/materials` |
| `#/website` | `#/shop/website` |
| `#/admin` | `#/settings/users` |
| `#/admin/<tab>` | orders, b2b, matches, phototest, website → Shop; webshop, requests → Shop → Requests; prices → Prices → Materials; shop → Settings → Company & shop; users, mail, system → Settings; sessions, audit → Settings → Logins & audit log |
| `#/settings` | `#/settings/company` |
| `#/work`, `#/covers`, `#/shop`, `#/prices` | the first page of that section you may see |
| `#/model/<cover>` | `#/model/<cover>/3d` |
| `#/model/<cover>/<old tab>` | `/downloads` → `/files`, `/settings` → `/adjust`, `/patterns` → `/pieces/flat`, `/sizes` → `/pieces/sizes`, `/cut` → `/pieces/cut`, `/drawing`, `/reference`, `/ai` → `/compare/…`, `/revisions`, `/log` → `/history/…` |
| `#/guide`, `#/account`, `#/configure`, `#/welcome/…` | unchanged |

The mails (approval requests, question digests, the arrangements' digest) link to the new
addresses.

## New addresses (this round)

| address | page |
|---|---|
| `#/work/workshop` | Work → Workshop ([workshop.md](workshop.md)) |
| `#/shop/orders/<n>` | Shop → Orders with order `<n>` highlighted (from the search) |
| `#/covers/all?view=cards` | All covers as cards (the table: `#/covers/all`) |
