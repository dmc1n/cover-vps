// The dealer embed (ADR-150, docs/plans/dealer-embed.md): <s2dio-configurator dealer="dpk_…">,
// our configurator on a dealer's own website. One module script from the shop's domain; no
// framework, its own shadow DOM. The look comes from the dealer's saved theme, then the element's
// attributes (lang, layout, view3d, kinds, colours: a subset only), then the dealer's own CSS
// (--s2dio-* custom properties and ::part()). Prices come from the server, already the dealer's
// (our B2B price never reaches this page). Events: s2dio:ready, s2dio:priced,
// s2dio:added-to-cart, s2dio:checkout-started (cancelable), s2dio:order-sent, s2dio:error; in the
// frame (/embed/v1/frame) the same as postMessage to the dealer's page.

import type { Viewer } from "./viewer3d";

const API = new URL(import.meta.url).origin;
const HEX = /^#[0-9a-fA-F]{6}$/;
const FONT = /^[A-Za-z0-9 ,'"-]{1,120}$/;
const LOCALES: Record<string, string> = { nl: "nl-NL", en: "en-IE", de: "de-DE", fr: "fr-FR" };
const COUNTRIES = ["NL", "BE", "DE", "FR", "LU", "AT", "CH", "DK", "ES", "IT", "GB"];
const SWATCH: Record<string, string> = {
  Charcoal: "#3a3d40",
  Navy: "#1f2d4d",
  "Light Grey": "#c9c9c4",
  Taupe: "#8b7d6b",
  Black: "#151515",
  Sand: "#d8c9a8",
  Green: "#3d5a40",
};

interface Field {
  key: string;
  label: string;
  default: number | boolean;
  min: number | null;
  max: number | null;
  unit: string | null;
  requires: string | null;
}
interface Product {
  key: string;
  label: string;
  supports: boolean;
  fields: Field[];
}
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
interface Config {
  dealer: { name: string; key: string };
  lang: string;
  languages: string[];
  texts: Record<string, string>;
  theme: Theme;
  layout: "full" | "compact";
  view3d: boolean;
  checkout: "ours" | "dealer";
  end_action: "checkout" | "send_order" | "cart";
  show_vat: boolean;
  shipping_extra: boolean;
  products: Product[];
  colours: string[];
  origins: string[];
  demo: boolean;
}
interface Price {
  amount: number;
  currency: string;
  vat_included: boolean;
  vat_pct: number;
  indicative: boolean;
}
interface Quote {
  id: string;
  product: string;
  sizes_cm: Record<string, unknown>;
  colour: string;
  support: string;
  pieces: number;
  price: Price;
  scene: string | null;
}
/** The studio's live preview (Shop → Dealer embeds): the draft look over the saved one. */
export interface Preview {
  theme?: Partial<Theme>;
  texts?: Record<string, Record<string, string>>;
  layout?: "full" | "compact";
  view3d?: boolean;
}

type Kids = (Node | string | null | false | undefined)[];

function h(
  tag: string,
  props: Record<string, string | boolean | ((e: Event) => void)> = {},
  ...kids: Kids
): HTMLElement {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (typeof v === "function") el.addEventListener(k.slice(2), v as EventListener);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false) el.setAttribute(k, v);
  }
  for (const c of kids) if (c) el.append(c instanceof Node ? c : document.createTextNode(c));
  return el;
}

function safe(v: unknown, re: RegExp, fallback: string): string {
  return typeof v === "string" && re.test(v) ? v : fallback;
}

