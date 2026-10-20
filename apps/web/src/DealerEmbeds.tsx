// Shop → Dealer embeds (ADR-150, docs/plans/dealer-embed.md): our configurator on a B2B dealer's
// own website. Per dealer site: its domains, its look (with a live preview of the real
// component), texts and languages, which kinds and fabrics, its prices (our B2B price plus a
// margin, or a price list), how its customers order, the snippet to copy, the secret key for the
// dealer's server and the counts per day. The purchase price shows only here, to us.
import { useCallback, useEffect, useRef, useState } from "react";
import { Heading, Icon, Info, StatusChip } from "./icons";

interface Theme {
  primary: string;
  accent: string;
  text: string;
  background: string;
  surface: string;
  border: string;
  radius_px: number;
  font: string;
  heading_font: string;
  logo_url: string;
}
interface Pricing {
  mode: "margin" | "list";
  margin_pct: number;
  kind_margin_pct: Record<string, number>;
  list: string;
  rounding: string;
  show_vat: boolean;
}
interface SiteSettings {
  theme: Theme;
  lang: string;
  languages: string[];
  texts: Record<string, Record<string, string>>;
  kinds: string[];
  colours: string[];
  layout: "full" | "compact";
  view3d: boolean;
  checkout: "ours" | "dealer";
  end_action: string;
  pricing: Pricing;
  return_url: string;
  shipping: string;
  dealer_confirms: boolean;
  deliver_to: string;
  customer_mail: boolean;
  notify_email: string;
}
interface Usage {
  day: string;
  load: number;
  quote: number;
  checkout: number;
  order: number;
  cart: number;
  paid?: number;
  paid_eur?: number;
}
interface Site {
  id: number;
  name: string;
  public_key: string;
  secret_shown: string | null;
  domains: string[];
  settings: SiteSettings;
  active: boolean;
  company_id: number;
  company: string | null;
  company_status: string | null;
  company_price_list: string | null;
  usage: Usage[];
  orders: {
    id: number;
    created: number;
    status: string;
    price_eur: number;
    purchase_eur: number;
    b2b_order: number | null;
    customer: string;
  }[];
}
interface Doc {
  enabled_on_live: boolean;
  sites: Site[];
  companies: { id: number; name: string; status: string; price_list: string }[];
  channels: Record<string, string>;
  products: Record<string, string>;
  colours: string[];
  languages: string[];
  roundings: string[];
  website: string;
  preview: string | null;
  made?: number;
}
interface Example {
  product: string;
  amount: number;
  vat_included: boolean;
  purchase_eur: number;
  net_eur: number;
}

async function call<R>(method: string, path: string, body?: unknown): Promise<R> {
  const r = await fetch(`/api/admin/embeds${path}`, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok)
    throw new Error(typeof d.detail === "string" ? d.detail : `${r.status} ${JSON.stringify(d.detail ?? "")}`);
  return d as R;
}

const eur = (n: number) => `€ ${n.toFixed(2)}`;
const COLOURS: [keyof Theme, string][] = [
  ["primary", "Buttons"],
  ["accent", "Accent"],
  ["text", "Text"],
  ["background", "Background"],
  ["surface", "Panels"],
  ["border", "Borders"],
];
const OWN_TEXTS: [string, string][] = [
  ["title", "Title"],
  ["intro", "Intro"],
  ["cta", "Button (order / send)"],
  ["thanks", "Thank-you text"],
];

