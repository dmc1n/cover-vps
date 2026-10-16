// The studio's map (docs/plans/studio-ui.md, ADR-122, ADR-126): four sections, each with its own pages
// (the sub-menu), every page and tab in the address, and every old address sent to its new
// place. Pure functions, so the browser check (e2e/uinav.py) and the code agree on one table.
import type { User } from "./api";
import type { IconName } from "./icons";

export type Role = User["role"];
/** Who sees a page: everyone, people who may edit (not viewers), or admins. */
export type Who = "all" | "edit" | "admin";

export interface Page {
  id: string;
  label: string;
  who: Who;
  hint: string;
  icon: IconName; // beside the label in the sub-menu (Studio 2.0, ADR-130)
  sep?: boolean; // a thin separator before this page in the sub-menu
  group?: string; // a small label before this page in the sub-menu (Shop: "Tools")
}
export interface Section {
  id: "work" | "covers" | "shop" | "settings";
  label: string;
  who: Who;
  hint: string;
  icon: IconName;
  pages: Page[];
}

export const SECTIONS: Section[] = [
  {
    id: "work",
    icon: "work",
    label: "Work",
    who: "all",
    hint: "What waits for a person: the Desk, the questions, the workshop",
    pages: [
      {
        id: "desk",
        icon: "desk",
        label: "Desk",
        who: "all",
        hint: "Approve or reject covers and arrangements",
      },
      {
        id: "questions",
        icon: "questions",
        label: "Questions",
        who: "all",
        hint: "The owner's and the workshop's questions",
      },
      {
        id: "workshop",
        icon: "workshop",
        label: "Workshop",
        who: "all", // the workshop login's start page (ADR-128)
        hint: "Orders to make, approved covers: their files, measured fits and the customers' answers",
      },
    ],
  },
  {
    id: "covers",
    icon: "covers",
    label: "Covers",
    who: "all",
    hint: "Every cover and model, arrangements, new covers",
    pages: [
      {
        id: "all",
        icon: "all-covers",
        label: "All covers",
        who: "all",
        hint: "Every model and its cover, as a table or as cards",
      },
      {
        id: "arrangements",
        icon: "arrangements",
        label: "Arrangements",
        who: "all",
        hint: "Furniture placed together under one cover",
      },
      {
        id: "new",
        icon: "new-cover",
        label: "New cover",
        who: "edit",
        hint: "From a 3D file or a drawing (PDF)",
      },
      {
        id: "learning",
        icon: "learning",
        label: "Learning",
        who: "all",
        hint: "Your covers against ours: pairs of drawings and 3D",
        sep: true,
      },
      {
        id: "links",
        icon: "links",
        label: "Links",
        who: "all", // viewers look; editors and admins decide (the API checks it, ADR-132)
        hint: "A drawing and a 3D model of the same product, linked: confirm or correct",
      },
      {
        id: "products",
        icon: "product-list",
        label: "Product list",
        who: "edit",
        hint: "The product list (Excel) linked to the drawings",
      },
    ],
  },
  {
    id: "shop",
    icon: "shop",
    label: "Shop",
    who: "edit",
    hint: "Orders, requests, business customers, the website",
    pages: [
      {
        id: "orders",
        icon: "orders",
        label: "Orders",
        who: "admin",
        hint: "Orders from the shop and the B2B shop",
      },
      {
        id: "requests",
        icon: "requests",
        label: "Requests",
        who: "admin",
        hint: "What customers asked: quotes from the configurator, and which existing cover fits (matches, learning mode)",
      },
      {
        id: "b2b",
        icon: "b2b",
        label: "B2B customers",
        who: "admin",
        hint: "Companies, their logins, own prices and orders",
      },
      {
        id: "website",
        icon: "website",
        label: "Website (AI)",
        who: "edit",
        hint: "Change the website's text, preview it; an admin publishes",
        sep: true,
      },
    ],
  },
  {
    id: "settings",
    icon: "settings",
    label: "Settings",
    who: "edit", // editors see only the Prices & costs tabs (read-only), as Prices before
    hint: "Everything that is set once: company, prices and costs, people, mail, keys, system",
    pages: [], // vertical tabs inside the page (SETTINGS_TABS)
  },
];

/** The Settings area's tabs, in groups (vertical on a wide screen, a row on a tablet). Since
 * ADR-126 the general price settings live here too (Prices & costs); what belongs to one cover
 * (its cost, prices, shop place, orders) is on the cover's own Price & shop tab. */
