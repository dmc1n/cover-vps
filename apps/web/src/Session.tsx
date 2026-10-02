import { createContext, useContext, useState } from "react";
import { auth, User } from "./api";

// Who is logged in, for the whole app. `null` while unknown; the login page when nobody is.
export const SessionContext = createContext<{ user: User | null; loginRequired: boolean }>({
  user: null,
  loginRequired: true,
});

export const useSession = () => useContext(SessionContext);

function Brand() {
  return (
    <div className="login-brand">
      <img src="/brand/s2dio-mark.svg" alt="S2DIO" />
      <span className="times">×</span>
      <img src="/brand/suns.svg" alt="SUNS" />
    </div>
  );
}

export function Login({ onDone }: { onDone: (u: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<{ challenge: string; sentTo: string } | null>(null);
  const [code, setCode] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (f: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await f();
    } catch (err) {
      setError(String(err).replace(/^Error: /, ""));
    } finally {
      setBusy(false);
    }
  };
  if (step)
    return (
      <div className="login-page">
        <form
          className="login-card"
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => onDone((await auth.verify(step.challenge, code, remember)).user));
          }}
        >
          <Brand />
          <h1>Your code</h1>
          <p className="muted">We sent a code of 6 digits to {step.sentTo}. It is valid for 10 minutes.</p>
          <label>
            Code
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              autoFocus
            />
          </label>
          <label className="check">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> Remember this
            device for 14 days
          </label>
          {error && <p className="error">{error}</p>}
          <button className="primary" disabled={busy || code.length !== 6}>
            {busy ? "Checking…" : "Log in"}
          </button>
          <button
            type="button"
            className="link"
            onClick={() => {
              setStep(null);
              setCode("");
            }}
          >
            Back
          </button>
        </form>
      </div>
    );
  return (
    <div className="login-page">
      <form
        className="login-card"
        onSubmit={(e) => {
          e.preventDefault();
          run(async () => {
            const r = await auth.login(username, password);
            if (r.user) onDone(r.user);
            else if (r.challenge) setStep({ challenge: r.challenge, sentTo: r.sent_to ?? "your e-mail" });
          });
        }}
      >
        <Brand />
        <h1>Cover Studio</h1>
        <p className="muted">Log in with your account.</p>
        <label>
          User name
          <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="primary" disabled={busy || !username || !password}>
          {busy ? "Logging in…" : "Log in"}
        </button>
        <p className="muted small">No password yet, or forgotten it? Ask an admin for a new link.</p>
      </form>
    </div>
  );
}

export function Welcome({ token, onDone }: { token: string; onDone: (u: User) => void }) {
  const [who, setWho] = useState<{ username: string; name: string } | null>(null);
  const [checked, setChecked] = useState(false);
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState("");
  if (!checked) {
    setChecked(true);
    auth
      .invite(token)
      .then(setWho)
      .catch((e) => setError(String(e).replace(/^Error: /, "")));
  }
  return (
    <div className="login-page">
      <form
        className="login-card"
        onSubmit={async (e) => {
          e.preventDefault();
          if (password !== again) return setError("the two passwords are not the same");
          try {
            const r = await auth.setPassword(token, password);
            window.location.hash = "#/";
            onDone(r.user);
          } catch (err) {
            setError(String(err).replace(/^Error: /, ""));
          }
        }}
      >
        <Brand />
        <h1>Welcome{who ? `, ${who.name}` : ""}</h1>
        {who && (
          <p className="muted">
            Choose a password for <strong>{who.username}</strong>: at least 12 characters, not your user name.
          </p>
        )}
        <label>
          New password
          <input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label>
          The same again
          <input type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="primary" disabled={!who || password.length < 12}>
          Save and log in
        </button>
      </form>
    </div>
  );
}

export function UserMenu({ user, onLogout }: { user: User; onLogout: () => void }) {
  return (
    <span className="user">
      {user.role === "admin" && (
        <a href="#/admin" className="nav">
          Admin
        </a>
      )}
      <a href="#/account" className="nav" title={`${user.username} · ${user.role}${user.can_approve ? " · may approve" : ""}`}>
        {user.name}
      </a>
      <button
        onClick={async () => {
          await auth.logout().catch(() => undefined);
          onLogout();
        }}
      >
        Log out
      </button>
    </span>
  );
}

export function Account({ user }: { user: User }) {
  const [old, setOld] = useState("");
  const [nw, setNw] = useState("");
  const [again, setAgain] = useState("");
  const [msg, setMsg] = useState("");
  return (
    <section className="card">
      <h2>My account</h2>
      <p className="muted">
        {user.name} · {user.username} · {user.role}
        {user.can_approve ? " · may approve definitive drawings" : ""}
        {user.email ? ` · ${user.email}` : ""}
      </p>
      <form
        className="fields"
        onSubmit={async (e) => {
          e.preventDefault();
          if (nw !== again) return setMsg("the two new passwords are not the same");
          try {
            await auth.changePassword(old, nw);
            setOld("");
            setNw("");
            setAgain("");
            setMsg("Password changed.");
          } catch (err) {
            setMsg(String(err).replace(/^Error: /, ""));
          }
        }}
      >
        <label className="field">
          Current password
          <input type="password" autoComplete="current-password" value={old} onChange={(e) => setOld(e.target.value)} />
        </label>
        <label className="field">
          New password (at least 12 characters)
          <input type="password" autoComplete="new-password" value={nw} onChange={(e) => setNw(e.target.value)} />
        </label>
        <label className="field">
          The same again
          <input type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} />
        </label>
        <div className="row">
          <button className="primary" disabled={!old || nw.length < 12}>
            Change password
          </button>
        </div>
      </form>
      {msg && <p className="muted">{msg}</p>}
    </section>
  );
}
