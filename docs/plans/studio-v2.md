# Cover Studio 2.0: fresher colours, iOS-like icons, less loose text (proposal, 13 Oct 2026)

Status: **built (ADR-130).** The owner chose **A · iOS light**, "with icons etc." (13 Oct 2026),
with the open points of §8 decided as: iOS blue as the one accent; a light header; the system
font with Inter as the web fallback; explanations behind an (i) everywhere; darker field borders
(3:1); waiting blue, produced purple. Later the same day: **our own icons** instead of plain
Lucide ("maak zelf unieke icons voor de backend"): `apps/web/src/icons/glyphs.tsx`, Lucide only
for generic utility glyphs. What was built, the counts and the checks: ADR-130 in
docs/DECISIONS.md. Below, unchanged, the proposal as the owner saw it (its file references are
to the proposal branch `studio-v2-proposal`, `out/studio2/`).

---

Original status: proposal for the owner to choose from. Mock-ups built
on a scratch copy from main (`004f218`, v1.40.0+), on a throwaway patch (`out/studio2/studio2-mockup.patch`,
not for merging).

## Samenvatting voor Rick

Je vroeg (13 okt): *"vooral de kleuren moeten we goed naar kijken, ik zou het graag wat frisser
zien, met meer icons zoals in iOS, er is heel veel losse text wat het onoverzichtelijk maakt."*

**Wat ik deed.** Drie richtingen gebouwd als echte studio op een kopie (17 hoezen, testgebruikers,
mail/publieke URL/shopdomein/Mollie leeg, inlogcode uit; nooit live). Elke richting heeft dezelfde
iconen en dezelfde tekstvermindering, zodat je alleen kleur en vorm vergelijkt. Van elke richting
zes pagina's (Desk met kaart, Workshop, All covers, 3D van een hoes, Price & shop, Settings),
licht en donker, op 1440 px, plus de huidige studio ter vergelijking.

**Bekijken.** Eén overzichtsplaat per richting:

- nu: https://preview.s2dio.living/media/studio2-current-sheet.jpg
- A · iOS licht: https://preview.s2dio.living/media/studio2-a-ios-sheet.jpg
- B · Frisse huisstijl: https://preview.s2dio.living/media/studio2-b-brand-sheet.jpg
- C · Leisteen & mint met zijbalk: https://preview.s2dio.living/media/studio2-c-sidebar-sheet.jpg
- de iconen: https://preview.s2dio.living/media/studio2-icons.jpg

Losse schermen: `studio2-<a-ios|b-brand|c-sidebar|current>-<light|dark>-<desk|workshop|covers|cover3d|price|settings>.jpg`
op dezelfde plek. De vergelijkingspagina met alles erin: `out/studio2/index.html` (op de server).

**De drie richtingen in het kort.**

- **A · iOS licht** — lichtgrijze ondergrond, witte kaarten met ronde hoeken, één helder iOS-blauw
  voor alles wat je kunt doen, het systeemlettertype (SF op Mac/iPad). Instellingen als een
  iOS-lijst met gekleurde icoontegels. Het meest "fris" en het meest vertrouwd voor wie een iPad
  gebruikt.
- **B · Frisse huisstijl** — warm gebroken wit, het SUNS-zand blijft (selectie, de lijn onder de
  kop), een frisgroen voor alle knoppen. Work Sans blijft. Het dichtst bij de website.
- **C · Leisteen & mint, zijbalk** — koel wit met mint-teal, de vier secties als zijbalk links
  zoals op een iPad. Meer ruimte boven, maar een grotere verandering (en twee zijbalken op
  Instellingen).

