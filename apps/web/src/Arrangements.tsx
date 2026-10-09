// Arrangements (ADR-089): furniture from the catalogue placed together, then one cover over the
// whole. The top view shows each member's real footprint; drag to move, turn by 90°, mirror,
// or snap one member against another's side. "Build cover" makes the arrangement a model
// (arr-<name>) and calculates its cover like any model. "Send to the Desk" puts it before Rens or
// Wout for approval; a change after that sends it back for approval by itself (ADR-115).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Job, type ModelBrief } from "./api";

interface Member {
  model_id: string;
  x_mm: number;
  y_mm: number;
  rot_deg: number;
  mirror: boolean;
}
interface Outline {
  model_id: string;
  size_mm: number[];
  outline_mm: number[][][];
}
interface Settings {
  gap_mm: number;
  grid_mm: number;
  rotation_step_deg: number;
  footprint?: string;
}
/** One plan the cover can take, seen from above at the hem (ADR-095). */
interface Plan {
  footprint: string;
  outline_mm: number[][];
  size_mm: number[];
  area_m2: number;
  empty_m2: number;
  rects_mm: number[][][];
}

const PLAN_NAMES: Record<string, [string, string]> = {
  follow: [
    "Follow the products (sharp corners)",
    "Each piece's own outline joined; straight walls, right-angled inner corners.",
  ],
  box: [
    "One rectangle around everything",
    "A simple box over the whole arrangement; spans open corners.",
  ],
  smooth: [
    "Smoothed outline",
    "The tightest box with slanted walls; cuts open corners diagonally.",
  ],
};

/** A small top view of one plan: the pieces in grey, the cover's outline in red. */
function PlanPreview({ plan }: { plan: Plan }) {
  const pts = [...plan.outline_mm, ...plan.rects_mm.flat()];
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const y0 = Math.min(...ys);
  const y1 = Math.max(...ys);
  const pad = Math.max(x1 - x0, y1 - y0) * 0.06;
  const w = x1 - x0 + 2 * pad;
  const line = w / 150;
  const poly = (ring: number[][]) =>
    ring.map(([x, y]) => `${x},${-y}`).join(" ");
  return (
    <svg
      viewBox={`${x0 - pad} ${-(y1 + pad)} ${w} ${y1 - y0 + 2 * pad}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {plan.rects_mm.map((r, i) => (
        <polygon
          key={i}
          points={poly(r)}
          className="member"
          strokeWidth={line / 2}
        />
      ))}
      <polygon
        points={poly(plan.outline_mm)}
        className="cover"
        strokeWidth={line}
      />
    </svg>
  );
}
/** Where an arrangement stands at the Desk (ADR-115). */
interface DeskInfo {
  status: string;
  at_desk: boolean;
  dxf_ok: boolean;
  sent: { by: string; time: number } | null;
  approved: { by: string; time: number } | null;
  produced: { by: string; time: number } | null;
  rejected: {
    by: string;
    time: number;
    reasons?: string[];
    text?: string;
  } | null;
  last: { action: string; by: string; time: number; text?: string } | null;
}
interface Listed {
  id: string;
  name: string;
  size_mm: number[];
  members: string[];
  stale: string[];
  built: boolean;
  desk?: DeskInfo;
}

const when = (t: number) =>
  new Date(t * 1000).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

/** The arrangement's place in the approval workflow, in words, with what to do next. */
function deskWords(d: DeskInfo): [string, string] {
  if (d.status === "approved" && d.approved)
    return [
      "approved",
      `Approved by ${d.approved.by} on ${when(d.approved.time)}`,
    ];
  if (d.status === "produced" && d.produced)
    return ["approved", `Produced (${when(d.produced.time)})`];
  if (d.status === "rejected" && d.rejected)
    return [
      "rejected",
      `Rejected by ${d.rejected.by} on ${when(d.rejected.time)}: ${[...(d.rejected.reasons ?? []), d.rejected.text ?? ""].filter(Boolean).join(" · ") || "no reason given"}`,
    ];
  if (d.status === "ai-checked" && d.sent) {
    const again =
      d.last && d.last.action.startsWith("changed after")
        ? ` again (${d.last.action}: ${d.last.text ?? ""})`
        : "";
    return [
      "waiting",
      `Waiting for approval at the Desk${again} · sent by ${d.sent.by} on ${when(d.sent.time)}`,
    ];
  }
  return ["new", "Not at the Desk yet"];
}

function DeskStatus({
  id,
  desk,
  built,
  running,
  onSend,
}: {
  id: string;
  desk: DeskInfo | null;
  built: boolean;
  running: boolean;
  onSend: () => void;
}) {
  if (!desk) return null;
  const [tone, words] = deskWords(desk);
  const canSend =
    built &&
    !running &&
    (desk.status === "new" ||
      desk.status === "rejected" ||
      (desk.status === "ai-checked" && !desk.sent));
  return (
    <div className={`arrange-desk t-${tone}`} data-testid="arr-desk-status">
      <b>{words}</b>
      {tone === "approved" && (
        <span className="muted">
          The cutting-table DXF is available. Changing the plan or the pieces
          and building again sends it back for approval.
        </span>
      )}
      {tone === "waiting" && (
        <span className="muted">
          Rens or Wout approve it at the Desk; the DXF for the cutting table
          waits until then.
        </span>
      )}
      {tone === "rejected" && (
        <span className="muted">
          Change it and build again: it goes back to the Desk by itself.
        </span>
      )}
      {tone === "new" && (
        <span className="muted">
          {built
            ? "When the cover looks right, send it to the Desk for approval. The DXF for the cutting table waits for the approval."
            : "Build the cover first, then send it to the Desk for approval."}
        </span>
      )}
      <div className="row">
        {canSend && (
          <button className="primary" onClick={onSend}>
            {desk.status === "rejected"
              ? "Send to the Desk again"
              : "Send to the Desk"}
          </button>
        )}
        {(desk.at_desk || desk.sent) && (
          <a href={`#/desk/${id}`}>Open its Desk card ↗</a>
        )}
      </div>
    </div>
  );
}

