// Settings (ADR-122, docs/plans/studio-ui.md §6): one place for everything that is set once,
// on tabs in five groups (ADR-126: Prices & costs moved in, merged tabs: Selling, Rules & defaults,
// System & logs). Every setting is one row: a plain name (the stored key small and grey),
// the right control, one line of explanation, its default and whether it was changed. The shop's
// settings are the same stored keys as before (GET/PUT /api/admin/shop/settings): no data moved.
// The company defaults from config/defaults.yaml are shown read-only (the developer changes them;
// which ones the owner wants to change himself is open question 5).
import { useCallback, useEffect, useMemo, useState } from "react";
import { admin, api, ParamSpec, Scalar, shopAdmin } from "./api";
import {
  AgentKeys,
  Audit,
  EmbedAndKeys,
  Mail,
  Sessions,
  System,
  Users,
} from "./Admin";
import { Heading, Icon, Info } from "./icons";
import { SETTINGS_TABS, visibleSettings } from "./nav";
import { MailOutbox } from "./MailOutbox";
import { PhotoTest } from "./PhotoTest";
import { Prices } from "./Prices";
import { useSession } from "./Session";
import { useUnsaved } from "./unsaved";

type Doc = Record<string, unknown>;
interface ShopState {
  settings: Doc;
  defaults: Doc;
  missing: string[];
  link_key_set?: boolean;
}

const get = (doc: unknown, path: string): unknown =>
  path
    .split(".")
    .reduce<unknown>(
      (cur, k) =>
        cur == null
          ? undefined
          : Array.isArray(cur)
            ? cur[Number(k)]
            : (cur as Doc)[k],
      doc,
    );
function put(doc: Doc, path: string, value: unknown): Doc {
  const copy = structuredClone(doc);
  const keys = path.split(".");
  let cur: Doc = copy;
  for (const k of keys.slice(0, -1)) {
    if (cur[k] == null || typeof cur[k] !== "object") cur[k] = {};
    cur = cur[k] as Doc;
  }
  cur[keys[keys.length - 1]] = value;
  return copy;
}
const shown = (v: unknown) =>
  v === null || v === undefined || v === ""
    ? "empty"
    : typeof v === "boolean"
      ? v
        ? "on"
        : "off"
      : String(v);
const same = (a: unknown, b: unknown) =>
  JSON.stringify(a ?? null) === JSON.stringify(b ?? null) ||
  ((a === "" || a == null) && (b === "" || b == null));

/** One setting in the shop's stored JSON: how it is shown and explained. */
interface Field {
  key: string; // the dotted path in the shop settings
  label: string;
  help: string;
  kind?: "text" | "email" | "number" | "bool" | "choice" | "url" | "secret";
  unit?: string;
  choices?: [string, string][];
  /** the company default that applies while the field is empty (a key in defaults.yaml) */
  fallback?: string;
  placeholder?: string;
}
interface Group {
  title: string;
  intro?: string;
  fields: Field[];
  advanced?: boolean;
}

