import { useCallback, useEffect, useState } from "react";
import { admin, Invite, MailSettings, User } from "./api";

type Tab = "users" | "mail" | "sessions" | "audit" | "system";
const when = (t: number | null) => (t ? new Date(t * 1000).toLocaleString() : "—");

// The admin page (ADR-047): users and their rights, the mail server, the public address,
// who is logged in, the audit log, and the state of the system.
export function Admin() {
  const [tab, setTab] = useState<Tab>("users");
  return (
    <>
      <section className="card">
        <h2>Admin</h2>
        <p className="muted">Users and their rights, the mail server, logins and the audit log.</p>
      </section>
      <nav className="tabs">
        {(["users", "mail", "sessions", "audit", "system"] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {{ users: "Users", mail: "Mail and address", sessions: "Logged in", audit: "Audit log", system: "System" }[t]}
          </button>
        ))}
      </nav>
      <section className="tab">
        {tab === "users" && <Users />}
        {tab === "mail" && <Mail />}
        {tab === "sessions" && <Sessions />}
        {tab === "audit" && <Audit />}
        {tab === "system" && <System />}
      </section>
    </>
  );
}

function InviteBox({ invite, who }: { invite: Invite; who: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="card invite">
      <strong>Link for {who}</strong> (valid for 3 days, once){invite.mailed ? ": sent by mail." : ":"}
      {invite.mail_problem && <p className="error">The mail did not go: {invite.mail_problem}</p>}
      <div className="row">
        <input readOnly value={invite.link} onFocus={(e) => e.target.select()} className="link" />
        <button
          onClick={() =>
            navigator.clipboard
              .writeText(invite.link)
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
  const [invite, setInvite] = useState<{ invite: Invite; who: string } | null>(null);
  const [form, setForm] = useState({ username: "", name: "", email: "", role: "viewer", can_approve: false });
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
            <th>Password</th>
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
                  onBlur={(e) => e.target.value !== (u.email ?? "") && change(u, { email: e.target.value })}
                />
              </td>
              <td>
                <select value={u.role} onChange={(e) => change(u, { role: e.target.value as User["role"] })}>
                  <option value="admin">admin</option>
                  <option value="editor">editor</option>
                  <option value="viewer">viewer</option>
                </select>
              </td>
              <td>
                <input type="checkbox" checked={u.can_approve} onChange={(e) => change(u, { can_approve: e.target.checked })} />
              </td>
              <td>
                <input type="checkbox" checked={u.active} onChange={(e) => change(u, { active: e.target.checked })} />
              </td>
              <td className="muted">{when(u.last_login)}</td>
              <td>
                <button
                  onClick={async () => {
                    try {
                      setInvite({ invite: await admin.invite(u.id), who: u.name });
                      load();
                    } catch (e) {
                      setError(String(e));
                    }
                  }}
                >
                  {u.has_password ? "Reset" : "New link"}
                </button>
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
            const r = await admin.addUser({ ...form, email: form.email || null, role: form.role as User["role"] });
            setInvite({ invite: r, who: r.user.name });
            setForm({ username: "", name: "", email: "", role: "viewer", can_approve: false });
            load();
          } catch (err) {
            setError(String(err));
          }
        }}
      >
        <h3>New user</h3>
        <div className="row">
          <input placeholder="user name" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <input placeholder="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="e-mail (optional)" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="viewer">viewer</option>
            <option value="editor">editor</option>
            <option value="admin">admin</option>
          </select>
          <label>
            <input type="checkbox" checked={form.can_approve} onChange={(e) => setForm({ ...form, can_approve: e.target.checked })} />{" "}
            may approve
          </label>
          <button className="primary" disabled={!form.username}>
            Add
          </button>
        </div>
        <p className="muted">
          Viewer: looks and downloads. Editor: also uploads, calculates and changes settings. Admin: also this page. “May
          approve”: may approve the definitive drawing of a cover.
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
  useEffect(() => {
    admin
      .mail()
      .then((r) => {
        setM(r.mail);
        setUrl(r.public_url);
      })
      .catch((e) => setMsg(String(e)));
  }, []);
  const field = (k: keyof MailSettings, label: string, type = "text") => (
    <label className="field">
      {label}
      <input
        type={type}
        value={String(m[k] ?? "")}
        onChange={(e) => setM({ ...m, [k]: type === "number" ? Number(e.target.value) : e.target.value })}
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
        <p className="muted">For invitations, password resets, approval requests and alerts.</p>
        <div className="fields">
          {field("host", "Server")}
          {field("port", "Port", "number")}
          <label className="field">
            Security
            <select value={m.security ?? "starttls"} onChange={(e) => setM({ ...m, security: e.target.value })}>
              <option value="starttls">STARTTLS (587)</option>
              <option value="ssl">SSL/TLS (465)</option>
              <option value="none">none</option>
            </select>
          </label>
          {field("username", "User name")}
          <label className="field">
            Password {m.password_set && <span className="muted">(saved; leave empty to keep it)</span>}
            <input type="password" value={m.password ?? ""} onChange={(e) => setM({ ...m, password: e.target.value })} />
          </label>
          {field("sender", "Sender address")}
        </div>
        <div className="row">
          <button className="primary">Save</button>
          <input placeholder="send a test mail to…" value={to} onChange={(e) => setTo(e.target.value)} />
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
          <input value={url} onChange={(e) => setUrl(e.target.value)} className="link" />
          <button className="primary">Save</button>
        </div>
      </form>
    </>
  );
}

function Sessions() {
  const [rows, setRows] = useState<{ username: string; created: number; expires: number; address: string }[]>([]);
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
  const [rows, setRows] = useState<{ time: number; username: string | null; action: string; detail: string | null }[]>([]);
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
          <tr className="static"><td>Engine version</td><td>{String(s.engine)}</td></tr>
          <tr className="static"><td>Models</td><td>{String(s.models)}</td></tr>
          <tr className="static"><td>Disk free</td><td>{String(s.disk_free_gb)} of {String(s.disk_total_gb)} GB</td></tr>
          <tr className="static"><td>Last backup</td><td>{String(s.last_backup ?? "—")}</td></tr>
          <tr className="static"><td>Login required</td><td>{yes(s.login_required)}</td></tr>
          <tr className="static"><td>Mail server set</td><td>{yes(s.mail)}</td></tr>
          <tr className="static"><td>AI key present</td><td>{yes(s.ai)}</td></tr>
        </tbody>
      </table>
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
          The server checks itself every 10 minutes (app, https, services, disk, certificate, backup, updates) and mails
          this address when something is wrong, and again when it is solved.
        </p>
        <div className="row">
          <input value={to} onChange={(e) => setTo(e.target.value)} className="link" />
          <button className="primary">Save</button>
        </div>
        {msg && <p className="muted">{msg}</p>}
        <h3>Last alerts</h3>
        {alerts.length === 0 ? <p className="muted">None.</p> : <pre>{alerts.join("\n")}</pre>}
      </form>
    </>
  );
}
