// Questions at the Desk (ADR-109): the open questions for the owner and the workshop, answered
// here instead of by mail. A list with filters (status, topic, search), one question at a time
// with its context, the covers it is about, its pictures and every answer; an answer form
// (an option or "anders, namelijk…", a comment, pictures marked in red as with a reject).
// The owner marks an answer final and the question processed, with a note the answerer sees.
// The question texts are Dutch; the studio around them is English.
// Keys: j / k next / previous question, 1–5 choose an option, 0 "anders", Ctrl+Enter send.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PictureTray, uploadPictures, type Pending } from "./DeskPictures";
import "./desk.css";

interface ModelRef {
  id: string;
  code: string;
  picture: boolean;
}
interface Answer {
  id: number;
  username: string;
  name: string;
  choice: number | null;
  other: string;
  comment: string;
  pictures: string[];
  time: number;
}
export interface Question {
  id: number;
  key: string | null;
  title: string;
  text: string;
  topic: string;
  context: string;
  models: ModelRef[];
  pictures: { name: string; caption: string }[];
  options: string[];
  other_allowed: boolean;
  status: "open" | "answered" | "processed";
  final_answer: number | null;
  final_by: string | null;
  processed: { note: string; by: string; time: number } | null;
  created: number;
  answers: Answer[];
  can_answer: boolean;
  you_answered: boolean;
  your_answer: number | null;
}
interface Listing {
  items: Question[];
  counts: Record<string, number>;
  for_you: number;
  topics: string[];
  is_owner: boolean;
  pictures_max: number;
}

const OTHER = -1;
const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  answered: "Answered",
  processed: "Processed",
};
const FILTERS = ["open", "answered", "processed", "all"] as const;
const letter = (i: number) => String.fromCharCode(97 + i);
const picUrl = (qid: number, name: string) =>
  `/api/questions/${qid}/pictures/${encodeURIComponent(name)}`;
const when = (t?: number | null) =>
  t
    ? new Date(t * 1000).toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";

async function call<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401) window.dispatchEvent(new Event("login-needed"));
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail ?? `error ${r.status}`);
  return data as T;
}

