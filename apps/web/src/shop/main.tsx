// The cover webshop (ADR-062, ADR-064): the landing page with the film, how it works, the green
// story, the FAQ, the configurator (our own 3D furniture, the cover, the rain and the support
// upsell, and which existing cover already fits), the checkout, the order status, the match
// proposal, the fit question and the legal pages. Every text, buttons included, comes from the
// site's content in as many languages as the shop is set to (the AI CMS translates); a language
// other than the first lives under /shop/<lang>/. The server puts the same text in the HTML for
// search engines; this replaces it once loaded.
import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./shop.css";
import { Scene } from "./Scene";

type T = Record<string, string>;
interface Content {
  meta: { title: T; description: T };
  hero: { title: T; subtitle: T; cta: T };
  steps: { title: T; text: T }[];
  green: { title: T; points: T[] };
  faq: { q: T; a: T }[];
  legal: Record<string, T>;
  ui: {
    words: Record<string, T>;
    status: Record<string, T>;
    field: Record<string, T>;
    product: Record<string, T>;
  };
}
interface Field {
  key: string;
  default: number | boolean;
  min: number | null;
  max: number | null;
  unit: string | null;
}
interface Info {
  content: Content;
  preview: boolean;
  settings: {
    company: Record<string, string>;
    shipping: { country: string; name: string; eur: number }[];
    payment: boolean;
    film_url: string;
    colours: string[];
    indicative: boolean;
    languages: string[];
    matching: "shadow" | "auto";
  };
  options: { products: Record<string, { label: string; fields: Field[] }> };
}
interface RainOption {
  ponds: number;
  water_l: number;
  flat_m2: number;
  dry: boolean;
  water: string | null;
}
interface Quote {
  id: string;
  product: string;
  pieces: number;
  cover_area_m2: number;
  fabric_m2: number;
  vents: number;
  balloons: number;
  colour: string;
  support: string;
  price: {
    cover_eur: number;
    support_eur: number;
    total_eur: number;
    indicative: boolean;
  };
  rain: {
    options: Record<string, RainOption>;
    advice: {
      support: string;
      count: number;
      price_eur: number;
      why: string;
    } | null;
  };
  scene: string;
  stock: { model_id: string; name: string } | null;
}
interface MatchSize {
  size: string;
  customer_cm: number;
  cover_cm: number;
  difference_cm: number;
  fit_pct: number;
  verdict: "exact" | "roomier" | "tighter";
}
interface Match {
  model_id: string;
  name: string;
  size_cm: number[];
  photo: boolean;
  score_pct: number;
  sizes: MatchSize[];
}

const SWATCH: Record<string, string> = {
  charcoal: "#3d4039",
  navy: "#283548",
  "light grey": "#b9bab3",
  taupe: "#8c7c68",
  black: "#1f1f1f",
  sand: "#c8b593",
};
const euro = (n: number, lang: string) =>
  new Intl.NumberFormat(lang, { style: "currency", currency: "EUR" }).format(n);

// The words of the page in the chosen language (English, then Dutch, when one is missing).
interface Tx {
  lang: string;
  t: (x: T | undefined) => string;
  w: (key: string, vars?: Record<string, string | number>) => string;
  status: (key: string) => string;
  field: (key: string) => string;
  product: (key: string) => string;
  href: (page: string) => string;
}
function makeTx(info: Info, lang: string): Tx {
  const ui = info.content.ui;
  const first = info.settings.languages[0] ?? "nl";
  const t = (x: T | undefined) => (x ? (x[lang] ?? x.en ?? x.nl ?? "") : "");
  return {
    lang,
    t,
    w: (key, vars = {}) =>
      Object.entries(vars).reduce(
        (s, [k, v]) => s.split(`{${k}}`).join(String(v)),
        t(ui.words[key]) || key,
      ),
    status: (key) => t(ui.status[key]) || key,
    field: (key) => t(ui.field[key]) || key,
    product: (key) => t(ui.product[key]) || key,
    href: (page) => `/shop/${lang === first ? "" : `${lang}/`}${page}`,
  };
}

