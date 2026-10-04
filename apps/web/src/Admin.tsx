import { useCallback, useEffect, useState } from "react";
import {
  admin,
  CustomerRequest,
  Invite,
  MailSettings,
  User,
  WebshopSettings,
} from "./api";

type Tab = "users" | "webshop" | "mail" | "sessions" | "audit" | "system";
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
        {(["users", "mail", "sessions", "audit", "system"] as Tab[]).map(
          (t) => (
            <button
              key={t}
              className={tab === t ? "active" : ""}
              onClick={() => setTab(t)}
            >
              {
                {
                  users: "Users",
                  webshop: "Webshop",
                  mail: "Mail and address",
                  sessions: "Logged in",
                  audit: "Audit log",
                  system: "System",
                }[t]
              }
            </button>
          ),
        )}
      </nav>
      <section className="tab">
        {tab === "users" && <Users />}
        {tab === "mail" && <Mail />}
        {tab === "sessions" && <Sessions />}
        {tab === "audit" && <Audit />}
        {tab === "system" && <System />}
        {tab === "webshop" && <Webshop />}
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