const isTyping = (t: EventTarget | null) => {
  const el = t as HTMLElement | null;
  return (
    !!el &&
    (["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) ||
      el.isContentEditable)
  );
};

/** "Covers | Questions (n)" at the top of the Desk; the badge counts the open questions. */
export function DeskTabs({ active }: { active: "covers" | "questions" }) {
  const [n, setN] = useState<{ open: number; for_you: number } | null>(null);
  useEffect(() => {
    let live = true;
    const load = () =>
      call<{ open: number; for_you: number }>("/api/questions/count")
        .then((c) => live && setN(c))
        .catch(() => undefined);
    load();
    window.addEventListener("questions-changed", load);
    return () => {
      live = false;
      window.removeEventListener("questions-changed", load);
    };
  }, []);
  return (
    <nav className="d-tabs" aria-label="Desk">
      <a
        href="#/desk"
        className={active === "covers" ? "on" : ""}
        aria-current={active === "covers" ? "page" : undefined}
      >
        Covers
      </a>
      <a
        href="#/questions"
        className={active === "questions" ? "on" : ""}
        aria-current={active === "questions" ? "page" : undefined}
      >
        Questions
        {n && n.open > 0 && (
          <span
            className={`d-badge ${n.for_you ? "mine" : ""}`}
            title={`${n.open} open, ${n.for_you} waiting for your answer`}
            aria-label={`${n.open} open questions`}
          >
            {n.open}
          </span>
        )}
      </a>
    </nav>
  );
}

export function Questions({ selected }: { selected: number | null }) {
  const [list, setList] = useState<Listing | null>(null);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState<(typeof FILTERS)[number]>("open");
  const [topic, setTopic] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const load = useCallback(
    () =>
      call<Listing>("/api/questions")
        .then(setList)
        .catch((e) => setErr(String(e.message ?? e))),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);

  const items = useMemo(() => {
    const s = search.trim().toLowerCase();
    return (list?.items ?? []).filter((q) => {
      if (status !== "all" && q.status !== status) return false;
      if (topic && q.topic !== topic) return false;
      if (s) {
        const text = `${q.title} ${q.text} ${q.models.map((m) => m.code).join(" ")}`;
        if (!text.toLowerCase().includes(s)) return false;
      }
      return true;
    });
  }, [list, status, topic, search]);
  const current = list?.items.find((q) => q.id === selected) ?? null;
  const open = (id: number) => (window.location.hash = `#/questions/${id}`);
  const idx = items.findIndex((q) => q.id === selected);
  // one column (a tablet): a chosen question comes into view below the list
  useEffect(() => {
    if (selected == null || window.innerWidth > 1100) return;
    const t = setTimeout(
      () =>
        document
          .querySelector(".q-card")
          ?.scrollIntoView({ block: "start", behavior: "smooth" }),
      50,
    );
    return () => clearTimeout(t);
  }, [selected]);

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "j" && items.length)
        open(items[Math.min(idx + 1, items.length - 1)].id);
      else if (e.key === "k" && items.length)
        open(items[Math.max(idx - 1, 0)].id);
      else if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [items, idx]);
  useEffect(() => {
    if (selected == null && items.length && window.innerWidth > 1100)
      open(items[0].id);
  }, [selected, items]);

  const changed = (q: Question) => {
    setList((l) =>
      l ? { ...l, items: l.items.map((x) => (x.id === q.id ? q : x)) } : l,
    );
    window.dispatchEvent(new Event("questions-changed"));
  };

  if (err)
    return (
      <div className="desk">
        <DeskTabs active="questions" />
        <p className="d-err">{err}</p>
      </div>
    );
  if (!list)
    return (
      <div className="desk">
        <DeskTabs active="questions" />
        <p className="d-muted">Loading the questions…</p>
      </div>
    );
  const c = list.counts;
  return (
    <div className="desk">
      <DeskTabs active="questions" />
      <section className="d-top">
        <div className="d-title">
          <h1>Questions</h1>
          <p>
            Questions for the owner and the workshop. Choose an answer, add a
            comment or a picture; Claude processes the answers every day at
            18:00. <kbd>j</kbd>
            <kbd>k</kbd> move · <kbd>1</kbd>–<kbd>5</kbd> choose · <kbd>0</kbd>{" "}
            anders · <kbd>Ctrl</kbd>+<kbd>Enter</kbd> send · <kbd>/</kbd> search
          </p>
        </div>
        <div className="d-kpis">
          <Tile label="Open" value={c.open ?? 0} accent />
          <Tile label="Waiting for you" value={list.for_you} />
          <Tile label="Answered" value={c.answered ?? 0} />
          <Tile label="Processed" value={c.processed ?? 0} />
        </div>
      </section>

      <div className="d-body">
        <aside className="d-queue q-queue">
          <div className="d-filters">
            <input
              ref={searchRef}
              className="d-search"
              type="search"
              placeholder="Search questions or covers"
              aria-label="Search questions or covers"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <div className="d-seg-ctl" role="group" aria-label="Status">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  className={status === f ? "on" : ""}
                  aria-pressed={status === f}
                  onClick={() => setStatus(f)}
                >
                  {f === "all" ? "All" : STATUS_LABEL[f]}
                </button>
              ))}
            </div>
            <div className="d-chips" role="group" aria-label="Topic">
              {list.topics
                .filter((t) => list.items.some((q) => q.topic === t))
                .map((t) => (
                  <button
                    key={t}
                    className={topic === t ? "on" : ""}
                    aria-pressed={topic === t}
                    onClick={() => setTopic(topic === t ? null : t)}
                  >
                    {t}
                  </button>
                ))}
            </div>
          </div>
          <ul className="d-list q-list">
            {items.map((q) => (
              <li
                key={q.id}
                className={q.id === selected ? "sel" : ""}
                onClick={() => open(q.id)}
              >
                <a
                  className="q-row"
                  href={`#/questions/${q.id}`}
                  aria-current={q.id === selected ? "true" : undefined}
                >
                  <span className="d-row-top">
                    <strong lang="nl">{q.title}</strong>
                    {q.status === "open" && q.can_answer && !q.you_answered && (
                      <span className="q-dot" title="Waiting for your answer" />
                    )}
                  </span>
                  <span className="d-row-sub">
                    <span className={`d-pill q-${q.status}`}>
                      {STATUS_LABEL[q.status]}
                    </span>
                    <span>{q.topic}</span>
                    {q.answers.length > 0 && (
                      <span>
                        {q.answers.length} answer
                        {q.answers.length > 1 ? "s" : ""}
                      </span>
                    )}
                    {q.models.length > 0 && (
                      <span>
                        {q.models.length === 1
                          ? q.models[0].code
                          : `${q.models.length} covers`}
                      </span>
                    )}
                  </span>
                </a>
              </li>
            ))}
            {!items.length && <li className="d-empty">Nothing here.</li>}
          </ul>
        </aside>
        <section className="d-card-host">
          {current ? (
            <QuestionCard
              key={current.id}
              q={current}
              isOwner={list.is_owner}
              picturesMax={list.pictures_max}
              onChanged={changed}
            />
          ) : (
            <div className="d-placeholder">Pick a question from the list.</div>
          )}
        </section>
      </div>
    </div>
  );
}

