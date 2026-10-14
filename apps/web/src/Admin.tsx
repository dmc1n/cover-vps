import { Heading, Info, Icon, IconButton, IconLink, StatusChip } from "./icons";
import { useCallback, useEffect, useState } from "react";
import {
  admin,
  AgentApiState,
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
import { deskHref, modelHref } from "./nav";

const when = (t: number | null) =>
  t ? new Date(t * 1000).toLocaleString() : "—";

// The admin parts (ADR-047), now spread over Shop and Settings (ADR-122, nav.ts): users and
// their rights, the mail server, logins and the audit log, the state of the system, orders,
// requests, matches and the website. The old #/admin and its tabs redirect to their places.

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

export function Users() {
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
        <Heading
          icon="mail"
          infoLabel="About Invitations"
          info={
            <>
              Everyone gets an invitation in English: what Cover Studio is, how
              to log in, their user name and a personal link to choose a
              password (works once, for 7 days). The line below, if you write
              one, is put at the top of the mail.
            </>
          }
        >
          Invitations
        </Heading>
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
            title={`Invite everyone not yet in (${waiting.length})`}
            aria-label={`Invite everyone not yet in (${waiting.length})`}
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
            <Icon name="mail" /> Invite all ({waiting.length})
          </button>
          <Info label="About inviting everyone">
            Users with an e-mail address and no password yet; use the buttons in
            the list for one person.
          </Info>
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
                  <option value="workshop">workshop</option>
                </select>
              </td>
              <td>
                <input
                  type="checkbox"
                  checked={u.can_approve}
                  disabled={u.role === "workshop"}
                  title={
                    u.role === "workshop"
                      ? "The workshop role never approves"
                      : "Approves at the Desk"
                  }
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
                    <StatusChip status="ready">has a password</StatusChip>{" "}
                    {sure === u.id ? (
                      <>
                        <button
                          className="danger"
                          title="Yes, reset and send a new link"
                          aria-label="Yes, reset and send a new link"
                          onClick={() => sendInvite(u)}
                        >
                          <Icon name="roll-back" /> Reset
                        </button>
                        <button className="link" onClick={() => setSure(null)}>
                          <Icon name="close" /> Cancel
                        </button>
                      </>
                    ) : (
                      <IconButton
                        icon="roll-back"
                        label="Reset password"
                        onClick={() => setSure(u.id)}
                        title="The password stops working; they get a link to choose a new one"
                      />
                    )}
                  </>
                ) : (
                  <>
                    <span className="muted">
                      {u.invited_until
                        ? `invited, link until ${new Date(u.invited_until * 1000).toLocaleDateString()}`
                        : "not invited yet"}
                    </span>{" "}
                    <IconButton
                      icon="mail"
                      label={u.invited_until ? "Send again" : "Send invitation"}
                      className={u.invited_until ? "" : "primary"}
                      disabled={!u.active}
                      title={
                        u.email
                          ? `Mail the invitation to ${u.email}`
                          : "No e-mail address: you get a link to pass on yourself"
                      }
                      onClick={() => sendInvite(u)}
                    />
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
              can_approve: u.can_approve && u.role !== "workshop",
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
        <Heading
          icon="users"
          infoLabel="About the roles"
          info="Viewer: looks and downloads. Editor: also uploads, calculates and changes settings. Admin: also this page. Workshop: the workshop's own login: Work → Workshop and the Desk read-only, fits, comments and pictures on a Desk card, its own questions and the DXF of approved covers; it never approves and sees no prices or settings. “May approve”: approves at the Desk (the only approval), as the names in desk.approvers do."
        >
          New user
        </Heading>
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
            <option value="workshop">workshop</option>
          </select>
          <label>
            <input
              type="checkbox"
              disabled={form.role === "workshop"}
              checked={form.can_approve && form.role !== "workshop"}
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
            <Icon name="add" /> Add
          </button>
        </div>
      </form>
    </>
  );
}