**Mijn advies: A**, met één ding uit B: het zand als selectiekleur van de hoes zelf (3D) blijft
zoals het is. Waarom: het geeft het meest het frisse iOS-gevoel waar je om vroeg, het
contrast is ruim (alle tekst ≥ 4.8:1, ook donker), één accentkleur maakt in één oogopslag
duidelijk wat klikbaar is, en de status-kleuren (groen goedgekeurd, blauw wacht, rood afgekeurd,
oranje waarschuwing, paars geproduceerd) vallen niet samen met die accentkleur behalve "wacht".
B is de veilige keus als de studio op de huisstijl moet lijken; C pas als je de zijbalk wilt.

**Minder losse tekst: 525 → 33.** In de code van main: 311 uitleg- en hulpregels, 148 herhaalde
labels, 66 lange knopteksten op de hoofdpagina's. Na het voorstel staan er nog 33 als lopende
tekst (lege lijsten, fouten, live status: die moeten zichtbaar blijven). De rest wordt een (i)
naast de titel, een icoon met tooltip, een kort label of een chip. Settings → Company & shop:
26 hulpregels → 0 zichtbaar, elk achter een (i).

**Vragen aan jou** staan onderaan (§8).

## 1. How it was done

- **The studio**: this worktree's main (`004f218`), served by `cover-web` on 127.0.0.1:18260 with
  a scratch data directory `out/studio2/data` (git-ignored, removed after the shots; `scratch_setup.py` rebuilds it): 17 models copied from the live data
  (approved, waiting, rejected drawing covers, an arrangement, a barbecue, three SUNS models), the
  questions, learning, product list, usage and price folders, and `app.db` taken with SQLite's
  backup API. On the copy: mail, public URL (set to the scratch address), shop domain, links and
  logo, Mollie, sessions, tokens, invites, orders, requests and B2B logins cleared; the users
  replaced by the test users (rick, rens, wout, eddy, vic); `cover-users two-factor off`.
  Script: `out/studio2/scratch_setup.py`. Live was not logged into and not touched.
- **The directions**: one throwaway patch (icons, text reductions, `Ico.tsx`, `studio2.css`) and
  the tokens of each direction as an override (`out/studio2/patch/studio2-tokens.css`, generated
  from `out/studio2/tokens.py`, scoped by `html[data-dir=a|b|c]`). Built four times (current, a,
  b, c) with `VITE_STUDIO2=<dir>`; `COVER_WEB_DIR` points the server at each build.
