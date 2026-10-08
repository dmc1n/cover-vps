// Admin → B2B customers (ADR-104): the business accounts of the B2B shop, apart from the
// studio's users. Invite a company by mail, approve a request, block, give a company another
// price list or its own fixed prices, its delivery addresses, its people, and see its orders.
import { useCallback, useEffect, useState } from "react";
import "./b2b-admin.css";

interface Addr {
  id: string | null;
  label: string;
  name: string;
  street: string;
  postcode: string;
  city: string;
  country: string;
}
interface Person {
  id: number;
  email: string;
  name: string | null;
  active: boolean;
  has_password: boolean;
  last_login: number | null;
  invited_until: number | null;
}
interface Company {
  id: number;
  created: number;
  name: string;
  vat_number: string | null;
  contact: string | null;
  email: string | null;
  phone: string | null;
  street: string | null;
  postcode: string | null;
  city: string | null;
  country: string | null;
  addresses: Addr[];
  price_list: string;
  fixed: Record<string, number>;
  reverse_charge: boolean;
  status: string;
  note: string | null;
  request: { message: string; lang: string; time: number } | null;
  users: Person[];
  orders: number;
  ordered_eur: number;
}
interface Settings {
  online_payment: boolean;
  min_order_eur: number;
  shipping_eur: number;
  payment_days: number;
  auto_produce: boolean;
}
interface State {
  companies: Company[];
  price_lists: Record<string, string>;
  statuses: string[];
  settings: Settings;
  shop_url: string;
}
interface B2BOrder {
  id: number;
  created: number;
  company: string;
  po: string | null;
  net_eur: number;
  vat_eur: number;
  gross_eur: number;
  address: Addr;
  lines: {
    qty: number;
    unit_eur: number;
    total_eur: number;
    product: string;
    label: string | null;
    colour: string;
    order_id: number;
    status: string | null;
    model_id: string | null;
  }[];
}
interface InviteResult {
  link: string | null;
  mailed: boolean;
}

async function call<R>(method: string, path: string, body?: unknown): Promise<R> {
  const r = await fetch(`/api/admin/b2b/${path}`, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok)
    throw new Error(typeof d.detail === "string" ? d.detail : `${r.status} ${JSON.stringify(d.detail ?? "")}`);
  return d as R;
}
const when = (t: number | null) => (t ? new Date(t * 1000).toLocaleString() : "—");
const eur = (n: number) => `€ ${n.toFixed(2)}`;
const NEW = {
  name: "",
  vat_number: "",
  contact: "",
  email: "",
  phone: "",
  street: "",
  postcode: "",
  city: "",
  country: "NL",
  price_list: "b2b",
  lang: "nl",
};

