import { Arrangements } from "./Arrangements";
import { Desk } from "./Desk";
import { Questions } from "./Questions";
import { DrawingUpload } from "./DrawingUpload";
import { useCallback, useEffect, useState } from "react";
import Configure from "./Configure";
import Guide from "./Guide";
import {
  api,
  Approval,
  approvals,
  auth,
  cm,
  fileUrl,
  Job,
  Kind,
  ModelBrief,
  ModelDetail,
  Scalar,
  Step,
  STEP_LABEL,
  STEPS,
  User,
} from "./api";
import { AiAdvice } from "./AiAdvice";
import { BatchBar, ModelInfo, Revisions } from "./Catalogue";
import { Gallery } from "./Gallery";
import { QuickSearch } from "./QuickSearch";
import { Matches, Orders, Requests, Website } from "./Admin";
import { B2BCustomers } from "./B2BCustomers";
import { PhotoTest } from "./PhotoTest";
import { Prices } from "./Prices";
import { Reference } from "./Reference";
import {
  Account,
  Login,
  SessionContext,
  useSession,
  UserMenu,
  Welcome,
} from "./Session";
import { Drawing, Learning } from "./Learning";
import { ProductsUpload } from "./DeskProducts";
import { SeamEditor } from "./SeamEditor";
import { Settings } from "./Settings";
import { SettingsArea } from "./SettingsArea";
import { Viewer } from "./Viewer";
import { installUnsavedGuard, mayLeave } from "./unsaved";
import {
  allowed,
  deskHref,
  MODEL_SUBS,
  MODEL_TABS,
  modelHref,
  parse,
  redirect,
  rememberPage,
  Route,
  SECTIONS,
  sectionHome,
  visibleSections,
} from "./nav";

// The studio's pages (ADR-122, nav.ts): five sections in the header, each with its sub-menu;
// every page, a cover's tab and a Desk card's tab in the address; old addresses redirect.

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    let shown = window.location.hash;
    // Back / Forward with unsaved edits asks too; staying puts the address back
    const on = () => {
      const next = window.location.hash;
      if (next === shown) return;
      if (!mayLeave(next)) {
        window.history.pushState(null, "", shown || "#/");
        return;
      }
      shown = next;
      setHash(next);
    };
    window.addEventListener("hashchange", on);
    window.addEventListener("popstate", on);
    return () => {
      window.removeEventListener("hashchange", on);
      window.removeEventListener("popstate", on);
    };
  }, []);
  return hash;
}

/** Open and waiting questions, for the counts in the header (was on the Desk's tabs). */
function useQuestionCount(): { open: number; for_you: number } | null {
  const [n, setN] = useState<{ open: number; for_you: number } | null>(null);
  useEffect(() => {
    let live = true;
    const load = () =>
      fetch("/api/questions/count")
        .then((r) => (r.ok ? r.json() : null))
        .then((c) => live && c && setN(c))
        .catch(() => undefined);
    load();
    window.addEventListener("questions-changed", load);
    return () => {
      live = false;
      window.removeEventListener("questions-changed", load);
    };
  }, []);
  return n;
}

export function App() {
  const hash = useHash();
  const welcome = hash.match(/^#\/welcome\/([A-Za-z0-9_-]+)/);
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined: checking
  const [loginRequired, setLoginRequired] = useState(true);
  useEffect(() => {
    auth
      .me()
      .then((r) => {
        setUser(r.user);
        setLoginRequired(r.auth);
      })
      .catch(() => setUser(null));
    const out = () => setUser(null);
    window.addEventListener("login-needed", out);
    return () => window.removeEventListener("login-needed", out);
  }, []);
  // a menu (details[data-menu]: Show, Simulate, More) closes on a click elsewhere or Escape
  useEffect(() => {
    const close = (keep: EventTarget | null) =>
      document
        .querySelectorAll<HTMLDetailsElement>("details[data-menu][open]")
        .forEach((d) => {
          if (!(keep instanceof Node) || !d.contains(keep)) d.open = false;
        });
    const click = (e: MouseEvent) => close(e.target);
    const key = (e: KeyboardEvent) => e.key === "Escape" && close(null);
    document.addEventListener("click", click);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("click", click);
      document.removeEventListener("keydown", key);
    };
  }, []);
  useEffect(installUnsavedGuard, []);
  // an admin's start page is the section page he was on last
  useEffect(() => {
    if (user && !redirect(hash, user)) rememberPage(hash, user);
  }, [hash, user]);
  // an old or bare address: to its new place, without a step in the browser's history
  const target = user ? redirect(hash, user) : null;
  useEffect(() => {
    if (target && target !== hash) {
      window.history.replaceState(null, "", target);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }
  }, [target, hash]);
  if (welcome) return <Welcome token={welcome[1]} onDone={setUser} />;
  if (hash.startsWith("#/configure")) return <Configure />; // the customers' configurator: no login
  if (hash.startsWith("#/guide") && !user)
    return (
      <div className="guide-page">
        <Guide loggedIn={false} />
      </div>
    );
  if (user === undefined)
    return <div className="login-page muted">Loading…</div>;
  if (user === null) return <Login onDone={setUser} />;
  if (target && target !== hash)
    return <div className="login-page muted">Loading…</div>;
  const route = parse(hash);
  return (
    <SessionContext.Provider value={{ user, loginRequired }}>
      <div className="app">
        <TopBar
          user={user}
          route={route}
          loginRequired={loginRequired}
          onLogout={() => setUser(null)}
        />
        <main className={`m-${route.section}`}>
          <Page route={route} user={user} />
        </main>
      </div>
    </SessionContext.Provider>
  );
}

