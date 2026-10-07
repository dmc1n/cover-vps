// Arrangements (ADR-089): furniture from the catalogue placed together, then one cover over the
// whole. The top view shows each member's real footprint; drag to move, turn by 90°, mirror,
// or snap one member against another's side. "Build cover" makes the arrangement a model
// (arr-<name>) and calculates its cover like any model.
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
}
interface Listed {
  id: string;
  name: string;
  size_mm: number[];
  members: string[];
  stale: string[];
  built: boolean;
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

export function Arrangements() {
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
      .then(setSettings)
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

  // the job building the cover: followed until it is done
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const t = setTimeout(async () => {
      try {
        const j = await api.job(job.id);
        setJob(j);
        if (j.status === "done" || j.status === "failed") reload();
      } catch (e) {
        setMsg(String(e));
      }
    }, 2000);
    return () => clearTimeout(t);
  }, [job, reload]);

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
  const build = async () => {
    setMsg("");
    try {
      const r = await call<{ model_id: string; job: Job }>(
        "/api/arrangements",
        {
          name: name || "Arrangement",
          members,
          model_id: editing,
          gap_mm: settings.gap_mm,
        },
      );
      setEditing(r.model_id);
      setBuilt(r.model_id);
      setJob(r.job);
    } catch (e) {
      setMsg(String((e as Error).message ?? e));
    }
  };
  const open = async (id: string) => {
    const doc = await call<{ name: string; members: Member[] }>(
      `/api/arrangements/${id}`,
    );
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
  };
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
              <button key={l.id} className="link" onClick={() => open(l.id)}>
                {l.name}{" "}
                {l.stale.length > 0 ? "(a member changed: build again)" : ""}
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
          <button
            className="primary"
            disabled={!members.length || running}
            onClick={build}
          >
            {running
              ? "Building the cover…"
              : editing
                ? "Build cover again"
                : "Build cover"}
          </button>
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
          {msg && <p className="error">{msg}</p>}
        </section>
      </div>
    </div>
  );
}
