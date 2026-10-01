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
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="login-page">
      <form
        className="login-card"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            onDone((await auth.login(username, password)).user);
          } catch (err) {
            setError(String(err).replace(/^Error: /, ""));
          } finally {
            setBusy(false);
          }
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
      <span title={`${user.username} · ${user.role}${user.can_approve ? " · may approve" : ""}`}>{user.name}</span>
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