export function Mail() {
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
        <Heading
          icon="mail"
          infoLabel="About for invitations"
          info={
            <>For invitations, password resets, approval requests and alerts.</>
          }
        >
          Outgoing mail (SMTP)
        </Heading>
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
            <input
              type="password"
              value={m.password ?? ""}
              onChange={(e) => setM({ ...m, password: e.target.value })}
            />
          </label>
          {m.password_set && (
            <Info label="About the saved password">
              Saved; leave empty to keep it.
            </Info>
          )}
          {field("sender", "Sender address")}
        </div>
        <div className="row">
          <button className="primary">
            <Icon name="save" /> Save
          </button>
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
            <Icon name="run" /> Test
          </button>
        </div>
        {msg && <p className="muted">{msg}</p>}
      </form>
      <section className="card">
        <Heading
          icon="keys"
          infoLabel="About Login code by mail"
          info={
            <>
              After the password, a code of 6 digits by mail; a device that
              passed it is remembered for 14 days. Needs the mail server above,
              and an e-mail address for every user.
            </>
          }
        >
          Login code by mail
        </Heading>
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
        <Heading
          icon="website"
          infoLabel="About Public address"
          info={<>Used in the links in mails.</>}
        >
          Public address
        </Heading>
        <div className="row">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="link"
          />
          <button className="primary">
            <Icon name="save" /> Save
          </button>
        </div>
      </form>
    </>
  );
}

export function Sessions() {
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

export function Audit() {
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

export function System() {
  const [s, setS] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    admin.system().then(setS);
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
          <Heading
            icon="publish"
            infoLabel="About Releases"
            info={
              <>
                The last switches of the app. Back to the release before, on the
                server: <code>scripts/rollback.sh</code> (handbook: server).
              </>
            }
          >
            Releases
          </Heading>
          <ul>
            {(s.releases as string[]).map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      )}
      <section className="card">
        <h3>
          <Icon name="st-warn" /> Alerts
        </h3>
        <p className="muted">
          <Icon name="mail" size={15} /> {String(s.alert_email ?? "—")}
        </p>
        <Info label="About server alerts">
          The server checks itself every 10 minutes (app, https, services, disk,
          certificate, backup, updates) and mails{" "}
          <b>{String(s.alert_email ?? "—")}</b> when something is wrong, and
          again when it is solved. The address: Settings →{" "}
          <a href="#/settings/mail">Mail &amp; notifications</a>.
        </Info>
        <h3>
          <Icon name="history" /> Last alerts
        </h3>
        {alerts.length === 0 ? (
          <p className="muted">None.</p>
        ) : (
          <pre>{alerts.join("\n")}</pre>
        )}
      </section>
    </>
  );
}

// The webshop (ADR-061): customers' requests from the configurator (Shop → Requests); which
// webshop addresses may show the configurator and the API keys (Settings → Website & API keys);
// who gets the requests by mail (Settings → Mail & notifications).
export function Requests() {
  const [reqs, setReqs] = useState<CustomerRequest[]>([]);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    admin
      .requests()
      .then((r) => setReqs(r.requests))
      .catch((e) => setMsg(String(e)));
  }, []);
  return (
    <>
      {msg && <p className="muted">{msg}</p>}
      <section className="card">
        <Heading
          id="req-quotes"
          icon="requests"
          infoLabel="About the quotes"
          info={
            <>
              <p>
                From the configurator (<a href="#/configure">#/configure</a>,
                also in a webshop). The cost price is only shown here.
              </p>
              <p>
                * indicative: the prices in the cost model (quote.*) are still
                placeholders.
              </p>
              <p>
                Who gets a request by mail: Settings →{" "}
                <a href="#/settings/mail">Mail &amp; notifications</a>. The
                configurator in a webshop and the API keys: Settings →{" "}
                <a href="#/settings/website">Website &amp; API keys</a>.
              </p>
            </>
          }
        >
          Quotes from the configurator
        </Heading>
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
      </section>
    </>
  );
}

