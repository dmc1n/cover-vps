// The drawing desk (ADR-079): the AI sorts, people approve. A queue of every drawing cover in
// order of need, one card per cover (the drawing beside our cover, what the program read, what
// the AIs say), and the actions: approve, reject with a reason, produced, fit after sewing.
// Keys: j / k next / previous, a approve, r reject, p produced, u undo.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ModelDetail } from "./api";
import { Viewer } from "./Viewer";
import { Corrections, RulesBar } from "./DeskCorrect";
import { ProductsPanel, ProductsUpload, type ProductList } from "./DeskProducts";
import "./desk.css";

type Scores = {
  gemini: number | null;
  deepseek: number | null;
  avg: number | null;
};
interface Item {
  id: string;
  code: string;
  drawing: boolean;
  status: string;
  outcome: string | null;
  scores: Scores;
  tags: string[];
  catalogue: string;
  pieces: number;
  vents: number;
  products?: string[];
  has_picture: boolean;
  last: { action: string; by: string; time: number } | null;
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
  reasons: string[];
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
// the drawings' series, and the SUNS catalogue (owner, 7 Oct 2026: every approval at the Desk)
const SERIES = ["C", "S", "D", "L", "R", "T", "U", "SUNS"];
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

async function getJSON<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401) window.dispatchEvent(new Event("login-needed"));
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail ?? `${r.status}`);
  return data as T;
}