// ---- the shop's settings, in plain words ----------------------------------------------------
const COMPANY: Group[] = [
  {
    title: "The company",
    intro:
      "On the invoices, the order mails, the legal pages and the shop's footer. What is empty shows as a placeholder in the shop.",
    fields: [
      {
        key: "company.name",
        label: "Trade name",
        help: "The name customers see.",
      },
      {
        key: "company.legal_name",
        label: "Legal name",
        help: "As registered; on invoices and the terms.",
      },
      {
        key: "company.kvk",
        label: "Chamber of Commerce number",
        help: "KvK number, on invoices and the legal pages.",
      },
      { key: "company.vat_number", label: "VAT number", help: "On invoices." },
      { key: "company.street", label: "Street and number", help: "" },
      { key: "company.postcode", label: "Postcode", help: "" },
      { key: "company.city", label: "City", help: "" },
      {
        key: "company.country",
        label: "Country",
        help: "Two-letter code, e.g. NL.",
      },
      {
        key: "company.email",
        label: "Customer service e-mail",
        help: "Shown to customers; replies to order mails go here.",
        kind: "email",
      },
      { key: "company.phone", label: "Phone", help: "Shown to customers." },
      {
        key: "company.iban",
        label: "IBAN",
        help: "For payment by bank transfer.",
      },
    ],
  },
  {
    title: "The shop",
    intro: "What the shop offers and how it looks.",
    fields: [
      {
        key: "domain",
        label: "The website's domain",
        help: "e.g. suns-covers.com; used in links, the sitemap and the preview site.",
      },
      {
        key: "languages",
        label: "Languages",
        help: "Language codes, comma separated; the first is the default.",
        placeholder: "nl,en,de,fr",
      },
      {
        key: "colours",
        label: "Colours offered",
        help: "Comma separated. Empty: the colours of the published price set's fabric (Prices).",
      },
      {
        key: "bbq_enabled",
        label: "Barbecue covers",
        help: "The barbecue option in the configurator, its quotes, matching and B2B; the preview site always has it (ADR-119).",
        kind: "bool",
      },
      {
        key: "logo_url",
        label: "Logo",
        help: "Address of the logo picture; empty: the built-in logo.",
        kind: "url",
      },
      {
        key: "og_image",
        label: "Share picture",
        help: "The picture when the shop is shared (1200 × 630); empty: /brand/og-shop.png.",
        kind: "url",
      },
      {
        key: "stock_delivery_note.nl",
        label: "Delivery promise, Dutch",
        help: "For an existing cover ordered directly (ADR-118); empty: not shown. Never for a made-to-measure cover.",
      },
      {
        key: "stock_delivery_note.en",
        label: "Delivery promise, English",
        help: "",
      },
      {
        key: "stock_delivery_note.de",
        label: "Delivery promise, German",
        help: "",
      },
      {
        key: "stock_delivery_note.fr",
        label: "Delivery promise, French",
        help: "",
      },
    ],
  },
  {
    title: "Support products",
    intro:
      "The balloon and the frame under a table cover, as the shop names and shows them.",
    fields: [
      { key: "products.balloon.name", label: "Balloon: name", help: "" },
      { key: "products.balloon.size", label: "Balloon: size", help: "" },
      {
        key: "products.balloon.photo",
        label: "Balloon: photo",
        help: "Address of a photo.",
        kind: "url",
      },
      { key: "products.frame.name", label: "Frame: name", help: "" },
      { key: "products.frame.size", label: "Frame: size", help: "" },
      {
        key: "products.frame.photo",
        label: "Frame: photo",
        help: "Address of a photo.",
        kind: "url",
      },
    ],
  },
  {
    title: "Home page film and story",
    advanced: true,
    intro:
      "Set once by the developer when a new film or story is made (ADR-067, ADR-108).",
    fields: [
      {
        key: "film_url",
        label: "Film (H.264)",
        help: "/media/<file>.mp4",
        kind: "url",
      },
      {
        key: "film_av1",
        label: "Film (AV1)",
        help: "The same film in AV1, played where the browser can.",
        kind: "url",
      },
      { key: "film_poster", label: "Film poster", help: "", kind: "url" },
      {
        key: "story_model",
        label: "Story model",
        help: "The catalogue model the scroll story shows.",
      },
      ...["hero", "rain", "measure", "cut", "sew", "pack"].map((k): Field => ({
        key: `story_media.${k}`,
        label: `Story picture: ${k}`,
        help: "",
        kind: "url",
      })),
    ],
  },
];

const PAYMENT: Group = {
  title: "Payment",
  intro:
    "Payments work as soon as a Mollie key is filled in: test_… for testing, live_… for real.",
  fields: [
    {
      key: "payment.mollie_key",
      label: "Mollie key",
      help: "Never shown in full; Replace to give a new key (test_… or live_…).",
      kind: "secret",
    },
    {
      key: "payment.bank_transfer",
      label: "Bank transfer",
      help: "Customers may also pay by bank transfer (to the IBAN above).",
      kind: "bool",
    },
  ],
};

const MATCHING: Group[] = [
  {
    title: "Matching a request to an existing cover",
    intro:
      "A customer's sizes against the covers we already make (ADR-064). Empty fields use the company default from config/defaults.yaml, shown beside them.",
    fields: [
      {
        key: "matching.mode",
        label: "Mode",
        help: "Learning: a colleague confirms every proposal first (Shop → Requests). Automatic: above the threshold the customer gets the existing cover directly.",
        kind: "choice",
        choices: [
          ["shadow", "Learning (a colleague confirms)"],
          ["auto", "Automatic"],
        ],
        fallback: "match.mode",
      },
      {
        key: "matching.threshold_pct",
        label: "Offer the existing cover from",
        help: "From this match on we offer the existing cover.",
        kind: "number",
        unit: "%",
        fallback: "match.threshold_pct",
      },
      {
        key: "matching.choice_pct",
        label: "Let the customer choose from",
        help: "From this match on the customer chooses: existing or made to measure; below it, made to measure.",
        kind: "number",
        unit: "%",
        fallback: "match.choice_pct",
      },
      {
        key: "matching.stock_discount_pct",
        label: "Discount on an existing cover",
        help: "Off the made-to-measure price when the customer takes an existing cover; empty: none.",
        kind: "number",
        unit: "%",
      },
    ],
  },
];

const MAIL_SHOP: Field[] = [
  {
    key: "notify_email",
    label: "New orders and shop messages",
    help: "Every new order, a paid order, a customer's fit answer. Empty: rick@s2dio.industries.",
    kind: "email",
  },
  {
    key: "fit_mail.enabled",
    label: "Ask customers whether the cover fits",
    help: "A mail to the customer some days after delivery; the answers come in at Shop → Requests.",
    kind: "bool",
  },
  {
    key: "fit_mail.days",
    label: "… this many days after delivery",
    help: "",
    kind: "number",
    unit: "days",
  },
];

