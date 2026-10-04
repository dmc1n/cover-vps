// The cover webshop (ADR-062): the landing page with the film, how it works, the green story,
// the FAQ, the configurator (our own 3D furniture, the cover, the rain and the support upsell),
// the checkout, the order status and the legal pages. NL and EN. The server puts the same text in
// the HTML for search engines; this replaces it once loaded.
import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./shop.css";
import { Scene } from "./Scene";

type Lang = "nl" | "en";
type T = Record<Lang, string>;
interface Content {
  meta: { title: T; description: T };
  hero: { title: T; subtitle: T; cta: T };
  steps: { title: T; text: T }[];
  green: { title: T; points: T[] };
  faq: { q: T; a: T }[];
  legal: Record<string, T>;
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
}

const W: Record<string, T> = {
  how: { nl: "Zo werkt het", en: "How it works" },
  configure: { nl: "Ontwerp je hoes", en: "Design your cover" },
  what: { nl: "Wat wil je afdekken?", en: "What do you want to cover?" },
  colour: { nl: "Kleur", en: "Colour" },
  vents: {
    nl: "Ventilatie (aanbevolen: tegen vocht)",
    en: "Air vents (recommended: against damp)",
  },
  rain: { nl: "Regentest", en: "Rain test" },
  none: { nl: "Zonder steun", en: "No support" },
  balloons: { nl: "Met ballonnen", en: "With balloons" },
  frame: { nl: "Met frame", en: "With a frame" },
  dry: { nl: "Water loopt af", en: "Water runs off" },
  wet: { nl: "Water blijft staan", en: "Water stays" },
  total: { nl: "Totaal incl. btw", en: "Total incl. VAT" },
  indicative: { nl: "Indicatieve prijs", en: "Indicative price" },
  order: { nl: "Bestellen", en: "Order" },
  pay: { nl: "Naar betalen", en: "Go to payment" },
  place: { nl: "Bestelling plaatsen", en: "Place the order" },
  name: { nl: "Naam", en: "Name" },
  email: { nl: "E-mail", en: "E-mail" },
  phone: { nl: "Telefoon (optioneel)", en: "Phone (optional)" },
  street: { nl: "Straat en huisnummer", en: "Street and number" },
  postcode: { nl: "Postcode", en: "Postcode" },
  city: { nl: "Plaats", en: "City" },
  country: { nl: "Land", en: "Country" },
  terms: {
    nl: "Ik ga akkoord met de voorwaarden (maatwerk: geen herroepingsrecht)",
    en: "I accept the terms (made to measure: no right of withdrawal)",
  },
  status: { nl: "Je bestelling", en: "Your order" },
  faq: { nl: "Veelgestelde vragen", en: "Questions" },
  terms_page: { nl: "Voorwaarden", en: "Terms" },
  privacy: { nl: "Privacy", en: "Privacy" },
  warranty: { nl: "Garantie", en: "Warranty" },
  shipping: { nl: "Verzending", en: "Delivery" },
  pieces: { nl: "stukken", en: "pieces" },
  empty: { nl: "Deze tekst volgt nog.", en: "This text follows." },
};
const STATUS: Record<string, T> = {
  awaiting_payment: { nl: "Wacht op betaling", en: "Awaiting payment" },
  paid: { nl: "Betaald", en: "Paid" },
  in_production: { nl: "Wordt gemaakt", en: "Being made" },
  sewn: { nl: "Genaaid", en: "Sewn" },
  shipped: { nl: "Verzonden", en: "Shipped" },
  cancelled: { nl: "Geannuleerd", en: "Cancelled" },
  failed: { nl: "Betaling mislukt", en: "Payment failed" },
};
const SWATCH: Record<string, string> = {
  charcoal: "#3d4039",
  navy: "#283548",
  "light grey": "#b9bab3",
  taupe: "#8c7c68",
  black: "#1f1f1f",
  sand: "#c8b593",
};
const FIELD: Record<string, T> = {
  table_length_cm: { nl: "Lengte tafel", en: "Table length" },
  table_width_cm: { nl: "Breedte tafel", en: "Table width" },
  table_height_cm: { nl: "Hoogte tafel", en: "Table height" },
  table_diameter_cm: { nl: "Doorsnede tafel", en: "Table diameter" },
  chairs: { nl: "Stoelen meenemen", en: "Cover the chairs too" },
  length_cm: { nl: "Lengte", en: "Length" },
  depth_cm: { nl: "Diepte", en: "Depth" },
  width_cm: { nl: "Breedte", en: "Width" },
  height_cm: { nl: "Hoogte", en: "Height" },
  back_height_cm: { nl: "Hoogte rugleuning", en: "Back height" },
  front_height_cm: { nl: "Hoogte voorkant/armleuning", en: "Front/arm height" },
  long_side_cm: { nl: "Lange zijde", en: "Long side" },
  short_side_cm: { nl: "Korte zijde", en: "Short side" },
};
const PRODUCT: Record<string, T> = {
  dining_set: { nl: "Eettafel met stoelen", en: "Dining set" },
  round_set: { nl: "Ronde tafel", en: "Round dining set" },
  sofa: { nl: "Bank", en: "Sofa" },
  corner_sofa: { nl: "Hoekbank", en: "Corner sofa" },
  lounger: { nl: "Ligbed", en: "Sun lounger" },
  item: { nl: "Stoel, bijzettafel, hocker", en: "Chair, side table, hocker" },
};
const euro = (n: number) =>
  new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(
    n,
  );

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

