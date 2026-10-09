import { useMemo, useRef, useState } from "react";
import {
  ChannelKey,
  PriceImportOptions,
  PriceImportReport,
  PriceImportRow,
  PriceImportTarget,
  prices,
} from "./api";

// Import prices (Excel), ADR-113: the owner's price list (retail prices incl. VAT) as fixed
// prices for our covers. Upload → look at what matched (exact / probable), choose by hand what
// did not → put the prices in the DRAFT. Nothing goes live here: Preview changes → Publish.

const eur = (x: number | null | undefined) =>
  x == null
    ? "—"
    : `€ ${x.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const KIND: Record<string, string> = {
  drawing: "drawing cover",
  catalogue: "SUNS model",
  arrangement: "arrangement",
  accessory: "sold with a cover",
  order: "order",
  other: "cover",
};
const STATUS: Record<PriceImportRow["status"], string> = {
  exact: "exact",
  probable: "probable",
  ambiguous: "which cover?",
  none: "not found",
  no_price: "no price",
};

export function PriceImport({
  beforeApply,
  onApplied,
}: {
  /** save the page's unsaved numbers first, so the import does not overwrite them */
  beforeApply: () => Promise<boolean>;
  onApplied: (msg: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [rep, setRep] = useState<PriceImportReport | null>(null);
  const [channel, setChannel] = useState<ChannelKey>("b2c");
  const [off, setOff] = useState<Set<string>>(new Set());
  const [picks, setPicks] = useState<Record<number, string>>({});
  const run = async (what: () => Promise<void>) => {
    setBusy(true);
    setErr("");
    try {
      await what();
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };
  const look = (file: File | null, opts: Partial<PriceImportOptions>) =>
    run(async () => {
      const r = await prices.importLook(file, {
        channel,
        incl_vat: "auto",
        ...(rep && !file
          ? {
              upload: rep.upload,
              incl_vat: String(rep.incl_vat),
              price_column: rep.price_column,
              id_columns: rep.id_columns,
            }
          : {}),
        ...opts,
      });
      setRep(r);
      setChannel(r.channel);
      setOff(new Set());
      setPicks({});
    });
  const names = useMemo(
    () => Object.fromEntries((rep?.covers ?? []).map((c) => [c.id, c])),
    [rep],
  );
  const matched = rep?.rows.filter((r) => r.targets.length > 0) ?? [];
  const open = rep?.rows.filter((r) => r.targets.length === 0) ?? [];
  const chosenIds = new Set<string>();
  for (const r of matched)
    for (const t of r.targets)
      if (t.chosen && t.stored != null && !off.has(t.id)) chosenIds.add(t.id);
  const pickList = Object.entries(picks)
    .filter(([, id]) => id && names[id])
    .map(([i, id]) => ({ index: Number(i), id }));
  for (const p of pickList) chosenIds.add(p.id);
  const unit = rep?.channel_shows_vat ? "incl. VAT" : "ex VAT";
  return (
    <section className="card price-import" data-testid="price-import">
      <h4>Import prices (Excel)</h4>
      <p className="help">
        Have a price list in Excel? Upload it: every row is matched to our
        covers (by code like S40, the drawing's “Cover 66”, or the SUNS name)
        and its price becomes that cover's <b>fixed price</b> in the channel.
        You see every match first; the prices go into the <b>draft</b>, so
        nothing is live until you preview and publish. .xlsx, .csv or a .zip of
        them.
      </p>
      <div className="row">
        <label className="inline">
          Price list
          <select
            aria-label="import channel"
            value={channel}
            disabled={busy}
            onChange={(e) => {
              const ch = e.target.value as ChannelKey;
              setChannel(ch);
              if (rep) look(null, { channel: ch });
            }}
          >
            <option value="b2c">B2C — consumers (webshop)</option>
            <option value="b2b">B2B — Sunsit, dealers</option>
          </select>
        </label>
        <button
          className="primary"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          {busy ? "Reading…" : "Upload price list (Excel)"}
        </button>
        <input
          ref={input}
          type="file"
          hidden
          data-testid="price-import-file"
          accept=".xlsx,.xlsm,.csv,.zip,.xls"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) look(f, { channel, incl_vat: "auto", upload: "" });
          }}
        />
      </div>
      {err && <p className="error">{err}</p>}
      {rep && (
        <>
          <div className="pi-summary" role="status">
            <b>{rep.file}</b>: {rep.rows.length} rows —{" "}
            {(["exact", "probable", "ambiguous", "none", "no_price"] as const)
              .filter((k) => rep.counts[k])
              .map((k) => `${rep.counts[k]} ${STATUS[k]}`)
              .join(", ")}
            .
          </div>
          <div className="pi-choices">
            <label className="inline">
              Prices in column
              <select
                aria-label="price column"
                value={rep.price_column}
                disabled={busy}
                onChange={(e) => look(null, { price_column: e.target.value })}
              >
                {rep.columns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                    {rep.price_columns.includes(c) ? "" : " (no prices?)"}
                  </option>
                ))}
              </select>
            </label>
            <label className="inline">
              The sheet's prices are
              <select
                aria-label="prices incl or ex VAT"
                value={String(rep.incl_vat)}
                disabled={busy}
                onChange={(e) => look(null, { incl_vat: e.target.value })}
              >
                <option value="true">incl. VAT</option>
                <option value="false">ex VAT</option>
              </select>
            </label>
            <span className="inline pi-cols">
              Covers named in:
              {rep.columns
                .filter((c) => c !== rep.price_column)
                .map((c) => (
                  <label key={c} className="check">
                    <input
                      type="checkbox"
                      checked={rep.id_columns.includes(c)}
                      disabled={busy}
                      onChange={(e) => {
                        const cols = e.target.checked
                          ? [...rep.id_columns, c]
                          : rep.id_columns.filter((x) => x !== c);
                        if (cols.length) look(null, { id_columns: cols });
                      }}
                    />{" "}
                    {c}
                  </label>
                ))}
            </span>
          </div>
          <p className="help">
            {rep.channel_name} shows its prices {unit}
            {rep.channel_shows_vat
              ? "; "
              : `; a price incl. VAT is stored ex VAT (÷ ${1 + rep.vat_pct / 100}), exactly, so the price incl. VAT stays the sheet's to the cent; `}
            no rounding is applied to a fixed price. <b>Exact</b> = named by its
            code, drawing number or own name; <b>probable</b> = a SUNS model
            whose family and type match the description, or one the product list
            links to that drawing: please check those.
          </p>
          <h5>Matched ({matched.length} rows)</h5>
          <table className="list pi-table" data-testid="pi-matched">
            <thead>
              <tr>
                <th></th>
                <th>Row in the sheet</th>
                <th>Our cover</th>
                <th className="num">In the sheet</th>
                <th className="num">Stored ({unit})</th>
                <th className="num">Shown incl. VAT</th>
                <th className="num">Now incl. VAT</th>
              </tr>
            </thead>
            <tbody>
              {matched.flatMap((r) =>
                r.targets.map((t, i) => (
                  <TargetRow
                    key={`${r.index}-${t.id}`}
                    row={r}
                    t={t}
                    first={i === 0}
                    span={r.targets.length}
                    on={t.chosen && t.stored != null && !off.has(t.id)}
                    busy={busy}
                    toggle={(v) => {
                      const s = new Set(off);
                      if (v) s.delete(t.id);
                      else s.add(t.id);
                      setOff(s);
                    }}
                  />
                )),
              )}
            </tbody>
          </table>
          {rep.conflicts.length > 0 && (
            <>
              <h5>One cover, two prices ({rep.conflicts.length})</h5>
              <p className="help">
                These covers are named by more than one row with different
                prices. Choose which row's price counts, or leave the cover out.
              </p>
              <table className="list pi-table" data-testid="pi-conflicts">
                <tbody>
                  {rep.conflicts.map((c) => {
                    const chosen = c.rows.find((x) => picks[x.index] === c.id);
                    return (
                      <tr key={c.id} className="static">
                        <td>
                          <b>{c.name}</b>
                          <div className="muted">{c.id}</div>
                        </td>
                        <td>
                          <select
                            aria-label={`price for ${c.id}`}
                            value={chosen ? String(chosen.index) : ""}
                            onChange={(e) => {
                              const p = { ...picks };
                              for (const x of c.rows)
                                if (p[x.index] === c.id) delete p[x.index];
                              if (e.target.value !== "")
                                p[Number(e.target.value)] = c.id;
                              setPicks(p);
                            }}
                          >
                            <option value="">leave this cover out</option>
                            {c.rows.map((x) => (
                              <option key={x.index} value={x.index}>
                                {eur(x.price_given)} — row {x.line}:{" "}
                                {x.label.slice(0, 50)}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
          {open.length > 0 && (
            <>
              <h5>Not matched or not sure ({open.length} rows)</h5>
              <p className="help">
                Choose the cover by hand (type a code, a name or an id), or
                leave the row out.
              </p>
              <table className="list pi-table" data-testid="pi-open">
                <thead>
                  <tr>
                    <th>Row in the sheet</th>
                    <th className="num">In the sheet</th>
                    <th>Why</th>
                    <th>Choose a cover</th>
                  </tr>
                </thead>
                <tbody>
                  {open.map((r) => (
                    <OpenRow
                      key={r.index}
                      row={r}
                      value={picks[r.index] ?? ""}
                      busy={busy}
                      known={(id) => names[id]?.name}
                      onPick={(id) => setPicks({ ...picks, [r.index]: id })}
                    />
                  ))}
                </tbody>
              </table>
              <datalist id="pi-covers">
                {rep.covers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </datalist>
            </>
          )}
          <div className="row pi-apply">
            <button
              className="primary"
              disabled={busy || chosenIds.size === 0}
              onClick={() =>
                run(async () => {
                  if (!(await beforeApply())) return;
                  const r = await prices.importApply({
                    upload: rep.upload,
                    channel: rep.channel,
                    incl_vat: String(rep.incl_vat),
                    price_column: rep.price_column,
                    id_columns: rep.id_columns,
                    exclude: [...off],
                    picks: pickList,
                  });
                  setRep(null);
                  onApplied(
                    `${r.count} prices put in the draft — ${r.note}. Nothing is live yet: Preview changes, then Publish.`,
                  );
                })
              }
            >
              Put {chosenIds.size} prices in the draft
            </button>
            <button disabled={busy} onClick={() => setRep(null)}>
              Cancel
            </button>
            <span className="muted">
              Not published: afterwards <b>Preview changes</b> shows every price
              that moves, then <b>Publish</b>.
            </span>
          </div>
        </>
      )}
    </section>
  );
}

function TargetRow({
  row,
  t,
  first,
  span,
  on,
  busy,
  toggle,
}: {
  row: PriceImportRow;
  t: PriceImportTarget;
  first: boolean;
  span: number;
  on: boolean;
  busy: boolean;
  toggle: (on: boolean) => void;
}) {
  const why = t.conflict
    ? "two prices for this cover: choose below"
    : t.dropped
      ? `left out: ${t.dropped}`
      : t.same_as != null
        ? "same price as a row above"
        : t.stored == null
          ? row.note || "no price"
          : t.why;
  const can = t.chosen && t.stored != null;
  const diff =
    t.current && t.shown_incl != null ? t.shown_incl - t.current.incl : null;
  return (
    <tr className={`static${on ? "" : " pi-off"}`}>
      <td>
        <input
          type="checkbox"
          aria-label={`import ${t.id}`}
          checked={on}
          disabled={busy || !can}
          onChange={(e) => toggle(e.target.checked)}
        />
      </td>
      {first && (
        <td rowSpan={span} className="pi-row">
          <span className="muted">row {row.line}</span> {row.label}
          {row.price_raw && (
            <div className="muted">price cell: “{row.price_raw}”</div>
          )}
        </td>
      )}
      <td>
        <span className={`pill pi-${t.confidence}`}>{t.confidence}</span>{" "}
        <b>{t.name}</b>
        <div className="muted">
          {KIND[t.kind] ?? t.kind} · {t.id}
          {t.calculated ? "" : " · not calculated yet"}
        </div>
        <div className="muted pi-why">{why}</div>
      </td>
      <td className="num">{first ? eur(row.price_given) : ""}</td>
      <td className="num">
        {t.stored == null
          ? "—"
          : t.stored.toLocaleString("en-GB", { maximumFractionDigits: 6 })}
      </td>
      <td className="num">{eur(t.shown_incl)}</td>
      <td className="num">
        {eur(t.current?.incl)}
        {t.current?.fixed && <div className="muted">fixed now</div>}
        {diff != null && Math.abs(diff) >= 0.005 && (
          <div className={diff > 0 ? "up" : "down"}>
            {diff > 0 ? "+" : "−"}
            {eur(Math.abs(diff))}
          </div>
        )}
      </td>
    </tr>
  );
}

function OpenRow({
  row,
  value,
  busy,
  known,
  onPick,
}: {
  row: PriceImportRow;
  value: string;
  busy: boolean;
  known: (id: string) => string | undefined;
  onPick: (id: string) => void;
}) {
  const name = value ? known(value) : undefined;
  const why =
    row.note ||
    (row.status === "none" ? "no cover with this code or name" : "");
  return (
    <tr className="static">
      <td className="pi-row">
        <span className="muted">row {row.line}</span> {row.label}
      </td>
      <td className="num">{eur(row.price_given)}</td>
      <td>
        <span className={`pill pi-${row.status}`}>{STATUS[row.status]}</span>
        {why && <div className="muted pi-why">{why}</div>}
      </td>
      <td>
        {row.price_given == null ? (
          <span className="muted">no price to import</span>
        ) : (
          <>
            {row.candidates.length > 0 && (
              <select
                aria-label={`candidates for row ${row.line}`}
                value={row.candidates.some((c) => c.id === value) ? value : ""}
                disabled={busy}
                onChange={(e) => onPick(e.target.value)}
              >
                <option value="">— leave out —</option>
                {row.candidates.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
            <input
              list="pi-covers"
              aria-label={`cover for row ${row.line}`}
              placeholder={
                row.candidates.length ? "or another cover…" : "code, name or id"
              }
              value={value}
              disabled={busy}
              onChange={(e) => onPick(e.target.value.trim())}
            />
            {value && (
              <div className={name ? "muted" : "error"}>
                {name ?? "no such cover"}
              </div>
            )}
          </>
        )}
      </td>
    </tr>
  );
}
