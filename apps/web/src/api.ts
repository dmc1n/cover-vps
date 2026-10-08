// Types and calls for the cover API (apps/api/coverapi/main.py).

export type Step =
  | "import"
  | "hull"
  | "cut"
  | "flatten"
  | "export"
  | "improve"
  | "ai"
  | "rain"
  | "drape"
  | "drawing-build";
export const STEPS: Step[] = ["import", "hull", "cut", "flatten", "export"];
export const STEP_LABEL: Record<Step, string> = {
  import: "Import",
  hull: "Cover surface",
  cut: "Seams and panels",
  flatten: "Flat patterns",
  export: "Cut pieces",
  improve: "Seams added by the program",
  ai: "AI advice",
  rain: "Rain simulation",
  drape: "Drape simulation",
  "drawing-build": "Cover from the drawing",
};

/** The drape simulation (drape.json, ADR-056): the sewn cover falling over the furniture. */
export interface Drape {
  engine?: string;
  fold_area_m2: number;
  fold_share_pct: number;
  max_fold_deg: number;
  max_stretch_pct: number;
  tight_share_pct: number;
  max_sag_mm: number;
  touching_share_pct: number;
  seconds_simulated: number;
  run_s: number;
  points: number;
  frames: number;
  faces: number[][];
  frame_box_mm: [number[], number[]];
  points_per_frame: number;
  ai?: {
    verdict?: string;
    summary?: string;
    problems?: string[];
    advice?: string[];
    error?: string;
  };
  wet?: {
    ponds: number;
    pond_volume_l: number;
    pond_area_m2: number;
    deepest_mm: number;
    flat_area_m2: number;
    growing_ponds: number;
    dry: boolean;
    pond_points_pct?: number;
    flat_points_pct?: number;
    stream_points_pct?: number;
    ai?: string | null;
  };
}

/** The rain simulation (rain.json, ADR-049). */
export interface Rain {
  cover_area_m2: number;
  ponds: {
    area_m2: number;
    volume_l: number;
    max_depth_mm: number;
    span_mm: number;
    volume_with_sag_l: number;
    keeps_growing: boolean;
    centre_mm: number[];
  }[];
  pond_area_m2: number;
  pond_volume_l: number;
  flat_area_m2: number;
  growing_ponds: number;
  exits: Record<string, number>;
  seams_along: { seam: string; run_mm: number }[];
  dry: boolean;
  drops: { path: number[][]; ends: string }[];
  ai?: {
    verdict?: string;
    summary?: string;
    risks?: string[];
    suggestions?: string[];
    error?: string;
  };
}

export type Status = "draft" | "checked" | "production";

export interface Revision {
  number: number;
  time: number;
  parameter_hash: string;
  trial: string[];
  status: Status;
  panels: number;
  max_stretch_pct: number;
  roll_length_mm: number | null;
  warnings: number;
}

export interface ModelBrief {
  id: string;
  family: string | null;
  category?: string | null;
  status: Status;
  tags: string[];
  notes: string;
  steps_done: Step[];
  files: string[];
  size_mm?: number[];
  source?: string;
  panels?: number;
  max_stretch_pct?: number;
  warnings: string[];
  grade: "ready" | "check" | "failed";
  reasons: string[];
  roll_length_mm?: number | null;
  kind?: Kind | null;
  approval?: Approval | null;
  dxf_ok?: boolean; // the cutting table's DXF: only for an approved cover (ADR-079)
  desk_status?: string;
}

/** What an uploaded file is: the furniture, or only the cover surface (kind.json). */
export interface Kind {
  guess: "product" | "cover" | null;
  sure: boolean;
  measures?: { sides_closed: number; floor_share: number; skin_ratio: number };
  reasons?: string[];
  confirmed: boolean;
  kind: "product" | "cover" | null;
}

export interface JobStep {
  name: Step;
  status: "waiting" | "running" | "done" | "failed";
  log: string;
  started?: number;
  finished?: number;
}

