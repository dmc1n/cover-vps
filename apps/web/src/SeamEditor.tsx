import { useEffect, useMemo, useRef, useState } from "react";
import { fileUrl, Job } from "./api";

// The seam editor: a top view of the cover (contour lines show the folds) with the seams.
// Hand-placed seams are what `seams.json` holds: points on the outline for the vertical skirt
// seams, and lines across the top. Saving cuts and flattens again.

type Pt = [number, number];

interface Plan {
  extent: [number, number, number, number];
  outline: Pt[];
  seams: { id: string; kind: string; points: Pt[] }[];
  panels: { name: string; region: string; at: Pt }[];
  manual: { skirt_seams?: Pt[]; top_seams?: Pt[][] } | null;
  auto: { skirt_seams?: Pt[]; top_seams?: Pt[][] } | null;
  image: string;
  proposals: { panel: string; points: Pt[] }[];
}

type Mode = "move" | "draw" | "skirt" | "delete";
const MODE_HELP: Record<Mode, string> = {
  move: "Drag a point to move it.",
  draw: "Click to add points of a new seam across the top; double-click (or Finish) to end it.",
  skirt: "Click on the outline to add a vertical skirt seam there.",
  delete: "Click a point to take it out, or a line to delete the whole seam.",
};

export function SeamEditor({ id, stamp, onJob }: { id: string; stamp: number; onJob: (j: Job) => void }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState("");
  const [skirt, setSkirt] = useState<Pt[]>([]);
  const [skirtAuto, setSkirtAuto] = useState(true); // the skirt seams are still the automatic ones
  const [tops, setTops] = useState<Pt[][]>([]);
  const [drawing, setDrawing] = useState<Pt[] | null>(null);
  const [mode, setMode] = useState<Mode>("move");
  const [dirty, setDirty] = useState(false);
  const [drag, setDrag] = useState<{ line: number; point: number } | { skirt: number } | null>(null);
  const svg = useRef<SVGSVGElement>(null);

  useEffect(() => {
    fetch(`/api/models/${id}/plan`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json()).detail ?? r.statusText);
        return (await r.json()) as Plan;
      })
      .then((p) => {
        setPlan(p);
        const start = p.manual ?? p.auto ?? {};
        setSkirt((p.manual?.skirt_seams ?? p.auto?.skirt_seams ?? []) as Pt[]);
        setSkirtAuto(!p.manual?.skirt_seams);
        setTops((start.top_seams ?? []) as Pt[][]);
        setDirty(false);
      })
      .catch((e) => setError(String(e)));
  }, [id, stamp]);

  const [xmin, ymin, xmax, ymax] = plan?.extent ?? [0, 0, 1, 1];
  const w = xmax - xmin;
  const h = ymax - ymin;
  const r = Math.max(w, h) / 160; // handle size in mm
  const toPlan = (e: { clientX: number; clientY: number }): Pt => {
    const s = svg.current!;
    const pt = s.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(s.getScreenCTM()!.inverse());
    return [Math.round(p.x * 10) / 10, Math.round(-p.y * 10) / 10];
  };
  const nearestOnOutline = (p: Pt): Pt => {
    let best: Pt = p;
    let bd = Infinity;
    const o = plan!.outline;
    for (let i = 0; i + 1 < o.length; i++) {
      const [ax, ay] = o[i];
      const [bx, by] = o[i + 1];
      const dx = bx - ax;
      const dy = by - ay;
      const t = Math.max(0, Math.min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy || 1)));
      const q: Pt = [ax + t * dx, ay + t * dy];
      const d = Math.hypot(q[0] - p[0], q[1] - p[1]);
      if (d < bd) {
        bd = d;
        best = [Math.round(q[0] * 10) / 10, Math.round(q[1] * 10) / 10];
      }
    }
    return best;
  };

  const change = (fn: () => void) => {
    fn();
    setDirty(true);
  };

  const onBackgroundClick = (e: React.MouseEvent) => {
    const p = toPlan(e);
    if (mode === "draw") change(() => setDrawing([...(drawing ?? []), p]));
    if (mode === "skirt") change(() => { setSkirt([...skirt, nearestOnOutline(p)]); setSkirtAuto(false); });
  };
  const finish = () => {
    if (drawing && drawing.length >= 2) change(() => setTops([...tops, drawing]));
    setDrawing(null);
  };
  const onMove = (e: React.PointerEvent) => {
    if (!drag) return;
    const p = toPlan(e);
    if ("skirt" in drag) {
      const next = [...skirt];
      next[drag.skirt] = nearestOnOutline(p);
      setSkirt(next);
      setSkirtAuto(false);
    } else {
      const next = tops.map((l) => [...l]);
      next[drag.line][drag.point] = p;
      setTops(next);
    }
    setDirty(true);
  };

  const save = async (automatic: boolean) => {
    setError("");
    const body = automatic
      ? { automatic: true }
      : { skirt_seams: skirtAuto || !skirt.length ? null : skirt, top_seams: tops };
    const res = await fetch(`/api/models/${id}/seams`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const out = await res.json();
    if (!res.ok) {
      setError(out.detail ?? res.statusText);
      return;
    }
    setDirty(false);
    if (out.job) onJob(out.job as Job);
  };

  const background = useMemo(
    () =>
      plan?.seams.map((s, i) => (
        <polyline
          key={i}
          className={`seam-now ${s.kind}`}
          points={s.points.map(([x, y]) => `${x},${-y}`).join(" ")}
        />
      )),
    [plan],
  );

  if (error && !plan) return <p className="error">{error}</p>;
  if (!plan) return <p className="muted">Loading the top view…</p>;

  return (
    <div className="seam-editor">
      <div className="settings-bar">
        {(["move", "draw", "skirt", "delete"] as Mode[]).map((m) => (
          <button key={m} className={mode === m ? "active-mode" : ""} onClick={() => { setMode(m); setDrawing(null); }}>
            {{ move: "Move points", draw: "Draw a top seam", skirt: "Add a skirt seam", delete: "Delete" }[m]}
          </button>
        ))}
        {drawing && <button onClick={finish}>Finish seam</button>}
        <button className="primary" disabled={!dirty} onClick={() => save(false)}>
          Save and recut
        </button>
        <button onClick={() => save(true)} title="Forget the hand-placed seams">
          Use automatic seams
        </button>
        <span className="muted">{MODE_HELP[mode]}</span>
      </div>
      {error && <p className="error">{error}</p>}
      <p className="muted">
        Grey: the seams of the last run. Blue: your seams ({plan.manual ? "from seams.json" : "starting from the automatic ones"});
        orange dashed: a seam the program proposes where a piece stretches too much (click it to add it);
        squares: vertical skirt seams{skirtAuto ? " (automatic until you move one)" : ""}. The contour lines (equal height) show where the top folds.
      </p>
      <svg
        ref={svg}
        className="plan"
        viewBox={`${xmin} ${-ymax} ${w} ${h}`}
        onClick={onBackgroundClick}
        onDoubleClick={() => mode === "draw" && finish()}
        onPointerMove={onMove}
        onPointerUp={() => setDrag(null)}
        onPointerLeave={() => setDrag(null)}
      >
        <image href={`${fileUrl(id, plan.image)}?v=${stamp}`} x={xmin} y={-ymax} width={w} height={h} preserveAspectRatio="none" />
        <polygon className="outline" points={plan.outline.map(([x, y]) => `${x},${-y}`).join(" ")} />
        {background}
        {plan.panels.map((p) => (
          <text key={p.name} x={p.at[0]} y={-p.at[1]} fontSize={r * 3.2} className="panel-name">
            {p.name}
          </text>
        ))}
        {tops.map((line, li) => (
          <g key={li}>
            <polyline
              className="seam-mine"
              strokeWidth={r * 0.6}
              points={line.map(([x, y]) => `${x},${-y}`).join(" ")}
              onClick={(e) => {
                if (mode !== "delete") return;
                e.stopPropagation();
                change(() => setTops(tops.filter((_, i) => i !== li)));
              }}
            />
            {line.map(([x, y], pi) => (
              <circle
                key={pi}
                cx={x}
                cy={-y}
                r={r}
                className="handle"
                onPointerDown={(e) => {
                  e.stopPropagation();
                  if (mode === "move") setDrag({ line: li, point: pi });
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (mode !== "delete") return;
                  change(() =>
                    setTops(
                      tops
                        .map((l, i) => (i === li ? l.filter((_, j) => j !== pi) : l))
                        .filter((l) => l.length >= 2),
                    ),
                  );
                }}
              />
            ))}
          </g>
        ))}
        {plan.proposals
          .filter((pr) => !tops.some((t) => t.length === pr.points.length && t.every((q, i) => q[0] === pr.points[i][0] && q[1] === pr.points[i][1])))
          .map((pr, i) => (
            <g key={`p${i}`} className="proposal" onClick={(e) => { e.stopPropagation(); change(() => setTops([...tops, pr.points])); }}>
              <title>Proposed seam for {pr.panel}: click to add it</title>
              <polyline strokeWidth={r * 0.6} points={pr.points.map(([x, y]) => `${x},${-y}`).join(" ")} />
              <text x={(pr.points[0][0] + pr.points[1][0]) / 2} y={-(pr.points[0][1] + pr.points[1][1]) / 2} fontSize={r * 3}>
                + proposed for {pr.panel}
              </text>
            </g>
          ))}
        {drawing && (
          <polyline className="seam-drawing" strokeWidth={r * 0.6} points={drawing.map(([x, y]) => `${x},${-y}`).join(" ")} />
        )}
        {skirt.map(([x, y], i) => (
          <rect
            key={i}
            x={x - r * 1.2}
            y={-y - r * 1.2}
            width={r * 2.4}
            height={r * 2.4}
            className="skirt-handle"
            onPointerDown={(e) => {
              e.stopPropagation();
              if (mode === "move") setDrag({ skirt: i });
            }}
            onClick={(e) => {
              e.stopPropagation();
              if (mode === "delete")
                change(() => {
                  setSkirt(skirt.filter((_, j) => j !== i));
                  setSkirtAuto(false);
                });
            }}
          />
        ))}
      </svg>
    </div>
  );
}
