import { useCallback, useEffect, useState } from "react";
import {
  admin,
  CustomerRequest,
  Invite,
  LearningBand,
  MailSettings,
  MatchRequest,
  shopAdmin,
  ShopOrder,
  User,
  WebshopSettings,
} from "./api";
import { B2BCustomers } from "./B2BCustomers";
import { PhotoTest } from "./PhotoTest";
import { Prices } from "./Prices";

type Tab =
  | "users"
  | "orders"
  | "b2b"
  | "matches"
  | "shop"
  | "phototest"
  | "prices"
  | "website"
  | "webshop"
  | "mail"
  | "sessions"
  | "audit"
  | "system";
const when = (t: number | null) =>
  t ? new Date(t * 1000).toLocaleString() : "—";

// The admin page (ADR-047): users and their rights, the mail server, the public address,
// who is logged in, the audit log, and the state of the system.
export function Admin() {
  const [tab, setTab] = useState<Tab>("users");
  return (
    <>
      <section className="card">
        <h2>Admin</h2>
        <p className="muted">
          Users and their rights, the mail server, logins and the audit log.
        </p>
      </section>
      <nav className="tabs">
        {(
          [
            "users",
            "orders",
            "b2b",
            "matches",
            "shop",
            "phototest",
            "prices",
            "website",
            "webshop",
            "mail",
            "sessions",
            "audit",
            "system",
          ] as Tab[]
        ).map((t) => (
          <button
            key={t}
            className={tab === t ? "active" : ""}
            onClick={() => setTab(t)}
          >
            {
              {
                users: "Users",
                orders: "Orders",
                b2b: "B2B customers",
                matches: "Matches",
                shop: "Shop settings",
                phototest: "Photo test",
                prices: "Prices & costing",
                website: "Website (AI)",
                webshop: "Requests",
                mail: "Mail and address",
                sessions: "Logged in",
                audit: "Audit log",
                system: "System",
              }[t]
            }
          </button>
        ))}
      </nav>
      <section className="tab">
        {tab === "users" && <Users />}
        {tab === "mail" && <Mail />}
        {tab === "sessions" && <Sessions />}
        {tab === "audit" && <Audit />}
        {tab === "system" && <System />}
        {tab === "webshop" && <Webshop />}
        {tab === "orders" && <Orders />}
        {tab === "b2b" && <B2BCustomers />}
        {tab === "matches" && <Matches />}
        {tab === "shop" && <ShopSettings />}
        {tab === "phototest" && <PhotoTest />}
        {tab === "prices" && <Prices canEdit />}
        {tab === "website" && <Website />}
      </section>
    </>
  );
}