export interface Job {
  id: string;
  model_id: string;
  status: "queued" | "running" | "done" | "failed";
  steps: JobStep[];
  error?: string;
  trial: Record<string, unknown>;
  created: number;
}

/** What the program read from a drawing (drawing_read.json, ADR-081). */
export interface DrawingRead {
  code: string;
  status: "built" | "needs a person";
  reader: "outline" | "views" | "plan-profile" | "ai" | null;
  reasons: string[];
  pieces?: number;
  vents?: number;
  features?: { vents_total?: number | null; vents_from?: string | null };
  views?: { scale_from: string; views: { kind: string; size_cm: number[] }[] };
  solid?: { how: string[]; fits_3d_view: number };
  outline?: {
    fits_3d_view: number | null;
    conflicts: { size: string; written_cm: number; outline_gives_cm: number }[];
  };
  job?: { id: string; status: string; error?: string } | null;
}

export interface PatternPanel {
  id: string;
  name: string;
  flat_width_mm: number;
  flat_length_mm: number;
  stretch: { quantile_pct: number; max_pct: number };
  fits_roll: boolean;
}

export interface Piece {
  id: string;
  name: string;
  quantity: number;
  size_mm: number[];
  area_m2: number;
  note: string;
}

export interface Diff {
  panels: {
    name: string;
    change: string;
    before_mm?: number[];
    after_mm?: number[];
  }[];
  settings: { key: string; before: unknown; after: unknown }[];
}

export interface ModelDetail extends ModelBrief {
  hull?: {
    area_m2: number;
    hem: { length_mm: number; height_mm: number };
  } | null;
  cut?: {
    panels: { name: string; region: string; area_m2: number }[];
    seams: { id: string; kind: string; length_mm: number }[];
    hem_length_mm: number;
    skirt_height_mm?: number[];
  };
  pattern?: {
    summary: {
      panels: number;
      max_stretch_pct: number;
      fabric_area_m2: number;
    };
    panels: PatternPanel[];
    parameter_hash: string;
  };
  finished?: { pieces: Piece[]; sheet?: { roll_length_mm: number } };
  diff?: Diff | null;
  job?: Job | null;
  revisions?: Revision[];
}

export type Scalar = string | number | boolean;

export interface ParamSpec {
  key: string;
  group: string;
  default: Scalar;
  kind: "bool" | "int" | "number" | "choice" | "str";
  choices: string[] | null;
  comment: string;
  to_confirm: boolean;
}

export interface ModelParams {
  values: Record<string, Scalar>;
  sources: Record<string, string>;
}

