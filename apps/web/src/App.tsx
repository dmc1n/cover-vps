import { Arrangements } from "./Arrangements";
import { Desk } from "./Desk";
import { Questions } from "./Questions";
import { useCallback, useEffect, useState } from "react";
import Configure from "./Configure";
import Guide from "./Guide";
import {
  api,
  approvals,
  auth,
  cm,
  fileUrl,
  Job,
  jobFinished,
  Kind,
  ModelDetail,
  Scalar,
  Step,
  STEP_LABEL,
  User,
} from "./api";
import { AiAdvice } from "./AiAdvice";
import { ModelInfo, Revisions } from "./Catalogue";
import { AllCovers, NewCover } from "./Covers";
import { Heading, Icon, IconButton, IconLink, Info, StatusChip } from "./icons";
import { Tpl } from "./layout";
import { Search } from "./Search";
import { Workshop } from "./Workshop";
import { Matches, Orders, Requests, Website } from "./Admin";
import { B2BCustomers } from "./B2BCustomers";
import { CoverPrice, CoverSummary } from "./CoverPrice";
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
import { LinkChip, Links } from "./Links";
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
  settingsWho,
  isEditor,
  isWorkshop,
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
              <Icon name={s.icon} />
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
        <Search />
        <a
          href="#/guide"
          className={`hdr-icon ${route.section === "guide" ? "on" : ""}`}
          title="The guide"
          aria-label="Guide"
        >
          <Icon name="guide" size={19} />
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
              <Icon name={p.icon} size={16} />
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

/** Which page an address shows; a page this person may not see says so. */
function Page({ route, user }: { route: Route; user: User }) {
  const { section, page, rest, query } = route;
  const sec = SECTIONS.find((s) => s.id === section);
  if (sec) {
    const pg = sec.pages.find((p) => p.id === page);
    if (
      !allowed(sec.who, user, sec.id) ||
      (pg && !allowed(pg.who, user, `${sec.id}/${pg.id}`))
    )
      return <NotAllowed />;
    if (sec.id === "settings" && !allowed(settingsWho(page), user))
      return <NotAllowed />;
  }
  const isAdmin = user.role === "admin";
  // the workshop login: Work, the guide and its account only (ADR-128; the server agrees)
  if (isWorkshop(user) && section === "model") return <NotAllowed />;
  switch (section) {
    case "model":
      return page ? (
        <ModelPage id={page} tab={rest[0] ?? "3d"} sub={rest[1] ?? ""} />
      ) : null;
    case "work":
      if (page === "questions")
        return <Questions selected={Number(rest[0] ?? "") || null} />;
      if (page === "workshop") return <Workshop />;
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
      if (page === "links") return <Links initialQ={query.get("q") ?? ""} />;
      if (page === "products") return <ProductList />;
      return (
        <AllCovers
          cards={query.get("view") === "cards"}
          priceCols={query.get("prices") ?? ""}
        />
      );
    case "shop":
      if (page === "orders")
        return (
          <Tpl
            kind="list"
            title="Orders"
            intro="Orders from the shop and the B2B shop. A paid order (or one on account) waits for production until you press Send to production: then its cover is made and goes to the Desk for a quick approval; the DXF follows that approval. A status change mails the customer."
          >
            <Orders focus={Number(rest[0] ?? "") || null} />
          </Tpl>
        );
      if (page === "requests")
        return (
          <Tpl
            kind="list"
            title="Requests"
            intro="What customers asked: which existing cover fits their sizes (in learning mode a colleague answers first), and the quotes from the configurator. A cover's own requests are also on its Price & shop tab."
          >
            <p className="jump" aria-label="On this page">
              {[
                ["req-matches", "Which cover fits"],
                ["req-quotes", "Quotes from the configurator"],
              ].map(([to, label]) => (
                <button
                  key={to}
                  className="link"
                  onClick={() =>
                    document
                      .getElementById(to)
                      ?.scrollIntoView({ behavior: "smooth" })
                  }
                >
                  {label} ↓
                </button>
              ))}
            </p>
            <Matches />
            <Requests />
          </Tpl>
        );
      if (page === "b2b")
        return (
          <Tpl
            kind="list"
            title="B2B customers"
            intro="Companies, their logins, prices and orders on account. The terms are under Settings → Selling; a cover's own B2B prices also show on its Price & shop tab."
          >
            <B2BCustomers />
          </Tpl>
        );
      return (
        <Tpl
          kind="form"
          title="Website (AI)"
          intro={`Say what should change on the website; the AI changes the draft, you check the preview${isAdmin ? " and publish" : "; an admin publishes"}.`}
        >
          <Website canPublish={isAdmin} />
        </Tpl>
      );
    case "settings":
      return (
        <Tpl kind="form">
          <SettingsArea tab={page} />
        </Tpl>
      );
    case "guide":
      return <Guide loggedIn />;
    case "account":
      return (
        <Tpl kind="form" title="My account">
          <Account user={user} />
        </Tpl>
      );
    default:
      return <NotAllowed />;
  }
}