/** A Settings tab: id, label, icon and the colour of its tile (iOS Settings, ADR-130). */
export type SettingsTab = [string, string, IconName, Tile];
export type Tile =
  "blue" | "orange" | "green" | "teal" | "indigo" | "purple" | "grey";
export const SETTINGS_TABS: { group: string; tabs: SettingsTab[] }[] = [
  {
    group: "Business",
    tabs: [
      ["company", "Company & shop", "company", "blue"],
      ["selling", "Selling", "selling", "orange"],
    ],
  },
  {
    group: "Prices & costs",
    tabs: [
      ["costs", "Costs", "costs", "green"],
      ["pricing", "Price rules", "pricing", "teal"],
      ["publish", "Publish & versions", "publish", "indigo"],
    ],
  },
  {
    group: "People & work",
    tabs: [
      ["users", "Users & rights", "users", "blue"],
      ["defaults", "Rules & defaults", "defaults", "grey"],
    ],
  },
  {
    group: "Connections",
    tabs: [
      ["mail", "Mail & notifications", "mail", "teal"],
      ["website", "Website & API keys", "keys", "orange"],
      ["ai", "AI & spending", "ai", "purple"],
    ],
  },
  {
    group: "Server",
    tabs: [["system", "System & logs", "system", "grey"]],
  },
];
/** Who sees a Settings tab: the price tabs are for editors too (they look, admins change, as the
 * API decides); every other tab is for admins. */
export const SETTINGS_WHO: Record<string, Who> = {
  costs: "edit",
  pricing: "edit",
  publish: "edit",
};
export const settingsWho = (tab: string): Who => SETTINGS_WHO[tab] ?? "admin";
export const SETTINGS_IDS = SETTINGS_TABS.flatMap((g) =>
  g.tabs.map((t) => t[0]),
);
/** The Settings tabs a person may see, in their groups. */
export const visibleSettings = (user: Viewer) =>
  SETTINGS_TABS.map((g) => ({
    ...g,
    tabs: g.tabs.filter(([id]) => allowed(settingsWho(id), user)),
  })).filter((g) => g.tabs.length > 0);

/** A cover's tabs (#/model/<id>/<tab>[/<sub>]), each with its icon. */
export const MODEL_TABS: [string, string, IconName][] = [
  ["3d", "3D", "3d"],
  ["pieces", "Pieces", "pieces"],
  ["seams", "Seams", "seams"],
  ["adjust", "Adjust", "adjust"],
  ["compare", "Compare", "compare"],
  ["history", "History", "history"],
  ["price", "Price & shop", "price"], // cost, prices, the shop, orders: this cover's own (ADR-126)
];
/** The sub-views inside a cover's tabs: the old twelve tabs, each still one click away. */
export const MODEL_SUBS: Record<string, [string, string][]> = {
  pieces: [
    ["cut", "Cut pieces"],
    ["cutfile", "Cutting file"], // cut.dxf drawn on the server, behind no download (ADR-147)
    ["flat", "Flat patterns"],
    ["sizes", "Size drawing"],
    ["files", "Files"], // the downloads (a tab of its own before ADR-126)
  ],
  compare: [
    ["drawing", "Your drawing"],
    ["reference", "Your reference"],
    ["ai", "AI advice"],
  ],
  history: [
    ["changes", "Approval & changes"],
    ["revisions", "Revisions"],
    ["log", "Warnings and log"],
  ],
};
/** A Desk card's tabs (#/work/desk/<id>/<tab>): a short label and an icon (ADR-130). */
export const DESK_TABS: [string, string, IconName][] = [
  ["check", "Check", "check"],
  ["pieces", "Pieces", "desk-pieces"],
  ["correct", "Correct", "correct"],
  ["history", "History", "history"],
];

export interface Viewer {
  role: Role;
  can_approve?: boolean;
  desk_approver?: boolean;
}

/** The workshop login (ADR-128) sees Work only: the Desk (read-only), its questions and the
 * Workshop; the server refuses everything else anyway (an allow-list in security.py). */
export const WORKSHOP_PAGES = new Set([
  "work",
  "work/desk",
  "work/questions",
  "work/workshop",
]);
export const isWorkshop = (user?: Viewer | null): boolean =>
  user?.role === "workshop";
/** May change things: editors and admins (not viewers, not the workshop login). */
export const isEditor = (user?: Viewer | null): boolean =>
  user?.role === "admin" || user?.role === "editor";

/** `id`: the section ("work") or the page ("work/desk") the check is for; the workshop login
 * sees only WORKSHOP_PAGES. */
