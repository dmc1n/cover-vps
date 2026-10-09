// Measuring on the 3D cover (ADR-111). The owner, 9 Oct 2026: "we have sewn some covers, and
// for checking it's easier if we have sizes in the 3D part, for example the height of the air
// vents and their placement."
//
// - MeasureTool: click (or tap) two points on the cover; the point snaps to a vent corner, a
//   seam's end, a corner of the mesh, a seam or the hem when it is close on screen. Shown: the
//   straight distance, the height difference and the distance along the fabric (the shortest
//   path over the cover, as a tape measure on a sewn cover goes; worked out by the server).
// - VentSizes: every air vent's opening, its bottom edge above the hem and the distance to the
//   seam or corner on each side, the numbers of the cutting file (vents.json), drawn on the
//   cover and listed below it.
//
// The engine works in mm, Z up; the scene in metres, Y up: (x, y, z) mm -> (x, z, -y) / 1000.
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { fileUrl } from "./api";
import type { FrameHook } from "./Unfold";

export const toScene = (p: number[]) =>
  new THREE.Vector3(p[0] / 1000, p[2] / 1000, -p[1] / 1000);
export const toMm = (v: THREE.Vector3) => [v.x * 1000, -v.z * 1000, v.y * 1000];
/** mm as cm with one decimal: the studio's unit for sizes on screen */
export const cm1 = (mm: number) => `${(mm / 10).toFixed(1)} cm`;
const signedCm = (mm: number) =>
  `${mm > 0 ? "+" : mm < 0 ? "−" : "±"}${Math.abs(mm / 10).toFixed(1)} cm`;

const SNAP_PX = 14; // a mouse point this close (screen pixels) to a corner or line snaps to it
const SNAP_TOUCH_PX = 26; // a finger is less precise
const CLICK_PX = 6; // a press that moved more than this was a turn of the view, not a click
const LABEL_H = 0.028; // label height as an angle (screen-constant size)
const SEE_THROUGH = 0.03; // m: a snap point this far behind the surface hit is hidden

export interface VentM {
  number?: number;
  piece: string;
  centre_mm: number[];
  corners_mm: number[][];
  normal: number[];
  size_mm: number[];
  above_hem_mm?: number;
  bottom_z_mm?: number;
  bottom_edge?: string;
  height_line_mm?: number[][];
  sides?: Record<
    "left" | "right",
    { to: string; name: string; mm: number; line_mm: number[][] }
  >;
}
interface SnapDoc {
  seams: { id: string; panels: string[]; points_mm: number[][] }[];
  edges: number[][][];
  vents: VentM[];
  lower_edge_z_mm: number;
  box_mm: number[][];
}
interface Snap {
  p: THREE.Vector3; // scene
  kind: string; // what it snapped to, for people
  prio: number;
}
interface Measurement {
  n: number;
  a: Snap;
  b: Snap;
  straight: number; // mm
  height: number; // mm, b above a
  surface?: number | null; // mm along the fabric; undefined while it is worked out
  why?: string;
  path?: number[][];
  group: THREE.Group;
}

/** A text label of constant size on screen, drawn over everything. */
export function tag(
  text: string,
  opts: { bg?: string; fg?: string; edge?: string; h?: number } = {},
): THREE.Sprite {
  const scale = 2;
  const font = `600 ${18 * scale}px 'DM Sans', system-ui, sans-serif`;
  const c = document.createElement("canvas");
  const g0 = c.getContext("2d")!;
  g0.font = font;
  const w = Math.ceil(g0.measureText(text).width) + 22 * scale;
  const h = 30 * scale;
  c.width = w;
  c.height = h;
  const g = c.getContext("2d")!;
  g.fillStyle = opts.bg ?? "rgba(255,255,255,0.94)";
  g.strokeStyle = opts.edge ?? "#3c443c";
  g.lineWidth = 2 * scale;
  g.beginPath();
  g.roundRect(scale, scale, w - 2 * scale, h - 2 * scale, 9 * scale);
  g.fill();
  g.stroke();
  g.fillStyle = opts.fg ?? "#1f241f";
  g.font = font;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(text, w / 2, h / 2 + scale);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: tex,
      depthTest: false,
      transparent: true,
      sizeAttenuation: false,
    }),
  );
  const hh = opts.h ?? LABEL_H;
  sprite.scale.set((hh * w) / h, hh, 1);
  sprite.renderOrder = 20;
  sprite.userData.text = text;
  return sprite;
}

