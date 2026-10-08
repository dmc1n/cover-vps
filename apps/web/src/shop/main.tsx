// The cover webshop (ADR-062, ADR-064): the landing page with the film, how it works, the green
// story, the FAQ, the configurator (our own 3D furniture, the cover, the rain and the support
// upsell, and which existing cover already fits), the checkout, the order status, the match
// proposal, the fit question and the legal pages. Every text, buttons included, comes from the
// site's content in as many languages as the shop is set to (the AI CMS translates); a language
// other than the first lives under /shop/<lang>/. The server puts the same text in the HTML for
// search engines; this replaces it once loaded.
import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { Suggest, type Suggestion } from "./Suggest";
import { createRoot } from "react-dom/client";
import "./shop.css";
import { Scene } from "./Scene";
import { Story, StoryContent } from "./Story";
import { Icon } from "./Icons";

type T = Record<string, string>;
interface Content {
  meta: {
    title: T;
    description: T;
    pages?: Record<string, { title: T; description: T }>;
  };
  hero: { title: T; subtitle: T; cta: T };
  steps: { title: T; text: T }[];
  green: { title: T; points: T[] };
  faq: { q: T; a: T }[];
  legal: Record<string, T>;
  story?: StoryContent;
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
  /** asked only when this yes/no is ticked (a lounger's headrest sizes) */
  requires?: string | null;
}
interface Info {
  content: Content;
  preview: boolean;
  settings: {
    company: Record<string, string>;
    shipping: { country: string; name: string; eur: number }[];
    payment: boolean;
    /** Mollie's mode from the key's prefix (ADR-103): test payments move no money */
    payment_mode?: "test" | "live" | "none";
    film_url: string;
    film_poster: string;
    logo_url: string;
    home_story: boolean;
    story_model: string;
    story_media: Record<string, string>;
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
// On the website (its own domain, ADR-066) the shop is the whole site; on the studio it lives
// under /shop/ (the colleagues' preview).
const ROOT = window.location.pathname.startsWith("/shop") ? "/shop/" : "/";
// how far a slider is filled, for its track (ADR-105)
const fill = (v: number, min: number, max: number) =>
  ({
    "--p": `${max > min ? Math.round(((v - min) / (max - min)) * 1000) / 10 : 0}%`,
  }) as React.CSSProperties;
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
    href: (page) => `${ROOT}${lang === first ? "" : `${lang}/`}${page}`,
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
  // over the film the header is clear with light type; further down it turns light
  const [light, setLight] = useState(page !== "");
  // scrolled a little but still over the film: a dark glass, so the header never sits on text
  const [moved, setMoved] = useState(false);
  useEffect(() => {
    if (page !== "") return;
    const on = () => {
      setLight(window.scrollY > window.innerHeight * 0.8);
      setMoved(window.scrollY > 24);
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, [page]);
  return (
    <header className={`s-head ${light ? "light" : moved ? "moved" : ""}`}>
      <a href={tx.href("")} className="s-logo">
        {info.settings.logo_url ? (
          <img
            src={
              light
                ? info.settings.logo_url.replace("-white", "-color")
                : info.settings.logo_url
            }
            alt={info.settings.company.name || "S2DIO"}
          />
        ) : (
          info.settings.company.name || "Covers"
        )}
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
              window.location.href = `${ROOT}${l === first ? "" : `${l}/`}${page}${window.location.search}`;
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
  // visitors who asked their device for less motion get the still picture
  const calm = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );
  // the scroll story (ADR-067): live once switched on, always on the preview address
  const story =
    info.settings.home_story || window.location.hostname.startsWith("preview.");
  if (story && c.story && info.settings.story_model)
    return (
      <Story
        t={t}
        hero={c.hero}
        story={c.story}
        media={{
          ...info.settings.story_media,
          hero: info.settings.story_media?.hero || info.settings.film_url,
        }}
        model={info.settings.story_model}
        cta={t(c.hero.cta)}
        configure={tx.href("configure")}
      >
        <section className="s-section" id="faq">
          <h2>{w("faq")}</h2>
          <div className="s-faq">
            {c.faq.map((f, i) => (
              <details key={i}>
                <summary>{t(f.q)}</summary>
                <p>{t(f.a)}</p>
              </details>
            ))}
          </div>
        </section>
      </Story>
    );
  return (
    <>
      <section className="s-hero">
        {info.settings.film_url && !calm ? (
          <video
            className="s-film"
            src={info.settings.film_url}
            poster={info.settings.film_poster || undefined}
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
          />
        ) : info.settings.film_poster ? (
          <img className="s-film" src={info.settings.film_poster} alt="" />
        ) : (
          <div className="s-film">
            <Scene url="/api/shop/demo.glb" spin={!calm} dark />
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
              <span className="s-num">{String(i + 1).padStart(2, "0")}</span>
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
// While the published price set is "indicative" (Admin → Prices & costing), every price says so
// plainly; the owner switches it off by publishing a set without it (ADR-098, ADR-103).
function Indicative({ tx }: { tx: Tx }) {
  return (
    <p className="s-indicative" role="note">
      <strong>{tx.w("indicative")}</strong> — {tx.w("indicative_note")}
    </p>
  );
}

// A field people never see or reach; a bot that fills every field is refused (ADR-103).
function Trap({ value, set }: { value: string; set: (v: string) => void }) {
  return (
    <input
      className="s-trap"
      name="website"
      tabIndex={-1}
      autoComplete="off"
      aria-hidden="true"
      value={value}
      onChange={(e) => set(e.target.value)}
    />
  );
}

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
  const [trap, setTrap] = useState("");
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
                  website: trap,
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
            <Trap value={trap} set={setTrap} />
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
  // started from a photo or a link (ADR-086): the sizes to apply once the product is set, the
  // ones the customer must still check, and what goes with the order for the workshop
  const pendingSizes = useRef<Record<string, number | boolean> | null>(null);
  const [estimated, setEstimated] = useState<string[]>([]);
  const [source, setSource] = useState<{
    url: string | null;
    summary: string;
    photos: File[];
  } | null>(null);
  const [stock, setStock] = useState<string | null>(start.get("stock"));
  const [matchToken, setMatchToken] = useState<string | null>(start.get("mt"));
  const [colour, setColour] = useState(info.settings.colours[0] ?? "");
  const [vents, setVents] = useState(true);
  const [support, setSupport] = useState("none");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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
    website: "", // the honeypot (ADR-103): people never see it
  });
  const [done, setDone] = useState<{
    status_url: string;
    checkout_url: string | null;
  } | null>(null);
  const first = useRef(true);
  // the delivery cost to the chosen country, shown before ordering (prices incl. VAT)
  const shipping =
    info.settings.shipping.find((s) => s.country === form.country)?.eur ?? 0;

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
    if (pendingSizes.current) {
      Object.assign(d, pendingSizes.current);
      pendingSizes.current = null;
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

  // how solid the cover is drawn (the owner, 6 Oct 2026: "too dark, a slider for the
  // transparency"); remembered per browser
  const [solid, setSolid] = useState<number>(() => {
    try {
      const v = Number(localStorage.getItem("cover-solid"));
      return v >= 0.15 && v <= 1 ? v : 0.6;
    } catch {
      return 0.6;
    }
  });
  const rain = quote?.rain;
  // the shop offers no support or balloons; the frame is off for now (the owner, 5 Oct 2026)
  const supports = Object.entries(rain?.options ?? {}).filter(
    ([k]) => k !== "frame",
  );
  return (
    <section className="s-config">
      <div className="s-config-view">
        <Scene url={quote?.scene ?? null} coverOpacity={solid} />
        <label className="s-solid">
          <span>{w("see_through")}</span>
          <input
            type="range"
            min={0.15}
            max={1}
            step={0.01}
            value={solid}
            style={fill(solid, 0.15, 1)}
            onChange={(e) => {
              const v = Number(e.target.value);
              setSolid(v);
              try {
                localStorage.setItem("cover-solid", String(v));
              } catch {
                /* the slider still works without storage */
              }
            }}
          />
        </label>
        {busy && <span className="s-busy">…</span>}
        {rain && (
          <div className="s-rain">
            <strong>{w("rain")}</strong>
            {supports.map(([k, v]) => (
              <button
                key={k}
                className={`s-chip ${support === k ? "on" : ""} ${v.dry ? "dry" : "wet"}`}
                onClick={() => setSupport(k)}
              >
                {w(k)}: {v.dry ? w("dry") : w("wet")}
                {!v.dry && v.flat_m2 > 0 ? ` (${v.flat_m2} m²)` : ""}
              </button>
            ))}
            {rain.advice?.support === "balloons" && support === "none" && (
              <p className="s-advice">
                <Icon name="drop" />{" "}
                {w("advice_flat", { m2: rain.options.none.flat_m2 })}{" "}
                {w("advice_balloons", { n: rain.advice.count })}{" "}
                <button
                  className="s-btn small"
                  onClick={() => setSupport(rain.advice!.support)}
                >
                  + {w(rain.advice.support)} (
                  {euro(rain.advice.price_eur, lang)})
                </button>
              </p>
            )}
          </div>
        )}
      </div>
      <aside className="s-config-panel">
        {step === "design" && (
          <>
            <h1>{w("configure")}</h1>
            <Suggest
              w={w}
              lang={lang}
              productName={tx.product}
              onUse={(sg: Suggestion, photos: File[]) => {
                pendingSizes.current = sg.sizes;
                setEstimated(sg.check);
                setSource({ url: sg.source.url, summary: sg.summary, photos });
                if (sg.product === product) {
                  setSizes({ ...sizes, ...sg.sizes });
                  pendingSizes.current = null;
                } else setProduct(sg.product);
              }}
            />
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
              products[product].fields
                .filter((f) => !f.requires || !!sizes[f.requires])
                .map((f) =>
                  f.min === null ? (
                    <label
                      key={f.key}
                      className={`s-check ${estimated.includes(f.key) ? "s-estimate" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={!!sizes[f.key]}
                        onChange={(e) => {
                          setSizes({ ...sizes, [f.key]: e.target.checked });
                          setEstimated(estimated.filter((k) => k !== f.key));
                        }}
                      />{" "}
                      {tx.field(f.key)}
                    </label>
                  ) : (
                    <label
                      key={f.key}
                      className={`s-range ${estimated.includes(f.key) ? "s-estimate" : ""}`}
                      title={
                        estimated.includes(f.key)
                          ? w("suggest_estimate")
                          : undefined
                      }
                    >
                      <span>
                        {tx.field(f.key)}
                        <b>{Number(sizes[f.key] ?? f.default)} cm</b>
                      </span>
                      <input
                        type="range"
                        min={f.min}
                        max={f.max ?? undefined}
                        value={Number(sizes[f.key] ?? f.default)}
                        style={fill(
                          Number(sizes[f.key] ?? f.default),
                          f.min,
                          f.max ?? 100,
                        )}
                        onChange={(e) => {
                          setSizes({
                            ...sizes,
                            [f.key]: Number(e.target.value),
                          });
                          setEstimated(estimated.filter((k) => k !== f.key));
                        }}
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
                </small>
                {quote.price.indicative && <Indicative tx={tx} />}
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
                body: JSON.stringify({
                  quote_id: quote.id,
                  ...form,
                  lang,
                  source_url: source?.url ?? null,
                  source_summary: source?.summary || null,
                }),
              });
              const data = await r.json();
              if (!r.ok) return setError(data.detail ?? "error");
              if (source?.photos.length) {
                // the photos the customer started from, kept with the order for the workshop
                const token = String(data.status_url ?? "")
                  .split("/")
                  .pop();
                const body = new FormData();
                for (const ph of source.photos) body.append("photos", ph);
                await fetch(`/api/shop/order/${token}/source`, {
                  method: "POST",
                  body,
                }).catch(() => undefined);
              }
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
                {w(quote.stock ? "terms_stock" : "terms")} (
                <a href={tx.href("terms")} target="_blank">
                  {w("terms_page")}
                </a>
                {", "}
                <a href={tx.href("returns")} target="_blank">
                  {pageTitle(info, tx, "returns")}
                </a>
                )
              </span>
            </label>
            <Trap
              value={form.website}
              set={(v) => setForm({ ...form, website: v })}
            />
            <div className="s-price">
              <small>
                {w("cover")} {euro(quote.price.total_eur, lang)} ·{" "}
                {w("shipping")} {euro(shipping, lang)}
              </small>
              <span>{w("total")}</span>
              <strong>{euro(quote.price.total_eur + shipping, lang)}</strong>
              {quote.price.indicative && <Indicative tx={tx} />}
            </div>
            {info.settings.payment_mode === "test" && (
              <p className="s-note">{w("test_payments")}</p>
            )}
            <button className="s-btn wide" disabled={!form.terms}>
              {info.settings.payment ? w("order_pay") : w("place_order")} →
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

// While a page's data loads: its shape, softly; when the link leads nowhere: say so (ADR-105).
function Loading({ tx }: { tx: Tx }) {
  return (
    <section className="s-section s-status" aria-busy="true">
      <div className="s-skeleton" role="status" aria-label={tx.w("loading")}>
        <span />
        <span />
        <span />
      </div>
    </section>
  );
}
function NotFound({ tx, title }: { tx: Tx; title: string }) {
  return (
    <section className="s-section s-status">
      <h1>{title}</h1>
      <div className="s-state">
        <p>{tx.w("not_found")}</p>
        <a className="s-btn" href={tx.href("configure")}>
          {tx.w("configure")} →
        </a>
      </div>
    </section>
  );
}

function OrderStatus({ token, tx }: { token: string; tx: Tx }) {
  // null while loading, false when there is no such order
  const [o, setO] = useState<
    | {
        order: number;
        status: string;
        total_eur: number;
        product: string;
        colour: string;
      }
    | null
    | false
  >(null);
  useEffect(() => {
    fetch(`/api/shop/order/${token}`)
      .then((r) => (r.ok ? r.json() : false))
      .then(setO)
      .catch(() => setO(false));
  }, [token]);
  if (o === null) return <Loading tx={tx} />;
  if (!o) return <NotFound tx={tx} title={tx.w("status")} />;
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
  const [a, setA] = useState<
    | {
        status: string;
        product?: string;
        sizes?: Record<string, number | boolean>;
        decision?: string;
        match?: Match | null;
        note?: string | null;
      }
    | null
    | false
  >(null);
  useEffect(() => {
    fetch(`/api/shop/match/${token}`)
      .then((r) => (r.ok ? r.json() : false))
      .then(setA)
      .catch(() => setA(false));
  }, [token]);
  if (a === null) return <Loading tx={tx} />;
  if (!a) return <NotFound tx={tx} title={tx.w("proposal")} />;
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

// The legal pages (ADR-103): terms, privacy, returns, cookies, contact and warranty. The server
// gives the owner's own text, or our draft marked "draft — to approve", with the company's
// details filled in. "## " is a heading, "- " a list item, a blank line a paragraph.
const LEGAL = ["terms", "privacy", "returns", "cookies", "contact", "warranty"];
const DRAFT = /^(CONCEPT|DRAFT) — /;

function LegalBlocks({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/\n\n+/)
        .map((b) => b.trim())
        .filter(Boolean)
        .map((block, i) => {
          const lines = block.split("\n");
          if (DRAFT.test(block))
            return (
              <p key={i} className="s-draft">
                <strong>{block}</strong>
              </p>
            );
          if (block.startsWith("## "))
            return (
              <div key={i}>
                <h2>{lines[0].slice(3)}</h2>
                {lines.length > 1 && (
                  <LegalBlocks text={lines.slice(1).join("\n")} />
                )}
              </div>
            );
          if (lines.every((l) => l.startsWith("- ")))
            return (
              <ul key={i}>
                {lines.map((l, j) => (
                  <li key={j}>{l.slice(2)}</li>
                ))}
              </ul>
            );
          return (
            <p key={i}>
              {lines.map((l, j) => (
                <span key={j}>
                  {j > 0 && <br />}
                  {l}
                </span>
              ))}
            </p>
          );
        })}
    </>
  );
}

function pageTitle(info: Info, tx: Tx, page: string): string {
  const own = info.content.meta.pages?.[page];
  return own ? tx.t(own.title) : tx.w(page === "terms" ? "terms_page" : page);
}

function Legal({ info, tx, page }: { info: Info; tx: Tx; page: string }) {
  const text = tx.t(info.content.legal[page]);
  return (
    <section className="s-section s-legal">
      <h1>{pageTitle(info, tx, page)}</h1>
      {text ? (
        <LegalBlocks text={text} />
      ) : (
        <p className="s-muted">{tx.w("empty")}</p>
      )}
    </section>
  );
}

function NotFound({ tx }: { tx: Tx }) {
  return (
    <section className="s-section s-legal">
      <h1>{tx.w("not_found")}</h1>
      <p>{tx.w("not_found_text")}</p>
      <p>
        <a className="s-btn" href={tx.href("")}>
          {tx.w("home")} →
        </a>
      </p>
    </section>
  );
}

function Footer({ info, tx }: { info: Info; tx: Tx }) {
  const c = info.settings.company;
  const logo = info.settings.logo_url;
  return (
    <footer className="s-foot">
      <div>
        {logo && (
          <img className="s-foot-logo" src={logo} alt={c.name || "S2DIO"} />
        )}
        {(c.name || !logo) && <strong>{c.name || "Covers"}</strong>}
        <p className="s-muted">
          {[
            c.city && c.country ? `${c.city}, ${c.country}` : c.city,
            c.email,
            c.phone,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>
      <nav>
        {LEGAL.map((p) => (
          <a key={p} href={tx.href(p)}>
            {pageTitle(info, tx, p)}
          </a>
        ))}
      </nav>
      {c.name && (
        <p className="s-foot-base">
          © {new Date().getFullYear()} {c.name}
        </p>
      )}
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
    .replace(ROOT === "/shop/" ? /^\/shop\/?/ : /^\//, "")
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
        `${ROOT}${want}/${page}${window.location.search}${window.location.hash}`,
      );
  }, [info, prefixed, langs, page]);
  const tx = useMemo(() => (info ? makeTx(info, lang) : null), [info, lang]);
  useEffect(() => {
    document.documentElement.lang = lang;
    if (!info || !tx) return;
    // the page's own title, as the server wrote it (ADR-103)
    const site = tx.t(info.content.meta.title);
    const own = info.content.meta.pages?.[page];
    const shopPage =
      page === "" ||
      /^(configure|order\/.+|match\/.+|fit\/.+|b2b(\/.*)?)$/.test(page) ||
      LEGAL.includes(page);
    document.title = own
      ? `${tx.t(own.title)} · ${site}`
      : shopPage
        ? site
        : `${tx.w("not_found")} · ${site}`;
  }, [lang, info, tx, page]);
  if (!info || !tx) return null;
  const order = page.match(/^order\/([A-Za-z0-9_-]+)$/);
  const match = page.match(/^match\/([A-Za-z0-9_-]+)$/);
  const fit = page.match(/^fit\/([A-Za-z0-9_-]+)$/);
  const legal = LEGAL.includes(page) ? [page, page] : null;
  // an address the shop does not know (the server answers 404 too); the business shop's own
  // pages (/b2b) are not this shop's
  const known =
    page === "" || page === "configure" || order || match || fit || legal;
  const missing = !known && !/^b2b(\/|$)/.test(page);
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
        ) : missing ? (
          <NotFound tx={tx} />
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