async function call<T>(url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail ?? `${r.status}`);
  return data as T;
}

/** A member's footprint as it stands: mirrored, turned, its box middle at (x, y) — as the
 * engine places it (coverengine/arrange.py). */
function placedRings(o: Outline, m: Member): number[][][] {
  const a = (m.rot_deg * Math.PI) / 180;
  const c = Math.cos(a);
  const s = Math.sin(a);
  const rings = o.outline_mm.map((ring) =>
    ring.map(([x0, y0]) => {
      const x = m.mirror ? -x0 : x0;
      return [x * c - y0 * s, x * s + y0 * c];
    }),
  );
  const all = rings.flat();
  const xs = all.map((p) => p[0]);
  const ys = all.map((p) => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  return rings.map((r) =>
    r.map(([x, y]) => [x - cx + m.x_mm, y - cy + m.y_mm]),
  );
}

const COLOURS = [
  "#778074",
  "#b08d57",
  "#5f7a8a",
  "#8a6f5f",
  "#6e776b",
  "#9a8a5a",
];

export function Arrangements({ openId }: { openId?: string | null } = {}) {
  const [models, setModels] = useState<ModelBrief[]>([]);
  const [listed, setListed] = useState<Listed[]>([]);
  const [settings, setSettings] = useState<Settings>({
    gap_mm: 0,
    grid_mm: 10,
    rotation_step_deg: 90,
  });
  const [members, setMembers] = useState<Member[]>([]);
  const [outlines, setOutlines] = useState<Record<string, Outline>>({});
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [msg, setMsg] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [built, setBuilt] = useState<string | null>(null);
  const [snapTo, setSnapTo] = useState<number>(0);
  const [side, setSide] = useState("right");
  const [align, setAlign] = useState("back");
  // the cover's plan, chosen before the cover is built (ADR-095)
  const [plans, setPlans] = useState<Plan[]>([]);
  const [plansFor, setPlansFor] = useState("");
  const [footprint, setFootprint] = useState("follow");
  const [builtFootprint, setBuiltFootprint] = useState<string | null>(null);
  // where the arrangement being edited stands at the Desk (ADR-115)
  const [desk, setDesk] = useState<DeskInfo | null>(null);
  const [hasCover, setHasCover] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{
    i: number;
    x: number;
    y: number;
    mx: number;
    my: number;
  } | null>(null);

  const reload = useCallback(() => {
    call<Listed[]>("/api/arrangements")
      .then(setListed)
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    api
      .models()
      .then((ms) =>
        setModels(
          ms.filter(
            (m) => !m.id.startsWith("arr-") && m.files.includes("model.glb"),
          ),
        ),
      );
    call<Settings>("/api/arrangements/settings")
      .then((s) => {
        setSettings(s);
        if (s.footprint) setFootprint(s.footprint);
      })
      .catch(() => undefined);
    reload();
  }, [reload]);

  const need = useMemo(
    () =>
      [...new Set(members.map((m) => m.model_id))].filter(
        (id) => !outlines[id],
      ),
    [members, outlines],
  );
  useEffect(() => {
    for (const id of need)
      call<Outline>(`/api/arrangements/outline/${id}`)
        .then((o) => setOutlines((cur) => ({ ...cur, [id]: o })))
        .catch((e) => setMsg(String(e.message ?? e)));
  }, [need]);

  // the plans to choose from, asked again a moment after the pieces stop moving
  const placement = JSON.stringify([members, settings.gap_mm]);
  useEffect(() => {
    if (!members.length) {
      setPlans([]);
      setPlansFor("");
      return;
    }
    const t = setTimeout(() => {
      call<{ options: Plan[] }>("/api/arrangements/footprints", {
        members,
        gap_mm: settings.gap_mm,
      })
        .then((r) => {
          setPlans(r.options);
          setPlansFor(placement);
        })
        .catch((e) => setMsg(String(e.message ?? e)));
    }, 600);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [placement]);

  const refreshDesk = useCallback((id: string) => {
    call<{ desk: DeskInfo; built: boolean }>(`/api/arrangements/${id}`)
      .then((r) => {
        setDesk(r.desk);
        setHasCover(r.built);
      })
      .catch(() => undefined);
  }, []);
  const sendToDesk = async () => {
    if (!built) return;
    setMsg("");
    try {
      const r = await call<{ desk: DeskInfo }>(
        `/api/arrangements/${built}/send`,
        {},
      );
      setDesk(r.desk);
      reload();
    } catch (e) {
      setMsg(String((e as Error).message ?? e));
    }
  };

  // the job building the cover: followed until it is done
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const t = setTimeout(async () => {
      try {
        const j = await api.job(job.id);
        setJob(j);
        if (j.status === "done" || j.status === "failed") {
          reload();
          refreshDesk(j.model_id);
        }
      } catch (e) {
        setMsg(String(e));
      }
    }, 2000);
    return () => clearTimeout(t);
  }, [job, reload, refreshDesk]);

  const placed = members.map((m) =>
    outlines[m.model_id] ? placedRings(outlines[m.model_id], m) : [],
  );
  const pts = placed.flat(2);
  const box = pts.length
    ? {
        x0: Math.min(...pts.map((p) => p[0])),
        x1: Math.max(...pts.map((p) => p[0])),
        y0: Math.min(...pts.map((p) => p[1])),
        y1: Math.max(...pts.map((p) => p[1])),
      }
    : { x0: -1000, x1: 1000, y0: -1000, y1: 1000 };
  const pad = 400;
  const view = {
    x: box.x0 - pad,
    y: -(box.y1 + pad),
    w: box.x1 - box.x0 + 2 * pad,
    h: box.y1 - box.y0 + 2 * pad,
  };

  const toPlan = (e: React.PointerEvent) => {
    const svg = svgRef.current!;
    const p = svg.createSVGPoint();
    p.x = e.clientX;
    p.y = e.clientY;
    const q = p.matrixTransform(svg.getScreenCTM()!.inverse());
    return { x: q.x, y: -q.y }; // the plan's y runs up; the screen's down
  };
  const grid = (v: number) =>
    Math.round(v / settings.grid_mm) * settings.grid_mm;
  const update = (i: number, change: Partial<Member>) =>
    setMembers((ms) => ms.map((m, k) => (k === i ? { ...m, ...change } : m)));

  const add = (id: string) => {
    const right = pts.length ? box.x1 + 600 : 0;
    setMembers((ms) => [
      ...ms,
      { model_id: id, x_mm: grid(right), y_mm: 0, rot_deg: 0, mirror: false },
    ]);
    setSel(members.length);
    setSearch("");
  };
  const snap = async () => {
    if (sel === null || sel === snapTo) return;
    try {
      const r = await call<{ member: Member }>("/api/arrangements/snap", {
        members,
        i: sel,
        j: snapTo,
        side,
        align,
      });
      update(sel, r.member);
    } catch (e) {
      setMsg(String((e as Error).message ?? e));
    }
  };
  const build = async (plan: string = footprint) => {
    setMsg("");
    try {
      const r = await call<{
        model_id: string;
        job: Job;
        footprint: string;
        desk?: DeskInfo;
      }>("/api/arrangements", {
        name: name || "Arrangement",
        members,
        model_id: editing,
        gap_mm: settings.gap_mm,
        footprint: plan,
      });
      setEditing(r.model_id);
      setBuilt(r.model_id);
      setBuiltFootprint(r.footprint);
      setJob(r.job);
      if (r.desk) setDesk(r.desk);
      setHasCover(false);
    } catch (e) {
      setMsg(String((e as Error).message ?? e));
    }
  };
  const open = async (id: string) => {
    const doc = await call<{
      name: string;
      members: Member[];
      footprint?: string;
    }>(`/api/arrangements/${id}`);
    // arrangements made before ADR-095 have no choice stored: they were built smoothed, and
    // the default plan is offered for the next build
    setFootprint(doc.footprint ?? settings.footprint ?? "follow");
    setBuiltFootprint(doc.footprint ?? "smooth");
    setMembers(
      doc.members.map(({ model_id, x_mm, y_mm, rot_deg, mirror }) => ({
        model_id,
        x_mm,
        y_mm,
        rot_deg,
        mirror,
      })),
    );
    setName(doc.name);
    setEditing(id);
    setBuilt(id);
    setSel(null);
    setJob(null);
    refreshDesk(id);
  };
  // #/arrangements/<id>: open that arrangement (the Desk card's "Edit arrangement")
  useEffect(() => {
    if (openId && openId !== editing) void open(openId).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId]);
  const found =
    search.length < 2
      ? []
      : models.filter((m) => m.id.includes(search.toLowerCase())).slice(0, 12);
  const running =
    !!job && (job.status === "queued" || job.status === "running");

  return (
    <div className="arrange">
      <section className="card">
        <h2>Arrangements</h2>
        <p className="muted">
          Place furniture from the catalogue together, then build one cover over
          the whole. Drag a piece to move it; select it to turn, mirror or snap
          it against another piece.
        </p>
        <div className="arrange-head">
          <input
            placeholder="Name, e.g. Portofino corner left"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <div className="arrange-find">
            <input
              placeholder="Add a model: search the catalogue…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {found.length > 0 && (
              <ul>
                {found.map((m) => (
                  <li key={m.id}>
                    <button className="link" onClick={() => add(m.id)}>
                      {m.id}{" "}
                      {m.size_mm && (
                        <span className="muted">
                          (
                          {m.size_mm.map((v) => Math.round(v / 10)).join(" × ")}{" "}
                          cm)
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        {listed.length > 0 && (
          <p className="muted">
            Arrangements:{" "}
            {listed.map((l) => (
              <button
                key={l.id}
                className="link"
                onClick={() =>
                  (window.location.hash = `#/arrangements/${l.id}`)
                }
              >
                {l.name}{" "}
                {l.desk && (
                  <span className={`arrange-pill t-${deskWords(l.desk)[0]}`}>
                    {
                      {
                        approved: "approved",
                        rejected: "rejected",
                        waiting: "waiting for approval",
                        new: "not at the Desk",
                      }[deskWords(l.desk)[0]]
                    }
                  </span>
                )}
                {l.stale.length > 0 ? " (a member changed: build again)" : ""}
              </button>
            ))}
          </p>
        )}
      </section>

      <div className="arrange-body">
        <section className="card arrange-plan">
          <div className="arrange-size">
            {pts.length > 0 && (
              <b>
                {((box.x1 - box.x0) / 10).toFixed(1)} ×{" "}
                {((box.y1 - box.y0) / 10).toFixed(1)} cm
              </b>
            )}{" "}
            <span className="muted">
              seen from above, the front at the bottom
            </span>
          </div>
          <svg
            ref={svgRef}
            viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
            onPointerMove={(e) => {
              const d = drag.current;
              if (!d) return;
              const p = toPlan(e);
              update(d.i, {
                x_mm: grid(d.x + p.x - d.mx),
                y_mm: grid(d.y + p.y - d.my),
              });
            }}
            onPointerUp={() => (drag.current = null)}
            onPointerLeave={() => (drag.current = null)}
          >
            <rect
              x={view.x}
              y={view.y}
              width={view.w}
              height={view.h}
              className="arrange-ground"
            />
            {placed.map((rings, i) => (
              <g
                key={i}
                className={sel === i ? "arrange-member on" : "arrange-member"}
                onPointerDown={(e) => {
                  const p = toPlan(e);
                  setSel(i);
                  drag.current = {
                    i,
                    x: members[i].x_mm,
                    y: members[i].y_mm,
                    mx: p.x,
                    my: p.y,
                  };
                  (e.target as Element).setPointerCapture?.(e.pointerId);
                }}
              >
                {rings.map((r, k) => (
                  <polygon
                    key={k}
                    points={r.map(([x, y]) => `${x},${-y}`).join(" ")}
                    fill={COLOURS[i % COLOURS.length]}
                    fillOpacity={0.55}
                    stroke="#1f241f"
                    strokeWidth={view.w / 400}
                  />
                ))}
                {rings.length > 0 && (
                  <text
                    x={members[i].x_mm}
                    y={-members[i].y_mm}
                    fontSize={view.w / 45}
                    textAnchor="middle"
                    className="arrange-label"
                  >
                    {i + 1}
                  </text>
                )}
              </g>
            ))}
          </svg>
        </section>

        <section className="card arrange-side">
          <h3>Pieces</h3>
          <ol>
            {members.map((m, i) => (
              <li
                key={i}
                className={sel === i ? "on" : ""}
                onClick={() => setSel(i)}
              >
                <span
                  className="dot"
                  style={{ background: COLOURS[i % COLOURS.length] }}
                />{" "}
                {m.model_id}
                <span className="muted">
                  {" "}
                  {Math.round(m.rot_deg)}°{m.mirror ? ", mirrored" : ""}
                </span>
              </li>
            ))}
          </ol>
          {sel !== null && members[sel] && (
            <div className="arrange-tools">
              <div className="row">
                <button
                  onClick={() =>
                    update(sel, {
                      rot_deg:
                        (members[sel].rot_deg -
                          settings.rotation_step_deg +
                          360) %
                        360,
                    })
                  }
                >
                  ↺ Turn
                </button>
                <button
                  onClick={() =>
                    update(sel, {
                      rot_deg:
                        (members[sel].rot_deg + settings.rotation_step_deg) %
                        360,
                    })
                  }
                >
                  ↻ Turn
                </button>
                <button
                  onClick={() => update(sel, { mirror: !members[sel].mirror })}
                >
                  Mirror
                </button>
                <button
                  className="danger"
                  onClick={() => {
                    setMembers((ms) => ms.filter((_, k) => k !== sel));
                    setSel(null);
                  }}
                >
                  Remove
                </button>
              </div>
              {members.length > 1 && (
                <div className="row">
                  <span>Snap to</span>
                  <select
                    value={snapTo}
                    onChange={(e) => setSnapTo(Number(e.target.value))}
                  >
                    {members.map((m, k) =>
                      k === sel ? null : (
                        <option key={k} value={k}>
                          {k + 1}. {m.model_id}
                        </option>
                      ),
                    )}
                  </select>
                  <select
                    value={side}
                    onChange={(e) => setSide(e.target.value)}
                  >
                    {["left", "right", "front", "back"].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                  <select
                    value={align}
                    onChange={(e) => setAlign(e.target.value)}
                  >
                    {(side === "left" || side === "right"
                      ? ["back", "front", "middle"]
                      : ["left", "right", "middle"]
                    ).map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                  <button onClick={snap}>Snap</button>
                </div>
              )}
            </div>
          )}
          {members.length > 0 && (
            <p className="muted">
              Cover plan: <b>{PLAN_NAMES[footprint]?.[0] ?? footprint}</b>{" "}
              (choose below)
            </p>
          )}
          <button
            className="primary"
            disabled={!members.length || running}
            onClick={() => build()}
          >
            {running
              ? "Building the cover…"
              : editing
                ? "Build cover again"
                : "Build cover"}
          </button>
          {built &&
            builtFootprint &&
            builtFootprint !== footprint &&
            !running && (
              <p className="muted">
                The cover was built as “
                {PLAN_NAMES[builtFootprint]?.[0] ?? builtFootprint}”: build it
                again for the plan chosen now.
              </p>
            )}
          {job && (
            <p className="muted">
              {job.status === "done"
                ? "The cover is ready."
                : job.status === "failed"
                  ? `Failed: ${job.error ?? ""}`
                  : "Calculating: cover surface, seams, flat patterns, cut pieces…"}
            </p>
          )}
          {built && (
            <p>
              <a href={`#/model/${built}`}>Open the model ↗</a>{" "}
              <span className="muted">(3D, dimensions, air vents, Unfold)</span>
            </p>
          )}
          {built && (
            <DeskStatus
              id={built}
              desk={desk}
              built={hasCover || job?.status === "done"}
              running={running}
              onSend={sendToDesk}
            />
          )}
          {msg && <p className="error">{msg}</p>}
        </section>
      </div>

      {members.length > 0 && (
        <section className="card">
          <h3>Cover plan</h3>
          <p className="muted">
            Seen from above at the hem. Choose how the cover runs round the
            pieces before it is built
            {built ? "; choosing another plan builds the cover again" : ""}.
          </p>
          {plans.length === 0 ? (
            <p className="muted">Working out the plans…</p>
          ) : (
            <div className="arrange-plans">
              {plans.map((p) => {
                const [title, note] = PLAN_NAMES[p.footprint] ?? [
                  p.footprint,
                  "",
                ];
                return (
                  <button
                    key={p.footprint}
                    className={footprint === p.footprint ? "on" : ""}
                    disabled={running}
                    onClick={() => {
                      setFootprint(p.footprint);
                      // a built cover is built again with the plan chosen
                      if (built && p.footprint !== builtFootprint)
                        void build(p.footprint);
                    }}
                  >
                    <PlanPreview plan={p} />
                    <b>
                      {title}
                      {p.footprint === (settings.footprint ?? "follow")
                        ? " — default"
                        : ""}
                    </b>
                    <span>
                      {(p.size_mm[0] / 10).toFixed(1)} ×{" "}
                      {(p.size_mm[1] / 10).toFixed(1)} cm,{" "}
                      {p.area_m2.toFixed(2)} m² seen from above
                      {p.empty_m2 > 0.005
                        ? `, of which ${p.empty_m2.toFixed(2)} m² over empty floor`
                        : ""}
                    </span>
                    <span className="muted">{note}</span>
                  </button>
                );
              })}
            </div>
          )}
          {plansFor !== placement && plans.length > 0 && (
            <p className="muted">The pieces moved: updating the plans…</p>
          )}
        </section>
      )}
    </div>
  );
}
