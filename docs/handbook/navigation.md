# Finding your way in the studio

Since ADR-122 (11 Oct 2026) the studio has **five sections** in the dark bar at the top, each
with its own pages in the light bar under it (the sub-menu). Every page, a cover's tab and a
Desk card's tab has its own address, so a link (in a mail, a bookmark, this handbook) opens
exactly that page, and the browser's Back button goes back one tab.

```
Work        Desk · Questions
Covers      All covers · Arrangements · New cover | Learning · Product list
Shop        Orders · Requests · Matches · B2B customers | Website (AI) | Tools: Photo test
Prices      Materials · Labour · Exchange rate · Channels & price lists · Import (Excel) | Costing · Versions
Settings    one page with tabs (admins)
```

At the right of the bar: search (models), **Guide**, your name (your account: password) and
**Log out**.

## Where you start

- **Approvers** (Rens, Wout, and whoever may approve at the Desk) start on **Work → Desk**.
- **An admin** starts on the page he was on last (remembered in that browser); the first time
  on Work → Desk.
- **Everyone else** starts on **Covers → All covers**.

(Open question for the owner: is this the right start page per person?)

## Who sees what

| section | viewer | editor | admin |
|---|---|---|---|
| Work: Desk, Questions | look | look (approving: approvers only) | everything |
| Covers: All covers, Arrangements, Learning | yes | yes | yes |
| Covers: New cover, Product list | – | yes | yes |
| Shop: Website (AI) | – | draft and preview | also publish |
| Shop: Orders, Requests, Matches, B2B customers, Photo test | – | – | yes |
| Prices | – | look | change and publish; Import (Excel) |
| Settings | – | – | yes |

A page that is not for your account says so ("Not for your account"). The server checks the
same rights on every action, whatever the menu shows.

## The pages

### Work

- **Desk** (`#/work/desk`, a card `#/work/desk/<cover>`): the queue on the left, the card on the
  right in four tabs, each with its own address:
  - **Check** (`…/<cover>`): the latest rejection and what happened since, the drawing beside
    our cover in 3D, the products, what the program read and what the AIs say;
  - **Pieces & revisions** (`…/<cover>/pieces`): the pieces and the revisions ("cut this");
  - **Correct this cover** (`…/<cover>/correct`): seams, vents, sizes, shape, with pictures;
    the drawing and the 3D stay above it;
  - **History** (`…/<cover>/history`): everything that happened, with the pictures.

  The decision bar stays at the bottom of the screen: **Approve**, **Reject**, **Comment**,
  **After sewing ▾** (Produced, a note, Measured…, Fits, Does not fit) and **Undo**. The keys are
  the same as before: `j` `k` move, `a` approve, `r` reject, `c` comment, `p` produced, `u`
  undo. **More** (top right of the card): Let the AI read it (costs about 1–5 cents), the check
  list, Edit arrangement, the cut pieces and DXF, the product list.
  The AI spend tile is shown to admins only (Settings → AI & spending has the details); the
  product-list upload moved to Covers → Product list.
- **Questions** (`#/work/questions`, one question `#/work/questions/<n>`): as before. The number
  beside Work and Questions counts the open questions; red when one waits for you.

### Covers

- **All covers** (`#/covers/all`): every model as a table, or **Cards** (`?view=cards`, the old
  Catalogue). Filters, tags, batch selection and recalculation are where they were.
- **Arrangements** (`#/covers/arrangements[/<arr-id>]`): as before, with *Send to the Desk*.
- **New cover** (`#/covers/new`): a 3D file (STEP, STL, …) or a drawing (PDF). These were at
  the top of the Models page.
- **Learning** (`#/covers/learning`): pairs of drawings and 3D (a zip).
- **Product list** (`#/covers/products`): upload the workshop's product list (Excel); the Desk
  shows the products on each card.

### A cover (`#/model/<cover>/<tab>`)

At the top: the picture, the name and sizes, a strip with the cover's grade, its status, its
Desk status (a link to its card), the approval of the definitive drawing, a lock when the DXF
waits for the Desk's approval, and "N changes since the run before". The buttons **Run again**,
**Edit details** (category, family, status, tags, notes) and **Desk card ↗**. Under it the
approval of the definitive drawing (Approve / Ask for approval / Withdraw, the approved PDFs),
a running job, a rejection at the Desk and today's warnings: these stay above the tabs.