function dot(colour: string, size = 0.012): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = c.height = 32;
  const g = c.getContext("2d")!;
  g.fillStyle = colour;
  g.strokeStyle = "#fff";
  g.lineWidth = 5;
  g.beginPath();
  g.arc(16, 16, 12, 0, Math.PI * 2);
  g.fill();
  g.stroke();
  const s = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(c),
      depthTest: false,
      transparent: true,
      sizeAttenuation: false,
    }),
  );
  s.scale.set(size, size, 1);
  s.renderOrder = 21;
  return s;
}

function line(
  pts: THREE.Vector3[],
  colour: string,
  over = true,
  dashed = false,
): THREE.Line {
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  const mat = dashed
    ? new THREE.LineDashedMaterial({
        color: colour,
        depthTest: !over,
        dashSize: 0.02,
        gapSize: 0.012,
        transparent: true,
      })
    : new THREE.LineBasicMaterial({
        color: colour,
        depthTest: !over,
        transparent: true,
      });
  const l = new THREE.Line(geo, mat);
  if (dashed) l.computeLineDistances();
  l.renderOrder = over ? 19 : 5;
  return l;
}

function dispose(o: THREE.Object3D) {
  o.traverse((x) => {
    const m = x as THREE.Mesh;
    m.geometry?.dispose();
    const mats = Array.isArray(m.material) ? m.material : [m.material];
    for (const mat of mats) {
      if (!mat) continue;
      (mat as THREE.SpriteMaterial).map?.dispose();
      mat.dispose();
    }
  });
}

