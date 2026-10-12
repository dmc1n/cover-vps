// The studio's map (docs/plans/studio-ui.md, ADR-122): five sections, each with its own pages
// (the sub-menu), every page and tab in the address, and every old address sent to its new
// place. Pure functions, so the browser check (e2e/uinav.py) and the code agree on one table.
import type { User } from "./api";

export type Role = User["role"];
/** Who sees a page: everyone, people who may edit (not viewers), or admins. */
export type Who = "all" | "edit" | "admin";

export interface Page {
  id: string;
  label: string;
  who: Who;
  hint: string;
  sep?: boolean; // a thin separator before this page in the sub-menu
  group?: string; // a small label before this page in the sub-menu (Shop: "Tools")
}
export interface Section {
  id: "work" | "covers" | "shop" | "prices" | "settings";
  label: string;
  who: Who;
  hint: string;
  pages: Page[];
}

export const SECTIONS: Section[] = [
  {
    id: "work",
    label: "Work",
    who: "all",
    hint: "What waits for a person: the Desk, the questions, the workshop",
    pages: [
      {
        id: "desk",
        label: "Desk",
        who: "all",
        hint: "Approve or reject covers and arrangements",
      },
      {
        id: "questions",
        label: "Questions",
        who: "all",
        hint: "The owner's and the workshop's questions",
      },
      {
        id: "workshop",
        label: "Workshop",
        who: "all", // a workshop right of its own is open owner question 92
        hint: "Approved covers: their files, measured fits and the customers' answers",
      },
    ],
  },
  {
    id: "covers",
    label: "Covers",
    who: "all",
    hint: "Every cover and model, arrangements, new covers",
    pages: [
      {
        id: "all",
        label: "All covers",
        who: "all",
        hint: "Every model and its cover, as a table or as cards",
      },
      {
        id: "arrangements",
        label: "Arrangements",
        who: "all",
        hint: "Furniture placed together under one cover",
      },
      {
        id: "new",
        label: "New cover",
        who: "edit",
        hint: "From a 3D file or a drawing (PDF)",
      },
      {
        id: "learning",
        label: "Learning",
        who: "all",
        hint: "Your covers against ours: pairs of drawings and 3D",
        sep: true,
      },
      {
        id: "products",
        label: "Product list",
        who: "edit",
        hint: "The product list (Excel) linked to the drawings",
      },
    ],
  },
  {
    id: "shop",
    label: "Shop",
    who: "edit",
    hint: "Orders, requests, matches, business customers, the website",
    pages: [
      {
        id: "orders",
        label: "Orders",
        who: "admin",
        hint: "Orders from the shop",
      },
      {
        id: "requests",
        label: "Requests",
        who: "admin",
        hint: "Quotes asked in the configurator",
      },
      {
        id: "matches",
        label: "Matches",
        who: "admin",
        hint: "Which existing cover fits a request; learning mode",
      },
      {
        id: "b2b",
        label: "B2B customers",
        who: "admin",
        hint: "Companies, their logins and orders",
      },
      {
        id: "website",
        label: "Website (AI)",
        who: "edit",
        hint: "Change the website's text, preview it; an admin publishes",
        sep: true,
      },
      {
        id: "phototest",
        label: "Photo test",
        who: "admin",
        hint: "A photo suggestion step by step",
        sep: true,
        group: "Tools",
      },
    ],
  },
  {
    id: "prices",
    label: "Prices",
    who: "edit",
    hint: "Purchase prices, labour, price lists and costing",
    pages: [
      { id: "materials", label: "Materials", who: "edit", hint: "" },
      { id: "labour", label: "Labour", who: "edit", hint: "" },
      { id: "rate", label: "Exchange rate", who: "edit", hint: "" },
      {
        id: "channels",
        label: "Channels & price lists",
        who: "edit",
        hint: "",
      },
      {
        id: "import",
        label: "Import (Excel)",
        who: "admin",
        hint: "A price list from Excel as fixed prices, into the draft",
      },
      { id: "costing", label: "Costing", who: "edit", hint: "", sep: true },
      { id: "versions", label: "Versions", who: "edit", hint: "" },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    who: "admin",
    hint: "Everything that is set once: company, people, mail, keys, system",
    pages: [], // vertical tabs inside the page (SETTINGS_TABS)
  },
];

/** The Settings area's tabs, in groups (vertical on a wide screen, a row on a tablet). */
export const SETTINGS_TABS: { group: string; tabs: [string, string][] }[] = [
  {
    group: "Business",
    tabs: [
      ["company", "Company & shop"],
      ["b2b", "B2B terms"],
      ["matching", "Matching"],
    ],
  },
  {
    group: "People & work",
    tabs: [
      ["users", "Users & rights"],
      ["desk", "Desk & approval"],
      ["defaults", "Cover defaults"],
    ],
  },
  {
    group: "Connections",
    tabs: [
      ["mail", "Mail & notifications"],
      ["website", "Website & API keys"],
      ["ai", "AI & spending"],
    ],
  },
  {
    group: "Server",
    tabs: [
      ["system", "System"],
      ["activity", "Logins & audit log"],
    ],
  },
];
export const SETTINGS_IDS = SETTINGS_TABS.flatMap((g) =>
  g.tabs.map((t) => t[0]),
);

/** A cover's tabs (#/model/<id>/<tab>[/<sub>]). */
export const MODEL_TABS: [string, string][] = [
  ["3d", "3D"],
  ["pieces", "Pieces"],
  ["seams", "Seams"],
  ["adjust", "Adjust"],
  ["compare", "Compare"],
  ["history", "History"],
  ["files", "Files"],
];
/** The sub-views inside a cover's tabs: the old twelve tabs, each still one click away. */
export const MODEL_SUBS: Record<string, [string, string][]> = {
  pieces: [
    ["cut", "Cut pieces"],
    ["flat", "Flat patterns"],
    ["sizes", "Size drawing"],
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
/** A Desk card's tabs (#/work/desk/<id>/<tab>). */
export const DESK_TABS: [string, string][] = [
  ["check", "Check"],
  ["pieces", "Pieces & revisions"],
  ["correct", "Correct this cover"],
  ["history", "History"],
];

export interface Viewer {
  role: Role;
  can_approve?: boolean;
  desk_approver?: boolean;
}

export const allowed = (who: Who, user: Viewer): boolean =>
  who === "all" ||
  (who === "edit" && user.role !== "viewer") ||
  (who === "admin" && user.role === "admin");

export const visibleSections = (user: Viewer): Section[] =>
  SECTIONS.filter((s) => allowed(s.who, user)).map((s) => ({
    ...s,
    pages: s.pages.filter((p) => allowed(p.who, user)),
  }));

/** Approvers (the Desk's, or the definitive drawing's) start at Work → Desk; everyone else at
 * Covers → All covers (the owner, 11 Oct 2026: existing roles only; open question 3). */
export const startPage = (user: Viewer): string => {
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
    return v && /^#\/(work|covers|shop|prices|settings)\/[a-z0-9]+$/.test(v)
      ? v
      : null;
  } catch {
    return null; // a private window
  }
}
/** Remember the section page an admin is on (his start page next time). */
export function rememberPage(hash: string, user: Viewer): void {
  if (user.role !== "admin") return;
  const m = hash.match(/^#\/(work|covers|shop|prices|settings)\/[a-z0-9]+/);
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
  if (s.id === "settings") return "#/settings/company";
  return s.pages.length ? `#/${s.id}/${s.pages[0].id}` : null;
}

// Old Admin tabs and where they live now.
const ADMIN_TO: Record<string, string> = {
  users: "#/settings/users",
  orders: "#/shop/orders",
  b2b: "#/shop/b2b",
  matches: "#/shop/matches",
  shop: "#/settings/company",
  phototest: "#/shop/phototest",
  prices: "#/prices/materials",
  website: "#/shop/website",
  webshop: "#/shop/requests",
  requests: "#/shop/requests",
  mail: "#/settings/mail",
  sessions: "#/settings/activity",
  audit: "#/settings/activity",
  system: "#/settings/system",
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
  downloads: "files",
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
  if (p === "#/prices") return "#/prices/materials";
  if (p === "#/admin") return "#/settings/users";
  if ((m = p.match(/^#\/admin\/([a-z0-9]+)$/)))
    return ADMIN_TO[m[1]] ?? "#/settings/users";
  if ((m = p.match(/^#\/model\/([a-z0-9-]+)$/))) return `#/model/${m[1]}/3d`;
  if ((m = p.match(/^#\/model\/([a-z0-9-]+)\/([a-z0-9]+)$/)) && MODEL_OLD[m[2]])
    return `#/model/${m[1]}/${MODEL_OLD[m[2]]}`;
  if (p === "#/settings") return "#/settings/company";
  if (["#/work", "#/covers", "#/shop", "#/prices"].includes(p))
    return sectionHome(p.slice(2), user) ?? startPage(user);
  if (p === "#/covers/all" || p.startsWith("#/model/")) return null;
  if ((m = p.match(/^#\/(work|covers|shop|prices)\/([a-z0-9]+)/))) {
    const s = SECTIONS.find((x) => x.id === m![1])!;
    if (!s.pages.some((x) => x.id === m![2]))
      return sectionHome(s.id, user) ?? startPage(user);
    return null;
  }
  if ((m = p.match(/^#\/settings\/([a-z0-9]+)$/)))
    return SETTINGS_IDS.includes(m[1]) ? null : "#/settings/company";
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
    "prices",
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