function useInView<E extends HTMLElement>(): [React.RefObject<E>, boolean] {
  const ref = useRef<E>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => e.isIntersecting && setSeen(true),
      { threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return [ref, seen];
}

function Reveal({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const [ref, seen] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className={`reveal ${seen ? "in" : ""} ${className}`}>
      {children}
    </div>
  );
}

function Header({ info, tx, page }: { info: Info; tx: Tx; page: string }) {
  const langs = info.settings.languages;
  return (
    <header className="s-head">
      <a href={tx.href("")} className="s-logo">
        <img src="/brand/s2dio-mark.svg" alt="" />{" "}
        {info.settings.company.name || "Covers"}
      </a>
      <nav>
        <a href={`${tx.href("")}#how`}>{tx.w("how")}</a>
        <a href={`${tx.href("")}#faq`}>{tx.w("faq")}</a>
        <a href={tx.href("configure")} className="s-btn small">
          {tx.w("configure")}
        </a>
        {langs.length > 1 && (
          <select
            className="s-lang"
            aria-label={tx.w("language")}
            value={tx.lang}
            onChange={(e) => {
              const l = e.target.value;
              try {
                localStorage.setItem("lang", l);
              } catch {
                /* no storage */
              }
              const first = langs[0];
              window.location.href = `/shop/${l === first ? "" : `${l}/`}${page}${window.location.search}`;
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
  );
}

function Home({ info, tx }: { info: Info; tx: Tx }) {
  const c = info.content;
  const { t, w } = tx;
  return (
    <>
      <section className="s-hero">
        {info.settings.film_url ? (
          <video
            className="s-film"
            src={info.settings.film_url}
            autoPlay
            muted
            loop
            playsInline
          />
        ) : (
          <div className="s-film">
            <Scene url="/api/shop/demo.glb" spin dark />
          </div>
        )}
        <div className="s-hero-text">
          <h1>{t(c.hero.title)}</h1>
          <p>{t(c.hero.subtitle)}</p>
          <a className="s-btn" href={tx.href("configure")}>
            {t(c.hero.cta)} →
          </a>
        </div>
      </section>
      <section className="s-section" id="how">
        <Reveal>
          <h2>{w("how")}</h2>
        </Reveal>
        <div className="s-steps">
          {c.steps.map((s, i) => (
            <Reveal key={i} className="s-step">
              <span className="s-num">{i + 1}</span>
              <h3>{t(s.title)}</h3>
              <p>{t(s.text)}</p>
            </Reveal>
          ))}
        </div>
      </section>
      <section className="s-section s-green">
        <Reveal>
          <h2>{t(c.green.title)}</h2>
        </Reveal>
        <div className="s-points">
          {c.green.points.map((p, i) => (
            <Reveal key={i} className="s-point">
              <span className="s-leaf">❋</span>
              <p>{t(p)}</p>
            </Reveal>
          ))}
        </div>
        <Reveal>
          <a className="s-btn" href={tx.href("configure")}>
            {t(c.hero.cta)} →
          </a>
        </Reveal>
      </section>
      <section className="s-section" id="faq">
        <Reveal>
          <h2>{w("faq")}</h2>
        </Reveal>
        <div className="s-faq">
          {c.faq.map((f, i) => (
            <details key={i}>
              <summary>{t(f.q)}</summary>
              <p>{t(f.a)}</p>
            </details>
          ))}
        </div>
      </section>
    </>
  );
}

// How one existing cover fits, size by size ("2 cm roomier in length").
function FitLines({ m, tx }: { m: Match; tx: Tx }) {
  return (
    <ul className="s-fit">
      {m.sizes.map((s) => (
        <li key={s.size} className={s.verdict}>
          {tx.w(`size_${s.size}`)}:{" "}
          {s.verdict === "exact"
            ? tx.w("match_exact")
            : tx.w(
                s.verdict === "roomier" ? "match_roomier" : "match_tighter",
                {
                  cm: Math.abs(Math.round(s.difference_cm)),
                },
              )}
        </li>
      ))}
    </ul>
  );
}

// Which existing cover already fits: at once (auto), or a colleague answers by mail (learning).
function MatchCard({
  info,
  tx,
  product,
  sizes,
  stock,
  onPick,
}: {
  info: Info;
  tx: Tx;
  product: string;
  sizes: Record<string, number | boolean>;
  stock: string | null;
  onPick: (m: Match | null, token: string | null) => void;
}) {
  const auto = info.settings.matching === "auto";
  const [res, setRes] = useState<{
    decision: string;
    match: Match | null;
    token: string;
  } | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setSent(false);
    if (!auto || !Object.keys(sizes).length) return;
    const timer = setTimeout(async () => {
      const r = await fetch("/api/shop/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product, sizes, lang: tx.lang }),
      });
      if (r.ok) setRes(await r.json());
    }, 700);
    return () => clearTimeout(timer);
  }, [auto, product, sizes, tx.lang]);
  if (stock) return null;
  if (!auto)
    return (
      <div className="s-match">
        <h3>{tx.w("match_title")}</h3>
        {sent ? (
          <p>{tx.w("match_sent")}</p>
        ) : (
          <form
            className="s-checkout"
            onSubmit={async (e) => {
              e.preventDefault();
              setError("");
              const r = await fetch("/api/shop/match", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  product,
                  sizes,
                  email,
                  name,
                  lang: tx.lang,
                }),
              });
              const d = await r.json();
              if (!r.ok) return setError(d.detail ?? "error");
              setSent(true);
            }}
          >
            <p className="s-muted">{tx.w("match_ask_text")}</p>
            <input
              placeholder={tx.w("name")}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <input
              placeholder={tx.w("email")}
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <button className="s-btn small">{tx.w("match_ask")} →</button>
            {error && <p className="s-error">{error}</p>}
          </form>
        )}
      </div>
    );
  if (!res) return null;
  const m = res.match;
  return (
    <div className={`s-match ${res.decision}`}>
      <h3>{tx.w("match_title")}</h3>
      {m && res.decision !== "custom" ? (
        <>
          <p className="s-match-pct">
            {tx.w("match_fits", { name: m.name, pct: Math.round(m.score_pct) })}
          </p>
          <p className="s-muted">
            {tx.w(
              res.decision === "existing" ? "match_existing" : "match_choice",
            )}
          </p>
          <FitLines m={m} tx={tx} />
          <button className="s-btn small" onClick={() => onPick(m, res.token)}>
            {tx.w("match_pick")} →
          </button>
        </>
      ) : (
        <p className="s-muted">{tx.w("match_custom")}</p>
      )}
    </div>
  );
}