/** The header (one line: the mark, five sections, search, guide, me) and the sub-menu. */
function TopBar({
  user,
  route,
  loginRequired,
  onLogout,
}: {
  user: User;
  route: Route;
  loginRequired: boolean;
  onLogout: () => void;
}) {
  const questions = useQuestionCount();
  const sections = visibleSections(user);
  const current = sections.find((s) => s.id === route.section);
  const count = (page: string) =>
    page === "questions" && questions && questions.open > 0 ? (
      <span
        className={`nav-count ${questions.for_you ? "mine" : ""}`}
        title={`${questions.open} open, ${questions.for_you} waiting for your answer`}
        aria-label={`${questions.open} open questions`}
      >
        {questions.open}
      </span>
    ) : null;
  return (
    <div className="topbar">
      <header className="hdr">
        <a href="#/" className="brand" title="Cover Studio: your start page">
          <img src="/brand/s2dio-mark.svg" alt="" />
          <span className="title">Cover Studio</span>
        </a>
        <nav className="sections" aria-label="Sections">
          {sections.map((s) => (
            <a
              key={s.id}
              href={sectionHome(s.id, user) ?? "#/"}
              className={s.id === route.section ? "on" : ""}
              aria-current={s.id === route.section ? "true" : undefined}
              title={s.hint}
            >
              {s.label}
              {s.id === "work" && count("questions")}
            </a>
          ))}
        </nav>
        {route.section === "model" && (
          <span className="crumb">
            <a href="#/covers/all">Covers</a> / {route.page}
          </span>
        )}
        <QuickSearch />
        <a
          href="#/guide"
          className={`hdr-icon ${route.section === "guide" ? "on" : ""}`}
          title="The guide"
        >
          Guide
        </a>
        {loginRequired && <UserMenu user={user} onLogout={onLogout} />}
      </header>
      {current && current.pages.length > 0 && (
        <nav className="subnav" aria-label={current.label}>
          {current.pages.map((p) => [
            p.group && (
              <span key={`g-${p.id}`} className="subnav-group">
                {p.group}
              </span>
            ),
            <a
              key={p.id}
              href={`#/${current.id}/${p.id}`}
              className={`${p.id === route.page ? "on" : ""} ${p.sep && !p.group ? "sep" : ""}`}
              aria-current={p.id === route.page ? "page" : undefined}
              title={p.hint}
            >
              {p.label}
              {count(p.id)}
            </a>,
          ])}
        </nav>
      )}
    </div>
  );
}

function NotAllowed() {
  return (
    <section className="card">
      <h2>Not for your account</h2>
      <p className="muted">
        This page is for {""}
        other roles. Ask an admin if you need it;{" "}
        <a href="#/">your start page</a>.
      </p>
    </section>
  );
}