const WEBSITE: Field[] = [
  {
    key: "website_link.closed",
    label: "The shop here only for the website",
    help: "On: the shop on this server answers only the website (its key) and logged-in colleagues; visitors are sent to the website (ADR-066).",
    kind: "bool",
  },
  {
    key: "home_story",
    label: "Scroll story as the home page",
    help: "On: live; the preview site always shows it.",
    kind: "bool",
  },
  {
    key: "agent_api_enabled",
    label: "API for AI agents",
    help: "On: /api/v2, llms-full.txt, the measuring guide and the cover pages on the live website (also set AGENT_API in the Worker). The preview site always has them (ADR-135).",
    kind: "bool",
  },
  {
    key: "custom_lead_time.nl",
    label: "Made-to-measure lead time, Dutch",
    help: 'What the agent API says about a made-to-measure cover\'s lead time; empty: "confirmed after the order" (ADR-135).',
  },
  {
    key: "custom_lead_time.en",
    label: "Made-to-measure lead time, English",
    help: "",
  },
  {
    key: "custom_lead_time.de",
    label: "Made-to-measure lead time, German",
    help: "",
  },
  {
    key: "custom_lead_time.fr",
    label: "Made-to-measure lead time, French",
    help: "",
  },
];

// ---- building blocks ------------------------------------------------------------------------

function useParams() {
  const [specs, setSpecs] = useState<ParamSpec[] | null>(null);
  useEffect(() => {
    api
      .specs()
      .then(setSpecs)
      .catch(() => setSpecs([]));
  }, []);
  return specs;
}

function useShop() {
  const [state, setState] = useState<ShopState | null>(null);
  const [msg, setMsg] = useState("");
  const load = useCallback(() => {
    shopAdmin
      .settings()
      .then((r) => setState(r as unknown as ShopState))
      .catch((e) => setMsg(String(e)));
  }, []);
  useEffect(load, [load]);
  return { state, setState, msg, setMsg, load };
}

/** A row: the name and key, the control, the explanation and where the value comes from. */
export function Row({
  label,
  keyName,
  help,
  chip,
  children,
}: {
  label: string;
  keyName?: string;
  help?: string;
  chip?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="set-row">
      <div className="set-name" title={keyName}>
        {label}
        {help && <Info label={`About ${label}`}>{help}</Info>}
      </div>
      <div className="set-value">{children}</div>
      <div className="set-help">{chip}</div>
    </div>
  );
}

function Source({
  value,
  dflt,
  fallback,
}: {
  value: unknown;
  dflt: unknown;
  fallback?: Scalar;
}) {
  const empty = value === null || value === undefined || value === "";
  if (empty && fallback !== undefined)
    return (
      <span className="src">uses the company default: {shown(fallback)}</span>
    );
  if (same(value, dflt))
    return (
      <span className={`src ${empty ? "warn" : ""}`}>
        {empty ? "empty" : `default: ${shown(dflt)}`}
      </span>
    );
  return (
    <span className="src changed" title="Different from the shop's default">
      changed · default {shown(dflt)}
    </span>
  );
}

