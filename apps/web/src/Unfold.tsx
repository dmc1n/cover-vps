// "Unfold" (ADR-085): the cover's pieces pulled apart and laid flat on a table, with their net
// and cut outlines, the allowance bands (seams, hem), the vent openings and hoods, a label per
// piece and a list of where the fabric goes. The data: /api/models/{id}/unfold.json and .bin.
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import type { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

interface FlatPiece {
  name: string;
  quantity: number;
  extra: boolean;
  net_cm: number[];
  cut_cm: number[];
  net_m2: number;
  cut_m2: number;
  seam_m2: number;
  hem_m2: number;
  ease_cm: number;
  net: number[][];
  cut: number[][];
  openings: number[][][];
  label_at: number[];
  bands: { seam?: Band[]; hem?: Band[] };
}
interface Band {
  outer: number[][];
  holes: number[][][];
}
interface Totals {
  net_m2: number;
  seam_m2: number;
  hem_m2: number;
  vents_m2: number;
  cut_m2: number;
  fabric_m2: number;
  waste_m2: number;
  roll_length_m: number;
}
interface Meta {
  points: number;
  triangles: number;
  pieces: { name: string; index: number }[];
  flat: FlatPiece[];
  totals: Totals;
}

export type FrameHook = () => void;

const PALETTE = [
  "#c4b08e",
  "#8e9a7f",
  "#b9a27a",
  "#a7b39a",
  "#d2c3a3",
  "#7f8b72",
  "#c9b797",
  "#9aa58c",
  "#bfa984",
  "#b4bea6",
];
const COLOURS = {
  seam: "#d98c3a",
  hem: "#4d7fb3",
  cut: "#3c443c",
  net: "#1f241f",
};
const SPLIT = 0.45; // the scrubber: 0 → 0.45 pulled apart, 0.45 → 1 laid flat
const SPEED = 0.0035; // per frame while playing (about 5 s for the whole way)

const ease = (x: number) => (x < 0.5 ? 2 * x * x : 1 - (-2 * x + 2) ** 2 / 2);

function textSprite(lines: string[], height: number): THREE.Sprite {
  const c = document.createElement("canvas");
  const w = 560;
  const h = 64 + (lines.length - 1) * 52;
  c.width = w;
  c.height = h;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgba(255,255,255,0.93)";
  g.strokeStyle = "#3c443c";
  g.lineWidth = 3;
  g.beginPath();
  g.roundRect(3, 3, w - 6, h - 6, 16);
  g.fill();
  g.stroke();
  g.fillStyle = "#1f241f";
  g.textAlign = "center";
  lines.forEach((l, i) => {
    g.font =
      i === 0
        ? "700 40px 'DM Sans', system-ui"
        : "500 34px 'DM Sans', system-ui";
    g.fillText(l, w / 2, 46 + i * 52);
  });
  const s = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(c),
      depthTest: false,
      transparent: true,
    }),
  );
  s.scale.set((height * w) / h, height, 1);
  s.renderOrder = 12;
  return s;
}

function fill(
  poly: number[][],
  colour: string,
  y: number,
  opacity = 0.85,
  holes: number[][][] = [],
): THREE.Mesh {
  const v = (p: number[]) => new THREE.Vector2(p[0], -p[2]);
  const shape = new THREE.Shape(poly.map(v));
  for (const h of holes) shape.holes.push(new THREE.Path(h.map(v)));
  const geo = new THREE.ShapeGeometry(shape);
  geo.rotateX(-Math.PI / 2);
  geo.translate(0, y, 0);
  return new THREE.Mesh(
    geo,
    new THREE.MeshBasicMaterial({
      color: colour,
      transparent: true,
      opacity,
      side: THREE.DoubleSide,
    }),
  );
}

function outline(
  poly: number[][],
  colour: string,
  y: number,
  dashed: boolean,
): THREE.Line {
  const pts = [...poly, poly[0]].map((p) => new THREE.Vector3(p[0], y, p[2]));
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  const mat = dashed
    ? new THREE.LineDashedMaterial({
        color: colour,
        dashSize: 0.025,
        gapSize: 0.015,
      })
    : new THREE.LineBasicMaterial({ color: colour });
  const line = new THREE.Line(geo, mat);
  if (dashed) line.computeLineDistances();
  return line;
}