function Header({
  lang,
  setLang,
  info,
}: {
  lang: Lang;
  setLang: (l: Lang) => void;
  info: Info;
}) {
  return (
    <header className="s-head">
      <a href="/shop/" className="s-logo">
        <img src="/brand/s2dio-mark.svg" alt="" />{" "}
        {info.settings.company.name || "Covers"}
      </a>
      <nav>
        <a href="/shop/#how">{W.how[lang]}</a>
        <a href="/shop/#faq">{W.faq[lang]}</a>
        <a href="/shop/configure" className="s-btn small">
          {W.configure[lang]}
        </a>
        <button
          className="s-lang"
          onClick={() => setLang(lang === "nl" ? "en" : "nl")}
        >
          {lang === "nl" ? "EN" : "NL"}
        </button>
      </nav>
    </header>
  );
}

function Home({ info, lang }: { info: Info; lang: Lang }) {
  const c = info.content;
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
          <h1>{c.hero.title[lang]}</h1>
          <p>{c.hero.subtitle[lang]}</p>
          <a className="s-btn" href="/shop/configure">
            {c.hero.cta[lang]} →
          </a>
        </div>
      </section>
      <section className="s-section" id="how">
        <Reveal>
          <h2>{W.how[lang]}</h2>
        </Reveal>
        <div className="s-steps">
          {c.steps.map((s, i) => (
            <Reveal key={i} className="s-step">
              <span className="s-num">{i + 1}</span>
              <h3>{s.title[lang]}</h3>
              <p>{s.text[lang]}</p>
            </Reveal>
          ))}
        </div>
      </section>
      <section className="s-section s-green">
        <Reveal>
          <h2>{c.green.title[lang]}</h2>
        </Reveal>
        <div className="s-points">
          {c.green.points.map((p, i) => (
            <Reveal key={i} className="s-point">
              <span className="s-leaf">❋</span>
              <p>{p[lang]}</p>
            </Reveal>
          ))}
        </div>
        <Reveal>
          <a className="s-btn" href="/shop/configure">
            {c.hero.cta[lang]} →
          </a>
        </Reveal>
      </section>
      <section className="s-section" id="faq">
        <Reveal>
          <h2>{W.faq[lang]}</h2>
        </Reveal>
        <div className="s-faq">
          {c.faq.map((f, i) => (
            <details key={i}>
              <summary>{f.q[lang]}</summary>
              <p>{f.a[lang]}</p>
            </details>
          ))}
        </div>
      </section>
    </>
  );
}