- **The screenshots**: `out/studio2/shoot.py` in the Playwright Docker image
  (`--user $(id -u):$(id -g)`), 1440 × 900, light and dark (the browser's colour scheme and the
  studio's own theme choice), logged in as rick. Only pages are opened, nothing saved. Every
  screenshot was looked at.
- **The audit**: Codex (read-only) read the JSX of every main page and listed each explanation,
  repeated label and long button with a proposal; I re-anchored every item on main
  (`out/studio2/audit_fix.py`: 509 of 525 found by their text, 286 line numbers corrected), judged
  which ones must stay visible, and wrote the table (§3). Items: `out/studio2/audit.json`.
- **Done by Codex** (reviewed before use): the loose-text audit's first listing, the first icon
  mapping per menu item, tab, action and status with the licence check
  (`out/studio2/icons-codex.json`; I changed 12 of its choices, §5), and an independent contrast
  table (§4.4). The design, the tokens, the patch and the screenshots are mine.

## 2. What is wrong now (from the screenshots)

1. **Colour**: a near-black header over warm grey paper and olive/khaki accents. Calm, but heavy
   and a little dull; the one primary colour (dark olive) looks the same as a disabled button.
   Status colours are muted (the Desk's pipeline: olive, brown, rust).
2. **Text**: every page opens with a sentence ("Every model and its cover. A row or a card opens
   the cover; tick some to run them together."), every Settings row has a helper sentence and a
   config key in mono (`company.legal_name`), the Desk's head is a line of shortcuts, the
   Workshop shows five underlined file links per row (45 links on one screen).
3. **No icons** except ↗ ▾ ✓ ✕ ◐ as characters: the header, sub-menu, tabs and toolbars are all
   words, so everything has the same weight.

## 3. Loose text: the audit, before → after

Counted in the JSX of main, per page (a cover's 7 tabs and the Settings tabs one by one).
"After" = what still stands as running text once the proposal is built; short labels, chips and
icons are not counted (they are no longer loose text). Kept on purpose: empty states ("Nothing
matches these filters"), errors, live status lines ("The AI is reading…").

| page | explanations / helper lines | repeated labels | long buttons | total before | visible after |
|---|---|---|---|---|---|
| Desk | 3 → 1 | 10 → 0 | 1 → 0 | 14 | 1 |
| Desk card | 22 → 4 | 11 → 0 | 6 → 0 | 39 | 4 |
| Workshop | 5 → 2 | 12 → 0 | 0 → 0 | 17 | 2 |
| All covers (table; cards the same) | 3 → 1 | 5 → 0 | 0 → 0 | 8 | 1 |
| Cover — 3D | 14 → 2 | 4 → 0 | 7 → 0 | 25 | 2 |
| Cover — Pieces | 23 → 2 | 1 → 0 | 4 → 0 | 28 | 2 |
| Cover — Seams | 4 → 0 | 1 → 0 | 7 → 0 | 12 | 0 |
| Cover — Adjust | 3 → 0 | 2 → 0 | 6 → 0 | 11 | 0 |
| Cover — Compare | 19 → 5 | 9 → 0 | 4 → 0 | 32 | 5 |
| Cover — History | 9 → 3 | 2 → 0 | 4 → 0 | 15 | 3 |
| Cover — Price & shop | 18 → 3 | 14 → 0 | 7 → 0 | 39 | 3 |
| Shop — Orders | 3 → 0 | 2 → 0 | 0 → 0 | 5 | 0 |
| Shop — Requests | 7 → 0 | 7 → 0 | 0 → 0 | 14 | 0 |
| Shop — B2B customers | 6 → 2 | 9 → 0 | 4 → 0 | 19 | 2 |
| Shop — Website (AI) | 4 → 0 | 1 → 0 | 2 → 0 | 7 | 0 |
| Settings — Company & shop | 26 → 0 | 2 → 0 | 0 → 0 | 28 | 0 |
| Settings — Selling | 12 → 0 | 3 → 0 | 0 → 0 | 15 | 0 |
| Settings — Costs | 29 → 1 | 6 → 0 | 2 → 0 | 37 | 1 |
| Settings — Price rules | 36 → 1 | 14 → 0 | 3 → 0 | 53 | 1 |
| Settings — Publish & versions | 18 → 2 | 10 → 0 | 3 → 0 | 31 | 2 |
| Settings — Users & rights | 4 → 0 | 5 → 0 | 2 → 0 | 11 | 0 |
| Settings — Rules & defaults | 2 → 0 | 1 → 0 | 0 → 0 | 3 | 0 |
| Settings — Mail & notifications | 14 → 0 | 2 → 0 | 0 → 0 | 16 | 0 |
| Settings — Website & API keys | 11 → 1 | 4 → 0 | 3 → 0 | 18 | 1 |
| Settings — AI & spending | 10 → 2 | 5 → 0 | 1 → 0 | 16 | 2 |
| Settings — System & logs | 3 → 0 | 1 → 0 | 0 → 0 | 4 | 0 |
| **all** (All covers counted once) | **308 → 32** | **143 → 0** | **66 → 0** | **517** | **32** |

(The table in `out/studio2/audit-table.md` counts All covers' table and cards apart: 525 → 33.)

What replaces what (the 525 items):

| becomes | how many | examples |
|---|---|---|
| (i) popover beside the title or field | 273 | page intros ("Every cover the Desk approved…"), every Settings helper line ("As registered; on invoices and the terms."), the Price & shop footnote |
| removed (the column head or the tab says it) | 80 | "Desk card" link on every Workshop row (→ an icon), "Fit on the sewn cover" → "Fit", `company.legal_name` under each label (→ the label's tooltip) |
| chip | 56 | "17 covers: 14 ready, 3 to check, 0 failed" → three status chips; "not measured yet" → "—" |
| icon + tooltip | 52 | Workshop files: Check list, Cut pieces (SVG), Cutting list, Size drawing → four icon buttons; Edit details, Desk card, Undo, More, Log out, Guide, Table / Cards |
| short label (≤ 2 words) | 64 | "Approve the definitive drawing" → "Approve drawing"; "Save in draft" → "Save"; "Run again" → "Run"; "Correct this cover" → "Correct"; "+ New cover" → "New"; "After sewing ▾" → "Sewn ▾"; "Search everything…" → "Search" |

Rules for every page (so new pages follow them):

1. A page or section explains itself in an (i), never in a line under its title.
2. A field's help is its (i); the config key is the label's tooltip, not a second line.
3. A label that would repeat on every row is the column head; a state is a chip with an icon.
4. A toolbar action is an icon with a tooltip and an aria-label; a page's one main action may
   keep a short label (≤ 2 words) next to its icon.
5. Visible stays: empty states, errors, live status, numbers.

## 4. The three directions

All three: Lucide icons (§5), the same text reductions, large rounded cards, pill-shaped sub-menu
and status chips with an icon, sentence-case table heads (no SPACED CAPITALS), links without
underline in tables, the search with a magnifier. Light and dark for each; every text pair meets
WCAG AA (4.5:1), checked by `out/studio2/tokens.py` and independently by Codex (§4.4).

Token names are the ones `studio.css` already uses; new: `--wait`, `--wait-soft`, `--made`,
`--made-soft` (the statuses had no own colour for waiting and produced), `--radius-lg`,
`--radius-sm`, `--icon-stroke`.

### 4.1 A · iOS light (recommended)

Grouped light-grey ground with white cards (iOS Settings), one iOS blue for everything you can
act on, a translucent light header (no more black bar), Settings tabs with coloured icon tiles.

| token | light | dark | | token | light | dark |
|---|---|---|---|---|---|---|
| bg | `#f2f2f7` | `#000000` | | accent (links) | `#0062cc` | `#5eb0ff` |
| surface | `#ffffff` | `#1c1c1e` | | primary (buttons) | `#0068d6` | `#0a6fe0` |
| sunken | `#f7f7fa` | `#121214` | | on-primary | `#ffffff` | `#ffffff` |
| stone (hover) | `#e9e9ee` | `#2c2c2e` | | accent-soft | `#e5f0ff` | `#0b2a4a` |
| line | `#e3e3e8` | `#38383a` | | head | `#f9f9fb` | `#161618` |
| line-strong | `#c7c7cc` | `#48484a` | | head-dim | `#636366` | `#aeaeb2` |
| ink | `#1c1c1e` | `#f5f5f7` | | focus | `#007aff` | `#0a84ff` |
| ink-2 | `#3a3a3c` | `#e5e5ea` | | | | |
| muted | `#636366` | `#aeaeb2` | | | | |

Contrast (text on its ground, light / dark): ink on bg 15.3 / 19.3; muted on bg 5.4 / 9.5, on
stone 4.95 / 6.3; accent on surface 5.8 / 7.4; white on primary 5.3 / 4.8; head-dim on head 5.7 / 8.2.

Status colours (text on its soft tint; dark in brackets):

| status | text | tint | ratio | icon |
|---|---|---|---|---|
| approved | `#18753a` (`#4cd964`) | `#e3f6e8` (`#10321a`) | 5.1 (7.7) | circle-check |
| waiting | `#0062cc` (`#5eb0ff`) | `#e5f0ff` (`#0b2a4a`) | 5.0 (6.3) | clock |
| rejected | `#d1001f` (`#ff6961`) | `#ffe8ea` (`#3d1414`) | 4.8 (5.7) | circle-x |
| warning | `#a34a00` (`#ffb340`) | `#fff1e0` (`#3a2a0f`) | 5.4 (7.8) | triangle-alert |
| produced | `#7a3fa8` (`#d6a3ff`) | `#f3eafa` (`#2e1d3d`) | 5.8 (7.8) | package-check |

Type: `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter Variable", Inter, system-ui`
(SF on Apple devices, Inter self-hosted elsewhere, OFL). Scale: page title 26/700 (−0.02 em),
section 20/650, card head 15/650, body 14/400, small 12.5, chips 12/550.
Shape: radius 10 (controls), 14 (cards), 8 (small), 999 (pills, chips); control height 34;
shadow `0 1px 2px rgba(0,0,0,.04)` on cards (none in dark: the surface step does it), pop-over
`0 12px 32px rgba(0,0,0,.14)`; spacing on a 4-px grid (4, 8, 12, 16, 20, 24), cards 16–20 inside.
Settings tiles in iOS system colours (blue, orange, green, teal, indigo, purple, grey) with white
glyphs.

### 4.2 B · Fresh brand

Warm off-white, SUNS sand for selection, the header's bottom line and the "to review" tile; a fresh
green for every action and link; Work Sans stays (the website's type); icons on sand tiles.

| token | light | dark | | token | light | dark |
|---|---|---|---|---|---|---|
| bg | `#faf8f4` | `#151512` | | accent / primary | `#1d7457` | `#6fd1a4` / `#2f9e74` |
| surface | `#ffffff` | `#1e1d19` | | on-primary | `#ffffff` | `#08130e` |
| sunken | `#f6f2ea` | `#191814` | | sand | `#d4bf96` | `#d4bf96` |
| stone | `#eee8dc` | `#2b2a24` | | sand-deep (text) | `#7d6440` | `#e2cfa8` |
| line | `#ebe5d9` | `#34322b` | | sand-soft | `#f5eddc` | `#3a3122` |
| ink | `#24221d` | `#f2efe7` | | head | `#fffdf9` | `#1a1916` |
| muted | `#685f50` | `#aca596` | | focus | `#1d7457` | `#6fd1a4` |

Statuses (text on its tint): approved `#1d7457` on `#e2f3ea` (4.95; dark `#6fd1a4` on `#173226`, 7.5),
waiting (sand-amber) `#86601a` on `#fbf0d6` (5.0; `#efc56b`, 8.4), rejected `#b23a2c` on `#fbe5e0`
(4.9; `#ff8f7d`, 6.7), warning `#9a5a00` on `#fdf0dc` (4.9; `#f2b04f`, 7.3), produced `#2a6390` on
`#e3eef7` (5.4; `#8fc3ec`, 7.7).
Note: approved and the action colour are the same green, so a green button and a green chip mean
different things; acceptable, but A separates them.
Type: Work Sans Variable, same scale as A. Shape: radius 10 / 16 / 8, control 34; warm shadows
`0 1px 2px rgba(60,48,20,.05), 0 6px 18px rgba(60,48,20,.05)`.

### 4.3 C · Slate & mint, sidebar (my alternative)

Cool paper and a mint-teal accent; the four sections become an iPadOS-style sidebar on the left
(brand, search, sections, then guide, theme, me, log out at the bottom), the sub-menu a pill row
on top of the page. Inter, a little denser (13.5 px body). Most room for the page's content
(no 102-px header block), but the biggest change; Settings then has two side columns, and the
breadcrumb in the header goes (the cover's title already says where you are).

| token | light | dark | | token | light | dark |
|---|---|---|---|---|---|---|
| bg | `#f6f8f9` | `#0f1417` | | accent | `#0b7a70` | `#5eead4` |
| surface | `#ffffff` | `#171e22` | | primary | `#0b7a70` | `#14b8a6` |
| sunken | `#f1f4f6` | `#13191c` | | on-primary | `#ffffff` | `#04201c` |
| stone | `#e6ebee` | `#222b31` | | accent-soft | `#e0f5f2` | `#0f3330` |
| line | `#e2e7eb` | `#2a343b` | | head (sidebar) | `#eef2f4` | `#13191c` |
| ink | `#16202a` | `#e9eef1` | | focus | `#0b7a70` | `#5eead4` |
| muted | `#5b6873` | `#9aa7b1` | | | | |

Statuses: approved `#137a3e` on `#e1f5e8`, waiting (indigo) `#4b55c8` on `#eceefe`, rejected
`#c4233b` on `#fde7ea`, warning `#a14d00` on `#fff0df`, produced `#0e6c96` on `#e2f2fa` (all ≥ 4.75;
dark: `#5fd38d`, `#a5abff`, `#ff8a9a`, `#f5b056`, `#7cc8ec`). Type: Inter, page title 22/700,
section 18, body 13.5, small 12. Shape: radius 8 / 12 / 6, control 32, shadow
`0 1px 2px rgba(16,32,42,.06)`.

### 4.4 Contrast check

Every text pair of §4 for each direction and theme — 25 text pairs and 3 non-text pairs × 6 —
is computed by `out/studio2/tokens.py` (table in `out/studio2/tokens.json`, and on the comparison
page): **no text pair fails AA**. Lowest text pairs: A light bad on bad-soft 4.82, A dark white on
primary 4.81; B light sand-deep on sand-soft 4.78; C light accent on accent-soft 4.59. Codex
computed every pair independently (`out/studio2/contrast-codex.md`): all agree within 0.02, and it
suggests the nearest hex for each pair under 5.0 (e.g. A dark primary `#0a6cdb` → 5.0, C accent
`#0a736a` → 5.0), worth taking in the build for some margin.
Input borders (`line-strong` on surface) are 1.6–1.9:1 in all three, like today's 1.7:1: the
field's shape is also given by its fill and focus ring; WCAG 1.4.11 (3:1) would need darker
borders (Codex: A `#94949e`, B `#a6926b`, C `#8797a4`), open point for the build (question 5).

## 5. The icons: Lucide

**Choice: Lucide** (`lucide-react`, v1.56.0, ISC; the Feather-derived part MIT). One React
component per icon, imported by name, so only the icons used land in the build (the mock-up's 64
icons and the patch add about 10 kB gzip: main.js 115 → 125 kB), no runtime, no font. Its 24-px, 2-px-stroke, round-cap style is
the closest open set to SF Symbols (regular weight); we draw at 1.75–2 px. Compared:
Phosphor (MIT, rounder, six weights; larger package, a little playful), Tabler (MIT, 5,000+
icons, slightly more technical), SF Symbols themselves (Apple licence: only on Apple platforms,
not for a web app). Docs/LICENSES.md row to add under *Not Python* when built:

`| Lucide (`lucide-react` 1.56.0) | ISC; MIT for Feather-derived icons | the studio's icons (Studio 2.0); keep the package's LICENSE notices |`

and, for directions A and C, `| Inter (`@fontsource-variable/inter`) | OFL-1.1 | the studio's typeface where SF is missing (Studio 2.0) |`.

The map (also on the comparison page with the glyphs; `apps/web/src/Ico.tsx` in the patch):

| where | item → icon |
|---|---|
| sections | Work → briefcase · Covers → layers · Shop → shopping-bag · Settings → settings |
| Work | Desk → inbox · Questions → message-circle-question · Workshop → scissors |
| Covers | All covers → layout-list · Arrangements → sofa · New cover → circle-plus · Learning → graduation-cap · Product list → file-spreadsheet |
| Shop | Orders → package · Requests → message-square-text · B2B customers → building-2 · Website (AI) → globe |
| Settings tabs | Company & shop → store · Selling → tag · Costs → coins · Price rules → badge-percent · Publish & versions → cloud-upload · Users & rights → users · Rules & defaults → sliders-horizontal · Mail & notifications → mail · Website & API keys → key-round · AI & spending → sparkles · System & logs → server |
| a cover's tabs | 3D → box · Pieces → puzzle · Seams → spline · Adjust → sliders-horizontal · Compare → columns-2 · History → history · Price & shop → euro |
| a Desk card's tabs | Check → list-checks · Pieces & revisions → layers · Correct → pencil-ruler · History → history |
| header (icon only) | Search → search · Guide → circle-help · Theme → sun-moon / sun / moon · Me → circle-user · Log out → log-out |
| actions | Run → play · Edit details → pencil-line · Desk card → inbox · Open cover → external-link · Approve / Save → check · Reject → x · Comment → message-square · Undo → undo-2 · More → ellipsis · Check list → clipboard-list · Cut pieces (SVG) → scissors · Cutting list → file-text · Size drawing / Measure → ruler · DXF → file-down · Table → table-2 · Cards → layout-grid · New → circle-plus · CSV → file-spreadsheet · PDF → file-text · AI spend → chart-column · explanation → info |
| statuses | approved → circle-check · waiting → clock · AI checked → sparkles · rejected → circle-x · warning / to check → triangle-alert / circle-alert · produced → package-check · draft → pencil-line |

Codex proposed 122 actions with an icon each (`out/studio2/icons-codex.json`, with file:line); I
kept most and changed: Work (briefcase stays), Desk inbox instead of Work, Workshop scissors (not
hammer: we sew), Questions message-circle-question (circle-help is the Guide), All covers
layout-list and Arrangements sofa (layout-grid is the Cards view), Requests message-square-text
(inbox is the Desk), Users users (not shield-check), Publish cloud-upload (not rocket), Pieces
puzzle (scissors is the Workshop), Seams spline, Price & shop euro (tag is Selling), Desk card
inbox everywhere.

## 6. What the mock-ups show (looked at, every one)

- **Now**: dark header, olive accents, the Desk's pipeline in olive/brown/rust, Workshop rows with
  five underlined links each, Settings rows with three columns of text.
- **A**: the Desk reads at once: blue "to review" tile, soft green / blue / red pipeline,
  icon-tabs on the card, Approve / Reject / Comment with icons, Undo and More as icons. Workshop:
  four tinted icon buttons and one blue DXF button per row instead of five links. Settings looks
  like iOS Settings (tiles, one-line rows, (i) beside the label). Dark: true black ground, grey
  cards, readable.
- **B**: the same layout, warmer; the sand line under the header and the sand "to review" tile
  keep the SUNS feel; green buttons. Dark: warm brown-black, green and sand stay legible.
- **C**: the sidebar gives the pages ~100 px more height; the cover page starts at the top.
  Settings shows two side columns next to each other (sections + settings tabs), which is the one
  awkward screen.
- Known mock-up shortcuts (fixed properly in the build): the not-converted helper paragraphs
  (`p.help`, `.set-intro`, …) are folded into an (i) by CSS only, which expands in place on hover;
  the Desk's queue filter "To do / 2nd round" wraps at 1440 (as today); the 3D canvas keeps its
  cream backdrop in all directions.

## 7. Step plan (after the two running agents have merged)

Each step its own commit, `make test` and the browser checks before the next; no release until
the owner has seen step 2 on the preview.

1. **Tokens first.** Replace the token block of `apps/web/src/studio.css` (light, dark by media
   and by `data-theme`, `.theme-light`) with the chosen direction's values from
   `out/studio2/tokens.json`; add `--wait`, `--made`, `--radius-lg`, `--radius-sm`; move the
   hard-coded colours left in studio.css (27 hex values after the token block: `.nav-count`,
   header hovers `rgba(255,255,255,…)`) onto tokens; the font (Inter via `@fontsource-variable/inter`
   for A/C). Shape rules: radii, shadows, pills, sentence-case table heads (the parts of
   `apps/web/src/studio2.css` in the patch that are not about icons). Run uinav (contrast of every text, light
   and dark, 1440 and 820) — it must stay green.
2. **Icons in the nav and toolbars.** Add `lucide-react`, `Ico.tsx` with the map of §5 (one
   place, as `nav.ts` is for the map), the icons in the header, sub-menu, cover tabs, Desk card
   tabs and Settings tabs (`icon` added to `Page` / `SETTINGS_TABS` / `MODEL_TABS` / `DESK_TABS`
   in `nav.ts`). Toolbar actions icon-only with `title` and `aria-label` equal to the old label,
   so uinav's and the other e2e scripts' `get_by_role(name=…)` keep working (check: "Log out",
   "Approve", "Reject", tab names). Status chips with an icon (`StatusChip`). LICENSES.md rows.
3. **Text reduction page by page**, from `out/studio2/audit.json` (every item with page, file,
   line and proposal): the `Info` popover component (click and keyboard, not hover only: the
   iPad has no hover), `PageHead`'s intro into it, then Desk + Desk card, Workshop, All covers, a
   cover's 7 tabs, Shop pages, Settings tabs. Settings: help into the label's (i), the key into
   the tooltip, the three-column row becomes two columns plus the source chip.
4. **The checks**: `uinav.py` light and dark at 1440 and 820 with its contrast check (every text
   ≥ 4.5:1); every e2e in `apps/web/e2e/` on a scratch copy (mail, public URL, shop domain,
   Mollie cleared; login code off): flow (make e2e), desk_pictures, prices, questions, measure,
   arrangements_desk, priceimport, b2b, bbq, stock_order, b2c, suggest_layout; the Desk at
   iPad width (820) for Rens; `uiaudit.py` before/after with word counts per page (the
   "words" column should drop by about half). Screenshots looked at, then the handbook's
   screenshots and docs/handbook/navigation.md updated.
5. **Release** by the owner's word only, as a minor version with an ADR (ADR-128 or the next
   free number): "Studio 2.0: tokens, Lucide icons, (i) instead of loose text".

Effort: step 1 half a day, step 2 half a day, step 3 one to two days (517 items), checks half a day.

## 8. Questions for the owner

1. **Which direction**: A (iOS light), B (fresh brand) or C (sidebar)? Or A's colours with C's
   sidebar?
2. **Accent colour** in A: iOS blue, or a fresh teal (`#0b7a70`, from C) so the studio is less
   "Apple" and closer to outdoor/green?
3. **The header**: light (as in all three proposals) or keep the dark bar from today?
4. **Explanations**: behind an (i) everywhere, or keep one short line on the Settings pages the
   workshop rarely visits?
5. **Input borders**: a little darker so every field meets the 3:1 rule for controls (slightly
   heavier look), or keep them light as now?
6. **Font**: the device's own (SF on Mac/iPad, Segoe on Windows) with Inter as fallback (A), or
   Work Sans everywhere as on the website (B)?
7. **Status colours**: waiting in blue (A) or amber (B)? Produced in purple (A) or blue (B)?

## 9. Files

- `out/studio2/index.html` — the comparison page (screenshots in `out/studio2/img/`, swatches,
  contrast, icons, the audit table); not in git (screenshots show drawings, the repository is public).
- `out/studio2/studio2-mockup.patch` — the throwaway patch (not for merging).
- `out/studio2/tokens.py`, `tokens.json`, `patch/studio2-tokens.css` — the three token sets and the check.
- `out/studio2/audit.json`, `audit-table.md`, `audit_fix.py` — the loose-text audit.
- `out/studio2/icons-codex.json`, `icons-svg.json`, `contrast-codex.md` — Codex's mapping and table, the glyphs.
- `out/studio2/scratch_setup.py`, `serve.sh`, `build.sh`, `shoot.py`, `shoot.sh`, `shoot_all.sh`,
  `make_page.py` — how to rebuild all of it.
- `~/cover-data/media/studio2-*.jpg` — the JPGs for https://preview.s2dio.living/media/.