export function Desk({ selected }: { selected: string | null }) {
  const [q, setQ] = useState<Queue | null>(null);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState<string>("open");
  const [series, setSeries] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("need");
  const load = useCallback(
    () =>
      getJSON<Queue>("/api/desk")
        .then(setQ)
        .catch((e) => setErr(String(e.message ?? e))),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);

  const items = useMemo(() => {
    const all = q?.items ?? [];
    const shown = all.filter((i) => {
      if (status === "open" && ["approved", "produced"].includes(i.status))
        return false;
      if (status !== "open" && status !== "all" && i.status !== status)
        return false;
      if (series === "SUNS" && !i.id.startsWith("suns-")) return false;
      if (
        series &&
        series !== "SUNS" &&
        !(i.id.startsWith("drawing-") && i.code.toUpperCase().startsWith(series))
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

  const open = (id: string) => (window.location.hash = `#/desk/${id}`);
  const idx = items.findIndex((i) => i.id === selected);
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
      <div className="desk">
        <p className="d-err">{err}</p>
      </div>
    );
  if (!q)
    return (
      <div className="desk">
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
  return (
    <div className="desk">
      <section className="d-top">
        <div className="d-title">
          <h1>Desk</h1>
          <p>
            The AI sorts, people approve. {q.items.length} drawing covers ·{" "}
            <kbd>j</kbd>
            <kbd>k</kbd> move · <kbd>a</kbd> approve · <kbd>r</kbd> reject ·{" "}
            <kbd>p</kbd> produced · <kbd>u</kbd> undo
          </p>
        </div>
        <div className="d-kpis">
          <Kpi label="To review" value={toReview} accent />
          <Kpi label="Approved" value={c.approved ?? 0} />
          <Kpi label="Produced" value={c.produced ?? 0} />
          <Kpi label="Rejected" value={c.rejected ?? 0} />
          <Kpi
            label="Avg AI score"
            value={q.avg_score == null ? "–" : q.avg_score.toFixed(0)}
          />
          {q.spend && (
            <Kpi
              label="AI spend this month"
              value={`€${q.spend.month_eur.toFixed(2)}`}
              sub={`${q.spend.pct.toFixed(0)} % of €${q.spend.budget_eur}`}
              bar={Math.min(q.spend.pct, 100)}
            />
          )}
        </div>
        <RulesBar canAct={q.can_approve} onChanged={load} />
        <ProductsUpload onDone={load} />
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
              {["open", "all", "rejected", "approved", "produced"].map((s) => (
                <button
                  key={s}
                  className={status === s ? "on" : ""}
                  onClick={() => setStatus(s)}
                >
                  {s === "open"
                    ? "To do"
                    : s === "all"
                      ? "All"
                      : STATUS_LABEL[s]}
                </button>
              ))}
            </div>
            <div className="d-chips">
              {SERIES.map((s) => (
                <button
                  key={s}
                  className={series === s ? "on" : ""}
                  onClick={() => setSeries(series === s ? null : s)}
                >
                  {s}
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
          <ul className="d-list">
            {items.map((i) => (
              <li
                key={i.id}
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
                    <Pill status={i.status} />
                  </div>
                  <div className="d-row-sub">
                    <Score label="G" v={i.scores.gemini} />
                    <Score label="D" v={i.scores.deepseek} />
                    <span className={i.pieces > 30 ? "d-flag" : ""}>
                      {i.pieces} pcs
                    </span>
                    <span>{i.vents} vents</span>
                    {i.tags.includes("shape-to-check") && (
                      <span className="d-flag">shape to check</span>
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
              canAct={q.can_approve}
              reasons={q.reasons}
              onChanged={load}
              onNext={() =>
                idx >= 0 && idx + 1 < items.length && open(items[idx + 1].id)
              }
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
  value,
  sub,
  accent,
  bar,
}: {
  label: string;
  value: number | string;
  sub?: string;
  accent?: boolean;
  bar?: number;
}) {
  return (
    <div className={`d-kpi ${accent ? "accent" : ""}`}>
      <span className="d-kpi-label">{label}</span>
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

function Pill({ status }: { status: string }) {
  return (
    <span className={`d-pill s-${status}`}>
      {STATUS_LABEL[status] ?? status}
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
  canAct,
  reasons,
  onChanged,
  onNext,
}: {
  id: string;
  canAct: boolean;
  reasons: string[];
  onChanged: () => void;
  onNext: () => void;
}) {
  const [card, setCard] = useState<Card | null>(null);
  const [model, setModel] = useState<ModelDetail | null>(null);
  const [page, setPage] = useState(0);
  const [zoom, setZoom] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [why, setWhy] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [fitNote, setFitNote] = useState("");
  const [msg, setMsg] = useState("");
  const [allDiffs, setAllDiffs] = useState(false);
  const [allRevs, setAllRevs] = useState(false);
  // "let the AI read it": its job followed here, the outcome shown beside the button
  const [aiJob, setAiJob] = useState<string | null>(null);
  const [aiNote, setAiNote] = useState("");
  const textRef = useRef<HTMLTextAreaElement>(null);
  const load = useCallback(() => {
    getJSON<Card>(`/api/desk/${id}`)
      .then(setCard)
      .catch((e) => setMsg(String(e.message ?? e)));
    api
      .model(id)
      .then(setModel)
      .catch(() => setModel(null));
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);
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

  const act = useCallback(
    async (body: Record<string, unknown>, done: string, next = false) => {
      setMsg("");
      try {
        await getJSON(`/api/desk/${id}`, body);
        setMsg(done);
        setRejecting(false);
        load();
        onChanged();
        if (next) setTimeout(onNext, 350);
      } catch (e) {
        setMsg(String((e as Error).message ?? e));
      }
    },
    [id, load, onChanged, onNext],
  );

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (!canAct || !card) return;
      if (t && ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (e.key === "a") act({ action: "approve" }, "Approved", true);
      if (e.key === "r") {
        setRejecting(true);
        setTimeout(() => textRef.current?.focus(), 50);
      }
      if (e.key === "p")
        act(
          { action: "produced", done: card.desk.status !== "produced" },
          card.desk.status !== "produced" ? "Marked produced" : "Not produced",
        );
      if (e.key === "u") act({ action: "undo" }, "Undone");
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [canAct, card, act]);

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
  return (
    <article className="d-card">
      <div className="d-card-head">
        <div>
          <h2>{card.code}</h2>
          <span className="d-id">{card.id}</span>
        </div>
        <div className="d-head-right">
          {ck.outcome && (
            <span
              className={`d-outcome o-${ck.outcome.replace(/[: ]+/g, "-")}`}
            >
              {OUTCOME_LABEL[ck.outcome] ?? ck.outcome}
            </span>
          )}
          <Score label="G" v={card.scores.gemini} />
          <Score label="D" v={card.scores.deepseek} />
          <Pill status={st.status} />
          {canAct &&
            ck.outcome !== "agreed: same" &&
            st.status !== "approved" &&
            st.status !== "produced" && (
            <button
              className={`d-ai ${aiJob ? "busy" : ""}`}
              disabled={!!aiJob}
              title="The AI reads the drawing: a proposal (about 1–5 cents), marked 'read by the AI', to approve here"
              onClick={async () => {
                setAiNote("");
                try {
                  const r = await api.aiReadDrawing(card.id);
                  setAiJob(r.job.id);
                } catch (e) {
                  setAiNote(String((e as Error).message ?? e));
                }
              }}
            >
              {aiJob ? "AI is reading… (about a minute)" : "Let the AI read it"}
            </button>
          )}
          <a className="d-open" href={`#/model/${card.id}`}>
            Open model ↗
          </a>
        </div>
      </div>

      {(aiJob || aiNote) && (
        <p className={`d-ai-note ${aiJob ? "busy" : ""}`} role="status">
          {aiJob
            ? "The AI is reading the drawing and the program builds its proposal. This card updates by itself."
            : aiNote}
        </p>
      )}
      <div className="d-split">
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
              onClick={() => setZoom(true)}
            />
          ) : (
            <div className="d-noimg big">No drawing found</div>
          )}
        </figure>
        <figure className="d-3d">
          <figcaption>Our cover</figcaption>
          {model ? (
            <Viewer id={card.id} files={model.files} stamp={0} />
          ) : card.has_picture ? (
            <img
              src={`/api/models/${card.id}/files/cover.png`}
              alt="our cover"
            />
          ) : (
            <div className="d-noimg big">No picture</div>
          )}
        </figure>
      </div>

      <div className="d-grid">
        {card.product_list && <ProductsPanel list={card.product_list} />}
        <section className="d-panel">
          <h3>What the program read</h3>
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
        <section className="d-panel">
          <h3>What the AIs say</h3>
          {!g && !ds && <p className="d-muted">Not checked yet.</p>}
          {g && (
            <div className="d-ai">
              <span className="d-ai-who">
                Gemini · looks{ck.gemini_second ? " (second look)" : ""}
              </span>
              <p>{g.summary}</p>
            </div>
          )}
          {ds && (
            <div className="d-ai">
              <span className="d-ai-who">DeepSeek · reads the numbers</span>
              <p>{ds.summary}</p>
            </div>
          )}
          {[...(g?.differences ?? []), ...(ds?.differences ?? [])].length >
            0 && (
            <ul className="d-diffs">
              {[...(g?.differences ?? []), ...(ds?.differences ?? [])]
                .slice(0, allDiffs ? undefined : 6)
                .map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
            </ul>
          )}
          {[...(g?.differences ?? []), ...(ds?.differences ?? [])].length >
            6 && (
            <button className="d-more" onClick={() => setAllDiffs(!allDiffs)}>
              {allDiffs ? "Show fewer" : "Show all differences"}
            </button>
          )}
        </section>
        <section className="d-panel">
          <h3>Pieces</h3>
          <table className="d-table">
            <tbody>
              {card.pieces_list.map((p) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td>×{p.quantity}</td>
                  <td>
                    {p.size_mm?.map((x) => Math.round(x / 10)).join(" × ")} cm
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
                      ? "Show the last 4"
                      : `Show all ${card.revisions.length}`}
                  </button>
                </caption>
              )}
            </table>
          ) : (
            <p className="d-muted">No revisions kept.</p>
          )}
        </section>
        <Corrections
          id={card.id}
          canAct={canAct}
          onChanged={() => {
            load();
            onChanged();
          }}
        />
        <section className="d-panel d-wide">
          <h3>History</h3>
          <ol className="d-timeline">
            {[...st.history].reverse().map((h, i) => (
              <li key={i}>
                <span
                  className={`d-tl-dot a-${h.action.replace(/\s+/g, "-")}`}
                />
                <strong>{h.action}</strong> {h.by && <>by {h.by}</>}{" "}
                <time>{when(h.time)}</time>
                {h.reasons && h.reasons.length > 0 && (
                  <em> · {h.reasons.join(", ")}</em>
                )}
                {h.text && <q>{h.text}</q>}
                {h.fits != null && (
                  <em>
                    {" "}
                    · {h.fits ? "fits" : "does not fit"} {h.note}
                  </em>
                )}
                {h.done != null && (
                  <em> · {h.done ? "produced" : "not produced"}</em>
                )}
              </li>
            ))}
            {!st.history.length && <li className="d-muted">Nothing yet.</li>}
          </ol>
        </section>
      </div>

      <div className="d-actions">
        {!canAct && (
          <span className="d-muted">
            Only Rens, Rick, Wouter or an admin can decide here.
          </span>
        )}
        {canAct && !rejecting && (
          <>
            <button
              className="d-btn d-primary"
              disabled={st.status === "approved" || st.status === "produced"}
              onClick={() => act({ action: "approve" }, "Approved", true)}
            >
              ✓ Approve <kbd>a</kbd>
            </button>
            <button
              className="d-btn d-danger"
              onClick={() => setRejecting(true)}
            >
              ✕ Reject <kbd>r</kbd>
            </button>
            <label
              className={`d-check ${st.status === "approved" || st.status === "produced" ? "" : "off"}`}
            >
              <input
                type="checkbox"
                checked={st.status === "produced"}
                disabled={
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
            <span className="d-fit">
              <input
                placeholder="After sewing: note…"
                value={fitNote}
                onChange={(e) => setFitNote(e.target.value)}
              />
              <button
                className="d-btn d-ghost"
                onClick={() =>
                  act({ action: "fit", fits: true, note: fitNote }, "Fit saved")
                }
              >
                Fits
              </button>
              <button
                className="d-btn d-ghost"
                onClick={() =>
                  act(
                    { action: "fit", fits: false, note: fitNote },
                    "Fit saved",
                  )
                }
              >
                Does not fit
              </button>
            </span>
            {st.history.length > 0 && (
              <button
                className="d-btn d-ghost d-small"
                onClick={() => act({ action: "undo" }, "Undone")}
              >
                Undo <kbd>u</kbd>
              </button>
            )}
          </>
        )}
        {canAct && rejecting && (
          <div className="d-reject">
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
            <textarea
              ref={textRef}
              placeholder="What is wrong? (kept in the history; to change the cover itself, use “Correct this cover”)"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <button
              className="d-btn d-danger"
              onClick={() =>
                act({ action: "reject", reasons: why, text }, "Rejected", true)
              }
            >
              Reject
            </button>
            <button
              className="d-btn d-ghost"
              onClick={() => setRejecting(false)}
            >
              Cancel
            </button>
          </div>
        )}
        {msg && <span className="d-msg">{msg}</span>}
      </div>

      {zoom && (
        <div className="d-zoom" onClick={() => setZoom(false)}>
          <img
            src={`/api/desk/${card.id}/page/${page}`}
            alt="the drawing, large"
          />
        </div>
      )}
    </article>
  );
}
