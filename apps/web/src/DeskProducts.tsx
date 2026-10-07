// The workshop's product list at the Desk (ADR-091): upload an .xlsx, .csv or a .zip of them,
// see what was linked through which column, pick another column and apply again; and on a
// card the products of a drawing cover, or the drawings a SUNS model is linked to.
import { useEffect, useRef, useState } from "react";
import "./desk.css";
import "./desk-products.css";

type Row = Record<string, string>;
export interface ProductsResult {
  kind?: "products";
  file: string;
  files: { file: string; tables?: number; rows?: number; error?: string }[];
  column?: string;
  columns?: string[];
  rows?: number;
  linked_rows?: number;
  covers?: number;
  unmatched?: Row[];
  unmatched_count?: number;
  without_products?: string[];
  twice?: Record<string, string[]>;
  suns?: { linked: number; suggested_only: number };
  pdfs?: { count: number; matched: number; new: string[] };
}
interface Ref {
  id: string;
  code: string;
  product: string;
}
export interface ProductList {
  source?: string;
  column?: string;
  time?: number;
  columns?: string[];
  rows?: string[][];
  suns?: { linked: string[]; suggested: string[] };
  drawings?: { linked: Ref[]; suggested: Ref[] };
}

const SHOWN_ROWS = 12;
const sunsName = (id: string) => id.replace(/^suns-/, "").replace(/-/g, " ");

async function send(file: File | null, column: string): Promise<ProductsResult> {
  const form = new FormData();
  if (file) form.append("file", file);
  if (column) form.append("column", column);
  const r = await fetch("/api/desk-products", { method: "POST", body: form });
  if (r.status === 401) window.dispatchEvent(new Event("login-needed"));
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail ?? `${r.status}`);
  return data as ProductsResult;
}

// the button in the Desk's top bar, and the result under it
export function ProductsUpload({ onDone }: { onDone: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [res, setRes] = useState<ProductsResult | null>(null);
  const [last, setLast] = useState<{ file: string | null; time?: number } | null>(null);
  useEffect(() => {
    fetch("/api/desk-products")
      .then((r) => (r.ok ? r.json() : null))
      .then(setLast)
      .catch(() => setLast(null));
  }, [res]);
  const run = async (file: File | null, column = "") => {
    setBusy(true);
    setErr("");
    try {
      setRes(await send(file, column));
      onDone();
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="dp-upload">
      <div className="dp-bar">
        <button
          className="d-btn d-small"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          {busy ? "Reading the list…" : "Upload product list (Excel)"}
        </button>
        <input
          ref={input}
          type="file"
          hidden
          accept=".xlsx,.xlsm,.csv,.zip,.xls"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) run(f);
          }}
        />
        <span className="d-muted">
          .xlsx, .csv or a .zip of them · links every row to its drawing
          {last?.file && !res && <> · last: {last.file}</>}
        </span>
      </div>
      {err && <p className="d-err dp-err">{err}</p>}
      {res && (
        <ProductsSummary
          res={res}
          busy={busy}
          onColumn={(c) => run(null, c)}
          onClose={() => setRes(null)}
        />
      )}
    </div>
  );
}

