// The B2B shop (ADR-101): business customers log in at /b2b and order at their own price list,
// ex VAT, on account. The same configurator and catalogue covers as the consumer shop, with
// quantities, an order list, their PO number, their delivery addresses and their previous
// orders ("order again"). Every word comes from the site's content (ui.b2b, plus the shop's own
// words for the configurator), in the shop's languages. Logins, the session and its CSRF token
// are the studio's B2B API (apps/api/coverapi/b2b.py); nothing here is cached or indexed.
import { StrictMode, useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "../shop.css";
import "./b2b.css";
import { Scene } from "../Scene";

type T = Record<string, string>;
interface Field {
  key: string;
  default: number | boolean;
  min: number | null;
  max: number | null;
  unit: string | null;
  requires?: string | null;
}
interface Info {
  content: {
    ui: {
      words: Record<string, T>;
      status: Record<string, T>;
      field: Record<string, T>;
      product: Record<string, T>;
      b2b?: Record<string, T>;
    };
  };
  settings: {
    company: Record<string, string>;
    logo_url: string;
    colours: string[];
    languages: string[];
  };
  options: { products: Record<string, { label: string; fields: Field[] }> };
}
interface Addr {
  id: string | null;
  label: string;
  name: string;
  street: string;
  postcode: string;
  city: string;
  country: string;
}
interface Me {
  user: { email: string; name: string | null; lang: string | null };
  company: {
    name: string;
    vat_number: string | null;
    contact: string | null;
    invoice_address: Addr;
    addresses: Addr[];
    price_list: string;
    vat_pct: number;
    reverse_charge: boolean;
  };
  csrf: string;
  settings: {
    online_payment: boolean;
    min_order_eur: number;
    shipping_eur: number;
    payment_days: number;
  };
}
interface RainOption {
  ponds: number;
  flat_m2: number;
  dry: boolean;
  water: string | null;
}
interface Quote {
  id: string;
  product: string;
  label: string | null;
  pieces: number;
  cover_area_m2: number;
  vents: number;
  balloons: number;
  colour: string;
  sizes_cm: Record<string, number | boolean | string>;
  support: string;
  price: {
    cover_eur: number;
    support_eur: number;
    unit_eur: number;
    source: "list" | "list_fixed" | "company_fixed";
    vat_pct: number;
    indicative: boolean;
  };
  rain: {
    options: Record<string, RainOption>;
    advice: { support: string; count: number; price_eur: number } | null;
  } | null;
  scene: string;
  stock: { model_id: string; name: string } | null;
}
interface Line {
  quote: Quote;
  qty: number;
}
interface Item {
  model_id: string;
  name: string;
  category: string;
  kind: string;
  size_cm: number[];
  side: string | null;
  photo: boolean;
  fixed_eur: number | null;
}
interface PastLine {
  qty: number;
  unit_eur: number;
  total_eur: number;
  product: string;
  label: string | null;
  colour: string;
  support: string;
  sizes_cm: Record<string, number | boolean | string>;
  status: string | null;
  order_id: number;
}
interface PastOrder {
  id: number;
  created: number;
  po: string | null;
  net_eur: number;
  vat_eur: number;
  gross_eur: number;
  address: Addr;
  lines: PastLine[];
}

const SWATCH: Record<string, string> = {
  charcoal: "#3d4039",
  navy: "#283548",
  "light grey": "#b9bab3",
  taupe: "#8c7c68",
  black: "#1f1f1f",
  sand: "#c8b593",
};
// On the website the B2B shop is /b2b/; on the studio (the colleagues' preview) /shop/b2b/.
const ROOT = window.location.pathname.startsWith("/shop/")
  ? "/shop/b2b/"
  : "/b2b/";
const CONSUMER = ROOT === "/b2b/" ? "/" : "/shop/";

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
async function api<R>(
  method: string,
  path: string,
  body?: unknown,
  csrf?: string,
): Promise<R> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrf) headers["x-b2b-csrf"] = csrf;
  const r = await fetch(`/api/b2b/${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(String(d.detail ?? r.status), r.status);
  return d as R;
}

interface Tx {
  lang: string;
  b: (key: string, vars?: Record<string, string | number>) => string;
  w: (key: string, vars?: Record<string, string | number>) => string;
  field: (key: string) => string;
  product: (key: string) => string;
  status: (key: string | null) => string;
  eur: (n: number) => string;
}
function makeTx(info: Info, lang: string): Tx {
  const ui = info.content.ui;
  const t = (x: T | undefined) => (x ? (x[lang] ?? x.en ?? x.nl ?? "") : "");
  const fill = (s: string, vars: Record<string, string | number>) =>
    Object.entries(vars).reduce((a, [k, v]) => a.split(`{${k}}`).join(String(v)), s);
  const money = new Intl.NumberFormat(lang, { style: "currency", currency: "EUR" });
  return {
    lang,
    b: (key, vars = {}) => fill(t(ui.b2b?.[key]) || key, vars),
    w: (key, vars = {}) => fill(t(ui.words[key]) || key, vars),
    field: (key) => t(ui.field[key]) || key,
    product: (key) => t(ui.product[key]) || key,
    status: (key) =>
      key === "on_account"
        ? t(ui.b2b?.status_on_account) || key
        : t(ui.status[key ?? ""]) || key || "",
    eur: (n) => money.format(n),
  };
}

function sizesText(s: Record<string, number | boolean | string>): string {
  return Object.values(s)
    .filter((v) => typeof v === "number")
    .slice(0, 3) // length, width/depth, height: the strips and the rest are details
    .map((v) => Math.round(Number(v)))
    .join(" × ");
}

// ---- logged out: log in, forgot, request an account, set a password ----------------------

function Login({ tx, onIn }: { tx: Tx; onIn: (me: Me) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  return (
    <section className="b-narrow">
      <h1>{tx.b("login_title")}</h1>
      <p className="s-muted">{tx.b("login_text")}</p>
      <form
        className="s-checkout"
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          try {
            onIn(await api<Me>("POST", "login", { email, password, lang: tx.lang }));
          } catch (err) {
            setError((err as Error).message);
          }
        }}
      >
        <label className="b-field">
          <span>{tx.w("email")}</span>
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="b-field">
          <span>{tx.b("password")}</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button className="s-btn wide">{tx.b("login")} →</button>
        {error && <p className="s-error">{error}</p>}
      </form>
      <p>
        <a href={`${ROOT}forgot`}>{tx.b("forgot")}</a>
      </p>
      <div className="b-box">
        <strong>{tx.b("no_account")}</strong>
        <p className="s-muted">{tx.b("request_text")}</p>
        <a className="s-btn small" href={`${ROOT}request`}>
          {tx.b("request")} →
        </a>
      </div>
      <p>
        <a className="s-link" href={CONSUMER}>
          {tx.b("consumer_shop")} →
        </a>
      </p>
    </section>
  );
}

function Forgot({ tx }: { tx: Tx }) {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  return (
    <section className="b-narrow">
      <h1>{tx.b("forgot")}</h1>
      {sent ? (
        <p>{tx.b("forgot_sent")}</p>
      ) : (
        <form
          className="s-checkout"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await api("POST", "password/forgot", { email, lang: tx.lang });
              setSent(true);
            } catch (err) {
              setError((err as Error).message);
            }
          }}
        >
          <p className="s-muted">{tx.b("forgot_text")}</p>
          <label className="b-field">
            <span>{tx.w("email")}</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <button className="s-btn wide">{tx.b("send_link")} →</button>
          {error && <p className="s-error">{error}</p>}
        </form>
      )}
      <p>
        <a href={ROOT}>← {tx.b("back_login")}</a>
      </p>
    </section>
  );
}

function RequestAccount({ tx }: { tx: Tx }) {
  const [f, setF] = useState({
    company: "",
    vat_number: "",
    contact: "",
    email: "",
    phone: "",
    street: "",
    postcode: "",
    city: "",
    country: "NL",
    message: "",
  });
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const label: Record<string, string> = {
    company: tx.b("company"),
    vat_number: tx.b("vat_number"),
    contact: tx.b("contact"),
    email: tx.w("email"),
    phone: tx.w("phone"),
    street: tx.w("street"),
    postcode: tx.w("postcode"),
    city: tx.w("city"),
    country: tx.w("country"),
  };
  return (
    <section className="b-narrow">
      <h1>{tx.b("request")}</h1>
      {sent ? (
        <p className="b-ok">{tx.b("request_sent")}</p>
      ) : (
        <form
          className="s-checkout"
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            try {
              await api("POST", "request", { ...f, lang: tx.lang });
              setSent(true);
            } catch (err) {
              setError((err as Error).message);
            }
          }}
        >
          <p className="s-muted">{tx.b("request_text")}</p>
          {Object.keys(label).map((k) => (
            <label className="b-field" key={k}>
              <span>{label[k]}</span>
              <input
                required={["company", "contact", "email"].includes(k)}
                type={k === "email" ? "email" : "text"}
                maxLength={k === "country" ? 2 : 160}
                value={f[k as keyof typeof f]}
                onChange={(e) => setF({ ...f, [k]: e.target.value })}
              />
            </label>
          ))}
          <label className="b-field">
            <span>{tx.b("message")}</span>
            <textarea
              value={f.message}
              onChange={(e) => setF({ ...f, message: e.target.value })}
            />
          </label>
          <button className="s-btn wide">{tx.b("send")} →</button>
          {error && <p className="s-error">{error}</p>}
        </form>
      )}
      <p>
        <a href={ROOT}>← {tx.b("back_login")}</a>
      </p>
    </section>
  );
}

function SetPassword({
  tx,
  token,
  onIn,
}: {
  tx: Tx;
  token: string;
  onIn: (me: Me) => void;
}) {
  const [who, setWho] = useState<{ email: string; company: string } | null>(null);
  const [bad, setBad] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ email: string; company: string }>("GET", `token/${token}`)
      .then(setWho)
      .catch((e) => setBad((e as Error).message));
  }, [token]);
  return (
    <section className="b-narrow">
      <h1>{tx.b("set_password")}</h1>
      {bad ? (
        <p className="s-error">{bad}</p>
      ) : (
        who && (
          <form
            className="s-checkout"
            onSubmit={async (e) => {
              e.preventDefault();
              setError("");
              try {
                const me = await api<Me>("POST", `token/${token}`, { password });
                window.history.replaceState(null, "", ROOT);
                onIn(me);
              } catch (err) {
                setError((err as Error).message);
              }
            }}
          >
            <p>
              <strong>{who.company}</strong>
              <br />
              <span className="s-muted">{who.email}</span>
            </p>
            <input type="email" hidden readOnly autoComplete="username" value={who.email} />
            <label className="b-field">
              <span>{tx.b("password")}</span>
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <p className="s-muted">{tx.b("password_rule")}</p>
            <button className="s-btn wide">{tx.b("save_password")} →</button>
            {error && <p className="s-error">{error}</p>}
          </form>
        )
      )}
    </section>
  );
}

// ---- logged in -------------------------------------------------------------------------------

function PriceBox({
  tx,
  quote,
  onAdd,
}: {
  tx: Tx;
  quote: Quote;
  onAdd: (qty: number) => void;
}) {
  const [qty, setQty] = useState(1);
  const [added, setAdded] = useState(false);
  useEffect(() => setAdded(false), [quote.id]);
  return (
    <div className="s-price b-pricebox">
      <span>
        {tx.b("unit_price")} · {tx.b("ex_vat")}
      </span>
      <strong>{tx.eur(quote.price.unit_eur)}</strong>
      <small>
        {quote.price.source === "company_fixed" ? `${tx.b("fixed_price")} · ` : ""}
        {quote.pieces} {tx.w("pieces")} · {quote.cover_area_m2} m²
        {quote.price.support_eur
          ? ` · ${tx.w(quote.support)} ${tx.eur(quote.price.support_eur)}`
          : ""}
        {quote.price.indicative ? ` · ${tx.w("indicative")}` : ""}
      </small>
      <div className="b-qty">
        <label>
          {tx.b("qty")}{" "}
          <input
            type="number"
            min={1}
            max={999}
            value={qty}
            onChange={(e) => setQty(Math.max(1, Math.min(999, Number(e.target.value) || 1)))}
          />
        </label>
        <button
          className="s-btn small"
          onClick={() => {
            onAdd(qty);
            setAdded(true);
          }}
        >
          {tx.b("add")} →
        </button>
      </div>
      {added && <p className="b-ok">{tx.b("added")} ✓</p>}
    </div>
  );
}

function Configure({
  info,
  tx,
  onAdd,
}: {
  info: Info;
  tx: Tx;
  onAdd: (q: Quote, qty: number) => void;
}) {
  const products = info.options.products;
  const [product, setProduct] = useState("dining_set");
  const [sizes, setSizes] = useState<Record<string, number | boolean>>({});
  const [colour, setColour] = useState(info.settings.colours[0] ?? "");
  const [vents, setVents] = useState(true);
  const [support, setSupport] = useState("none");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const d: Record<string, number | boolean> = {};
    for (const f of products[product].fields) d[f.key] = f.default;
    setSizes(d);
    setSupport("none");
  }, [product, products]);
  useEffect(() => {
    if (!Object.keys(sizes).length) return;
    const t = setTimeout(async () => {
      setBusy(true);
      setError("");
      try {
        setQuote(
          await api<Quote>("POST", "quote", { product, sizes, colour, vents, support }),
        );
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    }, 400);
    return () => clearTimeout(t);
  }, [product, sizes, colour, vents, support]);
  const rain = quote?.rain;
  const supports = Object.entries(rain?.options ?? {}).filter(([k]) => k !== "frame");
  return (
    <section className="s-config b-config">
      <div className="s-config-view">
        <Scene url={quote?.scene ?? null} coverOpacity={0.6} />
        {busy && <span className="s-busy">…</span>}
        {rain && supports.length > 1 && (
          <div className="s-rain">
            <strong>{tx.w("rain")}</strong>
            {supports.map(([k, v]) => (
              <button
                key={k}
                className={`s-chip ${support === k ? "on" : ""} ${v.dry ? "dry" : "wet"}`}
                onClick={() => setSupport(k)}
              >
                {tx.w(k)}: {v.dry ? tx.w("dry") : tx.w("wet")}
              </button>
            ))}
            {rain.advice?.support === "balloons" && support === "none" && (
              <p className="s-advice">
                💧 {tx.w("advice_flat", { m2: rain.options.none.flat_m2 })}{" "}
                {tx.w("advice_balloons", { n: rain.advice.count })} (
                {tx.eur(rain.advice.price_eur)} {tx.b("ex_vat")})
              </p>
            )}
          </div>
        )}
      </div>
      <aside className="s-config-panel">
        <h2>{tx.b("tab_configure")}</h2>
        <p className="s-muted">{tx.w("what")}</p>
        <div className="s-products">
          {Object.keys(products).map((k) => (
            <button
              key={k}
              className={`s-card ${product === k ? "on" : ""}`}
              onClick={() => setProduct(k)}
            >
              {tx.product(k)}
            </button>
          ))}
        </div>
        {products[product].fields
          .filter((f) => !f.requires || !!sizes[f.requires])
          .map((f) =>
            f.min === null ? (
              <label key={f.key} className="s-check">
                <input
                  type="checkbox"
                  checked={!!sizes[f.key]}
                  onChange={(e) => setSizes({ ...sizes, [f.key]: e.target.checked })}
                />{" "}
                {tx.field(f.key)}
              </label>
            ) : (
              <label key={f.key} className="s-range">
                <span>
                  {tx.field(f.key)}
                  <b>
                    <input
                      className="b-cm"
                      type="number"
                      min={f.min}
                      max={f.max ?? undefined}
                      value={Number(sizes[f.key] ?? f.default)}
                      onChange={(e) =>
                        setSizes({ ...sizes, [f.key]: Number(e.target.value) })
                      }
                    />{" "}
                    cm
                  </b>
                </span>
                <input
                  type="range"
                  min={f.min}
                  max={f.max ?? undefined}
                  value={Number(sizes[f.key] ?? f.default)}
                  onChange={(e) => setSizes({ ...sizes, [f.key]: Number(e.target.value) })}
                />
              </label>
            ),
          )}
        <p className="s-muted">{tx.w("colour")}</p>
        <div className="s-swatches">
          {info.settings.colours.map((c) => (
            <button
              key={c}
              title={c}
              className={`s-swatch ${colour === c ? "on" : ""}`}
              style={{ background: SWATCH[c.toLowerCase()] ?? "#777" }}
              onClick={() => setColour(c)}
            />
          ))}
          <span>{colour}</span>
        </div>
        <label className="s-check">
          <input type="checkbox" checked={vents} onChange={(e) => setVents(e.target.checked)} />{" "}
          {tx.w("vents")}
        </label>
        {quote && <PriceBox tx={tx} quote={quote} onAdd={(n) => onAdd(quote, n)} />}
        {error && <p className="s-error">{error}</p>}
      </aside>
    </section>
  );
}

function Catalogue({
  info,
  tx,
  onAdd,
}: {
  info: Info;
  tx: Tx;
  onAdd: (q: Quote, qty: number) => void;
}) {
  const [items, setItems] = useState<Item[] | null>(null);
  const [kind, setKind] = useState("");
  const [find, setFind] = useState("");
  const [open, setOpen] = useState<Item | null>(null);
  const [colour, setColour] = useState(info.settings.colours[0] ?? "");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ items: Item[] }>("GET", "catalogue")
      .then((r) => setItems(r.items))
      .catch((e) => setError((e as Error).message));
  }, []);
  useEffect(() => {
    if (!open) return;
    setQuote(null);
    api<Quote>("POST", "quote", {
      product: open.kind,
      stock_model: open.model_id,
      colour,
      rain: false,
    })
      .then(setQuote)
      .catch((e) => setError((e as Error).message));
  }, [open, colour]);
  const kinds = useMemo(
    () => [...new Set((items ?? []).map((i) => i.kind))],
    [items],
  );
  const shown = (items ?? []).filter(
    (i) =>
      (!kind || i.kind === kind) &&
      (!find || `${i.name} ${i.model_id}`.toLowerCase().includes(find.toLowerCase())),
  );
  return (
    <section className="b-page">
      <h2>{tx.b("tab_catalogue")}</h2>
      <p className="s-muted">
        {tx.b("catalogue_text")} {tx.b("prices_note")}
      </p>
      <div className="b-filters">
        <input
          type="search"
          placeholder={tx.b("search")}
          value={find}
          onChange={(e) => setFind(e.target.value)}
        />
        <button className={`s-chip ${kind === "" ? "on" : ""}`} onClick={() => setKind("")}>
          {tx.b("all")}
        </button>
        {kinds.map((k) => (
          <button
            key={k}
            className={`s-chip ${kind === k ? "on" : ""}`}
            onClick={() => setKind(k)}
          >
            {tx.product(k)}
          </button>
        ))}
      </div>
      {error && <p className="s-error">{error}</p>}
      {items === null && <p className="s-muted">…</p>}
      <div className="b-grid">
        {shown.map((i) => (
          <article
            key={i.model_id}
            className={`b-item ${open?.model_id === i.model_id ? "on" : ""}`}
          >
            <button className="b-item-head" onClick={() => setOpen(i)}>
              {i.photo ? (
                <img src={`/api/b2b/catalogue/${i.model_id}.jpg`} alt="" loading="lazy" />
              ) : (
                <div className="b-noimg">{tx.product(i.kind)}</div>
              )}
              <strong>{i.name}</strong>
              <span className="s-muted">
                {tx.product(i.kind)} · {i.size_cm.map((x) => Math.round(x)).join(" × ")} cm
              </span>
              {i.fixed_eur !== null ? (
                <span className="b-fixed">
                  {tx.b("fixed_price")}: {tx.eur(i.fixed_eur)} {tx.b("ex_vat")}
                </span>
              ) : (
                <span className="s-link">{tx.b("show_price")} →</span>
              )}
            </button>
            {open?.model_id === i.model_id && (
              <div className="b-item-body">
                <div className="s-swatches">
                  {info.settings.colours.map((c) => (
                    <button
                      key={c}
                      title={c}
                      className={`s-swatch ${colour === c ? "on" : ""}`}
                      style={{ background: SWATCH[c.toLowerCase()] ?? "#777" }}
                      onClick={() => setColour(c)}
                    />
                  ))}
                  <span>{colour}</span>
                </div>
                {quote ? (
                  <PriceBox tx={tx} quote={quote} onAdd={(n) => onAdd(quote, n)} />
                ) : (
                  <p className="s-muted">…</p>
                )}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function Cart({
  tx,
  me,
  lines,
  setLines,
  onOrdered,
}: {
  tx: Tx;
  me: Me;
  lines: Line[];
  setLines: (l: Line[]) => void;
  onOrdered: () => void;
}) {
  const [po, setPo] = useState("");
  const [note, setNote] = useState("");
  const [addressId, setAddressId] = useState<string>("");
  const [done, setDone] = useState<{ order: number } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const s = me.settings;
  const sub = lines.reduce((a, l) => a + l.quote.price.unit_eur * l.qty, 0);
  const net = sub + (lines.length ? s.shipping_eur : 0);
  const vat = (net * me.company.vat_pct) / 100;
  const short = s.min_order_eur > 0 && net < s.min_order_eur;
  const addresses = [me.company.invoice_address, ...me.company.addresses];
  if (done)
    return (
      <section className="b-narrow">
        <h2>{tx.b("ordered", { n: done.order })}</h2>
        <p>{tx.b("ordered_text")}</p>
      </section>
    );
  return (
    <section className="b-page">
      <h2>{tx.b("tab_cart")}</h2>
      {lines.length === 0 ? (
        <p className="s-muted">{tx.b("cart_empty")}</p>
      ) : (
        <>
          <table className="b-table">
            <thead>
              <tr>
                <th />
                <th>{tx.b("unit_price")}</th>
                <th>{tx.b("qty")}</th>
                <th>{tx.b("ex_vat")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={`${l.quote.id}-${i}`}>
                  <td>
                    <strong>{l.quote.label ?? tx.product(l.quote.product)}</strong>
                    <br />
                    <span className="s-muted">
                      {l.quote.colour} · {sizesText(l.quote.sizes_cm)} cm
                      {l.quote.support !== "none" ? ` · ${tx.w(l.quote.support)}` : ""}
                    </span>
                  </td>
                  <td>{tx.eur(l.quote.price.unit_eur)}</td>
                  <td>
                    <input
                      className="b-cm"
                      type="number"
                      min={1}
                      max={999}
                      aria-label={tx.b("qty")}
                      value={l.qty}
                      onChange={(e) =>
                        setLines(
                          lines.map((x, j) =>
                            j === i
                              ? { ...x, qty: Math.max(1, Math.min(999, Number(e.target.value) || 1)) }
                              : x,
                          ),
                        )
                      }
                    />
                  </td>
                  <td>{tx.eur(l.quote.price.unit_eur * l.qty)}</td>
                  <td>
                    <button
                      className="s-link"
                      onClick={() => setLines(lines.filter((_, j) => j !== i))}
                    >
                      {tx.b("remove")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="b-checkout">
            <form
              className="s-checkout"
              onSubmit={async (e) => {
                e.preventDefault();
                setError("");
                setBusy(true);
                try {
                  const r = await api<{ order: number }>(
                    "POST",
                    "order",
                    {
                      lines: lines.map((l) => ({ quote_id: l.quote.id, qty: l.qty })),
                      address_id: addressId || null,
                      po,
                      note,
                      lang: tx.lang,
                    },
                    me.csrf,
                  );
                  setDone(r);
                  onOrdered();
                } catch (err) {
                  setError((err as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label className="b-field">
                <span>{tx.b("po")}</span>
                <input value={po} maxLength={60} onChange={(e) => setPo(e.target.value)} />
              </label>
              <label className="b-field">
                <span>{tx.b("deliver_to")}</span>
                <select value={addressId} onChange={(e) => setAddressId(e.target.value)}>
                  {addresses.map((a) => (
                    <option key={a.id ?? ""} value={a.id ?? ""}>
                      {a.id ? a.label || a.name : tx.b("invoice_address")}: {a.street},{" "}
                      {a.city} {a.country}
                    </option>
                  ))}
                </select>
              </label>
              <label className="b-field">
                <span>{tx.b("note")}</span>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <p className="b-account">✓ {tx.b("on_account")}</p>
              <button className="s-btn wide" disabled={busy || short}>
                {tx.b("place_order")} →
              </button>
              {short && (
                <p className="s-error">{tx.b("min_order", { eur: tx.eur(s.min_order_eur) })}</p>
              )}
              {error && <p className="s-error">{error}</p>}
            </form>
            <dl className="b-totals">
              <dt>{tx.b("subtotal")}</dt>
              <dd>{tx.eur(sub)}</dd>
              {s.shipping_eur > 0 && (
                <>
                  <dt>{tx.b("shipping")}</dt>
                  <dd>{tx.eur(s.shipping_eur)}</dd>
                </>
              )}
              <dt>
                {me.company.reverse_charge
                  ? tx.b("reverse_charge")
                  : `${tx.b("vat")} ${me.company.vat_pct} %`}
              </dt>
              <dd>{tx.eur(vat)}</dd>
              <dt className="b-total">{tx.b("incl_vat")}</dt>
              <dd className="b-total">{tx.eur(net + vat)}</dd>
            </dl>
          </div>
        </>
      )}
    </section>
  );
}

function Orders({
  tx,
  me,
  onAgain,
}: {
  tx: Tx;
  me: Me;
  onAgain: (lines: Line[]) => void;
}) {
  const [orders, setOrders] = useState<PastOrder[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ orders: PastOrder[] }>("GET", "orders")
      .then((r) => setOrders(r.orders))
      .catch((e) => setError((e as Error).message));
  }, []);
  return (
    <section className="b-page">
      <h2>{tx.b("tab_orders")}</h2>
      {error && <p className="s-error">{error}</p>}
      {orders?.length === 0 && <p className="s-muted">{tx.b("no_orders")}</p>}
      {orders?.map((o) => (
        <article key={o.id} className="b-order">
          <header>
            <strong>{tx.b("order_n", { n: o.id })}</strong>
            <span className="s-muted">
              {new Date(o.created * 1000).toLocaleDateString(tx.lang)}
              {o.po ? ` · ${o.po}` : ""} · {o.address.city}
            </span>
            <span>
              {tx.eur(o.net_eur)} {tx.b("ex_vat")}
            </span>
            <button
              className="s-btn small"
              onClick={async () => {
                try {
                  const r = await api<{ lines: Line[] }>(
                    "POST",
                    `orders/${o.id}/reorder`,
                    {},
                    me.csrf,
                  );
                  onAgain(r.lines);
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              {tx.b("reorder")} →
            </button>
          </header>
          <ul>
            {o.lines.map((l, i) => (
              <li key={i}>
                {l.qty} × {l.label ?? tx.product(l.product)}, {l.colour},{" "}
                {sizesText(l.sizes_cm)} cm · {tx.eur(l.unit_eur)}{" "}
                <span className="b-status">{tx.status(l.status)}</span>
              </li>
            ))}
          </ul>
        </article>
      ))}
    </section>
  );
}

function Addresses({ tx, me, onSaved }: { tx: Tx; me: Me; onSaved: () => void }) {
  const empty: Addr = {
    id: null,
    label: "",
    name: "",
    street: "",
    postcode: "",
    city: "",
    country: "NL",
  };
  const [list, setList] = useState<Addr[]>(me.company.addresses);
  const [add, setAdd] = useState<Addr>(empty);
  const [msg, setMsg] = useState("");
  const save = async (next: Addr[]) => {
    setMsg("");
    try {
      const r = await api<{ addresses: Addr[] }>("PUT", "addresses", { addresses: next }, me.csrf);
      setList(r.addresses);
      setMsg(tx.b("saved"));
      onSaved();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };
  const inv = me.company.invoice_address;
  return (
    <section className="b-page b-two">
      <div>
        <h2>{tx.b("tab_addresses")}</h2>
        <div className="b-box">
          <strong>{tx.b("invoice_address")}</strong>
          <p>
            {inv.name}
            <br />
            {inv.street}
            <br />
            {inv.postcode} {inv.city} {inv.country}
          </p>
        </div>
        {list.map((a) => (
          <div className="b-box" key={a.id}>
            <strong>{a.label || a.name}</strong>
            <p>
              {a.name}
              <br />
              {a.street}
              <br />
              {a.postcode} {a.city} {a.country}
            </p>
            <button className="s-link" onClick={() => save(list.filter((x) => x.id !== a.id))}>
              {tx.b("remove")}
            </button>
          </div>
        ))}
      </div>
      <form
        className="s-checkout"
        onSubmit={(e) => {
          e.preventDefault();
          save([...list, add]).then(() => setAdd(empty));
        }}
      >
        <h3>{tx.b("add_address")}</h3>
        {(
          [
            ["label", tx.b("address_label")],
            ["name", tx.w("name")],
            ["street", tx.w("street")],
            ["postcode", tx.w("postcode")],
            ["city", tx.w("city")],
            ["country", tx.w("country")],
          ] as const
        ).map(([k, l]) => (
          <label className="b-field" key={k}>
            <span>{l}</span>
            <input
              required={["street", "postcode", "city", "country"].includes(k)}
              maxLength={k === "country" ? 2 : 160}
              value={add[k]}
              onChange={(e) => setAdd({ ...add, [k]: e.target.value })}
            />
          </label>
        ))}
        <button className="s-btn">{tx.b("save")}</button>
        {msg && <p className="s-muted">{msg}</p>}
      </form>
    </section>
  );
}

function Account({ tx, me, onOut }: { tx: Tx; me: Me; onOut: () => void }) {
  const [old, setOld] = useState("");
  const [neu, setNeu] = useState("");
  const [msg, setMsg] = useState("");
  const c = me.company;
  return (
    <section className="b-page b-two">
      <div>
        <h2>{c.name}</h2>
        <p>
          {tx.b("vat_number")}: {c.vat_number || "—"}
          <br />
          {tx.b("contact")}: {c.contact || "—"}
          <br />
          {me.user.email}
        </p>
        <p className="s-muted">
          {tx.b("prices_note")} ({c.price_list})
        </p>
        <button
          className="s-btn small"
          onClick={async () => {
            await api("POST", "logout", {}).catch(() => undefined);
            onOut();
          }}
        >
          {tx.b("logout")}
        </button>
      </div>
      <form
        className="s-checkout"
        onSubmit={async (e) => {
          e.preventDefault();
          setMsg("");
          try {
            await api("POST", "password", { old, new: neu }, me.csrf);
            setOld("");
            setNeu("");
            setMsg(tx.b("saved"));
          } catch (err) {
            setMsg((err as Error).message);
          }
        }}
      >
        <h3>{tx.b("change_password")}</h3>
        <input type="email" hidden readOnly autoComplete="username" value={me.user.email} />
        <label className="b-field">
          <span>{tx.b("old_password")}</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={old}
            onChange={(e) => setOld(e.target.value)}
          />
        </label>
        <label className="b-field">
          <span>{tx.b("new_password")}</span>
          <input
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            value={neu}
            onChange={(e) => setNeu(e.target.value)}
          />
        </label>
        <button className="s-btn">{tx.b("save")}</button>
        {msg && <p className="s-muted">{msg}</p>}
      </form>
    </section>
  );
}

type Tab = "catalogue" | "configure" | "cart" | "orders" | "addresses" | "account";

function Shop({
  info,
  tx,
  me,
  reload,
  onOut,
}: {
  info: Info;
  tx: Tx;
  me: Me;
  reload: () => void;
  onOut: () => void;
}) {
  const key = `b2b-cart:${me.user.email}`;
  const [tab, setTab] = useState<Tab>(() => {
    const h = window.location.hash.slice(1) as Tab;
    return ["catalogue", "configure", "cart", "orders", "addresses", "account"].includes(h)
      ? h
      : "catalogue";
  });
  const [lines, setLinesState] = useState<Line[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(key) ?? "[]") as Line[];
    } catch {
      return [];
    }
  });
  const setLines = useCallback(
    (l: Line[]) => {
      setLinesState(l);
      try {
        localStorage.setItem(key, JSON.stringify(l));
      } catch {
        /* the order list still works for this visit */
      }
    },
    [key],
  );
  const go = (t: Tab) => {
    setTab(t);
    window.history.replaceState(null, "", `#${t}`);
    window.scrollTo(0, 0);
  };
  const add = (q: Quote, qty: number) => setLines([...lines, { quote: q, qty }]);
  const count = lines.reduce((a, l) => a + l.qty, 0);
  return (
    <>
      <nav className="b-tabs">
        <span className="b-who">
          {tx.b("welcome", { name: me.user.name || me.company.name })} · {me.company.name}
        </span>
        {(["catalogue", "configure", "cart", "orders", "addresses", "account"] as Tab[]).map(
          (t) => (
            <button key={t} className={tab === t ? "on" : ""} onClick={() => go(t)}>
              {tx.b(`tab_${t}`)}
              {t === "cart" && count > 0 ? ` (${count})` : ""}
            </button>
          ),
        )}
      </nav>
      {tab === "catalogue" && <Catalogue info={info} tx={tx} onAdd={add} />}
      {tab === "configure" && <Configure info={info} tx={tx} onAdd={add} />}
      {tab === "cart" && (
        <Cart tx={tx} me={me} lines={lines} setLines={setLines} onOrdered={() => setLines([])} />
      )}
      {tab === "orders" && (
        <Orders
          tx={tx}
          me={me}
          onAgain={(l) => {
            setLines([...lines, ...l]);
            go("cart");
          }}
        />
      )}
      {tab === "addresses" && <Addresses tx={tx} me={me} onSaved={reload} />}
      {tab === "account" && <Account tx={tx} me={me} onOut={onOut} />}
    </>
  );
}

