// Covers → Links (ADR-132): a drawing cover and a 3D-model cover of the same product, side by
// side, with the program's score and its reasons. A person confirms, says "Not a pair", or chooses
// another partner; nothing learns from a pair until a person confirmed it. Editors and admins
// decide (the API checks it too), viewers look, the workshop login does not see the page.
import { useCallback, useEffect, useState } from "react";
import { fileUrl } from "./api";
import { Icon, StatusChip } from "./icons";
import { FilterRow, Tpl } from "./layout";
import { isEditor, modelHref } from "./nav";
import { useSession } from "./Session";

interface Brief {
  id: string;
  code: string;
  name: string;
  kind: string | null;
  cover_cm: number[] | null;
  furniture_cm: number[] | null;
  plan: string;
  hand: string | null;
  status: string | null;
}
export interface Link {
  id: number;
  drawing_id: string;
  model_id: string;
  status: "proposed" | "confirmed" | "rejected" | "manual";
  score: number | null;
  strength: "high" | "likely" | "unsure";
  signals: Record<string, number>;
  reasons: string[];
  doubts: string[];
  facts: { drawing?: Brief; model?: Brief };
  mirror: boolean;
  sheet: string | null;
  source: string;
  note: string;
  stale: boolean;
  decided: number | null;
  decided_by: string | null;
  version: number;
}
interface ListResult {
  links: Link[];
  nopartner: string[];
  total: number;
  counts: Record<string, number>;
  bulk_min: number;
  may_edit: boolean;
}

const FILTERS: [string, string][] = [
  ["proposed", "Proposed"],
  ["confirmed", "Confirmed"],
  ["manual", "Chosen"],
  ["rejected", "Not a pair"],
  ["nopartner", "No partner"],
];
const SIGNALS: [string, string][] = [
  ["names", "names"],
  ["size", "size"],
  ["shape", "plan"],
  ["kind", "kind"],
  ["side", "hand"],
  ["picture", "picture"],
];

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

const size = (v?: number[] | null) =>
  v ? v.map((x) => Math.round(x)).join(" × ") + " cm" : "–";