export function B2BCustomers() {
  const [s, setS] = useState<State | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [form, setForm] = useState(NEW);
  const [invite, setInvite] = useState<(InviteResult & { who: string }) | null>(null);
  const load = useCallback(() => {
    call<State>("GET", "companies")
      .then(setS)
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);
  const run = async <R,>(f: () => Promise<R>): Promise<R | undefined> => {
    setError("");
    try {
      const r = await f();
      load();
      return r;
    } catch (e) {
      setError(String(e));
      return undefined;
    }
  };
  if (!s) return <p className="muted">{error || "…"}</p>;
  const requests = s.companies.filter((c) => c.status === "requested");
  const rest = s.companies.filter((c) => c.status !== "requested");
  return (
    <>
      {error && <p className="error">{error}</p>}
      <section className="card">
        <h3>B2B customers</h3>
        <p className="muted">
          Business customers (Sunsit, dealers) log in at{" "}
          <a href={s.shop_url} target="_blank" rel="noreferrer">
            {s.shop_url}
          </a>{" "}
          with their own account (not a studio login). They see the same configurator and
          the catalogue covers at their price list, ex VAT, and order on account; each order
          line appears under Orders, flagged B2B. Nobody gets in without an invitation from
          here: a request from the site waits below for your approval.
        </p>
        {invite && (
          <p className={invite.mailed ? "" : "error"}>
            {invite.mailed
              ? `The invitation was mailed to ${invite.who}.`
              : `No mail was sent (no mail server?). Send ${invite.who} this link yourself:`}{" "}
            {invite.link && <code>{invite.link}</code>}
          </p>
        )}
      </section>
      {requests.length > 0 && (
        <section className="card">
          <h3>Requests ({requests.length})</h3>
          <table className="list">
            <tbody>
              {requests.map((c) => (
                <tr key={c.id} className="static">
                  <td>
                    <strong>{c.name}</strong> · VAT {c.vat_number || "—"}
                    <br />
                    <span className="muted">
                      {c.contact} &lt;{c.email}&gt; · {c.phone} · {c.city} {c.country} ·{" "}
                      {when(c.created)}
                    </span>
                    {c.request?.message && <p>{c.request.message}</p>}
                  </td>
                  <td className="nowrap">
                    <button
                      className="primary"
                      onClick={async () => {
                        const r = await run(() =>
                          call<InviteResult>("POST", `companies/${c.id}/approve`),
                        );
                        if (r) setInvite({ ...r, who: c.email ?? c.name });
                      }}
                    >
                      Approve and invite
                    </button>{" "}
                    <button
                      onClick={() =>
                        run(() => call("PUT", `companies/${c.id}`, { status: "rejected" }))
                      }
                    >
                      Reject
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <section className="card">
        <h3>Companies</h3>
        <table className="list">
          <thead>
            <tr>
              <th>Company</th>
              <th>Status</th>
              <th>Price list</th>
              <th>People</th>
              <th>Orders</th>
            </tr>
          </thead>
          <tbody>
            {rest.length === 0 && (
              <tr className="static">
                <td colSpan={5} className="muted">
                  No business customers yet: invite the first one below.
                </td>
              </tr>
            )}
            {rest.map((c) => (
              <tr key={c.id} onClick={() => setOpen(open === c.id ? null : c.id)}>
                <td>
                  <strong>{c.name}</strong>
                  <br />
                  <span className="muted">
                    VAT {c.vat_number || "—"} · {c.city} {c.country}
                  </span>
                </td>
                <td>
                  <span className={`b2b-status ${c.status}`}>{c.status}</span>
                </td>
                <td>
                  {s.price_lists[c.price_list] ?? c.price_list}
                  {Object.keys(c.fixed).length > 0 &&
                    ` + ${Object.keys(c.fixed).length} fixed`}
                </td>
                <td>{c.users.length}</td>
                <td>
                  {c.orders} · {eur(c.ordered_eur)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {open !== null && s.companies.find((c) => c.id === open) && (
        <CompanyCard
          key={open}
          c={s.companies.find((c) => c.id === open)!}
          s={s}
          run={run}
          onInvite={(r, who) => setInvite({ ...r, who })}
        />
      )}
      <section className="card">
        <h3>Invite a company</h3>
        <p className="muted">
          The company gets an account at once; its contact gets a mail with a link to
          choose a password (valid for 7 days), in the language chosen here.
        </p>
        <form
          className="fields b2b-fields"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await run(() =>
              call<InviteResult>("POST", "companies", { ...form, send_invite: true }),
            );
            if (r) {
              setInvite({ ...r, who: form.email });
              setForm(NEW);
            }
          }}
        >
          {(
            [
              ["name", "Company"],
              ["vat_number", "VAT number"],
              ["contact", "Contact person"],
              ["email", "E-mail (logs in)"],
              ["phone", "Phone"],
              ["street", "Street (invoice address)"],
              ["postcode", "Postcode"],
              ["city", "City"],
              ["country", "Country (2 letters)"],
            ] as const
          ).map(([k, l]) => (
            <label className="field" key={k}>
              <span>{l}</span>
              <input
                required={k === "name" || k === "email"}
                type={k === "email" ? "email" : "text"}
                value={form[k]}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })}
              />
            </label>
          ))}
          <label className="field">
            <span>Price list</span>
            <select
              value={form.price_list}
              onChange={(e) => setForm({ ...form, price_list: e.target.value })}
            >
              {Object.entries(s.price_lists).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Language of the mails</span>
            <select value={form.lang} onChange={(e) => setForm({ ...form, lang: e.target.value })}>
              {["nl", "en", "de", "fr"].map((l) => (
                <option key={l}>{l}</option>
              ))}
            </select>
          </label>
          <button className="primary">Invite</button>
        </form>
      </section>
      <SettingsCard s={s} run={run} />
    </>
  );
}

function CompanyCard({
  c,
  s,
  run,
  onInvite,
}: {
  c: Company;
  s: State;
  run: <R>(f: () => Promise<R>) => Promise<R | undefined>;
  onInvite: (r: InviteResult, who: string) => void;
}) {
  const [f, setF] = useState({
    name: c.name,
    vat_number: c.vat_number ?? "",
    contact: c.contact ?? "",
    email: c.email ?? "",
    phone: c.phone ?? "",
    street: c.street ?? "",
    postcode: c.postcode ?? "",
    city: c.city ?? "",
    country: c.country ?? "",
    price_list: c.price_list,
    reverse_charge: c.reverse_charge,
    note: c.note ?? "",
  });
  const [fixed, setFixed] = useState(
    Object.entries(c.fixed)
      .map(([k, v]) => `${k} = ${v}`)
      .join("\n"),
  );
  const [person, setPerson] = useState({ email: "", name: "", lang: "nl" });
  const [orders, setOrders] = useState<B2BOrder[] | null>(null);
  useEffect(() => {
    call<{ orders: B2BOrder[] }>("GET", `orders?company=${c.id}`)
      .then((r) => setOrders(r.orders))
      .catch(() => setOrders([]));
  }, [c.id]);
  const parsed = (): Record<string, number> =>
    Object.fromEntries(
      fixed
        .split("\n")
        .map((l) => l.split("="))
        .filter((p) => p.length === 2 && p[0].trim())
        .map(([k, v]) => [k.trim(), Number(v.trim().replace(",", "."))]),
    );
  return (
    <section className="card">
      <h3>
        {c.name} <span className={`b2b-status ${c.status}`}>{c.status}</span>
      </h3>
      <p>
        {c.status !== "blocked" ? (
          <button
            className="danger"
            onClick={() => run(() => call("PUT", `companies/${c.id}`, { status: "blocked" }))}
          >
            Block (logs everyone out)
          </button>
        ) : (
          <button
            onClick={() => run(() => call("PUT", `companies/${c.id}`, { status: "active" }))}
          >
            Unblock
          </button>
        )}
      </p>
      <form
        className="fields b2b-fields"
        onSubmit={(e) => {
          e.preventDefault();
          run(() => call("PUT", `companies/${c.id}`, { ...f, fixed: parsed() }));
        }}
      >
        {(
          [
            ["name", "Company"],
            ["vat_number", "VAT number"],
            ["contact", "Contact person"],
            ["email", "E-mail for the order mails"],
            ["phone", "Phone"],
            ["street", "Street (invoice address)"],
            ["postcode", "Postcode"],
            ["city", "City"],
            ["country", "Country"],
          ] as const
        ).map(([k, l]) => (
          <label className="field" key={k}>
            <span>{l}</span>
            <input value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
          </label>
        ))}
        <label className="field">
          <span>Price list</span>
          <select
            value={f.price_list}
            onChange={(e) => setF({ ...f, price_list: e.target.value })}
          >
            {Object.entries(s.price_lists).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={f.reverse_charge}
            onChange={(e) => setF({ ...f, reverse_charge: e.target.checked })}
          />{" "}
          VAT reverse-charged (no VAT on the order: an EU company outside NL with a valid VAT
          number; check with the accountant)
        </label>
        <label className="field">
          <span>
            Fixed prices for this company, ex VAT, one per line: <code>suns-… = 249</code>,{" "}
            <code>balloon = 12</code>, <code>frame = 55</code>. They win over the price list.
          </span>
          <textarea rows={4} value={fixed} onChange={(e) => setFixed(e.target.value)} />
        </label>
        <label className="field">
          <span>Note (only for us)</span>
          <textarea rows={2} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
        </label>
        <button className="primary">Save</button>
      </form>
      <h4>Delivery addresses</h4>
      {c.addresses.length === 0 ? (
        <p className="muted">None besides the invoice address (the company can add them).</p>
      ) : (
        <ul>
          {c.addresses.map((a) => (
            <li key={a.id}>
              <strong>{a.label || a.name}</strong>: {a.name}, {a.street}, {a.postcode} {a.city}{" "}
              {a.country}
            </li>
          ))}
        </ul>
      )}
      <h4>People who log in</h4>
      <table className="list">
        <tbody>
          {c.users.map((u) => (
            <tr key={u.id} className="static">
              <td>
                {u.name || u.email}
                <br />
                <span className="muted">
                  {u.email} · last login {when(u.last_login)}
                  {!u.has_password &&
                    (u.invited_until
                      ? ` · invited until ${when(u.invited_until)}`
                      : " · no password yet")}
                </span>
              </td>
              <td className="nowrap">
                <button
                  onClick={async () => {
                    const r = await run(() => call<InviteResult>("POST", `users/${u.id}/invite`));
                    if (r) onInvite(r, u.email);
                  }}
                >
                  {u.has_password ? "New password link" : "Send the invitation again"}
                </button>{" "}
                <button
                  onClick={() => run(() => call("PUT", `users/${u.id}`, { active: !u.active }))}
                >
                  {u.active ? "Switch off" : "Switch on"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form
        className="row"
        onSubmit={async (e) => {
          e.preventDefault();
          const r = await run(() => call<InviteResult>("POST", `companies/${c.id}/users`, person));
          if (r) {
            onInvite(r, person.email);
            setPerson({ email: "", name: "", lang: "nl" });
          }
        }}
      >
        <input
          type="email"
          required
          placeholder="e-mail of another person"
          value={person.email}
          onChange={(e) => setPerson({ ...person, email: e.target.value })}
        />
        <input
          placeholder="name"
          value={person.name}
          onChange={(e) => setPerson({ ...person, name: e.target.value })}
        />
        <button>Invite</button>
      </form>
      <h4>Orders</h4>
      {orders === null ? (
        <p className="muted">…</p>
      ) : orders.length === 0 ? (
        <p className="muted">No orders yet.</p>
      ) : (
        <table className="list">
          <tbody>
            {orders.map((o) => (
              <tr key={o.id} className="static">
                <td>
                  B2B {o.id} · {when(o.created)} {o.po ? `· PO ${o.po}` : ""}
                  <br />
                  <span className="muted">
                    {o.lines
                      .map(
                        (l) =>
                          `${l.qty} × ${l.label ?? l.product} ${l.colour} (order ${l.order_id}: ${l.status ?? "?"})`,
                      )
                      .join("; ")}
                  </span>
                </td>
                <td className="nowrap">
                  {eur(o.net_eur)} ex VAT
                  <br />
                  <span className="muted">{eur(o.gross_eur)} incl.</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function SettingsCard({
  s,
  run,
}: {
  s: State;
  run: <R>(f: () => Promise<R>) => Promise<R | undefined>;
}) {
  const [f, setF] = useState(s.settings);
  return (
    <section className="card">
      <h3>B2B settings</h3>
      <form
        className="fields b2b-fields"
        onSubmit={(e) => {
          e.preventDefault();
          run(() => call("PUT", "settings", f));
        }}
      >
        <label className="field">
          <span>Minimum order, € ex VAT (0: none)</span>
          <input
            type="number"
            min={0}
            value={f.min_order_eur}
            onChange={(e) => setF({ ...f, min_order_eur: Number(e.target.value) })}
          />
        </label>
        <label className="field">
          <span>Shipping per order on top, € ex VAT (0: in the price list's extras)</span>
          <input
            type="number"
            min={0}
            value={f.shipping_eur}
            onChange={(e) => setF({ ...f, shipping_eur: Number(e.target.value) })}
          />
        </label>
        <label className="field">
          <span>Payment term of the invoice, days</span>
          <input
            type="number"
            min={0}
            value={f.payment_days}
            onChange={(e) => setF({ ...f, payment_days: Number(e.target.value) })}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={f.auto_produce}
            onChange={(e) => setF({ ...f, auto_produce: e.target.checked })}
          />{" "}
          An order on account goes into production at once (like a paid consumer order)
        </label>
        <label className="check">
          <input type="checkbox" checked={f.online_payment} disabled readOnly /> Online payment
          for business customers (later; every order is on account now)
        </label>
        <button className="primary">Save</button>
      </form>
    </section>
  );
}