function PageHead({
  title,
  children,
  actions,
}: {
  title: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <h1 className="page-title">{title}</h1>
        {children && <p className="muted">{children}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

/** Which page an address shows; a page this person may not see says so. */
function Page({ route, user }: { route: Route; user: User }) {
  const { section, page, rest, query } = route;
  const sec = SECTIONS.find((s) => s.id === section);
  if (sec) {
    const pg = sec.pages.find((p) => p.id === page);
    if (!allowed(sec.who, user) || (pg && !allowed(pg.who, user)))
      return <NotAllowed />;
  }
  const isAdmin = user.role === "admin";
  switch (section) {
    case "model":
      return page ? (
        <ModelPage id={page} tab={rest[0] ?? "3d"} sub={rest[1] ?? ""} />
      ) : null;
    case "work":
      if (page === "questions")
        return <Questions selected={Number(rest[0] ?? "") || null} />;
      return <Desk selected={rest[0] ?? null} tab={rest[1] ?? "check"} />;
    case "covers":
      if (page === "arrangements")
        return (
          <Arrangements
            openId={rest[0]?.match(/^arr-[a-z0-9-]+$/) ? rest[0] : null}
          />
        );
      if (page === "new") return <NewCover />;
      if (page === "learning") return <Learning />;
      if (page === "products") return <ProductList />;
      return <AllCovers cards={query.get("view") === "cards"} />;
    case "shop":
      if (page === "orders") return <Orders />;
      if (page === "requests")
        return (
          <>
            <PageHead title="Requests">
              Quotes customers asked for in the configurator.
            </PageHead>
            <Requests />
          </>
        );
      if (page === "matches") return <Matches />;
      if (page === "b2b") return <B2BCustomers />;
      if (page === "phototest") return <PhotoTest />;
      return (
        <>
          <PageHead title="Website (AI)">
            Say what should change on the website; the AI changes the draft, you
            check the preview{isAdmin ? " and publish" : "; an admin publishes"}
            .
          </PageHead>
          <Website canPublish={isAdmin} />
        </>
      );
    case "prices":
      return <Prices canEdit={isAdmin} sub={page} />;
    case "settings":
      return <SettingsArea tab={page} />;
    case "guide":
      return <Guide loggedIn />;
    case "account":
      return <Account user={user} />;
    default:
      return <NotAllowed />;
  }
}

/** Covers → All covers: one list, as a table or as cards (was Models and Catalogue). */
function AllCovers({ cards }: { cards: boolean }) {
  const { user } = useSession();
  return (
    <>
      <PageHead
        title="All covers"
        actions={
          <>
            <span className="seg" role="group" aria-label="View">
              <a href="#/covers/all" className={cards ? "" : "on"}>
                Table
              </a>
              <a href="#/covers/all?view=cards" className={cards ? "on" : ""}>
                Cards
              </a>
            </span>
            {user?.role !== "viewer" && (
              <a className="btn primary" href="#/covers/new">
                + New cover
              </a>
            )}
          </>
        }
      >
        Every model and its cover. A row or a card opens the cover.
      </PageHead>
      {cards ? <Gallery /> : <ModelList />}
    </>
  );
}

/** Covers → New cover: from a 3D file or from a drawing (was the top of the Models page). */
function NewCover() {
  return (
    <>
      <PageHead title="New cover">
        From a 3D file of the furniture, or from a drawing (PDF). Pairs of
        drawings and 3D to learn from go to{" "}
        <a href="#/covers/learning">Learning</a>.
      </PageHead>
      <Upload />
      <DrawingUpload />
    </>
  );
}

/** Covers → Product list: the product list (Excel) linked to the drawings (was on the Desk). */
function ProductList() {
  const [done, setDone] = useState(0);
  return (
    <>
      <PageHead title="Product list">
        The workshop's product list (Excel): every row is linked to its drawing
        cover; the Desk shows the products on each card.
        {done > 0 && " The list is read; the Desk shows it."}
      </PageHead>
      <div className="desk desk-inline">
        <ProductsUpload onDone={() => setDone((n) => n + 1)} />
      </div>
    </>
  );
}

function ModelList() {
  const [models, setModels] = useState<ModelBrief[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [grade, setGrade] = useState("");
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const load = useCallback(() => {
    api
      .models()
      .then(setModels)
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);
  const q = query.toLowerCase();
  const shown = (models ?? []).filter(
    (m) =>
      (!q ||
        m.id.includes(q) ||
        m.tags.some((t) => t.toLowerCase().includes(q)) ||
        m.notes.toLowerCase().includes(q)) &&
      (!category ||
        (category === "-"
          ? !m.category
          : (m.category ?? "") === category ||
            (m.category ?? "").startsWith(`${category} ›`))) &&
      (!status || m.status === status) &&
      (!grade || m.grade === grade),
  );
  const cats = [
    ...new Set((models ?? []).map((m) => m.category).filter(Boolean)),
  ].sort() as string[];
  const groups = [...new Set(cats.map((c) => c.split(" › ")[0]))];
  const selected = shown.filter((m) => picked[m.id]);
  return (
    <>
      <h2 className="count-line">
        Models{" "}
        {models && (
          <span className="muted">
            ({models.length}: {models.filter((m) => m.grade === "ready").length}{" "}
            ready, {models.filter((m) => m.grade === "check").length} to check,{" "}
            {models.filter((m) => m.grade === "failed").length} failed)
          </span>
        )}
      </h2>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <input
          className="search"
          placeholder="Search name, tag or note…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">all categories</option>
          {groups.map((g) => (
            <optgroup key={g} label={g}>
              <option value={g}>all {g}</option>
              {cats
                .filter((c) => c.startsWith(`${g} ›`))
                .map((c) => (
                  <option key={c} value={c}>
                    {c.split(" › ")[1]} (
                    {(models ?? []).filter((m) => m.category === c).length})
                  </option>
                ))}
            </optgroup>
          ))}
          <option value="-">no category</option>
        </select>
        <select value={grade} onChange={(e) => setGrade(e.target.value)}>
          <option value="">any cover</option>
          <option value="ready">ready</option>
          <option value="check">to check</option>
          <option value="failed">failed</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">any status</option>
          <option>draft</option>
          <option>checked</option>
          <option>production</option>
        </select>
      </div>
      {selected.length > 0 && <BatchBar selected={selected} onDone={load} />}
      {!models ? (
        <p className="muted">Loading…</p>
      ) : !models.length ? (
        <p className="muted">No models yet: Covers → New cover.</p>
      ) : (
        <table className="list">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  checked={shown.length > 0 && shown.every((m) => picked[m.id])}
                  onChange={(e) =>
                    setPicked(
                      Object.fromEntries(
                        shown.map((m) => [m.id, e.target.checked]),
                      ),
                    )
                  }
                />
              </th>
              <th>Model</th>
              <th>Cover</th>
              <th>Category</th>
              <th>Status</th>
              <th>Size (cm)</th>
              <th>Steps done</th>
              <th>Panels</th>
              <th>Worst stretch</th>
              <th>Warnings</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((m) => (
              <tr
                key={m.id}
                onClick={() => (window.location.hash = modelHref(m.id))}
              >
                <td onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={!!picked[m.id]}
                    onChange={(e) =>
                      setPicked({ ...picked, [m.id]: e.target.checked })
                    }
                  />
                </td>
                <td>
                  <a href={modelHref(m.id)}>{m.id}</a>
                  {m.tags.map((t) => (
                    <span key={t} className="badge">
                      {t}
                    </span>
                  ))}
                </td>
                <td title={m.reasons.join("\n")}>
                  <span className={`badge grade-${m.grade}`}>{m.grade}</span>
                  {m.no_cover && (
                    <span
                      className="badge no-cover"
                      title={
                        m.no_cover_reason || "not in the shop, not on the Desk"
                      }
                    >
                      no cover
                    </span>
                  )}
                </td>
                <td className="nowrap">
                  {m.category ? m.category.split(" › ")[1] : ""}
                </td>
                <td>
                  <span className={`badge status-${m.status}`}>{m.status}</span>
                </td>
                <td>
                  {m.size_mm
                    ? m.size_mm.map((v) => (v / 10).toFixed(0)).join(" × ")
                    : "–"}
                </td>
                <td>
                  <Steps done={m.steps_done} />
                </td>
                <td>{m.panels ?? "–"}</td>
                <td>
                  {m.max_stretch_pct != null
                    ? `${m.max_stretch_pct.toFixed(1)} %`
                    : "–"}
                </td>
                <td>{m.warnings.length || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function Steps({ done }: { done: Step[] }) {
  return (
    <span className="steps">
      {STEPS.map((s) => (
        <span
          key={s}
          className={done.includes(s) ? "step done" : "step"}
          title={STEP_LABEL[s]}
        />
      ))}
    </span>
  );
}

function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [units, setUnits] = useState("");
  const [up, setUp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const send = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const r = await api.upload(file, units, up);
      window.location.hash = modelHref(r.model_id);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  };
  return (
    <section className="card upload">
      <h2>New model</h2>
      <p className="muted">
        STEP, IGES, STL, OBJ, PLY or GLB: the complete product, or only the
        cover surface. After the import the program shows which one it thinks it
        is; you confirm, and the rest runs by itself: cover, seams, patterns and
        the cut pieces.
      </p>
      <div className="row">
        <input
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <label>
          Units{" "}
          <select value={units} onChange={(e) => setUnits(e.target.value)}>
            <option value="">from the file</option>
            <option>mm</option>
            <option>cm</option>
            <option>m</option>
            <option>in</option>
          </select>
        </label>
        <label>
          Up{" "}
          <select value={up} onChange={(e) => setUp(e.target.value)}>
            <option value="">automatic</option>
            <option>z</option>
            <option>y</option>
            <option>x</option>
            <option>-z</option>
            <option>-y</option>
            <option>-x</option>
          </select>
        </label>
        <button className="primary" disabled={!file || busy} onClick={send}>
          {busy ? "Uploading…" : "Upload and run"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

/** The approval of the definitive drawing (ADR-047): who approved which revision, or why not. */
function ApprovalCard({
  model,
  onChange,
}: {
  model: ModelDetail;
  onChange: () => void;
}) {
  const { user } = useSession();
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  if (!model.files.includes("cut.dxf")) return null;
  const a: Approval | null | undefined = model.approval;
  const act = async (f: () => Promise<unknown>, done: string) => {
    setMsg("");
    try {
      await f();
      setMsg(done);
      onChange();
    } catch (e) {
      setMsg(String(e).replace(/^Error: /, ""));
    }
  };
  const date = a ? new Date(a.time * 1000).toLocaleString() : "";
  return (
    <section
      className={`card approval ${a ? (a.valid ? "ok" : "stale") : "none"}`}
    >
      <div className="approval-state">
        {!a && <strong>Definitive drawing: not approved yet</strong>}
        {a && a.valid && (
          <strong>
            Approved by {a.name} on {date}
            {a.revision !== null && `, revision ${a.revision}`}
          </strong>
        )}
        {a && !a.valid && (
          <strong>
            Changed after the approval by {a.name} ({date}): approve again
            before cutting
          </strong>
        )}
        {a?.note && <span className="muted"> · {a.note}</span>}
      </div>
      <div className="row">
        {a?.valid && (
          <>
            <a
              href={`/api/models/${model.id}/approved/sizes.pdf`}
              target="_blank"
              rel="noreferrer"
            >
              Approved size drawing
            </a>
            <a
              href={`/api/models/${model.id}/approved/cutting-list.pdf`}
              target="_blank"
              rel="noreferrer"
            >
              Approved cutting list
            </a>
          </>
        )}
        {user?.can_approve && (!a || !a.valid) && (
          <>
            <input
              placeholder="note (optional)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <button
              className="primary"
              onClick={() =>
                act(() => approvals.approve(model.id, note), "Approved.")
              }
            >
              Approve the definitive drawing
            </button>
          </>
        )}
        {user?.can_approve && a && (
          <button
            onClick={() =>
              act(() => approvals.withdraw(model.id), "Approval withdrawn.")
            }
          >
            Withdraw
          </button>
        )}
        {!user?.can_approve && user?.role !== "viewer" && (!a || !a.valid) && (
          <button
            onClick={() =>
              act(async () => {
                const r = await approvals.ask(model.id);
                setMsg(
                  r.mailed.length
                    ? `Asked ${r.mailed.join(", ")} by mail.`
                    : "No approver could be mailed.",
                );
              }, "")
            }
          >
            Ask for approval
          </button>
        )}
      </div>
      {msg && <p className="muted">{msg}</p>}
    </section>
  );
}

const KIND_LABEL = {
  product: "the complete product (furniture)",
  cover: "only the cover surface",
} as const;

/** After an upload: what the program thinks the file is; the owner confirms (ADR-039). */
function KindCheck({
  kind,
  onConfirm,
}: {
  kind: Kind;
  onConfirm: (k: "product" | "cover") => void;
}) {
  const guess = kind.guess ?? "product";
  const other = guess === "product" ? "cover" : "product";
  return (
    <section className="card kind-check">
      <h3>Check: what is this file?</h3>
      <p>
        The program thinks this is <strong>{KIND_LABEL[guess]}</strong>
        {kind.sure ? "." : ", but it is not sure."} Look at the 3D view below
        and confirm.
      </p>
      {kind.reasons && (
        <ul className="muted">
          {kind.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      <p className="muted">
        Complete product: the program makes the cover round it. Cover surface
        only: the surface is the cover, and only its pieces are drawn.
      </p>
      <div className="row">
        <button className="primary" onClick={() => onConfirm(guess)}>
          Yes, {KIND_LABEL[guess]}
        </button>
        <button onClick={() => onConfirm(other)}>
          No, it is {KIND_LABEL[other]}
        </button>
      </div>
    </section>
  );
}

/** The changes since the run before, without the noise of a new default (`null → value`). */
function realChanges(model: ModelDetail) {
  const settings = (model.diff?.settings ?? []).filter(
    (s) => s.before !== null && s.before !== undefined,
  );
  const panels = model.diff?.panels ?? [];
  return { settings, panels };
}

/** A sub-view row inside a cover's tab (the old tabs, each one click away, in the address). */
function SubTabs({ id, tab, sub }: { id: string; tab: string; sub: string }) {
  const subs = MODEL_SUBS[tab];
  if (!subs) return null;
  return (
    <span className="seg sub-seg" role="group" aria-label="In this tab">
      {subs.map(([k, label]) => (
        <a
          key={k}
          href={modelHref(id, tab, k)}
          className={k === sub ? "on" : ""}
        >
          {label}
        </a>
      ))}
    </span>
  );
}

function ModelPage({
  id,
  tab: tabIn,
  sub: subIn,
}: {
  id: string;
  tab: string;
  sub: string;
}) {
  const { user } = useSession();
  const [model, setModel] = useState<ModelDetail | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [stamp, setStamp] = useState(Date.now());
  const [details, setDetails] = useState(false);
  // the tab is the address's (#/model/<id>/<tab>): another cover opens on its own tab
  const tab = MODEL_TABS.some(([t]) => t === tabIn) ? tabIn : "3d";
  const subs = MODEL_SUBS[tab];
  const sub = subs?.some(([k]) => k === subIn) ? subIn : (subs?.[0][0] ?? "");

  const load = useCallback(() => {
    api
      .model(id)
      .then((m) => {
        setModel(m);
        setJob(m.job ?? null);
      })
      .catch((e) => setError(String(e)));
  }, [id]);
  useEffect(() => {
    setModel(null);
    setDetails(false);
    load();
  }, [load]);

  // follow a running job
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const t = window.setInterval(async () => {
      const j = await api.job(job.id);
      setJob(j);
      if (j.status === "done" || j.status === "failed") {
        setStamp(Date.now());
        load();
      }
    }, 1500);
    return () => window.clearInterval(t);
  }, [job, load]);

  const run = async (steps: Step[] | null, trial: Record<string, Scalar>) => {
    try {
      setJob(await api.run(id, steps, trial));
    } catch (e) {
      setError(String(e));
    }
  };

  if (error && !model) return <p className="error">{error}</p>;
  if (!model) return <p className="muted">Loading…</p>;
  const running = job && (job.status === "queued" || job.status === "running");
  const has = (f: string) => model.files.includes(f);
  const changes = realChanges(model);
  const nChanges = changes.settings.length + changes.panels.length;
  const a = model.approval;

  return (
    <>
      <section className="cv-head">
        {has("cover.png") && (
          <img
            className="cv-thumb"
            src={`${fileUrl(id, "cover.png")}?v=${stamp}`}
            alt=""
          />
        )}
        <div className="cv-title">
          <h1 className="page-title">{model.id}</h1>
          <p className="muted">
            {model.source}
            {model.size_mm &&
              ` · ${model.size_mm.map((v) => (v / 10).toFixed(1)).join(" × ")} cm`}
            {model.cut && ` · hem ${cm(model.cut.hem_length_mm)}`}
            {model.cut?.skirt_height_mm &&
              ` · skirt ${cm(model.cut.skirt_height_mm[0])}`}
            {model.pattern && ` · ${model.pattern.summary.panels} panels`}
            {model.finished?.sheet &&
              ` · about ${(model.finished.sheet.roll_length_mm / 1000).toFixed(2)} m of roll`}
          </p>
          <div className="cv-strip" data-testid="status-strip">
            <span
              className={`badge grade-${model.grade}`}
              title={model.reasons.join("\n")}
            >
              cover: {model.grade}
            </span>
            <span className={`badge status-${model.status}`}>
              {model.status}
            </span>
            {model.no_cover && <span className="badge no-cover">no cover</span>}
            {model.desk_status && (
              <a className="badge" href={deskHref(id)} title="Its Desk card">
                Desk: {model.desk_status}
              </a>
            )}
            <span
              className={`badge ${a ? (a.valid ? "ok" : "warn") : ""}`}
              title="The definitive drawing (approval below)"
            >
              {a
                ? a.valid
                  ? `approved by ${a.name}`
                  : "changed after approval"
                : "not approved"}
            </span>
            {model.dxf_ok === false && (
              <span
                className="badge"
                title="Approve the cover on the Desk first"
              >
                🔒 DXF
              </span>
            )}
            {nChanges > 0 && (
              <a className="badge" href={modelHref(id, "history", "changes")}>
                {nChanges} change{nChanges > 1 ? "s" : ""} since the run before
              </a>
            )}
          </div>
        </div>
        <div className="cv-actions">
          <button
            className="primary"
            disabled={!!running || !has("model.json")}
            onClick={() => run(null, {})}
          >
            Run again
          </button>
          <button
            className={details ? "on" : ""}
            aria-expanded={details}
            onClick={() => setDetails(!details)}
          >
            Edit details
          </button>
          <a className="btn" href={deskHref(id)}>
            Desk card ↗
          </a>
        </div>
      </section>
      {model.kind && !model.kind.confirmed && has("model.json") && !running && (
        <KindCheck
          kind={model.kind}
          onConfirm={async (k) => {
            try {
              const r = await api.setKind(id, k);
              if (r.job) setJob(r.job);
              load();
            } catch (e) {
              setError(String(e));
            }
          }}
        />
      )}
      <ApprovalCard model={model} onChange={load} />
      {details && (
        <ModelInfo
          key={`${model.id}-${model.family}-${model.status}`}
          model={model}
          onSaved={load}
        />
      )}
      {job && <JobBar job={job} />}
      {model.desk_status === "rejected" && (
        <section className="card attention" role="status">
          <strong>Rejected at the Desk.</strong> The reasons and the pictures
          are on its <a href={deskHref(id)}>Desk card</a>; correct the cover,
          then it goes back to the Desk.
        </section>
      )}
      {model.warnings.length > 0 && (
        <section className="card attention" data-testid="warnings-now">
          <strong>
            {model.warnings.length} warning
            {model.warnings.length > 1 ? "s" : ""} now:
          </strong>{" "}
          {model.warnings.slice(0, 2).join(" · ")}
          {model.warnings.length > 2 && " …"}{" "}
          <a href={modelHref(id, "history", "log")}>all, with the run log</a>
        </section>
      )}
      {error && <p className="error">{error}</p>}
      <nav className="tabs" aria-label="Cover">
        {MODEL_TABS.map(([t, label]) => (
          <a
            key={t}
            href={modelHref(id, t)}
            className={tab === t ? "active" : ""}
            aria-current={tab === t ? "page" : undefined}
          >
            {label}
            {t === "history" && model.warnings.length > 0 && (
              <span className="count">{model.warnings.length}</span>
            )}
          </a>
        ))}
      </nav>
      <section className="tab">
        <SubTabs id={id} tab={tab} sub={sub} />
        {tab === "3d" && (
          <Viewer
            id={id}
            files={model.files}
            stamp={stamp}
            onRain={
              user?.role === "viewer" ? undefined : () => run(["rain"], {})
            }
            rainBusy={!!running && job?.steps.some((s) => s.name === "rain")}
            onDrape={
              user?.role === "viewer" ? undefined : () => run(["drape"], {})
            }
            drapeBusy={!!running && job?.steps.some((s) => s.name === "drape")}
          />
        )}
        {tab === "pieces" && sub === "cut" && (
          <CutPieces model={model} stamp={stamp} />
        )}
        {tab === "pieces" && sub === "flat" && (
          <Patterns model={model} stamp={stamp} />
        )}
        {tab === "pieces" && sub === "sizes" && (
          <Pdf id={id} name="sizes.pdf" has={has("sizes.pdf")} stamp={stamp} />
        )}
        {tab === "seams" && <SeamEditor id={id} stamp={stamp} onJob={setJob} />}
        {tab === "adjust" && (
          <Settings id={id} onRun={(steps, trial) => run(steps, trial)} />
        )}
        {tab === "compare" && sub === "drawing" && (
          <Drawing id={id} files={model.files} stamp={stamp} />
        )}
        {tab === "compare" && sub === "reference" && (
          <Reference id={id} canEdit={user?.role !== "viewer"} />
        )}
        {tab === "compare" && sub === "ai" && (
          <AiAdvice id={id} files={model.files} stamp={stamp} onJob={setJob} />
        )}
        {tab === "history" && sub === "changes" && <Changes model={model} />}
        {tab === "history" && sub === "revisions" && (
          <Revisions model={model} />
        )}
        {tab === "history" && sub === "log" && <Log model={model} job={job} />}
        {tab === "files" && <Files model={model} />}
      </section>
    </>
  );
}

/** History → Approval & changes: the approval, the Desk, and what changed since the run before. */
function Changes({ model }: { model: ModelDetail }) {
  const { settings, panels } = realChanges(model);
  const a = model.approval;
  return (
    <>
      <h3>Approval</h3>
      <p>
        {!a && "The definitive drawing is not approved yet."}
        {a &&
          `${a.valid ? "Approved" : "Approved, then changed"} by ${a.name} on ${new Date(a.time * 1000).toLocaleString()}${a.revision !== null ? `, revision ${a.revision}` : ""}.`}{" "}
        At the Desk:{" "}
        <a href={deskHref(model.id, "history")}>
          {model.desk_status ?? "not on the Desk"}
        </a>{" "}
        (its history, the pictures and the measured fits).
      </p>
      <h3>Since the run before</h3>
      {settings.length === 0 && panels.length === 0 ? (
        <p className="muted">
          No setting and no panel changed (new defaults that this cover did not
          have before are not listed).
        </p>
      ) : (
        <section className="card diff">
          {settings.map((s) => (
            <span key={s.key} className="chip">
              {s.key}: {String(s.before)} → {String(s.after)}
            </span>
          ))}
          {panels.length === 0
            ? " no panel changed by more than 1 mm."
            : panels.map((p) => (
                <span key={p.name} className="chip">
                  {p.name}:{" "}
                  {p.change === "size" && p.before_mm && p.after_mm
                    ? `${p.before_mm.map((v) => v.toFixed(0)).join("×")} → ${p.after_mm.map((v) => v.toFixed(0)).join("×")} mm`
                    : p.change}
                </span>
              ))}
        </section>
      )}
    </>
  );
}

function JobBar({ job }: { job: Job }) {
  const trial = Object.keys(job.trial || {}).length;
  return (
    <section className={`card job ${job.status}`}>
      <span>
        {job.status === "queued" && "Waiting to run…"}
        {job.status === "running" && "Running…"}
        {job.status === "done" && "Last run finished."}
        {job.status === "failed" && `Last run failed: ${job.error ?? ""}`}
        {trial > 0 &&
          ` (trial with ${trial} changed setting${trial > 1 ? "s" : ""}, not saved)`}
      </span>
      <span className="steps">
        {job.steps.map((s) => (
          <span key={s.name} className={`jobstep ${s.status}`}>
            {STEP_LABEL[s.name]}
          </span>
        ))}
      </span>
    </section>
  );
}

function Patterns({ model, stamp }: { model: ModelDetail; stamp: number }) {
  const [view, setView] = useState("pattern.svg");
  if (!model.pattern) return <p className="muted">No patterns yet.</p>;
  return (
    <>
      <div className="row">
        {[
          ["pattern.svg", "Flat pieces"],
          [
            "pattern-stretch.svg",
            "Stretch (red stretched, blue squeezed; full colour 2 %)",
          ],
        ].map(([f, l]) => (
          <label key={f}>
            <input
              type="radio"
              checked={view === f}
              onChange={() => setView(f)}
            />{" "}
            {l}
          </label>
        ))}
      </div>
      <div className="svgbox">
        <img src={`${fileUrl(model.id, view)}?v=${stamp}`} alt={view} />
      </div>
      <table className="list">
        <thead>
          <tr>
            <th>Panel</th>
            <th>Flat (narrowest × length)</th>
            <th>Stretch</th>
            <th>Roll</th>
          </tr>
        </thead>
        <tbody>
          {model.pattern.panels.map((p) => (
            <tr key={p.id}>
              <td>
                {p.id} {p.name}
              </td>
              <td>
                {cm(p.flat_width_mm)} × {cm(p.flat_length_mm)}
              </td>
              <td className={p.stretch.quantile_pct > 2 ? "bad" : "ok"}>
                {p.stretch.quantile_pct.toFixed(1)} %
              </td>
              <td className={p.fits_roll ? "ok" : "bad"}>
                {p.fits_roll ? "fits" : "too wide"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function CutPieces({ model, stamp }: { model: ModelDetail; stamp: number }) {
  if (!model.finished) return <p className="muted">No cut pieces yet.</p>;
  return (
    <>
      <p>
        {model.dxf_ok === false ? (
          <span
            className="dxf-locked"
            title="Approve the cover on the Desk first"
          >
            🔒 DXF for the cutting table: approve this cover on the{" "}
            <a href={deskHref(model.id)}>Desk</a> first
          </span>
        ) : (
          <a href={fileUrl(model.id, "cut.dxf")} download>
            Download the DXF for the cutting table
          </a>
        )}{" "}
        ·{" "}
        <a
          href={fileUrl(model.id, "cutting-list.pdf")}
          target="_blank"
          rel="noreferrer"
        >
          cutting list (PDF)
        </a>{" "}
        ·{" "}
        <a href={fileUrl(model.id, "checklist.pdf")}>
          check list for the sewn cover (PDF)
        </a>
      </p>
      <div className="svgbox">
        <img
          src={`${fileUrl(model.id, "cut.svg")}?v=${stamp}`}
          alt="cut pieces"
        />
      </div>
      <table className="list">
        <thead>
          <tr>
            <th>Piece</th>
            <th>Qty</th>
            <th>Size</th>
            <th>Area</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {model.finished.pieces.map((p) => (
            <tr key={p.id}>
              <td>
                {p.id} {p.name}
              </td>
              <td>{p.quantity}</td>
              <td>
                {cm(p.size_mm[0])} × {cm(p.size_mm[1])}
              </td>
              <td>{p.area_m2.toFixed(3)} m²</td>
              <td className="muted">{p.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Pdf({
  id,
  name,
  has,
  stamp,
}: {
  id: string;
  name: string;
  has: boolean;
  stamp: number;
}) {
  if (!has) return <p className="muted">Not made yet.</p>;
  return (
    <iframe
      className="pdf"
      title={name}
      src={`${fileUrl(id, name)}?v=${stamp}`}
    />
  );
}

const FILE_HELP: Record<string, string> = {
  "cut.dxf": "for the cutting table: pieces with allowances",
  "cut.svg": "the cut pieces, to view or print",
  "cutting-list.pdf": "every piece and the fabric needed",
  "checklist.pdf":
    "the workshop's check list: sizes to measure on the sewn cover",
  "sizes.pdf": "size drawing, seam to seam",
  "pattern.dxf": "flat pieces seam to seam (no allowances)",
  "pattern.svg": "flat pieces, to view or print",
  "pattern-stretch.svg": "stretch per piece",
  "model.glb": "the furniture (3D)",
  "hull.glb": "the cover surface (3D)",
  "preview.glb": "furniture and cover, water spots red (3D)",
  "balloons.glb": "the balloons under a table cover (3D)",
  "chairs.glb": "the chair space beside a table, covered too (3D)",
  "panels.glb": "the panels in colour (3D)",
  "cover.json": "this model's own settings",
  "seams.json": "seams placed by hand",
};

function Files({ model }: { model: ModelDetail }) {
  return (
    <table className="list">
      <tbody>
        {model.files.map((f) => (
          <tr key={f}>
            <td>
              <a href={fileUrl(model.id, f)} download>
                {f}
              </a>
            </td>
            <td className="muted">{FILE_HELP[f] ?? ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Log({ model, job }: { model: ModelDetail; job: Job | null }) {
  return (
    <>
      <h3>Warnings</h3>
      {model.warnings.length ? (
        <ul className="warnings">
          {model.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">None.</p>
      )}
      {job && (
        <>
          <h3>Last run</h3>
          {job.steps.map((s) => (
            <details key={s.name} open={s.status === "failed"}>
              <summary>
                {STEP_LABEL[s.name]}: {s.status}
              </summary>
              <pre>{s.log || "(no output)"}</pre>
            </details>
          ))}
        </>
      )}
    </>
  );
}