function Configure({ info, tx }: { info: Info; tx: Tx }) {
  const { w, lang } = tx;
  const products = info.options.products;
  const start = useMemo(() => new URLSearchParams(window.location.search), []);
  const [product, setProduct] = useState(() => {
    const p = start.get("product");
    return p && products[p] ? p : "dining_set";
  });
  const [sizes, setSizes] = useState<Record<string, number | boolean>>({});
  const [stock, setStock] = useState<string | null>(start.get("stock"));
  const [matchToken, setMatchToken] = useState<string | null>(start.get("mt"));
  const [colour, setColour] = useState(info.settings.colours[0] ?? "");
  const [vents, setVents] = useState(true);
  const [support, setSupport] = useState("none");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showWater, setShowWater] = useState(true);
  const [step, setStep] = useState<"design" | "checkout">("design");
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    street: "",
    postcode: "",
    city: "",
    country: "NL",
    note: "",
    terms: false,
  });
  const [done, setDone] = useState<{
    status_url: string;
    checkout_url: string | null;
  } | null>(null);
  const first = useRef(true);

  useEffect(() => {
    const d: Record<string, number | boolean> = {};
    for (const f of products[product].fields) d[f.key] = f.default;
    if (first.current) {
      first.current = false;
      try {
        Object.assign(d, JSON.parse(start.get("sizes") ?? "{}"));
      } catch {
        /* no sizes given */
      }
    } else {
      setStock(null);
    }
    setSizes(d);
    setSupport("none");
  }, [product, products, start]);
  useEffect(() => {
    if (!Object.keys(sizes).length) return;
    const t = setTimeout(async () => {
      setBusy(true);
      setError("");
      try {
        const r = await fetch("/api/shop/quote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            product,
            sizes,
            colour,
            vents,
            support,
            stock_model: stock,
            match_token: stock ? matchToken : null,
          }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.detail ?? r.status);
        setQuote(data);
      } catch (e) {
        setError(String(e).replace(/^Error: /, ""));
      } finally {
        setBusy(false);
      }
    }, 400);
    return () => clearTimeout(t);
  }, [product, sizes, colour, vents, support, stock, matchToken]);

  const rain = quote?.rain;
  const water =
    rain && showWater ? (rain.options[support]?.water ?? null) : null;
  const overlay = useMemo(() => (water ? [water] : []), [water]);
  return (
    <section className="s-config">
      <div className="s-config-view">
        <Scene url={quote?.scene ?? null} overlays={overlay} />
        {busy && <span className="s-busy">…</span>}
        {rain && (
          <div className="s-rain">
            <strong>{w("rain")}</strong>
            {Object.entries(rain.options).map(([k, v]) => (
              <button
                key={k}
                className={`s-chip ${support === k ? "on" : ""} ${v.dry ? "dry" : "wet"}`}
                onClick={() => setSupport(k)}
              >
                {w(k)}: {v.dry ? w("dry") : w("wet")}
                {!v.dry && v.flat_m2 > 0 ? ` (${v.flat_m2} m²)` : ""}
              </button>
            ))}
            {rain.advice && support === "none" && (
              <p className="s-advice">
                💧 {w("advice_flat", { m2: rain.options.none.flat_m2 })}{" "}
                {rain.advice.support === "balloons"
                  ? w("advice_balloons", { n: rain.advice.count })
                  : w("advice_frame")}{" "}
                <button
                  className="s-btn small"
                  onClick={() => setSupport(rain.advice!.support)}
                >
                  + {w(rain.advice.support)} (
                  {euro(rain.advice.price_eur, lang)})
                </button>
              </p>
            )}
            <label className="s-check">
              <input
                type="checkbox"
                checked={showWater}
                onChange={(e) => setShowWater(e.target.checked)}
              />{" "}
              {w("show_water")}
            </label>
          </div>
        )}
      </div>
      <aside className="s-config-panel">
        {step === "design" && (
          <>
            <h1>{w("configure")}</h1>
            <p className="s-muted">{w("what")}</p>
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
            {stock && quote?.stock ? (
              <div className="s-match existing">
                <p className="s-match-pct">
                  {w("match_chosen", { name: quote.stock.name })}
                </p>
                <button
                  className="s-link"
                  onClick={() => {
                    setStock(null);
                    setMatchToken(null);
                  }}
                >
                  ← {w("match_custom_cta")}
                </button>
              </div>
            ) : (
              products[product].fields.map((f) =>
                f.min === null ? (
                  <label key={f.key} className="s-check">
                    <input
                      type="checkbox"
                      checked={!!sizes[f.key]}
                      onChange={(e) =>
                        setSizes({ ...sizes, [f.key]: e.target.checked })
                      }
                    />{" "}
                    {tx.field(f.key)}
                  </label>
                ) : (
                  <label key={f.key} className="s-range">
                    <span>
                      {tx.field(f.key)}
                      <b>{Number(sizes[f.key] ?? f.default)} cm</b>
                    </span>
                    <input
                      type="range"
                      min={f.min}
                      max={f.max ?? undefined}
                      value={Number(sizes[f.key] ?? f.default)}
                      onChange={(e) =>
                        setSizes({ ...sizes, [f.key]: Number(e.target.value) })
                      }
                    />
                  </label>
                ),
              )
            )}
            <MatchCard
              info={info}
              tx={tx}
              product={product}
              sizes={sizes}
              stock={stock}
              onPick={(m, token) => {
                setStock(m ? m.model_id : null);
                setMatchToken(token);
              }}
            />
            <p className="s-muted">{w("colour")}</p>
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
              <input
                type="checkbox"
                checked={vents}
                onChange={(e) => setVents(e.target.checked)}
              />{" "}
              {w("vents")}
            </label>
            {quote && (
              <div className="s-price">
                <span>{w("total")}</span>
                <strong>{euro(quote.price.total_eur, lang)}</strong>
                <small>
                  {quote.pieces} {w("pieces")} · {quote.cover_area_m2} m² ·{" "}
                  {quote.vents}× vent
                  {quote.price.support_eur
                    ? ` · ${w(quote.support)} ${euro(quote.price.support_eur, lang)}`
                    : ""}
                  {quote.price.indicative ? ` · ${w("indicative")}` : ""}
                </small>
                <button
                  className="s-btn wide"
                  onClick={() => setStep("checkout")}
                >
                  {w("order")} →
                </button>
              </div>
            )}
            {error && <p className="s-error">{error}</p>}
          </>
        )}
        {step === "checkout" && quote && !done && (
          <form
            className="s-checkout"
            onSubmit={async (e) => {
              e.preventDefault();
              setError("");
              const r = await fetch("/api/shop/order", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ quote_id: quote.id, ...form, lang }),
              });
              const data = await r.json();
              if (!r.ok) return setError(data.detail ?? "error");
              if (data.checkout_url) window.location.href = data.checkout_url;
              else setDone(data);
            }}
          >
            <button
              type="button"
              className="s-link"
              onClick={() => setStep("design")}
            >
              ← {w("configure")}
            </button>
            <h2>{w("order")}</h2>
            {(
              ["name", "email", "phone", "street", "postcode", "city"] as const
            ).map((k) => (
              <input
                key={k}
                placeholder={w(k)}
                required={k !== "phone"}
                type={k === "email" ? "email" : "text"}
                value={form[k]}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })}
              />
            ))}
            <select
              value={form.country}
              onChange={(e) => setForm({ ...form, country: e.target.value })}
            >
              {info.settings.shipping.map((s) => (
                <option key={s.country} value={s.country}>
                  {s.name} {s.eur ? `(+ ${euro(s.eur, lang)})` : ""}
                </option>
              ))}
            </select>
            <label className="s-check">
              <input
                type="checkbox"
                checked={form.terms}
                onChange={(e) => setForm({ ...form, terms: e.target.checked })}
              />{" "}
              <span>
                {w("terms")} (
                <a href={tx.href("terms")} target="_blank">
                  {w("terms_page")}
                </a>
                )
              </span>
            </label>
            <div className="s-price">
              <span>{w("total")}</span>
              <strong>{euro(quote.price.total_eur, lang)}</strong>
            </div>
            <button className="s-btn wide" disabled={!form.terms}>
              {info.settings.payment ? w("pay") : w("place")} →
            </button>
            {error && <p className="s-error">{error}</p>}
          </form>
        )}
        {done && (
          <div className="s-done">
            <h2>{w("thanks")}</h2>
            <p>{w("thanks_text")}</p>
            <a className="s-btn" href={done.status_url}>
              {w("status")} →
            </a>
          </div>
        )}
      </aside>
    </section>
  );
}

