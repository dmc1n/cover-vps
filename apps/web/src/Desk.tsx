// The drawing desk (ADR-079): the AI sorts, people approve. A queue of every drawing cover in
// order of need, one card per cover (the drawing beside our cover, what the program read, what
// the AIs say), and the actions: approve, reject with a reason, produced, fit after sewing.
// Keys: j / k next / previous, a approve, r reject, c comment, p produced, u undo.
// The card in four tabs, each in the address (#/work/desk/<id>/<tab>, ADR-122): Check (the
// drawing beside our cover, what the program read, the AIs), Pieces & revisions, Correct this
// cover, History; the decision bar stays at the bottom of the screen.
// A reject or a comment takes pictures, marked in red (DeskPictures.tsx, ADR-096).
// Arrangements (ADR-115): the series ARR; their card shows the members, their places and the
// cover's plan from above instead of a drawing; their maker sends them, Rens or Wout approve.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ModelDetail } from "./api";
import { Viewer } from "./Viewer";
import { Corrections, RulesBar } from "./DeskCorrect";
import {
  MeasuredForm,
  MeasuredSummary,
  type MeasuredRow,
} from "./DeskMeasured";
import { ProductsPanel, type ProductList } from "./DeskProducts";
import {
  PictureThumbs,
  PictureTray,
  uploadPictures,
  type Pending,
} from "./DeskPictures";
import {
  Icon,
  IconButton,
  IconLink,
  Info,
  StatusChip,
  type IconName,
} from "./icons";
import { useSession } from "./Session";
import {
  arrangementHref,
  DESK_TABS,
  deskHref,
  isWorkshop,
  modelHref,
} from "./nav";
import {
  ArrangementPlan,
  FOOTPRINT_NAMES,
  MEMBER_COLOURS,
} from "./ArrangementPlan";

type Scores = {
  gemini: number | null;
  deepseek: number | null;
  avg: number | null;
};
interface Item {
  id: string;
  code: string;
  drawing: boolean;
  arrangement?: boolean;
  sent?: { by: string; time: number } | null; // an arrangement sent to the Desk (ADR-115)
  status: string;
  outcome: string | null;
  scores: Scores;
  tags: string[];
  second_round?: string | null;
  catalogue: string;
  pieces: number;
  vents: number;
  products?: string[];
  has_picture: boolean;
  last: { action: string; by: string; time: number } | null;
  /** a shop order's cover sent to production: first in the queue, one click approves it
   * (ADR-128); `built`: its cutting file exists */
  order?: { order: number; b2b: boolean; by: string; time: number } | null;
  built?: boolean;
  /** the last remark a person left (reject, comment, fit) and the studio's last change: a
   * remark newer than the change waits for us (Rens, 14 Oct 2026; desk_open_remarks.py) */
  last_remark_time?: number | null;
  last_change_time?: number | null;
  open_remark?: boolean;
}
interface Spend {
  month_eur: number;
  budget_eur: number;
  pct: number;
  calls: number;
}
interface Queue {
  items: Item[];
  counts: Record<string, number>;
  avg_score: number | null;
  spend: Spend | null;
  can_approve: boolean;
  /** the workshop login: a fit, a comment, pictures; never approve (ADR-128) */
  can_note?: boolean;
  reasons: string[];
  pictures_max?: number;
}
interface Verdict {
  same?: boolean;
  score?: number;
  summary?: string;
  differences?: string[];
}
interface Hist {
  action: string;
  by: string;
  time: number;
  reasons?: string[];
  text?: string;
  done?: boolean;
  fits?: boolean;
  note?: string;
  n?: number;
  undid?: string;
  pictures?: string[];
  measured?: MeasuredRow[]; // with a fit: measured on the sewn cover (ADR-111)
}
interface Card extends Item {
  desk: {
    status: string;
    approved?: { by: string; time: number };
    produced?: { by: string; time: number };
    rejected?: { by: string; time: number; reasons: string[]; text: string };
    fit?: { fits: boolean; note: string; by: string; time: number };
    preferred_revision?: number;
    history: Hist[];
  };
  /** something in the history an undo can take back (the server decides) */
  can_undo?: boolean;
  check: {
    outcome?: string;
    gemini?: Verdict;
    gemini_second?: Verdict;
    deepseek?: Verdict;
    source?: string;
  };
  read: Record<string, unknown>;
  notes: string;
  pieces_list: {
    name: string;
    quantity: number;
    size_mm: number[];
    area_m2?: number;
  }[];
  revisions: {
    number: number;
    time: number;
    panels: number;
    roll_length_mm?: number;
  }[];
  product_list?: ProductList;
  pages: number;
  dxf_ok: boolean;
  arrangement_info?: Arrangement | null;
}
/** An arrangement on its card (ADR-115): its members, their places, the cover's plan. */
interface Arrangement {
  name: string;
  gap_mm: number;
  size_mm?: number[];
  time?: number;
  stale: string[];
  plan: {
    footprint: string;
    outline_mm: number[][];
    rects_mm: number[][][];
    size_mm: number[];
  } | null;
  members: {
    model_id: string;
    code: string;
    x_mm: number;
    y_mm: number;
    rot_deg: number;
    mirror: boolean;
    size_mm?: number[] | null;
    exists: boolean;
    has_picture: boolean;
    stale: boolean;
  }[];
}

const STATUS_LABEL: Record<string, string> = {
  new: "New",
  "ai-checked": "AI checked",
  rejected: "Rejected",
  approved: "Approved",
  produced: "Produced",
};
const OUTCOME_LABEL: Record<string, string> = {
  "agreed: same": "AIs: same",
  "agreed: different": "AIs: different",
  "person to check": "AIs disagree",
  "check failed": "check failed",
};
// the drawings' series, the SUNS catalogue (owner, 7 Oct 2026: every approval at the Desk) and
// the arrangements (owner, 9 Oct 2026: "that must be the workflow"; ADR-115)
const SERIES = ["C", "S", "D", "L", "R", "T", "U", "SUNS", "ARR"];
const SERIES_TITLE: Record<string, string> = {
  SUNS: "The SUNS catalogue",
  ARR: "Arrangements: furniture placed together under one cover",
};
// an arrangement is not checked by an AI: sent by its maker, it waits for a person
const ARR_LABEL: Record<string, string> = {
  new: "Not sent yet",
  "ai-checked": "Ready for approval",
};
const statusLabel = (status: string, arrangement?: boolean) =>
  (arrangement && ARR_LABEL[status]) || STATUS_LABEL[status] || status;
const cm = (mm: number) => `${(mm / 10).toFixed(0)}`;
// the list's order: what needs a person first (the server's), or by code, product, status, score
const SORTS: Record<string, string> = {
  need: "Needs a person first",
  code: "Code",
  product: "Product",
  status: "Status",
  score: "AI score (low first)",
};
const natural = (a: string, b: string) =>
  a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
const STATUS_ORDER = ["new", "ai-checked", "rejected", "approved", "produced"];
function sortItems(items: Item[], by: string): Item[] {
  // a shop order waiting for its quick approval stays on top, whatever the sort (ADR-128)
  const orders = items.filter((i) => i.order);
  const rest = items.filter((i) => !i.order);
  return [...orders, ...sortRest(rest, by)];
}
function sortRest(items: Item[], by: string): Item[] {
  if (by === "need") return items;
  const out = [...items];
  const prod = (i: Item) => i.products?.[0] ?? "";
  out.sort((a, b) => {
    if (by === "product") {
      // covers without a product last
      if (!prod(a) !== !prod(b)) return prod(a) ? -1 : 1;
      return natural(prod(a), prod(b)) || natural(a.code, b.code);
    }
    if (by === "status")
      return (
        STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
        natural(a.code, b.code)
      );
    if (by === "score")
      return (
        (a.scores.avg ?? Infinity) - (b.scores.avg ?? Infinity) ||
        natural(a.code, b.code)
      );
    return natural(a.code, b.code);
  });
  return out;
}
const when = (t?: number) =>
  t
    ? new Date(t * 1000).toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
