import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChannelKey,
  Costing,
  CostingProducts,
  Currency,
  PriceMove,
  prices,
  PriceSet,
  PricesState,
  PriceVersion,
} from "./api";

// Prices & costing (ADR-098): materials, labour, the fixed exchange rate, the extra costs and
// the price lists per channel, the costing of every cover. Admins edit a draft, preview which
// prices move, then publish (every version kept, with a rollback); editors look.

type Sub =
  "materials" | "labour" | "rate" | "channels" | "costing" | "versions";
const SUBS: [Sub, string][] = [
  ["materials", "Materials"],
  ["labour", "Labour"],
  ["rate", "Exchange rate"],
  ["channels", "Channels & price lists"],
  ["costing", "Costing"],
  ["versions", "Versions"],
];
const CHANNELS: ChannelKey[] = ["b2c", "b2b"];
const ROUNDING_LABEL: Record<string, string> = {
  none: "none (cents)",
  "0.01": "cents",
  "0.95": "up to .95",
  "0.99": "up to .99",
  "0.90": "up to .90",
  "1": "whole euros",
  "5": "up to 5 euros",
  "10": "up to 10 euros",
};
const eur = (x: number) =>
  `€ ${x.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const idr = (x: number) => `Rp ${Math.round(x).toLocaleString("en-GB")}`;
const when = (t: number) => new Date(t * 1000).toLocaleString();

export function Prices({ canEdit }: { canEdit: boolean }) {
  const [state, setState] = useState<PricesState | null>(null);
  const [doc, setDoc] = useState<PriceSet | null>(null);
  const [dirty, setDirty] = useState(false);
  const [sub, setSub] = useState<Sub>("materials");
  const [msg, setMsg] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [moves, setMoves] = useState<{
    rows: PriceMove[];
    changed: number;
    total: number;
  } | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    prices
      .state()
      .then((s) => {
        setState(s);
        setDoc(structuredClone(s.draft?.data ?? s.current));
        setErrors(s.draft_errors);
        setDirty(false);
      })
      .catch((e) => setMsg(String(e)));
  }, []);
  useEffect(load, [load]);
  if (!state || !doc) return <p className="muted">{msg || "Loading…"}</p>;
  const edit = canEdit && state.can_edit;
  const update = (fn: (d: PriceSet) => void) => {
    const copy = structuredClone(doc);
    fn(copy);
    setDoc(copy);
    setDirty(true);
    setMoves(null);
  };
  const rate = doc.exchange.idr_per_eur || 1;
  const ctx: Ctx = { doc, update, edit, state, rate };
  const run = async (what: () => Promise<void>) => {
    setBusy(true);
    setMsg("");
    try {
      await what();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };
  const saveDraft = async () => {
    const r = await prices.saveDraft(doc);
    setErrors(r.errors);
    setDirty(false);
    setState({ ...state, draft: r.draft, draft_errors: r.errors });
    return r.errors;
  };
  const pub = state.published;
  return (
    <div className="prices">
      <section className="card">
        <h3>Prices &amp; costing</h3>
        <p className="muted">
          Purchase prices, labour, the exchange rate and the price lists for
          consumers (B2C) and business customers (B2B). The configurator, the
          shop and every costing use the <b>published</b> version.{" "}
          {edit
            ? "Change numbers below, look at which prices move, then publish."
            : "You can look; an admin changes the prices."}
        </p>
        <p className="prices-status">
          {pub ? (
            <>
              Live: <b>version {pub.version}</b> by {pub.username},{" "}
              {when(pub.created)}
              {pub.note ? ` — ${pub.note}` : ""}
            </>
          ) : (
            <>
              Live: <b>the documented defaults</b> (nothing published yet)
            </>
          )}
          {state.current.indicative && (
            <span className="pill warn">indicative (placeholder prices)</span>
          )}
          {state.draft && (
            <span className="pill">
              draft by {state.draft.by}, {when(state.draft.time)} — not live
            </span>
          )}
          {dirty && <span className="pill warn">unsaved changes</span>}
        </p>
        {errors.length > 0 && (
          <ul className="error">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
        {edit && (
          <div className="row">
            <button
              disabled={busy || !dirty}
              onClick={() => run(async () => void (await saveDraft()))}
            >
              Save draft
            </button>
            <button
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const p = await prices.preview(doc);
                  setErrors(p.errors);
                  setMoves(p.errors.length ? null : p);
                })
              }
            >
              Preview changes
            </button>
            <input
              className="note"
              placeholder="What changed (for the history)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <button
              className="primary"
              disabled={busy || (!dirty && !state.draft)}
              onClick={() =>
                run(async () => {
                  if (dirty) {
                    const errs = await saveDraft();
                    if (errs.length) return;
                  }
                  const r = await prices.publish(note);
                  setNote("");
                  setMoves(null);
                  load();
                  setMsg(
                    `Published version ${r.version}: ${r.prices_changed} prices changed.`,
                  );
                })
              }
            >
              Publish
            </button>
            <button
              disabled={busy || (!state.draft && !dirty)}
              onClick={() =>
                run(async () => {
                  await prices.discard();
                  load();
                  setMoves(null);
                  setMsg("Draft discarded.");
                })
              }
            >
              Discard draft
            </button>
          </div>
        )}
        {msg && <p className="muted">{msg}</p>}
      </section>
      {moves && <Moves moves={moves} />}
      <nav className="tabs">
        {SUBS.map(([k, label]) => (
          <button
            key={k}
            className={sub === k ? "active" : ""}
            onClick={() => setSub(k)}
          >
            {label}
          </button>
        ))}
      </nav>
      <section className="tab">
        {sub === "materials" && <Materials {...ctx} />}
        {sub === "labour" && <Labour {...ctx} />}
        {sub === "rate" && <Rate {...ctx} />}
        {sub === "channels" && <Channels {...ctx} />}
        {sub === "costing" && (
          <CostingView hasDraft={!!state.draft} dirty={dirty} />
        )}
        {sub === "versions" && (
          <Versions
            edit={edit}
            onChange={() => {
              load();
              setMsg("");
            }}
          />
        )}
      </section>
    </div>
  );
}

interface Ctx {
  doc: PriceSet;
  update: (fn: (d: PriceSet) => void) => void;
  edit: boolean;
  state: PricesState;
  rate: number;
}

function Num({
  value,
  onChange,
  edit,
  step = "any",
  label,
}: {
  value: number;
  onChange: (v: number) => void;
  edit: boolean;
  step?: string;
  label?: string;
}) {
  return (
    <input
      type="number"
      step={step}
      aria-label={label}
      className="num"
      value={Number.isFinite(value) ? value : ""}
      disabled={!edit}
      onChange={(e) =>
        onChange(e.target.value === "" ? 0 : Number(e.target.value))
      }
    />
  );
}

function Txt({
  value,
  onChange,
  edit,
  label,
  wide,
}: {
  value: string;
  onChange: (v: string) => void;
  edit: boolean;
  label?: string;
  wide?: boolean;
}) {
  return (
    <input
      aria-label={label}
      className={wide ? "wide" : ""}
      value={value}
      disabled={!edit}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function Pick({
  value,
  options,
  onChange,
  edit,
  labels,
  label,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
  edit: boolean;
  labels?: Record<string, string>;
  label?: string;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      disabled={!edit}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {labels?.[o] ?? o}
        </option>
      ))}
    </select>
  );
}

/** A price in its own currency, and the other currency beside it. */
function Both({
  amount,
  currency,
  rate,
}: {
  amount: number;
  currency: Currency;
  rate: number;
}) {
  return (
    <span className="muted both">
      {currency === "IDR" ? eur(amount / rate) : idr(amount * rate)}
    </span>
  );
}

function Materials({ doc, update, edit, state, rate }: Ctx) {
  const c = state.choices;
  return (
    <>
      <section className="card">
        <h4>Fabrics</h4>
        <p className="muted">
          Price per metre of roll. The costing takes the metres from each
          cover's cut plan and adds the waste; a fabric on another roll width is
          scaled. The configurator picks the fabric that offers the customer's
          colour, else the first.
        </p>
        <table className="list prices-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name / quality</th>
              <th>Colours</th>
              <th>Price / m</th>
              <th>Currency</th>
              <th>Other currency</th>
              <th>Roll width mm</th>
              <th>Waste %</th>
              {edit && <th />}
            </tr>
          </thead>
          <tbody>
            {doc.fabrics.map((f, i) => (
              <tr key={i} className="static">
                <td>
                  <Txt
                    value={f.code}
                    edit={edit}
                    label="fabric code"
                    onChange={(v) =>
                      update((d) => void (d.fabrics[i].code = v))
                    }
                  />
                </td>
                <td>
                  <Txt
                    value={f.name}
                    edit={edit}
                    wide
                    label="fabric name"
                    onChange={(v) =>
                      update((d) => void (d.fabrics[i].name = v))
                    }
                  />
                </td>
                <td>
                  <Txt
                    value={f.colours}
                    edit={edit}
                    wide
                    label="colours"
                    onChange={(v) =>
                      update((d) => void (d.fabrics[i].colours = v))
                    }
                  />
                </td>
                <td>
                  <Num
                    value={f.price}
                    edit={edit}
                    label="fabric price"
                    onChange={(v) =>
                      update((d) => void (d.fabrics[i].price = v))
                    }
                  />
                </td>
                <td>
                  <Pick
                    value={f.currency}
                    options={c.currencies}
                    edit={edit}
                    onChange={(v) =>
                      update(
                        (d) => void (d.fabrics[i].currency = v as Currency),
                      )
                    }
                  />
                </td>
                <td>
                  <Both amount={f.price} currency={f.currency} rate={rate} />
                </td>
                <td>
                  <Num
                    value={f.roll_width_mm}
                    edit={edit}
                    onChange={(v) =>
                      update((d) => void (d.fabrics[i].roll_width_mm = v))
                    }
                  />
                </td>
                <td>
                  <Num
                    value={f.waste_pct}
                    edit={edit}
                    onChange={(v) =>
                      update((d) => void (d.fabrics[i].waste_pct = v))
                    }
                  />
                </td>
                {edit && (
                  <td>
                    <button
                      disabled={doc.fabrics.length < 2}
                      onClick={() => update((d) => void d.fabrics.splice(i, 1))}
                    >
                      Remove
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {edit && (
          <button
            onClick={() =>
              update(
                (d) =>
                  void d.fabrics.push({
                    ...d.fabrics[0],
                    code: `fabric-${d.fabrics.length + 1}`,
                    name: "New fabric",
                    colours: "",
                  }),
              )
            }
          >
            Add fabric
          </button>
        )}
      </section>
      <section className="card">
        <h4>Components</h4>
        <p className="muted">
          Everything else that goes into a cover, counted per something the
          cover has (its vents, its metres of cord, ...). The balloon and the
          frame are sold next to the cover, at their own price.
        </p>
        <table className="list prices-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>Counted</th>
              <th>Purchase price</th>
              <th>Currency</th>
              <th>Other currency</th>
              {edit && <th />}
            </tr>
          </thead>
          <tbody>
            {doc.components.map((x, i) => (
              <tr key={i} className="static">
                <td>
                  <Txt
                    value={x.code}
                    edit={edit}
                    label="component code"
                    onChange={(v) =>
                      update((d) => void (d.components[i].code = v))
                    }
                  />
                </td>
                <td>
                  <Txt
                    value={x.name}
                    edit={edit}
                    wide
                    label="component name"
                    onChange={(v) =>
                      update((d) => void (d.components[i].name = v))
                    }
                  />
                </td>
                <td>
                  <Pick
                    value={x.per}
                    options={c.per}
                    labels={c.per_label}
                    edit={edit}
                    onChange={(v) =>
                      update((d) => void (d.components[i].per = v))
                    }
                  />
                </td>
                <td>
                  <Num
                    value={x.price}
                    edit={edit}
                    label={`${x.code} price`}
                    onChange={(v) =>
                      update((d) => void (d.components[i].price = v))
                    }
                  />
                </td>
                <td>
                  <Pick
                    value={x.currency}
                    options={c.currencies}
                    edit={edit}
                    onChange={(v) =>
                      update(
                        (d) => void (d.components[i].currency = v as Currency),
                      )
                    }
                  />
                </td>
                <td>
                  <Both amount={x.price} currency={x.currency} rate={rate} />
                </td>
                {edit && (
                  <td>
                    <button
                      disabled={[
                        "vent_set",
                        "cord",
                        "elastic",
                        "balloon",
                        "frame",
                      ].includes(x.code)}
                      title="the program counts this one itself"
                      onClick={() =>
                        update((d) => void d.components.splice(i, 1))
                      }
                    >
                      Remove
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {edit && (
          <button
            onClick={() =>
              update(
                (d) =>
                  void d.components.push({
                    code: `part-${d.components.length + 1}`,
                    name: "New component",
                    per: "cover",
                    price: 0,
                    currency: "EUR",
                  }),
              )
            }
          >
            Add component
          </button>
        )}
      </section>
    </>
  );
}

function Labour({ doc, update, edit, state, rate }: Ctx) {
  const c = state.choices;
  const lab = doc.labour;
  return (
    <section className="card">
      <h4>Labour</h4>
      <p className="muted">
        The hourly rate of the workshop and the minutes per operation. Each
        operation is counted per something the cover has.
      </p>
      <div className="row">
        <label className="inline">
          Hourly rate{" "}
          <Num
            value={lab.rate}
            edit={edit}
            label="hourly rate"
            onChange={(v) => update((d) => void (d.labour.rate = v))}
          />
        </label>
        <Pick
          value={lab.currency}
          options={c.currencies}
          edit={edit}
          label="labour currency"
          onChange={(v) =>
            update((d) => void (d.labour.currency = v as Currency))
          }
        />
        <Both amount={lab.rate} currency={lab.currency} rate={rate} />
      </div>
      <table className="list prices-table">
        <thead>
          <tr>
            <th>Code</th>
            <th>Operation</th>
            <th>Counted</th>
            <th>Minutes</th>
            {edit && <th />}
          </tr>
        </thead>
        <tbody>
          {lab.operations.map((o, i) => (
            <tr key={i} className="static">
              <td>
                <Txt
                  value={o.code}
                  edit={edit}
                  label="operation code"
                  onChange={(v) =>
                    update((d) => void (d.labour.operations[i].code = v))
                  }
                />
              </td>
              <td>
                <Txt
                  value={o.name}
                  edit={edit}
                  wide
                  label="operation name"
                  onChange={(v) =>
                    update((d) => void (d.labour.operations[i].name = v))
                  }
                />
              </td>
              <td>
                <Pick
                  value={o.per}
                  options={c.per}
                  labels={c.per_label}
                  edit={edit}
                  onChange={(v) =>
                    update((d) => void (d.labour.operations[i].per = v))
                  }
                />
              </td>
              <td>
                <Num
                  value={o.minutes}
                  edit={edit}
                  label={`${o.code} minutes`}
                  onChange={(v) =>
                    update((d) => void (d.labour.operations[i].minutes = v))
                  }
                />
              </td>
              {edit && (
                <td>
                  <button
                    onClick={() =>
                      update((d) => void d.labour.operations.splice(i, 1))
                    }
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {edit && (
        <button
          onClick={() =>
            update(
              (d) =>
                void d.labour.operations.push({
                  code: `op-${d.labour.operations.length + 1}`,
                  name: "New operation",
                  per: "cover",
                  minutes: 0,
                }),
            )
          }
        >
          Add operation
        </button>
      )}
    </section>
  );
}

function Rate({ doc, update, edit }: Ctx) {
  const ex = doc.exchange;
  return (
    <section className="card">
      <h4>Exchange rate</h4>
      <p className="muted">
        A fixed rate, entered by hand: every cost in rupiah is converted with
        it, and both currencies are shown.
      </p>
      <div className="row">
        <label className="inline">
          1 EUR ={" "}
          <Num
            value={ex.idr_per_eur}
            edit={edit}
            label="rupiah per euro"
            onChange={(v) => update((d) => void (d.exchange.idr_per_eur = v))}
          />{" "}
          IDR
        </label>
        <label className="inline">
          Date{" "}
          <input
            type="date"
            value={ex.date}
            disabled={!edit}
            aria-label="rate date"
            onChange={(e) =>
              update((d) => void (d.exchange.date = e.target.value))
            }
          />
        </label>
        <label className="inline">
          Note{" "}
          <Txt
            value={ex.note}
            edit={edit}
            wide
            label="rate note"
            onChange={(v) => update((d) => void (d.exchange.note = v))}
          />
        </label>
      </div>
      <p className="muted">
        1 IDR = {eur(1 / (ex.idr_per_eur || 1)).replace("€ 0.00", "€ <0.01")} ·
        1,000,000 IDR = {eur(1e6 / (ex.idr_per_eur || 1))}
      </p>
      <h4>Indicative</h4>
      <label className="check">
        <input
          type="checkbox"
          checked={doc.indicative}
          disabled={!edit}
          onChange={(e) =>
            update((d) => void (d.indicative = e.target.checked))
          }
        />{" "}
        The prices are still placeholders: the shop says "indicative" next to
        every price. Switch this off when the real prices are in.
      </label>
    </section>
  );
}

function Channels({ doc, update, edit, state, rate }: Ctx) {
  const c = state.choices;
  const [products, setProducts] = useState<CostingProducts | null>(null);
  const [newKey, setNewKey] = useState<Record<string, string>>({});
  useEffect(() => {
    prices
      .products()
      .then(setProducts)
      .catch(() => setProducts(null));
  }, []);
  const names = useMemo(
    () =>
      Object.fromEntries((products?.models ?? []).map((m) => [m.id, m.name])),
    [products],
  );
  return (
    <div className="prices-channels">
      {CHANNELS.map((k) => {
        const ch = doc.channels[k];
        const set = (fn: (x: PriceSet["channels"][ChannelKey]) => void) =>
          update((d) => fn(d.channels[k]));
        const ex = ch.extras;
        return (
          <section key={k} className="card" data-channel={k}>
            <h4>
              {k.toUpperCase()}: {ch.name}
            </h4>
            <label className="setting">
              Name{" "}
              <Txt
                value={ch.name}
                edit={edit}
                onChange={(v) => set((x) => void (x.name = v))}
              />
            </label>
            <h5>Extra costs (lines of their own, per cover)</h5>
            <label className="setting">
              Shipping
              <span>
                <Num
                  value={ex.shipping.amount}
                  edit={edit}
                  label={`${k} shipping`}
                  onChange={(v) =>
                    set((x) => void (x.extras.shipping.amount = v))
                  }
                />
                <Pick
                  value={ex.shipping.currency}
                  options={c.currencies}
                  edit={edit}
                  onChange={(v) =>
                    set(
                      (x) => void (x.extras.shipping.currency = v as Currency),
                    )
                  }
                />
              </span>
            </label>
            <label className="setting">
              Import duties
              <span>
                <Pick
                  value={ex.duties.mode}
                  options={c.duty_modes}
                  edit={edit}
                  labels={{
                    pct: "% of cost + shipping",
                    fixed: "fixed amount",
                  }}
                  onChange={(v) =>
                    set(
                      (x) => void (x.extras.duties.mode = v as "pct" | "fixed"),
                    )
                  }
                />
                <Num
                  value={ex.duties.value}
                  edit={edit}
                  label={`${k} duties`}
                  onChange={(v) => set((x) => void (x.extras.duties.value = v))}
                />
                {ex.duties.mode === "fixed" && (
                  <Pick
                    value={ex.duties.currency ?? "EUR"}
                    options={c.currencies}
                    edit={edit}
                    onChange={(v) =>
                      set(
                        (x) => void (x.extras.duties.currency = v as Currency),
                      )
                    }
                  />
                )}
              </span>
            </label>
            <label className="setting">
              Packaging
              <span>
                <Num
                  value={ex.packaging.amount}
                  edit={edit}
                  label={`${k} packaging`}
                  onChange={(v) =>
                    set((x) => void (x.extras.packaging.amount = v))
                  }
                />
                <Pick
                  value={ex.packaging.currency}
                  options={c.currencies}
                  edit={edit}
                  onChange={(v) =>
                    set(
                      (x) => void (x.extras.packaging.currency = v as Currency),
                    )
                  }
                />
                {ex.packaging.currency === "IDR" && (
                  <Both
                    amount={ex.packaging.amount}
                    currency="IDR"
                    rate={rate}
                  />
                )}
              </span>
            </label>
            <h5>Price list</h5>
            <label className="setting">
              Rule
              <span>
                <Pick
                  value={ch.method}
                  options={c.methods}
                  edit={edit}
                  label={`${k} method`}
                  onChange={(v) =>
                    set((x) => void (x.method = v as "markup" | "margin"))
                  }
                />
                <Num
                  value={ch.pct}
                  edit={edit}
                  label={`${k} percentage`}
                  onChange={(v) => set((x) => void (x.pct = v))}
                />
                %
                <Pick
                  value={ch.base}
                  options={c.bases}
                  edit={edit}
                  labels={{
                    landed: "on cost + extra costs",
                    cost: "on the cost price only",
                  }}
                  onChange={(v) =>
                    set((x) => void (x.base = v as "landed" | "cost"))
                  }
                />
              </span>
            </label>
            <label className="setting">
              Rounding
              <Pick
                value={ch.rounding}
                options={c.roundings}
                labels={ROUNDING_LABEL}
                edit={edit}
                label={`${k} rounding`}
                onChange={(v) => set((x) => void (x.rounding = v))}
              />
            </label>
            <label className="setting">
              VAT %
              <span>
                <Num
                  value={ch.vat_pct}
                  edit={edit}
                  onChange={(v) => set((x) => void (x.vat_pct = v))}
                />
                <label className="check">
                  <input
                    type="checkbox"
                    checked={ch.show_vat}
                    disabled={!edit}
                    onChange={(e) =>
                      set((x) => void (x.show_vat = e.target.checked))
                    }
                  />{" "}
                  prices shown incl. VAT
                </label>
              </span>
            </label>
            <p className="muted">
              {ch.method === "markup"
                ? `Price = base × ${(1 + ch.pct / 100).toFixed(3)}`
                : `Price = base ÷ ${(1 - ch.pct / 100).toFixed(3)} (a ${ch.pct} % margin of the price)`}
              , {ch.show_vat ? "incl." : "ex"} VAT, rounded{" "}
              {ROUNDING_LABEL[ch.rounding] ?? ch.rounding}.
            </p>
            <h5>Fixed prices ({ch.show_vat ? "incl." : "ex"} VAT)</h5>
            <table className="list">
              <tbody>
                {Object.entries(ch.fixed).map(([key, v]) => (
                  <tr key={key} className="static">
                    <td>
                      {key}
                      <div className="muted">{names[key] ?? ""}</div>
                    </td>
                    <td>
                      <Num
                        value={v}
                        edit={edit}
                        label={`${k} fixed ${key}`}
                        onChange={(n) => set((x) => void (x.fixed[key] = n))}
                      />
                    </td>
                    {edit && (
                      <td>
                        <button
                          onClick={() => set((x) => void delete x.fixed[key])}
                        >
                          Remove
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {edit && (
              <div className="row">
                <input
                  list="price-products"
                  placeholder="model id, balloon or frame"
                  aria-label={`${k} fixed product`}
                  value={newKey[k] ?? ""}
                  onChange={(e) =>
                    setNewKey({ ...newKey, [k]: e.target.value })
                  }
                />
                <button
                  disabled={!newKey[k]}
                  onClick={() => {
                    const key = (newKey[k] ?? "").trim();
                    if (key)
                      set((x) => void (x.fixed[key] = x.fixed[key] ?? 0));
                    setNewKey({ ...newKey, [k]: "" });
                  }}
                >
                  Add fixed price
                </button>
              </div>
            )}
          </section>
        );
      })}
      <datalist id="price-products">
        <option value="balloon">Balloon</option>
        <option value="frame">Frame</option>
        {(products?.models ?? []).map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </datalist>
    </div>
  );
}

function Moves({
  moves,
}: {
  moves: { rows: PriceMove[]; changed: number; total: number };
}) {
  const [all, setAll] = useState(false);
  const rows = all ? moves.rows : moves.rows.slice(0, 40);
  const cell = (b: number, a: number) =>
    Math.abs(a - b) < 0.005 ? (
      <span className="muted">{eur(a)}</span>
    ) : (
      <>
        <span className="muted">{eur(b)}</span> → <b>{eur(a)}</b>
      </>
    );
  return (
    <section className="card prices-moves">
      <h4>
        {moves.changed} of {moves.total} prices move
      </h4>
      <p className="muted">
        Before = the live prices, after = this draft. Covers, the configurator's
        products at their default sizes, the balloon and the frame. B2C incl.
        VAT, B2B as its price list shows it.
      </p>
      {moves.changed > 0 && (
        <table className="list">
          <thead>
            <tr>
              <th>Product</th>
              <th>Kind</th>
              <th>Cost price</th>
              <th>B2C</th>
              <th>B2B</th>
              <th>Δ B2C</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="static">
                <td>
                  {r.name}
                  <div className="muted">{r.key}</div>
                </td>
                <td>{r.kind}</td>
                <td>{cell(r.before.cost, r.after.cost)}</td>
                <td>{cell(r.before.b2c, r.after.b2c)}</td>
                <td>{cell(r.before.b2b, r.after.b2b)}</td>
                <td
                  className={
                    r.delta_b2c > 0 ? "up" : r.delta_b2c < 0 ? "down" : ""
                  }
                >
                  {r.delta_b2c > 0 ? "+" : ""}
                  {r.delta_b2c.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {moves.rows.length > rows.length && (
        <button onClick={() => setAll(true)}>
          Show all {moves.rows.length}
        </button>
      )}
    </section>
  );
}

function CostingView({
  hasDraft,
  dirty,
}: {
  hasDraft: boolean;
  dirty: boolean;
}) {
  const [products, setProducts] = useState<CostingProducts | null>(null);
  const [mode, setMode] = useState<"model" | "configurator">("model");
  const [model, setModel] = useState("");
  const [product, setProduct] = useState("sofa");
  const [sizes, setSizes] = useState<Record<string, number | boolean>>({});
  const [set, setSet] = useState<"current" | "draft">("current");
  const [c, setC] = useState<Costing | null>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    prices
      .products()
      .then((p) => {
        setProducts(p);
        if (p.models.length) setModel((m) => m || p.models[0].id);
      })
      .catch((e) => setMsg(String(e)));
  }, []);
  const query = useMemo((): Record<string, string> | null => {
    if (mode === "model") return model ? { model, set } : null;
    return { product, sizes: JSON.stringify(sizes), set };
  }, [mode, model, product, sizes, set]);
  useEffect(() => {
    if (!query) return;
    const t = setTimeout(() => {
      prices
        .costing(query)
        .then((x) => {
          setC(x);
          setMsg("");
        })
        .catch((e) => {
          setC(null);
          setMsg(String(e));
        });
    }, 250);
    return () => clearTimeout(t);
  }, [query]);
  const spec = products?.configurator.find((p) => p.product === product);
  const qs = query ? new URLSearchParams(query).toString() : "";
  return (
    <>
      <section className="card">
        <div className="row">
          <label className="check">
            <input
              type="radio"
              checked={mode === "model"}
              onChange={() => setMode("model")}
            />{" "}
            A cover (catalogue, drawing, arrangement)
          </label>
          <label className="check">
            <input
              type="radio"
              checked={mode === "configurator"}
              onChange={() => setMode("configurator")}
            />{" "}
            A configurator product
          </label>
          <span className="spacer" />
          <label className="inline">
            Prices{" "}
            <select
              value={set}
              aria-label="price set"
              onChange={(e) => setSet(e.target.value as "current" | "draft")}
            >
              <option value="current">live</option>
              <option value="draft" disabled={!hasDraft}>
                draft{hasDraft ? "" : " (none)"}
              </option>
            </select>
          </label>
        </div>
        {dirty && set === "draft" && (
          <p className="muted">
            Save the draft to see your latest changes here.
          </p>
        )}
        {mode === "model" ? (
          <div className="row">
            <input
              list="costing-models"
              className="wide"
              aria-label="cover to cost"
              value={model}
              onChange={(e) => setModel(e.target.value.trim())}
              placeholder="model id"
            />
            <datalist id="costing-models">
              {(products?.models ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.kind}: {m.name}
                </option>
              ))}
            </datalist>
            <span className="muted">
              {products?.models.length ?? 0} calculated covers
            </span>
          </div>
        ) : (
          <div className="row">
            <select
              value={product}
              aria-label="configurator product"
              onChange={(e) => {
                setProduct(e.target.value);
                setSizes({});
              }}
            >
              {(products?.configurator ?? []).map((p) => (
                <option key={p.product} value={p.product}>
                  {p.label}
                </option>
              ))}
            </select>
            {spec?.fields.map((f) =>
              typeof f.default === "boolean" ? (
                <label key={f.key} className="check">
                  <input
                    type="checkbox"
                    checked={Boolean(sizes[f.key] ?? f.default)}
                    onChange={(e) =>
                      setSizes({ ...sizes, [f.key]: e.target.checked })
                    }
                  />{" "}
                  {f.key}
                </label>
              ) : (
                <label key={f.key} className="inline">
                  {f.key.replace(/_cm$/, "").replace(/_/g, " ")}{" "}
                  <input
                    type="number"
                    className="num"
                    min={f.min ?? undefined}
                    max={f.max ?? undefined}
                    value={Number(sizes[f.key] ?? f.default)}
                    onChange={(e) =>
                      setSizes({ ...sizes, [f.key]: Number(e.target.value) })
                    }
                  />{" "}
                  cm
                </label>
              ),
            )}
          </div>
        )}
        {msg && <p className="error">{msg}</p>}
      </section>
      {c && (
        <section className="card costing" data-testid="costing">
          <div className="row">
            <h4>
              {c.name}
              {c.model ? <span className="muted"> · {c.model}</span> : null}
            </h4>
            <span className="spacer" />
            {c.indicative && <span className="pill warn">indicative</span>}
            <a className="button" href={`/api/prices/costing.csv?${qs}`}>
              CSV
            </a>
            <a
              className="button"
              href={`/api/prices/costing.pdf?${qs}`}
              target="_blank"
              rel="noreferrer"
            >
              PDF
            </a>
          </div>
          <p className="muted">
            {c.facts.piece} pieces · {c.facts.fabric_m?.toFixed(2)} m of roll in
            the cut plan · {c.facts.seam_m?.toFixed(1)} m of seam ·{" "}
            {c.facts.hem_m?.toFixed(1)} m of hem · {c.facts.vent} vents ·{" "}
            {c.facts.cord_m?.toFixed(1)} m of cord · fabric {c.fabric.name} · 1
            EUR = {c.exchange.idr_per_eur.toLocaleString("en-GB")} IDR (
            {c.exchange.date})
          </p>
          <table className="list costing-lines">
            <thead>
              <tr>
                <th>Item</th>
                <th>How</th>
                <th>Quantity</th>
                <th>Unit price</th>
                <th>EUR</th>
                <th>IDR</th>
              </tr>
            </thead>
            <tbody>
              {c.lines.map((x) => (
                <tr key={x.section + x.code} className={`static ${x.section}`}>
                  <td>
                    <span className="muted">{x.section}</span> {x.name}
                  </td>
                  <td className="muted">{x.note}</td>
                  <td>
                    {x.qty.toLocaleString("en-GB", {
                      maximumFractionDigits: 3,
                    })}{" "}
                    {x.unit}
                  </td>
                  <td>
                    {x.currency === "IDR"
                      ? idr(x.unit_price)
                      : eur(x.unit_price)}
                  </td>
                  <td>{eur(x.eur)}</td>
                  <td className="muted">{idr(x.idr)}</td>
                </tr>
              ))}
              <tr className="static total">
                <td colSpan={2}>
                  Cost price{" "}
                  <span className="muted">
                    (fabric {eur(c.fabric_eur)} · components{" "}
                    {eur(c.components_eur)} · labour {eur(c.labour_eur)},{" "}
                    {Math.round(c.labour_minutes)} min)
                  </span>
                </td>
                <td />
                <td />
                <td>{eur(c.cost_eur)}</td>
                <td>{idr(c.cost_idr)}</td>
              </tr>
            </tbody>
          </table>
          <div className="prices-channels">
            {Object.entries(c.channels).map(([k, ch]) => (
              <div key={k} className="card channel-price" data-channel={k}>
                <h5>
                  {k.toUpperCase()}: {ch.name}
                </h5>
                <table className="list">
                  <tbody>
                    <tr className="static">
                      <td>Cost price</td>
                      <td>{eur(c.cost_eur)}</td>
                    </tr>
                    {ch.extras.map((e) => (
                      <tr key={e.code} className="static">
                        <td>+ {e.name}</td>
                        <td>{eur(e.eur)}</td>
                      </tr>
                    ))}
                    <tr className="static total">
                      <td>Landed cost</td>
                      <td>{eur(ch.landed_eur)}</td>
                    </tr>
                    <tr className="static">
                      <td>
                        Price ex VAT{" "}
                        <span className="muted">
                          {ch.fixed
                            ? "(fixed price)"
                            : `(${ch.method} ${ch.pct} % on the ${ch.base === "landed" ? "landed" : "cost"} price)`}
                        </span>
                      </td>
                      <td>{eur(ch.net_eur)}</td>
                    </tr>
                    <tr className="static">
                      <td>VAT {ch.vat_pct} %</td>
                      <td>{eur(ch.vat_eur)}</td>
                    </tr>
                    <tr className="static">
                      <td>Price incl. VAT</td>
                      <td>{eur(ch.gross_eur)}</td>
                    </tr>
                    <tr className="static total">
                      <td>
                        Shown price{" "}
                        <span className="muted">
                          ({ch.show_vat ? "incl." : "ex"} VAT)
                        </span>
                      </td>
                      <td>{eur(ch.shown_eur)}</td>
                    </tr>
                    <tr className="static">
                      <td>Margin</td>
                      <td>
                        {eur(ch.margin_eur)}{" "}
                        <span className="muted">({ch.margin_pct} %)</span>
                      </td>
                    </tr>
                    {Object.entries(ch.accessories).map(([code, a]) => (
                      <tr key={code} className="static">
                        <td>
                          Sold with it: {a.count} × {code}
                        </td>
                        <td>{eur(a.shown_eur)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function Versions({ edit, onChange }: { edit: boolean; onChange: () => void }) {
  const [vs, setVs] = useState<PriceVersion[] | null>(null);
  const [msg, setMsg] = useState("");
  const load = useCallback(() => {
    prices
      .versions()
      .then((r) => setVs(r.versions))
      .catch((e) => setMsg(String(e)));
  }, []);
  useEffect(load, [load]);
  if (!vs) return <p className="muted">{msg || "Loading…"}</p>;
  if (!vs.length)
    return (
      <p className="muted">
        Nothing published yet: the shop uses the documented defaults.
      </p>
    );
  return (
    <section className="card">
      <h4>Published versions</h4>
      {msg && <p className="error">{msg}</p>}
      <table className="list">
        <thead>
          <tr>
            <th>Version</th>
            <th>When</th>
            <th>Who</th>
            <th>Note</th>
            <th>Fabric / m</th>
            <th>B2C</th>
            <th>B2B</th>
            {edit && <th />}
          </tr>
        </thead>
        <tbody>
          {vs.map((v, i) => (
            <tr key={v.version} className="static">
              <td>
                {v.version}
                {i === 0 && <span className="pill">live</span>}
              </td>
              <td>{when(v.created)}</td>
              <td>{v.username}</td>
              <td>{v.note}</td>
              <td>
                {v.data.fabrics[0]?.price} {v.data.fabrics[0]?.currency}
              </td>
              <td>
                {v.data.channels.b2c.method} {v.data.channels.b2c.pct} %
              </td>
              <td>
                {v.data.channels.b2b.method} {v.data.channels.b2b.pct} %
              </td>
              {edit && (
                <td>
                  {i > 0 && (
                    <button
                      onClick={async () => {
                        if (
                          !window.confirm(
                            `Make version ${v.version} live again?`,
                          )
                        )
                          return;
                        try {
                          await prices.rollback(v.version);
                          load();
                          onChange();
                        } catch (e) {
                          setMsg(String(e));
                        }
                      }}
                    >
                      Roll back to this
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