function OrderStatus({ token, tx }: { token: string; tx: Tx }) {
  const [o, setO] = useState<{
    order: number;
    status: string;
    total_eur: number;
    product: string;
    colour: string;
  } | null>(null);
  useEffect(() => {
    fetch(`/api/shop/order/${token}`)
      .then((r) => r.json())
      .then(setO)
      .catch(() => setO(null));
  }, [token]);
  if (!o) return <section className="s-section">…</section>;
  const steps = [
    "awaiting_payment",
    "paid",
    "in_production",
    "sewn",
    "shipped",
  ];
  const at = steps.indexOf(o.status);
  return (
    <section className="s-section s-status">
      <h1>
        {tx.w("status")} #{o.order}
      </h1>
      <p className="s-muted">
        {tx.product(o.product)} · {o.colour} · {euro(o.total_eur, tx.lang)}
      </p>
      <ol className="s-track">
        {steps.map((s, i) => (
          <li key={s} className={i <= at ? "on" : ""}>
            {tx.status(s)}
          </li>
        ))}
      </ol>
      {at < 0 && <p>{tx.status(o.status)}</p>}
    </section>
  );
}

// The answer to a match request (learning mode): the cover a colleague chose, or custom.
function MatchAnswer({ token, tx }: { token: string; tx: Tx }) {
  const [a, setA] = useState<{
    status: string;
    product?: string;
    sizes?: Record<string, number | boolean>;
    decision?: string;
    match?: Match | null;
    note?: string | null;
  } | null>(null);
  useEffect(() => {
    fetch(`/api/shop/match/${token}`)
      .then((r) => r.json())
      .then(setA)
      .catch(() => setA(null));
  }, [token]);
  if (!a) return <section className="s-section">…</section>;
  const q = (extra: Record<string, string>) =>
    `${tx.href("configure")}?${new URLSearchParams({
      product: a.product ?? "",
      sizes: JSON.stringify(a.sizes ?? {}),
      ...extra,
    })}`;
  return (
    <section className="s-section s-status">
      <h1>{tx.w("proposal")}</h1>
      {a.status !== "answered" ? (
        <p>{tx.w("proposal_wait")}</p>
      ) : a.match && a.decision !== "custom" ? (
        <div className="s-match existing">
          <p className="s-match-pct">
            {tx.w("match_fits", {
              name: a.match.name,
              pct: Math.round(a.match.score_pct),
            })}
          </p>
          <FitLines m={a.match} tx={tx} />
          {a.note && <p>{a.note}</p>}
          <a className="s-btn" href={q({ stock: a.match.model_id, mt: token })}>
            {tx.w("match_pick")} →
          </a>{" "}
          <a className="s-link" href={q({})}>
            {tx.w("match_custom_cta")}
          </a>
        </div>
      ) : (
        <div className="s-match custom">
          <p>{tx.w("match_custom")}</p>
          {a.note && <p>{a.note}</p>}
          <a className="s-btn" href={q({})}>
            {tx.w("match_custom_cta")} →
          </a>
        </div>
      )}
    </section>
  );
}

