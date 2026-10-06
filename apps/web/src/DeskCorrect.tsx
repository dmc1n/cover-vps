// Corrections that change the cover itself (ADR-082), on the Desk card: a seam removed or added,
// the vents, a size read wrong, a shape that is missing. Each correction is saved on the cover,
// recalculated at once and kept as a test case; the same correction on several covers of a
// group is proposed as the group's rule (RulesBar, on top of the Desk).
import { useCallback, useEffect, useState } from "react";

interface SeamPoint {
  id: string;
  kind: string;
  panels: string[];
  length_mm: number | null;
  at: number[] | null;
}
interface PiecePoint {
  name: string;
  region: string;
  at: number[];
  min: number[];
  max: number[];
}
interface CorrectView {
  seams: SeamPoint[];
  pieces: PiecePoint[];
  drawn: boolean;
  sizes_cm: number[];
  settings: Record<string, number>;
  piece_count: number;
  vents: number;
  shapes: string[];
  feedback: Record<string, unknown>[];
  edits: Record<string, unknown>[];
}
interface Proposal {
  group: string;
  key: string;
  value: unknown;
  covers: string[];
  count: number;
}
interface Rules {
  rules: Record<string, Record<string, unknown>>;
  proposals: Proposal[];
  shape_problems: Record<string, Record<string, number>>;
  learn_after: number;
}

async function call<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401) window.dispatchEvent(new Event("login-needed"));
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail ?? `${r.status}`);
  return data as T;
}

const TABS = ["seams", "vents", "sizes", "shape"] as const;
type Tab = (typeof TABS)[number];
const KEY_LABEL: Record<string, string> = {
  "features.vents_total": "air vents",
  "features.vent_above_hem_mm": "vent height above the hem (mm)",
  "seams.skirt_height_mm": "skirt seam height (mm)",
};
const flat = (tree: Record<string, unknown>, pre = ""): [string, unknown][] =>
  Object.entries(tree).flatMap(([k, v]) =>
    v && typeof v === "object" && !Array.isArray(v)
      ? flat(v as Record<string, unknown>, `${pre}${k}.`)
      : [[`${pre}${k}`, v] as [string, unknown]],
  );