function tableGroup(meta: Meta): THREE.Group {
  const g = new THREE.Group();
  const all = meta.flat.flatMap((p) => p.cut);
  const xs = all.map((p) => p[0]);
  const zs = all.map((p) => p[2]);
  const span = Math.max(
    Math.max(...xs) - Math.min(...xs),
    Math.max(...zs) - Math.min(...zs),
  );
  for (const p of meta.flat) {
    if (p.extra) g.add(fill(p.cut, "#e7dcc4", 0.004, 0.9));
    for (const b of p.bands.seam ?? [])
      g.add(fill(b.outer, COLOURS.seam, 0.005, 0.85, b.holes));
    for (const b of p.bands.hem ?? [])
      g.add(fill(b.outer, COLOURS.hem, 0.005, 0.85, b.holes));
    g.add(outline(p.cut, COLOURS.cut, 0.007, true));
    if (p.net.length) g.add(outline(p.net, COLOURS.net, 0.008, false));
    for (const o of p.openings) {
      g.add(fill(o, "#f9f6e8", 0.009, 1));
      g.add(outline(o, COLOURS.net, 0.01, false));
    }
    const lines = p.extra
      ? [`${p.name} ×${p.quantity}`, `${p.cut_cm[0]} × ${p.cut_cm[1]} cm`]
      : [
          p.quantity > 1 ? `${p.name} ×${p.quantity}` : p.name,
          `net ${p.net_cm[0]} × ${p.net_cm[1]} cm`,
          `cut ${p.cut_cm[0]} × ${p.cut_cm[1]} cm`,
        ];
    const xs2 = p.cut.map((q) => q[0]);
    const zs2 = p.cut.map((q) => q[2]);
    const pw = Math.max(...xs2) - Math.min(...xs2);
    const pd = Math.max(...zs2) - Math.min(...zs2);
    // a label as large as its piece allows, never tiny next to a large table
    const s = textSprite(lines, Math.max(Math.min(pw, pd) * 0.28, span * 0.03));
    s.position.set(p.label_at[0], 0.05, p.label_at[2]);
    g.add(s);
  }
  return g;
}

const pct = (part: number, of: number) =>
  of > 0 ? `${Math.round((100 * part) / of)} %` : "–";

