// Search everything, in the header (ADR-124): covers (name, tag, note, family), the Desk's codes
// and product names, the questions, and the shop's orders (admins). The lists are fetched the
// first time the box is used, each with the rights the person already has; nothing new is
// exposed. Ctrl+K (Cmd+K) focuses the box; arrows and Enter open a hit; Escape closes.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, shopAdmin, type ModelBrief, type ShopOrder } from "./api";
import { deskHref, modelHref, questionHref } from "./nav";
import { useSession } from "./Session";

interface DeskRef {
  id: string;
  code: string;
  status: string;
  products?: string[];
  tags: string[];
}
interface QuestionRef {
  id: number;
  title: string;
  status: string;
  models: { id: string; code: string }[];
}
interface Hit {
  group: "Covers" | "Desk" | "Questions" | "Orders";
  key: string;
  href: string;
  label: string;
  note: string;
}
interface Sources {
  models: ModelBrief[];
  desk: DeskRef[];
  questions: QuestionRef[];
  orders: ShopOrder[];
}
const PER_GROUP = 5;

const json = (url: string) =>
  fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(r.status)));

export function Search() {
  const { user } = useSession();
  const admin = user?.role === "admin";
  const [src, setSrc] = useState<Sources | null>(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = () => {
    if (src || loading) return;
    setLoading(true);
    // each list on its own: one that fails (or is not for this role) leaves the others
    Promise.all([
      api.models().catch(() => [] as ModelBrief[]),
      json("/api/desk")
        .then((d) => d.items as DeskRef[])
        .catch(() => [] as DeskRef[]),
      json("/api/questions")
        .then((d) => d.items as QuestionRef[])
        .catch(() => [] as QuestionRef[]),
      admin
        ? shopAdmin
            .orders()
            .then((d) => d.orders)
            .catch(() => [] as ShopOrder[])
        : Promise.resolve([] as ShopOrder[]),
    ]).then(([models, desk, questions, orders]) => {
      setSrc({ models, desk, questions, orders });
      setLoading(false);
    });
  };

  const hits = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length || !src) return [];
    const match = (text: string) => {
      const t = text.toLowerCase();
      return words.every((w) => t.includes(w));
    };
    const codes = new Map(src.desk.map((d) => [d.id, d]));
    const out: Hit[] = [];
    const add = (h: Hit[]) => out.push(...h.slice(0, PER_GROUP));
    add(
      src.models
        .filter((m) =>
          match(
            `${m.id} ${m.tags.join(" ")} ${m.notes} ${m.family ?? ""} ${m.category ?? ""} ${codes.get(m.id)?.code ?? ""}`,
          ),
        )
        .map((m) => ({
          group: "Covers",
          key: `m-${m.id}`,
          href: modelHref(m.id),
          label: m.id,
          note: `${m.grade === "check" ? "to check" : m.grade}${m.panels != null ? ` · ${m.panels} pieces` : ""}`,
        })),
    );
    add(
      src.desk
        .filter((d) => match(`${d.code} ${(d.products ?? []).join(" ")}`))
        .map((d) => ({
          group: "Desk",
          key: `d-${d.id}`,
          href: deskHref(d.id),
          label: d.code,
          note: `${d.status}${d.products?.length ? ` · ${d.products.slice(0, 2).join(", ")}` : ""}`,
        })),
    );
    add(
      src.questions
        .filter((x) =>
          match(
            `#${x.id} ${x.id} ${x.title} ${x.models.map((m) => m.code).join(" ")}`,
          ),
        )
        .map((x) => ({
          group: "Questions",
          key: `q-${x.id}`,
          href: questionHref(x.id),
          label: `#${x.id} ${x.title}`,
          note: x.status,
        })),
    );
    add(
      src.orders
        .filter((o) =>
          match(
            `#${o.id} ${o.id} ${String(o.data.customer.name ?? "")} ${o.email} ${o.data.quote.quote.product} ${o.model_id ?? ""}`,
          ),
        )
        .map((o) => ({
          group: "Orders",
          key: `o-${o.id}`,
          href: `#/shop/orders/${o.id}`,
          label: `Order ${o.id}: ${String(o.data.customer.name ?? "")}`,
          note: `${o.status} · ${o.data.quote.quote.product}`,
        })),
    );
    return out;
  }, [q, src]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node))
        setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", key);
    };
  }, []);

  const go = (h: Hit) => {
    window.location.hash = h.href;
    setOpen(false);
    setQ("");
    input.current?.blur();
  };

  return (
    <div className="quick-search" ref={box} role="search">
      <input
        ref={input}
        type="search"
        placeholder="Search everything…"
        aria-label="Search covers, Desk codes, questions and orders"
        title="Covers, Desk codes, questions and orders (Ctrl+K)"
        value={q}
        onFocus={() => {
          load();
          setOpen(true);
        }}
        onChange={(e) => {
          setQ(e.target.value);
          setAt(0);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setAt((a) => Math.min(a + 1, hits.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setAt((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter" && hits[at]) go(hits[at]);
          else if (e.key === "Escape") {
            setOpen(false);
            input.current?.blur();
          }
        }}
      />
      {open && q && (
        <ul className="hits" role="listbox" aria-label="Search results">
          {!src && <li className="muted">Loading…</li>}
          {src && hits.length === 0 && <li className="muted">Nothing found</li>}
          {hits.map((h, i) => [
            (i === 0 || hits[i - 1].group !== h.group) && (
              <li
                key={`g-${h.group}`}
                className="hit-group"
                role="presentation"
              >
                {h.group}
              </li>
            ),
            <li
              key={h.key}
              role="option"
              aria-selected={i === at}
              className={i === at ? "active" : ""}
              onMouseEnter={() => setAt(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                go(h);
              }}
            >
              <span className="id">{h.label}</span>
              <span className="muted">{h.note}</span>
            </li>,
          ])}
        </ul>
      )}
    </div>
  );
}