function Control({
  f,
  value,
  saved,
  onChange,
}: {
  f: Field;
  value: unknown;
  saved?: unknown; // the stored value (a secret shows it shortened)
  onChange: (v: unknown) => void;
}) {
  const kind = f.kind ?? "text";
  if (kind === "bool")
    return (
      <label className="switch">
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>{value ? "on" : "off"}</span>
      </label>
    );
  if (kind === "choice")
    return (
      <select
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      >
        {f.fallback && <option value="">company default</option>}
        {f.choices?.map(([k, l]) => (
          <option key={k} value={k}>
            {l}
          </option>
        ))}
      </select>
    );
  if (kind === "number")
    return (
      <span className="with-unit">
        <input
          type="number"
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(e) =>
            onChange(e.target.value === "" ? null : Number(e.target.value))
          }
        />
        {f.unit && <span className="muted">{f.unit}</span>}
      </span>
    );
  if (kind === "secret")
    return <Secret value={value} saved={saved} onChange={onChange} />;
  return (
    <input
      type={kind === "email" ? "email" : "text"}
      value={value === null || value === undefined ? "" : String(value)}
      placeholder={f.placeholder ?? ""}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

/** A stored secret: shown shortened as the server sends it; Replace gives an empty field. */
function Secret({
  value,
  saved,
  onChange,
}: {
  value: unknown;
  saved: unknown; // the stored key, shortened by the server, as last loaded or saved
  onChange: (v: unknown) => void;
}) {
  const stored = String(saved ?? "");
  const now = String(value ?? "");
  const [editing, setEditing] = useState(false);
  // after a save the form reloads: a new stored value ends the replacing
  useEffect(() => setEditing(false), [stored]);
  if (!editing)
    return (
      <span className="secret">
        <code>
          {now === "" && stored
            ? "removed (Save to confirm)"
            : stored || "not set"}
        </code>
        <button type="button" className="sm" onClick={() => setEditing(true)}>
          {stored ? "Replace" : "Set"}
        </button>
        {stored && now !== "" && (
          <button type="button" className="sm" onClick={() => onChange("")}>
            Remove
          </button>
        )}
        {stored && now === "" && (
          <button type="button" className="sm" onClick={() => onChange(stored)}>
            Keep it
          </button>
        )}
      </span>
    );
  return (
    <span className="secret">
      <input
        type="password"
        autoComplete="off"
        value={now === stored ? "" : now}
        placeholder="test_… or live_…"
        onChange={(e) => onChange(e.target.value || stored)}
      />
      <button
        type="button"
        className="sm"
        onClick={() => {
          setEditing(false);
          onChange(stored);
        }}
        title="Keep the stored one"
        aria-label="Keep the stored one"
      >
        <Icon name="undo" size={15} /> Keep stored
      </button>
    </span>
  );
}

/** A form over some of the shop's stored settings: one Save for the whole tab. */
function ShopForm({
  groups,
  intro,
  owns,
  specs,
}: {
  groups: Group[];
  intro?: React.ReactNode;
  owns: string[]; // the top-level keys this form saves (only those are sent)
  specs: ParamSpec[] | null;
}) {
  const { state, setState, msg, setMsg } = useShop();
  const [draft, setDraft] = useState<Doc | null>(null);
  const [onlyChanged, setOnlyChanged] = useState(false);
  useEffect(() => {
    if (state) setDraft(state.settings);
  }, [state]);
  const dirty =
    !!state && !!draft && owns.some((k) => !same(draft[k], state.settings[k]));
  useUnsaved(`shop:${owns.join(",")}`, dirty);
  if (!state || !draft) return <p className="muted">{msg || "Loading…"}</p>;
  const fallback = (key?: string) =>
    key ? specs?.find((s) => s.key === key)?.default : undefined;
  const save = async () => {
    setMsg("");
    try {
      const body = Object.fromEntries(owns.map((k) => [k, draft[k]]));
      const r = await shopAdmin.saveSettings(body);
      setState(r as unknown as ShopState);
      setMsg("Saved.");
    } catch (e) {
      setMsg(String(e));
    }
  };
  const rows = (g: Group) =>
    g.fields
      .filter(
        (f) =>
          !onlyChanged || !same(get(draft, f.key), get(state.defaults, f.key)),
      )
      .map((f) => (
        <Row
          key={f.key}
          label={f.label}
          keyName={f.key}
          help={f.help}
          chip={
            <Source
              value={get(draft, f.key)}
              dflt={get(state.defaults, f.key)}
              fallback={fallback(f.fallback)}
            />
          }
        >
          <Control
            f={f}
            value={get(draft, f.key)}
            saved={get(state.settings, f.key)}
            onChange={(v) => setDraft(put(draft, f.key, v))}
          />
        </Row>
      ));
  return (
    <form
      className="set-form"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      {intro}
      <label className="check set-filter">
        <input
          type="checkbox"
          checked={onlyChanged}
          onChange={(e) => setOnlyChanged(e.target.checked)}
        />{" "}
        Only changed values
      </label>
      {groups.map((g) =>
        g.advanced ? (
          <details key={g.title} className="set-group">
            <summary>
              {g.title} <span className="muted">(advanced)</span>
            </summary>
            {g.intro && (
              <p className="set-group-info">
                <Info label={`About ${g.title}`}>{g.intro}</Info>
              </p>
            )}
            {rows(g)}
          </details>
        ) : (
          <section key={g.title} className="set-group">
            <Heading info={g.intro}>{g.title}</Heading>
            {rows(g)}
          </section>
        ),
      )}
      <div className="set-save">
        <button className="primary" disabled={!dirty}>
          Save
        </button>
        <button
          type="button"
          disabled={!dirty}
          onClick={() => setDraft(state.settings)}
        >
          Undo changes
        </button>
        {dirty && <span className="src changed">unsaved changes</span>}
        {msg && <span className="muted">{msg}</span>}
      </div>
    </form>
  );
}

/** The company defaults of some groups, read-only, with their comments from defaults.yaml. */
function Defaults({
  specs,
  groups,
  intro,
  filter = true,
}: {
  specs: ParamSpec[] | null;
  groups: string[];
  intro?: React.ReactNode;
  filter?: boolean;
}) {
  const [q, setQ] = useState("");
  const rows = useMemo(
    () =>
      (specs ?? []).filter(
        (s) =>
          groups.includes(s.group) &&
          (!q ||
            `${s.key} ${s.comment}`.toLowerCase().includes(q.toLowerCase())),
      ),
    [specs, groups, q],
  );
  if (!specs) return <p className="muted">Loading…</p>;
  return (
    <section className="set-group">
      {intro}
      {filter && (
        <input
          className="set-search"
          placeholder="Search a setting…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      )}
      {rows.map((s) => (
        <Row
          key={s.key}
          label={s.key.split(".").slice(1).join(".").replace(/_/g, " ")}
          keyName={s.key}
          help={s.comment}
          chip={
            <>
              {s.to_confirm && <span className="src warn">to confirm</span>}
              <span
                className="src"
                title="Changed by the developer in config/defaults.yaml"
              >
                🔒 developer
              </span>
            </>
          }
        >
          <span className="ro">{shown(s.default)}</span>
        </Row>
      ))}
      {!rows.length && <p className="muted">Nothing found.</p>}
    </section>
  );
}

// ---- the tabs that are not a plain form ------------------------------------------------------

interface B2BSettings {
  online_payment: boolean;
  min_order_eur: number;
  shipping_eur: number;
  payment_days: number;
}
const B2B_DEFAULTS: B2BSettings = {
  online_payment: false,
  min_order_eur: 0,
  shipping_eur: 0,
  payment_days: 14,
};

/** The B2B terms (was a card on Admin → B2B customers): same API, PUT /api/admin/b2b/settings. */
function B2BTerms() {
  const [saved, setSaved] = useState<B2BSettings | null>(null);
  const [f, setF] = useState<B2BSettings | null>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    fetch("/api/admin/b2b/companies")
      .then((r) => r.json())
      .then((d) => {
        setSaved(d.settings);
        setF(d.settings);
      })
      .catch((e) => setMsg(String(e)));
  }, []);
  useUnsaved("b2b-terms", !!f && JSON.stringify(f) !== JSON.stringify(saved));
  if (!f || !saved) return <p className="muted">{msg || "Loading…"}</p>;
  const num = (
    k: keyof B2BSettings,
    label: string,
    help: string,
    unit: string,
  ) => (
    <Row
      label={label}
      keyName={`b2b.${k}`}
      help={help}
      chip={<Source value={f[k]} dflt={B2B_DEFAULTS[k]} />}
    >
      <span className="with-unit">
        <input
          type="number"
          min={0}
          value={Number(f[k])}
          onChange={(e) => setF({ ...f, [k]: Number(e.target.value) })}
        />
        <span className="muted">{unit}</span>
      </span>
    </Row>
  );
  const dirty = JSON.stringify(f) !== JSON.stringify(saved);
  return (
    <form
      className="set-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setMsg("");
        try {
          const r = await fetch("/api/admin/b2b/settings", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(f),
          });
          const d = await r.json();
          if (!r.ok) throw new Error(d.detail ?? r.statusText);
          setSaved(d.settings);
          setF(d.settings);
          setMsg("Saved.");
        } catch (err) {
          setMsg(String(err));
        }
      }}
    >
      <section className="set-group">
        {num("min_order_eur", "Minimum order", "Ex VAT; 0: no minimum.", "€")}
        {num(
          "shipping_eur",
          "Shipping per order",
          "On top, ex VAT; 0: in the price list's extras.",
          "€",
        )}
        {num(
          "payment_days",
          "Payment term",
          "Days to pay the invoice of an order on account.",
          "days",
        )}
        <Row
          label="Into production"
          keyName="b2b.production"
          help="An order on account waits for production, like a paid consumer order, until someone in the studio presses Send to production (Shop → Orders or Work → Workshop; owner, question 86, ADR-128)."
        >
          <span className="ro">by Send to production</span>
        </Row>
        <Row
          label="Online payment"
          keyName="b2b.online_payment"
          help="Later; every business order is on account now."
        >
          <label className="switch">
            <input
              type="checkbox"
              checked={f.online_payment}
              disabled
              readOnly
            />
            <span>{f.online_payment ? "on" : "off"}</span>
          </label>
        </Row>
      </section>
      <div className="set-save">
        <button className="primary" disabled={!dirty}>
          Save
        </button>
        <button type="button" disabled={!dirty} onClick={() => setF(saved)}>
          Undo changes
        </button>
        {msg && <span className="muted">{msg}</span>}
      </div>
    </form>
  );
}