export function DealerEmbeds() {
  const [doc, setDoc] = useState<Doc | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [company, setCompany] = useState<number | "">("");
  const [name, setName] = useState("");
  const load = useCallback(() => {
    call<Doc>("GET", "")
      .then(setDoc)
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);
  if (!doc) return <p className="muted">{error || "…"}</p>;
  const site = doc.sites.find((s) => s.id === open) || null;
  return (
    <>
      {error && <p className="error">{error}</p>}
      <section className="card">
        <div className="head-row">
          <Icon name="embed" />
          <span>
            {doc.enabled_on_live ? (
              <StatusChip status="approved">On for the live shop</StatusChip>
            ) : (
              <StatusChip status="warning">Preview only</StatusChip>
            )}{" "}
            {doc.preview && (
              <a href={`${doc.preview}/embed-demo`} target="_blank" rel="noreferrer">
                The demo with two dealer sites
              </a>
            )}
          </span>
          <Info label="About dealer embeds">
            <p>
              A dealer (a B2B customer) puts our configurator on its own website with one
              script tag, or a frame where its site builder refuses scripts. Its customers see
              the dealer's colours, fonts, logo and texts, and the dealer's prices: our B2B price
              plus the dealer's margin, or a price list. Our B2B price never reaches the page.
            </p>
            <p>
              Per site: our checkout in the dealer's look (we invoice the customer), or the
              order is sent to the dealer (the dealer confirms; it becomes a B2B order on
              account). The page answers only on the domains listed here. Off on the live shop
              until the owner's go (the shop setting dealer_embed_enabled); the preview website
              always has it.
            </p>
          </Info>
        </div>
        <form
          className="fields b2b-fields"
          onSubmit={async (e) => {
            e.preventDefault();
            if (company === "") return;
            setError("");
            try {
              const d = await call<Doc>("POST", "", { company_id: company, name: name.trim() });
              setDoc(d);
              setOpen(d.made ?? null);
              setName("");
            } catch (err) {
              setError(String(err));
            }
          }}
        >
          <label className="field">
            <span>Dealer (B2B customer)</span>
            <select
              required
              value={company}
              onChange={(e) => setCompany(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">—</option>
              {doc.companies.map((c) => (
                <option key={c.id} value={c.id} disabled={c.status !== "active"}>
                  {c.name}
                  {c.status !== "active" ? ` (${c.status})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Name of the site</span>
            <input required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <button className="primary">
            <Icon name="new" /> New dealer site
          </button>
        </form>
      </section>
      <section className="card">
        <h3>
          <Icon name="embed" /> Dealer sites
        </h3>
        <table className="list">
          <thead>
            <tr>
              <th>Site</th>
              <th>Domains</th>
              <th>Checkout</th>
              <th>Today</th>
            </tr>
          </thead>
          <tbody>
            {doc.sites.length === 0 && (
              <tr className="static">
                <td colSpan={4} className="muted">
                  No dealer sites yet: make the first one above.
                </td>
              </tr>
            )}
            {doc.sites.map((s) => {
              const today = s.usage.find((u) => u.day === new Date().toISOString().slice(0, 10));
              return (
                <tr key={s.id} onClick={() => setOpen(open === s.id ? null : s.id)}>
                  <td>
                    <strong>{s.name}</strong>{" "}
                    {!s.active && <StatusChip status="rejected">off</StatusChip>}
                    <br />
                    <span className="muted">{s.company}</span>
                  </td>
                  <td>{s.domains.join(", ") || <span className="muted">none yet</span>}</td>
                  <td>
                    {s.settings.checkout === "ours" ? "Our checkout" : "To the dealer"} ·{" "}
                    {s.settings.end_action}
                  </td>
                  <td>
                    {today
                      ? `${today.load} loads · ${today.quote} prices · ${today.order + today.checkout} orders`
                      : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
      {site && (
        <SiteEditor
          key={site.id}
          site={site}
          doc={doc}
          onSaved={(d) => {
            setDoc(d);
            setError("");
          }}
          onError={setError}
        />
      )}
    </>
  );
}

function SiteEditor({
  site,
  doc,
  onSaved,
  onError,
}: {
  site: Site;
  doc: Doc;
  onSaved: (d: Doc) => void;
  onError: (e: string) => void;
}) {
  const [s, setS] = useState<SiteSettings>(site.settings);
  const [domains, setDomains] = useState(site.domains.join("\n"));
  const [title, setTitle] = useState(site.name);
  const [active, setActive] = useState(site.active);
  const [textLang, setTextLang] = useState(site.settings.lang);
  const [secret, setSecret] = useState("");
  const [example, setExample] = useState<Example | null>(null);
  const [saved, setSaved] = useState("");
  const set = <K extends keyof SiteSettings>(k: K, v: SiteSettings[K]) => setS({ ...s, [k]: v });
  const theme = (k: keyof Theme, v: string | number) => set("theme", { ...s.theme, [k]: v });
  const pricing = (p: Partial<Pricing>) => set("pricing", { ...s.pricing, ...p });
  const toggle = (list: string[], v: string) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
  const buys = new Set(["b2b", site.company_price_list || "b2b"]);
  const refreshExample = useCallback(() => {
    call<Example>("GET", `/${site.id}/example?product=sofa`)
      .then(setExample)
      .catch(() => setExample(null));
  }, [site.id]);
  useEffect(refreshExample, [refreshExample]);
  const save = async () => {
    onError("");
    setSaved("");
    try {
      const d = await call<Doc>("PUT", `/${site.id}`, {
        name: title.trim(),
        active,
        domains: domains.split(/\s+/).filter(Boolean),
        settings: s,
      });
      onSaved(d);
      setSaved("Saved.");
      refreshExample();
    } catch (e) {
      onError(String(e));
    }
  };
  const base = doc.preview || doc.website;
  const script = `<script type="module" src="${base}/embed/v1/configurator.js"></script>\n<s2dio-configurator dealer="${site.public_key}" lang="${s.lang}"></s2dio-configurator>`;
  const frame = `<iframe src="${base}/embed/v1/frame?dealer=${site.public_key}&lang=${s.lang}" title="Cover configurator" style="width:100%;height:900px;border:0" loading="lazy" sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"></iframe>`;
  const ends =
    s.checkout === "ours"
      ? [["checkout", "Order and pay (our checkout)"]]
      : [
          ["send_order", "Send the order to the dealer"],
          ["cart", "Add to the dealer's own cart (event)"],
        ];
  return (
    <section className="card">
      <Heading icon="embed" infoLabel="About this dealer site" info="Everything here is the dealer's own: saved together with Save. The preview on the right shows the look as you type; its prices follow the saved settings.">
        {site.name} · {site.company}
      </Heading>
      <div className="embed-editor" style={{ display: "grid", gap: 24, gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)" }}>
        <div>
          <h4>Site</h4>
          <div className="fields">
            <label className="field">
              <span>Name</span>
              <input value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label className="field">
              <span>Domains (one per line, https://…)</span>
              <textarea rows={3} value={domains} onChange={(e) => setDomains(e.target.value)} />
            </label>
            <label className="check">
              <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />{" "}
              Active
            </label>
          </div>
          <h4>Look</h4>
          <div className="fields">
            {COLOURS.map(([k, label]) => (
              <label className="field" key={k}>
                <span>{label}</span>
                <input type="color" value={String(s.theme[k])} onChange={(e) => theme(k, e.target.value)} />
              </label>
            ))}
            <label className="field">
              <span>Corners (px)</span>
              <input type="number" min={0} max={40} value={s.theme.radius_px} onChange={(e) => theme("radius_px", Number(e.target.value))} />
            </label>
            <label className="field">
              <span>Font ("inherit": the dealer's page font)</span>
              <input value={s.theme.font} maxLength={120} onChange={(e) => theme("font", e.target.value)} />
            </label>
            <label className="field">
              <span>Heading font</span>
              <input value={s.theme.heading_font} maxLength={120} onChange={(e) => theme("heading_font", e.target.value)} />
            </label>
            <label className="field">
              <span>Logo (https address)</span>
              <input value={s.theme.logo_url} maxLength={500} onChange={(e) => theme("logo_url", e.target.value)} />
            </label>
            <label className="field">
              <span>Layout</span>
              <select value={s.layout} onChange={(e) => set("layout", e.target.value as "full" | "compact")}>
                <option value="full">Full (two columns on a wide page)</option>
                <option value="compact">Compact (one column, a list of kinds)</option>
              </select>
            </label>
            <label className="check">
              <input type="checkbox" checked={s.view3d} onChange={(e) => set("view3d", e.target.checked)} /> 3D view
            </label>
          </div>
          <h4>Languages and texts</h4>
          <div className="fields">
            <label className="field">
              <span>Default language</span>
              <select value={s.lang} onChange={(e) => set("lang", e.target.value)}>
                {doc.languages.map((l) => (
                  <option key={l}>{l}</option>
                ))}
              </select>
            </label>
            <div className="field">
              <span>Languages</span>
              {doc.languages.map((l) => (
                <label className="check" key={l}>
                  <input type="checkbox" checked={s.languages.includes(l)} onChange={() => set("languages", toggle(s.languages, l))} /> {l}
                </label>
              ))}
            </div>
            <label className="field">
              <span>Own texts in</span>
              <select value={textLang} onChange={(e) => setTextLang(e.target.value)}>
                {doc.languages.map((l) => (
                  <option key={l}>{l}</option>
                ))}
              </select>
            </label>
            {OWN_TEXTS.map(([k, label]) => (
              <label className="field" key={k}>
                <span>
                  {label} ({textLang}; empty: ours)
                </span>
                <input
                  value={s.texts[textLang]?.[k] || ""}
                  maxLength={k === "intro" ? 600 : k === "thanks" ? 400 : 120}
                  onChange={(e) =>
                    set("texts", { ...s.texts, [textLang]: { ...(s.texts[textLang] || {}), [k]: e.target.value } })
                  }
                />
              </label>
            ))}
          </div>
          <h4>Range (none ticked: all)</h4>
          <div className="fields">
            <div className="field">
              <span>Kinds</span>
              {Object.entries(doc.products).map(([k, label]) => (
                <label className="check" key={k}>
                  <input type="checkbox" checked={s.kinds.includes(k)} onChange={() => set("kinds", toggle(s.kinds, k))} /> {label}
                </label>
              ))}
            </div>
            <div className="field">
              <span>Fabric colours</span>
              {doc.colours.map((c) => (
                <label className="check" key={c}>
                  <input type="checkbox" checked={s.colours.includes(c)} onChange={() => set("colours", toggle(s.colours, c))} /> {c}
                </label>
              ))}
            </div>
          </div>
          <h4>Prices</h4>
          <div className="fields">
            <label className="field">
              <span>The customer's price</span>
              <select value={s.pricing.mode} onChange={(e) => pricing({ mode: e.target.value as "margin" | "list" })}>
                <option value="margin">Our B2B price + the dealer's margin</option>
                <option value="list">A price list</option>
              </select>
            </label>
            {s.pricing.mode === "margin" ? (
              <>
                <label className="field">
                  <span>Margin (%)</span>
                  <input type="number" min={0} max={500} step="0.5" value={s.pricing.margin_pct} onChange={(e) => pricing({ margin_pct: Number(e.target.value) })} />
                </label>
                {Object.entries(doc.products).map(([k, label]) => (
                  <label className="field" key={k}>
                    <span>{label}: own margin (%, empty: the above)</span>
                    <input
                      type="number"
                      min={0}
                      max={500}
                      value={s.pricing.kind_margin_pct[k] ?? ""}
                      onChange={(e) => {
                        const m = { ...s.pricing.kind_margin_pct };
                        if (e.target.value === "") delete m[k];
                        else m[k] = Number(e.target.value);
                        pricing({ kind_margin_pct: m });
                      }}
                    />
                  </label>
                ))}
              </>
            ) : (
              <label className="field">
                <span>Price list (Settings → Prices)</span>
                <select value={s.pricing.list} onChange={(e) => pricing({ list: e.target.value })}>
                  {Object.entries(doc.channels)
                    .filter(([k]) => !buys.has(k))
                    .map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                </select>
              </label>
            )}
            <label className="field">
              <span>Rounding up to</span>
              <select value={s.pricing.rounding} onChange={(e) => pricing({ rounding: e.target.value })}>
                {doc.roundings.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
            <label className="check">
              <input type="checkbox" checked={s.pricing.show_vat} onChange={(e) => pricing({ show_vat: e.target.checked })} /> Prices incl. VAT
            </label>
            {example && (
              <p className="muted">
                A sofa at the default sizes (saved settings): the dealer buys at {eur(example.purchase_eur)} ex
                VAT; its customer sees {eur(example.amount)} {example.vat_included ? "incl. VAT" : "ex VAT"}.
              </p>
            )}
          </div>
          <h4>Ordering</h4>
          <div className="fields">
            <label className="field">
              <span>Checkout</span>
              <select
                value={s.checkout}
                onChange={(e) => {
                  const c = e.target.value as "ours" | "dealer";
                  setS({ ...s, checkout: c, end_action: c === "ours" ? "checkout" : "send_order" });
                }}
              >
                <option value="dealer">The dealer sells and invoices (we make)</option>
                <option value="ours">Our checkout, in the dealer's look (we invoice)</option>
              </select>
            </label>
            <label className="field">
              <span>At the end</span>
              <select value={s.end_action} onChange={(e) => set("end_action", e.target.value)}>
                {ends.map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            {s.checkout === "ours" ? (
              <>
                <label className="field">
                  <span>Back to (after paying; on a listed domain)</span>
                  <input value={s.return_url} maxLength={500} onChange={(e) => set("return_url", e.target.value)} />
                </label>
                <label className="field">
                  <span>Delivery</span>
                  <select value={s.shipping} onChange={(e) => set("shipping", e.target.value)}>
                    <option value="customer">The customer pays our rate</option>
                    <option value="included">In the price</option>
                  </select>
                </label>
              </>
            ) : (
              <>
                <label className="check">
                  <input type="checkbox" checked={s.dealer_confirms} onChange={(e) => set("dealer_confirms", e.target.checked)} /> The
                  dealer confirms each order first
                </label>
                <label className="field">
                  <span>Deliver to</span>
                  <select value={s.deliver_to} onChange={(e) => set("deliver_to", e.target.value)}>
                    <option value="dealer">The dealer</option>
                    <option value="customer">The customer (drop shipping)</option>
                  </select>
                </label>
                <label className="check">
                  <input type="checkbox" checked={s.customer_mail} onChange={(e) => set("customer_mail", e.target.checked)} /> Mail
                  the customer "sent to the dealer"
                </label>
                <label className="field">
                  <span>The dealer's orders to (empty: the company's e-mail)</span>
                  <input type="email" value={s.notify_email} onChange={(e) => set("notify_email", e.target.value)} />
                </label>
              </>
            )}
          </div>
          <p>
            <button className="primary" onClick={save}>
              <Icon name="save" /> Save
            </button>{" "}
            <span className="muted">{saved}</span>
          </p>
        </div>
        <div>
          <h4>Live preview</h4>
          <LivePreview dealer={site.public_key} draft={s} />
        </div>
      </div>
      <h4>Snippet</h4>
      <Snippet label="Script (recommended)" code={script} />
      <Snippet label="Frame (site builders without scripts: Wix, Squarespace)" code={frame} />
      <p className="muted">
        Public key <code>{site.public_key}</code> (in the page; opens nothing secret). Secret key for
        the dealer's server (reads a price back: GET /api/embed/v1/verify/&lt;quote&gt;):{" "}
        {site.secret_shown || "none yet"}{" "}
        <button
          onClick={async () => {
            if (site.secret_shown && !window.confirm("Make a new secret key? The old one stops working."))
              return;
            try {
              setSecret((await call<{ secret: string }>("POST", `/${site.id}/secret`)).secret);
            } catch (e) {
              onError(String(e));
            }
          }}
        >
          <Icon name="keys" /> {site.secret_shown ? "New secret key" : "Make a secret key"}
        </button>
      </p>
      {secret && (
        <p className="error">
          Shown once: <code>{secret}</code>
        </p>
      )}
      <h4>The last 30 days</h4>
      <table className="list">
        <thead>
          <tr>
            <th>Day</th>
            <th>Loads</th>
            <th>Prices</th>
            <th>Checkouts</th>
            <th>Sent to dealer</th>
            <th>Carts</th>
            <th>Paid</th>
          </tr>
        </thead>
        <tbody>
          {site.usage.length === 0 && (
            <tr className="static">
              <td colSpan={7} className="muted">
                Nothing yet.
              </td>
            </tr>
          )}
          {site.usage.map((u) => (
            <tr key={u.day} className="static">
              <td>{u.day}</td>
              <td>{u.load}</td>
              <td>{u.quote}</td>
              <td>{u.checkout}</td>
              <td>{u.order}</td>
              <td>{u.cart}</td>
              <td>{u.paid ? `${u.paid} · ${eur(u.paid_eur || 0)}` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {site.orders.length > 0 && (
        <>
          <h4>Sent to the dealer</h4>
          <table className="list">
            <tbody>
              {site.orders.map((o) => (
                <tr key={o.id} className="static">
                  <td>D{o.id}</td>
                  <td>{new Date(o.created * 1000).toLocaleString()}</td>
                  <td>{o.customer}</td>
                  <td>
                    <StatusChip status={o.status === "confirmed" ? "approved" : o.status === "declined" ? "rejected" : "waiting"}>
                      {o.status}
                    </StatusChip>
                  </td>
                  <td>
                    {eur(o.price_eur)} (buys at {eur(o.purchase_eur)})
                    {o.b2b_order ? ` · B2B order ${o.b2b_order}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

function Snippet({ label, code }: { label: string; code: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="field">
      <span>
        {label}{" "}
        <button
          onClick={() => {
            void navigator.clipboard?.writeText(code).then(() => {
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            });
          }}
        >
          <Icon name="copy" /> {copied ? "Copied" : "Copy"}
        </button>
      </span>
      <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
        <code>{code}</code>
      </pre>
    </div>
  );
}

/** The real component, from this server's build, with the editor's draft look over it. */
function LivePreview({ dealer, draft }: { dealer: string; draft: SiteSettings }) {
  const host = useRef<HTMLDivElement>(null);
  const el = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!document.querySelector("script[data-s2dio-embed]")) {
      const s = document.createElement("script");
      s.type = "module";
      s.src = "/embed/v1/configurator.js";
      s.dataset.s2dioEmbed = "1";
      document.head.append(s);
    }
    const e = document.createElement("s2dio-configurator");
    e.setAttribute("dealer", dealer);
    el.current = e;
    host.current?.replaceChildren(e);
    return () => {
      e.remove();
      el.current = null;
    };
  }, [dealer]);
  useEffect(() => {
    const e = el.current as (HTMLElement & { preview?: unknown }) | null;
    if (e)
      e.preview = { theme: draft.theme, texts: draft.texts, layout: draft.layout, view3d: draft.view3d };
  }, [draft]);
  return <div ref={host} style={{ border: "1px dashed var(--line-strong)", borderRadius: 12, padding: 8 }} />;
}
