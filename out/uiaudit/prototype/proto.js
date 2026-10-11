// Cover Studio, proposed layout: a static, clickable prototype (docs/plans/studio-ui.md).
// Hash routes as the real app would have them; the old routes redirect (see REDIRECTS).
// Every value is an example; nothing is saved.
"use strict";

// ---------------------------------------------------------------- the information architecture
// Five sections, each with its own pages (the sub-menu). `roles`: who sees it.
const IA = [
  {
    id: "work", label: "Work", nl: "Werk", roles: ["admin", "approver", "editor", "workshop"],
    hint: "What waits for a person today",
    pages: [
      { id: "desk", label: "Desk", count: 7, hot: true, hint: "Approve or reject covers and arrangements" },
      { id: "questions", label: "Questions", count: 3, hot: true, hint: "The owner's and the workshop's questions" },
      { id: "workshop", label: "Workshop", count: 4, hint: "Check lists, measured on the sewn cover, fits" },
    ],
  },
  {
    id: "covers", label: "Covers", nl: "Hoezen", roles: ["admin", "approver", "editor", "workshop"],
    hint: "Every cover and model, new ones, arrangements",
    pages: [
      { id: "all", label: "All covers", hint: "Table or cards, one list (was Models + Catalogue)" },
      { id: "arrangements", label: "Arrangements", hint: "Furniture placed together, one cover" },
      { id: "new", label: "New cover", hint: "From a 3D file, a drawing (PDF) or a zip", roles: ["admin", "approver", "editor"] },
      { sep: true },
      { id: "learning", label: "Learning", hint: "Your covers against ours; lessons" },
      { id: "products", label: "Product list", hint: "The workshop's list linked to the drawings", roles: ["admin", "approver", "editor"] },
    ],
  },
  {
    id: "shop", label: "Shop", nl: "Winkel", roles: ["admin", "editor"],
    hint: "Orders, requests, matches, customers, the website",
    pages: [
      { id: "orders", label: "Orders", count: 2, hint: "Consumer and B2B orders" },
      { id: "requests", label: "Requests", hint: "Quotes asked in the configurator" },
      { id: "matches", label: "Matches", count: 1, hint: "Which existing cover fits; learning mode" },
      { id: "b2b", label: "B2B customers", hint: "Companies, logins, their orders", roles: ["admin"] },
      { sep: true },
      { id: "website", label: "Website (AI)", hint: "Change the website's text, preview, publish" },
      { id: "phototest", label: "Photo test", hint: "A photo suggestion step by step", roles: ["admin"] },
    ],
  },
  {
    id: "prices", label: "Prices", nl: "Prijzen", roles: ["admin", "editor"],
    hint: "Purchase prices, labour, price lists, costing",
    pages: [
      { id: "materials", label: "Materials" },
      { id: "labour", label: "Labour" },
      { id: "rate", label: "Exchange rate" },
      { id: "channels", label: "Channels & price lists" },
      { id: "import", label: "Import (Excel)", roles: ["admin"] },
      { sep: true },
      { id: "costing", label: "Costing" },
      { id: "versions", label: "Versions" },
    ],
  },
  {
    id: "settings", label: "Settings", nl: "Instellingen", roles: ["admin"],
    hint: "Everything that is set once: company, people, rules, mail, system",
    pages: [], // vertical tabs inside the page
  },
];

// Settings: one area, vertical tabs, a short explanation per tab and per setting.
const SETTINGS = [
  { grp: "Business" },
  { id: "company", label: "Company & shop", n: 14 },
  { id: "b2b", label: "B2B terms", n: 5 },
  { id: "matching", label: "Matching", n: 8 },
  { grp: "People & work" },
  { id: "users", label: "Users & rights", n: 6 },
  { id: "desk", label: "Desk & approval", n: 8 },
  { id: "defaults", label: "Cover defaults", n: 24 },
  { grp: "Connections" },
  { id: "mail", label: "Mail & notifications", n: 11 },
  { id: "website", label: "Website & API keys", n: 9 },
  { id: "ai", label: "AI & spending", n: 6 },
  { grp: "Server" },
  { id: "system", label: "System", n: 0 },
  { id: "activity", label: "Logins & audit log", n: 0 },
];

