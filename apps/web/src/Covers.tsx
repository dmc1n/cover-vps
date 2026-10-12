// Covers → All covers and New cover (ADR-124, step 8 of docs/plans/studio-ui.md).
// All covers: the old Models table and Catalogue cards as one page with a Table / Cards switch.
// One filter row serves both views (search, category, cover grade, status, tag, sort), the
// selection and the batch bar work in both, and the filters stay when the view changes.
// New cover: the three uploads (a 3D file, a drawing, reference pairs) on one page.
// Since ADR-126 the Table can show every cover's price (cost, B2C, B2B, margin, fixed or
// calculated; live or draft): `?prices=live|draft` in the address; a price opens the cover's
// Price & shop tab. Editors and admins (as the prices' API); there is no separate price page.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  fileUrl,
  ModelBrief,
  PriceRow,
  prices,
  Step,
  STEP_LABEL,
  STEPS,
} from "./api";
import { BatchBar } from "./Catalogue";
import { DrawingUpload } from "./DrawingUpload";
import { FilterRow, Tpl } from "./layout";
import { ReferenceUpload } from "./Learning";
import { modelHref } from "./nav";
import { useSession } from "./Session";

type Sort = "name" | "grade" | "stretch" | "size" | "b2c" | "margin";
type PriceCols = "" | "live" | "draft";
const eur = (x: number) =>
  `€ ${x.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const GRADE_ORDER = { ready: 0, check: 1, failed: 2 };

const title = (id: string) =>
  id
    .replace(/^suns-/, "")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

/** Does a model pass the filters? (the old table's and the old cards' rules, together) */
function passes(
  m: ModelBrief,
  f: {
    q: string;
    category: string;
    grade: string;
    status: string;
    tag: string;
  },
): boolean {
  const q = f.q.trim().toLowerCase();
  const text =
    `${m.id} ${m.tags.join(" ")} ${m.notes} ${m.family ?? ""}`.toLowerCase();
  return (
    (!q ||
      text.includes(q) ||
      m.id.includes(q.replace(/\s+/g, "-")) ||
      q.split(/\s+/).every((w) => text.includes(w))) &&
    (!f.category ||
      (f.category === "-"
        ? !m.category
        : (m.category ?? "") === f.category ||
          (m.category ?? "").startsWith(`${f.category} ›`))) &&
    (!f.grade || m.grade === f.grade) &&
    (!f.status || m.status === f.status) &&
    (!f.tag || m.tags.includes(f.tag))
  );
}

export function AllCovers({
  cards,
  priceCols: colsIn = "",
}: {
  cards: boolean;
  priceCols?: string;
}) {
  const { user } = useSession();
  const mayPrices = !!user && user.role !== "viewer";
  const wanted = colsIn === "1" ? "live" : colsIn; // ?prices=1: the live prices
  const priceCols: PriceCols =
    mayPrices && !cards && (wanted === "live" || wanted === "draft")
      ? wanted
      : "";
  const [rows, setRows] = useState<Record<string, PriceRow> | null>(null);
  const [units, setUnits] = useState<Record<string, { show_vat: boolean }>>({});
  const [priceMsg, setPriceMsg] = useState("");
  useEffect(() => {
    if (!priceCols) return;
    let current = true; // a slower answer for the other choice is ignored (Codex)
    setRows(null);
    prices
      .list(priceCols === "draft" ? "draft" : "current")
      .then((r) => {
        if (!current) return;
        setRows(r.rows);
        setUnits(r.units);
        setPriceMsg(
          priceCols === "draft" && r.set !== "draft"
            ? "There is no draft: the live prices are shown."
            : "",
        );
      })
      .catch((e) => current && setPriceMsg(String(e)));
    return () => {
      current = false;
    };
  }, [priceCols]);
  const setCols = (v: PriceCols) => {
    window.location.hash = v ? `#/covers/all?prices=${v}` : "#/covers/all";
  };
  const [models, setModels] = useState<ModelBrief[] | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [grade, setGrade] = useState("");
  const [status, setStatus] = useState("");
  const [tag, setTag] = useState("");
  const [sort, setSort] = useState<Sort>("name");
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const load = useCallback(() => {
    api
      .models()
      .then(setModels)
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);
  const all = models ?? [];
  const cats = useMemo(
    () =>
      [
        ...new Set(all.map((m) => m.category).filter(Boolean)),
      ].sort() as string[],
    [all],
  );
  const groups = [...new Set(cats.map((c) => c.split(" › ")[0]))];
  const tags = useMemo(
    () => [...new Set(all.flatMap((m) => m.tags))].sort(),
    [all],
  );
  const shown = useMemo(() => {
    const list = all.filter((m) =>
      passes(m, { q, category, grade, status, tag }),
    );
    const vol = (m: ModelBrief) =>
      m.size_mm ? m.size_mm[0] * m.size_mm[1] * m.size_mm[2] : 0;
    const price = (m: ModelBrief) => rows?.[m.id]?.b2c.shown ?? -1;
    const margin = (m: ModelBrief) => rows?.[m.id]?.b2c.margin_pct ?? -999;
    return list.sort((a, b) =>
      sort === "b2c" && rows
        ? price(b) - price(a) || a.id.localeCompare(b.id)
        : sort === "margin" && rows
          ? margin(a) - margin(b) || a.id.localeCompare(b.id)
          : sort === "grade"
            ? GRADE_ORDER[a.grade] - GRADE_ORDER[b.grade] ||
              a.id.localeCompare(b.id)
            : sort === "stretch"
              ? (a.max_stretch_pct ?? 999) - (b.max_stretch_pct ?? 999)
              : sort === "size"
                ? vol(b) - vol(a)
                : a.id.localeCompare(b.id),
    );
  }, [all, q, category, grade, status, tag, sort, rows]);
  const selected = shown.filter((m) => picked[m.id]);
  const allPicked = shown.length > 0 && shown.every((m) => picked[m.id]);
  const pickAll = (on: boolean) =>
    setPicked({
      ...picked,
      ...Object.fromEntries(shown.map((m) => [m.id, on])),
    });
  const pick = (id: string, on: boolean) => setPicked({ ...picked, [id]: on });
  const count = (g: string) => all.filter((m) => m.grade === g).length;
  const filtered = !!(q || category || grade || status || tag);
  return (
    <Tpl
      kind="list"
      title="All covers"
      intro="Every model and its cover. A row or a card opens the cover; tick some to run them together."
      actions={
        <>
          <span className="seg" role="group" aria-label="View">
            <a
              href="#/covers/all"
              className={cards ? "" : "on"}
              aria-current={cards ? undefined : "true"}
            >
              Table
            </a>
            <a
              href="#/covers/all?view=cards"
              className={cards ? "on" : ""}
              aria-current={cards ? "true" : undefined}
            >
              Cards
            </a>
          </span>
          {user?.role !== "viewer" && (
            <a className="btn primary" href="#/covers/new">
              + New cover
            </a>
          )}
        </>
      }
    >
      {models && (
        <h2 className="count-line">
          {all.length} covers: {count("ready")} ready, {count("check")} to
          check, {count("failed")} failed
        </h2>
      )}
      {error && <p className="error">{error}</p>}
      <FilterRow
        count={
          models && (
            <>
              {shown.length} shown
              {filtered && (
                <>
                  {" · "}
                  <button
                    className="link"
                    onClick={() => {
                      setQ("");
                      setCategory("");
                      setGrade("");
                      setStatus("");
                      setTag("");
                    }}
                  >
                    clear filters
                  </button>
                </>
              )}
            </>
          )
        }
      >
        <label className="pick-all" title="Select every cover shown">
          <input
            type="checkbox"
            aria-label="Select all shown"
            checked={allPicked}
            onChange={(e) => pickAll(e.target.checked)}
          />
        </label>
        <input
          className="search"
          type="search"
          placeholder="Search name, tag, note or family…"
          aria-label="Search covers"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          value={category}
          aria-label="Category"
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">all categories</option>
          {groups.map((g) => (
            <optgroup key={g} label={g}>
              <option value={g}>all {g}</option>
              {cats
                .filter((c) => c.startsWith(`${g} ›`))
                .map((c) => (
                  <option key={c} value={c}>
                    {c.split(" › ")[1]} (
                    {all.filter((m) => m.category === c).length})
                  </option>
                ))}
            </optgroup>
          ))}
          <option value="-">no category</option>
        </select>
        <select
          value={grade}
          aria-label="Cover"
          onChange={(e) => setGrade(e.target.value)}
        >
          <option value="">any cover</option>
          <option value="ready">ready</option>
          <option value="check">to check</option>
          <option value="failed">failed</option>
        </select>
        <select
          value={status}
          aria-label="Status"
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">any status</option>
          <option>draft</option>
          <option>checked</option>
          <option>production</option>
        </select>
        <select
          value={tag}
          aria-label="Tag"
          onChange={(e) => setTag(e.target.value)}
        >
          <option value="">all tags</option>
          {tags.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <select
          value={sort}
          aria-label="Sort"
          onChange={(e) => setSort(e.target.value as Sort)}
        >
          <option value="name">sort by name</option>
          <option value="grade">sort by cover (ready first)</option>
          <option value="stretch">sort by stretch</option>
          <option value="size">sort by size</option>
          {priceCols && <option value="b2c">sort by B2C price</option>}
          {priceCols && (
            <option value="margin">sort by margin (lowest first)</option>
          )}
        </select>
        {mayPrices && !cards && (
          <select
            value={priceCols}
            aria-label="Prices"
            title="Show every cover's cost, prices and margin"
            onChange={(e) => setCols(e.target.value as PriceCols)}
          >
            <option value="">no prices</option>
            <option value="live">prices: live</option>
            <option value="draft">prices: draft</option>
          </select>
        )}
      </FilterRow>
      {priceCols && priceMsg && <p className="muted">{priceMsg}</p>}
      {selected.length > 0 && (
        <div className="selbar">
          <BatchBar selected={selected} onDone={load} />
          <button className="sm ghost" onClick={() => pickAll(false)}>
            Clear selection
          </button>
        </div>
      )}
      {!models ? (
        !error && <p className="muted">Loading…</p>
      ) : !models.length ? (
        <p className="muted">No covers yet: Covers → New cover.</p>
      ) : cards ? (
        <Cards models={shown} picked={picked} pick={pick} />
      ) : (
        <Table
          models={shown}
          picked={picked}
          pick={pick}
          prices={priceCols ? (rows ?? {}) : null}
          units={units}
        />
      )}
    </Tpl>
  );
}

type PickProps = {
  models: ModelBrief[];
  picked: Record<string, boolean>;
  pick: (id: string, on: boolean) => void;
};

function Table({
  models,
  picked,
  pick,
  prices: pr,
  units = {},
}: PickProps & {
  prices: Record<string, PriceRow> | null;
  units?: Record<string, { show_vat: boolean }>;
}) {
  // the unit of the set shown (a draft may show a channel differently from the live set)
  const vatOf = (k: string) =>
    units[k] ? (units[k].show_vat ? "incl. VAT" : "ex VAT") : "";
  const cell = (id: string, child: React.ReactNode) => (
    <td className="nowrap price-cell">
      <a href={modelHref(id, "price")} onClick={(e) => e.stopPropagation()}>
        {child}
      </a>
    </td>
  );
  return (
    <div className="table-wrap">
      <table className="list">
        <thead>
          <tr>
            <th aria-label="Selected" />
            <th>Model</th>
            <th>Cover</th>
            <th>Category</th>
            <th>Status</th>
            <th>Size (cm)</th>
            {/* with the prices on, the technical columns make room for them */}
            {!pr && (
              <>
                <th>Steps done</th>
                <th>Panels</th>
                <th>Worst stretch</th>
                <th>Warnings</th>
              </>
            )}
            {pr && (
              <>
                <th>Cost</th>
                <th>B2C {vatOf("b2c")}</th>
                <th>B2B {vatOf("b2b")}</th>
                <th>Margin B2C</th>
                <th>Source</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr
              key={m.id}
              className={picked[m.id] ? "picked" : ""}
              onClick={() => (window.location.hash = modelHref(m.id))}
            >
              <td onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  aria-label={`Select ${m.id}`}
                  checked={!!picked[m.id]}
                  onChange={(e) => pick(m.id, e.target.checked)}
                />
              </td>
              <td>
                <a href={modelHref(m.id)}>{m.id}</a>
                {m.tags.map((t) => (
                  <span key={t} className="badge">
                    {t}
                  </span>
                ))}
              </td>
              <td title={m.reasons.join("\n")}>
                <span className={`badge grade-${m.grade}`}>{m.grade}</span>
                {m.no_cover && (
                  <span
                    className="badge no-cover"
                    title={
                      m.no_cover_reason || "not in the shop, not on the Desk"
                    }
                  >
                    no cover
                  </span>
                )}
              </td>
              <td className="nowrap">
                {m.category ? m.category.split(" › ")[1] : ""}
              </td>
              <td>
                <span className={`badge status-${m.status}`}>{m.status}</span>
              </td>
              <td>
                {m.size_mm
                  ? m.size_mm.map((v) => (v / 10).toFixed(0)).join(" × ")
                  : "–"}
              </td>
              {!pr && (
                <>
                  <td>
                    <Steps done={m.steps_done} />
                  </td>
                  <td>{m.panels ?? "–"}</td>
                  <td>
                    {m.max_stretch_pct != null
                      ? `${m.max_stretch_pct.toFixed(1)} %`
                      : "–"}
                  </td>
                  <td>{m.warnings.length || ""}</td>
                </>
              )}
              {pr &&
                (pr[m.id] ? (
                  <>
                    {cell(m.id, eur(pr[m.id].cost))}
                    {cell(m.id, eur(pr[m.id].b2c.shown))}
                    {cell(m.id, eur(pr[m.id].b2b.shown))}
                    {cell(m.id, <>{pr[m.id].b2c.margin_pct} %</>)}
                    {cell(
                      m.id,
                      pr[m.id].b2c.fixed || pr[m.id].b2b.fixed
                        ? `fixed ${[
                            pr[m.id].b2c.fixed && "B2C",
                            pr[m.id].b2b.fixed && "B2B",
                          ]
                            .filter(Boolean)
                            .join(", ")}`
                        : "calculated",
                    )}
                  </>
                ) : (
                  <td colSpan={5} className="muted">
                    not calculated
                  </td>
                ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Cards({ models, picked, pick }: PickProps) {
  return (
    <div className="gallery">
      {models.map((m) => (
        <div
          key={m.id}
          className={`product-wrap ${picked[m.id] ? "picked" : ""}`}
        >
          <label className="pick" title="Select">
            <input
              type="checkbox"
              aria-label={`Select ${m.id}`}
              checked={!!picked[m.id]}
              onChange={(e) => pick(m.id, e.target.checked)}
            />
          </label>
          <a
            className="product"
            href={modelHref(m.id)}
            title={m.reasons.join("\n")}
          >
            <div className="pics">
              {m.files.includes("product.jpg") ? (
                <img
                  loading="lazy"
                  src={fileUrl(m.id, "product.jpg")}
                  alt="product"
                />
              ) : (
                <div className="nopic">no photo</div>
              )}
              {m.files.includes("cover.png") ? (
                <img
                  loading="lazy"
                  src={fileUrl(m.id, "cover.png")}
                  alt="cover"
                />
              ) : (
                <div className="nopic">no cover yet</div>
              )}
            </div>
            <div className="name">{title(m.id)}</div>
            <div className="facts">
              <span className={`badge grade-${m.grade}`}>
                {m.grade === "check" ? "to check" : m.grade}
              </span>
              <span className={`badge status-${m.status}`}>{m.status}</span>
              {m.no_cover && <span className="badge no-cover">no cover</span>}
              {m.category && (
                <span className="badge">{m.category.split(" › ")[1]}</span>
              )}
              {m.tags.map((t) => (
                <span key={t} className="badge">
                  {t}
                </span>
              ))}
              {m.size_mm && (
                <span>
                  {m.size_mm.map((v) => Math.round(v / 10)).join("×")} cm
                </span>
              )}
              {m.panels != null && <span>{m.panels} panels</span>}
              {m.max_stretch_pct != null && (
                <span className={m.max_stretch_pct > 2 ? "bad" : "ok"}>
                  {m.max_stretch_pct.toFixed(1)} %
                </span>
              )}
              {m.roll_length_mm ? (
                <span>{(m.roll_length_mm / 1000).toFixed(1)} m fabric</span>
              ) : null}
            </div>
          </a>
        </div>
      ))}
    </div>
  );
}

function Steps({ done }: { done: Step[] }) {
  return (
    <span className="steps">
      {STEPS.map((s) => (
        <span
          key={s}
          className={done.includes(s) ? "step done" : "step"}
          title={STEP_LABEL[s]}
        />
      ))}
    </span>
  );
}

/** Covers → New cover: the three ways in, on one page. */
export function NewCover() {
  return (
    <Tpl
      kind="form"
      title="New cover"
      intro={
        <>
          Three ways in: a 3D file of the furniture, a drawing (PDF), or pairs
          of your own drawings and 3D models to learn from. What the pairs gave
          is on <a href="#/covers/learning">Learning</a>.
        </>
      }
    >
      <div className="uploads">
        <Upload />
        <DrawingUpload />
        <ReferenceUpload />
      </div>
    </Tpl>
  );
}

function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [units, setUnits] = useState("");
  const [up, setUp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const send = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const r = await api.upload(file, units, up);
      window.location.hash = modelHref(r.model_id);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  };
  return (
    <section className="card upload">
      <h2>From a 3D file</h2>
      <p className="muted">
        STEP, IGES, STL, OBJ, PLY or GLB: the complete product, or only the
        cover surface. After the import the program shows which one it thinks it
        is; you confirm, and the rest runs by itself: cover, seams, patterns and
        the cut pieces.
      </p>
      <div className="row">
        <input
          type="file"
          aria-label="3D file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <label>
          Units{" "}
          <select value={units} onChange={(e) => setUnits(e.target.value)}>
            <option value="">from the file</option>
            <option>mm</option>
            <option>cm</option>
            <option>m</option>
            <option>in</option>
          </select>
        </label>
        <label>
          Up{" "}
          <select value={up} onChange={(e) => setUp(e.target.value)}>
            <option value="">automatic</option>
            <option>z</option>
            <option>y</option>
            <option>x</option>
            <option>-z</option>
            <option>-y</option>
            <option>-x</option>
          </select>
        </label>
        <button className="primary" disabled={!file || busy} onClick={send}>
          {busy ? "Uploading…" : "Upload and run"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