export function ProductsSummary({
  res,
  busy,
  onColumn,
  onClose,
}: {
  res: ProductsResult;
  busy?: boolean;
  onColumn?: (column: string) => void;
  onClose?: () => void;
}) {
  const [col, setCol] = useState(res.column ?? "");
  const [allRows, setAllRows] = useState(false);
  useEffect(() => setCol(res.column ?? ""), [res.column]);
  const unmatched = res.unmatched ?? [];
  const heads = unmatched.length
    ? Object.keys(unmatched[0]).filter((k) => !k.startsWith("_"))
    : [];
  const twice = Object.entries(res.twice ?? {});
  return (
    <section className="dp-result" role="status">
      <div className="dp-head">
        <div>
          <strong className="dp-big">
            {res.linked_rows ?? 0} of {res.rows ?? 0} rows
          </strong>{" "}
          linked to {res.covers ?? 0} drawings
          <span className="d-muted"> · {res.file}</span>
        </div>
        {onClose && (
          <button className="d-link" onClick={onClose} aria-label="close">
            ✕
          </button>
        )}
      </div>
      {res.columns && (
        <div className="dp-col">
          <label>
            Link column{" "}
            <select
              value={col}
              onChange={(e) => setCol(e.target.value)}
              disabled={!onColumn}
            >
              {res.columns.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          {onColumn && (
            <button
              className="d-btn d-small"
              disabled={busy || col === res.column}
              onClick={() => onColumn(col)}
            >
              Apply again
            </button>
          )}
          <span className="d-muted">
            the program picked “{res.column}”: its values name the most drawings
          </span>
        </div>
      )}
      <ul className="dp-facts">
        {res.files.map((f) => (
          <li key={f.file} className={f.error ? "bad" : ""}>
            {f.file}:{" "}
            {f.error ?? `${f.rows} rows in ${f.tables} sheet${f.tables === 1 ? "" : "s"}`}
          </li>
        ))}
        {res.suns && (
          <li>
            SUNS models linked: {res.suns.linked}
            {res.suns.suggested_only > 0 &&
              ` · ${res.suns.suggested_only} more only suggested (check them on the cards)`}
          </li>
        )}
        {res.without_products && res.without_products.length > 0 && (
          <li>
            Drawings without a product: {res.without_products.length} (
            {res.without_products.slice(0, 12).join(", ")}
            {res.without_products.length > 12 && " …"})
          </li>
        )}
        {res.pdfs && (
          <li>
            PDFs in the zip: {res.pdfs.count}, matched to existing drawings:{" "}
            {res.pdfs.matched}
            {res.pdfs.new.length > 0 && <>, new: {res.pdfs.new.join(", ")}</>}
          </li>
        )}
      </ul>
      {twice.length > 0 && (
        <div className="dp-warn">
          <strong>One code, two products</strong> — both are on the drawing; worth a look:
          <ul>
            {twice.map(([code, names]) => (
              <li key={code}>
                <b>{code}</b>: {names.join(" · ")}
              </li>
            ))}
          </ul>
        </div>
      )}
      {unmatched.length > 0 && (
        <div className="dp-unmatched">
          <h4>
            Not linked: {res.unmatched_count} rows{" "}
            <span className="d-muted">(no drawing with that code yet)</span>
          </h4>
          <table className="d-table">
            <thead>
              <tr>
                {heads.map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {unmatched.slice(0, allRows ? undefined : SHOWN_ROWS).map((r, i) => (
                <tr key={i}>
                  {heads.map((h) => (
                    <td key={h}>{r[h]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {unmatched.length > SHOWN_ROWS && (
            <button className="d-more" onClick={() => setAllRows(!allRows)}>
              {allRows ? "Show fewer" : `Show all ${unmatched.length}`}
            </button>
          )}
        </div>
      )}
    </section>
  );
}

// a card's Products panel
export function ProductsPanel({ list }: { list: ProductList }) {
  if (list.drawings) {
    const { linked, suggested } = list.drawings;
    return (
      <section className="d-panel d-wide dp-panel">
        <h3>Drawings for this product</h3>
        <DrawingRefs refs={linked} />
        {suggested.length > 0 && (
          <>
            <p className="dp-sub">Suggested (same family, type not certain)</p>
            <DrawingRefs refs={suggested} soft />
          </>
        )}
      </section>
    );
  }
  if (!list.rows?.length) return null;
  const suns = list.suns ?? { linked: [], suggested: [] };
  return (
    <section className="d-panel d-wide dp-panel">
      <h3>Products</h3>
      <div className="dp-scroll">
        <table className="d-table">
          <thead>
            <tr>
              {(list.columns ?? []).map((c) => (
                <th key={c} className={c === list.column ? "link" : ""}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {list.rows.map((r, i) => (
              <tr key={i}>
                {r.map((v, j) => (
                  <td key={j}>{v}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(suns.linked.length > 0 || suns.suggested.length > 0) && (
        <div className="dp-suns">
          {suns.linked.length > 0 && <span className="dp-sub">SUNS models</span>}
          {suns.linked.map((id) => (
            <a key={id} className="dp-chip" href={`#/desk/${id}`}>
              {sunsName(id)}
            </a>
          ))}
          {suns.suggested.length > 0 && (
            <span className="dp-sub">suggested</span>
          )}
          {suns.suggested.map((id) => (
            <a
              key={id}
              className="dp-chip soft"
              href={`#/desk/${id}`}
              title="Same family; the type could not be confirmed from the description"
            >
              {sunsName(id)}?
            </a>
          ))}
        </div>
      )}
      <p className="dp-sub">
        From {list.source} · linked through “{list.column}”
      </p>
    </section>
  );
}

function DrawingRefs({ refs, soft }: { refs: Ref[]; soft?: boolean }) {
  if (!refs.length) return <p className="d-muted">None.</p>;
  return (
    <ul className="dp-refs">
      {refs.map((r) => (
        <li key={r.id}>
          <a className={`dp-chip ${soft ? "soft" : ""}`} href={`#/desk/${r.id}`}>
            {r.code}
            {soft && "?"}
          </a>
          <span>{r.product}</span>
        </li>
      ))}
    </ul>
  );
}