function Tile({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: boolean;
}) {
  return (
    <div className={`d-kpi ${accent ? "accent" : ""}`}>
      <span className="d-kpi-label">{label}</span>
      <span className="d-kpi-value">{value}</span>
    </div>
  );
}

function chosenText(q: Question, a: Answer): string {
  if (a.choice === OTHER) return `Anders: ${a.other}`;
  if (a.choice != null && a.choice >= 0 && a.choice < q.options.length)
    return `${letter(a.choice)}) ${q.options[a.choice]}`;
  return "";
}

function QuestionCard({
  q,
  isOwner,
  picturesMax,
  onChanged,
}: {
  q: Question;
  isOwner: boolean;
  picturesMax: number;
  onChanged: (q: Question) => void;
}) {
  // your earlier answer, to change it
  const mine = q.answers.find((a) => a.id === q.your_answer);
  const [choice, setChoice] = useState<number | null>(mine?.choice ?? null);
  const [other, setOther] = useState(mine?.other ?? "");
  const [comment, setComment] = useState(mine?.comment ?? "");
  const [pending, setPending] = useState<Pending[]>([]);
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState("");
  const [zoom, setZoom] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [showContext, setShowContext] = useState(q.context.length < 400);
  const formRef = useRef<HTMLFormElement>(null);
  const otherRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!zoom) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setZoom(null);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [zoom]);

  const send = async () => {
    if (sending) return;
    if (choice == null && !comment.trim() && !pending.length) {
      setMsg("Choose an option or write a comment.");
      return;
    }
    if (choice === OTHER && !other.trim()) {
      setMsg("Anders, namelijk…: write what.");
      otherRef.current?.focus();
      return;
    }
    setSending(true);
    setMsg("");
    try {
      let names: string[] = [];
      const toSend = pending.filter((p) => !p.name);
      if (toSend.length) {
        const got = await uploadPictures(
          String(q.id),
          toSend,
          `/api/questions/${q.id}/pictures`,
        );
        const map = new Map(toSend.map((p, i) => [p.key, got[i]]));
        const named = pending.map((p) =>
          p.name ? p : { ...p, name: map.get(p.key) },
        );
        setPending(named); // uploaded once: a second try reuses them
        names = named.map((p) => p.name!).filter(Boolean);
      } else names = pending.map((p) => p.name!).filter(Boolean);
      const out = await call<Question>(`/api/questions/${q.id}/answer`, {
        choice,
        other: choice === OTHER ? other : "",
        comment,
        pictures: names,
      });
      pending.forEach((p) => URL.revokeObjectURL(p.url));
      setPending([]);
      setMsg("Thank you, your answer is saved.");
      onChanged(out);
    } catch (e) {
      setMsg(String((e as Error).message ?? e));
    } finally {
      setSending(false);
    }
  };

  const owner = async (path: string, body: unknown, done: string) => {
    try {
      const out = await call<Question>(`/api/questions/${q.id}/${path}`, body);
      setMsg(done);
      setNote("");
      onChanged(out);
    } catch (e) {
      setMsg(String((e as Error).message ?? e));
    }
  };

  // 1–5 choose an option, 0 "anders", Ctrl+Enter sends
  useEffect(() => {
    if (!q.can_answer) return;
    const on = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        if (formRef.current?.contains(document.activeElement as Node)) {
          e.preventDefault();
          send();
        }
        return;
      }
      if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
      if (document.querySelector(".d-marker")) return;
      const n = Number(e.key);
      if (e.key >= "1" && e.key <= "9" && n <= q.options.length) {
        setChoice(n - 1);
        formRef.current?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "0" && q.other_allowed) {
        setChoice(OTHER);
        formRef.current?.scrollIntoView({ block: "nearest" });
        setTimeout(() => otherRef.current?.focus(), 0);
      }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  });

  const sources = [
    ...q.pictures.map((p, i) => ({
      label: `Mark picture ${i + 1}`,
      url: picUrl(q.id, p.name),
    })),
    ...q.models
      .filter((m) => m.picture)
      .slice(0, 4)
      .map((m) => ({
        label: `Mark ${m.code}`,
        url: `/api/models/${encodeURIComponent(m.id)}/files/cover.png`,
      })),
  ];

  return (
    <article className="d-card q-card" aria-labelledby={`q-${q.id}-title`}>
      <div className="d-card-head">
        <div>
          <h2 id={`q-${q.id}-title`} lang="nl">
            {q.title}
          </h2>
          <span className="d-id">
            #{q.id} · {q.topic} · asked {when(q.created)}
          </span>
        </div>
        <div className="d-head-right">
          <span className={`d-pill q-${q.status}`}>
            {STATUS_LABEL[q.status]}
          </span>
        </div>
      </div>

      <div className="q-body">
        <p className="q-text" lang="nl">
          {q.text}
        </p>

        {q.processed && (
          <div className="q-note-done" role="status">
            <strong>Processed</strong> by {q.processed.by},{" "}
            {when(q.processed.time)}: <span lang="nl">{q.processed.note}</span>
          </div>
        )}

        {q.models.length > 0 && (
          <section className="q-section">
            <h3>Covers</h3>
            <ul className="q-covers">
              {q.models.map((m) => (
                <li key={m.id}>
                  <a
                    href={`#/desk/${m.id}`}
                    title={`Open ${m.code} on the Desk`}
                  >
                    {m.picture ? (
                      <img
                        src={`/api/models/${encodeURIComponent(m.id)}/files/cover.png`}
                        alt=""
                        loading="lazy"
                      />
                    ) : (
                      <span className="d-noimg" />
                    )}
                    <span>{m.code}</span>
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}

        {q.pictures.length > 0 && (
          <section className="q-section">
            <h3>Pictures</h3>
            <ul className="q-pictures">
              {q.pictures.map((p) => (
                <li key={p.name}>
                  <button
                    type="button"
                    className="q-pic"
                    onClick={() => setZoom(picUrl(q.id, p.name))}
                    title="Click to enlarge"
                  >
                    <img
                      src={picUrl(q.id, p.name)}
                      alt={p.caption || "picture"}
                      loading="lazy"
                    />
                  </button>
                  {p.caption && <span lang="nl">{p.caption}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {q.context && (
          <section className="q-section">
            <h3>
              <button
                type="button"
                className="q-toggle"
                aria-expanded={showContext}
                onClick={() => setShowContext(!showContext)}
              >
                Context {showContext ? "▾" : "▸"}
              </button>
            </h3>
            {showContext && (
              <p className="q-context" lang="nl">
                {q.context}
              </p>
            )}
          </section>
        )}

        <section className="q-section">
          <h3>Answers ({q.answers.length})</h3>
          {!q.answers.length && <p className="d-muted">No answer yet.</p>}
          <ol className="q-answers">
            {q.answers.map((a) => (
              <li key={a.id} className={q.final_answer === a.id ? "final" : ""}>
                <div className="q-answer-head">
                  <strong>{a.name}</strong>
                  <span className="d-muted">{when(a.time)}</span>
                  {q.final_answer === a.id && (
                    <span className="d-pill q-final">
                      Final{q.final_by ? ` · ${q.final_by}` : ""}
                    </span>
                  )}
                  {isOwner && q.final_answer !== a.id && (
                    <button
                      type="button"
                      className="d-btn d-ghost d-small"
                      onClick={() =>
                        owner("final", { answer_id: a.id }, "Marked final.")
                      }
                    >
                      Mark final
                    </button>
                  )}
                  {isOwner && q.final_answer === a.id && (
                    <button
                      type="button"
                      className="d-btn d-ghost d-small"
                      onClick={() =>
                        owner(
                          "final",
                          { answer_id: null },
                          "Final mark removed.",
                        )
                      }
                    >
                      Not final
                    </button>
                  )}
                </div>
                {chosenText(q, a) && (
                  <div className="q-chosen" lang="nl">
                    {chosenText(q, a)}
                  </div>
                )}
                {a.comment && (
                  <div className="q-comment" lang="nl">
                    {a.comment}
                  </div>
                )}
                {a.pictures.length > 0 && (
                  <span className="d-thumbs">
                    {a.pictures.map((n) => (
                      <img
                        key={n}
                        src={picUrl(q.id, n)}
                        alt="attached picture"
                        loading="lazy"
                        title="Click to enlarge"
                        onClick={() => setZoom(picUrl(q.id, n))}
                      />
                    ))}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </section>

        {q.can_answer && (
          <form
            ref={formRef}
            className="q-form"
            aria-label="Your answer"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <h3>
              {q.you_answered
                ? "Change your answer (it replaces your earlier one)"
                : "Your answer"}
            </h3>
            <fieldset className="q-options" lang="nl">
              <legend className="sr-only">Choose an option</legend>
              {q.options.map((o, i) => (
                <label key={i} className={choice === i ? "on" : ""}>
                  <input
                    type="radio"
                    name={`q-${q.id}`}
                    checked={choice === i}
                    onChange={() => setChoice(i)}
                  />
                  <kbd>{i + 1}</kbd>
                  <span>
                    {letter(i)}) {o}
                  </span>
                </label>
              ))}
              {q.other_allowed && (
                <label className={`q-other ${choice === OTHER ? "on" : ""}`}>
                  <input
                    type="radio"
                    name={`q-${q.id}`}
                    checked={choice === OTHER}
                    onChange={() => setChoice(OTHER)}
                  />
                  <kbd>0</kbd>
                  <span>Anders, namelijk…</span>
                  <input
                    ref={otherRef}
                    type="text"
                    className="d-search"
                    aria-label="Anders, namelijk"
                    value={other}
                    onFocus={() => setChoice(OTHER)}
                    onChange={(e) => {
                      setOther(e.target.value);
                      setChoice(OTHER);
                    }}
                  />
                </label>
              )}
            </fieldset>
            <PictureTray
              pending={pending}
              onChange={setPending}
              drawingUrl={null}
              max={picturesMax}
              sources={sources}
            />
            <textarea
              aria-label="Comment"
              placeholder="Opmerking (optioneel): waarom, een maat, wat er nog ontbreekt…"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
            <div className="q-send">
              <button
                type="submit"
                className="d-btn d-primary"
                disabled={sending}
              >
                {sending ? "Sending…" : "Send answer"} <kbd>Ctrl</kbd>
                <kbd>Enter</kbd>
              </button>
              {msg && (
                <span className="d-msg" role="status">
                  {msg}
                </span>
              )}
            </div>
          </form>
        )}
        {!q.can_answer && msg && (
          <span className="d-msg" role="status">
            {msg}
          </span>
        )}

        {isOwner && (
          <section className="q-section q-owner">
            <h3>Owner</h3>
            {q.status !== "processed" ? (
              <div className="q-done">
                <textarea
                  aria-label="What was done"
                  placeholder="What was done with the answer (shown to whoever answered)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
                <button
                  type="button"
                  className="d-btn"
                  disabled={!note.trim()}
                  onClick={() => owner("done", { note }, "Marked processed.")}
                >
                  Mark processed
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="d-btn d-ghost"
                onClick={() => owner("reopen", {}, "Opened again.")}
              >
                Reopen
              </button>
            )}
          </section>
        )}
      </div>

      {zoom && (
        <div className="d-zoom" onClick={() => setZoom(null)}>
          <img src={zoom} alt="large" />
        </div>
      )}
    </article>
  );
}