// The one question after delivery: how does it fit (1-5), a comment and a photo if you like.
function FitQuestion({ token, tx }: { token: string; tx: Tx }) {
  const [score, setScore] = useState(0);
  const [comment, setComment] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  return (
    <section className="s-section s-status">
      <h1>{tx.w("fit_title")}</h1>
      {done ? (
        <p>{tx.w("fit_thanks")}</p>
      ) : (
        <form
          className="s-checkout s-fit-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            const r = await fetch(`/api/shop/fit/${token}`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ score, comment }),
            });
            if (!r.ok) return setError((await r.json()).detail ?? "error");
            if (photo)
              await fetch(`/api/shop/fit/${token}/photo`, {
                method: "POST",
                body: photo,
              });
            setDone(true);
          }}
        >
          <div className="s-stars" role="radiogroup">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                type="button"
                key={n}
                role="radio"
                aria-checked={score === n}
                className={n <= score ? "on" : ""}
                onClick={() => setScore(n)}
              >
                ★
              </button>
            ))}
          </div>
          <textarea
            placeholder={tx.w("fit_comment")}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <label className="s-check">
            {tx.w("fit_photo")}{" "}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
            />
          </label>
          <button className="s-btn" disabled={!score}>
            {tx.w("fit_send")} →
          </button>
          {error && <p className="s-error">{error}</p>}
        </form>
      )}
    </section>
  );
}