async function json<T>(r: Response): Promise<T> {
  if (r.status === 401 && !r.url.includes("/api/auth/")) {
    window.dispatchEvent(new Event("login-needed")); // the session ended: show the login
  }
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      if (body.detail)
        msg =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

export const api = {
  models: () => fetch("/api/models").then((r) => json<ModelBrief[]>(r)),
  model: (id: string) =>
    fetch(`/api/models/${id}`).then((r) => json<ModelDetail>(r)),
  job: (id: string) => fetch(`/api/jobs/${id}`).then((r) => json<Job>(r)),
  specs: () => fetch("/api/parameters").then((r) => json<ParamSpec[]>(r)),
  params: (id: string) =>
    fetch(`/api/models/${id}/parameters`).then((r) => json<ModelParams>(r)),
  saveParams: (id: string, values: Record<string, Scalar>) =>
    fetch(`/api/models/${id}/parameters`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    }).then((r) => json<ModelParams>(r)),
  run: (id: string, steps: Step[] | null, trial: Record<string, Scalar>) =>
    fetch(`/api/models/${id}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps, trial }),
    }).then((r) => json<Job>(r)),
  families: () => fetch("/api/families").then((r) => json<string[]>(r)),
  categories: () =>
    fetch("/api/categories").then((r) =>
      json<
        {
          group: string;
          category: string;
          name: string;
          on_suns_site: boolean;
        }[]
      >(r),
    ),
  setInfo: (
    id: string,
    info: Partial<
      Pick<ModelBrief, "family" | "category" | "status" | "tags" | "notes">
    >,
  ) =>
    fetch(`/api/models/${id}/info`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(info),
    }).then((r) =>
      json<Pick<ModelBrief, "family" | "status" | "tags" | "notes">>(r),
    ),
  compare: (id: string, a: number, b: number) =>
    fetch(`/api/models/${id}/compare?a=${a}&b=${b}`).then((r) => json<Diff>(r)),
  batch: (model_ids: string[], steps: Step[] | null) =>
    fetch("/api/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_ids, steps }),
    }).then((r) => json<{ jobs: Job[] }>(r)),
  setKind: (id: string, kind: "product" | "cover") =>
    fetch(`/api/models/${id}/kind`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind }),
    }).then((r) => json<{ kind: Kind; job: Job | null }>(r)),
  /** Route A: a drawing (PDF) read by the program and built as a cover (ADR-081). */
  uploadDrawing: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch("/api/models/drawing", { method: "POST", body: form }).then(
      (r) => json<{ model_id: string; code: string; job: Job }>(r),
    );
  },
  rebuildDrawing: (id: string) =>
    fetch(`/api/models/${id}/drawing`, { method: "POST" }).then((r) =>
      json<{ model_id: string; job: Job }>(r),
    ),
  aiReadDrawing: (id: string) =>
    fetch(`/api/models/${id}/drawing/ai`, { method: "POST" }).then((r) =>
      json<{ model_id: string; job: Job }>(r),
    ),
  drawingRead: (id: string) =>
    fetch(`/api/models/${id}/drawing`).then((r) => json<DrawingRead>(r)),
  upload: (file: File, units: string, up: string) => {
    const form = new FormData();
    form.append("file", file);
    if (units) form.append("units", units);
    if (up) form.append("up", up);
    return fetch("/api/models", { method: "POST", body: form }).then((r) =>
      json<{ model_id: string; job: Job }>(r),
    );
  },
};

export const fileUrl = (id: string, name: string) =>
  `/api/models/${id}/files/${name}`;

export const cm = (mm: number) => `${(mm / 10).toFixed(1)} cm`;

export const revisionUrl = (id: string, n: number, name: string) =>
  `/api/models/${id}/revisions/${n}/${name}`;

export interface AiReview {
  time: number;
  model: string;
  summary: string;
  target_pieces: number | null;
  pieces_now: number;
  problems: string[];
  suggestions: { action: string; value: number | null; reason: string }[];
  applied: { action: string; value: number | null }[];
}

export const ACTION_LABEL: Record<string, string> = {
  drop_program_seams: "Remove the seams the program added",
  skirt_one_piece: "Skirt in one piece",
  no_walls: "No separate wall pieces",
  smoother_surface: "Calmer cover surface (15 mm, bridge 15 cm, smooth)",
  set_skirt_height: "Skirt at this height",
};

// ---- logins, the admin page and approvals (ADR-047)

export interface User {
  id: number;
  username: string;
  name: string;
  email: string | null;
  role: "admin" | "editor" | "viewer";
  can_approve: boolean;
  active: boolean;
  last_login: number | null;
  has_password: boolean;
  invited_until?: number | null;
}

export interface Approval {
  approved_by: string;
  name: string;
  time: number;
  revision: number | null;
  note: string;
  valid: boolean;
}

export interface MailSettings {
  host?: string;
  port?: number;
  security?: string;
  username?: string;
  sender?: string;
  password_set?: boolean;
}

const send = (method: string, url: string, body?: unknown) =>
  fetch(url, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

export const auth = {
  me: () =>
    fetch("/api/auth/me").then((r) => json<{ user: User; auth: boolean }>(r)),
  login: (username: string, password: string) =>
    send("POST", "/api/auth/login", { username, password }).then((r) =>
      json<{
        user?: User;
        two_factor?: boolean;
        challenge?: string;
        sent_to?: string;
      }>(r),
    ),
  verify: (challenge: string, code: string, remember: boolean) =>
    send("POST", "/api/auth/verify", { challenge, code, remember }).then((r) =>
      json<{ user: User }>(r),
    ),
  logout: () =>
    send("POST", "/api/auth/logout").then((r) => json<{ ok: boolean }>(r)),
  invite: (token: string) =>
    fetch(`/api/auth/invite/${token}`).then((r) =>
      json<{ username: string; name: string }>(r),
    ),
  changePassword: (old: string, nw: string) =>
    send("POST", "/api/auth/password", { old, new: nw }).then((r) =>
      json<{ ok: boolean }>(r),
    ),
  setPassword: (token: string, password: string) =>
    send("POST", `/api/auth/invite/${token}`, { password }).then((r) =>
      json<{ user: User }>(r),
    ),
};

export interface Invite {
  link: string | null;
  mailed: boolean;
  mail_problem: string | null;
  days?: number;
}

export interface CustomerRequest {
  id: number;
  created: number;
  name: string;
  email: string;
  phone: string | null;
  note: string | null;
  source: string;
  status: string;
  quote: {
    product: string;
    shape: string;
    sizes_cm: Record<string, number>;
    colour: string;
    pieces: unknown[];
    fabric_m2: number;
    roll_m: number;
    price: {
      cost_eur: number;
      sale_eur: number;
      labour_minutes: number;
      placeholder_prices: boolean;
    };
  } | null;
}
export interface WebshopSettings {
  keys: { name: string; created: number }[];
  embed_origins: string[];
  request_email: string;
}

export const shopAdmin = {
  settings: () =>
    fetch("/api/admin/shop/settings").then((r) =>
      json<{ settings: Record<string, unknown>; missing: string[] }>(r),
    ),
  saveSettings: (body: Record<string, unknown>) =>
    send("PUT", "/api/admin/shop/settings", body).then((r) =>
      json<{ settings: Record<string, unknown>; missing: string[] }>(r),
    ),
  cms: () =>
    fetch("/api/admin/cms").then((r) =>
      json<{
        draft: Record<string, unknown>;
        live: Record<string, unknown>;
        history: string[];
        preview: string;
      }>(r),
    ),
  command: (text: string) =>
    send("POST", "/api/admin/cms/command", { text }).then((r) =>
      json<{ summary: string; changes: { path: string; value: unknown }[] }>(r),
    ),
  publish: () =>
    send("POST", "/api/admin/cms/publish").then((r) =>
      json<{ previous_version: string }>(r),
    ),
  discard: () =>
    send("POST", "/api/admin/cms/discard").then((r) => json<unknown>(r)),
  restore: (v: string) =>
    send("POST", `/api/admin/cms/restore/${v}`).then((r) => json<unknown>(r)),
  orders: () =>
    fetch("/api/admin/orders").then((r) =>
      json<{ orders: ShopOrder[]; statuses: string[] }>(r),
    ),
  setStatus: (id: number, status: string) =>
    send("PUT", `/api/admin/orders/${id}`, { status }).then((r) =>
      json<unknown>(r),
    ),
  produce: (id: number) =>
    send("POST", `/api/admin/orders/${id}/produce`).then((r) =>
      json<{ model_id: string }>(r),
    ),
  linkKey: () =>
    send("POST", "/api/admin/shop/link-key").then((r) =>
      json<{ key: string; note: string }>(r),
    ),
  translate: () =>
    send("POST", "/api/admin/cms/translate").then((r) =>
      json<{ translated: number; texts: number; languages: string[] }>(r),
    ),
  matches: () =>
    fetch("/api/admin/matches").then((r) =>
      json<{ requests: MatchRequest[]; mode: string }>(r),
    ),
  answerMatch: (id: number, chosen: string, note: string) =>
    send("PUT", `/api/admin/matches/${id}`, { chosen, note }).then((r) =>
      json<{ changed: boolean }>(r),
    ),
  learning: () =>
    fetch("/api/admin/learning").then((r) =>
      json<{
        bands: LearningBand[];
        threshold_pct: number;
        choice_pct: number;
        mode: string;
      }>(r),
    ),
  feedback: () =>
    fetch("/api/admin/feedback").then((r) =>
      json<{ feedback: FitFeedback[] }>(r),
    ),
};

// ADR-064: a customer's sizes against our range, a colleague's answer, and what we learn.
export interface MatchCandidate {
  model_id: string;
  name: string;
  size_cm: number[];
  score_pct: number;
  sizes: { size: string; difference_cm: number; verdict: string }[];
}
export interface MatchRequest {
  id: number;
  created: number;
  email: string | null;
  name: string | null;
  lang: string | null;
  product: string;
  given: Record<string, number | boolean>;
  result: {
    customer_cm: number[];
    matches: MatchCandidate[];
    decision: string;
    chosen_entry?: MatchCandidate;
  };
  best_model: string | null;
  best_pct: number | null;
  decision: string;
  mode: string;
  status: string;
  chosen: string | null;
  chosen_by: string | null;
  changed: number | null;
  note: string | null;
}
export interface LearningBand {
  band: string;
  requests: number;
  answered_by_staff: number;
  changed: number;
  custom_chosen: number;
  orders: number;
  fit_answers: number;
  fit_avg: number | null;
  returns: number;
}
export interface FitFeedback {
  id: number;
  created: number;
  order_id: number;
  score: number;
  comment: string | null;
  photo: string | null;
}

export interface ShopOrder {
  id: number;
  created: number;
  status: string;
  email: string;
  total_eur: number;
  model_id: string | null;
  token: string;
  data: {
    customer: Record<string, string | boolean>;
    shipping_eur: number;
    /** a line of a B2B order on account (ADR-101) */
    b2b?: { order: number; po: string; qty: number; company: string };
    quote: {
      input: { support: string };
      quote: {
        product: string;
        colour: string;
        sizes_cm: Record<string, number>;
      };
    };
  };
}

export const admin = {
  requests: () =>
    fetch("/api/admin/requests").then((r) =>
      json<{ requests: CustomerRequest[] }>(r),
    ),
  webshop: () =>
    fetch("/api/admin/webshop").then((r) => json<WebshopSettings>(r)),
  setWebshop: (body: Partial<WebshopSettings> & { revoke?: string }) =>
    send("PUT", "/api/admin/webshop", body).then((r) =>
      json<WebshopSettings>(r),
    ),
  newKey: (name: string) =>
    send("POST", "/api/admin/webshop/keys", { name }).then((r) =>
      json<{ name: string; key: string; note: string }>(r),
    ),
  users: () =>
    fetch("/api/admin/users").then((r) =>
      json<{ users: User[]; roles: string[] }>(r),
    ),
  addUser: (
    u: Partial<User> & {
      username: string;
      send_invite?: boolean;
      note?: string;
    },
  ) =>
    send("POST", "/api/admin/users", u).then((r) =>
      json<{ user: User } & Invite>(r),
    ),
  changeUser: (id: number, changes: Partial<User>) =>
    send("PUT", `/api/admin/users/${id}`, changes).then((r) =>
      json<{ user: User }>(r),
    ),
  invite: (id: number, note = "") =>
    send("POST", `/api/admin/users/${id}/invite`, { note }).then((r) =>
      json<Invite>(r),
    ),
  inviteAll: (note = "") =>
    send("POST", "/api/admin/users/invite-all", { note }).then((r) =>
      json<{
        invited: {
          name: string;
          email: string;
          mailed: boolean;
          mail_problem: string | null;
        }[];
      }>(r),
    ),
  sessions: () =>
    fetch("/api/admin/sessions").then((r) =>
      json<{
        sessions: {
          username: string;
          created: number;
          expires: number;
          address: string;
        }[];
      }>(r),
    ),
  audit: () =>
    fetch("/api/admin/audit").then((r) =>
      json<{
        audit: {
          time: number;
          username: string | null;
          action: string;
          detail: string | null;
        }[];
      }>(r),
    ),
  mail: () =>
    fetch("/api/admin/mail").then((r) =>
      json<{ mail: MailSettings; public_url: string; two_factor: boolean }>(r),
    ),
  twoFactor: (on: boolean) =>
    send("PUT", "/api/admin/two-factor", { on }).then((r) =>
      json<{ two_factor: boolean }>(r),
    ),
  saveMail: (m: MailSettings & { password?: string }) =>
    send("PUT", "/api/admin/mail", m).then((r) =>
      json<{ mail: MailSettings }>(r),
    ),
  testMail: (to: string) =>
    send("POST", "/api/admin/mail/test", { to }).then((r) =>
      json<{ ok: boolean }>(r),
    ),
  publicUrl: (url: string) =>
    send("PUT", "/api/admin/public-url", { url }).then((r) =>
      json<{ public_url: string }>(r),
    ),
  system: () =>
    fetch("/api/admin/system").then((r) => json<Record<string, unknown>>(r)),
  alertEmail: (to: string) =>
    send("PUT", "/api/admin/alert-email", { to }).then((r) =>
      json<{ alert_email: string }>(r),
    ),
};

export const approvals = {
  approve: (id: string, note: string) =>
    send("POST", `/api/models/${id}/approve`, { note }).then((r) =>
      json<{ approval: Approval }>(r),
    ),
  withdraw: (id: string) =>
    send("DELETE", `/api/models/${id}/approve`).then((r) => json<unknown>(r)),
  ask: (id: string) =>
    send("POST", `/api/models/${id}/approval-request`).then((r) =>
      json<{ mailed: string[]; not_mailed: string[] }>(r),
    ),
};

// ---- prices and costing (ADR-098) ---------------------------------------------------------------

export type Currency = "EUR" | "IDR";
export interface Fabric {
  code: string;
  name: string;
  colours: string;
  price: number;
  currency: Currency;
  roll_width_mm: number;
  waste_pct: number;
}
export interface Component {
  code: string;
  name: string;
  per: string;
  price: number;
  currency: Currency;
}
export interface Operation {
  code: string;
  name: string;
  per: string;
  minutes: number;
}
export interface Money {
  amount: number;
  currency: Currency;
}
export interface Channel {
  name: string;
  method: "markup" | "margin";
  pct: number;
  base: "landed" | "cost";
  rounding: string;
  vat_pct: number;
  show_vat: boolean;
  extras: {
    shipping: Money;
    duties: { mode: "pct" | "fixed"; value: number; currency?: Currency };
    packaging: Money;
  };
  fixed: Record<string, number>;
}
export type ChannelKey = "b2c" | "b2b";
export interface PriceSet {
  format_version: number;
  indicative: boolean;
  exchange: { idr_per_eur: number; date: string; note: string };
  fabrics: Fabric[];
  components: Component[];
  labour: { rate: number; currency: Currency; operations: Operation[] };
  channels: Record<ChannelKey, Channel>;
  /** fields the owner confirmed at their documented value (no longer "placeholder") */
  confirmed?: string[];
}
export interface PriceVersion {
  version: number;
  created: number;
  username: string;
  note: string;
  from_version: number | null;
  data: PriceSet;
}
export interface PricesState {
  published: PriceVersion | null;
  current: PriceSet;
  using_defaults: boolean;
  draft: { data: PriceSet; by: string; time: number } | null;
  draft_errors: string[];
  defaults: PriceSet;
  can_edit: boolean;
  /** ids of the fields still at their "to confirm" default (costing.FIELD_KEYS) */
  placeholders: string[];
  placeholder_total: number;
  choices: {
    per: string[];
    per_label: Record<string, string>;
    currencies: Currency[];
    roundings: string[];
    methods: string[];
    bases: string[];
    duty_modes: string[];
  };
}
export interface PriceMove {
  key: string;
  name: string;
  kind: string;
  before: { cost: number; b2c: number; b2b: number };
  after: { cost: number; b2c: number; b2b: number };
  delta_b2c: number;
}
export interface CostLine {
  section: string;
  code: string;
  name: string;
  qty: number;
  unit: string;
  unit_price: number;
  currency: Currency;
  eur: number;
  idr: number;
  note: string;
}
export interface ChannelPrice {
  name: string;
  extras: { code: string; name: string; eur: number; idr: number }[];
  extras_eur: number;
  landed_eur: number;
  method: string;
  pct: number;
  base: string;
  show_vat: boolean;
  vat_pct: number;
  net_eur: number;
  vat_eur: number;
  gross_eur: number;
  shown_eur: number;
  margin_eur: number;
  margin_pct: number;
  fixed: boolean;
  accessories: Record<string, { count: number; shown_eur: number }>;
}
export interface Costing {
  name: string;
  kind: string;
  model?: string;
  product?: string;
  sizes_cm?: Record<string, unknown>;
  facts: Record<string, number>;
  fabric: { code: string; name: string };
  lines: CostLine[];
  fabric_eur: number;
  components_eur: number;
  labour_eur: number;
  labour_minutes: number;
  cost_eur: number;
  cost_idr: number;
  channels: Record<string, ChannelPrice>;
  exchange: { idr_per_eur: number; date: string };
  indicative: boolean;
}
export interface CostingProducts {
  models: { id: string; name: string; kind: string }[];
  /** a representative cover for the live examples */
  example: string | null;
  configurator: {
    product: string;
    label: string;
    fields: {
      key: string;
      default: number | boolean;
      min: number | null;
      max: number | null;
    }[];
  }[];
}

export interface PriceCheck {
  errors: string[];
  placeholders: string[];
  placeholder_total: number;
  costing: Costing | null;
  costing_error?: string;
}

export const prices = {
  state: () => fetch("/api/prices").then((r) => json<PricesState>(r)),
  saveDraft: (data: PriceSet) =>
    send("PUT", "/api/prices/draft", { data }).then((r) =>
      json<{ draft: PricesState["draft"]; errors: string[] }>(r),
    ),
  discard: () =>
    send("DELETE", "/api/prices/draft").then((r) => json<unknown>(r)),
  preview: (data?: PriceSet) =>
    send("POST", "/api/prices/preview", data ? { data } : {}).then((r) =>
      json<{
        errors: string[];
        rows: PriceMove[];
        changed: number;
        total: number;
      }>(r),
    ),
  publish: (note: string) =>
    send("POST", "/api/prices/publish", { note }).then((r) =>
      json<{ version: number; prices_changed: number }>(r),
    ),
  versions: () =>
    fetch("/api/prices/versions").then((r) =>
      json<{ versions: PriceVersion[] }>(r),
    ),
  rollback: (v: number) =>
    send("POST", `/api/prices/rollback/${v}`).then((r) =>
      json<{ version: number }>(r),
    ),
  products: () =>
    fetch("/api/prices/products").then((r) => json<CostingProducts>(r)),
  /** the page's unsaved numbers: errors, placeholders and one cover's costing under them */
  check: (
    data: PriceSet,
    what: { model?: string; product?: string; sizes?: unknown },
  ) =>
    send("POST", "/api/prices/check", { data, ...what }).then((r) =>
      json<PriceCheck>(r),
    ),
  costing: (q: Record<string, string>) =>
    fetch(`/api/prices/costing?${new URLSearchParams(q)}`).then((r) =>
      json<Costing>(r),
    ),
};