const tone = (s: number | null | undefined) =>
  s == null ? "none" : s >= 80 ? "good" : s >= 60 ? "mid" : "bad";

/** A refusal or a failure with the server's own reason (409, 400, 403...). */
export class DeskError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function getJSON<T>(url: string, body?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(url, {
      method: body === undefined ? "GET" : "POST",
      headers:
        body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    throw new DeskError(0, `no connection to the studio (${String(e)})`);
  }
  if (r.status === 401) window.dispatchEvent(new Event("login-needed"));
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : data.detail
          ? JSON.stringify(data.detail)
          : r.statusText || "no reason given";
    throw new DeskError(r.status, detail);
  }
  return data as T;
}

/** What a failed action says on the screen: never silent (14 Oct 2026). */
export function failText(what: string, e: unknown): string {
  const err = e as DeskError;
  const why = String(err?.message ?? e);
  if (err?.status === 409 || err?.status === 400)
    return `${what} refused: ${why}`;
  if (err?.status === 403) return `${what} not allowed: ${why}`;
  if (err?.status === 401) return `${what}: log in again (${why})`;
  if (err?.status) return `${what} failed (${err.status}): ${why}`;
  return `${what} failed: ${why}`;
}

const day = (t?: number | null) =>
  t
    ? new Date(t * 1000).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
      })
    : "";

/** "Changed 12 Oct" or "Not changed yet": has the studio changed the cover since the last
 * remark a person left? (Rens, 14 Oct 2026) Nothing when nobody left a remark. */
function RemarkChip({ item }: { item: Item }) {
  if (!item.last_remark_time) return null;
  if (item.open_remark)
    return (
      <StatusChip
        status="warning"
        className="d-remark-chip"
        title={`Your last remark (${when(item.last_remark_time)}) is newer than the studio's last change${item.last_change_time ? ` (${when(item.last_change_time)})` : ""}: it waits for us`}
      >
        Not changed yet
      </StatusChip>
    );
  if (!item.last_change_time) return null;
  return (
    <StatusChip
      status="changed"
      className="d-remark-chip"
      title={`Changed by the studio ${when(item.last_change_time)}, after the last remark (${when(item.last_remark_time)})`}
    >
      Changed {day(item.last_change_time)}
    </StatusChip>
  );
}

type Toast = { text: string; kind: "ok" | "err" | "busy"; n: number };