/** Who gets which mail, in one list; the addresses stay where the server reads them. */
function Recipients({ specs }: { specs: ParamSpec[] | null }) {
  const [alert, setAlert] = useState<string | null>(null);
  const [request, setRequest] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    admin
      .system()
      .then((s) => setAlert(String(s.alert_email ?? "")))
      .catch((e) => setMsg(String(e)));
    admin
      .webshop()
      .then((w) => setRequest(w.request_email))
      .catch((e) => setMsg(String(e)));
  }, []);
  const p = (k: string) => specs?.find((s) => s.key === k)?.default;
  const saveOne = async (what: () => Promise<unknown>) => {
    setMsg("");
    try {
      await what();
      setMsg("Saved.");
    } catch (e) {
      setMsg(String(e));
    }
  };
  return (
    <section className="set-group">
      <Heading
        icon="mail"
        info="Every mail the studio and the shop send to us, in one list. Customers and business customers get their own mails; those are written in the website's text (Shop → Website)."
      >
        Who gets which mail
      </Heading>
      <Row
        label="Configurator requests"
        keyName="request_email"
        help="A quote asked in the configurator (Shop → Requests)."
      >
        <span className="inline-save">
          <input
            type="email"
            value={request ?? ""}
            onChange={(e) => setRequest(e.target.value)}
          />
          <button
            type="button"
            disabled={request === null}
            onClick={() =>
              saveOne(() => admin.setWebshop({ request_email: request ?? "" }))
            }
          >
            Save
          </button>
        </span>
      </Row>
      <Row
        label="Server alerts, B2B requests and orders"
        keyName="alert_email"
        help="The server's self-check every 10 minutes (when something is wrong, and when it is solved); a company asking for a B2B account; a B2B order."
      >
        <span className="inline-save">
          <input
            type="email"
            value={alert ?? ""}
            onChange={(e) => setAlert(e.target.value)}
          />
          <button
            type="button"
            disabled={alert === null}
            onClick={() => saveOne(() => admin.alertEmail(alert ?? ""))}
          >
            Save
          </button>
        </span>
      </Row>
      <Row
        label="Approval requests"
        keyName="users.may_approve"
        help="“Send to the Desk for approval” on a cover puts it on the Desk and mails the Desk's approvers (may approve, desk.approvers, admins) who have an e-mail address, with a link to its Desk card."
      >
        <span className="ro">the approvers</span>
      </Row>
      <Row
        label="New questions"
        keyName="questions.digest_hours"
        help="Mailed to whoever may answer, at most one digest per this many hours (0: no mails)."
        chip={<span className="src">🔒 developer</span>}
      >
        <span className="ro">every {shown(p("questions.digest_hours"))} h</span>
      </Row>
      <Row
        label="New answers"
        keyName="questions.answer_digest_hours"
        help="Mailed to the owners (questions.owners), at most one digest per this many hours."
        chip={<span className="src">🔒 developer</span>}
      >
        <span className="ro">
          every {shown(p("questions.answer_digest_hours"))} h
        </span>
      </Row>
      <Row
        label="AI spending warnings"
        keyName="spend.warn_pct"
        help="The watchdog mails the alert address at these shares of the month's budget, and on a costly hour."
        chip={<span className="src">🔒 developer</span>}
      >
        <span className="ro">at {shown(p("spend.warn_pct"))} %</span>
      </Row>
      {msg && <p className="muted">{msg}</p>}
    </section>
  );
}