function css(t: Theme): string {
  const c = (k: keyof Theme, d: string) => safe(t[k], HEX, d);
  const font = safe(t.font, FONT, "inherit");
  const head = safe(t.heading_font, FONT, "inherit");
  const r = Math.max(0, Math.min(40, Number(t.radius_px) || 0));
  return `
:host{display:block;container-type:inline-size;font-family:var(--s2dio-font,${font});
  color:var(--s2dio-text,${c("text", "#1d1d1f")});line-height:1.45}
:host([hidden]){display:none}
*{box-sizing:border-box}
.root{--p:var(--s2dio-primary,${c("primary", "#1f4d3a")});--a:var(--s2dio-accent,${c("accent", "#c8a24a")});
  --t:var(--s2dio-text,${c("text", "#1d1d1f")});--bg:var(--s2dio-bg,${c("background", "#ffffff")});
  --s:var(--s2dio-surface,${c("surface", "#f4f3ef")});--b:var(--s2dio-border,${c("border", "#cfcabd")});
  --r:var(--s2dio-radius,${r}px);--hf:var(--s2dio-heading-font,${head === "inherit" ? "inherit" : head});
  background:var(--bg);color:var(--t);border-radius:var(--r);padding:clamp(14px,3cqi,28px)}
header{display:flex;align-items:center;gap:14px;margin-bottom:6px}
header img{max-height:44px;max-width:160px;object-fit:contain}
h2{font-family:var(--hf);font-size:1.5em;margin:0;font-weight:600}
h3{font-family:var(--hf);font-size:1.05em;margin:18px 0 8px;font-weight:600}
p{margin:6px 0}
.muted{opacity:.75;font-size:.9em}
.grid{display:grid;gap:20px;grid-template-columns:1fr}
@container (min-width:720px){.full .grid{grid-template-columns:1.1fr 1fr}}
.kinds{display:flex;flex-wrap:wrap;gap:8px}
.kind,.colour{border:1px solid var(--b);background:var(--s);color:var(--t);border-radius:var(--r);
  padding:9px 14px;font:inherit;cursor:pointer}
.kind[aria-pressed=true],.colour[aria-pressed=true]{border-color:var(--p);box-shadow:inset 0 0 0 2px var(--p)}
.colour{display:inline-flex;align-items:center;gap:8px}
.dot{width:16px;height:16px;border-radius:50%;border:1px solid var(--b)}
.fields{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
label{display:block;font-size:.9em;margin-bottom:4px}
input,select,textarea{width:100%;padding:9px 10px;font:inherit;color:var(--t);background:var(--bg);
  border:1px solid var(--b);border-radius:calc(var(--r) / 2)}
.check{display:flex;align-items:center;gap:8px}.check input{width:auto}
.side{display:flex;flex-direction:column;gap:12px}
.viewer{position:relative;aspect-ratio:4/3;background:var(--s);border:1px solid var(--b);
  border-radius:var(--r);overflow:hidden}
.viewer canvas{display:block;width:100%!important;height:100%!important}
.viewer .note{position:absolute;inset:auto 0 8px;text-align:center;font-size:.85em;opacity:.7}
.price{background:var(--s);border:1px solid var(--b);border-radius:var(--r);padding:14px 16px}
.amount{font-family:var(--hf);font-size:1.9em;font-weight:600}
button.go{background:var(--p);color:var(--bg);border:0;border-radius:var(--r);padding:12px 20px;
  font:inherit;font-weight:600;cursor:pointer}
button.go[disabled]{opacity:.55;cursor:default}
button.alt{background:transparent;color:var(--t);border:1px solid var(--b);border-radius:var(--r);
  padding:11px 18px;font:inherit;cursor:pointer}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}
.message{padding:10px 12px;border-radius:var(--r);background:var(--s);border-left:4px solid var(--a)}
.error{border-left-color:#b3261e}
.trap{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
footer{margin-top:16px;font-size:.78em;opacity:.65}
.compact header{margin-bottom:0}.compact .intro{display:none}
.compact .kinds{display:block}
:focus-visible{outline:2px solid var(--a);outline-offset:2px}
`;
}

class S2dioConfigurator extends HTMLElement {
  static observedAttributes = ["dealer", "lang", "layout", "view3d", "kinds", "colours"];
  private root: ShadowRoot;
  private config: Config | null = null;
  private failed = "";
  private product = "";
  private sizes: Record<string, number | boolean> = {};
  private colour = "";
  private support = "none";
  private quote: Quote | null = null;
  private busy = false;
  private step: "configure" | "form" | "sent" | "added" = "configure";
  private reference = "";
  private notice = "";
  private draft: Preview | null = null;
  private viewer: Viewer | null = null;
  private viewerHost: HTMLElement | null = null;
  private shown = "";
  private timer = 0;
  private asked = 0;
  private parentOrigin = "";