export function Desk({
  selected,
  tab = "check",
}: {
  selected: string | null;
  tab?: string;
}) {
  const { user } = useSession();
  const [q, setQ] = useState<Queue | null>(null);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState<string>("open");
  const [series, setSeries] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("need");
  // the queue and its counts; a refresh that fails says so and keeps what is on the screen
  const [refreshErr, setRefreshErr] = useState("");
  const loaded = useRef(false);
  const load = useCallback(
    () =>
      getJSON<Queue>("/api/desk")
        .then((data) => {
          loaded.current = true;
          setQ(data);
          setRefreshErr("");
        })
        .catch((e) => {
          if (loaded.current) setRefreshErr(failText("Refreshing the list", e));
          else setErr(String((e as Error).message ?? e));
        }),
    [],
  );
  // one message for every action, also after its card was left (a toast at the top)
  const [toast, setToast] = useState<Toast | null>(null);
  const notify = useCallback((text: string, kind: Toast["kind"]) => {
    setToast((t) => ({ text, kind, n: (t?.n ?? 0) + 1 }));
  }, []);
  useEffect(() => {
    if (!toast || toast.kind !== "ok") return;
    const t = setTimeout(
      () => setToast((cur) => (cur?.n === toast.n ? null : cur)),
      6000,
    );
    return () => clearTimeout(t);
  }, [toast]);
  useEffect(() => {
    load();
  }, [load]);

  const items = useMemo(() => {
    const all = q?.items ?? [];
    const shown = all.filter((i) => {
      // 2nd round: changed after a remark and waiting for a look again (Rens, 14 Oct 2026)
      if (
        status === "second" &&
        !(i.second_round && ["new", "ai-checked"].includes(i.status))
      )
        return false;
      // waiting for us: a remark newer than the studio's last change (desk_open_remarks.py)
      if (status === "waiting" && !i.open_remark) return false;
      if (status === "open" && ["approved", "produced"].includes(i.status))
        return false;
      if (
        status !== "open" &&
        status !== "all" &&
        status !== "second" &&
        status !== "waiting" &&
        i.status !== status
      )
        return false;
      if (series === "SUNS" && !i.id.startsWith("suns-")) return false;
      if (series === "ARR" && !i.arrangement) return false;
      if (
        series &&
        series !== "SUNS" &&
        series !== "ARR" &&
        !(
          i.id.startsWith("drawing-") && i.code.toUpperCase().startsWith(series)
        )
      )
        return false;
      if (search) {
        const s = search.toLowerCase();
        const text = `${i.code} ${i.id} ${i.tags.join(" ")} ${(i.products ?? []).join(" ")}`;
        if (!text.toLowerCase().includes(s)) return false;
      }
      return true;
    });
    return sortItems(shown, sort);
  }, [q, status, series, search, sort]);

  // what was just done on the card before, shown on the next one (an approval or a rejection
  // moves on by itself; its message must not vanish with the card)
  // kept with the card it is meant for: the card may mount before or after it is set
  const [flash, setFlash] = useState<{ id: string; text: string }>({
    id: "",
    text: "",
  });
  const open = (id: string, done = "") => {
    setFlash({ id, text: done });
    window.location.hash = deskHref(id);
  };
  // an order's quick approval from the queue: one click (ADR-128)
  const [quickMsg, setQuickMsg] = useState("");
  const [quickBusy, setQuickBusy] = useState<string | null>(null);
  const [cardRev, setCardRev] = useState(0); // the open card reloads after a quick approval
  const quick = async (i: Item) => {
    if (quickBusy) return;
    setQuickBusy(i.id);
    const what = `Approving order ${i.order?.order}: ${i.code}`;
    setQuickMsg(`${what}…`);
    notify(
      `${what}… (the drawings are stamped, this can take a while)`,
      "busy",
    );
    try {
      await getJSON(`/api/desk/${i.id}`, { action: "approve" });
      const done = `Approved order ${i.order?.order}: ${i.code}`;
      setQuickMsg(done);
      notify(done, "ok");
    } catch (e) {
      const m = failText(`Approving order ${i.order?.order}`, e);
      setQuickMsg(m);
      notify(m, "err");
    } finally {
      setQuickBusy(null);
      await load();
      setCardRev((n) => n + 1);
    }
  };
  const idx = items.findIndex((i) => i.id === selected);
  // the newest list and selection, for an action that ends after a re-render
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  /** the card after this one in the list as it is now (before the action changes it) */
  const nextAfter = useCallback((id: string): string | null => {
    const list = itemsRef.current;
    const k = list.findIndex((i) => i.id === id);
    if (k < 0) return null;
    return list[k + 1]?.id ?? null;
  }, []);
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (e.key === "j" && items.length)
        open(items[Math.min(idx + 1, items.length - 1)].id);
      if (e.key === "k" && items.length) open(items[Math.max(idx - 1, 0)].id);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [items, idx]);
  useEffect(() => {
    if (!selected && items.length && window.innerWidth > 1100)
      open(items[0].id);
  }, [selected, items]);

  if (err)
    return (
      <div className="desk tpl tpl-queue">
        <p className="d-err">{err}</p>
      </div>
    );
  if (!q)
    return (
      <div className="desk tpl tpl-queue">
        <p className="d-muted">Loading the desk…</p>
      </div>
    );
  const c = q.counts;
  const total = q.items.length || 1;
  const toReview = (c["new"] ?? 0) + (c["ai-checked"] ?? 0);
  const seg = [
    ["produced", c.produced ?? 0],
    ["approved", c.approved ?? 0],
    ["ai-checked", c["ai-checked"] ?? 0],
    ["new", c.new ?? 0],
    ["rejected", c.rejected ?? 0],
  ] as const;
  const waiting = q.items.filter((i) => i.open_remark).length;
  return (
    <div className="desk tpl tpl-queue">
      {toast && (
        <div
          className={`d-toast t-${toast.kind}`}
          role={toast.kind === "err" ? "alert" : "status"}
          data-testid="desk-toast"
        >
          <span>{toast.text}</span>
          <button
            type="button"
            aria-label="Close the message"
            onClick={() => setToast(null)}
          >
            ×
          </button>
        </div>
      )}
      <section className="d-top">
        <div className="d-title">
          <div className="head-row">
            <h1>Desk</h1>
            <Info label="About the Desk and its keys">
              The AI sorts, people approve. {q.items.length} covers ·{" "}
              <kbd>j</kbd>
              <kbd>k</kbd> move
              {q.can_approve ? (
                <>
                  {" "}
                  · <kbd>a</kbd> approve · <kbd>r</kbd> reject · <kbd>c</kbd>{" "}
                  comment · <kbd>p</kbd> produced · <kbd>u</kbd> undo
                </>
              ) : q.can_note ? (
                <>
                  {" "}
                  · <kbd>c</kbd> comment
                </>
              ) : null}
            </Info>
          </div>
        </div>
        <div className="d-kpis">
          <Kpi label="To review" icon="st-wait" value={toReview} accent />
          <Kpi label="Approved" icon="st-ok" value={c.approved ?? 0} />
          <Kpi label="Produced" icon="st-made" value={c.produced ?? 0} />
          <Kpi label="Rejected" icon="st-bad" value={c.rejected ?? 0} />
          <Kpi
            label="AI score"
            title="The average AI score"
            icon="st-ai"
            value={q.avg_score == null ? "–" : q.avg_score.toFixed(0)}
          />
          {q.spend && user?.role === "admin" && (
            <Kpi
              icon="stats"
              title="AI spend this month"
              label="AI spend"
              value={`€${q.spend.month_eur.toFixed(2)}`}
              sub={`${q.spend.pct.toFixed(0)} % of €${q.spend.budget_eur}`}
              bar={Math.min(q.spend.pct, 100)}
            />
          )}
        </div>
        <RulesBar canAct={q.can_approve} onChanged={load} />
        <div className="d-pipe" aria-label="pipeline">
          {seg.map(([k, n]) =>
            n ? (
              <span
                key={k}
                className={`d-seg s-${k}`}
                style={{ flexGrow: n / total }}
                title={`${STATUS_LABEL[k]}: ${n}`}
              >
                {n / total > 0.06 && `${STATUS_LABEL[k]} ${n}`}
              </span>
            ) : null,
          )}
        </div>
      </section>

      <div className="d-body">
        <aside className="d-queue">
          <div className="d-filters">
            <input
              className="d-search"
              placeholder="Search code, product, model or tag…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <div className="d-seg-ctl">
              {[
                "open",
                "waiting",
                "second",
                "all",
                "rejected",
                "approved",
                "produced",
              ].map((s) => (
                <button
                  key={s}
                  className={status === s ? "on" : ""}
                  data-filter={s}
                  title={
                    s === "waiting"
                      ? "A remark (reject, comment, fit) newer than the studio's last change"
                      : s === "second"
                        ? "Changed after a remark, waiting for a look again"
                        : undefined
                  }
                  onClick={() => setStatus(s)}
                >
                  {s === "open"
                    ? "To do"
                    : s === "waiting"
                      ? `Waiting for us${waiting ? ` ${waiting}` : ""}`
                      : s === "all"
                        ? "All"
                        : s === "second"
                          ? "2nd round"
                          : STATUS_LABEL[s]}
                </button>
              ))}
            </div>
            <div className="d-chips">
              {SERIES.map((s) => (
                <button
                  key={s}
                  className={series === s ? "on" : ""}
                  title={SERIES_TITLE[s]}
                  onClick={() => setSeries(series === s ? null : s)}
                >
                  {s}
                  {s === "ARR" && (
                    <span className="d-chip-n">
                      {q.items.filter((i) => i.arrangement).length}
                    </span>
                  )}
                </button>
              ))}
            </div>
            <label className="d-sort">
              Sort
              <select value={sort} onChange={(e) => setSort(e.target.value)}>
                {Object.entries(SORTS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {quickMsg && (
            <p className="d-msg" role="status" data-testid="desk-quick-msg">
              {quickMsg}
            </p>
          )}
          {refreshErr && (
            <p className="d-msg d-msg-err" role="alert">
              {refreshErr}{" "}
              <button className="d-btn d-ghost d-small" onClick={() => load()}>
                Try again
              </button>
            </p>
          )}
          <ul className="d-list">
            {items.map((i) => (
              <li
                key={i.id}
                data-id={i.id}
                className={i.id === selected ? "sel" : ""}
                onClick={() => open(i.id)}
              >
                {i.has_picture ? (
                  <img
                    src={`/api/models/${i.id}/files/cover.png`}
                    alt=""
                    loading="lazy"
                  />
                ) : (
                  <span className="d-noimg" />
                )}
                <div className="d-row">
                  <div className="d-row-top">
                    <strong>{i.code}</strong>
                    <Pill status={i.status} arrangement={i.arrangement} />
                  </div>
                  <RemarkChip item={i} />
                  {i.order && (
                    <div className="d-order" data-testid="desk-order">
                      <span
                        className="d-order-tag"
                        title={`sent to production by ${i.order.by}, ${when(i.order.time)}`}
                      >
                        ORDER #{i.order.order}
                        {i.order.b2b ? " · B2B" : ""}
                      </span>
                      {q.can_approve &&
                        (i.built ? (
                          <button
                            className="d-btn d-primary d-small"
                            title="The order's quick approval: the DXF follows at once"
                            data-testid="desk-quick-approve"
                            disabled={!!quickBusy}
                            aria-busy={quickBusy === i.id}
                            onClick={(e) => {
                              e.stopPropagation();
                              quick(i);
                            }}
                          >
                            <Icon name="approve" size={14} />
                            {quickBusy === i.id ? "Approving…" : "Approve"}
                          </button>
                        ) : (
                          <span className="d-muted">being calculated…</span>
                        ))}
                    </div>
                  )}
                  <div className="d-row-sub">
                    {i.arrangement ? (
                      <span className="d-arr-tag" title="An arrangement">
                        ARR
                      </span>
                    ) : (
                      <>
                        <Score label="G" v={i.scores.gemini} />
                        <Score label="D" v={i.scores.deepseek} />
                      </>
                    )}
                    <span
                      className={`d-n ${i.pieces > 30 ? "d-flag" : ""}`}
                      title={`${i.pieces} pieces`}
                    >
                      <Icon name="pieces" size={13} />
                      {i.pieces}
                    </span>
                    <span className="d-n" title={`${i.vents} vents`}>
                      <Icon name="vents" size={13} />
                      {i.vents}
                    </span>
                    {i.tags.includes("shape-to-check") && (
                      <span className="d-flag">shape to check</span>
                    )}
                    {i.second_round && (
                      <span className="d-second" title={i.second_round}>
                        2nd round
                      </span>
                    )}
                    {i.arrangement && i.sent && i.status === "ai-checked" && (
                      <span
                        className="d-n"
                        title={`sent by ${i.sent.by}, ${when(i.sent.time)}`}
                      >
                        <Icon name="send" size={13} />
                        {i.sent.by}
                      </span>
                    )}
                  </div>
                  {i.products && i.products.length > 0 && (
                    <div className="d-row-prod" title={i.products.join("\n")}>
                      {i.products.join(" · ")}
                    </div>
                  )}
                </div>
              </li>
            ))}
            {!items.length && <li className="d-empty">Nothing here.</li>}
          </ul>
        </aside>
        <section className="d-card-host">
          {selected ? (
            <CardView
              key={selected}
              id={selected}
              tab={DESK_TABS.some(([t]) => t === tab) ? tab : "check"}
              canAct={q.can_approve}
              canNote={!!q.can_note}
              reasons={q.reasons}
              picturesMax={q.pictures_max ?? 8}
              onChanged={load}
              flash={flash.id === selected ? flash.text : ""}
              rev={cardRev}
              notify={notify}
              nextAfter={nextAfter}
              onNext={(done, from, next) => {
                // only when the person is still on that card: a click elsewhere wins
                if (selectedRef.current !== from) return;
                if (next) open(next, done);
                else
                  notify(`${done} · that was the last one in this list`, "ok");
              }}
            />
          ) : (
            <div className="d-placeholder">Pick a cover from the list.</div>
          )}
        </section>
      </div>
    </div>
  );
}

function Kpi({
  label,
  icon,
  title,
  value,
  sub,
  accent,
  bar,
}: {
  label: string;
  icon?: IconName;
  title?: string;
  value: number | string;
  sub?: string;
  accent?: boolean;
  bar?: number;
}) {
  return (
    <div className={`d-kpi ${accent ? "accent" : ""}`} title={title}>
      <span className="d-kpi-label">
        {icon && <Icon name={icon} size={15} />}
        {label}
      </span>
      <span className="d-kpi-value">{value}</span>
      {sub && <span className="d-kpi-sub">{sub}</span>}
      {bar != null && (
        <span className="d-kpi-bar">
          <i style={{ width: `${bar}%` }} />
        </span>
      )}
    </div>
  );
}

const PILL_ICON: Record<string, IconName> = {
  approved: "st-ok",
  produced: "st-made",
  rejected: "st-bad",
  "ai-checked": "st-ai",
  new: "st-wait",
};

function Pill({
  status,
  arrangement,
}: {
  status: string;
  arrangement?: boolean;
}) {
  return (
    <span className={`d-pill s-${status}${arrangement ? " arr" : ""}`}>
      <Icon name={PILL_ICON[status] ?? "st-wait"} size={13} />
      {statusLabel(status, arrangement)}
    </span>
  );
}

function Score({ label, v }: { label: string; v: number | null }) {
  return (
    <span
      className={`d-score t-${tone(v)}`}
      title={label === "G" ? "Gemini" : "DeepSeek"}
    >
      {label} {v == null ? "–" : Math.round(v)}
    </span>
  );
}

function CardView({
  id,
  tab,
  canAct,
  reasons,
  picturesMax,
  onChanged,
  onNext,
  nextAfter = () => null,
  notify = () => {},
  rev = 0,
  flash = "",
  canNote = false,
}: {
  id: string;
  tab: string;
  flash?: string;
  /** reload the card (a quick approval in the queue changed it) */
  rev?: number;
  notify?: (text: string, kind: "ok" | "err" | "busy") => void;
  nextAfter?: (id: string) => string | null;
  canAct: boolean;
  /** the workshop login: Comment and After sewing (a fit, measured sizes), nothing else */
  canNote?: boolean;
  reasons: string[];
  picturesMax: number;
  onChanged: () => void | Promise<unknown>;
  /** after an approval or a rejection: the next card (`next`, chosen before the list changed) */
  onNext: (done: string, from: string, next: string | null) => void;
}) {
  const { user } = useSession();
  const workshopLogin = isWorkshop(user); // no cover page, no product list (ADR-128)
  const [card, setCard] = useState<Card | null>(null);
  const [model, setModel] = useState<ModelDetail | null>(null);
  // when the cover was loaded: its 3D files are asked for afresh after a rebuild (ADR-138)
  const [stamp, setStamp] = useState(0);
  const [page, setPage] = useState(0);
  const [zoom, setZoom] = useState<string | null>(null);
  // the dialog at the bottom: a reject (reasons, words, pictures) or a comment (ADR-096)
  const [dialog, setDialog] = useState<"" | "reject" | "note">("");
  const [pending, setPending] = useState<Pending[]>([]);
  const [sending, setSending] = useState(false);
  const snap = useRef<(() => string | null) | null>(null);
  const [why, setWhy] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [fitNote, setFitNote] = useState("");
  // after sewing: the sizes measured against the check list (ADR-111)
  const [measuring, setMeasuring] = useState(false);
  const [sewing, setSewing] = useState(false); // the "After sewing" row of the action bar
  const [measured, setMeasured] = useState<Record<string, number>>({});
  const [msg, setMsg] = useState(flash);
  useEffect(() => {
    if (flash) setMsg(flash);
  }, [flash]);
  const [allDiffs, setAllDiffs] = useState(false);
  const [allRevs, setAllRevs] = useState(false);
  // "let the AI read it": its job followed here, the outcome shown beside the button
  const [aiJob, setAiJob] = useState<string | null>(null);
  const [aiNote, setAiNote] = useState("");
  const textRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const load = useCallback(
    () =>
      Promise.all([
        getJSON<Card>(`/api/desk/${id}`)
          .then(setCard)
          .catch((e) => setMsg(failText("Loading the card", e))),
        api
          .model(id)
          .then((m) => {
            setModel(m);
            setStamp(Date.now());
          })
          .catch(() => setModel(null)),
      ]),
    [id],
  );
  useEffect(() => {
    load();
  }, [load, rev]);
  useEffect(() => {
    setMeasuring(false);
    setMeasured({});
    setSewing(false);
  }, [id]);
  useEffect(() => {
    setAiJob(null);
    setAiNote("");
  }, [id]);
  useEffect(() => {
    if (!aiJob) return;
    const t = setInterval(async () => {
      try {
        const j = await api.job(aiJob);
        if (j.status === "queued" || j.status === "running") return;
        clearInterval(t);
        setAiJob(null);
        if (j.status === "failed") {
          setAiNote(`Failed: ${j.error ?? "see the model's log"}`);
        } else {
          const r = await api.drawingRead(id).catch(() => null);
          setAiNote(
            !r
              ? "Done."
              : r.status === "built"
                ? `Built by the AI: ${r.pieces ?? "?"} pieces, ${r.vents ?? "?"} vents. Check it against the drawing, then approve or reject.`
                : `Nothing built: ${r.reasons.join("; ")}`,
          );
        }
        load();
        onChanged();
      } catch (e) {
        clearInterval(t);
        setAiJob(null);
        setAiNote(String((e as Error).message ?? e));
      }
    }, 2000);
    return () => clearInterval(t);
  }, [aiJob, id, load, onChanged]);

  // one action at a time (14 Oct 2026: an approval stamps the drawings for seconds, the button
  // gave no sign and people clicked again): busy on the screen, then the outcome in words,
  // the list and its counts refreshed, and on to the next card
  const [busy, setBusy] = useState("");
  const [msgErr, setMsgErr] = useState(false);
  const busyRef = useRef(false);
  const code = card?.code ?? id;
  const act = useCallback(
    async (
      body: Record<string, unknown>,
      done: string,
      next = false,
      doing = "Saving…",
    ) => {
      if (busyRef.current) return false;
      busyRef.current = true;
      setBusy(doing);
      setMsg(doing);
      setMsgErr(false);
      const action = String(body.action);
      const slow = action === "approve";
      notify(
        slow
          ? `${doing} ${code}: the drawings are stamped, this can take a while`
          : `${doing} ${code}`,
        "busy",
      );
      const following = next ? nextAfter(id) : null; // before the list changes
      try {
        await getJSON(`/api/desk/${id}`, body);
      } catch (e) {
        const m = failText(`${ACTION_NAME[action] ?? action} ${code}`, e);
        setMsg(m);
        setMsgErr(true);
        notify(m, "err");
        busyRef.current = false;
        setBusy("");
        // the card and the list as they are now: someone else may have acted
        await Promise.all([load(), onChanged()]);
        return false;
      }
      setDialog("");
      setMsg(done);
      notify(`${done}: ${code}`, "ok");
      // the list and its counts follow (the Desk's own state: it outlives this card), and
      // the next card opens at once, chosen before the list changed
      const refresh = Promise.all([next ? null : load(), onChanged()]);
      if (next) onNext(`${done}: ${code}`, id, following);
      await refresh;
      busyRef.current = false;
      setBusy("");
      return true;
    },
    [id, code, load, onChanged, onNext, nextAfter, notify],
  );

  // a reject or a comment: the pictures go up first, then the action names them
  const send = async (
    body: Record<string, unknown>,
    done: string,
    next: boolean,
  ) => {
    setSending(true);
    setMsg("");
    try {
      // only pictures not sent yet go up: a refused action (no reason given) and a second
      // try do not upload them twice
      const fresh = pending.filter((p) => !p.name);
      const names = await uploadPictures(id, fresh);
      const sent = pending.map((p) =>
        p.name ? p : { ...p, name: names[fresh.indexOf(p)] },
      );
      setPending(sent);
      const pictures = sent.map((p) => p.name as string);
      if (
        await act(
          { ...body, pictures },
          done,
          next,
          body.action === "reject" ? "Rejecting…" : "Saving the comment…",
        )
      ) {
        sent.forEach((p) => URL.revokeObjectURL(p.url));
        setPending([]);
        setText("");
      }
    } catch (e) {
      setMsg(String((e as Error).message ?? e));
    } finally {
      setSending(false);
    }
  };
  const openDialog = (kind: "reject" | "note") => {
    setDialog(kind);
    // the whole dialog in sight, its Pictures row too: focusing the text alone scrolled
    // only that far, and the picture buttons stayed below the screen (Rens, 8 Oct 2026)
    setTimeout(() => {
      textRef.current?.focus({ preventScroll: true });
      dialogRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
    }, 50);
  };

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (!card || !(canAct || canNote)) return;
      if (t && ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (t?.isContentEditable) return;
      // the keys do what the buttons do, only when the buttons are there
      if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
      if (e.defaultPrevented || dialog || zoom || busyRef.current) return;
      if (!canAct) {
        if (e.key === "c") openDialog("note"); // the workshop: a comment only
        return;
      }
      const done = ["approved", "produced"].includes(card.desk.status);
      if (e.key === "a") {
        if (done) notify(`${card.code} is already ${card.desk.status}`, "ok");
        else act({ action: "approve" }, "Approved", true, "Approving…");
      }
      if (e.key === "r") openDialog("reject");
      if (e.key === "c") openDialog("note");
      if (e.key === "p")
        act(
          { action: "produced", done: card.desk.status !== "produced" },
          card.desk.status !== "produced" ? "Marked produced" : "Not produced",
        );
      if (e.key === "u" && card.can_undo !== false)
        act({ action: "undo" }, "Undone", false, "Undoing…");
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [canAct, canNote, card, act, dialog, zoom, notify]);

  if (!card) return <div className="d-card d-loading">{msg || "Loading…"}</div>;
  const ck = card.check;
  const g = ck.gemini_second ?? ck.gemini;
  const ds = ck.deepseek;
  const read = card.read as {
    vents_total?: number | null;
    vents_from?: string | null;
    vents_at?: string | null;
    open_bottom?: boolean;
    drawstring?: boolean;
    elastic?: boolean;
    zip?: boolean;
  };
  const facts: [string, boolean | null, string][] = [];
  if (read.vents_total != null)
    facts.push([
      "Air vents",
      read.vents_total === card.vents,
      `drawing ${read.vents_total}${read.vents_from === "arrows" ? " (counted from arrows)" : ""} · cover ${card.vents}`,
    ]);
  if (read.vents_at)
    facts.push([
      "Vent position",
      null,
      `drawing says “at ${read.vents_at}”; we place them 5 cm above the hem`,
    ]);
  if (read.open_bottom != null)
    facts.push([
      "Open at the bottom",
      read.open_bottom ? true : null,
      read.open_bottom ? "as drawn" : "not mentioned",
    ]);
  for (const k of ["drawstring", "elastic", "zip"] as const)
    if (read[k])
      facts.push([k[0].toUpperCase() + k.slice(1), null, "on the drawing"]);
  facts.push([
    "Pieces",
    card.pieces <= 10 ? true : null,
    `${card.pieces} pieces + vents`,
  ]);
  facts.push([
    "Cutting-table DXF",
    card.dxf_ok,
    card.dxf_ok ? "available" : "locked until approved",
  ]);
  const st = card.desk;
  const arr = card.arrangement_info ?? null;
  if (arr) {
    // an arrangement: no drawing and no AI check, but who sent it and its plan
    facts.length = 0;
    facts.push([
      "Sent to the Desk",
      card.sent ? true : null,
      card.sent
        ? `by ${card.sent.by}, ${when(card.sent.time)}`
        : "not yet: its maker sends it from the Arrangements page",
    ]);
    if (arr.plan)
      facts.push([
        "Cover plan",
        null,
        `${FOOTPRINT_NAMES[arr.plan.footprint] ?? arr.plan.footprint} · ${cm(arr.plan.size_mm[0])} × ${cm(arr.plan.size_mm[1])} cm at the hem`,
      ]);
    if (arr.size_mm)
      facts.push([
        "Furniture together",
        null,
        `${arr.size_mm.map(cm).join(" × ")} cm (L × D × H)`,
      ]);
    facts.push([
      "Members up to date",
      arr.stale.length ? false : true,
      arr.stale.length
        ? `${arr.stale.join(", ")} changed since: build the arrangement again`
        : "as when it was built",
    ]);
    facts.push([
      "Pieces",
      card.pieces <= 10 ? true : null,
      `${card.pieces} pieces + ${card.vents} vents`,
    ]);
    facts.push([
      "Cutting-table DXF",
      card.dxf_ok,
      card.dxf_ok ? "available" : "locked until approved",
    ]);
  }
  const diffs = [...(g?.differences ?? []), ...(ds?.differences ?? [])];
  // what happened after the last rejection (a correction, a rebuild, a comment)
  const since = st.rejected
    ? st.history.filter(
        (h) => h.time > st.rejected!.time && h.action !== "reject",
      )
    : [];
  const showAi =
    canAct &&
    !arr &&
    ck.outcome !== "agreed: same" &&
    st.status !== "approved" &&
    st.status !== "produced";
  const checklist = model?.files.includes("checklist.pdf")
    ? `/api/models/${card.id}/files/checklist.pdf`
    : null;
  const counts: Record<string, number | undefined> = {
    pieces: card.pieces_list.length || undefined,
    history: st.history.length || undefined,
  };
  // the drawing and the 3D stay mounted on every tab (a snapshot for a picture works from any
  // tab); they are on the screen on Check and Correct
  const split = tab === "check" || tab === "correct";
  return (
    <article className="d-card">
      <div className="d-card-head">
        <div>
          <h2>{card.code}</h2>
          <span className="d-id">
            {card.id}
            {card.products?.length ? ` · ${card.products[0]}` : ""}
          </span>
        </div>
        <div className="d-head-right">
          {ck.outcome && (
            <span
              className={`d-outcome o-${ck.outcome.replace(/[: ]+/g, "-")}`}
            >
              {OUTCOME_LABEL[ck.outcome] ?? ck.outcome}
            </span>
          )}
          {!arr && (
            <>
              <Score label="G" v={card.scores.gemini} />
              <Score label="D" v={card.scores.deepseek} />
            </>
          )}
          <Pill status={st.status} arrangement={!!arr} />
          <RemarkChip item={card} />
          {!workshopLogin && (
            <IconLink
              icon="open"
              label="Open cover"
              className="d-open"
              href={modelHref(card.id)}
            />
          )}
          <details className="d-menu" data-menu>
            <summary className="icon-btn" title="More" aria-label="More">
              <Icon name="more" />
            </summary>
            <div className="d-menu-list">
              {showAi && (
                <button
                  className={`d-ai ${aiJob ? "busy" : ""}`}
                  disabled={!!aiJob}
                  title="The AI reads the drawing: a proposal (about 1–5 cents), marked 'read by the AI', to approve here"
                  onClick={async (e) => {
                    (
                      e.currentTarget.closest("details") as HTMLDetailsElement
                    ).open = false;
                    setAiNote("");
                    try {
                      const r = await api.aiReadDrawing(card.id);
                      setAiJob(r.job.id);
                    } catch (err) {
                      setAiNote(String((err as Error).message ?? err));
                    }
                  }}
                >
                  <span className="d-mi">
                    <Icon name="ai" size={16} />
                    {aiJob ? "Reading… (a minute)" : "Let the AI read it"}
                  </span>
                  <small>about 1–5 cents</small>
                </button>
              )}
              {checklist && (
                <a
                  href={checklist}
                  title="Check list (PDF): the sizes to measure on the sewn cover"
                >
                  <span className="d-mi">
                    <Icon name="checklist" size={16} />
                    Check list (PDF)
                  </span>
                </a>
              )}
              {arr && !workshopLogin && (
                <a href={arrangementHref(card.id)}>
                  <span className="d-mi">
                    <Icon name="arrangements" size={16} />
                    Edit arrangement
                  </span>
                </a>
              )}
              {!workshopLogin && (
                <a href={modelHref(card.id, "pieces")}>
                  <span className="d-mi">
                    <Icon name="pieces" size={16} />
                    Cut pieces and DXF
                  </span>
                </a>
              )}
              {workshopLogin && card.dxf_ok && (
                <a
                  href={`/api/models/${card.id}/files/cut.dxf`}
                  download
                  title="Cutting table (DXF), approved at the Desk"
                >
                  <span className="d-mi">
                    <Icon name="dxf" size={16} />
                    Cutting table (DXF)
                  </span>
                </a>
              )}
              {!workshopLogin && (
                <a
                  href="#/covers/products"
                  title="Product list: upload the workshop's list (Excel)"
                >
                  <span className="d-mi">
                    <Icon name="product-list" size={16} />
                    Product list
                  </span>
                </a>
              )}
            </div>
          </details>
        </div>
      </div>
      {arr && (
        <p
          className={`d-arr-status s-${st.status}`}
          role="status"
          data-testid="arr-status"
        >
          {arrStatus(st, card.sent)}
        </p>
      )}

      {(aiJob || aiNote) && (
        <p className={`d-ai-note ${aiJob ? "busy" : ""}`} role="status">
          {aiJob
            ? "The AI is reading the drawing and the program builds its proposal. This card updates by itself."
            : aiNote}
        </p>
      )}
      {card.second_round && (
        <p className="d-ai-note" role="status">
          <strong>2nd round · </strong>
          {card.second_round}
        </p>
      )}
      <nav className="d-cardtabs" aria-label="Card">
        {DESK_TABS.map(([t, label, icon]) => (
          <a
            key={t}
            href={deskHref(card.id, t)}
            className={tab === t ? "on" : ""}
            aria-current={tab === t ? "page" : undefined}
          >
            <Icon name={icon} size={16} />
            {label}
            {counts[t] && <span className="d-chip-n">{counts[t]}</span>}
          </a>
        ))}
      </nav>
      {measuring && (
        <section className="d-panel d-measuring">
          <h3>
            <Icon name="measure" /> Measured on the sewn cover
          </h3>
          <MeasuredForm id={card.id} onChange={setMeasured} />
        </section>
      )}
      <div className="d-split" hidden={!split}>
        {arr ? (
          <ArrangementFigure arr={arr} />
        ) : (
          <figure className="d-drawing">
            <figcaption>
              The drawing
              {card.pages > 1 && (
                <span className="d-pages">
                  {Array.from({ length: card.pages }, (_, i) => (
                    <button
                      key={i}
                      className={i === page ? "on" : ""}
                      onClick={() => setPage(i)}
                    >
                      {i + 1}
                    </button>
                  ))}
                </span>
              )}
            </figcaption>
            {card.pages ? (
              <img
                src={`/api/desk/${card.id}/page/${page}`}
                alt="the drawing"
                onClick={() => setZoom(`/api/desk/${card.id}/page/${page}`)}
              />
            ) : (
              <div className="d-noimg big">No drawing found</div>
            )}
          </figure>
        )}
        <figure className="d-3d">
          <figcaption>Our cover</figcaption>
          {model ? (
            <Viewer
              id={card.id}
              files={model.files}
              stamp={stamp}
              snapshot={snap}
            />
          ) : card.has_picture ? (
            <img
              src={`/api/models/${card.id}/files/cover.png?v=${stamp}`}
              alt="our cover"
            />
          ) : (
            <div className="d-noimg big">No picture</div>
          )}
        </figure>
      </div>

      <div className="d-grid">
        {tab === "check" && (
          <>
            {st.status === "rejected" && st.rejected && (
              <section className="d-panel d-wide d-rejected">
                <h3>
                  Rejected by {st.rejected.by}, {when(st.rejected.time)}
                </h3>
                {st.rejected.reasons.length > 0 && (
                  <p>{st.rejected.reasons.join(" · ")}</p>
                )}
                {st.rejected.text && <q>{st.rejected.text}</q>}
                {since.length > 0 && (
                  <ul className="d-since">
                    {since.map((h, i) => (
                      <li key={i}>
                        Since then:{" "}
                        <strong>
                          {h.action === "note" ? "comment" : h.action}
                        </strong>
                        {h.by && <> by {h.by}</>} <time>{when(h.time)}</time>
                        {h.text && <> · {h.text}</>}
                      </li>
                    ))}
                  </ul>
                )}
                <a href={deskHref(card.id, "history")}>
                  The whole history, with the pictures
                </a>
              </section>
            )}
            {card.product_list && <ProductsPanel list={card.product_list} />}
            <section className="d-panel">
              <h3>{arr ? "The arrangement" : "What the program read"}</h3>
              <ul className="d-facts">
                {facts.map(([k, ok, v]) => (
                  <li key={k}>
                    <i
                      className={`d-dot ${ok === true ? "ok" : ok === false ? "bad" : "info"}`}
                    />
                    <span>{k}</span>
                    <em>{v}</em>
                  </li>
                ))}
              </ul>
            </section>
            {!arr && (
              <section className="d-panel">
                <h3>What the AIs say</h3>
                {!g && !ds && <p className="d-muted">Not checked yet.</p>}
                {g && (
                  <div className="d-verdict">
                    <span className="d-ai-who">
                      Gemini · looks{ck.gemini_second ? " (second look)" : ""}
                    </span>
                    <p>{g.summary}</p>
                  </div>
                )}
                {ds && (
                  <div className="d-verdict">
                    <span className="d-ai-who">
                      DeepSeek · reads the numbers
                    </span>
                    <p>{ds.summary}</p>
                  </div>
                )}
                {diffs.length > 0 && (
                  <ul className="d-diffs">
                    {diffs.slice(0, allDiffs ? undefined : 6).map((d, i) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                )}
                {diffs.length > 6 && (
                  <button
                    className="d-more"
                    onClick={() => setAllDiffs(!allDiffs)}
                  >
                    {allDiffs ? "Show fewer" : "Show all"}
                  </button>
                )}
              </section>
            )}
          </>
        )}
        {tab === "pieces" && (
          <>
            <section className="d-panel">
              <h3>Pieces</h3>
              <table className="d-table">
                <tbody>
                  {card.pieces_list.map((p) => (
                    <tr key={p.name}>
                      <td>{p.name}</td>
                      <td>×{p.quantity}</td>
                      <td>
                        {p.size_mm?.map((x) => Math.round(x / 10)).join(" × ")}{" "}
                        cm
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="d-panel">
              <h3>Revisions</h3>
              {card.revisions.length ? (
                <table className="d-table">
                  <tbody>
                    {[...card.revisions]
                      .reverse()
                      .slice(0, allRevs ? undefined : 4)
                      .map((r) => (
                        <tr
                          key={r.number}
                          className={
                            st.preferred_revision === r.number ? "pref" : ""
                          }
                        >
                          <td>r{r.number}</td>
                          <td>{when(r.time)}</td>
                          <td>{r.panels} panels</td>
                          <td>
                            {canAct && card.revisions.length > 1 && (
                              <button
                                className="d-link"
                                onClick={() =>
                                  act(
                                    { action: "prefer", n: r.number },
                                    `r${r.number} is the one to cut`,
                                  )
                                }
                              >
                                {st.preferred_revision === r.number
                                  ? "★ to cut"
                                  : "cut this"}
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                  {card.revisions.length > 4 && (
                    <caption className="d-caption">
                      <button
                        className="d-more"
                        onClick={() => setAllRevs(!allRevs)}
                      >
                        {allRevs
                          ? "Show fewer"
                          : `Show all ${card.revisions.length}`}
                      </button>
                    </caption>
                  )}
                </table>
              ) : (
                <p className="d-muted">No revisions kept.</p>
              )}
            </section>
          </>
        )}
        {/* kept mounted on every tab: a correction being written, its sizes and pictures
            survive a look at Check or History */}
        <div className="d-correct-host" hidden={tab !== "correct"}>
          <Corrections
            id={card.id}
            canAct={canAct}
            onChanged={() => {
              load();
              onChanged();
            }}
            snapshot3d={() => snap.current?.() ?? null}
            drawingUrl={card.pages ? `/api/desk/${card.id}/page/${page}` : null}
            picturesMax={picturesMax}
            paste={!dialog && tab === "correct"}
          />
        </div>
        {tab === "history" && (
          <section className="d-panel d-wide">
            <h3>History</h3>
            <ol className="d-timeline">
              {[...st.history].reverse().map((h, i) => (
                <li key={i}>
                  <span
                    className={`d-tl-dot a-${h.action.replace(/\s+/g, "-")}`}
                  />
                  <strong
                    className={
                      h.action.startsWith("changed after") ? "d-tl-warn" : ""
                    }
                  >
                    {h.action === "note" ? "comment" : h.action}
                  </strong>{" "}
                  {h.by && <>by {h.by}</>} <time>{when(h.time)}</time>
                  {h.reasons && h.reasons.length > 0 && (
                    <em> · {h.reasons.join(", ")}</em>
                  )}
                  {h.text && <q>{h.text}</q>}
                  {h.note && h.fits == null && <em> · {h.note}</em>}
                  {h.fits != null && (
                    <em>
                      {" "}
                      · {h.fits ? "fits" : "does not fit"} {h.note}
                    </em>
                  )}
                  {h.measured && h.measured.length > 0 && (
                    <MeasuredSummary rows={h.measured} />
                  )}
                  {h.done != null && (
                    <em> · {h.done ? "produced" : "not produced"}</em>
                  )}
                  {h.pictures && h.pictures.length > 0 && (
                    <PictureThumbs
                      id={card.id}
                      names={h.pictures}
                      onOpen={setZoom}
                    />
                  )}
                </li>
              ))}
              {!st.history.length && <li className="d-muted">Nothing yet.</li>}
            </ol>
          </section>
        )}
      </div>

      <div className="d-actions">
        {!canAct && !canNote && (
          <span className="d-muted">
            Only Rens, Rick, Wouter or an admin can decide here.
          </span>
        )}
        {!canAct && canNote && !dialog && (
          <span className="d-muted" data-testid="workshop-note">
            The workshop adds fits and comments; an approver decides.
          </span>
        )}
        {(canAct || canNote) && !dialog && (
          <>
            {canAct && (
              <>
                <button
                  className="d-btn d-primary"
                  data-testid="desk-approve"
                  aria-busy={busy === "Approving…"}
                  disabled={
                    !!busy ||
                    st.status === "approved" ||
                    st.status === "produced"
                  }
                  title={
                    st.status === "approved" || st.status === "produced"
                      ? `Already ${st.status}`
                      : undefined
                  }
                  onClick={() =>
                    act({ action: "approve" }, "Approved", true, "Approving…")
                  }
                >
                  <Icon name="approve" />
                  {busy === "Approving…" ? (
                    <>
                      <span className="d-spin" aria-hidden="true" />
                      Approving…
                    </>
                  ) : (
                    <>
                      Approve <kbd>a</kbd>
                    </>
                  )}
                </button>
                <button
                  className="d-btn d-danger"
                  data-testid="desk-reject"
                  disabled={!!busy}
                  onClick={() => openDialog("reject")}
                >
                  <Icon name="reject" />
                  Reject <kbd>r</kbd>
                </button>
              </>
            )}
            <button
              className="d-btn d-ghost"
              data-testid="desk-comment"
              disabled={!!busy}
              title="A remark with pictures, without changing the status"
              onClick={() => openDialog("note")}
            >
              <Icon name="comment" />
              Comment <kbd>c</kbd>
            </button>
            <span className="d-grow" />
            <button
              className={`d-btn d-ghost ${sewing || measuring ? "on" : ""}`}
              aria-expanded={sewing || measuring}
              data-testid="after-sewing"
              title="Produced, the fit after sewing and what was measured"
              onClick={() => setSewing(!(sewing || measuring))}
            >
              <Icon name="sewing" />
              After sewing {sewing || measuring ? "▴" : "▾"}
            </button>
            {canAct && st.history.length > 0 && card.can_undo !== false && (
              <IconButton
                icon="undo"
                label="Undo (u)"
                className="d-undo"
                disabled={!!busy}
                onClick={() =>
                  act({ action: "undo" }, "Undone", false, "Undoing…")
                }
              />
            )}
            {(sewing || measuring) && (
              <div className="d-sewing">
                {canAct && (
                  <label
                    className={`d-check ${st.status === "approved" || st.status === "produced" ? "" : "off"}`}
                  >
                    <input
                      type="checkbox"
                      checked={st.status === "produced"}
                      disabled={
                        !!busy ||
                        !(st.status === "approved" || st.status === "produced")
                      }
                      onChange={(e) =>
                        act(
                          { action: "produced", done: e.target.checked },
                          e.target.checked ? "Marked produced" : "Not produced",
                        )
                      }
                    />
                    Produced <kbd>p</kbd>
                  </label>
                )}
                <span className="d-fit">
                  <input
                    placeholder="After sewing: note…"
                    value={fitNote}
                    onChange={(e) => setFitNote(e.target.value)}
                  />
                  <button
                    className={`d-btn d-ghost ${measuring ? "on" : ""}`}
                    data-testid="measured-toggle"
                    title="Enter what you measured on the sewn cover against the check list; it is saved with Fits or Does not fit"
                    onClick={() => setMeasuring(!measuring)}
                  >
                    Measured…
                  </button>
                  {[true, false].map((fits) => (
                    <button
                      key={String(fits)}
                      className="d-btn d-ghost"
                      disabled={!!busy}
                      onClick={async () => {
                        const values = measuring ? measured : {};
                        const n = Object.keys(values).length;
                        const ok = await act(
                          {
                            action: "fit",
                            fits,
                            note: fitNote,
                            measured: values,
                          },
                          n
                            ? `Fit saved, with ${n} measured sizes`
                            : "Fit saved",
                        );
                        if (ok && n) setMeasuring(false);
                      }}
                    >
                      {fits ? "Fits" : "Does not fit"}
                    </button>
                  ))}
                </span>
              </div>
            )}
          </>
        )}
        {(canAct || canNote) && dialog && (
          <div className="d-reject" ref={dialogRef}>
            {dialog === "reject" ? (
              <div className="d-chips">
                {reasons.map((r) => (
                  <button
                    key={r}
                    className={why.includes(r) ? "on" : ""}
                    onClick={() =>
                      setWhy(
                        why.includes(r)
                          ? why.filter((x) => x !== r)
                          : [...why, r],
                      )
                    }
                  >
                    {r}
                  </button>
                ))}
              </div>
            ) : (
              <strong className="d-dialog-title">Comment</strong>
            )}
            <PictureTray
              pending={pending}
              onChange={setPending}
              snapshot3d={() => snap.current?.() ?? null}
              drawingUrl={
                card.pages ? `/api/desk/${card.id}/page/${page}` : null
              }
              max={picturesMax}
            />
            <textarea
              ref={textRef}
              placeholder={
                dialog === "reject"
                  ? "What is wrong? (kept in the history; to change the cover itself, use “Correct this cover”)"
                  : "Your remark (kept in the history; the status stays as it is)"
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <button
              className={`d-btn ${dialog === "reject" ? "d-danger" : "d-primary"}`}
              data-testid="desk-dialog-send"
              disabled={sending || !!busy}
              onClick={() =>
                dialog === "reject"
                  ? send(
                      { action: "reject", reasons: why, text },
                      "Rejected",
                      true,
                    )
                  : send({ action: "note", text }, "Comment saved", false)
              }
            >
              {sending
                ? "Sending…"
                : dialog === "reject"
                  ? "Reject"
                  : "Save comment"}
            </button>
            <button
              className="d-btn d-ghost"
              disabled={sending || !!busy}
              onClick={() => setDialog("")}
            >
              Cancel
            </button>
          </div>
        )}
        {msg && (
          <span
            className={`d-msg ${msgErr ? "d-msg-err" : ""} ${busy ? "busy" : ""}`}
            role={msgErr ? "alert" : "status"}
            data-testid="desk-msg"
          >
            {msg}
          </span>
        )}
      </div>

      {zoom && (
        <div className="d-zoom" onClick={() => setZoom(null)}>
          <img src={zoom} alt="large" />
        </div>
      )}
    </article>
  );
}

/** An action's name in a message ("Approve D2 refused: ..."). */
const ACTION_NAME: Record<string, string> = {
  approve: "Approve",
  reject: "Reject",
  note: "Comment",
  produced: "Produced",
  fit: "Fit",
  undo: "Undo",
  prefer: "Prefer",
};

/** Where an arrangement stands, in one line for its card (ADR-115). */
function arrStatus(st: Card["desk"], sent: Item["sent"]): string {
  if (st.status === "approved" && st.approved)
    return `Approved by ${st.approved.by}, ${when(st.approved.time)}: the cutting-table DXF is available.`;
  if (st.status === "produced" && st.produced)
    return `Produced (${when(st.produced.time)}).`;
  if (st.status === "rejected" && st.rejected)
    return `Rejected by ${st.rejected.by}, ${when(st.rejected.time)}: ${[...st.rejected.reasons, st.rejected.text].filter(Boolean).join(" · ")}. Changing it on the Arrangements page sends it back.`;
  const changed = [...st.history]
    .reverse()
    .find((h) => h.action.startsWith("changed after"));
  if (st.status === "ai-checked" && sent)
    return changed && changed.time >= sent.time
      ? `Waiting for approval again: ${changed.action} (${changed.text ?? ""}), ${when(changed.time)}.`
      : `Waiting for approval: sent by ${sent.by}, ${when(sent.time)}.`;
  return "Not sent to the Desk yet: its maker sends it from the Arrangements page (an approver may approve it all the same).";
}

/** The arrangement seen from above, and its members with links to their own models. */
function ArrangementFigure({ arr }: { arr: Arrangement }) {
  return (
    <figure className="d-drawing d-arr">
      <figcaption>
        The arrangement from above
        {arr.plan && (
          <span className="d-arr-legend">
            <i /> cover plan:{" "}
            {FOOTPRINT_NAMES[arr.plan.footprint] ?? arr.plan.footprint}
          </span>
        )}
      </figcaption>
      {arr.plan ? (
        <ArrangementPlan
          rects={arr.plan.rects_mm}
          outline={arr.plan.outline_mm}
        />
      ) : (
        <div className="d-noimg big">No plan recorded</div>
      )}
      <p className="d-arr-front">front</p>
      <ol className="d-arr-members" data-testid="arr-members">
        {arr.members.map((m, i) => (
          <li key={i}>
            <span
              className="d-arr-dot"
              style={{ background: MEMBER_COLOURS[i % MEMBER_COLOURS.length] }}
            >
              {i + 1}
            </span>
            {m.has_picture ? (
              <img
                src={`/api/models/${m.model_id}/files/cover.png`}
                alt=""
                loading="lazy"
              />
            ) : (
              <span className="d-noimg" />
            )}
            <span className="d-arr-what">
              <a href={modelHref(m.model_id)} title="its own model">
                {m.code}
              </a>
              <em>
                {m.size_mm
                  ? `${m.size_mm.slice(0, 2).map(cm).join(" × ")} cm · `
                  : ""}
                at {cm(m.x_mm)}, {cm(m.y_mm)} cm · turned{" "}
                {Math.round(m.rot_deg)}°{m.mirror ? " · mirrored" : ""}
                {m.stale ? " · changed since" : ""}
              </em>
            </span>
            <a className="d-link" href={deskHref(m.model_id)}>
              its Desk card
            </a>
          </li>
        ))}
      </ol>
    </figure>
  );
}