function Configure({ info, lang }: { info: Info; lang: Lang }) {
  const products = info.options.products;
  const [product, setProduct] = useState("dining_set");
  const [sizes, setSizes] = useState<Record<string, number | boolean>>({});
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
        const r = await fetch("/api/shop/quote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ product, sizes, colour, vents, support }),
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
  }, [product, sizes, colour, vents, support]);

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
            <strong>{W.rain[lang]}</strong>
            {Object.entries(rain.options).map(([k, v]) => (
              <button
                key={k}
                className={`s-chip ${support === k ? "on" : ""} ${v.dry ? "dry" : "wet"}`}
                onClick={() => setSupport(k)}
              >
                {W[k]?.[lang] ?? k}: {v.dry ? W.dry[lang] : W.wet[lang]}
                {!v.dry && v.flat_m2 > 0 ? ` (${v.flat_m2} m²)` : ""}
              </button>
            ))}
            {rain.advice && support === "none" && (
              <p className="s-advice">
                💧{" "}
                {lang === "nl"
                  ? `Zonder steun is ${rain.options.none.flat_m2} m² van het dak vlak: daar blijft water staan. ${
                      rain.advice.support === "balloons"
                        ? `Met ${rain.advice.count} ballon${rain.advice.count === 1 ? "" : "nen"} onder de hoes loopt het af.`
                        : "Met een frame krijgt het dak een vaste helling en loopt het af."
                    }`
                  : `Without support ${rain.options.none.flat_m2} m² of the top is flat: water stays. ${
                      rain.advice.support === "balloons"
                        ? `With ${rain.advice.count} balloon${rain.advice.count === 1 ? "" : "s"} under the cover it runs off.`
                        : "With a frame the top gets a fixed slope and the water runs off."
                    }`}{" "}
                <button
                  className="s-btn small"
                  onClick={() => setSupport(rain.advice!.support)}
                >
                  + {W[rain.advice.support][lang]} (
                  {euro(rain.advice.price_eur)})
                </button>
              </p>
            )}
            <label className="s-check">
              <input
                type="checkbox"
                checked={showWater}
                onChange={(e) => setShowWater(e.target.checked)}
              />{" "}
              {lang === "nl" ? "Toon het water" : "Show the water"}
            </label>
          </div>
        )}
      </div>
      <aside className="s-config-panel">
        {step === "design" && (
          <>
            <h1>{W.configure[lang]}</h1>
            <p className="s-muted">{W.what[lang]}</p>
            <div className="s-products">
              {Object.keys(products).map((k) => (
                <button
                  key={k}
                  className={`s-card ${product === k ? "on" : ""}`}
                  onClick={() => setProduct(k)}
                >
                  {PRODUCT[k]?.[lang] ?? products[k].label}
                </button>
              ))}
            </div>
            {products[product].fields.map((f) =>
              f.min === null ? (
                <label key={f.key} className="s-check">
                  <input
                    type="checkbox"
                    checked={!!sizes[f.key]}
                    onChange={(e) =>
                      setSizes({ ...sizes, [f.key]: e.target.checked })
                    }
                  />{" "}
                  {FIELD[f.key]?.[lang] ?? f.key}
                </label>
              ) : (
                <label key={f.key} className="s-range">
                  <span>
                    {FIELD[f.key]?.[lang] ?? f.key}
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
            )}
            <p className="s-muted">{W.colour[lang]}</p>
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
              {W.vents[lang]}
            </label>
            {quote && (
              <div className="s-price">
                <span>{W.total[lang]}</span>
                <strong>{euro(quote.price.total_eur)}</strong>
                <small>
                  {quote.pieces} {W.pieces[lang]} · {quote.cover_area_m2} m² ·{" "}
                  {quote.vents}× vent
                  {quote.price.support_eur
                    ? ` · ${W[quote.support][lang]} ${euro(quote.price.support_eur)}`
                    : ""}
                  {quote.price.indicative ? ` · ${W.indicative[lang]}` : ""}
                </small>
                <button
                  className="s-btn wide"
                  onClick={() => setStep("checkout")}
                >
                  {W.order[lang]} →
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
                body: JSON.stringify({ quote_id: quote.id, ...form }),
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
              ← {W.configure[lang]}
            </button>
            <h2>{W.order[lang]}</h2>
            {(
              ["name", "email", "phone", "street", "postcode", "city"] as const
            ).map((k) => (
              <input
                key={k}
                placeholder={W[k][lang]}
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
                  {s.name} {s.eur ? `(+ ${euro(s.eur)})` : ""}
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
                {W.terms[lang]} (
                <a href="/shop/terms" target="_blank">
                  {W.terms_page[lang]}
                </a>
                )
              </span>
            </label>
            <div className="s-price">
              <span>{W.total[lang]}</span>
              <strong>{euro(quote.price.total_eur)}</strong>
            </div>
            <button className="s-btn wide" disabled={!form.terms}>
              {info.settings.payment ? W.pay[lang] : W.place[lang]} →
            </button>
            {error && <p className="s-error">{error}</p>}
          </form>
        )}
        {done && (
          <div className="s-done">
            <h2>{lang === "nl" ? "Dank je wel!" : "Thank you!"}</h2>
            <p>
              {lang === "nl"
                ? "Je bestelling is ontvangen. Je krijgt een bevestiging per e-mail; de betaalgegevens volgen."
                : "We have your order. You get a confirmation by e-mail; the payment details follow."}
            </p>
            <a className="s-btn" href={done.status_url}>
              {W.status[lang]} →
            </a>
          </div>
        )}
      </aside>
    </section>
  );
}

function OrderStatus({ token, lang }: { token: string; lang: Lang }) {
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
        {W.status[lang]} #{o.order}
      </h1>
      <p className="s-muted">
        {PRODUCT[o.product]?.[lang]} · {o.colour} · {euro(o.total_eur)}
      </p>
      <ol className="s-track">
        {steps.map((s, i) => (
          <li key={s} className={i <= at ? "on" : ""}>
            {STATUS[s][lang]}
          </li>
        ))}
      </ol>
      {at < 0 && <p>{STATUS[o.status]?.[lang] ?? o.status}</p>}
    </section>
  );
}

function Legal({ info, lang, page }: { info: Info; lang: Lang; page: string }) {
  const text = info.content.legal[page]?.[lang] ?? "";
  return (
    <section className="s-section s-legal">
      <h1>{W[page === "terms" ? "terms_page" : page]?.[lang] ?? page}</h1>
      {text ? (
        text.split(/\n\n+/).map((p, i) => <p key={i}>{p}</p>)
      ) : (
        <p className="s-muted">{W.empty[lang]}</p>
      )}
    </section>
  );
}

function Footer({ info, lang }: { info: Info; lang: Lang }) {
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
        <a href="/shop/terms">{W.terms_page[lang]}</a>
        <a href="/shop/privacy">{W.privacy[lang]}</a>
        <a href="/shop/warranty">{W.warranty[lang]}</a>
      </nav>
    </footer>
  );
}

function App() {
  const [info, setInfo] = useState<Info | null>(null);
  const [lang, setLangState] = useState<Lang>(() => {
    try {
      const s = localStorage.getItem("lang");
      if (s === "nl" || s === "en") return s;
    } catch {
      /* no storage */
    }
    return navigator.language.startsWith("nl") ? "nl" : "en";
  });
  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("lang", l);
    } catch {
      /* no storage */
    }
  };
  useEffect(() => {
    const preview = new URLSearchParams(window.location.search).get("preview");
    fetch(
      `/api/shop/info${preview ? `?preview=${encodeURIComponent(preview)}` : ""}`,
    )
      .then((r) => r.json())
      .then(setInfo);
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
    if (info) document.title = info.content.meta.title[lang];
  }, [lang, info]);
  if (!info) return null;
  const path = window.location.pathname.replace(/\/+$/, "");
  const order = path.match(/^\/shop\/order\/([A-Za-z0-9_-]+)/);
  const legal = path.match(/^\/shop\/(terms|privacy|warranty)$/);
  return (
    <div className="s-app">
      {info.preview && (
        <div className="s-preview">
          PREVIEW: {lang === "nl" ? "nog niet live" : "not live yet"}
        </div>
      )}
      <Header lang={lang} setLang={setLang} info={info} />
      <main>
        {path === "/shop/configure" ? (
          <Configure info={info} lang={lang} />
        ) : order ? (
          <OrderStatus token={order[1]} lang={lang} />
        ) : legal ? (
          <Legal info={info} lang={lang} page={legal[1]} />
        ) : (
          <Home info={info} lang={lang} />
        )}
      </main>
      <Footer info={info} lang={lang} />
    </div>
  );
}

createRoot(document.getElementById("shop")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
