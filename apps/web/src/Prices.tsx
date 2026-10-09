import { ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  ChannelKey,
  ChannelPrice,
  Costing,
  CostingProducts,
  CostLine,
  Currency,
  PriceCheck,
  PriceMove,
  prices,
  PriceSet,
  PricesState,
  PriceVersion,
} from "./api";
import { PriceImport } from "./PriceImport";

// Prices & costing (ADR-098): materials, labour, the fixed exchange rate, the extra costs and
// the price lists per channel, the costing of every cover. Admins edit a draft, preview which
// prices move, then publish (every version kept, with a rollback); editors look.
//
// Every tab says what it is for and what to fill in; every field has its unit, a one-line help
// and a "placeholder" mark while it still holds the documented default ("to confirm" in
// config/defaults.yaml). Live examples beside the settings cost one real cover with the numbers
// as they are typed (POST /api/prices/check), so the owner sees what a number does.

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
const BUILT_IN = ["vent_set", "cord", "elastic", "balloon", "frame"];
const EXAMPLE_KEY = "prices.example";
const eur = (x: number) =>
  `€ ${x.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const idr = (x: number) => `Rp ${Math.round(x).toLocaleString("en-GB")}`;
const num = (x: number | undefined, digits = 1) =>
  (x ?? 0).toLocaleString("en-GB", { maximumFractionDigits: digits });
const money = (x: number, c: Currency) => (c === "IDR" ? idr(x) : eur(x));
const when = (t: number) => new Date(t * 1000).toLocaleString();

// What each built-in line is, in the workshop, with a realistic example.
const COMPONENT_HELP: Record<string, string> = {
  vent_set:
    "One set per air vent: the plastic insert that keeps it open, the membrane, the logo. Example € 3.75; a cover with 4 vents uses 4 sets.",
  cord: "Drawcord in the hem channel, per metre: the hem's length plus a piece to tie. Example € 0.65/m.",
  elastic:
    "Only for covers with an elastic hem instead of a cord, per metre of hem. Example € 0.85/m.",
  balloon:
    "Goes under a table cover so rain runs off. Not in the cover's cost price: sold next to the cover at its own price (Channels). Example € 14.50.",
  frame:
    "A gabled frame under a table cover, like the balloon; sold next to the cover. Example € 64.50.",
};
const OPERATION_HELP: Record<string, string> = {
  cut_setup:
    "Once per cover: fetch the roll, load the cut file, lay the fabric on the cutting table. Example 12.5 min.",
  piece:
    "For every piece cut: cutting, pen marks, sorting, handling. Example 6.5 min; 8 pieces = 52 min.",
  seam: "Double stitching, per metre of seam (each seam counted once). Example 2.5 min/m; 12 m of seam = 30 min.",
  vent: "Per air vent: cut the opening, sew the hood, fit the insert and the logo. Example 9.5 min.",
  hem: "Per metre of hem: sewing the hem with its cord channel and threading the cord. Example 1.75 min/m.",
  pack: "Once per cover: folding, bagging and boxing. Example 6.5 min.",
};

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
  const [products, setProducts] = useState<CostingProducts | null>(null);
  const [example, setExampleState] = useState("");
  const [check, setCheck] = useState<PriceCheck | null>(null);
  const load = useCallback(() => {
    prices
      .state()
      .then((s) => {
        setState(s);
        setDoc(structuredClone(s.draft?.data ?? s.current));
        setErrors(s.draft_errors);
        setDirty(false);
        if (s.draft?.note) setNote(s.draft.note); // an import's "Imported from …" (ADR-113)
      })
      .catch((e) => setMsg(String(e)));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    prices
      .products()
      .then((p) => {
        setProducts(p);
        let saved = "";
        try {
          saved = localStorage.getItem(EXAMPLE_KEY) ?? "";
        } catch {
          saved = "";
        }
        const ids = new Set(p.models.map((m) => m.id));
        setExampleState(
          ids.has(saved) ? saved : (p.example ?? p.models[0]?.id ?? ""),
        );
      })
      .catch(() => setProducts(null));
  }, []);
  // the numbers as they are now (typed, not saved): placeholders and the example's costing
  useEffect(() => {
    if (!doc) return;
    const t = setTimeout(() => {
      prices
        .check(doc, example ? { model: example } : {})
        .then(setCheck)
        .catch(() => setCheck(null));
    }, 300);
    return () => clearTimeout(t);
  }, [doc, example]);
  if (!state || !doc) return <p className="muted">{msg || "Loading…"}</p>;
  const edit = canEdit && state.can_edit;
  const update = (fn: (d: PriceSet) => void) => {
    const copy = structuredClone(doc);
    fn(copy);
    setDoc(copy);
    setDirty(true);
    setMoves(null);
  };
  const setExample = (id: string) => {
    setExampleState(id);
    try {
      localStorage.setItem(EXAMPLE_KEY, id);
    } catch {
      // a private window: the choice lasts until the page is closed
    }
  };
  const rate = doc.exchange.idr_per_eur || 1;
  const ph = new Set(check?.placeholders ?? state.placeholders);
  const phTotal = check?.placeholder_total ?? state.placeholder_total;
  const ctx: Ctx = {
    doc,
    update,
    edit,
    state,
    rate,
    ph,
    confirm: (id) =>
      update((d) => void (d.confirmed = [...(d.confirmed ?? []), id])),
    ex: check?.costing ?? null,
    exError: check?.errors.length
      ? "These numbers cannot be used yet: " + check.errors.join("; ")
      : (check?.costing_error ?? ""),
    products,
    example,
    setExample,
  };
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
  const shownErrors = dirty && check ? check.errors : errors;
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
        <ol className="prices-flow" aria-label="how a price is made">
          <li>
            <b>Cost price</b>
            <span>fabric + components (Materials) + labour (Labour)</span>
          </li>
          <li>
            <b>Landed cost</b>
            <span>+ shipping, duties, packaging (Channels)</span>
          </li>
          <li>
            <b>Price ex VAT</b>
            <span>× the channel's markup, or ÷ its margin</span>
          </li>
          <li>
            <b>Shown price</b>
            <span>+ VAT (B2C), rounded up</span>
          </li>
        </ol>
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
        <p className="prices-status">
          {ph.size > 0 ? (
            <span className="pill ph-count" data-testid="placeholder-count">
              {ph.size} of {phTotal} values are still placeholders
            </span>
          ) : (
            <span className="pill ok" data-testid="placeholder-count">
              all {phTotal} values confirmed
            </span>
          )}
          <span className="muted">
            {ph.size > 0
              ? "Marked “placeholder — please confirm” below: our assumptions, waiting for your real numbers. Type the real number, or tap “keep this value” if it is right."
              : "Every number is your own (or confirmed)."}
          </span>
        </p>
        {shownErrors.length > 0 && (
          <ul className="error">
            {shownErrors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        )}
        {edit && (
          <>
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
            <p className="help">
              <b>Save draft</b> keeps your numbers without changing the shop.{" "}
              <b>Preview changes</b> lists every price that would move, before →
              after. <b>Publish</b> makes them live for the shop and every
              costing; each published version is kept (Versions can roll back).{" "}
              <b>Discard draft</b> throws your changes away.
            </p>
          </>
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
        {sub === "channels" && edit && (
          <PriceImport
            beforeApply={async () => !dirty || (await saveDraft()).length === 0}
            onApplied={(m) => {
              load();
              setMoves(null);
              setMsg(m);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        )}
        {sub === "channels" && <Channels {...ctx} />}
        {sub === "costing" && (
          <CostingView
            hasDraft={!!state.draft}
            dirty={dirty}
            doc={doc}
            products={products}
          />
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
  /** ids of the fields still at their placeholder */
  ph: Set<string>;
  confirm: (id: string) => void;
  /** the example cover's costing with the numbers as typed */
  ex: Costing | null;
  exError: string;
  products: CostingProducts | null;
  example: string;
  setExample: (id: string) => void;
}

// ---- small building blocks ----------------------------------------------------------------------

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
      inputMode="decimal"
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
      = {currency === "IDR" ? eur(amount / rate) : idr(amount * rate)}
    </span>
  );
}

/** What a tab is for, what to fill in and in which order, and where it goes. */
function Intro({ children }: { children: ReactNode }) {
  return <div className="prices-intro">{children}</div>;
}

/** The "placeholder — please confirm" mark of a field still at its documented default. */
function Mark({
  id,
  ph,
  edit,
  confirm,
}: Pick<Ctx, "ph" | "edit" | "confirm"> & { id: string }) {
  if (!ph.has(id)) return null;
  return (
    <span className="ph" data-field={id}>
      placeholder — please confirm
      {edit && (
        <button
          className="link"
          title="This number is right: it is no longer a placeholder (after you publish)"
          onClick={(e) => {
            e.preventDefault();
            confirm(id);
          }}
        >
          keep this value
        </button>
      )}
    </span>
  );
}

/** A labelled setting: the label with its unit, the input, and a one-line help under it. */
function Field({
  label,
  help,
  mark,
  children,
}: {
  label: ReactNode;
  help: ReactNode;
  mark?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="field">
      <div className="field-label">
        {label} {mark}
      </div>
      <div className="field-input">{children}</div>
      <p className="help">{help}</p>
    </div>
  );
}

/** A longer explanation, opened with a tap (no hovering needed on a tablet). */
function Explain({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="explain">
      <summary>{title}</summary>
      <div>{children}</div>
    </details>
  );
}

/** The live example: one real cover, costed with the numbers as they are typed. */
function Example({
  products,
  example,
  setExample,
  ex,
  exError,
  children,
}: Pick<Ctx, "products" | "example" | "setExample" | "ex" | "exError"> & {
  children: (c: Costing) => ReactNode;
}) {
  const models = products?.models ?? [];
  return (
    <aside className="prices-example" data-testid="live-example">
      <div className="example-head">
        <b>Live example</b>
        <span className="muted">
          with the numbers on this page, before saving
        </span>
        {models.length > 0 && (
          <select
            aria-label="example cover"
            value={example}
            onChange={(e) => setExample(e.target.value)}
          >
            {["catalogue", "drawing", "arrangement", "order", "other"].map(
              (kind) => {
                const ms = models.filter((m) => m.kind === kind);
                return ms.length ? (
                  <optgroup key={kind} label={kind}>
                    {ms.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </optgroup>
                ) : null;
              },
            )}
          </select>
        )}
      </div>
      {!models.length ? (
        <p className="muted">
          No calculated cover yet to show an example with.
        </p>
      ) : exError ? (
        <p className="error">{exError}</p>
      ) : ex ? (
        children(ex)
      ) : (
        <p className="muted">Calculating…</p>
      )}
    </aside>
  );
}

const findLine = (c: Costing | null, section: string, code: string) =>
  c?.lines.find((x) => x.section === section && x.code === code);

const facts = (c: Costing) =>
  `${c.facts.piece ?? 0} pieces, ${num(c.facts.seam_m)} m of seam, ${num(c.facts.hem_m)} m of hem, ${c.facts.vent ?? 0} vents`;

// ---- Materials ----------------------------------------------------------------------------------

function Materials(ctx: Ctx) {
  const { doc, update, edit, state, rate, ex } = ctx;
  const c = state.choices;
  const mark = (id: string) => <Mark id={id} {...ctx} />;
  return (
    <>
      <Intro>
        <p>
          <b>What every cover is made of, at purchase price.</b> Fill in the
          fabric first (the biggest cost), then each component. Prices may be in
          euros or rupiah; rupiah are converted with the rate on{" "}
          <i>Exchange rate</i>.
        </p>
        <p>
          For each cover the program takes the metres from its own cut plan and
          counts its vents, cord and pieces, so: fabric metres × price per metre
          + components × how many the cover has. Together with <i>Labour</i>{" "}
          this is the <b>cost price</b>; the <i>Channels</i> tab turns it into
          the shop price.
        </p>
      </Intro>
      {doc.fabrics.map((f, i) => {
        const id = (a: string) => `fabric:${f.code}.${a}`;
        const set = (fn: (x: PriceSet["fabrics"][number]) => void) =>
          update((d) => fn(d.fabrics[i]));
        const showExample = ex ? ex.fabric.code === f.code : i === 0;
        return (
          <section key={i} className="card" data-fabric={f.code}>
            <div className="row">
              <h4>Fabric: {f.name || f.code}</h4>
              <span className="spacer" />
              {edit && (
                <button
                  disabled={doc.fabrics.length < 2}
                  onClick={() => update((d) => void d.fabrics.splice(i, 1))}
                >
                  Remove fabric
                </button>
              )}
            </div>
            <div className="fields">
              <Field
                label="Price per metre of roll (EUR or IDR)"
                mark={mark(id("price"))}
                help="What you pay per running metre of the roll. Used for every cover: metres in its cut plan (+ waste) × this price. Example: Coverlast 152 cm ≈ € 24.50/m, or Rp 450,000/m."
              >
                <Num
                  value={f.price}
                  edit={edit}
                  label="fabric price"
                  onChange={(v) => set((x) => void (x.price = v))}
                />
                <Pick
                  value={f.currency}
                  options={c.currencies}
                  edit={edit}
                  label="fabric currency"
                  onChange={(v) =>
                    set((x) => void (x.currency = v as Currency))
                  }
                />
                <Both amount={f.price} currency={f.currency} rate={rate} />
              </Field>
              <Field
                label="Waste (%)"
                mark={mark(id("waste_pct"))}
                help="Fabric lost beyond the cut plan: roll ends, faults, test cuts. Added on top of the cut plan's metres. Example: 12.5 % turns 8.0 m into 9.0 m."
              >
                <Num
                  value={f.waste_pct}
                  edit={edit}
                  label="fabric waste"
                  onChange={(v) => set((x) => void (x.waste_pct = v))}
                />{" "}
                %
              </Field>
              <Field
                label="Roll width (mm)"
                mark={mark(id("roll_width_mm"))}
                help="The full width of the roll. The cut plans are laid out on 1500 mm; a narrower roll needs proportionally more metres. Example: 1520 (a 152 cm roll)."
              >
                <Num
                  value={f.roll_width_mm}
                  edit={edit}
                  label="roll width"
                  onChange={(v) => set((x) => void (x.roll_width_mm = v))}
                />{" "}
                mm
              </Field>
              <Field
                label="Name / quality"
                help="As the supplier calls it; printed on every costing. Example: Sunbrella Coverlast."
              >
                <Txt
                  value={f.name}
                  edit={edit}
                  wide
                  label="fabric name"
                  onChange={(v) => set((x) => void (x.name = v))}
                />
              </Field>
              <Field
                label="Colours offered (comma separated)"
                mark={mark(id("colours"))}
                help="The configurator uses the fabric that offers the customer's colour, else the first fabric. Example: Charcoal, Navy, Taupe."
              >
                <Txt
                  value={f.colours}
                  edit={edit}
                  wide
                  label="colours"
                  onChange={(v) => set((x) => void (x.colours = v))}
                />
              </Field>
              <Field
                label="Code"
                help="A short id without spaces; later the product code in Odoo. Example: coverlast."
              >
                <Txt
                  value={f.code}
                  edit={edit}
                  label="fabric code"
                  onChange={(v) => set((x) => void (x.code = v))}
                />
              </Field>
            </div>
            {showExample ? (
              <Example {...ctx}>
                {(cst) => {
                  const line = findLine(cst, "fabric", cst.fabric.code);
                  if (!line || cst.fabric.code !== f.code)
                    return (
                      <p className="muted">
                        {cst.name} uses {cst.fabric.name}, not this fabric.
                      </p>
                    );
                  return (
                    <p>
                      {cst.name}: {line.note} = <b>{num(line.qty, 2)} m</b> ×{" "}
                      {money(line.unit_price, line.currency)} ={" "}
                      <b>{eur(line.eur)}</b>{" "}
                      <span className="muted">({idr(line.idr)})</span> of a cost
                      price of {eur(cst.cost_eur)}.
                    </p>
                  );
                }}
              </Example>
            ) : null}
          </section>
        );
      })}
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
      <section className="card">
        <h4>Components</h4>
        <p className="help">
          Everything else that goes into a cover, at purchase price.{" "}
          <b>Counted per</b> is what the program multiplies the price by, from
          each cover's own pieces: its vents, its metres of cord, ... You can
          add your own (thread, labels, a strap) and say what it is counted per.
        </p>
        <table className="list prices-table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Counted per</th>
              <th>Purchase price (EUR or IDR)</th>
              <th>In the example cover</th>
              {edit && <th />}
            </tr>
          </thead>
          <tbody>
            {doc.components.map((x, i) => {
              const line = findLine(ex, "component", x.code);
              const acc =
                ex && x.code in (ex.channels.b2c?.accessories ?? {})
                  ? ex.channels.b2c.accessories[x.code]
                  : null;
              return (
                <tr key={i} className="static">
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
                    <div className="help">
                      {COMPONENT_HELP[x.code] ??
                        `Your own component, counted ${state.choices.per_label[x.per] ?? x.per}: added to every cover that has it.`}
                    </div>
                    <div className="code-row">
                      code{" "}
                      <Txt
                        value={x.code}
                        edit={edit && !BUILT_IN.includes(x.code)}
                        label="component code"
                        onChange={(v) =>
                          update((d) => void (d.components[i].code = v))
                        }
                      />
                    </div>
                  </td>
                  <td data-label="Counted per">
                    <Pick
                      value={x.per}
                      options={c.per}
                      labels={c.per_label}
                      edit={edit}
                      label={`${x.code} counted per`}
                      onChange={(v) =>
                        update((d) => void (d.components[i].per = v))
                      }
                    />
                  </td>
                  <td data-label="Purchase price">
                    <span className="nowrap">
                      <Num
                        value={x.price}
                        edit={edit}
                        label={`${x.code} price`}
                        onChange={(v) =>
                          update((d) => void (d.components[i].price = v))
                        }
                      />
                      <Pick
                        value={x.currency}
                        options={c.currencies}
                        edit={edit}
                        label={`${x.code} currency`}
                        onChange={(v) =>
                          update(
                            (d) =>
                              void (d.components[i].currency = v as Currency),
                          )
                        }
                      />
                    </span>
                    <div>
                      <Both
                        amount={x.price}
                        currency={x.currency}
                        rate={rate}
                      />
                    </div>
                    <Mark id={`component:${x.code}.price`} {...ctx} />
                  </td>
                  <td
                    className="example-cell"
                    data-label="In the example cover"
                  >
                    {line ? (
                      <>
                        {num(line.qty, 2)} {line.unit} ×{" "}
                        {money(line.unit_price, line.currency)} ={" "}
                        <b>{eur(line.eur)}</b>
                      </>
                    ) : acc ? (
                      <>
                        {acc.count} sold next to it (B2C {eur(acc.shown_eur)})
                      </>
                    ) : ex ? (
                      <span className="muted">not on this cover</span>
                    ) : null}
                  </td>
                  {edit && (
                    <td>
                      <button
                        disabled={BUILT_IN.includes(x.code)}
                        title={
                          BUILT_IN.includes(x.code)
                            ? "The program counts this one itself"
                            : undefined
                        }
                        onClick={() =>
                          update((d) => void d.components.splice(i, 1))
                        }
                      >
                        Remove
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
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
        <Example {...ctx}>
          {(cst) => (
            <p>
              {cst.name} ({facts(cst)}): components{" "}
              <b>{eur(cst.components_eur)}</b>, fabric {eur(cst.fabric_eur)},
              labour {eur(cst.labour_eur)} = cost price{" "}
              <b>{eur(cst.cost_eur)}</b>.
            </p>
          )}
        </Example>
      </section>
    </>
  );
}

// ---- Labour -------------------------------------------------------------------------------------

function Labour(ctx: Ctx) {
  const { doc, update, edit, state, rate, ex } = ctx;
  const c = state.choices;
  const lab = doc.labour;
  return (
    <>
      <Intro>
        <p>
          <b>The workshop's time.</b> Fill in the hourly rate first, then the
          minutes of each operation. The program counts every operation for each
          cover from its own cut pieces (how many pieces, metres of seam, vents,
          metres of hem) and adds it to the <b>cost price</b>: total minutes ÷
          60 × hourly rate.
        </p>
        <p>
          Tip: time one real cover in the workshop and compare it with the live
          example below; adjust the minutes until they match.
        </p>
      </Intro>
      <section className="card">
        <div className="fields">
          <Field
            label="Hourly rate (EUR or IDR per hour)"
            mark={<Mark id="labour.rate" {...ctx} />}
            help="The all-in cost of one workshop hour: wage, social costs, the machines' and the floor's share. Every minute below is paid at this rate. Example: € 42.50/h, or Rp 85,000/h."
          >
            <Num
              value={lab.rate}
              edit={edit}
              label="hourly rate"
              onChange={(v) => update((d) => void (d.labour.rate = v))}
            />
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
          </Field>
        </div>
        <h5>Operations: minutes each</h5>
        <p className="help">
          <b>Minutes</b> is the time for one of what it is <b>counted per</b>:
          per cover (once), per piece, per metre of seam, per vent, ... You can
          add your own operation (e.g. a quality check per cover).
        </p>
        <table className="list prices-table">
          <thead>
            <tr>
              <th>Operation</th>
              <th>Counted per</th>
              <th>Minutes each</th>
              <th>In the example cover</th>
              {edit && <th />}
            </tr>
          </thead>
          <tbody>
            {lab.operations.map((o, i) => {
              const line = findLine(ex, "labour", o.code);
              return (
                <tr key={i} className="static">
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
                    <div className="help">
                      {OPERATION_HELP[o.code] ??
                        `Your own operation, counted ${c.per_label[o.per] ?? o.per}.`}
                    </div>
                    <div className="code-row">
                      code{" "}
                      <Txt
                        value={o.code}
                        edit={edit}
                        label="operation code"
                        onChange={(v) =>
                          update((d) => void (d.labour.operations[i].code = v))
                        }
                      />
                    </div>
                  </td>
                  <td data-label="Counted per">
                    <Pick
                      value={o.per}
                      options={c.per}
                      labels={c.per_label}
                      edit={edit}
                      label={`${o.code} counted per`}
                      onChange={(v) =>
                        update((d) => void (d.labour.operations[i].per = v))
                      }
                    />
                  </td>
                  <td data-label="Minutes each">
                    <span className="nowrap">
                      <Num
                        value={o.minutes}
                        edit={edit}
                        label={`${o.code} minutes`}
                        onChange={(v) =>
                          update(
                            (d) => void (d.labour.operations[i].minutes = v),
                          )
                        }
                      />{" "}
                      min
                    </span>
                    <Mark id={`operation:${o.code}.minutes`} {...ctx} />
                  </td>
                  <td
                    className="example-cell"
                    data-label="In the example cover"
                  >
                    {line ? (
                      <>
                        {line.note.replace(/^.*= /, "")} ={" "}
                        <b>{eur(line.eur)}</b>
                        <div className="muted">{line.note.split(" = ")[0]}</div>
                      </>
                    ) : ex ? (
                      <span className="muted">0 min on this cover</span>
                    ) : null}
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
              );
            })}
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
        <Example {...ctx}>
          {(cst) => (
            <p>
              With these numbers {cst.name} ({facts(cst)}) takes{" "}
              <b>{Math.round(cst.labour_minutes)} min</b> ={" "}
              {num(cst.labour_minutes / 60, 2)} h ×{" "}
              {money(lab.rate, lab.currency)} = <b>{eur(cst.labour_eur)}</b>{" "}
              <span className="muted">({idr(cst.labour_eur * rate)})</span> of a
              cost price of {eur(cst.cost_eur)}.
            </p>
          )}
        </Example>
      </section>
    </>
  );
}

// ---- Exchange rate ------------------------------------------------------------------------------

function Rate(ctx: Ctx) {
  const { doc, update, edit, ph } = ctx;
  const ex = doc.exchange;
  const r = ex.idr_per_eur || 1;
  const [tryIdr, setTryIdr] = useState(450000);
  const idrPrices: [string, number][] = [
    ...doc.fabrics
      .filter((f) => f.currency === "IDR")
      .map((f): [string, number] => [`${f.name} per m`, f.price]),
    ...doc.components
      .filter((x) => x.currency === "IDR")
      .map((x): [string, number] => [x.name, x.price]),
    ...(doc.labour.currency === "IDR"
      ? [["Hourly rate", doc.labour.rate] as [string, number]]
      : []),
  ];
  return (
    <>
      <Intro>
        <p>
          <b>One fixed rate between rupiah and euros.</b> Production costs are
          in rupiah, sales in euros: every IDR amount on this page is converted
          to euros with this rate, and every costing shows both. It never
          changes by itself: enter a new rate when you want prices to follow the
          currency, then publish.
        </p>
        <p>
          Below it, <b>indicative</b> decides whether the shop says the prices
          are not final yet.
        </p>
      </Intro>
      <section className="card">
        <div className="fields">
          <Field
            label="Rupiah per euro (IDR for 1 EUR)"
            mark={<Mark id="exchange.idr_per_eur" {...ctx} />}
            help="How many rupiah one euro buys. Example: 18,500. A higher number makes every rupiah cost cheaper in euros, so cost prices in euros go down."
          >
            1 EUR ={" "}
            <Num
              value={ex.idr_per_eur}
              edit={edit}
              label="rupiah per euro"
              onChange={(v) => update((d) => void (d.exchange.idr_per_eur = v))}
            />{" "}
            IDR
          </Field>
          <Field
            label="Date of the rate"
            help="The day you took this rate; printed on every costing so you know how old it is."
          >
            <input
              type="date"
              value={ex.date}
              disabled={!edit}
              aria-label="rate date"
              onChange={(e) =>
                update((d) => void (d.exchange.date = e.target.value))
              }
            />
          </Field>
          <Field
            label="Note"
            help="Where the rate comes from. Example: “bank rate 8 Oct” or “Odoo rate”."
          >
            <Txt
              value={ex.note}
              edit={edit}
              wide
              label="rate note"
              onChange={(v) => update((d) => void (d.exchange.note = v))}
            />
          </Field>
        </div>
        <aside className="prices-example" data-testid="live-example">
          <div className="example-head">
            <b>Live example</b>
            <span className="muted">at this rate</span>
          </div>
          <p>
            <label className="inline">
              Try an amount{" "}
              <input
                type="number"
                className="num"
                aria-label="try an amount in rupiah"
                value={tryIdr}
                onChange={(e) => setTryIdr(Number(e.target.value) || 0)}
              />{" "}
              IDR
            </label>{" "}
            = <b>{eur(tryIdr / r)}</b>. Rp 450,000/m = {eur(450000 / r)}/m · Rp
            1,000,000 = {eur(1e6 / r)} · € 1 = {idr(r)}
          </p>
          {idrPrices.length > 0 && (
            <ul className="example-list">
              {idrPrices.map(([name, v]) => (
                <li key={name}>
                  {name}: {idr(v)} = <b>{eur(v / r)}</b>
                </li>
              ))}
            </ul>
          )}
          {ctx.ex && (
            <p>
              {ctx.ex.name}: cost price <b>{eur(ctx.ex.cost_eur)}</b> ={" "}
              {idr(ctx.ex.cost_idr)}.
            </p>
          )}
        </aside>
      </section>
      <section className="card">
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
          Prices are indicative (still placeholders)
        </label>
        <p className="help">
          While this is on, the shop shows “indicative” next to every price, so
          customers know it is not final. Switch it off, and publish, once the
          real purchase prices, labour and margins are in.
          {ph.size > 0 &&
            ` ${ph.size} values on this page are still placeholders.`}
        </p>
      </section>
    </>
  );
}

// ---- Channels & price lists ---------------------------------------------------------------------

/** markup p (of the base) ⇄ margin g (of the price): g = p / (1 + p), p = g / (1 − g) */
function markupMargin(method: string, pct: number): string {
  const p = pct / 100;
  if (method === "markup")
    return `markup ${num(pct, 1)} % = a margin of ${num((p / (1 + p)) * 100, 1)} % of the price`;
  return p < 1
    ? `margin ${num(pct, 1)} % = a markup of ${num((p / (1 - p)) * 100, 1)} % on the base`
    : "a margin must be below 100 %";
}

/** The worked example of one channel: from the cost price to the price the customer sees. */
function Worked({
  c,
  ch,
  live,
}: {
  c: Costing;
  ch: ChannelPrice;
  live?: ChannelPrice;
}) {
  const base = ch.base === "cost" ? c.cost_eur : ch.landed_eur;
  const p = ch.pct / 100;
  const factor = ch.method === "markup" ? 1 + p : 1 / (1 - p);
  const raw = base * factor;
  const rawShown = ch.show_vat ? raw * (1 + ch.vat_pct / 100) : raw;
  return (
    <ol className="worked">
      <li>
        Cost price <b>{eur(c.cost_eur)}</b>
        {ch.extras.map((e) => (
          <span key={e.code}>
            {" "}
            + {e.name.toLowerCase()} {eur(e.eur)}
          </span>
        ))}{" "}
        = landed cost <b>{eur(ch.landed_eur)}</b>
      </li>
      {ch.fixed ? (
        <li>
          Fixed price for this cover: <b>{eur(ch.shown_eur)}</b>{" "}
          {ch.show_vat ? "incl." : "ex"} VAT (the rule and rounding are skipped)
        </li>
      ) : (
        <>
          <li>
            {ch.base === "cost" ? "Cost price" : "Landed cost"} {eur(base)}{" "}
            {ch.method === "markup"
              ? `× ${num(factor, 3)} (markup ${num(ch.pct)} %)`
              : `÷ ${num(1 - p, 3)} (margin ${num(ch.pct)} %)`}{" "}
            = {eur(raw)} ex VAT
            {ch.show_vat && ` → + ${num(ch.vat_pct)} % VAT = ${eur(rawShown)}`}
          </li>
          <li>
            Rounded = shown price <b>{eur(ch.shown_eur)}</b>{" "}
            {ch.show_vat ? "incl." : "ex"} VAT
          </li>
        </>
      )}
      <li>
        Price ex VAT {eur(ch.net_eur)} · incl. VAT {eur(ch.gross_eur)} · margin{" "}
        <b>{eur(ch.margin_eur)}</b> ({num(ch.margin_pct)} % of the price ex VAT)
        {live && Math.abs(live.shown_eur - ch.shown_eur) >= 0.005 && (
          <span className="muted"> · live now {eur(live.shown_eur)}</span>
        )}
      </li>
      {Object.entries(ch.accessories).map(([code, a]) => (
        <li key={code}>
          Sold next to it: {a.count} × {code} = {eur(a.shown_eur)}
        </li>
      ))}
    </ol>
  );
}

function Channels(ctx: Ctx) {
  const { doc, update, edit, state, rate, products, example } = ctx;
  const c = state.choices;
  const [newKey, setNewKey] = useState<Record<string, string>>({});
  const [live, setLive] = useState<Costing | null>(null);
  useEffect(() => {
    if (!example) return;
    prices
      .costing({ model: example, set: "current" })
      .then(setLive)
      .catch(() => setLive(null));
  }, [example]);
  const names = useMemo(
    () =>
      Object.fromEntries((products?.models ?? []).map((m) => [m.id, m.name])),
    [products],
  );
  return (
    <>
      <Intro>
        <p>
          <b>Where the cost price becomes a selling price</b>, per channel:{" "}
          <b>B2C</b> = consumers in the webshop, <b>B2B</b> = Sunsit and
          dealers. For each, fill in first the <b>extra costs</b> of getting a
          cover to that customer, then the <b>price list</b>.
        </p>
        <p>
          Cost price + shipping + duties + packaging = <b>landed cost</b> → ×
          markup (or ÷ margin) = price ex VAT → + VAT → rounded up = the price
          the customer sees. The worked example under each channel shows every
          step with a real cover.
        </p>
        <Explain title="Terms explained: landed cost, markup and margin, rounding, VAT, fixed prices">
          <dl className="terms">
            <dt>Landed cost</dt>
            <dd>
              What a cover costs you once it is at the customer: cost price +
              shipping + import duties + packaging. Kept as separate lines, so
              you see what each adds.
            </dd>
            <dt>Markup or margin</dt>
            <dd>
              Markup is a % <i>on top of</i> the base: price = base × (1 +
              markup). Margin is the % of the <i>price</i> you keep: price =
              base ÷ (1 − margin). The same price can be said both ways: markup
              87.5 % = margin 46.7 % (0.875 ÷ 1.875), margin 40 % = markup 66.7
              % (0.40 ÷ 0.60). Example: base € 100 with markup 87.5 % → €
              187.50, of which € 87.50 (46.7 %) is margin.
            </dd>
            <dt>On cost + extra costs, or on cost only</dt>
            <dd>
              “On cost + extra costs” (normal) takes the markup on the landed
              cost, so shipping and duties are earned back with the markup on
              top. “On the cost price only” takes it on the cost price; the
              extra costs then come out of your margin.
            </dd>
            <dt>Rounding</dt>
            <dd>
              The shown price is rounded <i>up</i>. Example € 1,211.53: up to
              .95 → € 1,211.95; up to .99 → € 1,211.99; whole euros → € 1,212;
              up to 5 → € 1,215; up to 10 → € 1,220; none → € 1,211.53.
            </dd>
            <dt>VAT shown incl. or ex</dt>
            <dd>
              Consumers must see prices incl. VAT; businesses usually see them
              ex VAT. The rounding and fixed prices apply to the price as it is
              shown.
            </dd>
            <dt>Fixed price</dt>
            <dd>
              A price set by hand for one product in one channel; it wins over
              the rule, without rounding. For a launch price or a price agreed
              with a dealer.
            </dd>
          </dl>
        </Explain>
      </Intro>
      <div className="prices-channels">
        {CHANNELS.map((k) => {
          const ch = doc.channels[k];
          const set = (fn: (x: PriceSet["channels"][ChannelKey]) => void) =>
            update((d) => fn(d.channels[k]));
          const exr = ch.extras;
          const mark = (a: string) => <Mark id={`${k}.${a}`} {...ctx} />;
          const vatWord = ch.show_vat ? "incl." : "ex";
          return (
            <section key={k} className="card" data-channel={k}>
              <h4>
                {k.toUpperCase()}: {ch.name}
              </h4>
              <div className="fields one">
                <Field label="Name" help="Shown in costings and price lists.">
                  <Txt
                    value={ch.name}
                    edit={edit}
                    wide
                    label={`${k} name`}
                    onChange={(v) => set((x) => void (x.name = v))}
                  />
                </Field>
              </div>
              <h5>Extra costs per cover (lines of their own)</h5>
              <div className="fields one">
                <Field
                  label="Shipping per cover (EUR or IDR)"
                  mark={mark("shipping")}
                  help={
                    k === "b2c"
                      ? "Freight from Indonesia plus delivery to one consumer, per cover. Example: € 18.50."
                      : "Freight per cover to a business customer: pallets, shared. Example: € 9.50."
                  }
                >
                  <Num
                    value={exr.shipping.amount}
                    edit={edit}
                    label={`${k} shipping`}
                    onChange={(v) =>
                      set((x) => void (x.extras.shipping.amount = v))
                    }
                  />
                  <Pick
                    value={exr.shipping.currency}
                    options={c.currencies}
                    edit={edit}
                    label={`${k} shipping currency`}
                    onChange={(v) =>
                      set(
                        (x) =>
                          void (x.extras.shipping.currency = v as Currency),
                      )
                    }
                  />
                  {exr.shipping.currency === "IDR" && (
                    <Both
                      amount={exr.shipping.amount}
                      currency="IDR"
                      rate={rate}
                    />
                  )}
                </Field>
                <Field
                  label="Import duties (% of cost + shipping, or a fixed amount)"
                  mark={mark("duties")}
                  help="EU import duty on the cover. As a %, it is taken of the cost price + shipping (the customs value). Example: 12.5 % (tariff 6306)."
                >
                  <Pick
                    value={exr.duties.mode}
                    options={c.duty_modes}
                    edit={edit}
                    label={`${k} duties mode`}
                    labels={{
                      pct: "% of cost + shipping",
                      fixed: "fixed amount",
                    }}
                    onChange={(v) =>
                      set(
                        (x) =>
                          void (x.extras.duties.mode = v as "pct" | "fixed"),
                      )
                    }
                  />
                  <Num
                    value={exr.duties.value}
                    edit={edit}
                    label={`${k} duties`}
                    onChange={(v) =>
                      set((x) => void (x.extras.duties.value = v))
                    }
                  />
                  {exr.duties.mode === "fixed" ? (
                    <Pick
                      value={exr.duties.currency ?? "EUR"}
                      options={c.currencies}
                      edit={edit}
                      label={`${k} duties currency`}
                      onChange={(v) =>
                        set(
                          (x) =>
                            void (x.extras.duties.currency = v as Currency),
                        )
                      }
                    />
                  ) : (
                    "%"
                  )}
                </Field>
                <Field
                  label="Packaging per cover (EUR or IDR)"
                  mark={mark("packaging")}
                  help="Box and bag for one cover. Example: € 2.75."
                >
                  <Num
                    value={exr.packaging.amount}
                    edit={edit}
                    label={`${k} packaging`}
                    onChange={(v) =>
                      set((x) => void (x.extras.packaging.amount = v))
                    }
                  />
                  <Pick
                    value={exr.packaging.currency}
                    options={c.currencies}
                    edit={edit}
                    label={`${k} packaging currency`}
                    onChange={(v) =>
                      set(
                        (x) =>
                          void (x.extras.packaging.currency = v as Currency),
                      )
                    }
                  />
                  {exr.packaging.currency === "IDR" && (
                    <Both
                      amount={exr.packaging.amount}
                      currency="IDR"
                      rate={rate}
                    />
                  )}
                </Field>
              </div>
              <h5>Price list</h5>
              <div className="fields one">
                <Field
                  label="Rule: markup or margin (%), and on what"
                  mark={mark("pct")}
                  help={
                    <>
                      Markup: price = base × (1 + %). Margin: price = base ÷ (1
                      − %), the share of the price you keep. Here:{" "}
                      <b>{markupMargin(ch.method, ch.pct)}</b>.
                    </>
                  }
                >
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
                    label={`${k} base`}
                    labels={{
                      landed: "on cost + extra costs",
                      cost: "on the cost price only",
                    }}
                    onChange={(v) =>
                      set((x) => void (x.base = v as "landed" | "cost"))
                    }
                  />
                </Field>
                <Field
                  label={`Rounding (of the price ${vatWord} VAT)`}
                  help="The shown price is rounded up so it ends nicely. Example € 1,211.53: up to .95 → € 1,211.95, whole euros → € 1,212, up to 10 → € 1,220."
                >
                  <Pick
                    value={ch.rounding}
                    options={c.roundings}
                    labels={ROUNDING_LABEL}
                    edit={edit}
                    label={`${k} rounding`}
                    onChange={(v) => set((x) => void (x.rounding = v))}
                  />
                </Field>
                <Field
                  label="VAT (%) and how prices are shown"
                  mark={mark("vat_pct")}
                  help="VAT on the price ex VAT. Consumers see prices incl. VAT; business customers usually ex VAT. Example: 21 % (Dutch VAT)."
                >
                  <Num
                    value={ch.vat_pct}
                    edit={edit}
                    label={`${k} VAT`}
                    onChange={(v) => set((x) => void (x.vat_pct = v))}
                  />
                  %
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
                </Field>
              </div>
              <h5>Fixed prices ({vatWord} VAT)</h5>
              <p className="help">
                A price you set by hand for one product in this channel; it wins
                over the rule above, without rounding. Type a model id (or
                balloon, frame) and the price {vatWord} VAT.
              </p>
              {Object.keys(ch.fixed).length > 0 && (
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
                            onChange={(n) =>
                              set((x) => void (x.fixed[key] = n))
                            }
                          />
                        </td>
                        {edit && (
                          <td>
                            <button
                              onClick={() =>
                                set((x) => void delete x.fixed[key])
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
              )}
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
              <Example {...ctx}>
                {(cst) =>
                  cst.channels[k] ? (
                    <Worked
                      c={cst}
                      ch={cst.channels[k]}
                      live={live?.channels[k]}
                    />
                  ) : null
                }
              </Example>
            </section>
          );
        })}
      </div>
      <datalist id="price-products">
        <option value="balloon">Balloon</option>
        <option value="frame">Frame</option>
        {(products?.models ?? []).map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </datalist>
    </>
  );
}

// ---- the preview of a draft ---------------------------------------------------------------------

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
        VAT, B2B as its price list shows it. Nothing is live until you publish.
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

// ---- Costing ------------------------------------------------------------------------------------

type SetChoice = "current" | "draft" | "page";

function CostingView({
  hasDraft,
  dirty,
  doc,
  products,
}: {
  hasDraft: boolean;
  dirty: boolean;
  doc: PriceSet;
  products: CostingProducts | null;
}) {
  const [mode, setMode] = useState<"model" | "configurator">("model");
  const [model, setModel] = useState("");
  const [product, setProduct] = useState("sofa");
  const [sizes, setSizes] = useState<Record<string, number | boolean>>({});
  const [set, setSet] = useState<SetChoice>("current");
  const [c, setC] = useState<Costing | null>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (products?.models.length)
      setModel((m) => m || products.example || products.models[0].id);
  }, [products]);
  const query = useMemo((): Record<string, string> | null => {
    const s = set === "page" ? "current" : set;
    if (mode === "model") return model ? { model, set: s } : null;
    return { product, sizes: JSON.stringify(sizes), set: s };
  }, [mode, model, product, sizes, set]);
  useEffect(() => {
    if (!query) return;
    const t = setTimeout(() => {
      const get: Promise<Costing> =
        set === "page"
          ? prices
              .check(doc, mode === "model" ? { model } : { product, sizes })
              .then((r) => {
                if (r.costing) return r.costing;
                throw new Error(
                  r.errors.join("; ") || r.costing_error || "no costing",
                );
              })
          : prices.costing(query);
      get
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
  }, [query, set, doc, mode, model, product, sizes]);
  const spec = products?.configurator.find((p) => p.product === product);
  const qs = query ? new URLSearchParams(query).toString() : "";
  return (
    <>
      <Intro>
        <p>
          <b>What one cover costs and sells for, line by line.</b> Choose a
          cover (catalogue, drawing, arrangement, order) or a configurator
          product with its sizes. The quantities come from the cover's real cut
          pieces; the prices from the tabs before.
        </p>
        <p>
          <b>Prices:</b> “live” = what the shop uses now; “saved draft” = your
          saved, unpublished numbers; “this page” = the numbers on this page,
          also before saving. <b>CSV</b> opens in Excel, <b>PDF</b> to print.
        </p>
        <Explain title="What the lines mean">
          <dl className="terms">
            <dt>Cost price</dt>
            <dd>Fabric + components + labour: what it costs to make.</dd>
            <dt>Landed cost</dt>
            <dd>
              Cost price + the channel's shipping, duties and packaging: what it
              costs you at the customer.
            </dd>
            <dt>Price ex VAT / incl. VAT</dt>
            <dd>
              The channel's markup or margin on the landed cost (or the cost
              price), rounded; with and without VAT.
            </dd>
            <dt>Shown price</dt>
            <dd>
              What the customer sees: incl. VAT for consumers, ex VAT for
              business.
            </dd>
            <dt>Margin</dt>
            <dd>
              Price ex VAT − landed cost, in euros and as a % of the price ex
              VAT.
            </dd>
            <dt>Sold with it</dt>
            <dd>
              Balloons or a frame for a table cover: sold next to the cover at
              their own price, not in its cost price.
            </dd>
            <dt>Indicative</dt>
            <dd>
              The price set still holds placeholders; the shop says “indicative”
              next to its prices.
            </dd>
          </dl>
        </Explain>
      </Intro>
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
              onChange={(e) => setSet(e.target.value as SetChoice)}
            >
              <option value="current">live</option>
              <option value="draft" disabled={!hasDraft}>
                saved draft{hasDraft ? "" : " (none)"}
              </option>
              <option value="page">
                this page{dirty ? " (unsaved changes)" : ""}
              </option>
            </select>
          </label>
        </div>
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
              {products?.models.length ?? 0} calculated covers; type to search
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
            {set !== "page" && (
              <>
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
              </>
            )}
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
              {c.lines.map((x: CostLine) => (
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
                  <td>{money(x.unit_price, x.currency)}</td>
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

// ---- Versions -----------------------------------------------------------------------------------

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
  const intro = (
    <Intro>
      <p>
        <b>The history of the prices.</b> Every publish stores the whole price
        set as a new version, with who, when and the note you wrote. The newest
        is <b>live</b>: the shop, the configurator and every costing use it.
      </p>
      <p>
        <b>Draft</b> (your saved, unpublished numbers) → <b>Preview</b> (which
        prices would move) → <b>Publish</b> (a new live version).{" "}
        <b>Roll back</b> makes an older version live again; that too is stored
        as a new version, so nothing is ever lost and you can always go forward
        again.
      </p>
    </Intro>
  );
  if (!vs)
    return (
      <>
        {intro}
        <p className="muted">{msg || "Loading…"}</p>
      </>
    );
  if (!vs.length)
    return (
      <>
        {intro}
        <p className="muted">
          Nothing published yet: the shop uses the documented defaults.
        </p>
      </>
    );
  return (
    <>
      {intro}
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
                              `Make version ${v.version} live again? It is stored as a new version; the shop changes at once.`,
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
    </>
  );
}