function Legal({ info, tx, page }: { info: Info; tx: Tx; page: string }) {
  const text = tx.t(info.content.legal[page]);
  return (
    <section className="s-section s-legal">
      <h1>{tx.w(page === "terms" ? "terms_page" : page)}</h1>
      {text ? (
        text.split(/\n\n+/).map((p, i) => <p key={i}>{p}</p>)
      ) : (
        <p className="s-muted">{tx.w("empty")}</p>
      )}
    </section>
  );
}

function Footer({ info, tx }: { info: Info; tx: Tx }) {
  const c = info.settings.company;
  return (
    <footer className="s-foot">
      <div>
        <strong>{c.name || "Covers"}</strong>
        <p className="s-muted">
          {[c.city, c.country].filter(Boolean).join(", ")}{" "}
          {c.email && `· ${c.email}`} {c.phone && `· ${c.phone}`}
        </p>
      </div>
      <nav>
        <a href={tx.href("terms")}>{tx.w("terms_page")}</a>
        <a href={tx.href("privacy")}>{tx.w("privacy")}</a>
        <a href={tx.href("warranty")}>{tx.w("warranty")}</a>
      </nav>
    </footer>
  );
}

function App() {
  const [info, setInfo] = useState<Info | null>(null);
  useEffect(() => {
    const preview = new URLSearchParams(window.location.search).get("preview");
    fetch(
      `/api/shop/info${preview ? `?preview=${encodeURIComponent(preview)}` : ""}`,
    )
      .then((r) => r.json())
      .then(setInfo);
  }, []);
  const langs = useMemo(() => info?.settings.languages ?? ["nl"], [info]);
  const parts = window.location.pathname
    .replace(/\/+$/, "")
    .replace(/^\/shop\/?/, "")
    .split("/");
  const prefixed = langs.includes(parts[0]) && parts[0] !== langs[0];
  const lang = prefixed ? parts[0] : langs[0];
  const page = (prefixed ? parts.slice(1) : parts).join("/");
  useEffect(() => {
    if (!info || prefixed) return;
    // a visitor on the first language whose own (or chosen) language the shop also speaks
    let want = "";
    try {
      want = localStorage.getItem("lang") ?? "";
    } catch {
      /* no storage */
    }
    want = want || navigator.language.slice(0, 2).toLowerCase();
    if (want !== langs[0] && langs.includes(want))
      window.location.replace(
        `/shop/${want}/${page}${window.location.search}${window.location.hash}`,
      );
  }, [info, prefixed, langs, page]);
  const tx = useMemo(() => (info ? makeTx(info, lang) : null), [info, lang]);
  useEffect(() => {
    document.documentElement.lang = lang;
    if (info && tx) document.title = tx.t(info.content.meta.title);
  }, [lang, info, tx]);
  if (!info || !tx) return null;
  const order = page.match(/^order\/([A-Za-z0-9_-]+)$/);
  const match = page.match(/^match\/([A-Za-z0-9_-]+)$/);
  const fit = page.match(/^fit\/([A-Za-z0-9_-]+)$/);
  const legal = page.match(/^(terms|privacy|warranty)$/);
  return (
    <div className="s-app">
      {info.preview && <div className="s-preview">{tx.w("preview")}</div>}
      <Header info={info} tx={tx} page={page} />
      <main>
        {page === "configure" ? (
          <Configure info={info} tx={tx} />
        ) : order ? (
          <OrderStatus token={order[1]} tx={tx} />
        ) : match ? (
          <MatchAnswer token={match[1]} tx={tx} />
        ) : fit ? (
          <FitQuestion token={fit[1]} tx={tx} />
        ) : legal ? (
          <Legal info={info} tx={tx} page={legal[1]} />
        ) : (
          <Home info={info} tx={tx} />
        )}
      </main>
      <Footer info={info} tx={tx} />
    </div>
  );
}

createRoot(document.getElementById("shop")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