export function Corrections({
  id,
  canAct,
  onChanged,
}: {
  id: string;
  canAct: boolean;
  onChanged: () => void;
}) {
  const [v, setV] = useState<CorrectView | null>(null);
  const [tab, setTab] = useState<Tab>("seams");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [piece, setPiece] = useState("");
  const [axis, setAxis] = useState("z");
  const [atCm, setAtCm] = useState("");
  const [skirtCm, setSkirtCm] = useState("");
  const [count, setCount] = useState("");
  const [hemCm, setHemCm] = useState("");
  const [what, setWhat] = useState("");
  const [readCm, setReadCm] = useState("");
  const [rightCm, setRightCm] = useState("");
  const [chips, setChips] = useState<string[]>([]);
  const [text, setText] = useState("");
  const load = useCallback(
    () =>
      call<CorrectView>(`/api/desk/${id}/correct`)
        .then((x) => {
          setV(x);
          setPiece((p) => p || x.pieces[0]?.name || "");
        })
        .catch((e) => setMsg(String(e.message ?? e))),
    [id],
  );
  useEffect(() => {
    load();
  }, [load]);

  const send = async (body: Record<string, unknown>, done: string) => {
    setBusy(true);
    setMsg("");
    try {
      const out = await call<{ steps: string[]; job: unknown }>(
        `/api/desk/${id}/correct`,
        body,
      );
      setMsg(
        out.steps.length
          ? `${done} · recalculating (${out.steps.join(" → ")}) · kept as a test case`
          : `${done} · kept for the drawing reader and as a test case`,
      );
      load();
      onChanged();
    } catch (e) {
      setMsg(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };
  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  // seams removed whose recalculation has not yet come back (the cut still lists them)
  const pending = new Set(
    (v?.edits ?? [])
      .filter((e) => e.op === "join" && typeof e.seam === "string")
      .map((e) => String(e.seam))
      .filter((sid) => v?.seams.some((s) => s.id === sid)),
  );
  const line = (f: Record<string, unknown>) => {
    const bits: string[] = [];
    if (f.op === "remove") bits.push(`removed ${String(f.seam)}`);
    if (f.op === "add")
      bits.push(
        `added on ${String(f.piece)} at ${String(f.at_cm)} cm (${String(f.axis ?? "z")})`,
      );
    if (f.op === "skirt") bits.push(`skirt seam at ${String(f.at_cm)} cm`);
    if (f.count != null) bits.push(`${String(f.count)} vents`);
    if (f.above_hem_cm != null)
      bits.push(`vents ${String(f.above_hem_cm)} cm above the hem`);
    if (f.correct_cm != null)
      bits.push(
        `${String(f.what || "size")} ${String(f.read_cm ?? "?")} → ${String(f.correct_cm)} cm`,
      );
    if (Array.isArray(f.chips) && f.chips.length)
      bits.push((f.chips as string[]).join(", "));
    if (f.text) bits.push(`“${String(f.text)}”`);
    return bits.join(" · ");
  };

  if (!v)
    return (
      <section className="d-panel d-wide dc">
        <h3>Correct this cover</h3>
        <p className="d-muted">{msg || "Loading…"}</p>
      </section>
    );
  return (
    <section className="d-panel d-wide dc">
      <div className="dc-head">
        <h3>Correct this cover</h3>
        <p className="dc-note">
          A correction changes the cover itself: it is saved on the cover,
          recalculated at once and kept as a test the program must keep passing.
          The same correction on several covers of one series becomes a proposed
          rule for that series.
        </p>
      </div>
      <div className="d-seg-ctl dc-tabs">
        {TABS.map((t) => (
          <button
            key={t}
            className={tab === t ? "on" : ""}
            onClick={() => setTab(t)}
          >
            {t === "seams"
              ? `Seams · ${v.seams.length}`
              : t === "vents"
                ? `Vents · ${v.vents}`
                : t === "sizes"
                  ? "Sizes"
                  : "Shape"}
          </button>
        ))}
      </div>

      {tab === "seams" && (
        <div className="dc-body">
          {!v.drawn && (
            <p className="d-muted">
              This cover's seams follow the furniture: set the skirt seam's
              height here, or place seams in the model's seam editor.
            </p>
          )}
          {v.seams.length > 0 && (
            <table className="d-table dc-seams">
              <tbody>
                {v.seams.map((s) => (
                  <tr
                    key={s.id}
                    className={pending.has(s.id) ? "dc-pending" : ""}
                  >
                    <td>
                      <span className={`dc-kind k-${s.kind}`}>{s.kind}</span>
                    </td>
                    <td>{s.panels.join(" ⟷ ")}</td>
                    <td>
                      {s.length_mm != null &&
                        `${Math.round(s.length_mm / 10)} cm`}
                    </td>
                    <td>
                      {pending.has(s.id) ? (
                        <em className="d-muted">removed · recalculating</em>
                      ) : (
                        canAct &&
                        v.drawn && (
                          <button
                            className="d-link"
                            disabled={busy}
                            onClick={() =>
                              send(
                                { kind: "seam", op: "remove", seam: s.id },
                                `Seam ${s.id} removed`,
                              )
                            }
                          >
                            remove seam
                          </button>
                        )
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {canAct && v.drawn && v.pieces.length > 0 && (
            <div className="dc-row">
              <span>Add a seam to</span>
              <select value={piece} onChange={(e) => setPiece(e.target.value)}>
                {v.pieces.map((p) => (
                  <option key={p.name}>{p.name}</option>
                ))}
              </select>
              <select value={axis} onChange={(e) => setAxis(e.target.value)}>
                <option value="z">at a height above the hem</option>
                <option value="x">across, from its left end</option>
                <option value="y">across, from its front</option>
              </select>
              <input
                className="dc-num"
                placeholder="cm"
                value={atCm}
                onChange={(e) => setAtCm(e.target.value)}
              />
              <button
                className="d-btn d-ghost"
                disabled={busy || num(atCm) == null}
                onClick={() =>
                  send(
                    {
                      kind: "seam",
                      op: "add",
                      piece,
                      axis,
                      at_cm: num(atCm),
                    },
                    `Seam added to ${piece}`,
                  )
                }
              >
                Add seam
              </button>
            </div>
          )}
          {canAct && !v.drawn && (
            <div className="dc-row">
              <span>Skirt seam at</span>
              <input
                className="dc-num"
                placeholder={
                  v.settings["seams.skirt_height_mm"]
                    ? String(v.settings["seams.skirt_height_mm"] / 10)
                    : "auto"
                }
                value={skirtCm}
                onChange={(e) => setSkirtCm(e.target.value)}
              />
              <span>cm above the hem</span>
              <button
                className="d-btn d-ghost"
                disabled={busy || num(skirtCm) == null}
                onClick={() =>
                  send(
                    { kind: "seam", op: "skirt", at_cm: num(skirtCm) },
                    "Skirt seam moved",
                  )
                }
              >
                Move
              </button>
            </div>
          )}
        </div>
      )}

      {tab === "vents" && (
        <div className="dc-body">
          <div className="dc-row">
            <span>Air vents</span>
            <input
              className="dc-num"
              placeholder={String(v.vents)}
              value={count}
              onChange={(e) => setCount(e.target.value)}
            />
            <span>bottom edge</span>
            <input
              className="dc-num"
              placeholder={String(
                (v.settings["features.vent_above_hem_mm"] ?? 0) / 10,
              )}
              value={hemCm}
              onChange={(e) => setHemCm(e.target.value)}
            />
            <span>cm above the hem</span>
            {canAct && (
              <button
                className="d-btn d-ghost"
                disabled={busy || (num(count) == null && num(hemCm) == null)}
                onClick={() =>
                  send(
                    {
                      kind: "vents",
                      count: num(count),
                      above_hem_cm: num(hemCm),
                    },
                    "Vents corrected",
                  )
                }
              >
                Save
              </button>
            )}
          </div>
        </div>
      )}

      {tab === "sizes" && (
        <div className="dc-body">
          {v.sizes_cm.length > 0 && (
            <div className="d-chips dc-sizes">
              {v.sizes_cm.map((s) => (
                <button
                  key={s}
                  className={num(readCm) === s ? "on" : ""}
                  onClick={() => setReadCm(String(s))}
                >
                  {s} cm
                </button>
              ))}
            </div>
          )}
          <div className="dc-row">
            <input
              placeholder="which size (length, height, …)"
              value={what}
              onChange={(e) => setWhat(e.target.value)}
            />
            <span>read</span>
            <input
              className="dc-num"
              placeholder="cm"
              value={readCm}
              onChange={(e) => setReadCm(e.target.value)}
            />
            <span>is really</span>
            <input
              className="dc-num"
              placeholder="cm"
              value={rightCm}
              onChange={(e) => setRightCm(e.target.value)}
            />
            {canAct && (
              <button
                className="d-btn d-ghost"
                disabled={busy || num(rightCm) == null}
                onClick={() =>
                  send(
                    {
                      kind: "size",
                      what,
                      read_cm: num(readCm),
                      correct_cm: num(rightCm),
                    },
                    "Size corrected",
                  )
                }
              >
                Save
              </button>
            )}
          </div>
        </div>
      )}

      {tab === "shape" && (
        <div className="dc-body">
          <div className="d-chips">
            {v.shapes.map((s) => (
              <button
                key={s}
                className={chips.includes(s) ? "on" : ""}
                onClick={() =>
                  setChips(
                    chips.includes(s)
                      ? chips.filter((x) => x !== s)
                      : [...chips, s],
                  )
                }
              >
                {s}
              </button>
            ))}
          </div>
          <div className="dc-row">
            <input
              className="dc-wide"
              placeholder="What is missing, in a few words"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            {canAct && (
              <button
                className="d-btn d-ghost"
                disabled={busy || (!chips.length && !text.trim())}
                onClick={() =>
                  send({ kind: "shape", chips, text }, "Shape noted")
                }
              >
                Save
              </button>
            )}
          </div>
        </div>
      )}

      {v.feedback.length > 0 && (
        <ul className="dc-done">
          {[...v.feedback]
            .reverse()
            .slice(0, 6)
            .map((f, i) => (
              <li key={i}>
                <strong>{String(f.kind)}</strong> {line(f)}
                {f.by ? <em> · {String(f.by)}</em> : null}
              </li>
            ))}
        </ul>
      )}
      {msg && <p className="d-msg dc-msg">{msg}</p>}
    </section>
  );
}

export function RulesBar({
  canAct,
  onChanged,
}: {
  canAct: boolean;
  onChanged: () => void;
}) {
  const [r, setR] = useState<Rules | null>(null);
  const [msg, setMsg] = useState("");
  const load = useCallback(
    () =>
      call<Rules>("/api/desk-rules")
        .then(setR)
        .catch(() => setR(null)),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);
  if (!r) return null;
  const learnt = Object.entries(r.rules).flatMap(([g, tree]) =>
    flat(tree).map(([k, val]) => ({ g, k, val })),
  );
  const shapes = Object.entries(r.shape_problems).flatMap(([g, m]) =>
    Object.entries(m)
      .filter(([, n]) => n >= 2)
      .map(([s, n]) => ({ g, s, n })),
  );
  if (!r.proposals.length && !learnt.length && !shapes.length) return null;
  return (
    <section className="dc-rules">
      {r.proposals.map((p) => (
        <div key={`${p.group}-${p.key}`} className="dc-prop">
          <span className="dc-badge">learned</span>
          <span>
            Corrected the same way on <b>{p.count}</b> covers of{" "}
            <b>{p.group}</b>: {KEY_LABEL[p.key] ?? p.key} ={" "}
            <b>{String(p.value)}</b>
          </span>
          {canAct && (
            <button
              className="d-btn d-primary d-small"
              onClick={() =>
                call<{ covers: string[] }>("/api/desk-rules", {
                  group: p.group,
                  key: p.key,
                  value: p.value,
                })
                  .then((o) => {
                    setMsg(
                      `Now the rule for ${p.group}: ${o.covers.length} covers recalculate`,
                    );
                    load();
                    onChanged();
                  })
                  .catch((e) => setMsg(String(e.message ?? e)))
              }
            >
              Make it the rule
            </button>
          )}
        </div>
      ))}
      {learnt.length > 0 && (
        <div className="dc-learnt">
          <span className="dc-badge quiet">rules</span>
          {learnt.map(({ g, k, val }) => (
            <span key={`${g}-${k}`} className="dc-rule">
              {g}: {KEY_LABEL[k] ?? k} = {String(val)}
            </span>
          ))}
        </div>
      )}
      {shapes.length > 0 && (
        <div className="dc-learnt">
          <span className="dc-badge warn">for the program</span>
          {shapes.map(({ g, s, n }) => (
            <span key={`${g}-${s}`} className="dc-rule">
              {g}: “{s}” ×{n}
            </span>
          ))}
        </div>
      )}
      {msg && <span className="d-msg">{msg}</span>}
    </section>
  );
}
