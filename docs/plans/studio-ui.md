# The studio's layout: tighter and clearer (proposal, 11 Oct 2026)

Status: **steps 1, 2, 5 and 6 built (11 Oct 2026, night, ADR-122) and live in v1.36.0; steps 7, 8 and 9 built (12 Oct 2026, ADR-124; §11), not released.** §12 (one cover, one page; ADR-126) built 12 Oct 2026, evening, not released. Steps 3 and 4 wait for the owner (questions 83/84 and 93). Audited
release: v1.30.0 (main has moved on since, e.g. ADR-116; the layout findings still hold). This
document, the clickable prototype and the audit scripts are on the branch `studio-ui-audit`.

## Samenvatting voor Rick

Je vroeg (9 okt): *"De backend is rommelig. Te veel informatie op te veel plekken. Het moet
strakker en duidelijker. Submenu's kunnen helpen, en een admin-pagina waar de meeste
instellingen staan, op tabbladen met wat meer uitleg."*

**Wat ik deed.** Elke pagina, elk tabblad en elke knop van de studio (v1.30.0) doorgelopen, in de
code en in een echte browser op een kopie van 11 hoezen met testgebruikers (nooit live). Van
elke pagina een schermafdruk op 1440 en 820 px, met een telling van knoppen, velden, vinkjes,
paginahoogte en woorden (`out/uiaudit/before/`).

**Wat er mis is (de belangrijkste vijf).**

1. **Instellingen staan op zeven plekken**: dertien Admin-tabbladen, "Shop settings" als een
   kale lijst van 49 sleutelnamen (`legal_name`, `0`, `1`, `2`, `threshold_pct`), de B2B-tab,
   de Requests-tab, de System-tab, Prices & costing, en `config/defaults.yaml` (dat je niet in
   de studio ziet). Dezelfde waarde staat soms op twee plekken: de kleuren drie keer, de
   matchdrempel twee keer (de shop toont "to fill in" terwijl 90 % geldt), vijf mailadressen op
   vijf tabbladen.
2. **"Goedkeuren" betekent twee dingen.** De Desk keurt goed (en geeft de DXF vrij); de
   modelpagina heeft een tweede, losse goedkeuring ("Approve the definitive drawing"). Wie mag
   goedkeuren staat ook op twee plekken: het vinkje *may approve* bij de gebruiker én de lijst
   `desk.approvers` in de configuratie. Daarnaast heeft een hoes nog een "status" (draft /
   checked / production) en een "cover"-oordeel (ready / to check / failed).
3. **De Desk-kaart is 4.500 px lang**: tekening, 3D, producten, wat het programma las, de AI's,
   stukken, revisies, een correctielijst met 37 naden, en de geschiedenis, allemaal onder elkaar.
   Bovenaan de Desk staan ook de AI-kosten en de upload van de productlijst, elke keer weer.
4. **De modelpagina** heeft 12 tabbladen en vijf blokken boven de 3D (samenvatting,
   goedkeuring, catalogusgegevens met soms ruwe JSON in de notities, "since the run before" met
   tot 30 chips, de tabs). De 3D begint pas op 690 px. De 3D-balk heeft 15 knoppen en vinkjes
   in één rij. Het gekozen tabblad staat niet in het adres en blijft hangen als je naar een
   andere hoes gaat.
5. **Geen duidelijke start per persoon.** Iedereen landt op de modellenlijst met twee
   upload-blokken; Rens moet altijd eerst naar Desk. Admin zit verstopt naast je naam; Prices
   staat zowel bovenin als in Admin (tabbladen in tabbladen). De werkplaats kan een gemeten
   maat of "past / past niet" alleen invoeren als ze goedkeurder zijn. Engels en Nederlands door
   elkaar (vragen en uitleg in het Nederlands, knoppen in het Engels). De Desk heeft een eigen
   stijl, kleuren, lettertype en donkere modus; de rest van de studio niet.

**Wat ik voorstel.** Vijf onderdelen bovenin, elk met een vaste submenubalk eronder:

```
Werk (Work)          Desk · Vragen · Werkplaats
Hoezen (Covers)      Alle hoezen · Opstellingen · Nieuwe hoes · Leren · Productlijst
Winkel (Shop)        Bestellingen · Aanvragen · Matches · B2B-klanten · Website (AI) · Fototest
Prijzen (Prices)     Materialen · Arbeid · Wisselkoers · Kanalen · Import · Kostprijs · Versies
Instellingen         één pagina met tabbladen (alleen admins)
```

- **Instellingen** wordt één plek met tabbladen in groepen (Bedrijf & winkel, B2B,
  Matching, Gebruikers & rechten, Desk & goedkeuring, Standaardwaarden hoezen, Mail &
  meldingen, Website & API-sleutels, AI & kosten, Systeem, Logins & audit). Elk tabblad zegt
  waar het voor is; elke instelling heeft een gewone naam, één regel uitleg, de standaardwaarde,
  of hij is aangepast, en wie hem mag wijzigen. De waarden die je zelf wilt kunnen veranderen
  (vents, zoom, naadtoeslag, AI-budget, drempels) komen erin; de technische (meetkunde,
  simulatie) blijven bij de ontwikkelaar en zijn alleen te lezen.
- **De Desk-kaart** krijgt vier tabbladen (Controle · Stukken & revisies · Corrigeren ·
  Geschiedenis) en een vaste beslisbalk onderaan. Sneltoetsen blijven gelijk.
- **Een hoes** krijgt één kop met wat telt (status, goedkeuring, DXF, opnieuw rekenen) en 7 in
  plaats van 12 tabbladen, elk met een eigen adres. De 3D-balk gaat van 15 naar 6 knoppen; de
  lagen en vents zitten in een menu "Tonen".
- **Werkplaats** (nieuw, uit wat er al is): de goedgekeurde hoezen met DXF, snijlijst en
  checklist, en daar vul je gemeten maten en "past / past niet" in.
- **Eén rustige stijl** voor de hele studio, met de kleuren en het lettertype van de website
  (zand, warm zwart, Work Sans), maar compact: een werkinstrument, geen etalage. Licht en
  donker.
- **Oude links blijven werken** (`#/desk`, `#/admin`, `#/catalogue` …): ze sturen door.

**Hoe je het bekijkt.** Open `out/uiaudit/prototype/index.html` in een browser (geen server
nodig). Klik door de vijf onderdelen; rechtsonder kun je kijken als Rens, Eddy of de werkplaats.
Voorbeeldplaatjes: `out/uiaudit/after/`, de huidige studio: `out/uiaudit/before/`.

**Hoe we het bouwen.** In 9 kleine stappen, elke stap een eigen release die werkt; geen functie
verdwijnt; oude links sturen door. Eerst de navigatie en het adres per tabblad (stap 1), dan
Instellingen (stap 2–4), dan Desk-kaart en hoes-pagina (stap 5–6), de stijl (stap 7), de
Werkplaats (stap 8) en het opruimen (stap 9).

**Wat ik van je moet weten** (vragen onderaan, kort): de taal van de knoppen (Engels houden,
Nederlands, of kiezen per gebruiker), of de twee goedkeuringen één mogen worden, waar Rens en
de werkplaats moeten landen, of de werkplaats eigen inlogs krijgt, en welke standaardwaarden je
zelf wilt kunnen veranderen.

---

## 1. How the audit was done

- **The studio**: release v1.30.0 (`0208ca8`), run from `~/releases/v1.30.0` on port 18240 with a
  scratch data directory: 11 models copied from the live data (5 drawing covers, 5 SUNS models,
  1 arrangement), the questions, learning, product list and usage folders, and a fresh `app.db`
  with five test users: `rick` (admin, may approve), `rens` and `wout` (editor, may approve),
  `eddy` (editor), `vic` (viewer). Live was not logged into and not touched.
- **The script**: `apps/web/e2e/uiaudit.py` opens every page, tab and sub-tab (never a button that
  saves, approves, sends, runs or spends), takes a full-page screenshot at 1440 × 900 and
  820 × 1180, and counts what is on the screen: buttons, fields, checkboxes, links, headings, page
  height, words. Shots in `out/uiaudit/before/<width>/`, counts in `counts.json` (1440:
  `out/uiaudit/counts-1440.json`). Usage in its docstring.
- **The code**: `apps/web/src/*.tsx` read for every control, role check and setting, and the
  API (`apps/api/coverapi/*.py`) for where each setting is stored and which one wins.