export function UnfoldView({
  id,
  stamp,
  scene,
  frameHooks,
  camera,
  controls,
  hideLayers,
}: {
  id: string;
  stamp: number;
  scene: THREE.Scene | null;
  frameHooks: React.MutableRefObject<FrameHook[]>;
  camera: THREE.PerspectiveCamera | null;
  controls: OrbitControls | null;
  hideLayers: (hide: boolean) => void;
}) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState("");
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(true);
  const state = useRef({ t: 0, playing: true, frames: 0 });

  useEffect(() => {
    if (!scene) return;
    let alive = true;
    let mesh: THREE.Mesh | null = null;
    let table: THREE.Group | null = null;
    const base = `/api/models/${id}/unfold`;
    setError("");
    Promise.all([
      fetch(`${base}.json?v=${stamp}`).then(async (r) => {
        if (!r.ok)
          throw new Error(
            (await r.json().catch(() => ({}))).detail ?? r.statusText,
          );
        return r.json() as Promise<Meta>;
      }),
      fetch(`${base}.bin?v=${stamp}`).then((r) => r.arrayBuffer()),
    ])
      .then(([m, buf]) => {
        if (!alive) return;
        const n = m.points;
        const f = (k: number) => new Float32Array(buf, k * n * 12, n * 3);
        const design = f(0);
        const apart = f(1);
        const flat = f(2);
        const piece = new Uint8Array(buf, 3 * n * 12, n);
        const faces = new Uint32Array(buf.slice(3 * n * 12 + n));
        const geo = new THREE.BufferGeometry();
        geo.setAttribute(
          "position",
          new THREE.BufferAttribute(design.slice(), 3),
        );
        const col = new Float32Array(n * 3);
        const c = new THREE.Color();
        for (let i = 0; i < n; i++) {
          c.set(PALETTE[piece[i] % PALETTE.length]);
          col.set([c.r, c.g, c.b], i * 3);
        }
        geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
        geo.setIndex(new THREE.BufferAttribute(faces, 1));
        geo.computeVertexNormals();
        mesh = new THREE.Mesh(
          geo,
          new THREE.MeshStandardMaterial({
            vertexColors: true,
            side: THREE.DoubleSide,
            roughness: 0.85,
          }),
        );
        scene.add(mesh);
        table = tableGroup(m);
        table.visible = false;
        scene.add(table);
        hideLayers(true);
        // frame the cover and the table together
        const box = new THREE.Box3().setFromBufferAttribute(
          new THREE.BufferAttribute(design, 3),
        );
        box.union(
          new THREE.Box3().setFromBufferAttribute(
            new THREE.BufferAttribute(flat, 3),
          ),
        );
        const size = box.getSize(new THREE.Vector3()).length();
        const centre = box.getCenter(new THREE.Vector3());
        const box3 = (a: Float32Array) =>
          new THREE.Box3().setFromBufferAttribute(
            new THREE.BufferAttribute(a, 3),
          );
        const coverBox = box3(design);
        const tableBox = box3(flat);
        const cSize = coverBox.getSize(new THREE.Vector3()).length();
        const tSize = tableBox.getSize(new THREE.Vector3()).length();
        const coverAt = coverBox.getCenter(new THREE.Vector3());
        const tableAt = tableBox.getCenter(new THREE.Vector3());
        const views = {
          coverAt,
          coverEye: coverAt
            .clone()
            .add(
              new THREE.Vector3(0.7, 0.55, 1.0).multiplyScalar(cSize * 0.95),
            ),
          tableAt,
          tableEye: tableAt
            .clone()
            .add(new THREE.Vector3(0, 1.0, 0.18).multiplyScalar(tSize * 1.2)),
        };
        void size;
        void centre;
        setMeta(m);
        const pos = geo.getAttribute("position") as THREE.BufferAttribute;
        const arr = pos.array as Float32Array;
        let last = -1;
        const hook = () => {
          const s = state.current;
          if (s.playing) {
            s.t = Math.min(1, s.t + SPEED);
            if (s.t >= 1) s.playing = false;
          }
          if (s.t !== last) {
            last = s.t;
            const [a, b, w] =
              s.t < SPLIT
                ? [design, apart, ease(s.t / SPLIT)]
                : [apart, flat, ease((s.t - SPLIT) / (1 - SPLIT))];
            for (let k = 0; k < arr.length; k++)
              arr[k] = a[k] * (1 - w) + b[k] * w;
            pos.needsUpdate = true;
            // the camera follows: on the cover at first, straight above the table at the end
            if (camera && controls) {
              const f = ease(Math.min(1, Math.max(0, (s.t - 0.3) / 0.7)));
              controls.target.lerpVectors(views.coverAt, views.tableAt, f);
              camera.position.lerpVectors(views.coverEye, views.tableEye, f);
            }
            geo.computeVertexNormals();
            if (table) table.visible = s.t > 0.97;
          }
          s.frames += 1;
          if (s.frames % 6 === 0) {
            setT(s.t);
            setPlaying(s.playing);
          }
        };
        frameHooks.current.push(hook);
        (mesh as THREE.Mesh & { _hook?: FrameHook })._hook = hook;
      })
      .catch((e) => alive && setError(String(e.message ?? e)));
    return () => {
      alive = false;
      if (mesh) {
        const h = (mesh as THREE.Mesh & { _hook?: FrameHook })._hook;
        frameHooks.current = frameHooks.current.filter((x) => x !== h);
        scene.remove(mesh);
      }
      if (table) scene.remove(table);
      hideLayers(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, stamp, scene]);

  const seek = (v: number) => {
    state.current.t = v;
    state.current.playing = false;
    setT(v);
    setPlaying(false);
  };
  const play = () => {
    if (state.current.t >= 1) state.current.t = 0;
    state.current.playing = !state.current.playing;
    setPlaying(state.current.playing);
  };
  const tot = meta?.totals;
  return (
    <section className="card unfold">
      <div className="unfold-bar">
        <button className="primary" onClick={play} disabled={!meta}>
          {playing ? "❚❚ Pause" : t >= 1 ? "↺ Again" : "▶ Play"}
        </button>
        <input
          type="range"
          min={0}
          max={1}
          step={0.005}
          value={t}
          onChange={(e) => seek(Number(e.target.value))}
          aria-label="Unfold: from the cover to flat on the table"
        />
        <span className="muted">
          {t < 0.05
            ? "on the cover"
            : t < SPLIT + 0.05
              ? "pulled apart"
              : t < 0.97
                ? "laying flat"
                : "flat on the table"}
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      {!meta && !error && <p className="muted">Unfolding the pieces…</p>}
      {tot && (
        <>
          <div className="unfold-legend">
            <span>
              <i style={{ background: COLOURS.net }} /> net outline (sewn size)
            </span>
            <span>
              <i className="dash" /> cut outline
            </span>
            <span>
              <i style={{ background: COLOURS.seam }} /> seam allowance
            </span>
            <span>
              <i style={{ background: COLOURS.hem }} /> hem
            </span>
            <span>
              <i style={{ background: "#e7dcc4" }} /> vent hoods and membranes
            </span>
          </div>
          <table className="list unfold-table">
            <thead>
              <tr>
                <th>Piece</th>
                <th>Net (cm)</th>
                <th>Cut (cm)</th>
                <th>Net m²</th>
                <th>Seams m²</th>
                <th>Hem m²</th>
                <th>Ease</th>
              </tr>
            </thead>
            <tbody>
              {meta!.flat.map((p) => (
                <tr key={p.name}>
                  <td>
                    {p.name}
                    {p.quantity > 1 ? ` ×${p.quantity}` : ""}
                  </td>
                  <td>{p.extra ? "–" : `${p.net_cm[0]} × ${p.net_cm[1]}`}</td>
                  <td>{`${p.cut_cm[0]} × ${p.cut_cm[1]}`}</td>
                  <td>{p.extra ? "–" : p.net_m2.toFixed(2)}</td>
                  <td>{p.extra ? "–" : p.seam_m2.toFixed(2)}</td>
                  <td>{p.extra ? "–" : p.hem_m2.toFixed(2)}</td>
                  <td>{p.ease_cm ? `${p.ease_cm} cm` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <table className="list unfold-totals">
            <tbody>
              <tr>
                <td>The cover's surface (net)</td>
                <td>{tot.net_m2.toFixed(2)} m²</td>
                <td />
              </tr>
              <tr>
                <td>+ seam allowances</td>
                <td>{tot.seam_m2.toFixed(2)} m²</td>
                <td>{pct(tot.seam_m2, tot.net_m2)}</td>
              </tr>
              <tr>
                <td>+ hem</td>
                <td>{tot.hem_m2.toFixed(2)} m²</td>
                <td>{pct(tot.hem_m2, tot.net_m2)}</td>
              </tr>
              <tr>
                <td>+ vent hoods and membranes</td>
                <td>{tot.vents_m2.toFixed(2)} m²</td>
                <td>{pct(tot.vents_m2, tot.net_m2)}</td>
              </tr>
              <tr>
                <td>= cut pieces</td>
                <td>{tot.cut_m2.toFixed(2)} m²</td>
                <td>{pct(tot.cut_m2 - tot.net_m2, tot.net_m2)} extra</td>
              </tr>
              <tr>
                <td>+ left on the roll (between the pieces)</td>
                <td>{tot.waste_m2.toFixed(2)} m²</td>
                <td>{pct(tot.waste_m2, tot.net_m2)}</td>
              </tr>
              <tr className="sum">
                <td>= fabric used: {tot.roll_length_m.toFixed(2)} m of roll</td>
                <td>{tot.fabric_m2.toFixed(2)} m²</td>
                <td>
                  {pct(tot.fabric_m2 - tot.net_m2, tot.net_m2)} over the surface
                </td>
              </tr>
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