  constructor() {
    super();
    this.root = this.attachShadow({ mode: "open" });
    // a `preview` set before this script ran is an own property of the element: take it over
    if (Object.prototype.hasOwnProperty.call(this, "preview")) {
      const early = (this as unknown as { preview: Preview | null }).preview;
      delete (this as unknown as { preview?: unknown }).preview;
      this.draft = early;
    }
  }

  connectedCallback(): void {
    void this.load();
  }

  disconnectedCallback(): void {
    this.drop3d();
  }

  private drop3d(): void {
    this.viewer?.dispose();
    this.viewer = null;
    this.viewerHost = null;
    this.shown = "";
  }

  /** The 3D view's box: one per element, kept across renders (one WebGL context). */
  private viewerBox(): HTMLElement {
    if (!this.viewerHost)
      this.viewerHost = h("div", { class: "viewer", part: "viewer" }, h("div", { class: "note" }));
    return this.viewerHost;
  }

  attributeChangedCallback(name: string, old: string | null, now: string | null): void {
    if (old === now || !this.isConnected) return;
    if (name === "dealer" || name === "lang") void this.load();
    else this.render();
  }

  /** The studio's live preview: the draft theme, texts and layout over the saved ones. */
  set preview(p: Preview | null) {
    this.draft = p;
    this.render();
  }

  get preview(): Preview | null {
    return this.draft;
  }

  private get key(): string {
    return this.getAttribute("dealer") || "";
  }

  private url(path: string): string {
    return `${API}/api/embed/v1/${encodeURIComponent(this.key)}/${path}`;
  }

  private t(k: string): string {
    const c = this.config;
    const lang = c?.lang || "en";
    const own = this.draft?.texts?.[lang]?.[k];
    return (own && own.trim()) || c?.texts[k] || k;
  }

  private emit(type: string, detail: unknown): boolean {
    const ok = this.dispatchEvent(
      new CustomEvent(type, { detail, bubbles: true, composed: true, cancelable: true }),
    );
    if (this.hasAttribute("frame") && this.parentOrigin && window.parent !== window)
      window.parent.postMessage({ source: "s2dio-configurator", type, detail }, this.parentOrigin);
    return ok;
  }