- **The prototype's shots**: `apps/web/e2e/uiaudit_proto.py` → `out/uiaudit/after/` (1440 and
  820, light and dark).
- The screenshots are not in git (the repository is public and they show drawings and covers).
- Not captured: at 820 px the reject dialog and the drape view (software WebGL in the container
  timed out on those two long pages; the 1440 px shots show them) and the viewer's login.

## 2. Inventory

### 2.1 Roles

| person | role in the app | what for | how often |
|---|---|---|---|
| Rick (owner) | admin, may approve | everything; prices, shop, orders, settings, follow-up of questions and rejections | daily |
| Rens | approver (Desk) | approve / reject / comment drawing covers and arrangements; answer questions | daily (the Desk checks are run on laptop and iPad widths) |
| Wout | approver (Desk) | the same as Rens; arrangements | weekly |
| Workshop | no workshop role today: saving a measured fit needs approver rights | check list, measure the sewn cover, fits / does not fit, DXF | per cover sewn (≈ 100/week in production) |
| Editors (Eddy, colleagues) | editor | upload models, build arrangements, draft website text | occasionally |
| Viewer | viewer | look and download | rarely |

Rights live in three places today: the role (viewer / editor / admin), the per-user flag
**may approve** (used by the model page's "Approve the definitive drawing"), and the developer list
`desk.approvers` (used by the Desk: admin or a name in that list). `questions.owners` is a fourth
(who marks an answer final).

### 2.2 Pages and what is on them (v1.30.0)

Counts at 1440 px (buttons / fields / checkboxes / page height in px).

| page (route) | what is on it | who | how often | counts |
|---|---|---|---|---|
| **Header** (every page) | two logos and a wordmark, 7 links (Models, Desk, Catalogue, Arrangements, Learning, Prices, Guide), a crumb, model search, then Admin (admins) or Website (editors), the user's name, Log out. Wraps to two lines at 1440 px. | all | always | 9 links + search + 1 button |
| **Models** (`#/`, home) | "New model" upload card (file, units, up), "New cover from a drawing" upload card, the table (search, category, cover grade, status filters; checkbox per row; batch bar on selection) | Rick, editors | daily | 3 / 7 / 12 / 1131 |
| **Catalogue** (`#/catalogue`) | the same models as cards (photo + cover), search, grade, category, tag, sort | Rick | weekly | 1 / 6 / 0 / 927 |
| **Desk** (`#/desk[/id]`) | tabs Covers / Questions; title with keyboard hints; 6 KPI tiles incl. AI spend; learned-rule proposals; product-list upload; a pipeline bar; queue (search, 6 status buttons, 9 series chips, sort) and the card | Rens, Wout, Rick | daily | 77 / 7 / 7 / 4578 (C27) |
| **Desk card** | head (code, outcome, G/D scores, status, *Let the AI read it*, *Edit arrangement*, *Open model*), 2nd-round note, drawing (pages) or arrangement plan, the 3D viewer (+ its own toolbar, Check list link), Products, What the program read, What the AIs say, Pieces, Revisions, **Correct this cover** (Seams 37 rows / Vents / Sizes / Shape, pictures), Measured on the sewn cover (on request), History; action bar: Approve, Reject, Comment, Produced, after-sewing note, Measured…, Fits, Does not fit, Undo; reject/comment dialog with Pictures tray | Rens, Wout, Rick | daily | 42 / 7 / 7 / 2841 (S45) |
| **Questions** (`#/questions[/n]`) | Desk tabs; title + keys; 4 tiles; queue (search, status, topic chips); question with covers, pictures, context, answers; answer form (options, other, comment, pictures, send); owner's block (final, processed) | Rens, Rick, workshop | daily | 5 / 2 / 0 / 983 |
| **Arrangements** (`#/arrangements[/id]`) | intro, name, catalogue search to add, the list of arrangements as a line of links, plan canvas, pieces (turn, mirror, snap, dropdowns), cover plan (follow / box / smoothed), build, Desk status and *Send to the Desk*, the 3D cover | editors, Rick | weekly | 6 / 3 / 0 / 1486 |
| **Learning** (`#/learning`) | zip upload (drawings + 3D pairs; a zip with only a product list goes to the Desk's list), uploaded batches with each pair compared | Rick | rarely | 2 / 1 / 0 / 900 |
| **Prices** (`#/prices`, also Admin → Prices & costing) | intro, the four-step price flow, live version, placeholder counter, Save draft / Preview / note / Publish / Discard + help text; then 6 tabs: Materials, Labour, Exchange rate, Channels & price lists (with Import prices (Excel)), Costing, Versions; live examples | Rick (edit), editors (look) | monthly, intense when set up | 27 / 36 / 0 / 2271 |
| **Website** (`#/website`, editors; admins: Admin → Website (AI)) | instruction box, history, preview, publish / discard, translate | Rick, editors | weekly | 5 / 2 / 0 / 900 |
| **Guide** (`#/guide`) | the short guide, readable without logging in | new users | rarely | 1 / 1 / 0 / 3582 |
| **Account** (`#/account`) | name, e-mail, password | all | rarely | 2 / 4 / 0 / 900 |
| **Admin** (`#/admin`, via the user menu) | 13 tabs, state not in the address: Users · Orders · B2B customers · Matches · Shop settings · Photo test · Prices & costing · Website (AI) · Requests · Mail and address · Logged in · Audit log · System | Rick | daily (orders) to rarely | 13 tabs |
| Admin → Users | invitations line, invite all, the table (role, may approve, active, e-mail, access, links), new user form | Rick | monthly | 21 / 16 / 12 |
| Admin → Orders | consumer orders, status, into production | Rick | daily once the shop runs | 14 / 1 / 0 |
| Admin → B2B customers | requests, companies, invite a company, per company addresses / people / orders, **B2B settings** (minimum order, shipping, payment days, auto produce) | Rick | weekly | 16 / 15 / 2 |
| Admin → Matches | requests in learning mode (take %, custom, choose), What we learn, fit answers | Rick | daily once the shop runs | 14 / 1 / 0 |
| Admin → Shop settings | a form generated from the stored JSON: 49 fields with raw key names (`legal_name`, `kvk`, shipping as `0 / 1 / 2`, `film_av1`, `story_media.hero`, `matching.mode` as free text, `fit_mail.enabled`, `website_link.closed`), the website key, two Save buttons 3,600 px apart | Rick | set once, then rarely | 17 / 49 / 4 / 3836 |
| Admin → Photo test | try a photo suggestion step by step | Rick | rarely | 15 / 3 / 0 |
| Admin → Website (AI) | as `#/website`, with Publish | Rick | weekly | 18 / 2 / 0 |
| Admin → Requests | configurator requests (table); **configurator embed origins**, **requests are mailed to**; **API keys** | Rick | weekly / once | 16 / 4 / 0 |
| Admin → Mail and address | SMTP, test mail, login code by mail, public address | Rick | once | 17 / 9 / 1 |
| Admin → Logged in / Audit log | sessions; every login, change, approval | Rick | rarely | – |
| Admin → System | release, engine, models, disk, backup, login, mail, AI key; releases; **alert address**; last alerts | Rick | weekly glance | 15 / 2 / 0 |
| **Model page** (`#/model/<id>`) | summary card (name, file, size, hem, skirt, panels, roll; *Run again*); *Check: what is this file?* (after import); approval card (*Approve the definitive drawing* / *Ask for approval* / *Withdraw*, approved PDFs); catalogue info card (category, family, status, tags, notes — notes can hold raw JSON); job bar; *Since the run before* chips (up to 30); 12 tabs, state not in the address | everyone | daily | 20 / 7 / 6 / 1385 |
| model → 3D | 5 layer checkboxes (furniture, balloons, chair space, cover surface, panels), Show air vents, Vent sizes, Show dimensions, a hint, Measure, Check list (PDF), Unfold, Rain, Rain simulation / Simulate again, Drape, Water, Drape simulation / Drape again; rain and drape report cards; measure and vent-size panels | everyone | daily | up to 15 controls in one bar |
| model → Your drawing / Your reference / AI advice | the drawing's sizes against ours; uploads of a reference (3D or PDF) with a step report; the AI's advice with Apply | Rick | weekly | – |
| model → Seams | seam editor (draw, proposals, automatic seams) | Rick, editors | weekly | 23 / 7 / 0 |
| model → Patterns / Size drawing / Cut pieces | flat pieces + stretch (radio), the PDF, cut pieces with DXF (or lock), cutting list, check list | Rick, workshop | daily | – |
| model → Settings | ≈ 120 parameters in groups, search, Try without saving / Save for this model / Undo, source badges, use default | Rick | weekly | 19 / 30 / 1 / 2830 |
| model → Revisions / Downloads / Warnings and log | revisions; every file (≈ 40, half without explanation); warnings and the run log | Rick | rarely | – |
| **Configurator** (`#/configure`), **Welcome**, **Login** | public / one-time pages | customers, new users | – | – |

### 2.3 The same thing in more than one place

| what | where today | proposal |
|---|---|---|
| **Approval** | Desk *Approve* (ADR-079, unlocks the DXF, catalogue status → checked); model page *Approve the definitive drawing* (ADR-047, stamped PDFs, status → production); catalogue *Status* dropdown; Desk *Produced* | one approval, at the Desk; the model page shows it and links there (question Q2) |
| **Who may approve** | user flag *may approve*; `desk.approvers` (YAML); admins always | the user flag only (Settings → Users & rights); `questions.owners` becomes an *Owner* flag |
| **Prices** | top-bar *Prices*; Admin → *Prices & costing* (the same component, tabs inside tabs); `quote.*` in defaults.yaml as fall-back; the old `prices.*` block still stored in Shop settings (hidden) | one section *Prices*; Admin tab removed (redirect) |
| **Colours offered** | `quote.colours` (YAML); Shop settings `colours`; price set → fabric → *Colours offered* | the price set's fabric only; the others read from it |
| **Matching thresholds** | `match.threshold_pct = 90` (YAML) and Shop settings `matching.threshold_pct` (empty, shown as "to fill in", while 90 applies) | Settings → Matching, showing the effective value and its default |
| **Roll width** | `roll.width_mm` / `usable_width_mm` (YAML, read-only); price set → fabric → *Roll width (mm)* | shown once; the price set's is the fabric's, labelled as such |
| **Mail recipients** | `notify_email` (Shop settings), *Requests are mailed to* (Requests tab), alert address (System), the SMTP sender (Mail), B2B order mails | Settings → Mail & notifications: one list "who gets which mail" |
| **Uploads** | Models: 3D file and drawing PDF cards; Learning: zip of pairs (or a product list); Desk: product list (Excel) on top of every visit; model → Your reference; Prices → Channels → Import (Excel) | Covers → *New cover* (3D, PDF, zip); Covers → *Product list*; per-cover references stay on the cover; price import stays in Prices |
| **Models list and Catalogue** | two pages over the same list (table / cards), different filters | one *All covers* page with a Table / Cards toggle and one filter row |
| **Vents** | 3D *Show air vents* + *Vent sizes* (model and Desk card); Desk card *What the program read*; Correct this cover → Vents; check list PDF; Settings → features.* | the 3D *Show* menu; one vent line on the Desk card's Check tab; the rule's defaults in Settings → Cover defaults |
| **Check list (PDF)** | 3D toolbar link; Desk card caption link; Cut pieces tab; Downloads | the 3D bar (one), *Pieces* tab, *Workshop* |
| **Measured / fits** | Desk action bar (*Measured…*, *Fits*, *Does not fit*, note) for approvers only; History | *Workshop* page; the Desk keeps it under *After sewing* |
| **Website (AI)** | Admin tab (admins); `#/website` behind the user menu (editors) | Shop → Website (AI) for both; publishing stays admin |
| **AI spend** | Desk KPI tile; System (key present); watchdog mails | Settings → AI & spending (and a small tile for admins on the Desk) |
| **Revisions** | model → Revisions tab; Desk card → Revisions | model → History; Desk → Pieces & revisions |
| **Since the run before** | a card above the model tabs, up to 30 chips incl. `null → value` noise | model → History, only real changes; a one-line summary in the status strip |
| **Search** | header search: models only; queue searches on Desk and Questions | header search over covers, codes, products, orders, questions and settings |

## 3. Top tasks per role: where and how many clicks

Clicks counted from logging in (L) or from the page they are usually on. Proposed numbers assume
each person lands on their own start page (Q3).

| who | task | today | clicks today | proposed | clicks |
|---|---|---|---|---|---|
| Rens | approve or reject the next cover | L → Models (home) → **Desk** → card opens → Approve `a` | 1 + key | L → Work/Desk (home) → `a` | key |
| Rens | see the drawing beside the 3D while reading the facts | scroll a 4,500 px card | scrolling | Check tab: drawing, 3D and facts on one screen | 0 |
| Rens | correct the vents of a cover | card → scroll past 37 seams → Vents | 2 + scroll | card → *Correct this cover* → Vents | 2 |
| Rens | answer a question | Desk → Questions → pick → option → Send | 4 | Work → Questions (badge in the header) → pick → option → Send | 4 (visible from every page) |
| Rens / Wout | approve an arrangement | Desk → ARR chip → pick → `a` | 3 | Desk → (ready ones first) pick → `a` | 2 |
| Rick | change a price and publish | top-bar Prices → tab → edit → Publish (or Admin → Prices & costing: the same, nested) | 3 | Prices → sub-menu → edit → Publish | 3, one place |
| Rick | change the matching threshold | Admin (user menu) → Shop settings → scroll 3,000 px → field (empty, while 90 applies) → Save | 3 + scroll | Settings → Matching → field (shows 90, default 90) → Save | 3 |
| Rick | change the default vent height | not possible in the studio (developer edits YAML) | – | Settings → Cover defaults → field → Save (with reason) | 3 |
| Rick | add a person and let him approve | Admin → Users → form → Add; and ask the developer to add him to `desk.approvers` | 3 + a commit | Settings → Users & rights → + Add (may approve) | 2 |
| Rick | see today's orders | Admin (user menu) → Orders | 2 | Shop (count in the header) → Orders | 1 |
| Rick | find where a mail goes | Shop settings, Requests, System, Mail, B2B | 5 tabs | Settings → Mail & notifications | 2 |
| Rick | follow up rejections and answers | Desk → Rejected; Questions → Answered | 3–4 | Work → Desk / Questions with counts | 2 |
| Workshop | get the DXF, cutting list and check list | search the model → model page → Cut pieces tab | 3 | Work → Workshop → the row's buttons | 2 |
| Workshop | enter what was measured and whether it fits | Desk → search → card → Measured… → fill → Fits — **only as an approver** | 5 | Work → Workshop → *Measured…* → fill → Fits (a workshop right, Q4) | 3 |
| Editor | upload a new model or drawing | Models (home) → upload card | 1 | Covers → *+ New cover* → choose | 2 (but no upload cards on every visit) |
| Editor | build an arrangement and send it | Arrangements → … → Send to the Desk | – | Covers → Arrangements → … | same |

## 4. Problems, ranked

Ranked by how much they cost the people who use the studio daily (Rens, Rick, the workshop).

1. **Settings scattered, partly hidden, partly raw.** Seven places (13 Admin tabs, Shop settings,
   B2B, Requests, System, Prices, `config/defaults.yaml`). Shop settings is a form generated from
   JSON: 49 raw keys, list items named `0 / 1 / 2`, an enum (`matching.mode`) as free text, an
   empty field while a YAML default applies, two Save buttons 3,600 px apart, no explanation per
   field. Owner-relevant defaults (vents, hem, AI budget, digest hours) cannot be changed in the
   studio at all.
2. **Two approvals, two approver lists, four status words.** Desk approval and "definitive
   drawing" approval are separate; *may approve* and `desk.approvers` are separate; a cover also
   has a grade (ready / to check / failed), a catalogue status (draft / checked / production) and
   a Desk status (new / AI checked / ready / approved / rejected / produced). People cannot tell
   which one unlocks the DXF.
3. **Overloaded pages.** The Desk card (2,800–4,600 px, 42–77 buttons; *Correct this cover*
   alone lists every seam), the model page (five blocks before the tabs, 3D at 690 px), Shop
   settings (3,836 px), Prices (2,271 px with ≈ 300 px of explanation before the tabs).
4. **No sub-menus; nesting instead.** Tabs inside tabs (Admin → Prices & costing → Materials);
   Desk tabs (Covers / Questions) look like page content; the model page's tab and Admin's tab
   are not in the address, so a link cannot point to them and **the model page keeps the tab of
   the model before** (open a cover on *Downloads*, go to another: it opens on Downloads too —
   seen during the audit).
5. **Hidden or misplaced features.** Admin sits beside the user's name; Website hides there for
   editors; Prices for viewers is missing without a word; the AI spend is only on the Desk; the
   product-list upload is on top of the Desk every visit; *Let the AI read it* (costs money) is a
   prominent button; the workshop's measuring needs approver rights.
6. **The 3D toolbar**: up to 15 checkboxes, buttons and links in one wrapping row (layers, vents,
   vent sizes, dimensions, hint, Measure, Check list, Unfold, Rain, Rain simulation, Drape,
   Water, Drape simulation); expensive runs (drape: 40 minutes) sit beside view toggles.
7. **Inconsistent naming.** Model / product / cover / drawing for the same thing; *Panels*
   (3D) vs *Pieces* (Desk, cut list); *Settings* is both a model tab and (proposed) the
   settings area; *Requests* (configurator) vs *Requests* (B2B) vs *Matches* (learning
   requests); status values in lower case and English internal words (`ai-checked`, `shadow`).
8. **English and Dutch mixed.** Buttons English; questions, Rens's guide sections and many
   comments Dutch; option *anders* in an English form; handbook mixed.
9. **Three visual systems.** Studio (Poppins + Fraunces, cream/olive, pill buttons), Desk and
   Questions (Work Sans, grey/green, own dark mode), shop (ADR-105 tokens). Five font families
   loaded from Google Fonts. Dark mode only on the Desk.
10. **Tablet (820 px).** The header wraps; the Desk card stacks into a very long page (3,671 px
    for S45, 42 buttons); Shop settings grows to 3,959 px, a cover's Settings tab to 3,493 px,
    Prices to 2,737 px; the 3D toolbar wraps into three rows (with a drape: Rain, Simulate again,
    Back to the design, Water, Drape again on a row of their own). Counts per page:
    `out/uiaudit/counts-1440.json`, `counts-820.json`.
11. **Noise.** *Since the run before* shows `null → value` for every new default; Downloads lists
    ≈ 40 files, half without explanation; notes can show raw JSON; IDs (`drawing-c27`,
    `165cbbc3-…glb`) where a name would do.
12. **Header**: two logos + wordmark + italic title take a third of the bar; the bar wraps at 1440.

## 5. Proposed information architecture

```
Cover Studio
├── Work                                  (start page for approvers and the workshop)
│   ├── Desk            #/work/desk[/id[/check|pieces|correct|history]]
│   ├── Questions       #/work/questions[/n]
│   └── Workshop        #/work/workshop                     (new: built from existing data)
├── Covers                                (start page for admins and editors)
│   ├── All covers      #/covers/all[?view=cards]           (Models + Catalogue merged)
│   │   └── a cover     #/model/<id>/<3d|pieces|seams|adjust|compare|history|files>
│   ├── Arrangements    #/covers/arrangements[/id]
│   ├── New cover       #/covers/new                        (3D file · drawing PDF · zip)
│   ├── Learning        #/covers/learning
│   └── Product list    #/covers/products                   (moved from the Desk's top)
├── Shop                                  (admins; editors: Website only)
│   ├── Orders          #/shop/orders
│   ├── Requests        #/shop/requests                     (configurator quotes)
│   ├── Matches         #/shop/matches
│   ├── B2B customers   #/shop/b2b
│   ├── Website (AI)    #/shop/website                      (editors draft, admins publish)
│   └── Photo test      #/shop/phototest
├── Prices                                (admins edit, editors look)
│   └── Materials · Labour · Exchange rate · Channels & price lists · Import (Excel) · Costing · Versions
│                       #/prices/<tab>
├── Settings                              (admins)           #/settings/<tab>
│   ├── Business:       Company & shop · B2B terms · Matching
│   ├── People & work:  Users & rights · Desk & approval · Cover defaults
│   ├── Connections:    Mail & notifications · Website & API keys · AI & spending
│   └── Server:         System · Logins & audit log
└── (right side)  Search everything ( / ) · Guide (?) · Me: My account, light/dark, Log out
```

**Navigation pattern.** Five sections in the dark header; under it a light **sub-menu bar** with
the current section's pages, always visible (works on a tablet without hover); hovering a
section also shows its pages to jump directly. Counts where something waits for a person
(Desk, Questions, Orders, Matches) — red only when it waits for *you*.

**What moves, merges, disappears.**

| today | becomes |
|---|---|
| Models + Catalogue | Covers → All covers (Table / Cards) |
| Upload cards on Models, zip upload on Learning | Covers → New cover |
| Product list upload on the Desk | Covers → Product list |
| Desk's AI spend tile | Settings → AI & spending (admins keep a small tile) |
| Desk tabs Covers / Questions | the Work sub-menu |
| Admin (13 tabs) | Shop (Orders, Requests, Matches, B2B, Website, Photo test) + Settings (the rest) |
| Admin → Prices & costing | removed (same as Prices) |
| Shop settings (raw form) | Settings → Company & shop, Matching, Mail & notifications, Website & API keys |
| B2B settings (inside B2B customers) | Settings → B2B terms |
| Requests tab: embed origins, API keys, mail-to | Settings → Website & API keys / Mail & notifications |
| System: alert address | Settings → Mail & notifications |
| Model page: approval card | the status strip in the cover's header (+ History) |
| Model page: catalogue info card | *More → Edit details* (a side panel) |
| Model page: *Since the run before* | one line in the status strip; details in History |
| Model tabs (12) | 3D · Pieces (cut pieces, flat patterns, stretch, size drawing) · Seams · Adjust (was Settings) · Compare (your drawing, your reference, AI advice) · History (approval, Desk history, revisions, changes, warnings, run log) · Files |
| Website link in the user menu (editors) | Shop → Website (AI) |
| Admin link in the user menu | Settings in the header |

**Behind "advanced"** (shown on request, never removed): the developer-only parameters on a
cover's Adjust tab (≈ 110 of 120), the film and story media fields, picture limits, the fit curve
of matching, the run log, internal files in Files.

**Old links** redirect (the handbook, mails, bookmarks and the invitation mail keep working):

| old | new |
|---|---|
| `#/` | the person's start page (Work/Desk for approvers and the workshop, Covers for the rest) |
| `#/desk[/id]` | `#/work/desk[/id]` |
| `#/questions[/n]` | `#/work/questions[/n]` |
| `#/catalogue` | `#/covers/all?view=cards` |
| `#/arrangements[/id]` | `#/covers/arrangements[/id]` |
| `#/learning` | `#/covers/learning` |
| `#/prices` | `#/prices/materials` |
| `#/website` | `#/shop/website` |
| `#/admin` | `#/settings/users` (and `#/admin/<tab>` to its new place) |
| `#/model/<id>` | `#/model/<id>/3d` |
| `#/guide`, `#/account`, `#/configure`, `#/welcome/…` | unchanged |

The approval mails, question digests and invitations contain such links; they keep working
through the redirects, and are switched to the new form in the same step.

## 6. The Settings area

One page, vertical tabs in four groups; on a tablet the tabs become a scrolling row. Every tab
starts with two or three lines: what it is for, and who changes it. Every setting is one row:

| column | content |
|---|---|
| name | a plain name ("Bottom edge above the hem"), with the key in small grey (`features.vent_above_hem_mm`) for the handbook and the developer |
| value | the right control: a number with its unit, a switch, a choice, a list; never free text for a choice |
| explanation | one line; then the source chips: **default X** (the company value), **changed · default X** (an override, with *use default*), **empty** / **to confirm** in amber; and who may change it: ✎ admin, or 🔒 developer only |

A sticky *Save* bar at the bottom of each tab (one Save per tab, *Undo* beside it); "Only
changed values" filter; every save is in the audit log with who, when and the old → new value.

**Owner-editable vs developer-only.** Today every number lives in `config/defaults.yaml` (one
place, a commit per change, a test that no code duplicates a default). That stays the source of
the defaults. Owner-editable keys get an **override layer stored in app.db** (like the price set:
versioned, with who/when/why), applied between the YAML defaults and the model's own values
(CLAUDE.md "layered overrides": 1. defaults.yaml → 1b. company overrides (new) → 2. family
preset → 3. the model → 4. trial). `cover params` shows the new layer as its source; a changed
company default sweeps nothing by itself (models are recalculated only on request, as today).
Developer-only keys are shown read-only with their YAML comment.

| tab | settings (today's place) | who |
|---|---|---|
| **Company & shop** | company data (Shop settings `company.*`), domain, languages, logo, share picture, shipping per country (as a table), Mollie key, bank transfer, balloon / frame products; *advanced*: film and story media, story model, home_story | admin |
| **B2B terms** | minimum order, shipping per order, payment days, into production at once, online payment (later) (B2B customers tab) | admin |
| **Matching** | mode (learning / automatic as a choice), threshold, choice, stock discount (Shop settings), drawing statuses offered, size tolerance (`match.*`); *advanced*: tight / loose cm, fall-off, weights | admin (owner-editable YAML keys: `match.threshold_pct`, `choice_pct`, `mode`, `drawing_statuses`, `drawing_size_tol_cm`) |
| **Users & rights** | the users table with role, **may approve**, **owner** (replaces `desk.approvers` and `questions.owners`), **workshop** (Q4), active, access; invite, new link, deactivate | admin |
| **Desk & approval** | DXF only after approval, gate scope, arrangements gated, learn after, questions digest hours, answers digest hours; *advanced*: picture size / number / side (`desk.*`, `questions.*`) | admin (owner-editable) |
| **Cover defaults** | air vents: opening, per metre, minimum, above the hem, inner walls, align, logo, seam clearance; hem: type, allowance, cord exits; stitching: allowance, sides; welding overlap; skirt seam, skirt height; middle cord; strap marks; handles; fabric profile (read-only); *advanced*: everything else read-only (hull, flatten, drape physics, export, drawing reader, import) | admin for the owner-editable; developer for the rest |
| **Mail & notifications** | SMTP and test mail, public address, login code by mail; who gets which mail: new orders (`notify_email`), configurator requests, server alerts, B2B order mails, fit question (on, days), approval requests (the approvers), digests (see Desk & approval) | admin |
| **Website & API keys** | website key (new key), shop closed to visitors (`website_link.closed`), configurator embed origins, API keys, scroll story as home page | admin |
| **AI & spending** | this month's spend and the budget bar; budget, warn %, hourly spike, hard stop (`spend.*`); read-only: providers, models, prices per token (`ai.*`, `spend.prices`); photo suggestion limits (`suggest.per_hour`, `per_day`, `visitor_eur_day`) | admin (owner-editable: budget, warn, spike, hard stop, suggest limits) |
| **System** | release, engine, models, disk, backup, mail, AI key, releases, last alerts (read-only) | admin |
| **Logins & audit log** | logged in now; the audit log with a filter | admin |

Owner-editable keys from `config/defaults.yaml` (proposed; Q5 asks the owner to confirm):
`features.vent_width_mm`, `vent_height_mm`, `vents_per_metre`, `vents_min`, `vent_above_hem_mm`,
`vent_inner_walls`, `vent_align`, `vent_below_top_mm`, `vent_logo`, `vent_seam_clearance_mm`,
`middle_cord`, `strap_marks`, `handles`; `hem.type`, `hem.allowance_mm`, `hem.cord_exits`;
`stitching.allowance_mm`, `stitching.sides`; `welding.overlap_mm`; `construction.method`;
`seams.skirt_seam`, `seams.skirt_height_mm`; `quote.ease_cm`, `back_strip_cm`,
`lounger_slope_cm`; `desk.*`; `questions.digest_hours`, `answer_digest_hours`; `spend.budget_eur_month`,
`warn_pct`, `hourly_spike_eur`, `hard_stop`; `suggest.per_hour`, `per_day`, `visitor_eur_day`;
`match.threshold_pct`, `choice_pct`, `mode`, `drawing_statuses`, `drawing_size_tol_cm`.
Everything else stays developer-only (read-only in the studio). The prices (`quote.*` money and
minutes) stay in Prices, where they already are versioned.

## 7. Visual direction

**A studio design system** in one file of tokens, shared in spirit with the website (ADR-105) but
sized for work:

- **Colour**: the website's paper `#F3F1EC`, stone, surface, hairlines, warm ink `#26241F`, sand
  `#C8B593` for selection and accents; a near-black header. Status colours used *only* for state:
  ok (green), warn (amber), bad (red), info (blue). A dark theme from the same tokens for the
  whole studio (today only the Desk has one).
- **Type**: Work Sans only (self-hosted, as the shop), 14 px body, 12.5 px small, 20 / 24 px
  headings, tabular numerals. Drop Poppins, Fraunces, DM Sans and Caveat from the studio (the
  website keeps its own).
- **Density**: 32 px controls, 26 px small buttons, 4-point spacing, 8 px radius, rectangular
  buttons (no pills) with one primary per view; hairline panels instead of floating cards.
- **Header**: one small mark + "Cover Studio", five sections, search, ?, me. One line at every
  width.

**Page templates** (every page is one of four):

1. **List** (All covers, Orders, Requests, Workshop): page head (title, one line, the primary
   action), one filter row, a table with sticky header, row click opens the detail; selection
   bar for batch actions.
2. **List + detail** (Desk, Questions, Orders, Matches, B2B customers, Arrangements): a 340 px
   queue with its filters on the left, the detail on the right with a head (name, chips,
   secondary actions under *More*), tabs, and a sticky **action bar** at the bottom. Below
   1100 px the list and the detail take turns (← List).
3. **Object page** (a cover): header (picture, name, facts, the 2–3 main actions + *More*), a
   status strip (steps, grade, status, Desk, approval, last run), tabs in the address.
4. **Settings form** (Settings, Prices, a cover's Adjust): vertical or sub-menu tabs; intro;
   rows of name / control / explanation + source; sticky Save bar; *Advanced* folded.

**Toolbars.** Grouped left to right: *what you see* (menus, segmented view), *tools* (Measure),
then a spacer, then *rare or expensive* actions in a menu (Simulate: rain again, drape again ≈
40 min) and links (Check list). The 3D viewer:

| today (one row, up to 15) | proposed (6) |
|---|---|
| Furniture · Balloons · Chair space · Cover surface · Panels · Show air vents · Vent sizes · Show dimensions | **Show ▾** (Layers: furniture, cover surface, panels, balloons, chair space; On the cover: air vents, vent sizes, overall dimensions; the mouse hint) |
| Rain · Drape · Unfold · Back to the design · Stop the rain | **Design · Rain · Drape · Unfold** (one segmented control: which cover you look at); *Water* appears inside Drape |
| Measure / Stop measuring | **Measure** (toggle) |
| Rain simulation / Simulate again · Drape simulation / Drape again | **Simulate ▾** (rain again ≈ 1 min, drape again ≈ 40 min) |
| Check list (PDF) | **Check list** |
| "Drag to turn, scroll to zoom, right-drag to move." | in Show ▾ |

The choices stay remembered per browser, as today.

## 8. The prototype

`out/uiaudit/prototype/index.html` (+ `proto.css`, `proto.js`): static HTML, no backend, no
build. Open the file in a browser (double-click, or `xdg-open`), or serve the folder
(`python3 -m http.server -d out/uiaudit/prototype 8099`). It shows:

- the header with five sections, the sub-menu bar and the hover menus; counts;
- **Work → Desk**: queue + card with the four tabs (Check, Pieces & revisions, Correct this
  cover, History), the action bar, *After sewing* and *More* menus; the arrangement card;
- **Work → Questions** and **Work → Workshop**;
- **Covers → All covers** (table and cards), **New cover**, **Product list**;
- **a cover's page** (`#/model/drawing-c1/3d`): header, status strip, 7 tabs, the compact 3D
  toolbar with its *Show* and *Simulate* menus, Pieces, Adjust, Compare, History, Files;
- **Prices** in the new layout (draft bar on top, sub-menu tabs, the live example beside);
- **Settings** with every tab filled with the real settings and their explanations;
- **old links** redirect (try `#/admin`, `#/catalogue`, `#/desk`);
- **View as** (bottom right): Rick, Rens, Eddy, the workshop — the sections and actions change;
- light / dark (me menu, or the system setting); tablet width (resize to 820 px).

Every name and number in it is an example. Screenshots: `out/uiaudit/after/1440-light/`,
`820-light/`, and a few dark ones.

### Before / after (local screenshots, not in git)

| | before (`out/uiaudit/before/1440/`) | after (`out/uiaudit/after/1440-light/`) |
|---|---|---|
| Desk | `03-desk.png` (4,578 px, 77 buttons), `04-desk-card.png` | `01-work-desk.png`, `02-work-desk-correct.png` |
| Arrangement at the Desk | `06-desk-arr.png` | `03-work-desk-arr.png` |
| Models / Catalogue | `01-models.png`, `02-catalogue.png` | `06-covers-table.png`, `07-covers-cards.png`, `08-covers-new.png` |
| A cover | `33-model.png`, `44-model3d.png` | `09-model-3d.png`, `10-model-pieces.png`, `11-model-adjust.png`, `12-model-history.png` |
| Prices | `11-prices.png`, `26-admin-prices.png` | `14-prices-materials.png` |
| Settings | `20-admin.png` … `32-admin-system.png`, `24-admin-shop.png` (3,836 px) | `15-settings-company.png` … `19-settings-mail.png` |
| Tablet | `out/uiaudit/before/820/` | `out/uiaudit/after/820-light/` |

## 9. Migration plan: small, releasable steps

Each step is one release (`scripts/release.sh`), keeps every feature, has a browser check
(an e2e script in `apps/web/e2e/`, at 1440 and 820 px) and updates the handbook in the same
commit. Old links redirect from step 1 on.

1. **Routes and the header** (no visual change to pages). A small router with section/page/tab
   paths; redirects for every old route; the model page's tab and Admin's tab in the address
   (fixes the "tab sticks to the next model" bug); the five sections and the sub-menu bar; Admin
   and Website out of the user menu; start page per person. *Check*: every old link lands on its
   page; every page reachable for each role; header on one line at 820 px.
2. **Settings, part 1: the shell and what exists.** `#/settings/<tab>` with the vertical tabs;
   Users, Mail, Logged in, Audit, System moved in unchanged; Shop settings rebuilt as **Company
   & shop**, **Matching**, **Website & API keys** from a small schema (label, help, unit, kind,
   default) instead of the raw JSON form; B2B terms and the Requests tab's settings moved; all
   recipients into **Mail & notifications**. Data stays where it is (same API). *Check*: every
   field of the old forms is present and saves.
3. **One approver list, one owner list.** Users get *may approve* (exists) and *owner*; the Desk
   reads them; `desk.approvers` and `questions.owners` remain as a fall-back for one release, then
   go. (Needs Q2 for the approval itself.)
4. **Settings, part 2: owner-editable defaults.** The company-override layer in app.db (versioned,
   audit), applied after `config/defaults.yaml`; `cover params` shows it; **Cover defaults**,
   **Desk & approval**, **AI & spending** tabs; developer-only keys read-only. Duplicates resolved:
   colours from the price set; the matching thresholds show their effective value. ADR + tests
   (the registry test learns the new layer).
5. **The Desk card.** Four tabs (Check, Pieces & revisions, Correct this cover, History) in the
   address; the action bar with *After sewing* and *More*; *Let the AI read it* under More; the
   product-list upload to Covers → Product list; AI spend tile to admins only. Keys unchanged.
   *Check*: `desk_pictures.py`, `questions.py`, `arrangements_desk.py`, `measure.py` updated and
   green in Chromium, WebKit, Firefox and Edge.
6. **A cover's page.** Header + status strip; 7 tabs; catalogue info as *Edit details*; *Since
   the run before* into History (without `null →` noise); the compact 3D toolbar (Show ▾, view
   segment, Measure, Simulate ▾). (Needs Q2 for the approval card.)
7. **The look.** The studio tokens and Work Sans everywhere (one stylesheet, `desk.css` folded in),
   the four templates, dark mode for the whole studio; drop the extra fonts. Page by page, so a
   release never mixes half a page.
8. **Covers and Workshop.** *All covers* with Table / Cards (Models + Catalogue), *New cover*
   (three uploads), *Workshop* (approved covers, files, measured, fits) and the workshop right
   (Q4). Learning without its upload card.
9. **Tidy up.** Remove the old pages' code and the redirect shims that are no longer hit (the
   redirects themselves stay), the search over everything, the handbook rewritten around the new
   map (and in Dutch where the owner wants, Q1), CLAUDE.md's command list updated.

Steps 1–2 give the biggest relief for the least risk; 5 is the one Rens feels most; 4 is the only
step that changes how values are applied and gets its own ADR.

## 10. Open questions for the owner

1. **Language.** CLAUDE.md says "UI in English". Rens's guides and the questions are Dutch, and
   you used Dutch names (Werk, Catalogus, Instellingen). Keep English, switch the studio to Dutch,
   or let each person choose (the website already has the machinery)?
2. **One approval.** May the Desk's *Approve* become *the* approval of the definitive drawing
   (stamped PDFs, status production), so the model page's separate approval card goes? Or do
   you want two steps (Desk = the shape is right; definitive = may be produced)?
3. **Start pages.** Rens and Wout start on Work → Desk, you and editors on Covers — or you on
   Work too?
4. **The workshop.** Its own login(s) with a *workshop* right: see the Workshop page, download
   DXF / lists, enter measured sizes and fits, but not approve? Who are they (names, e-mail)?
5. **Which defaults you want to change yourself** (the list in §6), and whether a change there
   should recalculate covers (we suggest: never by itself; a button "recalculate the covers this
   affects").
6. **Wording.** "Covers" for the catalogue (instead of Models / Products), "Pieces" everywhere
   (instead of Panels), "Adjust" for a cover's own settings — agreed?
7. **Order of the steps**: start with 1–2 (navigation and Settings), or with 5 (the Desk card,
   which Rens uses most)?

## 11. What was built (11 Oct 2026, night; ADR-122)

The owner said to build the logical layout now. Steps **1, 2, 5 and 6** are built on the branch
(not released); the business questions (§10) are kept as they are today: English, both
approvals, no workshop role, the defaults read-only, the start pages as below.

- **Step 1 — routes and the header:** `apps/web/src/nav.ts` (sections, pages, rights, tabs,
  `redirect`, `parse`); the header on one line, the sub-menu bar, counts on Work/Questions;
  every old address redirects; tabs in the address everywhere; start pages: approvers → Work →
  Desk, an admin → the section page he used last, others → Covers.
- **Step 2 — Settings:** `apps/web/src/SettingsArea.tsx`: 11 tabs in 4 groups; the shop's
  settings in plain words over the same stored keys; B2B terms moved in; every mail recipient
  in one list; Mollie key masked with Replace, under Website & API keys; the YAML defaults
  read-only on Desk & approval, Cover defaults, AI & spending.
- **Step 5 — the Desk card:** four tabs, the sticky decision bar with *After sewing ▾*, *More*;
  the latest rejection on top of Check; the drawing and 3D on Check and Correct, mounted on
  every tab for the pictures; product list → Covers; the spend tile for admins.
- **Step 6 — a cover:** the head and status strip, seven tabs with addressable sub-views, the
  compact 3D toolbar; the approval card, jobs, a Desk rejection and today's warnings above the
  tabs; "since the run before" in History without noise.
- **Codex's second opinion** (taken where it fits): an admin's remembered start page; Photo
  test under *Tools*; nothing buried (the approval card, Withdraw and the approved PDFs, the
  kind check, the batch bar, the learned rules, Send to the Desk all stay where they were or
  above the tabs); vents and dimensions as quick toggles, the layers shown on the Show button,
  Water beside Drape, simulation times shown; 40 px touch targets on a tablet; digest timings
  under Mail; secrets masked with Replace; unsaved-edit warnings; the API's rights unchanged.
  Not taken: merging Users & rights with Logins & audit log into one tab (the owner named them
  as two tabs).
- **Codex's adversarial review of the branch** found three things, all fixed: the Mollie key's
  *Keep* could write an empty key after a first save (the control now follows the stored,
  shortened key, with an explicit *Remove*); a correction being written was lost when the Desk
  card's tab changed (Corrections now stays mounted, and leaving the cover with one asks);
  Back/Forward skipped the unsaved-edits question (now asked, and the address restored).
- **Checks:** `apps/web/e2e/uinav.py` (every menu item per role, every old address, a cover's
  and a card's tabs, 1440 and 820 px, screenshots in `out/uinew/`); the existing browser checks
  follow the new addresses and pass on scratch copies: desk_pictures (Chromium, WebKit, Firefox
  at 1440 and 820, and Edge with the office policies), questions (the same four), measure,
  prices, priceimport, arrangements_desk. b2b: the admin's part (Shop → B2B customers, invite,
  a fixed price) passes; the buyer's catalogue stays empty on the scratch copies at hand (no
  published B2B list), which this change does not touch. `make e2e` (flow.py) follows the new
  tabs up to the approval of the definitive drawing, which fails on the test chair in the API
  ("cannot save with zero pages", the stamped PDF), unrelated to the layout: to look at.

### Steps 7, 8 and 9 (12 Oct 2026; ADR-124)

- **Step 7 — the look:** one stylesheet, `apps/web/src/studio.css`, starting with the tokens
  (light and dark values); desk.css, desk-products.css, b2b-admin.css and the old house style
  folded in, the Desk's own palette gone. Work Sans everywhere, self-hosted (no Google fonts:
  Poppins, Fraunces, DM Sans and Caveat are gone from the studio; the shop and the B2B shop keep
  theirs). Dark mode for every page: the computer's setting, or ◐/☀/☾ left of the name,
  remembered per browser; drawings, patterns and pictures stay on white, the 3D on its light
  stage, the configurator always light. The four templates in `layout.tsx` (list, queue,
  object, form); every page of the router is one of them.
- **Step 8 — Covers and Workshop:** All covers is one component (`Covers.tsx`) for Table and
  Cards with one filter row (search, category, cover, status, tag, sort, select all shown), a
  box on every card, the batch bar; filters and selection stay across the switch. New cover has
  the three uploads (3D file, drawing, reference pairs); Learning lists the results only. Work →
  Workshop (`Workshop.tsx`, `GET /api/workshop`): approved and produced covers, their files (the
  DXF only past the approval gate), the revision to cut, the measured fit, the customers' fit
  answers (editors and admins); read-only, every role, no new right (question 92).
- **Step 9 — tidy up:** Gallery.tsx, QuickSearch.tsx, the old Models list and the CSS of gone
  pages and tabs removed; every unknown address → the start page; every redirect stays
  (`#/models` too: named in the handbook since v1.36.0). The header's search finds covers, Desk codes, questions
  and (admins) orders, Ctrl+K. The handbook rewritten around the map, in English
  (docs/handbook/README.md is its index, workshop.md new). CLAUDE.md's command list updated.
- **Checks:** uinav.py light and dark at 1440 and 820 with a contrast check of every text; the
  other browser checks on a scratch copy (mail, public URL, shop domain, Mollie cleared; login
  code off). Screenshots in out/uinew2/<width>-<theme>/.

| before (ADR-122) | now (ADR-124) |
|---|---|
| All covers: two components, Table filters (search, category, grade, status, batch) and Cards filters (search, grade, category, tag, sort) apart | one filter row for both; the selection and batch bar in both |
| New cover: 3D file and drawing; Learning: the zip upload and the results | New cover: 3D file, drawing, reference pairs; Learning: the results |
| Work: Desk, Questions | Work: Desk, Questions, Workshop |
| Search: models only | Search everything: covers, Desk codes, questions, orders (admins) |
| Light only (the Desk had its own dark) | Light and dark for the whole studio |

### Inventory: every screen, action and field, and where it is now

| before | now |
|---|---|
| Header: Models, Desk, Catalogue, Arrangements, Learning, Prices, Guide, crumb, search, Admin / Website, name, Log out | Work · Covers · Shop · Prices · Settings; crumb (on a cover); search; Guide; name (account); Log out |
| Models: New model upload (file, units, up) | Covers → New cover |
| Models: New cover from a drawing | Covers → New cover |
| Models: table, search, category / grade / status filters, checkboxes, batch bar | Covers → All covers (Table), unchanged |
| Catalogue: cards, search, grade, category, tag, sort | Covers → All covers → Cards (`?view=cards`), unchanged |
| Arrangements: everything incl. Send to the Desk | Covers → Arrangements, unchanged |
| Learning: zip upload, batches | Covers → Learning, unchanged |
| Desk tabs Covers / Questions | Work sub-menu Desk / Questions (count on Questions and Work) |
| Desk top: title and keys, KPI tiles, learned-rule proposals, pipeline | unchanged |
| Desk top: AI spend tile | admins only; Settings → AI & spending |
| Desk top: product-list upload | Covers → Product list (link in the card's More) |
| Desk queue: search, status buttons, series chips, sort | unchanged (kept while moving between cards and tabs) |
| Card head: code, outcome, scores, status, Open model | unchanged (Open cover ↗) |
| Card head: Let the AI read it | More → Let the AI read it (cost shown) |
| Card head: Edit arrangement | More → Edit arrangement |
| Card: 2nd round note, AI reading note, arrangement status | above the tabs |
| Card: drawing (pages, zoom) / arrangement plan and members, 3D viewer | Check and Correct tabs (mounted on all) |
| Card: Check list (PDF) in the 3D caption | the 3D toolbar and More |
| Card: Products, What the program read, What the AIs say (all differences) | Check tab |
| Card: Pieces, Revisions (cut this, all revisions) | Pieces & revisions tab |
| Card: Correct this cover (seams, vents, sizes, shape, pictures) | Correct this cover tab |
| Card: Measured on the sewn cover | above the tabs while measuring |
| Card: History (pictures, measured sizes) | History tab; the latest rejection also on Check |
| Action bar: Approve, Reject (reasons, text, pictures), Comment, Undo | unchanged, sticky |
| Action bar: Produced, after-sewing note, Measured…, Fits, Does not fit | After sewing ▾ row in the same bar |
| Questions: everything | Work → Questions, unchanged |
| Prices: draft bar, publish, versions, 6 tabs, import inside Channels | Prices; the tabs are the sub-menu; Import (Excel) its own tab |
| Admin → Users | Settings → Users & rights |
| Admin → Orders | Shop → Orders |
| Admin → B2B customers (companies, invites, orders) | Shop → B2B customers |
| Admin → B2B customers → B2B settings | Settings → B2B terms |
| Admin → Matches | Shop → Matches |
| Admin → Shop settings: company, domain, languages, colours, bbq, logo, og_image, delivery notes, products, film, story | Settings → Company & shop |
| Admin → Shop settings: shipping (0 / 1 / 2) | Settings → Company & shop → Shipping per country (a table) |
| Admin → Shop settings: payment (Mollie, bank transfer) | Settings → Website & API keys → Payment |
| Admin → Shop settings: matching.* | Settings → Matching |
| Admin → Shop settings: notify_email, fit_mail | Settings → Mail & notifications |
| Admin → Shop settings: website_link.closed, home_story, the website's key | Settings → Website & API keys |
| Admin → Shop settings: prices (hidden) | Prices (unchanged) |
| Admin → Photo test | Shop → Tools: Photo test |
| Admin → Prices & costing | Prices (redirect) |
| Admin → Website (AI); `#/website` for editors | Shop → Website (AI) for both; Publish for admins |
| Admin → Requests: the table | Shop → Requests |
| Admin → Requests: embed origins, API keys | Settings → Website & API keys |
| Admin → Requests: requests are mailed to | Settings → Mail & notifications |
| Admin → Mail and address: SMTP, test mail, login code, public address | Settings → Mail & notifications |
| Admin → Logged in, Audit log | Settings → Logins & audit log |
| Admin → System (facts, releases, last alerts) | Settings → System |
| Admin → System: alert address | Settings → Mail & notifications |
| Cover: summary card, Run again | the head |
| Cover: Check: what is this file? | above the tabs, unchanged |
| Cover: approval card (Approve, Ask, Withdraw, approved PDFs) | above the tabs, unchanged; its state also in the strip |
| Cover: catalogue info (category, family, status, tags, notes) | Edit details |
| Cover: job bar | above the tabs |
| Cover: Since the run before | History → Approval & changes (and a count in the strip) |
| Cover tabs: 3D | 3D |
| Your drawing, Your reference, AI advice | Compare → the same three |
| Seams | Seams |
| Patterns, Size drawing, Cut pieces | Pieces → Flat patterns, Size drawing, Cut pieces |
| Settings (the cover's) | Adjust |
| Revisions, Warnings and log | History → Revisions, Warnings and log; today's warnings also above the tabs |
| Downloads | Files |
| 3D: 5 layer checkboxes | Show ▾ (the layers on are named on the button) |
| 3D: Show air vents, Show dimensions | quick toggles Vents, Dimensions (and in Show ▾) |
| 3D: Vent sizes, the hint | Show ▾ |
| 3D: Rain / Stop the rain, Drape / Back to the design, Unfold / Back to the cover | one switch Design · Rain · Drape · Unfold |
| 3D: Water | beside the switch while on Drape |
| 3D: Measure | Measure |
| 3D: Rain simulation / Simulate again, Drape simulation / Drape again | Simulate ▾ (with the time each takes; running: shown in the bar) |
| 3D: Check list (PDF) | Check list (PDF) |
| Account, Guide, Configure, Welcome, Login | unchanged |

## 12. One cover, one page; settings in Settings (12 Oct 2026; ADR-126)

The owner (12 Oct 2026): *"we have to many different tabs, like the pricelist, why is this not
vissable in the item settings, all settings related to a covers should be visseble in the cover,
like cost, sales price etc, now there is to much information all over the place, it needs to be
less and more together"*; and that evening: *"dat mag alles in de settings page komen, maar
product gelateerde informatie bij het product houden niet overal plaatsen"* (general settings may
all go into Settings; what belongs to a product stays with the product and is not repeated
elsewhere).

### 12.1 Inventory: everything about ONE cover, where it was and where it goes

| what (about one cover) | was | now |
|---|---|---|
| Costing: fabric m², components, labour, total cost EUR and IDR, CSV, PDF | Prices → Costing (pick the cover from a list) | the cover → **Price & shop** → Cost |
| Its B2C price (incl. VAT), B2B price (ex VAT), margin per channel | Prices → Costing (per channel card) | the cover → Price & shop → Prices |
| Whether its price is fixed or calculated, and the fixed price itself | Prices → Channels & price lists → Fixed prices (a list of model ids, per channel) | the cover → Price & shop → Prices (source per channel; admins set or remove the fixed price **in the draft**) |
| Its price in the draft vs live; "N changes in the draft — Publish" | Prices → the draft bar (whole set) | the cover → Price & shop (its own draft vs live, the draft's size, Publish for admins, with the preview count and a confirmation) |
| Its row in an imported price list (match, price) | Prices → Import (Excel) | the import stays one action (Settings → Prices & costs → Publish & versions); the cover shows the result: a fixed price in the draft |
| Its price moving in a preview | Prices → Preview changes (all covers) | Settings → Publish & versions (all covers, it is about the whole set) |
| Offered in the shop / configurator as an existing cover ("Bestel direct"), its kind, sizes | nowhere (only by trying the configurator); Shop → Matches showed it per request | the cover → Price & shop → Shop (offered or why not) |
| Its category from the price list (section, family, item, suits) | nowhere in the studio (ADR-114, `match_list`) | the cover → Price & shop → Shop |
| "Bestel direct": how its direct-order price is made (fixed B2C price, or the configurator's minus the stock discount) and the delivery note | Settings → Matching (discount), Settings → Company & shop (note) | the cover → Price & shop → Shop (what applies to this cover; the settings themselves stay in Settings) |
| Match requests that proposed or chose it (learning) | Shop → Matches (all requests) | the cover → Price & shop → Shop (its requests, linking to Shop → Requests) |
| Orders of this cover (existing-cover orders, the production model of an order) | Shop → Orders (all orders) | the cover → Price & shop → Orders and quotes (links to Shop → Orders/<n>) |
| Quotes asked for this cover (stock quotes) | nowhere (files in quotes/) | the cover → Price & shop → Orders and quotes (recent ones) |
| B2B companies with their own price for it | Shop → B2B customers → a company → fixed prices | the cover → Price & shop → B2B (which companies, their price; editing stays on the company) |
| Desk status and history | the cover's strip (status), the Desk card | the cover's head: a summary row (Desk status, approved by, produced, fit, revision to cut, open questions) |
| Workshop: files, the revision to cut, measured fit | Work → Workshop (all approved covers) | the cover's head summary (fit, revision) and Pieces → Files |
| Questions about it | Work → Questions (search) | the cover's head summary: open questions about it, linking to each |
| Catalogue info (category, family, status, tags, notes, no-cover) | the cover → Edit details | unchanged |
| Files (downloads) | the cover → Files (a tab) | the cover → Pieces → Files (one tab fewer) |

What stays general (Settings, not per cover): materials and their prices, labour rate and
times, the exchange rate, the channels' extra costs, markup or margin, rounding, VAT, the
accessories' fixed prices (balloon, frame), the draft as a whole, preview, publish, versions and
rollback, the Excel import, the stock discount, the delivery note, the B2B terms.

### 12.2 The design

- **Header: four sections** — Work · Covers · Shop · Settings. Prices is no longer a section.
- **A cover: seven tabs** — 3D · Pieces · Seams · Adjust · Compare · History · **Price & shop**.
  Files moved into Pieces (Cut pieces · Flat patterns · Size drawing · Files); the old
  `#/model/<id>/files` and `/downloads` redirect there.
- **Price & shop** (`#/model/<id>/price`): Cost (the costing lines, EUR and IDR, CSV, PDF;
  live or draft), Prices (per channel: shown price, ex/incl. VAT, margin, source fixed or
  calculated, the draft's value beside the live one; admins type a fixed price or remove it:
  `PUT /api/prices/draft/fixed`, which writes the same draft row the old Channels table wrote),
  "the draft has N changes — Publish" (admins; the preview count first and a confirmation),
  Shop (offered or why not, kind, sizes, category from the price list, the direct-order price
  and its delivery note), B2B (companies with their own price; admins), Orders and quotes
  (admins; links). Editors see it read-only; viewers see the cover without prices (as before:
  prices are for editors and admins).
- **Covers → All covers** gets optional **price columns** (cost, B2C, B2B, margin, source; live
  or draft), switched on with *Prices* in the filter row and remembered in the address
  (`?prices=1`); a price cell opens the cover's Price & shop tab. No separate price page.
- **Settings** gets a group **Prices & costs** with three tabs: *Costs* (materials, labour,
  exchange rate on one page), *Price rules* (per channel: extra costs, markup or margin,
  rounding, VAT; the accessories' fixed prices; the costing of a configurator product), and
  *Publish & versions* (the draft, preview, publish, discard, the versions with rollback, and the
  Excel import). Editors see these three (read-only, as Prices before); every other Settings
  tab stays admin-only.
- **Settings, fewer tabs:** Matching and B2B terms → *Selling*; Desk & approval and Cover
  defaults → *Rules & defaults* (both read-only yaml); System and Logins & audit log → *System
  & logs*; Photo test moved from Shop into *AI & spending* (its tool).
- **Shop keeps only shop-wide pages:** Orders · Requests · B2B customers · Website (AI).
  Matches is a part of Requests (both are what customers asked).
- **Every old address redirects:** `#/prices[/materials|labour|rate]` → Settings → Costs,
  `#/prices/channels` and `/costing` → Price rules, `#/prices/import` and `/versions` → Publish
  & versions, `#/shop/matches` → Requests, `#/shop/phototest` → AI & spending,
  `#/settings/matching|b2b` → Selling, `#/settings/desk` → Rules & defaults, `#/settings/activity`
  → System & logs, `#/admin/prices|matches|phototest` likewise.
- **Unchanged:** the pricing maths, VAT, rounding, draft → preview → publish → versions, the
  rights (admins edit and publish, editors look, viewers none), B2B scoping, the approval gate,
  server-only settings.

| | before | after |
|---|---|---|
| Header sections | 5 | 4 |
| Prices | 7 tabs | 0 (3 tabs in Settings; the per-cover part on the cover) |
| Shop | 6 pages | 4 |
| Settings | 11 tabs | 11 (of which 3 are the former Prices; 8 of the former 11) |
| Tabs and pages in Prices + Shop + Settings | 24 | 15 |
| A cover | 7 tabs | 7 tabs (Files inside Pieces, Price & shop new) |

## 13. The owner's answers on approval and the workshop (13 Oct 2026; ADR-128)

- **Q2, one approval: yes, only the Desk** (question 83 a). The model page's *Approve the definitive
  drawing* is gone; its card shows the Desk's approval, the stamped PDFs and *Send to the Desk for
  approval*. Step 3's approver list: admins, *may approve* and `desk.approvers` all approve at
  the Desk; `desk.approvers` stays (it names Rens, Wouter and Wout by user name).
- **Q4, the workshop: its own login** (question 92 a): role `workshop`, start page Work →
  Workshop, Work only, fits, comments and pictures on a Desk card, its own questions, the DXF of
  approved covers; never approving, prices or settings (an allow-list in the API).
- With it: every cover's DXF behind the Desk (question 84 b) and orders into production by a
  click in the studio (question 86 b): Work → Workshop shows the orders to make on top.