/** The configurator in a webshop (embed origins) and the API keys. */
export function EmbedAndKeys() {
  const [set, setSet] = useState<WebshopSettings | null>(null);
  const [origins, setOrigins] = useState("");
  const [keyName, setKeyName] = useState("");
  const [newKey, setNewKey] = useState("");
  const [msg, setMsg] = useState("");
  const load = () =>
    admin
      .webshop()
      .then((w) => {
        setSet(w);
        setOrigins(w.embed_origins.join("\n"));
      })
      .catch((e) => setMsg(String(e)));
  useEffect(() => {
    load();
  }, []);
  return (
    <>
      {msg && <p className="muted">{msg}</p>}
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            setSet(
              await admin.setWebshop({
                embed_origins: origins.split(/\s+/).filter(Boolean),
              }),
            );
            setMsg("Saved.");
          } catch (err) {
            setMsg(String(err));
          }
        }}
      >
        <Heading
          icon="website"
          infoLabel="About Configurator in the webshop"
          info={
            <>
              Webshop addresses that may show the configurator in an iframe, one
              per line (for example https://hello-suns.com). Embed with:{" "}
              <code>
                &lt;iframe src="https://covers.suns.nu/#/configure"
                style="width:100%;height:900px;border:0"&gt;&lt;/iframe&gt;
              </code>
            </>
          }
        >
          Configurator in the webshop
        </Heading>
        <textarea
          rows={3}
          value={origins}
          onChange={(e) => setOrigins(e.target.value)}
          placeholder="https://hello-suns.com"
        />
        <div className="row">
          <button className="primary">
            <Icon name="save" /> Save
          </button>
        </div>
      </form>
      <section className="card">
        <Heading
          icon="keys"
          infoLabel="About API keys"
          info={
            <>
              For a webshop that calls the API from its own server
              (docs/handbook/webshop-api.md). A key is shown once.
            </>
          }
        >
          API keys
        </Heading>
        <ul>
          {(set?.keys ?? []).map((k) => (
            <li key={k.name}>
              {k.name} <span className="muted">{when(k.created)}</span>{" "}
              <IconButton
                icon="delete"
                label="revoke"
                className="link"
                onClick={async () => {
                  setSet(await admin.setWebshop({ revoke: k.name }));
                }}
              />
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
            title="Make a key"
            disabled={!keyName}
            onClick={async () => {
              const r = await admin.newKey(keyName);
              setNewKey(r.key);
              setKeyName("");
              load();
            }}
          >
            <Icon name="add" /> Create key
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

/** The API for AI agents (ADR-135): partner keys (optionally a B2B company's), the limits and
 * the counts per day (no addresses, no contents). */
export function AgentKeys() {
  const [st, setSt] = useState<AgentApiState | null>(null);
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [newKey, setNewKey] = useState("");
  const [msg, setMsg] = useState("");
  const load = () =>
    admin
      .agentApi()
      .then(setSt)
      .catch((e) => setMsg(String(e)));
  useEffect(() => {
    load();
  }, []);
  const keyName = (who: string) => {
    if (who === "anonymous") return "anonymous";
    const [kind, id] = who.split(":");
    if (kind === "key")
      return st?.keys.find((k) => String(k.id) === id)?.name ?? who;
    if (kind === "b2b")
      return `B2B login: ${st?.companies.find((c) => String(c.id) === id)?.name ?? id}`;
    return who;
  };
  const days = [...new Set((st?.usage ?? []).map((u) => u.day))];
  const callers = [...new Set((st?.usage ?? []).map((u) => u.who))];
  const total = (day: string, who: string) =>
    (st?.usage ?? [])
      .filter((u) => u.day === day && u.who === who)
      .reduce((a, u) => a + u.count, 0);
  return (
    <section className="card">
      <Heading
        icon="keys"
        infoLabel="About the API for AI agents"
        info={
          <>
            /api/v2: AI agents pass the sizes and get the best covers back
            (docs/handbook/agent-api.md). Open without a key within the limits
            below; a partner key gives higher limits and photo recognition. A
            key linked to a B2B customer gets that customer's prices ex VAT. A
            key is shown once. Limits are set in config/defaults.yaml
            (limits.agent_*).
          </>
        }
      >
        API for AI agents: partner keys
      </Heading>
      {msg && <p className="muted">{msg}</p>}
      <p className="muted">
        On the live website:{" "}
        {st?.enabled_on_live ? "on" : "off (the preview only)"} · limits:{" "}
        {st
          ? Object.entries(st.limits)
              .map(([k, v]) => `${k} ${v}`)
              .join(", ")
          : "…"}
      </p>
      <ul>
        {(st?.keys ?? []).map((k) => (
          <li key={k.id}>
            {k.name} <code>{k.shown}</code>
            {k.company ? ` · B2B: ${k.company}` : ""}{" "}
            <span className="muted">{when(k.created)}</span>{" "}
            {k.revoked ? (
              <StatusChip status="revoked">revoked</StatusChip>
            ) : (
              <IconButton
                icon="delete"
                label={`revoke ${k.name}`}
                className="link"
                onClick={async () => setSt(await admin.revokeAgentKey(k.id))}
              />
            )}
          </li>
        ))}
      </ul>
      <div className="row">
        <input
          aria-label="Key name"
          placeholder="partner, e.g. a garden centre's assistant"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <select
          aria-label="B2B customer"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
        >
          <option value="">public prices (no B2B customer)</option>
          {(st?.companies ?? [])
            .filter((c) => c.status === "active")
            .map((c) => (
              <option key={c.id} value={String(c.id)}>
                B2B: {c.name}
              </option>
            ))}
        </select>
        <button
          title="Make a partner key"
          disabled={!name}
          onClick={async () => {
            try {
              const r = await admin.newAgentKey(
                name,
                company ? Number(company) : null,
              );
              setNewKey(r.key);
              setName("");
              load();
            } catch (e) {
              setMsg(String(e));
            }
          }}
        >
          <Icon name="add" /> Create key
        </button>
      </div>
      {newKey && (
        <p>
          New key (copy it now, it is not shown again): <code>{newKey}</code>
        </p>
      )}
      <h3>Requests per day (last 7 days)</h3>
      {days.length === 0 ? (
        <p className="muted">No requests yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Caller</th>
                {days.map((d) => (
                  <th key={d}>{d}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {callers.map((w) => (
                <tr key={w}>
                  <td>{keyName(w)}</td>
                  {days.map((d) => (
                    <td key={d}>{total(d, w) || ""}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ---- the cover webshop (ADR-062) ----------------------------------------------------------------

// An order's statuses in words; "waiting for production": paid (or on account), waiting for
// someone in the studio to send it (owner, 13 Oct 2026, question 86 b; ADR-128).
const ORDER_STATUS_LABEL: Record<string, string> = {
  awaiting_payment: "awaiting payment",
  waiting_production: "waiting for production",
  in_production: "in production",
  on_account: "on account",
};
const RELEASABLE = ["paid", "waiting_production", "on_account"];

/** Shop → Orders; `focus`: an order opened from the search (#/shop/orders/<n>), shown and marked. */
export function Orders({ focus = null }: { focus?: number | null }) {
  const [orders, setOrders] = useState<ShopOrder[]>([]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
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
  useEffect(() => {
    if (focus && orders.some((o) => o.id === focus))
      document
        .getElementById(`order-${focus}`)
        ?.scrollIntoView({ block: "center" });
  }, [focus, orders]);
  return (
    <section className="card">
      <p className="muted">
        The shop: <a href="/shop/">/shop/</a>.
        {focus && !orders.some((o) => o.id === focus) && orders.length > 0 && (
          <Info label="About the requested order">
            Order {focus} is not among the latest 300.
          </Info>
        )}
      </p>
      {msg && <p className="error">{msg}</p>}
      <div className="table-wrap">
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
                <tr
                  key={o.id}
                  id={`order-${o.id}`}
                  className={`static ${o.id === focus ? "focus" : ""}`}
                >
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
                    {q.product}, {q.colour}, support{" "}
                    {o.data.quote.input.support}
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
                      aria-label={`Status of order ${o.id}`}
                      onChange={async (e) => {
                        setMsg("");
                        try {
                          await shopAdmin.setStatus(o.id, e.target.value);
                        } catch (err) {
                          setMsg(String(err).replace(/^Error: /, ""));
                        }
                        load();
                      }}
                    >
                      {statuses.map((s) => (
                        <option key={s} value={s}>
                          {ORDER_STATUS_LABEL[s] ?? s}
                        </option>
                      ))}
                    </select>
                    {o.released_by && (
                      <div className="muted small">
                        sent by {o.released_by}
                        {o.released ? `, ${when(o.released)}` : ""}
                      </div>
                    )}
                  </td>
                  <td>
                    {o.model_id ? (
                      <>
                        <a href={modelHref(o.model_id)}>{o.model_id}</a>
                        <br />
                        <IconLink
                          icon="desk"
                          label="Desk card"
                          className="small"
                          href={deskHref(o.model_id)}
                        />
                      </>
                    ) : RELEASABLE.includes(o.status) ? (
                      <button
                        className="primary"
                        disabled={busy !== null}
                        title="Someone in the studio decides: the cover is made and goes to the Desk for a quick approval; the DXF follows (ADR-128)"
                        onClick={async () => {
                          setBusy(o.id);
                          setMsg("");
                          try {
                            await shopAdmin.produce(o.id);
                            load();
                          } catch (e) {
                            setMsg(String(e).replace(/^Error: /, ""));
                          } finally {
                            setBusy(null);
                          }
                        }}
                      >
                        <Icon name="send-production" />
                        {busy === o.id ? "Sending…" : "Send to production"}
                      </button>
                    ) : (
                      <span className="muted small">not paid yet</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
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
        <Heading
          icon="ai"
          infoLabel="About Change the website with AI"
          info={
            <>
              Say in plain words what should change (Dutch or English): for
              example "add a FAQ about how long delivery takes: about three
              weeks" or "make the homepage title more inviting". The AI changes
              the draft in both languages; check the preview, then publish. Also
              on the server: <code>cover-site "…"</code>.
            </>
          }
        >
          Change the website with AI
        </Heading>
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
          <h3>
            <Icon name="publish" /> Preview and publish
          </h3>
          <p>
            <StatusChip status={state.changed ? "draft" : "published"}>
              {state.changed
                ? "The draft has changes that are not live yet."
                : "The draft is the same as the live site."}
            </StatusChip>{" "}
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
              <Icon name="publish" /> Publish
            </button>
            <button
              title="Discard the draft"
              disabled={!state.changed}
              onClick={async () => {
                await shopAdmin.discard();
                setMsg("The draft is the live site again.");
                load();
              }}
            >
              <Icon name="delete" /> Discard draft
            </button>
            <button
              disabled={busy}
              aria-label="Translate missing languages"
              title="Translate missing languages: DeepSeek fills in every language the shop is set to (Shop settings, languages)"
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
              <Icon name="ai" /> Translate
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
export function Matches() {
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
        <Heading
          id="req-matches"
          icon="covers"
          infoLabel="About match mode"
          info={
            <>
              {data.mode === "shadow"
                ? "Learning mode: customers see nothing until you answer. Take the proposal, choose another cover, or custom."
                : "Automatic: customers see the match at once; the requests are kept for learning."}{" "}
            </>
          }
        >
          Which existing cover fits (match requests)
        </Heading>
        <p className="muted">{limits}</p>
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
                      <a href={modelHref(m.model_id)}>{m.name}</a>{" "}
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
                    <StatusChip status="check">
                      no cover of this kind
                    </StatusChip>
                  )}
                </td>
                <td>
                  <StatusChip status={r.status}>{r.status}</StatusChip>
                  {r.status === "answered" ? (
                    <span>
                      {r.chosen === "custom" ? (
                        <StatusChip status="draft">Custom</StatusChip>
                      ) : (
                        r.chosen
                      )}{" "}
                      <span className="muted">by {r.chosen_by}</span>
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
                      <IconButton
                        icon="approve"
                        label="Choose"
                        disabled={!other[r.id]}
                        onClick={() => answer(r, other[r.id])}
                      />
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
        <Heading
          icon="learning"
          infoLabel="About what we learn"
          info={
            <>
              Per match band: how often a colleague changed the proposal, and
              how the delivered covers fit (the customers' answers, 1–5) and
              came back. When a band fits well with few changes, the threshold
              can move (Shop settings, matching).
            </>
          }
        >
          What we learn
        </Heading>
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
          <h3>
            <Icon name="st-ok" /> How the covers fit (customers' answers)
          </h3>
          <ul>
            {fits.map((f) => (
              <li key={f.order_id}>
                Order {f.order_id}: {"★".repeat(f.score)} {f.comment}{" "}
                {f.photo && (
                  <a
                    aria-label="photo"
                    title="photo"
                    href={`/api/admin/feedback/photo/${f.photo}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Icon name="camera" />
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