  private async call<T>(path: string, body?: unknown): Promise<T> {
    const r = await fetch(this.url(path), {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin", // a colleague's preview in the studio; never to a dealer's site
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = typeof d.detail === "string" ? d.detail : `${r.status}`;
      this.emit("s2dio:error", { code: r.status, message: msg });
      throw new Error(r.status === 429 ? this.t("busy") : msg);
    }
    return d as T;
  }

  private async load(): Promise<void> {
    if (!this.key) return;
    const lang = this.getAttribute("lang") || (navigator.language || "").slice(0, 2);
    try {
      this.config = await this.call<Config>(`config?lang=${encodeURIComponent(lang)}`);
      this.failed = "";
    } catch (e) {
      this.config = null;
      this.failed = String((e as Error).message || e);
    }
    const c = this.config;
    if (c && this.hasAttribute("frame")) {
      const anc = (location as Location & { ancestorOrigins?: DOMStringList }).ancestorOrigins;
      const parent = anc?.[0] || (document.referrer ? new URL(document.referrer).origin : "");
      this.parentOrigin =
        parent && (c.origins.includes(parent) || parent === location.origin) ? parent : "";
    }
    const products = this.products();
    this.product = products[0]?.key || "";
    this.reset();
    this.render();
    if (c) this.emit("s2dio:ready", { dealer: c.dealer.key, lang: c.lang });
  }

  /** The kinds the dealer offers, narrowed by the element's own `kinds` attribute. */
  private products(): Product[] {
    const all = this.config?.products || [];
    const only = (this.getAttribute("kinds") || "").split(",").map((s) => s.trim()).filter(Boolean);
    const some = all.filter((p) => !only.length || only.includes(p.key));
    return some.length ? some : all;
  }

  private colours(): string[] {
    const all = this.config?.colours || [];
    const only = (this.getAttribute("colours") || "").split(",").map((s) => s.trim()).filter(Boolean);
    const some = all.filter((c) => !only.length || only.includes(c));
    return some.length ? some : all;
  }

  private reset(): void {
    const p = this.products().find((x) => x.key === this.product);
    this.sizes = {};
    for (const f of p?.fields || []) this.sizes[f.key] = f.default;
    this.colour = this.colours()[0] || "";
    this.support = "none";
    this.quote = null;
    this.step = "configure";
    this.notice = "";
  }

  private layout(): "full" | "compact" {
    const a = this.getAttribute("layout");
    if (a === "full" || a === "compact") return a;
    return this.draft?.layout || this.config?.layout || "full";
  }

  private show3d(): boolean {
    if (this.getAttribute("view3d") === "off") return false;
    const on = this.draft?.view3d ?? this.config?.view3d ?? false;
    return Boolean(on);
  }

  private money(p: Price): string {
    const lang = this.config?.lang || "en";
    return new Intl.NumberFormat(LOCALES[lang] || lang, {
      style: "currency",
      currency: p.currency || "EUR",
    }).format(p.amount);
  }

  private dealerName(s: string): string {
    return s.replace("{dealer}", this.config?.dealer.name || "");
  }

  // ---- rendering ---------------------------------------------------------------------------
  private render(): void {
    const c = this.config;
    if (!this.show3d()) this.drop3d();
    const style = h("style");
    if (!c) {
      style.textContent = css({} as Theme);
      this.root.replaceChildren(
        style,
        h("div", { class: "root", part: "root" }, this.failed ? h("p", { class: "message error", part: "message" }, this.failed) : "…"),
      );
      return;
    }
    const theme = { ...c.theme, ...(this.draft?.theme || {}) } as Theme;
    style.textContent = css(theme);
    const logo =
      theme.logo_url && /^https:\/\//.test(theme.logo_url)
        ? h("img", { src: theme.logo_url, alt: c.dealer.name, part: "logo" })
        : null;
    const head = h(
      "header",
      { part: "header" },
      logo,
      h("div", {}, h("h2", { part: "title" }, this.t("title"))),
    );
    const intro = h("p", { class: "intro muted", part: "intro" }, this.t("intro"));
    const body =
      this.step === "sent"
        ? this.sentView()
        : this.step === "form"
          ? this.formView()
          : this.configureView();
    const demo = c.demo ? h("p", { class: "muted" }, this.t("demo")) : null;
    const foot = h("footer", { part: "footer" }, this.t("made_by"));
    this.root.replaceChildren(
      style,
      h("div", { class: `root ${this.layout()}`, part: "root", lang: c.lang }, head, intro, demo, body, foot),
    );
    if (this.step === "configure" && this.show3d()) void this.mount3d();
  }

  private configureView(): HTMLElement {
    const products = this.products();
    const p = products.find((x) => x.key === this.product) || products[0];
    const kinds =
      this.layout() === "compact"
        ? h(
            "select",
            {
              part: "kinds",
              "aria-label": this.t("choose_kind"),
              onchange: (e: Event) => this.choose((e.target as HTMLSelectElement).value),
            },
            ...products.map((x) =>
              h("option", { value: x.key, selected: x.key === p?.key }, x.label),
            ),
          )
        : h(
            "div",
            { class: "kinds", part: "kinds", role: "group", "aria-label": this.t("choose_kind") },
            ...products.map((x) =>
              h(
                "button",
                {
                  type: "button",
                  class: "kind",
                  part: "kind",
                  "aria-pressed": String(x.key === p?.key),
                  onclick: () => this.choose(x.key),
                },
                x.label,
              ),
            ),
          );
    const fields = h(
      "div",
      { class: "fields", part: "fields" },
      ...(p?.fields || [])
        .filter((f) => !f.requires || this.sizes[f.requires] === true)
        .map((f) => this.fieldView(f)),
    );
    const colours = this.colours();
    const colourView =
      colours.length > 1
        ? h(
            "div",
            { class: "kinds", part: "colours", role: "group", "aria-label": this.t("colour") },
            ...colours.map((col) =>
              h(
                "button",
                {
                  type: "button",
                  class: "colour",
                  part: "colour",
                  "aria-pressed": String(col === this.colour),
                  onclick: () => {
                    this.colour = col;
                    this.changed(true);
                  },
                },
                h("span", { class: "dot", style: `background:${SWATCH[col] || "#999"}` }),
                col,
              ),
            ),
          )
        : null;
    const support = p?.supports
      ? h(
          "div",
          {},
          h("h3", {}, this.t("support")),
          h(
            "select",
            {
              part: "input",
              "aria-label": this.t("support"),
              onchange: (e: Event) => {
                this.support = (e.target as HTMLSelectElement).value;
                this.changed(false);
              },
            },
            ...["none", "balloons", "frame"].map((s) =>
              h("option", { value: s, selected: s === this.support }, this.t(`support_${s}`)),
            ),
          ),
        )
      : null;
    const form = h(
      "div",
      { part: "form" },
      h("h3", {}, this.t("choose_kind")),
      kinds,
      h("h3", {}, this.t("sizes")),
      h("p", { class: "muted" }, this.t("sizes_help")),
      fields,
      colourView ? h("h3", {}, this.t("colour")) : null,
      colourView,
      support,
    );
    const side = h(
      "div",
      { class: "side" },
      this.show3d()
        ? this.viewerBox()
        : null,
      this.priceView(),
    );
    return h("div", { class: "grid" }, form, side);
  }

  private fieldView(f: Field): HTMLElement {
    const id = `f-${f.key}`;
    if (typeof f.default === "boolean")
      return h(
        "div",
        { class: "check", part: "field" },
        h("input", {
          id,
          type: "checkbox",
          part: "input",
          checked: this.sizes[f.key] === true,
          onchange: (e: Event) => {
            this.sizes[f.key] = (e.target as HTMLInputElement).checked;
            this.changed(true);
          },
        }),
        h("label", { for: id, part: "label" }, f.label),
      );
    return h(
      "div",
      { part: "field" },
      h("label", { for: id, part: "label" }, `${f.label}${f.unit ? ` (${f.unit})` : ""}`),
      h("input", {
        id,
        type: "number",
        inputmode: "numeric",
        part: "input",
        min: f.min === null ? false : String(f.min),
        max: f.max === null ? false : String(f.max),
        step: "1",
        value: String(this.sizes[f.key] ?? ""),
        oninput: (e: Event) => {
          const v = (e.target as HTMLInputElement).valueAsNumber;
          if (Number.isFinite(v)) this.sizes[f.key] = v;
          this.changed(false);
        },
      }),
    );
  }

  private priceView(): HTMLElement {
    const c = this.config!;
    const q = this.quote;
    const box = h("div", { class: "price", part: "price", "aria-live": "polite" });
    if (q) {
      const vat = q.price.vat_included ? this.t("incl_vat") : this.t("ex_vat");
      box.append(
        h("div", { class: "muted" }, this.t("price")),
        h("div", { class: "amount" }, this.money(q.price)),
        h(
          "div",
          { class: "muted" },
          `${vat}${c.shipping_extra ? ` · ${this.t("shipping_extra")}` : ""}${
            q.price.indicative ? ` · ${this.t("indicative")}` : ""
          }`,
        ),
      );
    }
    if (this.notice) box.append(h("p", { class: "message", part: "message" }, this.notice));
    const actions = h("div", { class: "actions" });
    actions.append(
      h(
        "button",
        {
          type: "button",
          class: q ? "alt" : "go",
          part: q ? "button" : "button primary",
          disabled: this.busy,
          onclick: () => void this.price(),
        },
        this.t("get_price"),
      ),
    );
    if (q) {
      const label =
        c.end_action === "checkout"
          ? this.t("order")
          : c.end_action === "cart"
            ? this.t("add_to_cart")
            : this.dealerName(this.t("cta") !== "cta" ? this.t("cta") : this.t("send"));
      actions.append(
        h(
          "button",
          {
            type: "button",
            class: "go",
            part: "button primary",
            disabled: this.busy,
            onclick: () => void this.finish(),
          },
          c.end_action === "checkout" && this.t("cta") !== "cta" ? this.t("cta") : label,
        ),
      );
    }
    box.append(actions);
    return box;
  }

  private async mount3d(): Promise<void> {
    const el = this.viewerHost;
    const scene = this.quote?.scene;
    if (!el || !scene || scene === this.shown) return;
    this.shown = scene;
    const note = el.querySelector(".note")!;
    note.textContent = this.t("loading_3d");
    if (!this.viewer) {
      const { mountViewer } = await import("./viewer3d");
      if (this.viewerHost !== el) return;
      const surface = { ...this.config?.theme, ...this.draft?.theme }.surface;
      this.viewer = mountViewer(el, safe(surface, HEX, "#f4f3ef"));
    }
    try {
      await this.viewer.show(API + scene);
    } finally {
      note.textContent = "";
    }
  }

  private formView(): HTMLElement {
    const lang = this.config?.lang || "nl";
    const input = (name: string, type = "text", required = true) =>
      h(
        "div",
        { part: "field" },
        h("label", { for: `c-${name}`, part: "label" }, this.t(name)),
        h("input", { id: `c-${name}`, name, type, required, part: "input", maxlength: "160" }),
      );
    const country = h(
      "select",
      { id: "c-country", name: "country", part: "input" },
      ...COUNTRIES.map((k) =>
        h("option", { value: k, selected: k === ({ nl: "NL", de: "DE", fr: "FR" }[lang] || "NL") }, k),
      ),
    );
    const form = h(
      "form",
      {
        part: "form",
        onsubmit: (e: Event) => {
          e.preventDefault();
          void this.send(e.target as HTMLFormElement);
        },
      },
      h("h3", {}, this.t("your_details")),
      h(
        "div",
        { class: "fields" },
        input("name"),
        input("email", "email"),
        input("phone", "tel", false),
        input("street", "text", false),
        input("postcode", "text", false),
        input("city", "text", false),
        h("div", { part: "field" }, h("label", { for: "c-country", part: "label" }, this.t("country")), country),
      ),
      h(
        "div",
        { part: "field" },
        h("label", { for: "c-note", part: "label" }, this.t("note")),
        h("textarea", { id: "c-note", name: "note", rows: "3", part: "input", maxlength: "2000" }),
      ),
      h(
        "div",
        { class: "trap", "aria-hidden": "true" },
        h("input", { name: "website", tabindex: "-1", autocomplete: "off" }),
      ),
      this.notice ? h("p", { class: "message error", part: "message" }, this.notice) : null,
      h(
        "div",
        { class: "actions" },
        h(
          "button",
          { type: "button", class: "alt", part: "button", onclick: () => this.back() },
          this.t("back"),
        ),
        h(
          "button",
          { type: "submit", class: "go", part: "button primary", disabled: this.busy },
          this.dealerName(this.t("send")),
        ),
      ),
    );
    return h("div", {}, this.quote ? this.priceSummary() : null, form);
  }

  private priceSummary(): HTMLElement {
    const q = this.quote!;
    return h(
      "div",
      { class: "price", part: "price" },
      h("div", { class: "amount" }, this.money(q.price)),
      h("div", { class: "muted" }, q.price.vat_included ? this.t("incl_vat") : this.t("ex_vat")),
    );
  }

  private sentView(): HTMLElement {
    const own = this.t("thanks");
    const text =
      own !== "thanks"
        ? own
        : this.dealerName(this.t("sent_text")).replace("{n}", this.reference);
    return h(
      "div",
      { class: "message", part: "message", role: "status" },
      h("h3", {}, this.t("sent_title")),
      h("p", {}, text),
      h("p", { class: "muted" }, this.reference),
    );
  }

  // ---- actions -----------------------------------------------------------------------------
  private choose(key: string): void {
    this.product = key;
    this.reset();
    this.render();
  }

  private back(): void {
    this.step = "configure";
    this.notice = "";
    this.render();
  }

  /** A change of the choices: the price on screen is gone; after a first price, a new one
   * follows by itself (a short pause after typing). */
  private changed(rerender: boolean): void {
    const had = this.quote !== null;
    this.quote = null;
    this.notice = "";
    window.clearTimeout(this.timer);
    if (had) this.timer = window.setTimeout(() => void this.price(), 700);
    if (rerender) this.render();
    else {
      const old = this.root.querySelector(".price");
      old?.replaceWith(this.priceView());
    }
  }

  private async price(): Promise<void> {
    const ask = ++this.asked;
    this.busy = true;
    this.notice = "";
    this.root.querySelector(".price")?.replaceWith(this.priceView());
    try {
      const sizes: Record<string, number | boolean> = {};
      const p = this.products().find((x) => x.key === this.product);
      for (const f of p?.fields || [])
        if (!f.requires || this.sizes[f.requires] === true) sizes[f.key] = this.sizes[f.key];
      const q = await this.call<Quote>("quote", {
        product: this.product,
        sizes,
        colour: this.colour || null,
        support: this.support,
        lang: this.config?.lang || "nl",
      });
      if (ask !== this.asked) return;
      this.quote = q;
      this.emit("s2dio:priced", this.detail(q));
    } catch (e) {
      if (ask === this.asked) this.notice = String((e as Error).message || e);
    } finally {
      if (ask === this.asked) {
        this.busy = false;
        this.render();
      }
    }
  }

  private detail(q: Quote) {
    return {
      quoteId: q.id,
      product: q.product,
      sizes: q.sizes_cm,
      colour: q.colour,
      support: q.support,
      price: { amount: q.price.amount, currency: q.price.currency, vatIncluded: q.price.vat_included },
    };
  }

  private async finish(): Promise<void> {
    const c = this.config!;
    const q = this.quote;
    if (!q) return;
    if (c.end_action === "send_order") {
      this.step = "form";
      this.notice = "";
      this.render();
      return;
    }
    this.busy = true;
    try {
      if (c.end_action === "cart") {
        await this.call("event", { type: "cart", quote_id: q.id });
        this.emit("s2dio:added-to-cart", this.detail(q));
        this.notice = this.t("added");
      } else {
        const { checkout_url } = await this.call<{ checkout_url: string }>("checkout", {
          quote_id: q.id,
          lang: c.lang,
        });
        const go = this.emit("s2dio:checkout-started", { quoteId: q.id, checkoutUrl: checkout_url });
        if (go) {
          if (this.hasAttribute("frame")) window.open(checkout_url, "_blank", "noopener");
          else window.location.assign(checkout_url);
        }
      }
    } catch (e) {
      this.notice = String((e as Error).message || e);
    } finally {
      this.busy = false;
      this.render();
    }
  }

  private async send(form: HTMLFormElement): Promise<void> {
    const q = this.quote;
    if (!q) return;
    const f = new FormData(form);
    const v = (k: string) => String(f.get(k) || "").trim();
    this.busy = true;
    try {
      const r = await this.call<{ reference: string }>("order", {
        quote_id: q.id,
        name: v("name"),
        email: v("email"),
        phone: v("phone"),
        street: v("street"),
        postcode: v("postcode"),
        city: v("city"),
        country: v("country") || "NL",
        note: v("note"),
        lang: this.config?.lang || "nl",
        website: v("website"),
      });
      this.reference = r.reference;
      this.step = "sent";
      this.emit("s2dio:order-sent", { reference: r.reference, quoteId: q.id });
    } catch (e) {
      this.notice = String((e as Error).message || e) || this.t("error");
    } finally {
      this.busy = false;
      this.render();
    }
  }
}

if (!customElements.get("s2dio-configurator"))
  customElements.define("s2dio-configurator", S2dioConfigurator);

export { S2dioConfigurator };