interface Spend {
  month_eur: number;
  budget_eur: number;
  pct: number;
  calls: number;
}

function AiSpending({ specs }: { specs: ParamSpec[] | null }) {
  const [spend, setSpend] = useState<Spend | null>(null);
  useEffect(() => {
    fetch("/api/desk")
      .then((r) => r.json())
      .then((d) => setSpend(d.spend ?? null))
      .catch(() => setSpend(null));
  }, []);
  return (
    <>
      {spend && (
        <section className="set-group">
          <h3>This month</h3>
          <div className="spend">
            <b>€ {spend.month_eur.toFixed(2)}</b> of € {spend.budget_eur} (
            {spend.pct.toFixed(0)} %), {spend.calls} calls
            <span className="spend-bar">
              <i style={{ width: `${Math.min(spend.pct, 100)}%` }} />
            </span>
          </div>
        </section>
      )}
      <Defaults specs={specs} groups={["spend"]} filter={false} />
      <details className="set-group">
        <summary>Which AI does what (providers and models)</summary>
        <Defaults specs={specs} groups={["ai"]} filter={false} />
      </details>
      <details className="set-group">
        <summary>Photo suggestions in the configurator: limits</summary>
        <Defaults specs={specs} groups={["suggest"]} filter={false} />
      </details>
    </>
  );
}

function WebsiteKey({ linkKeySet }: { linkKeySet?: boolean }) {
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState("");
  return (
    <section className="set-group">
      <Heading
        icon="keys"
        info={
          <>
            The website on its own domain (Cloudflare) reaches this studio with
            a key (ADR-066). A new key is shown once and stops the old one: put
            it in the Worker with <code>npx wrangler secret put LINK_KEY</code>.
          </>
        }
      >
        The website's key
      </Heading>
      {linkKeySet === false && <p className="muted">No key is set yet.</p>}
      {key && (
        <p>
          <code>{key}</code>
        </p>
      )}
      <button
        type="button"
        onClick={async () => {
          try {
            setKey((await shopAdmin.linkKey()).key);
          } catch (e) {
            setMsg(String(e));
          }
        }}
        title="New website key: the old one stops working"
        aria-label="New website key"
      >
        <Icon name="refresh" /> New key
      </button>
      {msg && <p className="muted">{msg}</p>}
    </section>
  );
}