const pct = (x: number | null) => (x == null ? "–" : `${Math.round(x * 100)}`);
const when = (t: number | null) =>
  t
    ? new Date(t * 1000).toLocaleString(undefined, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
const statusWord: Record<Link["status"], string> = {
  proposed: "proposed",
  confirmed: "confirmed",
  manual: "chosen by hand",
  rejected: "not a pair",
};

export function Links({ initialQ = "" }: { initialQ?: string }) {
  const { user } = useSession();
  const [status, setStatus] = useState("proposed");
  const [strength, setStrength] = useState("");
  const [q, setQ] = useState(initialQ);
  const [data, setData] = useState<ListResult | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [bulk, setBulk] = useState<Link[] | null>(null);
  const editor = isEditor(user) && !!data?.may_edit;

  const load = useCallback(() => {
    const p = new URLSearchParams({ status, q, strength, limit: "200" });
    call<ListResult>(`/api/links?${p}`)
      .then((d) => {
        setData(d);
        setErr("");
      })
      .catch((e) => setErr(String(e.message ?? e)));
  }, [status, q, strength]);
  useEffect(() => {
    const t = setTimeout(load, 150);
    return () => clearTimeout(t);
  }, [load]);

  const highs = (data?.links ?? []).filter(
    (l) =>
      l.status === "proposed" &&
      (l.score ?? 0) >= (data?.bulk_min ?? 1) &&
      l.doubts.length === 0,
  );
  const confirmAll = async () => {
    if (!bulk || !data) return;
    try {
      const r = await call<{ confirmed: number[]; skipped: unknown[] }>(
        "/api/links/bulk-confirm",
        { ids: bulk.map((l) => l.id), min_score: data.bulk_min },
      );
      setMsg(
        `${r.confirmed.length} confirmed` +
          (r.skipped.length ? `, ${r.skipped.length} skipped` : ""),
      );
      setBulk(null);
      load();
    } catch (e) {
      setErr(String((e as Error).message));
    }
  };

  return (
    <Tpl
      kind="list"
      title="Links"
      className="links-page"
      intro={
        <>
          A drawing cover and a cover made from the manufacturer's 3D model of
          the same product, linked so we can learn from the pair. The program
          proposes; you confirm, say <b>Not a pair</b>, or choose another
          partner. Nothing learns from a pair until a person confirmed it. The
          product list's links (namecode.xlsx) are proposals here too.
        </>
      }
    >
      <FilterRow
        count={
          data && (
            <>
              {status === "nopartner" ? data.nopartner.length : data.total}{" "}
              shown
            </>
          )
        }
      >
        <div className="seg" role="group" aria-label="Status">
          {FILTERS.map(([id, label]) => (
            <button
              key={id}
              className={status === id ? "on" : ""}
              aria-pressed={status === id}
              onClick={() => setStatus(id)}
            >
              {label}
              {data?.counts?.[id] != null && (
                <span className="links-count">{data.counts[id]}</span>
              )}
            </button>
          ))}
        </div>
        <input
          type="search"
          placeholder="Search a cover…"
          aria-label="Search a cover"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {status !== "nopartner" && (
          <select
            aria-label="Strength"
            value={strength}
            onChange={(e) => setStrength(e.target.value)}
          >
            <option value="">every score</option>
            <option value="high">high</option>
            <option value="likely">likely</option>
            <option value="unsure">unsure</option>
          </select>
        )}
      </FilterRow>
      {err && <p className="error">{err}</p>}
      {msg && <p className="ok-msg">{msg}</p>}
      {editor && status === "proposed" && highs.length > 0 && (
        <div className="selbar links-bulk">
          {bulk ? (
            <>
              <span>
                Confirm {bulk.length} links scoring at least{" "}
                {pct(data?.bulk_min ?? null)} with no doubt?
              </span>
              <button className="primary sm" onClick={confirmAll}>
                Confirm {bulk.length}
              </button>
              <button className="sm ghost" onClick={() => setBulk(null)}>
                Cancel
              </button>
            </>
          ) : (
            <button
              className="sm"
              onClick={() => setBulk(highs)}
              title={`Confirm every proposal on this page scoring at least ${pct(data?.bulk_min ?? null)} without a doubt`}
            >
              <Icon name="st-ok" size={15} /> Confirm all high ({highs.length})
            </button>
          )}
        </div>
      )}
      {data && status === "nopartner" && (
        <div className="links-list">
          {data.nopartner.length === 0 && (
            <p className="muted">Every drawing cover has a partner.</p>
          )}
          {data.nopartner.map((d) => (
            <NoPartner key={d} id={d} editor={editor} onDone={load} />
          ))}
        </div>
      )}
      {data && status !== "nopartner" && (
        <div className="links-list">
          {data.links.length === 0 && <p className="muted">Nothing here.</p>}
          {data.links.map((l) => (
            <LinkRow key={l.id} link={l} editor={editor} onDone={load} />
          ))}
        </div>
      )}
    </Tpl>
  );
}

function Side({
  id,
  brief,
  drawing,
}: {
  id: string;
  brief?: Brief;
  drawing: boolean;
}) {
  return (
    <div className="lk-side">
      <div className="lk-pics">
        <img
          src={fileUrl(id, "cover.png")}
          alt={`${id}: its cover`}
          loading="lazy"
        />
        {drawing && (
          <img
            className="lk-ref"
            src={fileUrl(id, "reference.png")}
            alt={`${id}: the drawing`}
            loading="lazy"
            onError={(e) => (e.currentTarget.style.display = "none")}
          />
        )}
      </div>
      <a className="lk-name" href={modelHref(id)}>
        {drawing ? brief?.code || id : id.replace(/^suns-/, "")}
      </a>
      <span className="lk-sub" title={brief?.name}>
        {brief?.name && brief.name !== id ? brief.name : ""}
      </span>
      <dl className="lk-facts">
        <dt>cover</dt>
        <dd>{size(brief?.cover_cm)}</dd>
        {!drawing && (
          <>
            <dt>furniture</dt>
            <dd>{size(brief?.furniture_cm)}</dd>
          </>
        )}
        <dt>plan</dt>
        <dd>
          {brief?.plan ?? "–"}
          {brief?.hand ? ` (${brief.hand})` : ""}
        </dd>
        <dt>kind</dt>
        <dd>{brief?.kind ?? "–"}</dd>
      </dl>
    </div>
  );
}

function LinkRow({
  link: l,
  editor,
  onDone,
}: {
  link: Link;
  editor: boolean;
  onDone: () => void;
}) {
  const [err, setErr] = useState("");
  const [picking, setPicking] = useState(false);
  const decide = async (status: string) => {
    try {
      await call(`/api/links/${l.id}/decide`, { status, version: l.version });
      onDone();
    } catch (e) {
      setErr(String((e as Error).message));
    }
  };
  const tone =
    l.status === "proposed"
      ? l.strength === "unsure"
        ? "check"
        : "waiting"
      : l.status === "rejected"
        ? "rejected"
        : "approved";
  return (
    <article
      className={`lk-row lk-${l.status}`}
      data-testid="link-row"
      aria-label={`${l.drawing_id} and ${l.model_id}`}
    >
      <Side id={l.drawing_id} brief={l.facts.drawing} drawing />
      <div className="lk-mid">
        <div className="lk-score" title="The program's score (0–100)">
          <span className="lk-num">{pct(l.score)}</span>
          <StatusChip status={tone}>
            {l.status === "proposed" ? l.strength : statusWord[l.status]}
          </StatusChip>
          {l.mirror && (
            <span
              className="badge"
              title="The drawing is the other hand of this model"
            >
              mirror
            </span>
          )}
          {l.sheet && (
            <span className="badge" title="The product list (namecode.xlsx)">
              product list
            </span>
          )}
          {l.stale && (
            <span className="badge" title="The last run no longer proposes it">
              old proposal
            </span>
          )}
        </div>
        <div className="lk-signals" aria-label="Signals">
          {SIGNALS.filter(([k]) => l.signals[k] != null).map(([k, w]) => (
            <span
              key={k}
              className="lk-sig"
              title={`${w}: ${pct(l.signals[k])}`}
            >
              <span className="lk-sig-w">{w}</span>
              <span className="lk-bar">
                <span style={{ width: `${Math.round(l.signals[k] * 100)}%` }} />
              </span>
            </span>
          ))}
        </div>
        {l.doubts.length > 0 && (
          <ul className="lk-doubts">
            {l.doubts.map((d, i) => (
              <li key={i}>
                <Icon name="st-warn" size={13} /> {d}
              </li>
            ))}
          </ul>
        )}
        {l.reasons.length > 0 && (
          <ul className="lk-reasons">
            {l.reasons.map((r, i) => (
              <li key={i}>
                <Icon name="st-ok" size={13} /> {r}
              </li>
            ))}
          </ul>
        )}
        {l.decided_by && (
          <p className="muted lk-who">
            {statusWord[l.status]} by {l.decided_by}, {when(l.decided)}
            {l.note && ` · ${l.note}`}
          </p>
        )}
        {err && <p className="error">{err}</p>}
        {editor && (
          <div className="lk-actions">
            {l.status !== "confirmed" && l.status !== "manual" && (
              <button
                className="primary sm"
                onClick={() => decide("confirmed")}
              >
                Confirm
              </button>
            )}
            {l.status !== "rejected" && (
              <button className="sm" onClick={() => decide("rejected")}>
                Not a pair
              </button>
            )}
            <button className="sm ghost" onClick={() => setPicking((x) => !x)}>
              Choose another
            </button>
            {l.status !== "proposed" && (
              <button
                className="sm ghost"
                onClick={() => decide("proposed")}
                title="Take the decision back: a proposal again"
              >
                Reopen
              </button>
            )}
          </div>
        )}
        {picking && (
          <Picker
            drawing={l.drawing_id}
            replaces={l.id}
            onDone={() => {
              setPicking(false);
              onDone();
            }}
          />
        )}
      </div>
      <Side id={l.model_id} brief={l.facts.model} drawing={false} />
    </article>
  );
}

function NoPartner({
  id,
  editor,
  onDone,
}: {
  id: string;
  editor: boolean;
  onDone: () => void;
}) {
  const [picking, setPicking] = useState(false);
  return (
    <article className="lk-row lk-alone" data-testid="nopartner-row">
      <Side id={id} drawing />
      <div className="lk-mid">
        <p className="muted">
          No 3D model scores as this product. A drawing of a whole set often has
          no single model: its partner is an arrangement.
        </p>
        {editor && (
          <div className="lk-actions">
            <button className="sm" onClick={() => setPicking((x) => !x)}>
              Choose a partner
            </button>
          </div>
        )}
        {picking && (
          <Picker
            drawing={id}
            replaces={null}
            onDone={() => {
              setPicking(false);
              onDone();
            }}
          />
        )}
      </div>
    </article>
  );
}

function Picker({
  drawing,
  replaces,
  onDone,
}: {
  drawing: string;
  replaces: number | null;
  onDone: () => void;
}) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<{ id: string; picture: boolean }[]>([]);
  const [mirror, setMirror] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    const t = setTimeout(() => {
      call<{ covers: { id: string; picture: boolean }[] }>(
        `/api/links-search?side=model&q=${encodeURIComponent(q)}`,
      )
        .then((d) => setHits(d.covers))
        .catch(() => setHits([]));
    }, 200);
    return () => clearTimeout(t);
  }, [q]);
  const pick = async (model: string) => {
    try {
      await call("/api/links/choose", {
        drawing_id: drawing,
        model_id: model,
        replaces,
        mirror,
      });
      onDone();
    } catch (e) {
      setErr(String((e as Error).message));
    }
  };
  return (
    <div className="lk-picker" role="dialog" aria-label="Choose another">
      <div className="lk-picker-row">
        <input
          type="search"
          autoFocus
          placeholder="Search a 3D model: evora daybed, kota corner…"
          aria-label="Search a 3D model"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className="lk-mirror">
          <input
            type="checkbox"
            checked={mirror}
            onChange={(e) => setMirror(e.target.checked)}
          />{" "}
          mirror image
        </label>
      </div>
      {err && <p className="error">{err}</p>}
      <ul className="lk-hits">
        {hits.map((h) => (
          <li key={h.id}>
            <button className="ghost sm" onClick={() => pick(h.id)}>
              {h.picture && (
                <img src={fileUrl(h.id, "cover.png")} alt="" loading="lazy" />
              )}
              {h.id.replace(/^suns-/, "")}
            </button>
          </li>
        ))}
        {hits.length === 0 && <li className="muted">No cover found.</li>}
      </ul>
    </div>
  );
}