function InviteBox({ invite, who }: { invite: Invite; who: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="card invite">
      <strong>Invitation for {who}</strong> (the link works once, for{" "}
      {invite.days ?? 7} days)
      {invite.mailed
        ? ": sent by mail. You can also pass the link on yourself:"
        : ": no mail sent, pass the link on yourself:"}
      {invite.mail_problem && (
        <p className="error">The mail did not go: {invite.mail_problem}</p>
      )}
      <div className="row">
        <input
          readOnly
          value={invite.link ?? ""}
          onFocus={(e) => e.target.select()}
          className="link"
        />
        <button
          onClick={() =>
            navigator.clipboard
              .writeText(invite.link ?? "")
              .then(() => setCopied(true))
              .catch(() => setCopied(false))
          }
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

function Users() {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [invite, setInvite] = useState<{ invite: Invite; who: string } | null>(
    null,
  );
  const [form, setForm] = useState({
    username: "",
    name: "",
    email: "",
    role: "viewer",
    can_approve: false,
    send: true,
  });
  const [note, setNote] = useState("");
  const [sentAll, setSentAll] = useState<
    | {
        name: string;
        email: string;
        mailed: boolean;
        mail_problem: string | null;
      }[]
    | null
  >(null);
  const [sure, setSure] = useState<number | null>(null); // the user whose password reset waits for a second click
  const waiting = users.filter((u) => u.active && u.email && !u.has_password);
  const sendInvite = async (u: User) => {
    setError("");
    try {
      setInvite({ invite: await admin.invite(u.id, note), who: u.name });
      setSure(null);
      load();
    } catch (e) {
      setError(String(e));
    }
  };
  const load = useCallback(() => {
    admin
      .users()
      .then((r) => setUsers(r.users))
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);
  const change = async (u: User, changes: Partial<User>) => {
    setError("");
    try {
      await admin.changeUser(u.id, changes);
      load();
    } catch (e) {
      setError(String(e));
    }
  };
  return (
    <>
      {error && <p className="error">{error}</p>}
      <section className="card invitations">
        <h3>Invitations</h3>
        <p className="muted">
          Everyone gets an invitation in English: what Cover Studio is, how to
          log in, their user name and a personal link to choose a password
          (works once, for 7 days). The line below, if you write one, is put at
          the top of the mail.
        </p>
        <textarea
          rows={2}
          maxLength={600}
          placeholder="Optional: e.g. You are invited to the Cover Studio kickoff on Monday 5 October at 10:00."
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <div className="row">
          <button
            className="primary"
            disabled={waiting.length === 0}
            onClick={async () => {
              setError("");
              try {
                setSentAll((await admin.inviteAll(note)).invited);
                load();
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            Invite everyone not yet in ({waiting.length})
          </button>
          <span className="muted">
            Users with an e-mail address and no password yet; use the buttons in
            the list for one person.
          </span>
        </div>
        {sentAll && (
          <ul>
            {sentAll.length === 0 && (
              <li>Nobody was waiting for an invitation.</li>
            )}
            {sentAll.map((r) => (
              <li key={r.email}>
                {r.name} ({r.email}):{" "}
                {r.mailed ? (
                  "sent"
                ) : (
                  <span className="error">not sent: {r.mail_problem}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      {invite && <InviteBox invite={invite.invite} who={invite.who} />}
      <table className="list">
        <thead>
          <tr>
            <th>Name</th>
            <th>User name</th>
            <th>E-mail</th>
            <th>Role</th>
            <th>May approve</th>
            <th>Active</th>
            <th>Last login</th>
            <th>Access</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="static">
              <td>{u.name}</td>
              <td>
                <code>{u.username}</code>
              </td>
              <td>
                <input
                  defaultValue={u.email ?? ""}
                  placeholder="add an e-mail"
                  onBlur={(e) =>
                    e.target.value !== (u.email ?? "") &&
                    change(u, { email: e.target.value })
                  }
                />
              </td>
              <td>
                <select
                  value={u.role}
                  onChange={(e) =>
                    change(u, { role: e.target.value as User["role"] })
                  }
                >
                  <option value="admin">admin</option>
                  <option value="editor">editor</option>
                  <option value="viewer">viewer</option>
                </select>
              </td>
              <td>
                <input
                  type="checkbox"
                  checked={u.can_approve}
                  onChange={(e) => change(u, { can_approve: e.target.checked })}
                />
              </td>
              <td>
                <input
                  type="checkbox"
                  checked={u.active}
                  onChange={(e) => change(u, { active: e.target.checked })}
                />
              </td>
              <td className="muted">{when(u.last_login)}</td>
              <td className="access">
                {u.has_password ? (
                  <>
                    <span className="muted">has a password</span>{" "}
                    {sure === u.id ? (
                      <>
                        <button
                          className="danger"
                          onClick={() => sendInvite(u)}
                        >
                          Yes, reset and send a new link
                        </button>
                        <button className="link" onClick={() => setSure(null)}>
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => setSure(u.id)}
                        title="The password stops working; they get a link to choose a new one"
                      >
                        Reset password
                      </button>
                    )}
                  </>
                ) : (
                  <>
                    <span className="muted">
                      {u.invited_until
                        ? `invited, link until ${new Date(u.invited_until * 1000).toLocaleDateString()}`
                        : "not invited yet"}
                    </span>{" "}
                    <button
                      className={u.invited_until ? "" : "primary"}
                      disabled={!u.active}
                      title={
                        u.email
                          ? `Mail the invitation to ${u.email}`
                          : "No e-mail address: you get a link to pass on yourself"
                      }
                      onClick={() => sendInvite(u)}
                    >
                      {u.invited_until ? "Send again" : "Send invitation"}
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          try {
            const { send, ...u } = form;
            const r = await admin.addUser({
              ...u,
              email: u.email || null,
              role: u.role as User["role"],
              send_invite: send,
              note,
            });
            if (send) setInvite({ invite: r, who: r.user.name });
            setForm({
              username: "",
              name: "",
              email: "",
              role: "viewer",
              can_approve: false,
              send: form.send,
            });
            load();
          } catch (err) {
            setError(String(err));
          }
        }}
      >
        <h3>New user</h3>
        <div className="row">
          <input
            placeholder="user name"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
          <input
            placeholder="name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            placeholder="e-mail (optional)"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <select
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          >
            <option value="viewer">viewer</option>
            <option value="editor">editor</option>
            <option value="admin">admin</option>
          </select>
          <label>
            <input
              type="checkbox"
              checked={form.can_approve}
              onChange={(e) =>
                setForm({ ...form, can_approve: e.target.checked })
              }
            />{" "}
            may approve
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.send}
              onChange={(e) => setForm({ ...form, send: e.target.checked })}
            />{" "}
            send the invitation now
          </label>
          <button className="primary" disabled={!form.username}>
            Add
          </button>
        </div>
        <p className="muted">
          Viewer: looks and downloads. Editor: also uploads, calculates and
          changes settings. Admin: also this page. “May approve”: may approve
          the definitive drawing of a cover.
        </p>
      </form>
    </>
  );
}

function Mail() {
  const [m, setM] = useState<MailSettings & { password?: string }>({});
  const [url, setUrl] = useState("");
  const [to, setTo] = useState("");
  const [msg, setMsg] = useState("");
  const [twoFactor, setTwoFactor] = useState(true);
  useEffect(() => {
    admin
      .mail()
      .then((r) => {
        setM(r.mail);
        setUrl(r.public_url);
        setTwoFactor(r.two_factor);
      })
      .catch((e) => setMsg(String(e)));
  }, []);
  const field = (k: keyof MailSettings, label: string, type = "text") => (
    <label className="field">
      {label}
      <input
        type={type}
        value={String(m[k] ?? "")}
        onChange={(e) =>
          setM({
            ...m,
            [k]: type === "number" ? Number(e.target.value) : e.target.value,
          })
        }
      />
    </label>
  );
  return (
    <>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            setM((await admin.saveMail(m)).mail);
            setMsg("Saved.");
          } catch (err) {
            setMsg(String(err));
          }
        }}
      >
        <h3>Outgoing mail (SMTP)</h3>
        <p className="muted">
          For invitations, password resets, approval requests and alerts.
        </p>
        <div className="fields">
          {field("host", "Server")}
          {field("port", "Port", "number")}
          <label className="field">
            Security
            <select
              value={m.security ?? "starttls"}
              onChange={(e) => setM({ ...m, security: e.target.value })}
            >
              <option value="starttls">STARTTLS (587)</option>
              <option value="ssl">SSL/TLS (465)</option>
              <option value="none">none</option>
            </select>
          </label>
          {field("username", "User name")}
          <label className="field">
            Password{" "}
            {m.password_set && (
              <span className="muted">(saved; leave empty to keep it)</span>
            )}
            <input
              type="password"
              value={m.password ?? ""}
              onChange={(e) => setM({ ...m, password: e.target.value })}
            />
          </label>
          {field("sender", "Sender address")}
        </div>
        <div className="row">
          <button className="primary">Save</button>
          <input
            placeholder="send a test mail to…"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
          <button
            type="button"
            disabled={!to}
            onClick={async () => {
              try {
                await admin.testMail(to);
                setMsg(`Test mail sent to ${to}.`);
              } catch (err) {
                setMsg(String(err));
              }
            }}
          >
            Test
          </button>
        </div>
        {msg && <p className="muted">{msg}</p>}
      </form>
      <section className="card">
        <h3>Login code by mail</h3>
        <p className="muted">
          After the password, a code of 6 digits by mail; a device that passed
          it is remembered for 14 days. Needs the mail server above, and an
          e-mail address for every user.
        </p>
        <label className="check">
          <input
            type="checkbox"
            checked={twoFactor}
            onChange={async (e) => {
              try {
                setTwoFactor(
                  (await admin.twoFactor(e.target.checked)).two_factor,
                );
              } catch (err) {
                setMsg(String(err));
              }
            }}
          />{" "}
          Ask for a login code by mail
        </label>
      </section>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            setUrl((await admin.publicUrl(url)).public_url);
            setMsg("Address saved.");
          } catch (err) {
            setMsg(String(err));
          }
        }}
      >
        <h3>Public address</h3>
        <p className="muted">Used in the links in mails.</p>
        <div className="row">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="link"
          />
          <button className="primary">Save</button>
        </div>
      </form>
    </>
  );
}

function Sessions() {
  const [rows, setRows] = useState<
    { username: string; created: number; expires: number; address: string }[]
  >([]);
  useEffect(() => {
    admin.sessions().then((r) => setRows(r.sessions));
  }, []);
  return (
    <table className="list">
      <thead>
        <tr>
          <th>User</th>
          <th>Since</th>
          <th>Until</th>
          <th>From</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s, i) => (
          <tr key={i} className="static">
            <td>{s.username}</td>
            <td>{when(s.created)}</td>
            <td>{when(s.expires)}</td>
            <td>{s.address}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Audit() {
  const [rows, setRows] = useState<
    {
      time: number;
      username: string | null;
      action: string;
      detail: string | null;
    }[]
  >([]);
  useEffect(() => {
    admin.audit().then((r) => setRows(r.audit));
  }, []);
  return (
    <table className="list">
      <thead>
        <tr>
          <th>When</th>
          <th>Who</th>
          <th>What</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((a, i) => (
          <tr key={i} className="static">
            <td className="nowrap">{when(a.time)}</td>
            <td>{a.username ?? "—"}</td>
            <td>{a.action}</td>
            <td className="muted detail">{a.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function System() {
  const [s, setS] = useState<Record<string, unknown> | null>(null);
  const [to, setTo] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    admin.system().then((r) => {
      setS(r);
      setTo(String(r.alert_email ?? ""));
    });
  }, []);
  if (!s) return <p className="muted">Loading…</p>;
  const yes = (v: unknown) => (v ? "yes" : "no");
  const problems = (s.open_problems as string[]) ?? [];
  const alerts = (s.alerts as string[]) ?? [];
  return (
    <>
      {problems.length > 0 && (
        <section className="card approval stale">
          <strong>Open problems</strong>
          <ul>
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </section>
      )}
      <table className="list facts">
        <tbody>
          <tr className="static">
            <td>Release (live)</td>
            <td>{String(s.release)}</td>
          </tr>
          <tr className="static">
            <td>Engine version</td>
            <td>{String(s.engine)}</td>
          </tr>
          <tr className="static">
            <td>Models</td>
            <td>{String(s.models)}</td>
          </tr>
          <tr className="static">
            <td>Disk free</td>
            <td>
              {String(s.disk_free_gb)} of {String(s.disk_total_gb)} GB
            </td>
          </tr>
          <tr className="static">
            <td>Last backup</td>
            <td>{String(s.last_backup ?? "—")}</td>
          </tr>
          <tr className="static">
            <td>Login required</td>
            <td>{yes(s.login_required)}</td>
          </tr>
          <tr className="static">
            <td>Mail server set</td>
            <td>{yes(s.mail)}</td>
          </tr>
          <tr className="static">
            <td>AI key present</td>
            <td>{yes(s.ai)}</td>
          </tr>
        </tbody>
      </table>
      {((s.releases as string[]) ?? []).length > 0 && (
        <section className="card">
          <h3>Releases</h3>
          <p className="muted">
            The last switches of the app. Back to the release before, on the
            server: <code>scripts/rollback.sh</code> (handbook: server).
          </p>
          <ul>
            {(s.releases as string[]).map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      )}
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            setTo((await admin.alertEmail(to)).alert_email);
            setMsg("Saved.");
          } catch (err) {
            setMsg(String(err));
          }
        }}
      >
        <h3>Alerts</h3>
        <p className="muted">
          The server checks itself every 10 minutes (app, https, services, disk,
          certificate, backup, updates) and mails this address when something is
          wrong, and again when it is solved.
        </p>
        <div className="row">
          <input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="link"
          />
          <button className="primary">Save</button>
        </div>
        {msg && <p className="muted">{msg}</p>}
        <h3>Last alerts</h3>
        {alerts.length === 0 ? (
          <p className="muted">None.</p>
        ) : (
          <pre>{alerts.join("\n")}</pre>
        )}
      </form>
    </>
  );
}

// The webshop (ADR-061): customers' requests from the configurator, the API keys, and which
// webshop addresses may show the configurator in an iframe.
function Webshop() {
  const [reqs, setReqs] = useState<CustomerRequest[]>([]);
  const [set, setSet] = useState<WebshopSettings | null>(null);
  const [origins, setOrigins] = useState("");
  const [to, setTo] = useState("");
  const [keyName, setKeyName] = useState("");
  const [newKey, setNewKey] = useState("");
  const [msg, setMsg] = useState("");
  const load = () => {
    admin
      .requests()
      .then((r) => setReqs(r.requests))
      .catch((e) => setMsg(String(e)));
    admin
      .webshop()
      .then((w) => {
        setSet(w);
        setOrigins(w.embed_origins.join("\n"));
        setTo(w.request_email);
      })
      .catch((e) => setMsg(String(e)));
  };
  useEffect(load, []);
  return (
    <>
      {msg && <p className="muted">{msg}</p>}
      <section className="card">
        <h3>Requests from customers</h3>
        <p className="muted">
          From the configurator (<a href="#/configure">#/configure</a>, also in
          a webshop). The cost price is only shown here.
        </p>
        <table className="list">
          <thead>
            <tr>
              <th>#</th>
              <th>When</th>
              <th>Customer</th>
              <th>What</th>
              <th>Fabric</th>
              <th>Cost</th>
              <th>Price</th>
              <th>From</th>
            </tr>
          </thead>
          <tbody>
            {reqs.length === 0 && (
              <tr className="static">
                <td colSpan={8} className="muted">
                  No requests yet.
                </td>
              </tr>
            )}
            {reqs.map((r) => (
              <tr key={r.id} className="static" title={r.note ?? ""}>
                <td>{r.id}</td>
                <td>{when(r.created)}</td>
                <td>
                  {r.name}
                  <br />
                  <span className="muted">
                    {r.email} {r.phone}
                  </span>
                </td>
                <td>
                  {r.quote?.product} ({r.quote?.shape})<br />
                  <span className="muted">
                    {Object.entries(r.quote?.sizes_cm ?? {})
                      .filter(([, v]) => typeof v === "number")
                      .map(([k, v]) => `${k.replace(/_cm$/, "")} ${v}`)
                      .join(", ")}
                    ; {r.quote?.colour}
                  </span>
                </td>
                <td>
                  {r.quote?.fabric_m2} m² / {r.quote?.roll_m} m
                </td>
                <td>€ {r.quote?.price.cost_eur}</td>
                <td>
                  € {r.quote?.price.sale_eur}
                  {r.quote?.price.placeholder_prices ? " *" : ""}
                </td>
                <td className="muted">{r.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">
          * indicative: the prices in the cost model (quote.*) are still
          placeholders.
        </p>
      </section>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            setSet(
              await admin.setWebshop({
                embed_origins: origins.split(/\s+/).filter(Boolean),
                request_email: to,
              }),
            );
            setMsg("Saved.");
          } catch (err) {
            setMsg(String(err));
          }
        }}
      >
        <h3>Configurator in the webshop</h3>
        <p className="muted">
          Webshop addresses that may show the configurator in an iframe, one per
          line (for example https://hello-suns.com). Embed with:{" "}
          <code>
            &lt;iframe src="https://covers.suns.nu/#/configure"
            style="width:100%;height:900px;border:0"&gt;&lt;/iframe&gt;
          </code>
        </p>
        <textarea
          rows={3}
          value={origins}
          onChange={(e) => setOrigins(e.target.value)}
          placeholder="https://hello-suns.com"
        />
        <label>
          Requests are mailed to{" "}
          <input value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <button className="primary">Save</button>
      </form>
      <section className="card">
        <h3>API keys</h3>
        <p className="muted">
          For a webshop that calls the API from its own server
          (docs/handbook/webshop-api.md). A key is shown once.
        </p>
        <ul>
          {(set?.keys ?? []).map((k) => (
            <li key={k.name}>
              {k.name} <span className="muted">(made {when(k.created)})</span>{" "}
              <button
                className="link"
                onClick={async () => {
                  setSet(await admin.setWebshop({ revoke: k.name }));
                }}
              >
                revoke
              </button>
            </li>
          ))}
        </ul>
        <div className="row">
          <input
            placeholder="name, e.g. hello-suns shop"
            value={keyName}
            onChange={(e) => setKeyName(e.target.value)}
          />
          <button
            disabled={!keyName}
            onClick={async () => {
              const r = await admin.newKey(keyName);
              setNewKey(r.key);
              setKeyName("");
              load();
            }}
          >
            Make a key
          </button>
        </div>
        {newKey && (
          <p>
            New key (copy it now, it is not shown again): <code>{newKey}</code>
          </p>
        )}
      </section>
    </>
  );
}

// ---- the cover webshop (ADR-062) ----------------------------------------------------------------

function Orders() {
  const [orders, setOrders] = useState<ShopOrder[]>([]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [msg, setMsg] = useState("");
  const load = () =>
    shopAdmin
      .orders()
      .then((r) => {
        setOrders(r.orders);
        setStatuses(r.statuses);
      })
      .catch((e) => setMsg(String(e)));
  useEffect(() => {
    load();
  }, []);
  return (
    <section className="card">
      <h3>Orders from the shop</h3>
      <p className="muted">
        The shop: <a href="/shop/">/shop/</a>. A paid order goes into production
        by itself (its pattern, then the drape); a status change mails the
        customer.
      </p>
      {msg && <p className="error">{msg}</p>}
      <table className="list">
        <thead>
          <tr>
            <th>#</th>
            <th>When</th>
            <th>Customer</th>
            <th>Cover</th>
            <th>Total</th>
            <th>Status</th>
            <th>Model</th>
          </tr>
        </thead>
        <tbody>
          {orders.length === 0 && (
            <tr className="static">
              <td colSpan={7} className="muted">
                No orders yet.
              </td>
            </tr>
          )}
          {orders.map((o) => {
            const c = o.data.customer;
            const q = o.data.quote.quote;
            return (
              <tr key={o.id} className="static">
                <td>{o.id}</td>
                <td>{when(o.created)}</td>
                <td>
                  {o.data.b2b && (
                    <span className="b2b-status active">
                      B2B {o.data.b2b.order}
                      {o.data.b2b.po ? ` · PO ${o.data.b2b.po}` : ""}
                    </span>
                  )}{" "}
                  {String(c.name)}
                  <br />
                  <span className="muted">
                    {o.email} · {String(c.postcode)} {String(c.city)}{" "}
                    {String(c.country)}
                  </span>
                </td>
                <td>
                  {q.product}, {q.colour}, support {o.data.quote.input.support}
                  <br />
                  <span className="muted">
                    {Object.entries(q.sizes_cm)
                      .filter(([, v]) => typeof v === "number")
                      .map(([k, v]) => `${k.replace(/_cm$/, "")} ${v}`)
                      .join(", ")}
                  </span>
                </td>
                <td>
                  {o.data.b2b ? `${o.data.b2b.qty} × ` : ""}€{" "}
                  {o.total_eur.toFixed(2)}
                  {o.data.b2b ? " ex VAT, on account" : ""}
                </td>
                <td>
                  <select
                    value={o.status}
                    onChange={async (e) => {
                      await shopAdmin.setStatus(o.id, e.target.value);
                      load();
                    }}
                  >
                    {statuses.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </td>
                <td>
                  {o.model_id ? (
                    <a href={`#/model/${o.model_id}`}>{o.model_id}</a>
                  ) : (
                    <button
                      onClick={async () => {
                        try {
                          await shopAdmin.produce(o.id);
                          load();
                        } catch (e) {
                          setMsg(String(e));
                        }
                      }}
                    >
                      Into production
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

// Every setting the shop needs; what is empty is listed at the top, to fill in later.
function ShopSettings() {
  const [s, setS] = useState<Record<string, unknown> | null>(null);
  const [linkKey, setLinkKey] = useState("");
  const [missing, setMissing] = useState<string[]>([]);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    shopAdmin
      .settings()
      .then((r) => {
        setS(r.settings);
        setMissing(r.missing);
      })
      .catch((e) => setMsg(String(e)));
  }, []);
  if (!s) return <p className="muted">{msg || "Loading…"}</p>;
  const set = (path: string[], value: unknown) => {
    const copy = JSON.parse(JSON.stringify(s));
    let cur = copy;
    for (const k of path.slice(0, -1)) cur = cur[k];
    cur[path[path.length - 1]] = value;
    setS(copy);
  };
  const field = (path: string[], v: unknown): React.ReactNode => {
    const key = path.join(".");
    if (typeof v === "boolean")
      return (
        <label key={key} className="check">
          <input
            type="checkbox"
            checked={v}
            onChange={(e) => set(path, e.target.checked)}
          />{" "}
          {path[path.length - 1]}
        </label>
      );
    if (v !== null && typeof v === "object" && !Array.isArray(v))
      return (
        <fieldset key={key} className="card">
          <legend>{path[path.length - 1]}</legend>
          {Object.entries(v as Record<string, unknown>).map(([k, x]) =>
            field([...path, k], x),
          )}
        </fieldset>
      );
    if (Array.isArray(v))
      return (
        <fieldset key={key} className="card">
          <legend>{path[path.length - 1]}</legend>
          {v.map((x, i) => field([...path, String(i)], x))}
        </fieldset>
      );
    const last = path[path.length - 1];
    const numeric =
      path[0] === "prices" ||
      last === "eur" ||
      last === "days" ||
      last.endsWith("_pct");
    return (
      <label key={key} className="setting">
        {path[path.length - 1]}
        <input
          value={v === null || v === undefined ? "" : String(v)}
          placeholder="to fill in"
          onChange={(e) =>
            set(
              path,
              numeric
                ? e.target.value === ""
                  ? null
                  : Number(e.target.value)
                : e.target.value,
            )
          }
        />
      </label>
    );
  };
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          const r = await shopAdmin.saveSettings(s);
          setS(r.settings);
          setMissing(r.missing);
          setMsg("Saved.");
        } catch (err) {
          setMsg(String(err));
        }
      }}
    >
      <section className="card">
        <h3>Shop settings</h3>
        <p className="muted">
          Everything the shop needs. Empty fields are shown as placeholders in
          the shop; payments work as soon as a Mollie key is filled in (test_…
          for testing, live_… for real). The prices are on the{" "}
          <i>Prices &amp; costing</i> tab.
        </p>
        {missing.length > 0 && (
          <p className="error">Still to fill in: {missing.join(", ")}</p>
        )}
        {msg && <p className="muted">{msg}</p>}
        <button className="primary">Save</button>
      </section>
      <section className="card">
        <h3>The website's key</h3>
        <p className="muted">
          The website on its own domain (Cloudflare) reaches this studio with a
          key (ADR-066). A new key is shown once and stops the old one: put it
          in the Worker with <code>npx wrangler secret put LINK_KEY</code>.
        </p>
        {linkKey && (
          <p>
            <code>{linkKey}</code>
          </p>
        )}
        <button
          type="button"
          onClick={async () => {
            try {
              setLinkKey((await shopAdmin.linkKey()).key);
            } catch (err) {
              setMsg(String(err));
            }
          }}
        >
          New website key
        </button>
      </section>
      {Object.entries(s)
        .filter(([k]) => k !== "prices") // on the Prices & costing tab now (ADR-098)
        .map(([k, v]) => field([k], v))}
      <button className="primary">Save</button>
    </form>
  );
}

// The AI CMS: a colleague says what should change, the AI changes the draft, a preview shows it,
// then it goes live (or not). Every published version is kept.
// Admins see this as a tab; editors on #/website (they draft and preview, an admin publishes).
export function Website({ canPublish = true }: { canPublish?: boolean }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<
    { q: string; a: string; changes: { path: string; value: unknown }[] }[]
  >([]);
  const [state, setState] = useState<{
    history: string[];
    preview: string;
    changed: boolean;
  } | null>(null);
  const [msg, setMsg] = useState("");
  const load = () =>
    shopAdmin
      .cms()
      .then((r) =>
        setState({
          history: r.history,
          preview: r.preview,
          changed: JSON.stringify(r.draft) !== JSON.stringify(r.live),
        }),
      )
      .catch((e) => setMsg(String(e)));
  useEffect(() => {
    load();
  }, []);
  return (
    <>
      <section className="card cms">
        <h3>Change the website with AI</h3>
        <p className="muted">
          Say in plain words what should change (Dutch or English): for example
          "add a FAQ about how long delivery takes: about three weeks" or "make
          the homepage title more inviting". The AI changes the draft in both
          languages; check the preview, then publish. Also on the server:{" "}
          <code>cover-site "…"</code>.
        </p>
        <form
          className="cms-line"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!text.trim()) return;
            setBusy(true);
            setMsg("");
            try {
              const r = await shopAdmin.command(text);
              setLog([{ q: text, a: r.summary, changes: r.changes }, ...log]);
              setText("");
              load();
            } catch (err) {
              setMsg(String(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <span className="prompt">›</span>
          <input
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="What should change on the website?"
          />
          <button className="primary" disabled={busy}>
            {busy ? "Working…" : "Change"}
          </button>
        </form>
        {msg && <p className="error">{msg}</p>}
        {log.map((l, i) => (
          <div key={i} className="cms-entry">
            <div>
              <b>› {l.q}</b>
            </div>
            <div className="muted">{l.a}</div>
            <ul>
              {l.changes.map((c) => (
                <li key={c.path}>
                  <code>{c.path}</code>: {JSON.stringify(c.value).slice(0, 160)}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
      {state && (
        <section className="card">
          <h3>Preview and publish</h3>
          <p>
            {state.changed
              ? "The draft has changes that are not live yet."
              : "The draft is the same as the live site."}{" "}
            <a href={state.preview} target="_blank" rel="noreferrer">
              Open the preview
            </a>
          </p>
          <div className="row">
            <button
              className="primary"
              disabled={!state.changed || !canPublish}
              title={canPublish ? undefined : "An admin publishes the draft"}
              onClick={async () => {
                const r = await shopAdmin.publish();
                setMsg(
                  `Published; the previous version (${r.previous_version}) is kept.`,
                );
                load();
              }}
            >
              Publish
            </button>
            <button
              disabled={!state.changed}
              onClick={async () => {
                await shopAdmin.discard();
                setMsg("The draft is the live site again.");
                load();
              }}
            >
              Discard the draft
            </button>
            <button
              disabled={busy}
              title="DeepSeek fills in every language the shop is set to (Shop settings, languages)"
              onClick={async () => {
                setBusy(true);
                setMsg("Translating…");
                try {
                  const r = await shopAdmin.translate();
                  setMsg(
                    `${r.translated} texts translated into ${r.languages.join(", ")}: check the preview, then publish.`,
                  );
                  load();
                } catch (e) {
                  setMsg(String(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              Translate missing languages
            </button>
          </div>
          {state.history.length > 0 && (
            <p className="muted">
              Earlier versions:{" "}
              {state.history.slice(0, 8).map((v) => (
                <button
                  key={v}
                  className="link"
                  disabled={!canPublish}
                  onClick={async () => {
                    await shopAdmin.restore(v);
                    setMsg(
                      `Version ${v} is in the draft: check the preview, then publish.`,
                    );
                    load();
                  }}
                >
                  {v}
                </button>
              ))}
            </p>
          )}
        </section>
      )}
    </>
  );
}

// ADR-064: which existing cover fits a customer's sizes. In learning mode (shadow) a colleague
// answers every request: the proposal, another cover, or custom; every change is counted below.
function Matches() {
  const [data, setData] = useState<{
    requests: MatchRequest[];
    mode: string;
  } | null>(null);
  const [bands, setBands] = useState<LearningBand[]>([]);
  const [limits, setLimits] = useState("");
  const [fits, setFits] = useState<
    {
      order_id: number;
      score: number;
      comment: string | null;
      photo: string | null;
    }[]
  >([]);
  const [msg, setMsg] = useState("");
  const [other, setOther] = useState<Record<number, string>>({});
  const [notes, setNotes] = useState<Record<number, string>>({});
  const load = useCallback(() => {
    shopAdmin
      .matches()
      .then(setData)
      .catch((e) => setMsg(String(e)));
    shopAdmin
      .learning()
      .then((r) => {
        setBands(r.bands);
        setLimits(
          `Existing cover from ${r.threshold_pct} %, a choice from ${r.choice_pct} %; mode: ${r.mode}.`,
        );
      })
      .catch(() => undefined);
    shopAdmin
      .feedback()
      .then((r) => setFits(r.feedback))
      .catch(() => undefined);
  }, []);
  useEffect(load, [load]);
  if (!data) return <p className="muted">{msg || "Loading…"}</p>;
  const answer = async (r: MatchRequest, chosen: string) => {
    try {
      const a = await shopAdmin.answerMatch(r.id, chosen, notes[r.id] ?? "");
      setMsg(
        `Request ${r.id} answered${a.changed ? " (changed: stored as a lesson)" : ""}; the customer has been mailed.`,
      );
      load();
    } catch (e) {
      setMsg(String(e));
    }
  };
  return (
    <>
      <section className="card">
        <h3>Requests</h3>
        <p className="muted">
          {data.mode === "shadow"
            ? "Learning mode: customers see nothing until you answer. Take the proposal, choose another cover, or custom."
            : "Automatic: customers see the match at once; the requests are kept for learning."}{" "}
          {limits}
        </p>
        {msg && <p>{msg}</p>}
        <table className="list">
          <thead>
            <tr>
              <th>#</th>
              <th>When</th>
              <th>Customer</th>
              <th>Furniture (cm)</th>
              <th>Best matches</th>
              <th>Answer</th>
            </tr>
          </thead>
          <tbody>
            {data.requests.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{when(r.created)}</td>
                <td>
                  {r.name} {r.email && <code>{r.email}</code>} {r.lang}
                </td>
                <td>
                  {r.product}: {r.result.customer_cm.join(" × ")}
                </td>
                <td>
                  {r.result.matches.slice(0, 4).map((m) => (
                    <div key={m.model_id}>
                      <a href={`#/model/${m.model_id}`}>{m.name}</a>{" "}
                      <b>{Math.round(m.score_pct)} %</b>{" "}
                      <span className="muted">
                        (
                        {m.sizes
                          .map(
                            (x) =>
                              `${x.difference_cm > 0 ? "+" : ""}${x.difference_cm}`,
                          )
                          .join(" / ")}
                        )
                      </span>
                    </div>
                  ))}
                  {!r.result.matches.length && (
                    <span className="muted">no cover of this kind</span>
                  )}
                </td>
                <td>
                  {r.status === "answered" ? (
                    <span>
                      {r.chosen} <span className="muted">by {r.chosen_by}</span>
                      {r.changed ? " · changed" : ""}
                    </span>
                  ) : (
                    <div className="row">
                      {r.best_model && r.decision !== "custom" && (
                        <button
                          className="primary"
                          onClick={() => answer(r, r.best_model!)}
                        >
                          Take {Math.round(r.best_pct ?? 0)} %
                        </button>
                      )}
                      <button onClick={() => answer(r, "custom")}>
                        Custom
                      </button>
                      <input
                        placeholder="other: suns-… or drawing-…"
                        value={other[r.id] ?? ""}
                        onChange={(e) =>
                          setOther({ ...other, [r.id]: e.target.value })
                        }
                      />
                      <button
                        disabled={!other[r.id]}
                        onClick={() => answer(r, other[r.id])}
                      >
                        Choose
                      </button>
                      <input
                        placeholder="note for the customer (optional)"
                        value={notes[r.id] ?? ""}
                        onChange={(e) =>
                          setNotes({ ...notes, [r.id]: e.target.value })
                        }
                      />
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h3>What we learn</h3>
        <p className="muted">
          Per match band: how often a colleague changed the proposal, and how
          the delivered covers fit (the customers' answers, 1–5) and came back.
          When a band fits well with few changes, the threshold can move (Shop
          settings, matching).
        </p>
        <table className="list">
          <thead>
            <tr>
              <th>Match</th>
              <th>Requests</th>
              <th>Answered</th>
              <th>Changed</th>
              <th>Custom</th>
              <th>Orders</th>
              <th>Fit (1–5)</th>
              <th>Returns</th>
            </tr>
          </thead>
          <tbody>
            {bands.map((b) => (
              <tr key={b.band}>
                <td>{b.band}</td>
                <td>{b.requests}</td>
                <td>{b.answered_by_staff}</td>
                <td>{b.changed}</td>
                <td>{b.custom_chosen}</td>
                <td>{b.orders}</td>
                <td>
                  {b.fit_avg ?? "—"}{" "}
                  <span className="muted">({b.fit_answers})</span>
                </td>
                <td>{b.returns}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {fits.length > 0 && (
        <section className="card">
          <h3>How the covers fit (customers' answers)</h3>
          <ul>
            {fits.map((f) => (
              <li key={f.order_id}>
                Order {f.order_id}: {"★".repeat(f.score)} {f.comment}{" "}
                {f.photo && (
                  <a
                    href={`/api/admin/feedback/photo/${f.photo}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    photo
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