// ---- the area -------------------------------------------------------------------------------

const TAB_INTRO: Record<string, string> = {
  company:
    "The company's details and what the shop offers. Saved for the shop at once.",
  selling:
    "How we sell existing covers and to business customers: matching, the direct-order discount, the B2B terms.",
  users:
    "Who may log in, with which role (the workshop has its own), and who approves at the Desk.",
  defaults: "",
  mail: "The mail server, the login code and every address that receives mail.",
  website: "How the website and webshops reach the studio.",
  ai: "What the AI costs and the limits that guard it (ADR-078). The values are company defaults in config/defaults.yaml, read-only here: the developer changes them (which ones you want to change yourself is an open question).",
  system:
    "The server's state, the releases, the last alerts; who is logged in and every login, change and approval. Read-only.",
};
const PRICE_TABS = ["costs", "pricing", "publish"];

export function SettingsArea({ tab }: { tab: string }) {
  const { user } = useSession();
  const label =
    SETTINGS_TABS.flatMap((g) => g.tabs).find(([t]) => t === tab)?.[1] ?? "";
  if (!user) return null;
  return (
    <div className="settings-area">
      <nav className="set-tabs" aria-label="Settings">
        {visibleSettings(user).map((g) => (
          <div key={g.group} className="set-tabgroup">
            <span className="set-tabgroup-name">{g.group}</span>
            {g.tabs.map(([id, l, icon, tile]) => (
              <a
                key={id}
                href={`#/settings/${id}`}
                className={id === tab ? "on" : ""}
                aria-current={id === tab ? "page" : undefined}
              >
                <span className={`set-ico tile-${tile}`}>
                  <Icon name={icon} size={15} />
                </span>
                {l}
              </a>
            ))}
          </div>
        ))}
      </nav>
      <section className="set-body">
        <div className="head-row">
          <h1 className="page-title">{label}</h1>
          {TAB_INTRO[tab] && (
            <Info label={`About ${label}`}>{TAB_INTRO[tab]}</Info>
          )}
        </div>
        {PRICE_TABS.includes(tab) ? (
          <Prices canEdit={user.role === "admin"} sub={tab} />
        ) : (
          <AdminTab tab={tab} />
        )}
      </section>
    </div>
  );
}