function App() {
  const [info, setInfo] = useState<Info | null>(null);
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const page = window.location.pathname.replace(/\/+$/, "").split(/\/b2b\/?/)[1] ?? "";
  const loadMe = useCallback(
    () =>
      api<Me>("GET", "me")
        .then(setMe)
        .catch(() => setMe(null)),
    [],
  );
  useEffect(() => {
    fetch("/api/shop/info")
      .then((r) => r.json())
      .then(setInfo);
    loadMe();
  }, [loadMe]);
  const langs = info?.settings.languages ?? ["nl"];
  const [lang, setLang] = useState<string>(() => {
    try {
      return localStorage.getItem("lang") ?? "";
    } catch {
      return "";
    }
  });
  const want = lang || me?.user.lang || navigator.language.slice(0, 2).toLowerCase();
  const use = langs.includes(want) ? want : langs[0];
  const tx = useMemo(() => (info ? makeTx(info, use) : null), [info, use]);
  useEffect(() => {
    document.documentElement.lang = use;
    if (tx) document.title = tx.b("title");
  }, [use, tx]);
  if (!info || !tx || me === undefined) return null;
  const token = page.match(/^(welcome|reset)\/([A-Za-z0-9_-]+)$/);
  const logo = info.settings.logo_url.replace("-white", "-color");
  return (
    <div className="s-app b-app">
      <header className="s-head light b-head">
        <a href={ROOT} className="s-logo">
          {logo ? (
            <img src={logo} alt={info.settings.company.name || "S2DIO"} />
          ) : (
            info.settings.company.name || "Covers"
          )}
          <span className="b-badge">{tx.b("title")}</span>
        </a>
        <nav>
          {langs.length > 1 && (
            <select
              className="s-lang"
              aria-label={tx.w("language")}
              value={use}
              onChange={(e) => {
                setLang(e.target.value);
                try {
                  localStorage.setItem("lang", e.target.value);
                } catch {
                  /* no storage */
                }
              }}
            >
              {langs.map((l) => (
                <option key={l} value={l}>
                  {l.toUpperCase()}
                </option>
              ))}
            </select>
          )}
        </nav>
      </header>
      <main className="b-main">
        {token ? (
          <SetPassword
            tx={tx}
            token={token[2]}
            onIn={(m) => {
              setMe(m);
            }}
          />
        ) : me ? (
          <Shop
            info={info}
            tx={tx}
            me={me}
            reload={loadMe}
            onOut={() => {
              setMe(null);
              window.history.replaceState(null, "", ROOT);
            }}
          />
        ) : page === "request" ? (
          <RequestAccount tx={tx} />
        ) : page === "forgot" ? (
          <Forgot tx={tx} />
        ) : (
          <Login tx={tx} onIn={setMe} />
        )}
      </main>
    </div>
  );
}

createRoot(document.getElementById("b2b")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