// Old links keep working (bookmarks, mails, the handbook): each redirects to its new place.
const REDIRECTS = [
  [/^#\/?$/, () => (role === "admin" || role === "editor" ? "#/covers/all" : "#/work/desk")],
  [/^#\/desk\/(.+)$/, (m) => `#/work/desk/${m[1]}`],
  [/^#\/desk$/, () => "#/work/desk"],
  [/^#\/questions(\/.*)?$/, (m) => `#/work/questions${m[1] ?? ""}`],
  [/^#\/catalogue$/, () => "#/covers/all?view=cards"],
  [/^#\/arrangements(\/.*)?$/, (m) => `#/covers/arrangements${m[1] ?? ""}`],
  [/^#\/learning$/, () => "#/covers/learning"],
  [/^#\/website$/, () => "#/shop/website"],
  [/^#\/prices$/, () => "#/prices/materials"],
  [/^#\/admin$/, () => "#/settings/users"],
  [/^#\/model\/([a-z0-9-]+)$/, (m) => `#/model/${m[1]}/3d`],
];

// ---------------------------------------------------------------- example data
const DESK = [
  { id: "drawing-c27", code: "C27", st: "rejected", g: 62, d: 70, pcs: 20, vents: 10, prod: "Pico corner left", round: "2nd round", why: "AIs disagree" },
  { id: "drawing-s45", code: "S45", st: "rejected", g: 100, d: 100, pcs: 3, vents: 4, prod: "Blocchi hocker" },
  { id: "arr-portofino-2-c", code: "portofino 2 + c", st: "ready", arr: true, pcs: 9, vents: 10, by: "Claude", round: "2nd round" },
  { id: "drawing-c2", code: "C2", st: "ai", g: 88, d: 92, pcs: 14, vents: 8, prod: "Lounge set Ibiza" },
  { id: "drawing-s40", code: "S40", st: "new", g: null, d: null, pcs: 6, vents: 4, prod: "Daybed Portofino" },
  { id: "drawing-c1", code: "C1", st: "ai", g: 91, d: 95, pcs: 14, vents: 8, prod: "Corner sofa Lucia" },
  { id: "suns-chaise-lounge-portofino", code: "SUNS Chaise lounge Portofino", st: "ai", g: 80, d: 84, pcs: 8, vents: 6 },
  { id: "drawing-c10", code: "C10", st: "approved", g: 95, d: 96, pcs: 11, vents: 7, prod: "Corner sofa Fiora" },
  { id: "drawing-s21", code: "S21", st: "produced", g: 90, d: 92, pcs: 5, vents: 4, prod: "Hocker Moon" },
];
const ST = {
  rejected: ["Rejected", "bad"], ready: ["Ready for approval", "warn"], ai: ["AI checked", "info"],
  new: ["New", ""], approved: ["Approved", "ok"], produced: ["Produced", "ok"],
};
const COVERS = [
  ["drawing-c1", "C1 · Corner sofa Lucia", "ready", "checked", "Sofa sets", "268 × 268 × 85", 14, "0.7 %", 1],
  ["drawing-c2", "C2 · Lounge set Ibiza", "ready", "checked", "Sofa sets", "344 × 268 × 90", 14, "0.8 %", 1],
  ["drawing-c27", "C27 · Pico corner left", "ready", "draft", "", "445 × 367 × 86", 20, "0.6 %", 3],
  ["drawing-s40", "S40 · Daybed Portofino", "ready", "checked", "Loungers", "92 × 105 × 86", 6, "0.0 %", 1],
  ["drawing-s45", "S45 · Blocchi hocker", "ready", "draft", "", "124 × 99 × 45", 3, "0.0 %", 1],
  ["suns-2-seater-kota", "SUNS 2-seater Kota", "ready", "checked", "Sofa sets", "180 × 115 × 88", 7, "0.0 %", 0],
  ["suns-2-seater-portofino", "SUNS 2-seater Portofino", "check", "draft", "Sofa sets", "213 × 107 × 85", 7, "0.0 %", 1],
  ["suns-chaise-lounge-portofino", "SUNS Chaise lounge Portofino", "ready", "draft", "Sofa sets", "133 × 202 × 85", 8, "0.0 %", 0],
  ["suns-dining-table-palermo-240", "SUNS Dining table Palermo 240", "ready", "checked", "Tables", "240 × 114 × 76", 8, "0.0 %", 0],
  ["arr-portofino-2-c", "Arrangement · portofino 2 + c", "ready", "draft", "", "346 × 202 × 85", 9, "0.0 %", 0],
];

// ---------------------------------------------------------------- helpers
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const chip = (txt, cls = "") => `<span class="chip ${cls}">${txt}</span>`;
const note = (html) => `<p class="proto-note">${html}</p>`;
let role = "admin";
try { role = localStorage.getItem("proto-role") || "admin"; } catch { /* a private window */ }
const can = (roles) => !roles || roles.includes(role);
const approver = () => role === "admin" || role === "approver";

function route() {
  let h = location.hash || "#/";
  for (const [re, to] of REDIRECTS) {
    const m = h.match(re);
    if (m) {
      const next = to(m);
      if (next !== h) { history.replaceState(null, "", next); h = next; }
      break;
    }
  }
  const [path, query] = h.slice(2).split("?");
  const parts = path.split("/").filter(Boolean);
  const q = Object.fromEntries(new URLSearchParams(query ?? ""));
  return { parts, q };
}

function renderNav(section, page) {
  $("#sections").innerHTML = IA.filter((s) => can(s.roles))
    .map((s) => {
      const first = s.id === "settings" ? "settings/company" : `${s.id}/${s.pages.find((p) => p.id && can(p.roles)).id}`;
      const total = s.pages.filter((p) => p.hot).reduce((a, p) => a + p.count, 0);
      const menu = s.pages.filter((p) => p.id && can(p.roles))
        .map((p) => `<span data-go="#/${s.id}/${p.id}">${p.label}<small>${p.hint ?? ""}</small></span>`).join("");
      const smenu = s.id === "settings"
        ? SETTINGS.filter((t) => t.id).map((t) => `<span data-go="#/settings/${t.id}">${t.label}</span>`).join("")
        : menu;
      return `<a href="#/${first}" class="${s.id === section ? "on" : ""}" title="${s.hint} (${s.nl})">
        <span class="lbl">${s.label}</span>${total ? `<span class="count hot">${total}</span>` : ""}
        <span class="menu">${smenu}</span></a>`;
    }).join("");
  const s = IA.find((x) => x.id === section);
  const sub = $("#subnav");
  if (!s || !s.pages.length) { sub.classList.add("hide"); return; }
  sub.classList.remove("hide");
  sub.innerHTML = s.pages.filter((p) => p.sep || can(p.roles))
    .map((p) => p.sep ? `<span class="sep"></span>`
      : `<a href="#/${s.id}/${p.id}" class="${p.id === page ? "on" : ""}" title="${p.hint ?? ""}">${p.label}${p.count ? `<span class="count ${p.hot ? "hot" : ""}">${p.count}</span>` : ""}</a>`)
    .join("");
}

// ---------------------------------------------------------------- Work → Desk (list + card)
function deskList(sel) {
  return `<aside class="panel list-col">
    <div class="filters">
      <input class="field" placeholder="Search code, product, model or tag  ( / )" />
      <div class="seg"><button class="on">To do 7</button><button>2nd round 2</button><button>Approved</button><button>Produced</button><button>All</button></div>
      <div style="display:flex;gap:6px;align-items:center">
        <select class="field" style="flex:1"><option>Every series</option><option>C</option><option>S</option><option>D</option><option>L</option><option>R</option><option>T</option><option>U</option><option>SUNS</option><option>ARR · arrangements (1)</option></select>
        <select class="field" style="flex:1"><option>Needs a person first</option><option>Code</option><option>Product</option><option>AI score</option></select>
      </div>
    </div>
    <ul>${DESK.map((i) => `<li class="${i.id === sel ? "sel" : ""}" data-go="#/work/desk/${i.id}">
      <span class="thumb"></span>
      <span class="t"><span style="display:flex;gap:6px;align-items:center;justify-content:space-between"><b>${esc(i.code)}</b>${chip(ST[i.st][0], ST[i.st][1])}</span>
      <span class="sub">${i.arr ? chip("ARR", "sand") + `<span>sent by ${i.by}</span>` : `<span>G ${i.g ?? "–"} · D ${i.d ?? "–"}</span>`}<span>${i.pcs} pcs</span><span>${i.vents} vents</span>${i.round ? chip(i.round, "warn") : ""}</span>
      ${i.prod ? `<span class="sub">${esc(i.prod)}</span>` : ""}</span></li>`).join("")}</ul>
  </aside>`;
}

function deskCard(id, tab) {
  const i = DESK.find((x) => x.id === id) ?? DESK[0];
  const t = (k, l, n) => `<a href="#/work/desk/${i.id}/${k}" class="${tab === k ? "on" : ""}">${l}${n ? `<span class="count">${n}</span>` : ""}</a>`;
  let body = "";
  if (tab === "check") {
    body = `<div class="split">
      <div class="figure"><span class="caption label">${i.arr ? "The arrangement from above" : "The drawing · page 1 of 2"}</span><div class="drawing"></div></div>
      <div class="viewer">${viewerBar(true)}<div class="figure"><div class="stage"><div class="sofa"></div>${vents()}</div></div></div>
    </div>
    <div class="grid3" style="padding:12px 14px">
      ${i.arr ? `<section><h4 class="label" style="margin-bottom:8px">The arrangement</h4><ul class="facts">
        <li><i class="dot"></i><span>1 · 2-seater Portofino</span>213 × 107 cm · at 0, 48 · <a href="#/model/suns-2-seater-portofino/3d">model</a></li>
        <li><i class="dot"></i><span>2 · Chaise Portofino</span>133 × 202 cm · at 167, 0 · <a href="#/model/suns-chaise-lounge-portofino/3d">model</a></li>
        <li><i class="dot ok"></i><span>Pieces</span>as when it was built</li>
        <li><i class="dot bad"></i><span>Cutting-table DXF</span>locked until approved</li></ul></section>` : `<section><h4 class="label" style="margin-bottom:8px">What the program read</h4><ul class="facts">
        <li><i class="dot ok"></i><span>Air vents</span>drawing 10 · cover 10</li>
        <li><i class="dot ok"></i><span>Open at the bottom</span>as drawn</li>
        <li><i class="dot"></i><span>Pieces</span>${i.pcs} pieces + vents</li>
        <li><i class="dot bad"></i><span>Cutting-table DXF</span>locked until approved</li></ul></section>`}
      ${i.arr ? `<section><h4 class="label" style="margin-bottom:8px">Cover plan</h4><div class="seg"><button class="on">Follow</button><button>Box</button><button>Smoothed</button></div><p class="small muted" style="margin-top:6px">Chosen on the Arrangements page; a change sends it back here.</p></section>` : `<section><h4 class="label" style="margin-bottom:8px">What the AIs say</h4>
        <p class="small"><b>Gemini · looks right.</b> Built from the exact top view and back profile; the drawing says 235.1 cm for one outer length but 96.5 in (245.1 cm)…</p>
        <button class="btn sm ghost" style="margin-top:6px">Read all</button></section>`}
      <section><h4 class="label" style="margin-bottom:8px">Products</h4>
        <p class="small">Pico · corner left <span class="muted">(Cover 83, C27)</span></p><p class="small" style="margin-top:6px">${chip("lounge pico corner")} <span class="muted">SUNS model, linked by code</span></p></section>
    </div>`;
  } else if (tab === "pieces") {
    body = `<div class="grid2" style="padding:12px 14px"><table class="list"><thead><tr><th>Piece</th><th class="num">Qty</th><th class="num">Size (cm)</th></tr></thead><tbody>
      ${["top-1 139 × 105", "top-3 169 × 110", "top-5 202 × 115", "skirt-right-2 127 × 48", "skirt-back 171 × 96", "vent-hood 28 × 32"].map((r) => { const [a, ...b] = r.split(" "); return `<tr><td>${a}</td><td class="num">${a.startsWith("vent") ? 10 : 1}</td><td class="num">${b.join(" ")}</td></tr>`; }).join("")}
      </tbody></table>
      <div><h4 class="label" style="margin-bottom:8px">Revisions</h4><ul class="facts">
      <li><i class="dot ok"></i><span>r11 · 9 Oct 07:41</span>20 pieces · <a href="#">cut file</a></li>
      <li><i class="dot"></i><span>r10 · 7 Oct 18:16</span>20 pieces · <a href="#">cut file</a></li>
      <li><i class="dot"></i><span>r9 · 7 Oct 15:05</span>25 pieces · <a href="#">cut file</a></li></ul>
      <button class="btn sm ghost">All 11 revisions</button></div></div>`;
  } else if (tab === "correct") {
    body = `<div style="padding:12px 14px" class="stack">
      <p class="muted small">A correction changes the cover itself: saved on the cover, calculated again at once, and kept as a test. Five times the same correction in one series becomes a proposed rule.</p>
      <div class="seg" style="width:max-content"><button class="on">Seams 37</button><button>Vents 10</button><button>Sizes</button><button>Shape</button></div>
      <div style="display:flex;gap:6px;flex-wrap:wrap"><input class="field" placeholder="Filter seams: piece name…" style="width:240px"/><select class="field"><option>All kinds</option><option>Corner</option><option>Skirt</option><option>Top</option></select></div>
      <table class="list"><thead><tr><th>Kind</th><th>Seam</th><th class="num">Length</th><th></th></tr></thead><tbody>
      ${[["corner", "skirt-right-2 ↔ skirt-left-1", 40], ["corner", "skirt-right-2 ↔ skirt-right-3", 38], ["skirt", "top-1 ↔ skirt-right-2", 108], ["top", "top-1 ↔ top-3", 135], ["top", "top-1 ↔ top-2", 12]].map(([k, s, l]) => `<tr><td>${chip(k)}</td><td>${s}</td><td class="num">${l} cm</td><td class="num"><button class="btn sm ghost">Remove seam</button></td></tr>`).join("")}
      </tbody></table><p class="muted small">5 of 37 shown · the list scrolls inside this tab; the card no longer grows by 3,000 px.</p>
      <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center"><span class="label">Add a seam to</span><select class="field"><option>top-1</option></select><select class="field"><option>at a height above the hem</option></select><input class="field" placeholder="cm" style="width:70px"/><button class="btn">Add seam</button></div>
    </div>`;
  } else {
    body = `<div style="padding:12px 14px"><ul class="timeline">
      <li><i class="dot bad"></i><div><b>Rejected</b> by Rens · 9 Oct 09:43 · <span class="muted">vents</span><div class="note">“vents verdelen zoals eerder aangegeven op tekening”</div></div></li>
      <li><i class="dot"></i><div><b>Reopened</b> by Claude · 9 Oct 08:41<div class="note">Vents now also on the front walls in the inner corner (decision 9 Oct, as Rens marked).</div></div></li>
      <li><i class="dot"></i><div><b>Comment</b> by Claude · 8 Oct 21:35 · 3 pictures <span style="display:inline-flex;gap:4px;vertical-align:middle"><span class="thumb"></span><span class="thumb"></span><span class="thumb"></span></span></div></li>
      <li><i class="dot"></i><div><b>Drawing uploaded</b> by Rick · 5 Oct 05:27</div></li></ul></div>`;
  }
  const acts = approver()
    ? `<button class="btn ok">✓ Approve <kbd>a</kbd></button><button class="btn danger" data-act="reject">✕ Reject <kbd>r</kbd></button><button class="btn">Comment <kbd>c</kbd></button>
       <span class="grow"></span>
       <span class="dd"><button class="btn ghost" data-dd>After sewing</button><span class="drop">
         <button class="item">Mark produced <small>p</small></button><button class="item">Fits…</button><button class="item">Does not fit…</button><button class="item">Measured on the sewn cover… <small>check list</small></button></span></span>
       <button class="btn ghost">Undo <kbd>u</kbd></button>`
    : `<span class="muted small">Only Rens, Rick, Wout or an admin decide here. You can comment.</span><span class="grow"></span><button class="btn">Comment <kbd>c</kbd></button>`;
  return `<section class="panel detail">
    <div class="detail-head">
      <a class="btn sm ghost back-to-list" href="#/work/desk">← List</a>
      <div class="grow"><h2>${esc(i.code)}</h2><div class="muted small">${i.id}${i.prod ? " · " + esc(i.prod) : ""}</div></div>
      ${i.why ? chip(i.why, "warn") : ""}${i.arr ? chip("ARR", "sand") : `<span class="small muted">G ${i.g ?? "–"} · D ${i.d ?? "–"}</span>`}${chip(ST[i.st][0], ST[i.st][1])}
      <a class="btn sm" href="#/model/${i.id}/3d">Open cover ↗</a>
      <span class="dd"><button class="btn sm ghost" data-dd>More</button><span class="drop" style="left:auto;right:0">
        <button class="item">Let the AI read the drawing <small>≈ 1–5 ct</small></button>
        <button class="item">Check list (PDF)</button>${i.arr ? `<button class="item">Edit the arrangement ↗</button>` : ""}<button class="item">Copy link</button></span></span>
    </div>
    ${i.round ? `<p class="note" style="margin:10px 14px 0"><b>2nd round ·</b> ${i.arr ? "changed after approval: the cover plan is now “follow”; approve again." : "in the pieces the drawing draws (25 → 20): no seam across the middle of the top; the back wall in long runs."}</p>` : ""}
    <nav class="tabs">${t("check", "Check")}${t("pieces", "Pieces & revisions", i.pcs)}${t("correct", "Correct this cover")}${t("history", "History", 6)}</nav>
    ${body}
    <div class="actionbar">${acts}</div>
  </section>`;
}

function vents() {
  return [22, 38, 54, 70].map((l) => `<span class="vent" style="left:${l}%"></span>`).join("");
}

// The 3D viewer's toolbar: 15 controls in a row before, 5 now (menus hold the rest).
function viewerBar(compact) {
  return `<div class="vbar">
    <span class="dd"><button class="btn sm" data-dd>Show</button><span class="drop">
      <div class="grp label">Layers</div>
      <label><input type="checkbox" /> Furniture</label>
      <label><input type="checkbox" /> Cover surface <small>water spots red</small></label>
      <label><input type="checkbox" checked /> Panels</label>
      <label><input type="checkbox" disabled /> Balloons <small>tables only</small></label>
      <label><input type="checkbox" disabled /> Chair space <small>tables only</small></label>
      <hr /><div class="grp label">On the cover</div>
      <label><input type="checkbox" checked /> Air vents</label>
      <label><input type="checkbox" /> Vent sizes <small>opening, heights, to the seams</small></label>
      <label><input type="checkbox" /> Overall dimensions</label>
      <hr /><div class="grp muted small">Drag to turn · scroll to zoom · right-drag to move</div>
    </span></span>
    <div class="seg" title="Which cover you look at"><button class="on">Design</button><button>Rain</button><button>Drape</button>${compact ? "" : "<button>Unfold</button>"}</div>
    <button class="btn sm" title="Click two points on the cover: straight, height and along the fabric, in cm">Measure</button>
    <span class="grow"></span>
    ${compact ? "" : `<span class="dd"><button class="btn sm ghost" data-dd>Simulate</button><span class="drop" style="left:auto;right:0">
      <button class="item">Rain again <small>≈ 1 min</small></button>
      <button class="item">Drape again <small>≈ 40 min, in its own queue</small></button>
      <hr /><label><input type="checkbox" /> Water on the drape</label></span></span>`}
    <a class="btn sm ghost" href="#" title="One sheet for the workshop">Check list (PDF)</a>
  </div>`;
}

function pageDesk(parts) {
  const sel = parts[2] ?? (innerWidth > 1100 ? DESK[0].id : null);
  const tab = parts[3] ?? "check";
  return `${note("<b>Desk</b>: the queue on the left; the card in four tabs (it was one 4,500 px column). The decision bar stays at the bottom of the screen while the card scrolls. Product list upload and AI spend moved out (Covers → Product list, Settings → AI). Keys unchanged: j k a r c p u.")}
  <div class="page-head"><div class="grow"><h1>Desk</h1><p>The AI sorts, people approve.</p></div>
    <div class="kpis"><div class="kpi accent"><b>3</b><span>To review</span></div><div class="kpi"><b>5</b><span>Approved</span></div><div class="kpi"><b>0</b><span>Produced</span></div><div class="kpi"><b>3</b><span>Rejected</span></div></div></div>
  <div class="note" style="margin-bottom:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">Proposed rule: <b>vent height above the hem = 120</b> — corrected the same way on 5 covers of series S. <button class="btn sm">Make it the rule</button><button class="btn sm ghost">Not now</button></div>
  <div class="ld ${sel ? "has-sel" : ""}">${deskList(sel)}${sel ? deskCard(sel, tab) : `<section class="panel detail" style="padding:40px;text-align:center" class="muted">Pick a cover from the list.</section>`}</div>`;
}

// ---------------------------------------------------------------- Work → Questions, Workshop
function pageQuestions(parts) {
  const sel = parts[2] ?? "71";
  const qs = [["71", "Vents op de voorwanden in de binnenhoek?", "vents", "answered"], ["72", "Hoe hoog is de rugstrook bij loungers?", "shape", "open"], ["73", "Prijs balloon: los of in de hoes?", "prices", "open"], ["74", "Levertijd in de webshop: 3 weken?", "webshop", "open"]];
  return `${note("<b>Questions</b> keeps its place next to the Desk (Work → Questions), with the same list + detail template as the Desk.")}
  <div class="page-head"><div class="grow"><h1>Questions</h1><p>For the owner and the workshop. Claude processes the answers every day at 18:00.</p></div>
  <div class="kpis"><div class="kpi accent"><b>3</b><span>Open</span></div><div class="kpi"><b>2</b><span>Waiting for you</span></div><div class="kpi"><b>12</b><span>Processed</span></div></div></div>
  <div class="ld has-sel"><aside class="panel list-col"><div class="filters"><input class="field" placeholder="Search questions or covers  ( / )"/><div class="seg"><button class="on">Open</button><button>Answered</button><button>Processed</button><button>All</button></div></div>
  <ul>${qs.map(([n, t, tp, s]) => `<li class="${n === sel ? "sel" : ""}" data-go="#/work/questions/${n}"><span class="t"><b>${n}. ${t}</b><span class="sub">${chip(tp)}${s === "open" ? chip("waiting for you", "bad") : chip("answered", "ok")}</span></span></li>`).join("")}</ul></aside>
  <section class="panel detail"><div class="detail-head"><a class="btn sm ghost back-to-list" href="#/work/questions">← List</a><div class="grow"><h2 lang="nl">${qs.find((q) => q[0] === sel)?.[1] ?? ""}</h2><div class="muted small">vents · asked by Claude, 9 Oct</div></div></div>
  <div style="padding:12px 14px" class="stack"><p lang="nl">Rens markeerde op 8 okt vents op de voorwanden in de binnenhoek van L-, U- en C-hoezen. Wil je dat voor alle hoezen?</p>
  <div style="display:flex;gap:6px;flex-wrap:wrap">${chip("C27")}${chip("C2")}${chip("C10")}</div>
  <div class="stack" style="gap:6px">${["Ja, op alle L/U/C-hoezen", "Alleen als de tekening ze toont", "Nee"].map((o, k) => `<label style="display:flex;gap:8px;align-items:center"><input type="radio" name="o"/> ${o} <kbd>${k + 1}</kbd></label>`).join("")}</div>
  <textarea class="field" style="height:70px;padding:8px" placeholder="Comment (optional)"></textarea></div>
  <div class="actionbar"><button class="btn">Pictures…</button><span class="grow"></span><button class="btn primary">Send answer <kbd>Ctrl</kbd><kbd>Enter</kbd></button></div></section></div>`;
}

function pageWorkshop() {
  const rows = [["C10", "Corner sofa Fiora", "approved", "r7", "—"], ["S21", "Hocker Moon", "produced", "r4", "fits · 2 sizes measured"], ["C1", "Corner sofa Lucia", "approved", "r9", "—"], ["SUNS 2-seater Kota", "", "approved", "r12", "—"]];
  return `${note("<b>Workshop</b> (new, built from what exists): the covers that may be cut, with the DXF, the cutting list and the check list, and where the measured sizes and the fit are entered. Today these sit in the Desk's action bar and in the 3D view's toolbar.")}
  <div class="page-head"><div class="grow"><h1>Workshop</h1><p>Approved covers: cut, sew, measure against the check list, report the fit.</p></div><div class="seg"><button class="on">To cut 3</button><button>To measure 1</button><button>Done</button></div></div>
  <section class="panel"><table class="list"><thead><tr><th></th><th>Cover</th><th>Status</th><th>Revision</th><th>Files</th><th>Fit</th><th></th></tr></thead><tbody>
  ${rows.map(([c, p, s, r, f]) => `<tr><td><span class="thumb"></span></td><td><b>${c}</b> <span class="muted">${p}</span></td><td>${chip(s === "produced" ? "Produced" : "Approved", "ok")}</td><td>${r}</td>
  <td><a class="btn sm ghost" href="#">DXF</a><a class="btn sm ghost" href="#">Cutting list</a><a class="btn sm ghost" href="#">Check list</a></td><td class="small">${f}</td>
  <td class="num">${s === "produced" ? `<button class="btn sm">Measured…</button>` : `<button class="btn sm">Mark produced</button>`}</td></tr>`).join("")}</tbody></table></section>`;
}

// ---------------------------------------------------------------- Covers
function pageCovers(q) {
  const cards = q.view === "cards";
  const head = `${note("<b>All covers</b> is one list: the old <i>Models</i> table and the <i>Catalogue</i> cards are two views of it (the toggle). Uploads moved to <b>New cover</b>; the filter bar is one row for both views.")}
  <div class="page-head"><div class="grow"><h1>Covers</h1><p>10 covers · 9 ready · 1 to check · 0 failed</p></div>
  ${can(["admin", "approver", "editor"]) ? `<a class="btn primary" href="#/covers/new">+ New cover</a>` : ""}</div>
  <section class="panel"><div class="toolbar"><input class="field" placeholder="Search name, code, product, tag or note" style="width:280px"/>
  <select class="field"><option>All categories</option><option>Sofa sets</option><option>Loungers</option><option>Tables</option></select>
  <select class="field"><option>Any cover</option><option>Ready</option><option>To check</option><option>Failed</option></select>
  <select class="field"><option>Any status</option><option>Draft</option><option>Checked</option><option>Production</option></select>
  <select class="field"><option>All sources</option><option>Drawing (C, S, D …)</option><option>SUNS</option><option>Arrangement</option></select>
  <span class="grow"></span><div class="seg"><button class="${cards ? "" : "on"}" data-go="#/covers/all">Table</button><button class="${cards ? "on" : ""}" data-go="#/covers/all?view=cards">Cards</button></div></div>`;
  if (cards)
    return `${head}<div class="cards" style="padding:12px">${COVERS.map((c) => `<a class="card" href="#/model/${c[0]}/3d"><div class="pics"><div class="sofa" style="left:20%;right:20%"></div></div><div class="t"><b>${c[1]}</b><div style="display:flex;gap:4px;flex-wrap:wrap">${chip(c[2] === "ready" ? "ready" : "to check", c[2] === "ready" ? "ok" : "warn")}${c[4] ? chip(c[4]) : ""}</div><span class="small muted">${c[5]} cm · ${c[6]} pieces · ${c[7]}</span></div></a>`).join("")}</div></section>`;
  return `${head}<table class="list"><thead><tr><th><input type="checkbox"/></th><th>Cover</th><th>Cover check</th><th>Status</th><th>Category</th><th class="num">Size (cm)</th><th class="num">Pieces</th><th class="num">Worst stretch</th><th class="num">Warnings</th></tr></thead><tbody>
  ${COVERS.map((c) => `<tr class="click" data-go="#/model/${c[0]}/3d"><td><input type="checkbox"/></td><td><span style="display:flex;gap:8px;align-items:center"><span class="thumb"></span><span><b>${c[1]}</b><br/><span class="muted small">${c[0]}</span></span></span></td><td>${chip(c[2] === "ready" ? "ready" : "to check", c[2] === "ready" ? "ok" : "warn")}</td><td>${chip(c[3], c[3] === "checked" ? "info" : "")}</td><td>${c[4]}</td><td class="num">${c[5]}</td><td class="num">${c[6]}</td><td class="num">${c[7]}</td><td class="num">${c[8] || ""}</td></tr>`).join("")}
  </tbody></table><div class="toolbar" style="border-top:1px solid var(--line);border-bottom:0"><span class="muted small">Select rows to run them again, set a status or a tag together.</span></div></section>`;
}

function pageNew() {
  return `${note("<b>New cover</b>: the three ways in, side by side. Before: two upload cards above the Models list, a zip on Learning, the product list on the Desk.")}
  <div class="page-head"><div class="grow"><h1>New cover</h1><p>Everything then runs by itself; a big model takes a few minutes.</p></div></div>
  <div class="choices">
    <div class="choice"><span class="ico">3D</span><h3>From a 3D file</h3><p class="muted small">STEP, IGES, STL, OBJ, PLY or GLB: the complete product, or only the cover surface. You confirm which after the import.</p><div class="drop-zone">Drop a file or <u>choose</u></div>
      <details><summary class="small muted">Units and up axis (only when the file does not say)</summary><div style="display:flex;gap:6px;margin-top:6px"><select class="field"><option>Units from the file</option><option>mm</option><option>cm</option><option>m</option><option>in</option></select><select class="field"><option>Up: automatic</option><option>z</option><option>y</option></select></div></details>
      <button class="btn primary">Upload and run</button></div>
    <div class="choice"><span class="ico">PDF</span><h3>From a drawing</h3><p class="muted small">The program reads the views, the sizes and the vents and builds the cover. When it is not sure it builds nothing and the drawing waits at the Desk.</p><div class="drop-zone">Drop a PDF or <u>choose</u></div><button class="btn primary">Upload drawing</button></div>
    <div class="choice"><span class="ico">ZIP</span><h3>Many at once</h3><p class="muted small">A zip of drawings with their 3D models (1.step + 1.pdf …) to compare, or the workshop's product list (Excel). Each pair is calculated and shown next to your drawing.</p><div class="drop-zone">Drop a zip or <u>choose</u></div><button class="btn primary">Upload zip</button></div>
  </div>`;
}

function pageSimple(title, sub, html, n) {
  return `${n ? note(n) : ""}<div class="page-head"><div class="grow"><h1>${title}</h1><p>${sub}</p></div></div>${html}`;
}

// ---------------------------------------------------------------- the model page
const MTABS = [["3d", "3D"], ["pieces", "Pieces"], ["seams", "Seams"], ["adjust", "Adjust"], ["compare", "Compare"], ["history", "History"], ["files", "Files"]];
function pageModel(parts) {
  const id = parts[1];
  const tab = parts[2] ?? "3d";
  const c = COVERS.find((x) => x[0] === id) ?? COVERS[5];
  const desk = DESK.find((x) => x.id === id);
  const locked = id.startsWith("drawing-") && (!desk || !["approved", "produced"].includes(desk.st));
  let body = "";
  if (tab === "3d") {
    body = `<div class="viewer">${viewerBar(false)}<div style="height:min(62vh,560px)"><div class="stage"><div class="sofa"></div>${vents()}<div class="readout"><b>Measure</b> · click two points<br/><span class="muted">straight 214.0 cm · along the fabric 218.6 cm</span></div><div class="legend">Panels in colour · vents shown</div></div></div></div>`;
  } else if (tab === "pieces") {
    body = `<div class="toolbar"><div class="seg"><button class="on">Cut pieces</button><button>Flat patterns</button><button>Stretch</button><button>Size drawing (PDF)</button></div><span class="grow"></span>
      ${locked ? `<span class="chip warn" title="Approve at the Desk first">🔒 DXF after approval</span>` : `<a class="btn sm primary" href="#">Download DXF</a>`}<a class="btn sm ghost" href="#">Cutting list</a><a class="btn sm ghost" href="#">Check list</a></div>
      <div class="grid2" style="padding:12px 14px"><div class="figure" style="aspect-ratio:16/10;background:var(--stone);border-radius:var(--r-s)"><div class="drawing" style="width:70%;height:60%"></div></div>
      <table class="list"><thead><tr><th>Piece</th><th class="num">Qty</th><th class="num">Size</th><th class="num">Area</th><th class="num">Stretch</th></tr></thead><tbody>
      ${["P1 top 139 × 105 1.46 0.4", "P2 back 169 × 110 1.86 0.7", "P3 skirt-front 202 × 48 0.97 0.2", "P4 skirt-left 127 × 48 0.61 0.1", "P5 vent-hood 28 × 32 0.09 –"].map((r) => { const a = r.split(" "); return `<tr><td>${a[0]} ${a[1]}</td><td class="num">${a[1].startsWith("vent") ? 4 : 1}</td><td class="num">${a[2]} × ${a[4]} cm</td><td class="num">${a[5]} m²</td><td class="num">${a[6]} %</td></tr>`; }).join("")}
      </tbody></table></div>`;
  } else if (tab === "adjust") {
    body = `<div class="toolbar"><input class="field" placeholder="Search settings…" style="width:240px"/><label class="small"><input type="checkbox"/> Only this cover's own values</label><span class="grow"></span><button class="btn" disabled>Try without saving</button><button class="btn primary" disabled>Save for this cover</button></div>
      <div class="setrow"><div class="name"><b>Vents per metre</b><code>features.vents_per_metre</code></div><div class="ctl"><input class="field" value="1"/></div><div class="help">One vent per full metre of each side, spread evenly.<div class="src">${chip("company default", "")}</div></div></div>
      <div class="setrow"><div class="name"><b>Vents in total</b><code>features.vents_total</code></div><div class="ctl"><input class="field" value="10"/><button class="btn sm ghost">Use default</button></div><div class="help">The number written on the drawing; always wins over the rule. 0 = the rule.<div class="src">${chip("this cover", "sand")}</div></div></div>
      <div class="setrow"><div class="name"><b>Skirt seam</b><code>seams.skirt_seam</code></div><div class="ctl"><select class="field"><option>level</option><option>follow</option></select></div><div class="help">At one height all round, so skirt pieces are straight strips.<div class="src">${chip("company default")}</div></div></div>
      <details class="adv"><summary>Advanced: 112 more (cover surface, flattening, export, drape …)</summary></details>`;
  } else if (tab === "compare") {
    body = `<div class="toolbar"><div class="seg"><button class="on">Your drawing</button><button>Your reference</button><button>AI advice</button></div><span class="grow"></span><button class="btn sm">Upload a reference…</button></div>
      <div class="grid2" style="padding:12px 14px"><div class="figure" style="background:var(--stone);border-radius:var(--r-s)"><span class="caption label">Your drawing</span><div class="drawing"></div></div>
      <div class="stack"><h4 class="label">Sizes in your drawing against ours</h4><ul class="facts"><li><i class="dot ok"></i><span>Length</span>268 cm · ours 268.4</li><li><i class="dot ok"></i><span>Depth</span>268 cm · ours 267.9</li><li><i class="dot warn"></i><span>Back height</span>85 cm · ours 83.6</li></ul>
      <div class="note"><b>Verdict:</b> agrees with the program's cover (96 % within ±5 mm).</div></div></div>`;
  } else if (tab === "history") {
    body = `<div class="grid2" style="padding:12px 14px"><div><h4 class="label" style="margin-bottom:8px">Approval &amp; Desk</h4><ul class="timeline">
      <li><i class="dot ok"></i><div><b>Approved</b> by Rens · revision 9 · 8 Oct<div class="small"><a href="#">Approved size drawing</a> · <a href="#">Approved cutting list</a></div></div></li>
      <li><i class="dot bad"></i><div><b>Rejected</b> by Rens · vents · 7 Oct</div></li></ul>
      <h4 class="label" style="margin:14px 0 8px">Since the run before</h4><p class="small">${chip("features.vents_total: 8 → 10")} ${chip("skirt-front: 202×46 → 202×48 mm")}</p></div>
      <div><h4 class="label" style="margin-bottom:8px">Revisions</h4><ul class="facts"><li><i class="dot ok"></i><span>r9 · 8 Oct</span>14 pieces · approved</li><li><i class="dot"></i><span>r8 · 7 Oct</span>14 pieces</li></ul>
      <h4 class="label" style="margin:14px 0 8px">Warnings &amp; run log <span class="count" style="background:var(--warn-soft);color:var(--warn)">1</span></h4><p class="small">seam top-2/top-3 radius 140 mm, below 150 (weld)</p><details class="small"><summary class="muted">Last run: import ✓ cover ✓ seams ✓ patterns ✓ cut pieces ✓</summary><pre class="note">…</pre></details></div></div>`;
  } else if (tab === "seams") {
    body = `<div class="toolbar"><div class="seg"><button class="on">Draw a seam</button><button>Move</button><button>Delete</button></div><button class="btn sm">Let the program add seams</button><span class="grow"></span><button class="btn sm ghost">Use automatic seams</button><button class="btn sm primary">Save seams</button></div><div style="height:420px"><div class="stage"><div class="sofa"></div></div></div>`;
  } else {
    body = `<table class="list"><tbody>${[["cut.dxf", "for the cutting table: pieces with allowances"], ["cutting-list.pdf", "every piece and the fabric needed"], ["checklist.pdf", "the workshop's check list"], ["sizes.pdf", "size drawing, seam to seam"], ["pattern.dxf", "flat pieces seam to seam"], ["panels.glb", "the panels in colour (3D)"], ["cover.json", "this cover's own settings"]].map(([f, h]) => `<tr><td><a href="#">${f}</a></td><td class="muted">${h}</td></tr>`).join("")}</tbody></table>`;
  }
  return `${note("<b>A cover's page</b>: one header with what matters (status, approval, DXF, run again) instead of five stacked cards; <b>7 tabs instead of 12</b>, each in the address (#/model/…/pieces), so a link opens the right tab. The viewer's 15 controls are now 6.")}
  <div class="crumbs"><a href="#/covers/all">Covers</a> / ${esc(c[1])}</div>
  <section class="panel">
    <div class="model-head"><span class="pic"></span>
      <div><h1 style="font-size:22px">${esc(c[1])}</h1><div class="meta"><span>${c[0]}</span><span>${c[5]} cm</span><span>${c[6]} pieces</span><span>hem 9.6 m</span><span>about 6.4 m of roll</span><span>${c[4] || "no category"}</span></div></div>
      <div class="acts" style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">
        ${desk ? `<a class="btn" href="#/work/desk/${id}">At the Desk</a>` : ""}
        <button class="btn">Run again</button>
        ${locked ? `<span class="btn" title="Approve at the Desk first" style="opacity:.6">🔒 DXF</span>` : `<a class="btn primary" href="#">Download DXF</a>`}
        <span class="dd"><button class="btn ghost" data-dd>More</button><span class="drop" style="left:auto;right:0"><button class="item">Edit details (family, status, tags, notes)</button><button class="item">Ask for approval</button><button class="item">Add to an arrangement</button><button class="item">Copy link</button></span></span>
      </div></div>
    <div class="status-strip"><span class="steps" title="import, cover, seams, patterns, cut pieces"><i></i><i></i><i></i><i></i><i></i></span>
      ${chip(c[2] === "ready" ? "Cover ready" : "To check", c[2] === "ready" ? "ok" : "warn")}${chip("Status: " + c[3], c[3] === "checked" ? "info" : "")}
      ${desk ? chip("Desk: " + ST[desk.st][0], ST[desk.st][1]) : ""}${locked ? chip("DXF locked until approved", "warn") : chip("Approved by Rens, revision 9", "ok")}
      <span class="grow" style="flex:1"></span><span class="muted">Last run 9 Oct 07:41 · nothing changed by more than 1 mm</span></div>
    <nav class="tabs">${MTABS.map(([k, l]) => `<a href="#/model/${id}/${k}" class="${k === tab ? "on" : ""}">${l}${k === "history" ? `<span class="count">1</span>` : ""}</a>`).join("")}</nav>
    ${body}
  </section>`;
}

// ---------------------------------------------------------------- Prices
function pagePrices(parts) {
  const sub = parts[1] ?? "materials";
  const rows = {
    materials: [["Fabric: Sunbrella Coverlast", "€ / m of roll (152 cm)", "24.50", true], ["Cutting waste", "% beyond the simple row layout", "12.5", true], ["Air vent set", "€ per vent: insert, membrane, logo", "3.75", true], ["Drawcord", "€ / m", "0.65", false], ["Elastic", "€ / m (elastic hem only)", "0.85", true], ["Balloon", "€ each; sold next to the cover", "14.50", true], ["Frame", "€ each; sold next to the cover", "64.50", true]],
    labour: [["Labour rate", "€ / hour, cutting and sewing", "42.50", true], ["Cutting table set-up", "min per cover", "12.5", true], ["Per piece", "min: cutting, pen, sorting", "6.5", true], ["Seam", "min / m, double stitching", "2.5", true], ["Vent", "min each: opening, hood, insert, logo", "9.5", true], ["Hem", "min / m with cord channel", "1.75", true], ["Packing", "min per cover", "6.5", true]],
  }[sub] ?? [["Rupiah per euro", "fixed, entered by hand", "18,500", true], ["Date of the rate", "", "8 Oct 2026", false]];
  return `${note("<b>Prices</b> is a section of its own (it was both in the top bar and inside Admin, as tabs inside tabs). Its tabs are the sub-menu; the draft bar stays on top while you scroll; a live example on the right follows what you type.")}
  <section class="panel" style="margin-bottom:12px"><div class="pricebar">
    <div class="grow"><b>Live: version 4</b> <span class="muted">by Rick, 9 Oct 14:02 — “Coverlast price per 1 Oct”</span><div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">${chip("draft by Rick, 11 Oct — not live", "sand")}${chip("23 of 31 values still placeholders", "warn")}</div></div>
    ${role === "admin" ? `<input class="field" placeholder="What changed (for the history)" style="width:240px"/><button class="btn">Save draft</button><button class="btn">Preview changes</button><button class="btn primary">Publish</button><span class="dd"><button class="btn ghost" data-dd>⋯</button><span class="drop" style="left:auto;right:0"><button class="item">Discard draft</button></span></span>` : `<span class="muted small">You can look; an admin changes the prices.</span>`}
  </div><div style="padding:0 14px 12px"><div class="flow"><span><b>Cost price</b> fabric + parts + labour</span><span><b>Landed</b> + shipping, duties, packing</span><span><b>Ex VAT</b> × markup or ÷ margin</span><span><b>Shown</b> + VAT, rounded</span></div></div></section>
  <div class="grid2" style="grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr)">
    <section class="panel"><header><h3>${IA[3].pages.find((p) => p.id === sub)?.label ?? ""}</h3><span class="grow"></span><span class="muted small">Every number with its unit and an example</span></header>
    ${rows.map(([n, h, v, ph]) => `<div class="setrow" style="grid-template-columns:minmax(160px,1fr) 140px minmax(120px,1fr)"><div class="name"><b>${n}</b><span class="muted small">${h}</span></div><div class="ctl"><input class="field" value="${v}"/></div><div class="help">${ph ? `<span class="ph">placeholder — please confirm</span> <button class="btn sm ghost">Keep this value</button>` : chip("confirmed", "ok")}</div></div>`).join("")}
    </section>
    <aside class="panel example"><header><h3>Example: C1 · Corner sofa Lucia</h3></header><div class="body stack small">
      <ul class="facts"><li><i class="dot"></i><span>Fabric 6.4 m</span>€ 176.40</li><li><i class="dot"></i><span>Parts</span>€ 38.15</li><li><i class="dot"></i><span>Labour 3 h 12</span>€ 136.00</li><li><i class="dot"></i><span>Cost price</span><b>€ 350.55</b></li><li><i class="dot"></i><span>B2C incl. VAT</span><b>€ 795.95</b></li><li><i class="dot"></i><span>B2B ex VAT</span><b>€ 572</b></li></ul>
      <select class="field"><option>Another cover…</option></select></div></aside>
  </div>`;
}

// ---------------------------------------------------------------- Settings
function setrow(name, key, ctl, help, src, who = "admin", locked = false) {
  return `<div class="setrow ${locked ? "locked" : ""}"><div class="name"><b>${name}</b>${key ? `<code>${key}</code>` : ""}</div><div class="ctl">${ctl}</div>
  <div class="help">${help}<div class="src">${src}<span class="who">${locked ? "🔒 developer only: a line in config/defaults.yaml" : "✎ " + who}</span></div></div></div>`;
}
const inp = (v, ph = "") => `<input class="field" value="${esc(v)}" placeholder="${ph}"/>`;
const sw = (on) => `<button class="switch ${on ? "on" : ""}" data-switch aria-pressed="${on}"></button>`;
const dflt = (v) => chip(`default ${v}`);
const ovr = (v) => chip(`changed · default ${v}`, "sand");

function settingsBody(tab) {
  switch (tab) {
    case "company": return {
      intro: "The company and the consumer shop: who you are on invoices and the website, which languages, colours and shipping costs. Payments start working once a Mollie key is filled in.",
      rows: [
        setrow("Company name", "company.name", inp("", "to fill in"), "On invoices, mails and the website's footer.", chip("empty", "warn")),
        setrow("Legal name, KvK, VAT number", "company.*", inp("", "to fill in"), "Shown on invoices and the legal pages.", chip("empty", "warn")),
        setrow("Address, e-mail, phone, IBAN", "company.*", `<button class="btn sm">Edit 7 fields</button>`, "Invoice address and contact for customers.", chip("3 empty", "warn")),
        setrow("Website domain", "domain", inp("", "example.com"), "The website's own address; needed for links in mails and the fit question.", chip("empty", "warn")),
        setrow("Languages", "languages", inp("nl,en,de,fr"), "The first is the main language. Missing texts are translated in Shop → Website (AI).", dflt("nl,en,de,fr")),
        setrow("Colours offered", "colours", inp("Charcoal, Navy, Light Grey, Taupe"), "The Coverlast colours in the configurator, comma separated. (Was in two places: Shop settings and the price defaults.)", dflt("4 colours")),
        setrow("Shipping per country", "shipping", `<button class="btn sm">NL · BE · DE</button>`, "Delivery cost per country for consumer orders.", chip("3 without a price", "warn")),
        setrow("Mollie key", "payment.mollie_key", inp("", "test_… or live_…"), "test_… to try, live_… for real payments.", chip("empty", "warn")),
        setrow("Bank transfer", "payment.bank_transfer", sw(true), "Offer payment by bank transfer; such an order goes into production by hand.", dflt("on")),
        setrow("Balloon and frame products", "products.*", `<button class="btn sm">Edit</button>`, "Name, size and photo of the supports sold next to table covers.", dflt("")),
      ],
      adv: "Home film, story media, logo and share picture (6)",
    };
    case "users": return {
      intro: "Who logs in, with which role, and who may approve. One place for rights: <b>may approve</b> replaces the developer list <code>desk.approvers</code>, and <b>owner</b> replaces <code>questions.owners</code>.",
      table: `<table class="list"><thead><tr><th>Name</th><th>Role</th><th>May approve</th><th>Owner</th><th>Access</th><th></th></tr></thead><tbody>
      ${[["Rick", "rick", "admin", true, true, "password set"], ["Rens", "rens", "editor", true, false, "password set"], ["Wout", "wout", "editor", true, false, "invited until 16 Oct"], ["Eddy", "eddy", "editor", false, false, "password set"], ["Workshop", "werk", "viewer", false, false, "not invited"]].map(([n, u, r, a, o, s]) => `<tr><td><b>${n}</b> <span class="muted small">${u}</span></td><td><select class="field" style="height:28px"><option>${r}</option></select></td><td>${sw(a)}</td><td>${sw(o)}</td><td class="small">${s}</td><td class="num"><span class="dd"><button class="btn sm ghost" data-dd>⋯</button><span class="drop" style="left:auto;right:0"><button class="item">Send invitation</button><button class="item">New password link</button><button class="item">Deactivate</button></span></span></td></tr>`).join("")}
      </tbody></table><div class="toolbar" style="border-top:1px solid var(--line);border-bottom:0"><button class="btn primary">+ Add a person</button><button class="btn">Invite everyone not yet in</button><span class="grow"></span><span class="muted small">viewer: looks and downloads · editor: also uploads, calculates, changes covers · admin: also Settings, Shop, publishing prices</span></div>`,
    };
    case "desk": return {
      intro: "How the Desk works: which covers need an approval before the workshop may download the DXF, when a repeated correction becomes a rule, and how often mails go out.",
      rows: [
        setrow("DXF only after approval", "desk.require_approval_for_dxf", sw(true), "The cutting table's file downloads only once a cover is approved at the Desk.", dflt("on")),
        setrow("Which covers need it", "desk.gate_scope", `<select class="field"><option>Drawing covers</option><option>Every cover</option></select>`, "Drawing covers only, or every model (the SUNS models are all still draft).", dflt("drawing covers")),
        setrow("Arrangements need it too", "desk.gate_arrangements", sw(true), "An arrangement's DXF only after Rens or Wout approved it, whatever the line above says.", dflt("on")),
        setrow("Propose a rule after", "desk.learn_after", inp("5"), "The same correction on this many covers of one series is proposed as the series' rule.", dflt("5")),
        setrow("Questions digest", "questions.digest_hours", inp("24"), "New questions mailed to those who answer: at most once per this many hours (0: no mail).", dflt("24")),
        setrow("Answers digest", "questions.answer_digest_hours", inp("8"), "New answers mailed to the owners: at most once per this many hours.", dflt("8")),
      ],
      adv: "Picture limits: size, number, longest side (3)",
    };
    case "defaults": return {
      intro: "The company's defaults for every cover. A cover's own value (its Adjust tab) still wins. <b>Owner-editable</b> values change here with a reason, kept in the history; values that the geometry depends on stay a line in <code>config/defaults.yaml</code> and are shown read-only.",
      rows: [
        `<div class="setrow" style="background:var(--stone)"><b class="label">Air vents</b></div>`,
        setrow("Vent opening", "features.vent_width_mm × vent_height_mm", `${inp("250")}<span class="muted">×</span>${inp("220")}<span class="muted">mm</span>`, "The opening, with a hood holding the plastic insert and a membrane inside.", dflt("250 × 220")),
        setrow("Vents per metre", "features.vents_per_metre", inp("1"), "One vent per full metre of each side, spread evenly; at least one per side.", dflt("1")),
        setrow("Bottom edge above the hem", "features.vent_above_hem_mm", `${inp("50")}<span class="muted">mm</span>`, "Where the vent sits on the skirt.", dflt("50")),
        setrow("Vents on inner walls", "features.vent_inner_walls", sw(true), "The front walls in the inner corner of L, U and C covers get vents too (9 Oct, question 71).", dflt("on")),
        setrow("Logo on every vent", "features.vent_logo", sw(true), "A frame marked LOGO on the hood, in pen.", dflt("on")),
        `<div class="setrow" style="background:var(--stone)"><b class="label">Hem, seams, fabric</b></div>`,
        setrow("Hem allowance", "hem.allowance_mm", `${inp("50")}<span class="muted">mm</span>`, "Fabric turned in for the hem with its cord channel.", chip("to confirm", "warn") + dflt("50")),
        setrow("Seam allowance (stitched)", "stitching.allowance_mm", `${inp("15")}<span class="muted">mm</span>`, "Per stitched seam.", chip("to confirm", "warn") + dflt("15")),
        setrow("Skirt seam", "seams.skirt_seam", `<select class="field"><option>level</option></select>`, "At one height all round, so skirt pieces are straight strips (company rule).", dflt("level")),
        setrow("Usable roll width", "roll.usable_width_mm", `${inp("1480")}<span class="muted">mm</span>`, "No piece may be wider in its narrowest direction.", dflt("1480"), "", true),
        setrow("Cover clearance", "hull.clearance_mm", `${inp("10")}<span class="muted">mm</span>`, "Room between the furniture and the cover.", dflt("10"), "", true),
      ],
      adv: "Developer-only: cover surface, flattening, drape physics, export, drawing reader (≈ 180, read-only)",
    };
    case "mail": return {
      intro: "The mail server, and every address the studio sends to, in one list. Before, these were on five tabs (Mail, Shop settings, Requests, System, B2B).",
      rows: [
        setrow("Mail server (SMTP)", "smtp.*", `<button class="btn sm">Server, port, user, sender</button><button class="btn sm ghost">Send a test mail</button>`, "Without it, invitations and notifications are copied by hand.", chip("set", "ok")),
        setrow("Public address", "public_url", inp("https://covers.suns.nu"), "Used in links in mails.", chip("set", "ok")),
        setrow("Login code by mail", "login_code", sw(false), "A second step when logging in from a new device.", dflt("off")),
        `<div class="setrow" style="background:var(--stone)"><b class="label">Who gets which mail</b></div>`,
        setrow("New orders", "notify_email", inp("", "orders@…"), "A mail for every paid or B2B order.", chip("empty", "warn")),
        setrow("Configurator requests", "request_email", inp("", "sales@…"), "A customer asks for a quote.", chip("empty", "warn")),
        setrow("Server alerts", "alert_email", inp("rick@…"), "The server checks itself every 10 minutes and mails when something is wrong.", chip("set", "ok")),
        setrow("Fit question to customers", "fit_mail.enabled · days", `${sw(false)}${inp("14")}<span class="muted">days</span>`, "One question after delivery; answers appear under Shop → Matches.", dflt("off, 14 days")),
      ],
    };
    case "ai": return {
      intro: "What the AI may cost. At 100 % of the budget paid calls stop (the Desk's “Let the AI read it”, the photo suggestion). This month so far: <b>€ 5.48 of € 50</b> (11 %).",
      rows: [
        setrow("Monthly budget", "spend.budget_eur_month", `<span class="muted">€</span>${inp("50")}`, "Paid AI calls per month.", chip("to confirm", "warn") + dflt("€ 50")),
        setrow("Warn at", "spend.warn_pct", `${inp("50,80")}<span class="muted">%</span>`, "The watchdog mails at these shares of the budget.", dflt("50, 80")),
        setrow("Warn on a spike", "spend.hourly_spike_eur", `<span class="muted">€</span>${inp("2.5")}`, "…and when one hour costs more than this.", dflt("€ 2.50")),
        setrow("Stop at the budget", "spend.hard_stop", sw(true), "Refuse paid calls once the budget is used up.", dflt("on")),
        setrow("Models and prices per token", "ai.* · spend.prices", inp("gemini-3.8-flash, deepseek-flash"), "Which AI reads and checks; set by the developer.", dflt(""), "", true),
      ],
    };
    case "matching": return {
      intro: "When a customer's sizes match a cover we already make. One place for the matching rules: <code>match.*</code> (sizes) and the shop's <code>matching.*</code> (mode, thresholds) were two lists with the same threshold in both.",
      rows: [
        setrow("Mode", "matching.mode", `<div class="seg"><button class="on">Learning (a colleague confirms)</button><button>Automatic</button></div>`, "Learning: every proposal waits in Shop → Matches. Automatic: above the threshold the customer sees it at once.", dflt("learning")),
        setrow("Offer the existing cover from", "match.threshold_pct", `${inp("90")}<span class="muted">%</span>`, "Match at or above this: we offer the existing cover.", dflt("90")),
        setrow("Let the customer choose from", "match.choice_pct", `${inp("80")}<span class="muted">%</span>`, "Between this and the threshold: existing or custom; below: custom.", dflt("80")),
        setrow("Stock discount", "matching.stock_discount_pct", `${inp("", "%")}`, "An existing cover sells at the configurator's price minus this.", chip("empty", "warn")),
        setrow("Drawing covers offered when", "match.drawing_statuses", `<select class="field"><option>Approved or produced</option></select>`, "Desk status that makes a drawing cover an existing cover in the shop.", dflt("approved, produced")),
      ],
      adv: "Fit curve: tight / loose cm and fall-off, weights (5)",
    };
    case "b2b": return {
      intro: "Terms for business customers. The companies themselves are in Shop → B2B customers.",
      rows: [
        setrow("Minimum order", "b2b.min_order_eur", `<span class="muted">€</span>${inp("0")}`, "Ex VAT; 0: none.", dflt("0")),
        setrow("Shipping per order", "b2b.shipping_eur", `<span class="muted">€</span>${inp("0")}`, "On top, ex VAT; 0: in the price list's extras.", dflt("0")),
        setrow("Payment term", "b2b.payment_days", `${inp("30")}<span class="muted">days</span>`, "Of the invoice.", dflt("30")),
        setrow("Into production at once", "b2b.auto_produce", sw(false), "An order on account goes into production like a paid consumer order.", dflt("off")),
      ],
    };
    case "website": return {
      intro: "How the website, other webshops and the studio reach each other. Keys are shown once.",
      rows: [
        setrow("Website key", "shop_link_key", `<button class="btn sm">Make a new key</button>`, "The website on Cloudflare reaches the studio with it; a new key stops the old one.", chip("set 7 Oct", "ok")),
        setrow("Studio shop closed to visitors", "website_link.closed", sw(false), "On: the studio's /shop/ is only a preview for colleagues; visitors go to the website.", dflt("off")),
        setrow("Configurator in other webshops", "embed_origins", `<textarea class="field" style="height:56px;padding:6px">https://hello-suns.com</textarea>`, "Addresses that may show the configurator in an iframe, one per line.", chip("1 address")),
        setrow("API keys", "webshop.keys", `<button class="btn sm">hello-suns shop · revoke</button><button class="btn sm">+ Make a key</button>`, "For a webshop that calls the API from its own server.", chip("1 key")),
        setrow("Scroll story as home page", "home_story", sw(false), "On: the live site opens with the scroll story; preview always shows it.", dflt("off")),
      ],
      adv: "Story model and media files (7)",
    };
    case "system": return {
      intro: "The server's state. Read only; alerts go to the address in Mail &amp; notifications.",
      table: `<table class="list"><tbody>${[["Release (live)", "v1.30.0"], ["Models", "433"], ["Disk free", "61 of 150 GB"], ["Last backup", "11 Oct 03:10"], ["Mail server", "set"], ["AI key", "present"]].map(([a, b]) => `<tr><td class="muted">${a}</td><td>${b}</td></tr>`).join("")}</tbody></table>
        <div class="body"><h4 class="label">Last releases</h4><p class="small">v1.30.0 · 9 Oct · v1.29.0 · 9 Oct · v1.28.0 · 8 Oct</p><h4 class="label" style="margin-top:10px">Last alerts</h4><p class="small muted">None.</p></div>`,
    };
    default: return {
      intro: "Who is logged in now, and every login, change and approval with who and when.",
      table: `<div class="toolbar"><div class="seg"><button class="on">Audit log</button><button>Logged in now (3)</button></div><input class="field" placeholder="Filter: person, action…"/></div><table class="list"><tbody>${[["11 Oct 09:12", "rens", "approve drawing-c10 r7"], ["11 Oct 08:58", "rick", "publish prices v4"], ["10 Oct 17:40", "eddy", "login"]].map((r) => `<tr><td class="small muted">${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td></tr>`).join("")}</tbody></table>`,
    };
  }
}

function pageSettings(parts) {
  const tab = parts[1] ?? "company";
  const b = settingsBody(tab);
  const t = SETTINGS.find((x) => x.id === tab);
  return `${note("<b>Settings</b>: one area with tabs for everything that is set once (was spread over 13 Admin tabs, Shop settings as raw keys, B2B, Requests, System and config/defaults.yaml). Every tab says what it is for; every setting says what it does, its default, whether it was changed, and who may change it.")}
  <div class="page-head"><div class="grow"><h1>Settings</h1><p>Only admins change these. Every change is kept in the audit log with who and when.</p></div></div>
  <div class="settings">
    <nav class="panel vtabs">${SETTINGS.map((s) => s.grp ? `<div class="grp label">${s.grp}</div>` : `<a href="#/settings/${s.id}" class="${s.id === tab ? "on" : ""}">${s.label}${s.n ? `<small>${s.n}</small>` : ""}</a>`).join("")}</nav>
    <section class="panel">
      <header><h3 style="font-size:var(--fs-l)">${t?.label ?? ""}</h3><span class="grow"></span>${b.rows ? `<label class="small muted"><input type="checkbox"/> Only changed values</label>` : ""}</header>
      <div class="intro"><p>${b.intro}</p></div>
      ${b.rows ? b.rows.join("") : ""}${b.table ?? ""}
      ${b.adv ? `<details class="adv"><summary>Advanced: ${b.adv}</summary><p class="muted small" style="padding:0 14px 12px">Shown only on request; same form, same explanations.</p></details>` : ""}
      ${b.rows ? `<div class="savebar"><span class="muted small">No unsaved changes</span><span class="grow" style="flex:1"></span><button class="btn" disabled>Undo</button><button class="btn primary" disabled>Save</button></div>` : ""}
    </section>
  </div>`;
}

// ---------------------------------------------------------------- Shop pages (lists)
function pageShop(page) {
  if (page === "orders") return pageSimple("Orders", "Consumer and B2B orders, newest first. A paid order goes into production by itself.",
    `<section class="panel"><div class="toolbar"><div class="seg"><button class="on">Open 2</button><button>In production</button><button>Shipped</button><button>All</button></div><select class="field"><option>All channels</option><option>Consumer</option><option>B2B</option></select><input class="field" placeholder="Search customer, order, cover"/></div>
    <table class="list"><thead><tr><th>#</th><th>When</th><th>Customer</th><th>Cover</th><th class="num">Total</th><th>Status</th><th></th></tr></thead><tbody>
    <tr class="click"><td>1042</td><td>10 Oct</td><td>J. de Vries <span class="muted small">consumer</span></td><td>C1 · Corner sofa Lucia, Charcoal</td><td class="num">€ 795.95</td><td>${chip("paid", "ok")}</td><td class="num"><button class="btn sm">Open</button></td></tr>
    <tr class="click"><td>1041</td><td>9 Oct</td><td>Sunsit B.V. <span class="muted small">B2B</span></td><td>3 × S40 · Daybed</td><td class="num">€ 1,716</td><td>${chip("on account", "info")}</td><td class="num"><button class="btn sm">Open</button></td></tr></tbody></table></section>`,
    "<b>Shop</b> collects what customers do: orders, requests, matches, B2B customers; plus the website's text. Its settings moved to Settings.");
  const label = IA[2].pages.find((p) => p.id === page)?.label ?? page;
  return pageSimple(label, IA[2].pages.find((p) => p.id === page)?.hint ?? "", `<section class="panel"><div class="body muted">The page as it is today, in the list template (filters on one row, a table, a detail on the right). Unchanged content.</div></section>`);
}

// ---------------------------------------------------------------- render
function render() {
  const { parts, q } = route();
  const [section, page] = parts;
  let html = "";
  let navSection = section;
  let navPage = page;
  if (section === "work" && page === "desk") html = pageDesk(parts);
  else if (section === "work" && page === "questions") html = pageQuestions(parts);
  else if (section === "work") { html = pageWorkshop(); navPage = "workshop"; }
  else if (section === "covers" && page === "new") html = pageNew();
  else if (section === "covers" && page === "arrangements") html = pageSimple("Arrangements", "Place furniture from the catalogue together, then build one cover over the whole and send it to the Desk.", `<section class="panel"><div class="body muted">The arrangement builder as today, in the list + detail template: the list of arrangements left (it is now a line of links), the plan and the cover right.</div></section>`);
  else if (section === "covers" && page === "learning") html = pageSimple("Learning", "Your own covers against the program's: zips of drawings with their 3D models, the references per cover, the lessons accepted.", `<section class="panel"><div class="body muted">As today, without its upload card (that is in New cover). Per-cover references stay on the cover's Compare tab, and are listed here too.</div></section>`);
  else if (section === "covers" && page === "products") html = pageSimple("Product list", "The workshop's product list (Excel) linked to the drawing covers; upload a new one to replace the links.", `<section class="panel"><div class="body"><div class="drop-zone">Drop an .xlsx, .csv or .zip</div><p class="muted small" style="margin-top:8px">Last: namecode.xlsx · 112 rows linked to 96 drawings through “Code” · 4 rows not linked</p></div></section>`, "Moved from the top of the Desk, where it took a line on every visit.");
  else if (section === "covers") { html = pageCovers(q); navPage = "all"; }
  else if (section === "model") { html = pageModel(parts); navSection = "covers"; navPage = "all"; }
  else if (section === "shop") html = pageShop(page ?? "orders");
  else if (section === "prices") html = pagePrices(parts);
  else if (section === "settings") html = role === "admin" ? pageSettings(parts) : `<p>Only admins see Settings.</p>`;
  else if (section === "guide") html = pageSimple("Guide", "How Cover Studio works: the short guide, also readable without logging in.", "");
  else if (section === "account") html = pageSimple("My account", "Name, e-mail, password.", "");
  else html = pageCovers(q);
  renderNav(navSection, navPage);
  $("#main").innerHTML = html;
  scrollTo(0, 0);
}

document.addEventListener("click", (e) => {
  const t = e.target;
  const go = t.closest("[data-go]");
  if (go) { location.hash = go.dataset.go; return; }
  const dd = t.closest("[data-dd]");
  document.querySelectorAll(".dd.open").forEach((d) => { if (!dd || d !== dd.parentElement) d.classList.remove("open"); });
  if (dd) { dd.parentElement.classList.toggle("open"); e.preventDefault(); return; }
  const s = t.closest("[data-switch]");
  if (s) { s.classList.toggle("on"); s.setAttribute("aria-pressed", s.classList.contains("on")); return; }
  if (t.closest("#me")) { $("#mepop").classList.toggle("hide"); return; }
  if (!t.closest("#mepop")) $("#mepop").classList.add("hide");
  if (t.closest("[data-theme]")) {
    const r = document.documentElement;
    const dark = r.dataset.theme ? r.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    r.dataset.theme = dark ? "light" : "dark";
  }
  const segBtn = t.closest(".seg button");
  if (segBtn && !segBtn.dataset.go) { segBtn.parentElement.querySelectorAll("button").forEach((b) => b.classList.remove("on")); segBtn.classList.add("on"); }
});
$("#role").value = role;
$("#role").addEventListener("change", (e) => {
  role = e.target.value;
  try { localStorage.setItem("proto-role", role); } catch { /* private window */ }
  location.hash = "#/";
  render();
});
addEventListener("hashchange", render);
render();