/** The admins' tabs (their hooks read the shop's settings, which only admins may). */
function AdminTab({ tab }: { tab: string }) {
  const specs = useParams();
  const { state } = useShop();
  return (
    <>
      {tab === "company" && (
        <ShopForm
          key="company"
          specs={specs}
          groups={COMPANY}
          owns={[
            "company",
            "domain",
            "languages",
            "colours",
            "bbq_enabled",
            "logo_url",
            "og_image",
            "stock_delivery_note",
            "products",
            "film_url",
            "film_av1",
            "film_poster",
            "story_model",
            "story_media",
          ]}
        />
      )}
      {tab === "company" && <Shipping />}
      {tab === "selling" && (
        <>
          <Heading level={2} className="set-h2" id="matching" icon="selling">
            Matching and direct orders
          </Heading>
          <ShopForm
            key="matching"
            specs={specs}
            groups={MATCHING}
            owns={["matching"]}
          />
          <details className="set-group">
            <summary>How a match is scored (developer values)</summary>
            <Defaults specs={specs} groups={["match"]} filter={false} />
          </details>
          <Heading
            level={2}
            className="set-h2"
            id="b2b"
            icon="b2b"
            info={
              <>
                The terms for business customers in the B2B shop (ADR-104). The
                companies, their logins and orders: Shop →{" "}
                <a href="#/shop/b2b">B2B customers</a>; their price list:
                Settings → <a href="#/settings/pricing">Price rules</a>; a
                company's own price for one cover also shows on that cover's
                Price &amp; shop tab.
              </>
            }
          >
            B2B terms
          </Heading>
          <B2BTerms />
        </>
      )}
      {tab === "users" && <Users />}
      {tab === "defaults" && (
        <Heading
          level={2}
          className="set-h2"
          id="desk"
          icon="desk"
          info={
            <>
              How the Desk works: which covers need an approval before the
              cutting-table DXF (every cover since ADR-128), who approves, when
              a repeated correction becomes a rule, how often the question mails
              go out. The Desk's approval is the only approval. Who approves:
              admins, users marked <b>may approve</b> (Users &amp; rights) and
              the names in <code>desk.approvers</code> below; the workshop role
              never.
            </>
          }
        >
          Desk &amp; approval
        </Heading>
      )}
      {tab === "defaults" && (
        <Defaults specs={specs} groups={["desk", "questions", "products"]} />
      )}
      {tab === "defaults" && (
        <Heading
          level={2}
          className="set-h2"
          id="cover"
          icon="covers"
          info={
            <>
              The company defaults every new cover starts from (
              <code>config/defaults.yaml</code>); a cover's own values are on
              its <i>Adjust</i> tab. Read-only here: the developer changes them,
              one commit per change (which ones you want to change yourself is
              open question 5).
            </>
          }
        >
          Cover defaults
        </Heading>
      )}
      {tab === "defaults" && (
        <Defaults
          specs={specs}
          groups={[
            "construction",
            "stitching",
            "welding",
            "hem",
            "features",
            "seams",
          ]}
        />
      )}
      {tab === "mail" && (
        <>
          <Recipients specs={specs} />
          <ShopForm
            key="mail"
            specs={specs}
            groups={[{ title: "Shop mails", fields: MAIL_SHOP }]}
            owns={["notify_email", "fit_mail"]}
          />
          <Mail />
        </>
      )}
      {tab === "website" && (
        <>
          <WebsiteKey linkKeySet={state?.link_key_set} />
          <ShopForm
            key="website"
            specs={specs}
            groups={[
              { title: "The shop on this server", fields: WEBSITE },
              PAYMENT,
            ]}
            owns={[
              "website_link",
              "home_story",
              "payment",
              "agent_api_enabled",
              "custom_lead_time",
            ]}
          />
          <EmbedAndKeys />
          <AgentKeys />
        </>
      )}
      {tab === "ai" && <AiSpending specs={specs} />}
      {tab === "ai" && (
        <>
          <PhotoTest />
        </>
      )}
      {tab === "system" && (
        <>
          <System />
          <MailOutbox />
          <Heading level={2} className="set-h2" id="activity" icon="users">
            Logged in now
          </Heading>
          <Sessions />
          <Heading level={2} className="set-h2" icon="history">
            Audit log
          </Heading>
          <Audit />
        </>
      )}
    </>
  );
}

/** Shipping per country: a small table instead of the old "0 / 1 / 2" list. */
function Shipping() {
  const { state, setState, msg, setMsg } = useShop();
  const [rows, setRows] = useState<
    { country: string; name: string; eur: number | null }[] | null
  >(null);
  useEffect(() => {
    if (state)
      setRows(
        (state.settings.shipping as {
          country: string;
          name: string;
          eur: number | null;
        }[]) ?? [],
      );
  }, [state]);
  const dirty =
    !!rows &&
    !!state &&
    JSON.stringify(rows) !== JSON.stringify(state.settings.shipping);
  useUnsaved("shipping", dirty);
  if (!rows || !state) return null;
  return (
    <section className="set-group">
      <Heading
        icon="delivery"
        info="What a consumer pays for shipping, incl. VAT; an empty price shows as “to fill in” in the shop."
      >
        Shipping per country
      </Heading>
      <table className="list compact">
        <thead>
          <tr>
            <th>Code</th>
            <th>Country</th>
            <th>Price (€)</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="static">
              {(["country", "name"] as const).map((k) => (
                <td key={k}>
                  <input
                    value={r[k]}
                    aria-label={`${k} ${i + 1}`}
                    onChange={(e) =>
                      setRows(
                        rows.map((x, j) =>
                          j === i ? { ...x, [k]: e.target.value } : x,
                        ),
                      )
                    }
                  />
                </td>
              ))}
              <td>
                <input
                  type="number"
                  value={r.eur ?? ""}
                  aria-label={`price ${i + 1}`}
                  onChange={(e) =>
                    setRows(
                      rows.map((x, j) =>
                        j === i
                          ? {
                              ...x,
                              eur:
                                e.target.value === ""
                                  ? null
                                  : Number(e.target.value),
                            }
                          : x,
                      ),
                    )
                  }
                />
              </td>
              <td>
                <button
                  type="button"
                  className="link"
                  onClick={() => setRows(rows.filter((_, j) => j !== i))}
                >
                  remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row">
        <button
          type="button"
          onClick={() =>
            setRows([...rows, { country: "", name: "", eur: null }])
          }
        >
          + Country
        </button>
        <button
          type="button"
          className="primary"
          disabled={!dirty}
          onClick={async () => {
            setMsg("");
            try {
              const r = await shopAdmin.saveSettings({ shipping: rows });
              setState(r as unknown as ShopState);
              setMsg("Shipping saved.");
            } catch (e) {
              setMsg(String(e));
            }
          }}
        >
          Save shipping
        </button>
        {msg && <span className="muted">{msg}</span>}
      </div>
    </section>
  );
}