/** A partner as people say it: a drawing by its code (D1), a model by its name. */
const partnerName = (id: string) =>
  id.startsWith("drawing-")
    ? id.replace(/^drawing-/, "").toUpperCase()
    : id.replace(/^suns-/, "").replace(/-/g, " ");

/** On a cover's page: "Linked to …" (a person's link) or the proposals waiting, as a chip. */
export function LinkChip({ id }: { id: string }) {
  const [links, setLinks] = useState<
    { id: number; partner: string; status: string; person: boolean }[] | null
  >(null);
  useEffect(() => {
    let live = true;
    fetch(`/api/links/of/${id}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => live && setLinks(d?.links ?? null))
      .catch(() => live && setLinks(null));
    return () => {
      live = false;
    };
  }, [id]);
  if (!links || links.length === 0) return null;
  const mine = links.filter((l) => l.person);
  if (mine.length > 0)
    return (
      <span className="lk-chip" data-testid="link-chip">
        <Icon name="links" size={13} /> Linked to{" "}
        {mine.slice(0, 2).map((l, i) => (
          <span key={l.id}>
            {i > 0 && ", "}
            <a href={modelHref(l.partner)}>{partnerName(l.partner)}</a>
          </span>
        ))}
        {mine.length > 2 && ` +${mine.length - 2}`}
      </span>
    );
  return (
    <a
      className="lk-chip lk-chip-wait"
      data-testid="link-chip"
      href={`#/covers/links?q=${encodeURIComponent(id)}`}
      title="Proposed links, waiting for a person"
    >
      <Icon name="links" size={13} /> {links.length} proposed link
      {links.length > 1 ? "s" : ""}
    </a>
  );
}