Seven tabs (was twelve); the old tabs are one click away inside them, each with its address:

| tab | inside | was |
|---|---|---|
| **3D** (`/3d`) | the 3D view | 3D |
| **Pieces** (`/pieces/cut`, `/flat`, `/sizes`) | Cut pieces (DXF, cutting list, check list), Flat patterns, Size drawing | Cut pieces, Patterns, Size drawing |
| **Seams** (`/seams`) | the seam editor | Seams |
| **Adjust** (`/adjust`) | this cover's own settings | Settings |
| **Compare** (`/compare/drawing`, `/reference`, `/ai`) | Your drawing, Your reference, AI advice | the same three tabs |
| **History** (`/history/changes`, `/revisions`, `/log`) | Approval & changes (since the run before, without "null → value" noise), Revisions, Warnings and log | Revisions, Warnings and log, the "Since the run before" card |
| **Files** (`/files`) | every file to download | Downloads |

Another cover always opens on its own address's tab (before, it kept the tab of the cover
before).

**The 3D toolbar** (on a cover and on a Desk card): **Show ▾** (the layers, with the ones on
named on the button; air vents, vent sizes, overall dimensions; the mouse hint), the quick
toggles **Vents** and **Dimensions**, which cover you look at — **Design · Rain · Drape ·
Unfold** — with **Water** beside it while you look at the drape, **Measure**, then
**Simulate ▾** (Rain again, about a minute; Drape again, about 40 minutes in its own queue; what
is running shows beside it) and **Check list (PDF)**. Your choices are remembered in the
browser, as before.

### Shop (admins; editors: Website only)

**Orders**, **Requests** (configurator quotes), **Matches**, **B2B customers** (the B2B terms
moved to Settings), **Website (AI)**, and under *Tools* the **Photo test**.

### Prices (`#/prices/<tab>`)

The same page as before; its tabs are now the sub-menu, each with its address. **Import
(Excel)** has its own tab (it was at the top of Channels & price lists). Moving between the tabs
keeps what you typed; leaving Prices with unsaved numbers asks first.

### Settings (`#/settings/<tab>`, admins)

One page, tabs in four groups. Every setting is one row: a plain name (its stored key small and
grey), the control, one line of explanation and where the value comes from — **default X**,
**changed · default X**, **empty**, or for matching **uses the company default: 90** when the
field is empty. **Only changed values** filters the rows; **Save** and **Undo changes** sit at
the bottom of the screen; leaving with unsaved changes asks first.

| group | tab | what |
|---|---|---|
| Business | **Company & shop** | the company, the shop (domain, languages, colours, barbecues, logo, delivery promise), support products, shipping per country (a table), *advanced:* film and story |
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

The shop settings are the same stored values as before (nothing moved in the data).

## Old addresses

Every old address still works and goes to its new place:

| old | new |
|---|---|
| `#/` | your start page |
| `#/desk`, `#/desk/<cover>` | `#/work/desk`, `#/work/desk/<cover>` |
| `#/questions`, `#/questions/<n>` | `#/work/questions`, `#/work/questions/<n>` |
| `#/catalogue` | `#/covers/all?view=cards` |
| `#/arrangements[/<id>]` | `#/covers/arrangements[/<id>]` |
| `#/learning` | `#/covers/learning` |
| `#/prices` | `#/prices/materials` |
| `#/website` | `#/shop/website` |
| `#/admin` | `#/settings/users` |
| `#/admin/<tab>` | orders, b2b, matches, phototest → Shop; prices → Prices; shop → Settings → Company & shop; webshop → Shop → Requests; mail, system, users → Settings; sessions, audit → Settings → Logins & audit log |
| `#/model/<cover>` | `#/model/<cover>/3d` (and the old tab names: `/downloads` → `/files`, `/settings` → `/adjust`, …) |
| `#/guide`, `#/account`, `#/configure`, `#/welcome/…` | unchanged |

The mails (approval requests, question digests) link to the new addresses.