/** The snap data (seams, hem, vents) of a cover, fetched once per cover. */
function useSnaps(id: string, stamp: number, on: boolean) {
  const [doc, setDoc] = useState<SnapDoc | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!on) return;
    let alive = true;
    fetch(`/api/models/${id}/measure.json?v=${stamp}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json()).detail ?? `${r.status}`);
        return r.json() as Promise<SnapDoc>;
      })
      .then((d) => alive && setDoc(d))
      .catch((e) => alive && setErr(String(e.message ?? e)));
    return () => {
      alive = false;
    };
  }, [id, stamp, on]);
  return { doc, err };
}

const CORNER_NAMES = ["bottom left", "bottom right", "top right", "top left"];

export function MeasureTool({
  id,
  stamp,
  scene,
  camera,
  canvas,
  pickables,
}: {
  id: string;
  stamp: number;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  canvas: HTMLCanvasElement;
  pickables: () => THREE.Object3D[];
}) {
  const { doc, err } = useSnaps(id, stamp, true);
  const [list, setList] = useState<Measurement[]>([]);
  const [first, setFirst] = useState<Snap | null>(null);
  const [hover, setHover] = useState("");
  const listRef = useRef(list);
  listRef.current = list;
  const firstRef = useRef(first);
  firstRef.current = first;
  const count = useRef(0);
  const overlay = useMemo(() => new THREE.Group(), []);

  // what can be snapped to, in scene coordinates
  const targets = useMemo(() => {
    const points: { p: THREE.Vector3; kind: string }[] = [];
    const segs: { a: THREE.Vector3; b: THREE.Vector3; kind: string }[] = [];
    if (!doc) return { points, segs };
    doc.vents.forEach((v, i) =>
      v.corners_mm.forEach((c, k) =>
        points.push({
          p: toScene(c),
          kind: `vent V${v.number ?? i + 1} corner, ${CORNER_NAMES[k]}`,
        }),
      ),
    );
    for (const s of doc.seams) {
      const pts = s.points_mm.map(toScene);
      points.push({ p: pts[0], kind: `end of seam ${s.id}` });
      points.push({ p: pts[pts.length - 1], kind: `end of seam ${s.id}` });
      for (let i = 0; i + 1 < pts.length; i++)
        segs.push({ a: pts[i], b: pts[i + 1], kind: `seam ${s.id}` });
    }
    for (const e of doc.edges) {
      const pts = e.map(toScene);
      const low = Math.max(...e.map((p) => p[2])) <= doc.lower_edge_z_mm + 5;
      for (let i = 0; i + 1 < pts.length; i++)
        segs.push({
          a: pts[i],
          b: pts[i + 1],
          kind: low ? "hem (lower edge)" : "free edge",
        });
    }
    return { points, segs };
  }, [doc]);

  useEffect(() => {
    scene.add(overlay);
    return () => {
      scene.remove(overlay);
      dispose(overlay);
      overlay.clear();
    };
  }, [scene, overlay]);

  // the pointer: hover marker, rubber band, clicks
  useEffect(() => {
    const ray = new THREE.Raycaster();
    const marker = dot("#d4472e", 0.016);
    marker.visible = false;
    overlay.add(marker);
    let band: THREE.Line | null = null;
    let bandTag: THREE.Sprite | null = null;
    const clearBand = () => {
      for (const o of [band, bandTag]) {
        if (!o) continue;
        overlay.remove(o);
        dispose(o);
      }
      band = bandTag = null;
    };
    const ndc = (x: number, y: number) => {
      const r = canvas.getBoundingClientRect();
      return new THREE.Vector2(
        ((x - r.left) / r.width) * 2 - 1,
        -((y - r.top) / r.height) * 2 + 1,
      );
    };
    const screen = (p: THREE.Vector3) => {
      const r = canvas.getBoundingClientRect();
      const q = p.clone().project(camera);
      return new THREE.Vector2(
        ((q.x + 1) / 2) * r.width,
        ((1 - q.y) / 2) * r.height,
      );
    };
    const firstHit = (from: THREE.Vector2) => {
      ray.setFromCamera(from, camera);
      const hits = ray.intersectObjects(pickables(), true);
      return hits.find((h) => (h.object as THREE.Mesh).isMesh) ?? null;
    };
    const seen = (p: THREE.Vector3) => {
      const dir = p.clone().sub(camera.position);
      const dist = dir.length();
      ray.set(camera.position, dir.normalize());
      const hits = ray.intersectObjects(pickables(), true);
      const h = hits.find((x) => (x.object as THREE.Mesh).isMesh);
      return !h || h.distance >= dist - SEE_THROUGH;
    };
    const snapAt = (x: number, y: number, radius: number): Snap | null => {
      const at = ndc(x, y);
      const r = canvas.getBoundingClientRect();
      const px = new THREE.Vector2(x - r.left, y - r.top);
      const hit = firstHit(at);
      const cands: (Snap & { d: number })[] = [];
      for (const t of targets.points) {
        const d = screen(t.p).distanceTo(px);
        if (d <= radius) cands.push({ p: t.p, kind: t.kind, prio: 0, d });
      }
      if (hit && hit.face) {
        const mesh = hit.object as THREE.Mesh;
        const pos = mesh.geometry.getAttribute("position");
        for (const k of [hit.face.a, hit.face.b, hit.face.c]) {
          const v = new THREE.Vector3()
            .fromBufferAttribute(pos, k)
            .applyMatrix4(mesh.matrixWorld);
          const d = screen(v).distanceTo(px);
          if (d <= radius * 0.7)
            cands.push({ p: v, kind: "mesh corner", prio: 1, d });
        }
      }
      for (const s of targets.segs) {
        const a = screen(s.a);
        const b = screen(s.b);
        const ab = b.clone().sub(a);
        const len2 = ab.lengthSq();
        const t =
          len2 > 0
            ? THREE.MathUtils.clamp(px.clone().sub(a).dot(ab) / len2, 0, 1)
            : 0;
        const d = a.clone().addScaledVector(ab, t).distanceTo(px);
        if (d <= radius)
          cands.push({
            p: s.a.clone().lerp(s.b, t),
            kind: `on the ${s.kind}`,
            prio: 2,
            d,
          });
      }
      cands.sort((p, q) => p.prio - q.prio || p.d - q.d);
      for (const c of cands.slice(0, 12)) if (seen(c.p)) return c;
      if (hit) return { p: hit.point.clone(), kind: "the surface", prio: 3 };
      return null;
    };
    let down: { x: number; y: number; t: number } | null = null;
    let frame = 0;
    const move = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      cancelAnimationFrame(frame);
      const { clientX, clientY } = e;
      frame = requestAnimationFrame(() => {
        const s = snapAt(clientX, clientY, SNAP_PX);
        marker.visible = !!s;
        if (s) marker.position.copy(s.p);
        setHover(s ? s.kind : "");
        const a = firstRef.current;
        clearBand();
        if (a && s) {
          band = line([a.p, s.p], "#d4472e", true, true);
          overlay.add(band);
          bandTag = tag(cm1(a.p.distanceTo(s.p) * 1000), { edge: "#d4472e" });
          bandTag.position.copy(a.p).lerp(s.p, 0.5);
          overlay.add(bandTag);
        }
      });
    };
    const press = (e: PointerEvent) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now() };
    };
    const release = (e: PointerEvent) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      down = null;
      if (moved > CLICK_PX || e.button > 0) return;
      const s = snapAt(
        e.clientX,
        e.clientY,
        e.pointerType === "touch" ? SNAP_TOUCH_PX : SNAP_PX,
      );
      if (!s) return;
      const a = firstRef.current;
      if (!a) {
        setFirst(s);
        return;
      }
      clearBand();
      setFirst(null);
      add(a, s);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setFirst(null);
      clearBand();
    };
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerdown", press);
    canvas.addEventListener("pointerup", release);
    window.addEventListener("keydown", key);
    const cursor = canvas.style.cursor;
    canvas.style.cursor = "crosshair";
    return () => {
      cancelAnimationFrame(frame);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerdown", press);
      canvas.removeEventListener("pointerup", release);
      window.removeEventListener("keydown", key);
      canvas.style.cursor = cursor;
      clearBand();
      overlay.remove(marker);
      dispose(marker);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas, camera, targets, overlay]);

  // the first point, while the second is chosen
  useEffect(() => {
    if (!first) return;
    const d = dot("#d4472e", 0.018);
    d.position.copy(first.p);
    overlay.add(d);
    return () => {
      overlay.remove(d);
      dispose(d);
    };
  }, [first, overlay]);

  const add = (a: Snap, b: Snap) => {
    count.current += 1;
    const n = count.current;
    const am = toMm(a.p);
    const bm = toMm(b.p);
    const group = new THREE.Group();
    group.add(line([a.p, b.p], "#d4472e"));
    for (const p of [a.p, b.p]) {
      const d = dot("#d4472e");
      d.position.copy(p);
      group.add(d);
    }
    const straight = a.p.distanceTo(b.p) * 1000;
    const t = tag(`${n}: ${cm1(straight)}`, { edge: "#d4472e" });
    t.position.copy(a.p).lerp(b.p, 0.5);
    t.center.set(0.5, -0.5); // over the line
    group.add(t);
    overlay.add(group);
    const m: Measurement = {
      n,
      a,
      b,
      straight,
      height: bm[2] - am[2],
      group,
    };
    setList((l) => [...l, m]);
    fetch(`/api/models/${id}/measure/geodesic`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ a: am, b: bm }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(
        (g: {
          surface_mm: number | null;
          path_mm: number[][];
          why?: string;
        }) => {
          if (!listRef.current.some((x) => x.n === n)) return; // cleared meanwhile
          if (g.surface_mm != null && g.path_mm.length > 1) {
            const path = line(g.path_mm.map(toScene), "#2f6fd0", true, true);
            path.name = "fabric";
            group.add(path);
            // the label says both when the fabric is longer than the straight line
            group.remove(t);
            dispose(t);
            const t2 = tag(
              `${n}: ${cm1(straight)} · fabric ${cm1(g.surface_mm)}`,
              { edge: "#d4472e" },
            );
            t2.position.copy(a.p).lerp(b.p, 0.5);
            t2.center.set(0.5, -0.5);
            group.add(t2);
          }
          setList((l) =>
            l.map((x) =>
              x.n === n
                ? { ...x, surface: g.surface_mm, why: g.why, path: g.path_mm }
                : x,
            ),
          );
        },
      )
      .catch((e) =>
        setList((l) =>
          l.map((x) =>
            x.n === n
              ? { ...x, surface: null, why: String(e.message ?? e) }
              : x,
          ),
        ),
      );
  };

  const remove = (n: number) => {
    const m = listRef.current.find((x) => x.n === n);
    if (m) {
      overlay.remove(m.group);
      dispose(m.group);
    }
    setList((l) => l.filter((x) => x.n !== n));
  };
  const clear = () => {
    for (const m of listRef.current) {
      overlay.remove(m.group);
      dispose(m.group);
    }
    setList([]);
    setFirst(null);
  };

  return (
    <section
      className="measure card"
      data-testid="measure"
      data-ready={doc || err ? "1" : "0"}
    >
      <div className="measure-head">
        <strong>Measure</strong>
        <span className="muted">
          {!doc && !err
            ? "Loading the seams and vents to snap to…"
            : first
              ? "Now click the second point. Esc cancels."
              : "Click two points on the cover (they snap to vent corners, seams and the hem). Drag still turns the view."}
        </span>
        {hover && (
          <span className="measure-snap" data-testid="measure-snap">
            {hover}
          </span>
        )}
        {list.length > 0 && (
          <button className="measure-clear" onClick={clear}>
            Clear all
          </button>
        )}
      </div>
      {err && <p className="muted">Snapping is off: {err}</p>}
      {list.length > 0 && (
        <ol className="measure-list">
          {list.map((m) => (
            <li key={m.n} data-testid="measurement">
              <b className="measure-n">{m.n}</b>
              <span>
                Straight <b data-testid="straight">{cm1(m.straight)}</b>
              </span>
              <span>
                Height difference <b>{signedCm(m.height)}</b>
              </span>
              <span>
                Along the fabric{" "}
                <b data-testid="surface">
                  {m.surface === undefined
                    ? "…"
                    : m.surface === null
                      ? "–"
                      : cm1(m.surface)}
                </b>
                {m.surface === null && m.why && (
                  <em className="muted"> ({m.why})</em>
                )}
              </span>
              <span className="muted measure-from">
                from {m.a.kind} to {m.b.kind}
              </span>
              <button
                className="measure-x"
                title="Remove this measurement"
                aria-label={`Remove measurement ${m.n}`}
                onClick={() => remove(m.n)}
              >
                ×
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

const SIDE_TO: Record<string, string> = {
  seam: "seam",
  corner: "corner",
  edge: "edge",
};
const LIFT_MM = 18; // the vent's dimension lines stand this far out of the cover

export function VentSizes({
  id,
  stamp,
  scene,
  camera,
  frameHooks,
}: {
  id: string;
  stamp: number;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  frameHooks: React.MutableRefObject<FrameHook[]>;
}) {
  const [vents, setVents] = useState<VentM[] | null>(null);
  useEffect(() => {
    let alive = true;
    fetch(`${fileUrl(id, "vents.json")}?v=${stamp}`)
      .then((r) => (r.ok ? r.json() : { vents: [] }))
      .then((d: { vents: VentM[] }) => alive && setVents(d.vents ?? []))
      .catch(() => alive && setVents([]));
    return () => {
      alive = false;
    };
  }, [id, stamp]);

  useEffect(() => {
    if (!vents?.length) return;
    const root = new THREE.Group();
    const parts: { g: THREE.Group; c: THREE.Vector3; n: THREE.Vector3 }[] = [];
    vents.forEach((v, i) => {
      const g = new THREE.Group();
      const n = v.normal;
      const out = (p: number[], mm = LIFT_MM) =>
        toScene([p[0] + n[0] * mm, p[1] + n[1] * mm, p[2] + n[2] * mm]);
      const num = v.number ?? i + 1;
      const name = tag(
        `V${num} ${cm1(v.size_mm[0]).replace(" cm", "")} × ${cm1(v.size_mm[1])}`,
        { bg: "#26241f", fg: "#fff", edge: "#26241f" },
      );
      // over the opening's top edge
      const [, , tr, tl] = v.corners_mm;
      name.position.copy(out(tr, 30).lerp(out(tl, 30), 0.5));
      name.center.set(0.5, -0.35);
      g.add(name);
      if (v.height_line_mm && v.above_hem_mm != null) {
        const [lo, hi] = v.height_line_mm;
        const a = out(lo);
        const b = out(hi);
        g.add(line([a, b], "#c0392b"));
        for (const p of [a, b]) {
          const d = dot("#c0392b", 0.009);
          d.position.copy(p);
          g.add(d);
        }
        const t = tag(`↕ ${cm1(v.above_hem_mm)}`, {
          edge: "#c0392b",
          h: 0.024,
        });
        t.position.copy(a).lerp(b, 0.5);
        t.center.set(1.1, 0.5); // beside the line
        g.add(t);
      }
      for (const side of ["left", "right"] as const) {
        const s = v.sides?.[side];
        if (!s) continue;
        const a = out(s.line_mm[0]);
        const b = out(s.line_mm[1]);
        g.add(line([a, b], "#2f6fd0"));
        for (const p of [a, b]) {
          const d = dot("#2f6fd0", 0.009);
          d.position.copy(p);
          g.add(d);
        }
        const t = tag(`↔ ${cm1(s.mm)}`, { edge: "#2f6fd0", h: 0.024 });
        t.position.copy(a).lerp(b, 0.5);
        t.center.set(0.5, 1.4); // under the line
        g.add(t);
      }
      root.add(g);
      parts.push({
        g,
        c: toScene(v.centre_mm),
        n: new THREE.Vector3(n[0], n[2], -n[1]),
      });
    });
    scene.add(root);
    // a vent on the far side is not labelled through the cover
    const hook: FrameHook = () => {
      for (const p of parts)
        p.g.visible = camera.position.clone().sub(p.c).dot(p.n) > 0;
    };
    frameHooks.current.push(hook);
    return () => {
      frameHooks.current = frameHooks.current.filter((h) => h !== hook);
      scene.remove(root);
      dispose(root);
    };
  }, [vents, scene, camera, frameHooks]);

  if (!vents) return null;
  return (
    <section className="measure card" data-testid="vent-sizes">
      <div className="measure-head">
        <strong>Air vent sizes</strong>
        <span className="muted">
          From the cutting file, along the fabric. Left and right as seen from
          outside.
        </span>
      </div>
      {vents.length === 0 ? (
        <p className="muted">No air vents on this cover.</p>
      ) : (
        <table className="list vent-table">
          <thead>
            <tr>
              <th>Vent</th>
              <th>On piece</th>
              <th>Opening (W × H)</th>
              <th>Bottom edge above the hem</th>
              <th>Left: to the</th>
              <th>Right: to the</th>
              <th>Bottom above the ground</th>
            </tr>
          </thead>
          <tbody>
            {vents.map((v, i) => (
              <tr key={i} data-testid="vent-row">
                <td>V{v.number ?? i + 1}</td>
                <td>{v.piece}</td>
                <td data-testid="vent-opening">
                  {cm1(v.size_mm[0])} × {cm1(v.size_mm[1])}
                </td>
                <td data-testid="vent-above">
                  {v.above_hem_mm != null ? cm1(v.above_hem_mm) : "–"}
                  {v.bottom_edge === "above" && (
                    <em className="muted"> (over the low skirt)</em>
                  )}
                </td>
                {(["left", "right"] as const).map((side) => {
                  const s = v.sides?.[side];
                  return (
                    <td key={side} data-testid={`vent-${side}`}>
                      {s
                        ? `${SIDE_TO[s.to] ?? s.to}${s.name ? ` ${s.name}` : ""}: ${cm1(s.mm)}`
                        : "–"}
                    </td>
                  );
                })}
                <td>{v.bottom_z_mm != null ? cm1(v.bottom_z_mm) : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