export const allowed = (who: Who, user: Viewer, id?: string): boolean =>
  isWorkshop(user)
    ? id !== undefined && WORKSHOP_PAGES.has(id)
    : who === "all" ||
      (who === "edit" && isEditor(user)) ||
      (who === "admin" && user.role === "admin");

export const visibleSections = (user: Viewer): Section[] =>
  SECTIONS.filter((s) => allowed(s.who, user, s.id)).map((s) => ({
    ...s,
    pages: s.pages.filter((p) => allowed(p.who, user, `${s.id}/${p.id}`)),
  }));

/** Approvers at the Desk start at Work → Desk, the workshop login at Work → Workshop (ADR-128);
 * everyone else at Covers → All covers (the owner, 11 Oct 2026; open question 3). */
export const startPage = (user: Viewer): string => {
  if (isWorkshop(user)) return "#/work/workshop";
  // an admin starts where he was last (his last section, remembered in this browser)
  if (user.role === "admin") {
    const last = rememberedPage();
    if (last) return last;
  }
  return user.desk_approver || user.can_approve
    ? "#/work/desk"
    : "#/covers/all";
};

const LAST_KEY = "studio.last";
function rememberedPage(): string | null {
  try {
    const v = localStorage.getItem(LAST_KEY);
    return v && /^#\/(work|covers|shop|settings)\/[a-z0-9]+$/.test(v)
      ? v
      : null;
  } catch {
    return null; // a private window
  }
}
/** Remember the section page an admin is on (his start page next time). */
export function rememberPage(hash: string, user: Viewer): void {
  if (user.role !== "admin") return;
  const m = hash.match(/^#\/(work|covers|shop|settings)\/[a-z0-9]+/);
  if (!m) return;
  try {
    localStorage.setItem(LAST_KEY, m[0]);
  } catch {
    /* a private window: not remembered */
  }
}

/** The first page of a section this person may see. */
export function sectionHome(id: string, user: Viewer): string | null {
  const s = visibleSections(user).find((x) => x.id === id);
  if (!s) return null;
  if (s.id === "settings") {
    const first = visibleSettings(user)[0]?.tabs[0]?.[0];
    return first ? `#/settings/${first}` : null;
  }
  return s.pages.length ? `#/${s.id}/${s.pages[0].id}` : null;
}

// Old Admin tabs and where they live now.
const ADMIN_TO: Record<string, string> = {
  users: "#/settings/users",
  orders: "#/shop/orders",
  b2b: "#/shop/b2b",
  matches: "#/shop/requests",
  shop: "#/settings/company",
  phototest: "#/settings/ai",
  prices: "#/settings/costs",
  website: "#/shop/website",
  webshop: "#/shop/requests",
  requests: "#/shop/requests",
  mail: "#/settings/mail",
  sessions: "#/settings/system",
  audit: "#/settings/system",
  system: "#/settings/system",
};
// The Prices section's tabs (ADR-098, 122) and where they live since ADR-126: the general part in
// Settings → Prices & costs; a cover's costing on the cover's own Price & shop tab.
const PRICES_TO: Record<string, string> = {
  materials: "#/settings/costs",
  labour: "#/settings/costs",
  rate: "#/settings/costs",
  channels: "#/settings/pricing",
  costing: "#/settings/pricing",
  import: "#/settings/publish",
  versions: "#/settings/publish",
};
// Shop pages that moved (ADR-126), and Settings tabs that were merged.
const SHOP_TO: Record<string, string> = {
  matches: "#/shop/requests",
  phototest: "#/settings/ai",
};
const SETTINGS_TO: Record<string, string> = {
  matching: "#/settings/selling",
  b2b: "#/settings/selling",
  desk: "#/settings/defaults",
  activity: "#/settings/system",
};
// A cover's old tabs (never in the address before, but named in the handbook) → tab/sub.
const MODEL_OLD: Record<string, string> = {
  drawing: "compare/drawing",
  reference: "compare/reference",
  ai: "compare/ai",
  patterns: "pieces/flat",
  sizes: "pieces/sizes",
  cut: "pieces/cut",
  settings: "adjust",
  revisions: "history/revisions",
  downloads: "pieces/files",
  files: "pieces/files", // Files moved into Pieces (ADR-126)
  log: "history/log",
};

/**
 * Where an address should go instead, or null when it is a page of its own. Every address the
 * studio, its mails or the handbook ever used still lands on its page (old #/desk, #/admin, …).
 */
export function redirect(hash: string, user: Viewer): string | null {
  const h = hash === "" || hash === "#" ? "#/" : hash;
  const p = h.split("?")[0].replace(/\/+$/, "") || "#";
  let m: RegExpMatchArray | null;
  if (p === "#" || p === "#/") return startPage(user);
  if ((m = p.match(/^#\/desk(?:\/([a-z0-9-]+))?$/)))
    return m[1] ? `#/work/desk/${m[1]}` : "#/work/desk";
  if ((m = p.match(/^#\/questions(?:\/(\d+))?$/)))
    return m[1] ? `#/work/questions/${m[1]}` : "#/work/questions";
  if (p === "#/catalogue") return "#/covers/all?view=cards";
  if (p === "#/models") return "#/covers/all"; // in the handbook since v1.36.0: bookmarks
  if ((m = p.match(/^#\/arrangements(?:\/([a-z0-9-]+))?$/)))
    return m[1] ? `#/covers/arrangements/${m[1]}` : "#/covers/arrangements";
  if (p === "#/learning") return "#/covers/learning";
  if (p === "#/website") return "#/shop/website";
  if (p === "#/prices") return "#/settings/costs";
  if ((m = p.match(/^#\/prices\/([a-z0-9]+)/)))
    return PRICES_TO[m[1]] ?? "#/settings/costs";
  if ((m = p.match(/^#\/shop\/([a-z0-9]+)$/)) && SHOP_TO[m[1]])
    return SHOP_TO[m[1]];
  if ((m = p.match(/^#\/settings\/([a-z0-9]+)$/)) && SETTINGS_TO[m[1]])
    return SETTINGS_TO[m[1]];
  if (p === "#/admin") return "#/settings/users";
  if ((m = p.match(/^#\/admin\/([a-z0-9]+)$/)))
    return ADMIN_TO[m[1]] ?? "#/settings/users";
  if ((m = p.match(/^#\/model\/([a-z0-9-]+)$/))) return `#/model/${m[1]}/3d`;
  if ((m = p.match(/^#\/model\/([a-z0-9-]+)\/([a-z0-9]+)$/)) && MODEL_OLD[m[2]])
    return `#/model/${m[1]}/${MODEL_OLD[m[2]]}`;
  if (p === "#/settings")
    return sectionHome("settings", user) ?? startPage(user);
  if (["#/work", "#/covers", "#/shop"].includes(p))
    return sectionHome(p.slice(2), user) ?? startPage(user);
  if (p === "#/covers/all" || p.startsWith("#/model/")) return null;
  if ((m = p.match(/^#\/(work|covers|shop)\/([a-z0-9]+)/))) {
    const s = SECTIONS.find((x) => x.id === m![1])!;
    if (!s.pages.some((x) => x.id === m![2]))
      return sectionHome(s.id, user) ?? startPage(user);
    return null;
  }
  if ((m = p.match(/^#\/settings\/([a-z0-9]+)$/)))
    return SETTINGS_IDS.includes(m[1])
      ? null
      : (sectionHome("settings", user) ?? startPage(user));
  // an address the studio never had: the person's start page, not "not for your account"
  if (
    !/^#\/(work|covers|shop|prices|settings|model|guide|account|configure|welcome)(\/|$|\?)/.test(
      p,
    )
  )
    return startPage(user);
  return null;
}

export interface Route {
  section: Section["id"] | "model" | "guide" | "account" | "other";
  page: string; // the section's page, the model's id, …
  rest: string[]; // what follows: a Desk card's id and tab, a model's tab and sub, …
  query: URLSearchParams;
}

export function parse(hash: string): Route {
  const [path, query] = hash.replace(/^#\/?/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  const head = parts[0] ?? "";
  const known = [
    "work",
    "covers",
    "shop",
    "settings",
    "model",
    "guide",
    "account",
  ];
  return {
    section: (known.includes(head) ? head : "other") as Route["section"],
    page: parts[1] ?? "",
    rest: parts.slice(2),
    query: new URLSearchParams(query ?? ""),
  };
}

// ---- links, so no page spells an address by hand ---------------------------------------------
export const deskHref = (id?: string | null, tab?: string) =>
  id
    ? `#/work/desk/${id}${tab && tab !== "check" ? `/${tab}` : ""}`
    : "#/work/desk";
export const questionHref = (n?: number | null) =>
  n ? `#/work/questions/${n}` : "#/work/questions";
export const modelHref = (id: string, tab = "3d", sub?: string) =>
  `#/model/${id}/${tab}${sub ? `/${sub}` : ""}`;
export const arrangementHref = (id?: string | null) =>
  id ? `#/covers/arrangements/${id}` : "#/covers/arrangements";
