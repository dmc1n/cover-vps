// Types and calls for the cover API (apps/api/coverapi/main.py).

export type Step = "import" | "hull" | "cut" | "flatten" | "export";
export const STEPS: Step[] = ["import", "hull", "cut", "flatten", "export"];
export const STEP_LABEL: Record<Step, string> = {
  import: "Import",
  hull: "Cover surface",
  cut: "Seams and panels",
  flatten: "Flat patterns",
  export: "Cut pieces",
};

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
  panels: { name: string; change: string; before_mm?: number[]; after_mm?: number[] }[];
  settings: { key: string; before: unknown; after: unknown }[];
}

export interface ModelDetail extends ModelBrief {
  hull?: { area_m2: number; hem: { length_mm: number; height_mm: number } } | null;
  cut?: {
    panels: { name: string; region: string; area_m2: number }[];
    seams: { id: string; kind: string; length_mm: number }[];
    hem_length_mm: number;
    skirt_height_mm?: number[];
  };
  pattern?: {
    summary: { panels: number; max_stretch_pct: number; fabric_area_m2: number };
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
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      if (body.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  return (await r.json()) as T;
}

export const api = {
  models: () => fetch("/api/models").then((r) => json<ModelBrief[]>(r)),
  model: (id: string) => fetch(`/api/models/${id}`).then((r) => json<ModelDetail>(r)),
  job: (id: string) => fetch(`/api/jobs/${id}`).then((r) => json<Job>(r)),
  specs: () => fetch("/api/parameters").then((r) => json<ParamSpec[]>(r)),
  params: (id: string) => fetch(`/api/models/${id}/parameters`).then((r) => json<ModelParams>(r)),
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
  setInfo: (id: string, info: Partial<Pick<ModelBrief, "family" | "status" | "tags" | "notes">>) =>
    fetch(`/api/models/${id}/info`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(info),
    }).then((r) => json<Pick<ModelBrief, "family" | "status" | "tags" | "notes">>(r)),
  compare: (id: string, a: number, b: number) =>
    fetch(`/api/models/${id}/compare?a=${a}&b=${b}`).then((r) => json<Diff>(r)),
  batch: (model_ids: string[], steps: Step[] | null) =>
    fetch("/api/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_ids, steps }),
    }).then((r) => json<{ jobs: Job[] }>(r)),
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

export const fileUrl = (id: string, name: string) => `/api/models/${id}/files/${name}`;

export const cm = (mm: number) => `${(mm / 10).toFixed(1)} cm`;

export const revisionUrl = (id: string, n: number, name: string) => `/api/models/${id}/revisions/${n}/${name}`;