/** Covers → Product list: the product list (Excel) linked to the drawings (was on the Desk). */
function ProductList() {
  const [done, setDone] = useState(0);
  return (
    <Tpl
      kind="form"
      title="Product list"
      intro={
        <>
          The workshop's product list (Excel): every row is linked to its
          drawing cover; the Desk shows the products on each card.
          {done > 0 && " The list is read; the Desk shows it."}
        </>
      }
    >
      <div className="desk desk-inline">
        <ProductsUpload onDone={() => setDone((n) => n + 1)} />
      </div>
    </Tpl>
  );
}

/** The approval: the Desk's, the only one (owner, 13 Oct 2026, question 83; ADR-128). Who approved
 * which revision and its stamped PDFs while it holds; otherwise where to get it approved. The
 * old "definitive drawing" approval shows as history only. */
function ApprovalCard({
  model,
  onChange,
}: {
  model: ModelDetail;
  onChange: () => void;
}) {
  const { user } = useSession();
  const [msg, setMsg] = useState("");
  if (!model.files.includes("cut.dxf")) return null;
  const ok = model.desk_approved;
  const holds =
    !!ok &&
    (model.desk_status === "approved" || model.desk_status === "produced");
  const old = model.approval;
  const stamped = model.stamped ?? [];
  const ask = async () => {
    setMsg("");
    try {
      const r = await approvals.ask(model.id);
      setMsg(
        r.mailed.length
          ? `On the Desk; asked ${r.mailed.join(", ")} by mail.`
          : "On the Desk, ready for approval (no approver could be mailed).",
      );
      onChange();
    } catch (e) {
      setMsg(String(e).replace(/^Error: /, ""));
    }
  };
  return (
    <section
      className={`card approval ${holds ? "ok" : "none"}`}
      data-testid="desk-approval"
    >
      <div className="approval-state">
        {holds && ok ? (
          <strong>
            <Icon name="st-ok" size={16} />
            Approved on the Desk by {ok.by} on{" "}
            {new Date(ok.time * 1000).toLocaleString()}
            {ok.revision != null && `, revision ${ok.revision}`}
          </strong>
        ) : (
          <strong>
            <Icon name="st-wait" size={16} />
            Not approved yet: the cutting-table DXF waits for the Desk
            {model.desk_status ? ` (now: ${model.desk_status})` : ""}
          </strong>
        )}
      </div>
      <div className="row">
        {holds &&
          stamped.map((f) => (
            <a
              key={f}
              className="btn sm"
              href={`/api/models/${model.id}/approved/${f}`}
              target="_blank"
              rel="noreferrer"
            >
              <Icon name={f === "sizes.pdf" ? "sizes" : "cutting-list"} />
              {f === "sizes.pdf"
                ? "Approved size drawing"
                : "Approved cutting list"}
            </a>
          ))}
        <a
          className="btn sm"
          href={deskHref(model.id)}
          aria-label="Its Desk card"
        >
          <Icon name="desk" />
          Desk card
        </a>
        {!holds && isEditor(user) && model.desk_status !== "ai-checked" && (
          <button
            className="sm"
            onClick={ask}
            title="Send to the Desk for approval"
            aria-label="Send to the Desk for approval"
          >
            <Icon name="send" />
            Send to Desk
          </button>
        )}
        {old && (
          <Info label="About the old approval">
            History: before the Desk became the only approval (ADR-128) the
            definitive drawing was approved by {old.name} on{" "}
            {new Date(old.time * 1000).toLocaleDateString()}
            {old.revision != null && `, revision ${old.revision}`}.
          </Info>
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
      <Heading
        icon="st-check"
        info={
          <>
            Look at the 3D view below and confirm. Complete product: the program
            makes the cover round it. Cover surface only: the surface is the
            cover, and only its pieces are drawn.
          </>
        }
      >
        Check: what is this file?
      </Heading>
      <p>
        The program thinks this is <strong>{KIND_LABEL[guess]}</strong>
        {kind.sure ? "." : ", but it is not sure."}
      </p>
      {kind.reasons && (
        <ul className="muted">
          {kind.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
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
    if (!job || jobFinished(job)) return;
    const t = window.setInterval(async () => {
      const j = await api.job(job.id);
      setJob(j);
      if (jobFinished(j)) {
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
  const approvedNow =
    model.desk_status === "approved" || model.desk_status === "produced";

  return (
    <div className="tpl tpl-object">
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
            <StatusChip
              status={model.grade}
              title={["The cover", ...model.reasons].join("\n")}
            >
              cover: {model.grade}
            </StatusChip>
            <StatusChip status={model.status} title="Catalogue status" />
            {model.no_cover && <span className="badge no-cover">no cover</span>}
            <LinkChip id={id} />
            {model.desk_status && (
              <a href={deskHref(id)} title="Its Desk card">
                <StatusChip status={model.desk_status}>
                  Desk: {model.desk_status}
                </StatusChip>
              </a>
            )}
            <StatusChip
              status={approvedNow ? "approved" : "waiting"}
              title="The Desk's approval, the only one (ADR-128)"
            >
              {approvedNow && model.desk_approved
                ? `approved by ${model.desk_approved.by}`
                : "not approved"}
            </StatusChip>
            {model.dxf_ok === false && (
              <StatusChip
                status="waiting"
                title="Approve the cover on the Desk first"
              >
                <Icon name="lock" size={13} /> DXF
              </StatusChip>
            )}
            {nChanges > 0 && (
              <a
                className="badge"
                href={modelHref(id, "history", "changes")}
                title="Changes since the run before"
              >
                <Icon name="history" size={13} /> {nChanges} change
                {nChanges > 1 ? "s" : ""}
              </a>
            )}
          </div>
        </div>
        <div className="cv-actions">
          <button
            className="primary"
            disabled={!!running || !has("model.json")}
            onClick={() => run(null, {})}
            title="Run again: every step that changed"
            aria-label="Run again"
          >
            <Icon name="run" />
            Run
          </button>
          <IconButton
            icon="edit"
            label="Edit details"
            className={details ? "on" : ""}
            aria-expanded={details}
            onClick={() => setDetails(!details)}
          />
          <IconLink icon="desk" label="Desk card" href={deskHref(id)} />
        </div>
      </section>
      <CoverSummary model={model} />
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
      {job && <JobBar job={job} onJob={setJob} />}
      {model.desk_status === "rejected" && (
        <section className="card attention bad" role="status">
          <Icon name="st-bad" />
          <strong>Rejected at the Desk</strong>
          <a className="btn sm" href={deskHref(id)}>
            Reasons
          </a>
          <Info label="What now">
            The reasons and the pictures are on its Desk card; correct the
            cover, then it goes back to the Desk.
          </Info>
        </section>
      )}
      {model.warnings.length > 0 && (
        <section className="card attention" data-testid="warnings-now">
          <Icon name="st-warn" />
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
        {MODEL_TABS.map(([t, label, icon]) => (
          <a
            key={t}
            href={modelHref(id, t)}
            className={tab === t ? "active" : ""}
            aria-current={tab === t ? "page" : undefined}
          >
            <Icon name={icon} size={16} />
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
            onRain={!isEditor(user) ? undefined : () => run(["rain"], {})}
            rainBusy={!!running && job?.steps.some((s) => s.name === "rain")}
            onDrape={!isEditor(user) ? undefined : () => run(["drape"], {})}
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
          <Reference id={id} canEdit={isEditor(user)} />
        )}
        {tab === "compare" && sub === "ai" && (
          <AiAdvice id={id} files={model.files} stamp={stamp} onJob={setJob} />
        )}
        {tab === "history" && sub === "changes" && <Changes model={model} />}
        {tab === "history" && sub === "revisions" && (
          <Revisions model={model} />
        )}
        {tab === "history" && sub === "log" && <Log model={model} job={job} />}
        {tab === "pieces" && sub === "files" && <Files model={model} />}
        {tab === "price" && <CoverPrice id={id} model={model} />}
      </section>
    </div>
  );
}

/** History → Approval & changes: the approval, the Desk, and what changed since the run before. */
function Changes({ model }: { model: ModelDetail }) {
  const { settings, panels } = realChanges(model);
  const a = model.approval;
  const ok = model.desk_approved;
  const holds =
    model.desk_status === "approved" || model.desk_status === "produced";
  return (
    <>
      <Heading
        icon="approve"
        info={
          <>
            The Desk's approval is the only approval (ADR-128).
            {a &&
              ` Before that, the definitive drawing was approved by ${a.name} on ${new Date(a.time * 1000).toLocaleString()} (history).`}{" "}
            The Desk card holds its history, the pictures and the measured fits.
          </>
        }
      >
        Approval
      </Heading>
      <p>
        {holds && ok
          ? `Approved on the Desk by ${ok.by} on ${new Date(ok.time * 1000).toLocaleString()}${ok.revision != null ? `, revision ${ok.revision}` : ""}.`
          : "Not approved on the Desk yet."}{" "}
        At the Desk:{" "}
        <a href={deskHref(model.id, "history")}>
          {model.desk_status ?? "not on the Desk"}
        </a>
      </p>
      <Heading icon="history">Since the run before</Heading>
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

/** limits.job_timeout_s in words: "4 h", "90 min". */
export function limitText(s: number): string {
  return s >= 3600 && s % 3600 === 0
    ? `${s / 3600} h`
    : `${Math.round(s / 60)} min`;
}

function JobBar({ job, onJob }: { job: Job; onJob: (j: Job) => void }) {
  const trial = Object.keys(job.trial || {}).length;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const again = async () => {
    setBusy(true);
    setErr("");
    try {
      onJob(await api.rerunJob(job.id));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className={`card job ${job.status}`} data-testid="jobbar">
      <span>
        {job.status === "queued" && "Waiting to run…"}
        {job.status === "running" && "Running…"}
        {job.status === "done" && "Last run finished."}
        {job.status === "failed" && `Last run failed: ${job.error ?? ""}`}
        {job.status === "interrupted" &&
          `Interrupted: ${job.error ?? "the server stopped while this ran"}`}
        {trial > 0 &&
          ` (trial with ${trial} changed setting${trial > 1 ? "s" : ""}, not saved)`}
        {(job.status === "queued" || job.status === "running") &&
          !!job.timeout_s && (
            <span
              className="muted"
              title="limits.job_timeout_s: a step that runs longer is stopped and the run fails"
            >
              {" "}
              · each step stops after {limitText(job.timeout_s)}
            </span>
          )}
        {(job.status === "interrupted" || job.status === "failed") && (
          <>
            {" "}
            <button type="button" disabled={busy} onClick={again}>
              {busy ? "Starting…" : "Run again"}
            </button>
          </>
        )}
        {err && <span className="error"> {err}</span>}
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
      <div className="row file-bar">
        {model.dxf_ok === false ? (
          <>
            <StatusChip status="waiting" className="dxf-locked">
              <Icon name="lock" size={13} /> DXF
            </StatusChip>
            <Info label="About the DXF">
              The DXF for the cutting table waits: approve this cover on the{" "}
              <a href={deskHref(model.id)}>Desk</a> first.
            </Info>
          </>
        ) : (
          <a
            className="btn dxf"
            href={fileUrl(model.id, "cut.dxf")}
            download
            title="Download the DXF for the cutting table"
            aria-label="Download the DXF for the cutting table"
          >
            <Icon name="dxf" size={16} />
            DXF
          </a>
        )}
        <a
          className="btn"
          href={fileUrl(model.id, "cutting-list.pdf")}
          target="_blank"
          rel="noreferrer"
          title="Cutting list (PDF)"
        >
          <Icon name="cutting-list" />
          Cutting list
        </a>
        <a
          className="btn"
          href={fileUrl(model.id, "checklist.pdf")}
          title="Check list for the sewn cover (PDF)"
        >
          <Icon name="checklist" />
          Check list
        </a>
      </div>
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
  if (!has)
    return (
      <p className="muted">
        <StatusChip status="draft">Not made yet</StatusChip>
      </p>
    );
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
                <Icon name="download" size={15} /> {f}
              </a>
              {FILE_HELP[f] && <Info label={`About ${f}`}>{FILE_HELP[f]}</Info>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Log({ model, job }: { model: ModelDetail; job: Job | null }) {
  return (
    <>
      <Heading icon="st-warn">Warnings</Heading>
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
          <Heading icon="run">Last run</Heading>
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
