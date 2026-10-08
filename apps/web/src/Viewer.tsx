import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { UnfoldView, type FrameHook } from "./Unfold";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Drape, fileUrl, Rain } from "./api";

// The 3D view: the furniture, the cover surface (water spots in red) and the panels, each a
// layer that can be switched on and off. The GLB files are in metres, Y up.

interface Layer {
  file: string;
  label: string;
  opacity: number;
}

const LAYERS: Layer[] = [
  { file: "model.glb", label: "Furniture", opacity: 1 },
  { file: "balloons.glb", label: "Balloons", opacity: 1 },
  { file: "chairs.glb", label: "Chair space", opacity: 0.35 },
  { file: "preview.glb", label: "Cover surface", opacity: 0.55 },
  { file: "panels.glb", label: "Panels", opacity: 1 },
];

// Rain drops: the paths are in mm, Z up (the engine's coordinates); the scene is glTF (metres,
// Y up): x, z, -y.
const toScene = (p: number[]) =>
  new THREE.Vector3(p[0] / 1000, p[2] / 1000, -p[1] / 1000);
const DROP_SPEED = 0.6; // path points per frame
const DROPS_SHOWN = 160;
const DRAPE_SPEED = 0.35; // frames of the fall per screen frame

// Air vents (vents.json, ADR-073): the opening drawn just outside the cover, with its hood.
interface Vent {
  piece: string;
  centre_mm: number[];
  corners_mm: number[][]; // bottom left, bottom right, top right, top left, from outside
  normal: number[];
  size_mm: number[];
}
const VENT_LIFT_MM = 4; // the opening sits this far outside the cover, so it is never hidden
const HOOD_MM = 60; // how far the hood hint stands out at its lower edge
const VENTS_KEY = "viewer.vents";
const ventsSaved = () => {
  try {
    return localStorage.getItem(VENTS_KEY) === "1";
  } catch {
    return false;
  }
};

function ventGroup(vents: Vent[]): THREE.Group {
  const group = new THREE.Group();
  const opening = new THREE.MeshBasicMaterial({
    color: "#26241f",
    side: THREE.DoubleSide,
  });
  const hood = new THREE.MeshStandardMaterial({
    color: "#b89f74",
    side: THREE.DoubleSide,
    roughness: 0.8,
  });
  const frame = new THREE.LineBasicMaterial({ color: "#d4472e" });
  for (const v of vents) {
    const n = v.normal;
    const at = (p: number[], out: number) =>
      toScene([p[0] + n[0] * out, p[1] + n[1] * out, p[2] + n[2] * out]);
    const [bl, br, tr, tl] = v.corners_mm.map((c) => at(c, VENT_LIFT_MM));
    const quad = new THREE.BufferGeometry().setFromPoints([
      bl,
      br,
      tr,
      bl,
      tr,
      tl,
    ]);
    quad.computeVertexNormals();
    group.add(new THREE.Mesh(quad, opening));
    group.add(
      new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints([bl, br, tr, tl]),
        frame,
      ),
    );
    // the hood: from the opening's top edge, out and down over its upper part
    const mid = (a: number[], b: number[], t: number) =>
      a.map((x, i) => x + (b[i] - x) * t);
    const [cbl, cbr, ctr, ctl] = v.corners_mm;
    const lowL = at(mid(ctl, cbl, 0.35), HOOD_MM);
    const lowR = at(mid(ctr, cbr, 0.35), HOOD_MM);
    const hoodGeo = new THREE.BufferGeometry().setFromPoints([
      tl,
      tr,
      lowR,
      tl,
      lowR,
      lowL,
    ]);
    hoodGeo.computeVertexNormals();
    group.add(new THREE.Mesh(hoodGeo, hood));
  }
  return group;
}

// Dimensions (the owner, 7 Oct 2026): the cover's overall length, depth and height drawn on
// the 3D view, in cm, to compare with the drawing (not only the pieces' sizes).
const DIMS_KEY = "viewer.dims";
const dimsSaved = () => {
  try {
    return localStorage.getItem(DIMS_KEY) === "1";
  } catch {
    return false;
  }
};

function label(text: string, size: number): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = 320;
  c.height = 80;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgba(255,255,255,0.92)";
  g.strokeStyle = "#3c443c";
  g.lineWidth = 3;
  g.beginPath();
  g.roundRect(4, 4, 312, 72, 18);
  g.fill();
  g.stroke();
  g.fillStyle = "#1f241f";
  g.font = "600 40px 'DM Sans', system-ui, sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(text, 160, 42);
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(c),
      depthTest: false,
      transparent: true,
    }),
  );
  sprite.scale.set(size, size / 4, 1);
  sprite.renderOrder = 10;
  return sprite;
}

function dimGroup(box: THREE.Box3): THREE.Group {
  const g = new THREE.Group();
  const s = box.getSize(new THREE.Vector3());
  const m = box.min;
  const off = Math.max(s.x, s.z) * 0.06; // the lines stand a little away from the cover
  const mat = new THREE.LineBasicMaterial({
    color: "#c0392b",
    depthTest: false,
  });
  const line = (a: THREE.Vector3, b: THREE.Vector3, text: string) => {
    const tick = new THREE.Vector3().subVectors(b, a).normalize();
    const n =
      Math.abs(tick.y) > 0.9
        ? new THREE.Vector3(1, 0, 0)
        : new THREE.Vector3(0, 1, 0);
    const t = n.clone().multiplyScalar(off * 0.3);
    const geo = new THREE.BufferGeometry().setFromPoints([
      a,
      b,
      a.clone().sub(t),
      a.clone().add(t),
      b.clone().sub(t),
      b.clone().add(t),
    ]);
    const segs = new THREE.LineSegments(geo, mat);
    segs.renderOrder = 9;
    g.add(segs);
    const l = label(text, Math.max(s.x, s.z) * 0.18);
    l.position.copy(a).add(b).multiplyScalar(0.5);
    g.add(l);
  };
  const cm = (v: number) => `${(v * 100).toFixed(1)} cm`; // the scene is in metres
  const y0 = m.y + 0.002;
  line(
    new THREE.Vector3(m.x, y0, box.max.z + off),
    new THREE.Vector3(box.max.x, y0, box.max.z + off),
    cm(s.x),
  );
  line(
    new THREE.Vector3(box.max.x + off, y0, m.z),
    new THREE.Vector3(box.max.x + off, y0, box.max.z),
    cm(s.z),
  );
  line(
    new THREE.Vector3(m.x - off, m.y, box.max.z + off),
    new THREE.Vector3(m.x - off, box.max.y, box.max.z + off),
    cm(s.y),
  );
  return g;
}

export function Viewer({
  id,
  files,
  stamp,
  onRain,
  rainBusy,
  onDrape,
  drapeBusy,
  snapshot,
}: {
  id: string;
  files: string[];
  stamp: number;
  onRain?: () => void;
  rainBusy?: boolean;
  onDrape?: (engine?: string) => void;
  drapeBusy?: boolean;
  // set to a function that returns the current view as a PNG data URL (the Desk's pictures)
  snapshot?: MutableRefObject<(() => string | null) | null>;
}) {
  const host = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rainAnim = useRef<{
    points: THREE.Points;
    paths: THREE.Vector3[][];
    t: number[];
  } | null>(null);
  const [rain, setRain] = useState<Rain | null>(null);
  const [raining, setRaining] = useState(false);
  const [draping, setDraping] = useState(false);
  const [drape, setDrape] = useState<Drape | null>(null);
  const [water, setWater] = useState(true); // the water heatmap over the draped cover
  const [showVents, setShowVents] = useState(ventsSaved);
  const [showDims, setShowDims] = useState(dimsSaved);
  const [unfolding, setUnfolding] = useState(false);
  const [glError, setGlError] = useState("");
  const frameHooks = useRef<FrameHook[]>([]);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const drapeAnim = useRef<{
    mesh: THREE.Mesh;
    frames: Float32Array[];
    t: number;
    final: THREE.Object3D | null;
    wet: THREE.Object3D | null;
  } | null>(null);
  const waterRef = useRef(water);
  waterRef.current = water;
  const groups = useRef<Record<string, THREE.Object3D>>({});
  const available = LAYERS.filter((l) => files.includes(l.file));
  const [shown, setShown] = useState<Record<string, boolean>>(
    (): Record<string, boolean> => {
      const panels = files.includes("panels.glb");
      if (files.includes("balloons.glb")) {
        // a table: furniture and balloons, with the cover see-through over them
        return {
          "model.glb": true,
          "balloons.glb": true,
          "chairs.glb": true,
          "preview.glb": true,
          "panels.glb": false,
        };
      }
      return {
        "model.glb": !panels,
        "preview.glb": false,
        "panels.glb": panels,
      };
    },
  );

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color("#f9f6e8"); // SUNS cream
    const camera = new THREE.PerspectiveCamera(
      40,
      el.clientWidth / el.clientHeight,
      0.01,
      100,
    );
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch (e) {
      // no WebGL (switched off, blocked by a policy, no graphics driver): say so here,
      // instead of an error that blanks the whole page (8 Oct 2026, ADR-096)
      const why = e instanceof Error ? e.message : String(e);
      setGlError(why);
      if (snapshot)
        snapshot.current = () => {
          throw new Error(`3D (WebGL) does not work in this browser (${why})`);
        };
      return () => {
        if (snapshot) snapshot.current = null;
      };
    }
    setGlError("");
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(el.clientWidth, el.clientHeight);
    el.appendChild(renderer.domElement);
    scene.add(new THREE.HemisphereLight("#fffdf6", "#85886f", 1.6)); // warm light, sage ground
    const sun = new THREE.DirectionalLight("#ffffff", 1.4);
    sun.position.set(2, 4, 3);
    scene.add(sun);
    const grid = new THREE.GridHelper(4, 40, "#d6cdb6", "#ebe4d2");
    scene.add(grid);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    cameraRef.current = camera;
    controlsRef.current = controls;
    const loader = new GLTFLoader();
    const box = new THREE.Box3();
    let framed = false;
    let alive = true;
    for (const layer of available) {
      loader.load(`${fileUrl(id, layer.file)}?v=${stamp}`, (gltf) => {
        if (!alive) return;
        const root = gltf.scene;
        root.traverse((o) => {
          const mesh = o as THREE.Mesh;
          if (!mesh.isMesh) return;
          const mats = Array.isArray(mesh.material)
            ? mesh.material
            : [mesh.material];
          for (const m of mats) {
            const std = m as THREE.MeshStandardMaterial;
            std.side = THREE.DoubleSide;
            if (layer.opacity < 1) {
              std.transparent = true;
              std.opacity = layer.opacity;
              std.depthWrite = false;
            }
          }
        });
        groups.current[layer.file] = root;
        root.visible = !!shownRef.current[layer.file];
        scene.add(root);
        if (!framed) {
          box.setFromObject(root);
          const size = box.getSize(new THREE.Vector3()).length();
          const centre = box.getCenter(new THREE.Vector3());
          controls.target.copy(centre);
          camera.position
            .copy(centre)
            .add(new THREE.Vector3(0.6, 0.5, 1.0).multiplyScalar(size));
          grid.position.y = box.min.y;
          framed = true;
        }
      });
    }
    const onResize = () => {
      camera.aspect = el.clientWidth / el.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(el.clientWidth, el.clientHeight);
    };
    window.addEventListener("resize", onResize);
    renderer.setAnimationLoop(() => {
      controls.update();
      const anim = rainAnim.current;
      if (anim) {
        const pos = anim.points.geometry.getAttribute(
          "position",
        ) as THREE.BufferAttribute;
        anim.paths.forEach((path, k) => {
          anim.t[k] += DROP_SPEED;
          if (anim.t[k] >= path.length - 1) anim.t[k] = -Math.random() * 40; // fall again
          const t = Math.max(anim.t[k], 0);
          const i = Math.floor(t);
          const a = path[i];
          const b = path[Math.min(i + 1, path.length - 1)];
          const p = a.clone().lerp(b, t - i);
          if (anim.t[k] < 0) p.y += 0.4; // still falling, above the cover
          pos.setXYZ(k, p.x, p.y, p.z);
        });
        pos.needsUpdate = true;
      }
      const fall = drapeAnim.current;
      if (fall && fall.t < fall.frames.length - 1) {
        fall.t = Math.min(fall.t + DRAPE_SPEED, fall.frames.length - 1);
        const i = Math.floor(fall.t);
        const a = fall.frames[i];
        const b = fall.frames[Math.min(i + 1, fall.frames.length - 1)];
        const w = fall.t - i;
        const pos = fall.mesh.geometry.getAttribute(
          "position",
        ) as THREE.BufferAttribute;
        const arr = pos.array as Float32Array;
        for (let k = 0; k < arr.length; k++) arr[k] = a[k] * (1 - w) + b[k] * w;
        pos.needsUpdate = true;
        fall.mesh.geometry.computeVertexNormals();
        if (fall.t >= fall.frames.length - 1 && fall.final) {
          fall.mesh.visible = false; // the cover as it lies: its folds, or where water goes
          const wetShown = waterRef.current && !!fall.wet;
          fall.final.visible = !wetShown;
          if (fall.wet) fall.wet.visible = wetShown;
        }
      }
      for (const hook of frameHooks.current) hook();
      renderer.render(scene, camera);
    });
    // render and read in the same task: the drawing buffer is still there, so no
    // preserveDrawingBuffer (and its cost on every frame) is needed
    if (snapshot)
      snapshot.current = () => {
        renderer.render(scene, camera);
        return renderer.domElement.toDataURL("image/png");
      };
    return () => {
      if (snapshot) snapshot.current = null;
      alive = false;
      rainAnim.current = null;
      sceneRef.current = null;
      window.removeEventListener("resize", onResize);
      renderer.setAnimationLoop(null);
      renderer.dispose();
      el.removeChild(renderer.domElement);
      groups.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, stamp, files.join(",")]);

  // rain: the blue water surfaces (rain.glb) and drops running down their paths
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    const group = new THREE.Group();
    if (raining && rain) {
      const paths = rain.drops
        .slice(0, DROPS_SHOWN)
        .map((d) => d.path.map(toScene))
        .filter((p) => p.length > 1);
      const geo = new THREE.BufferGeometry();
      geo.setAttribute(
        "position",
        new THREE.BufferAttribute(new Float32Array(paths.length * 3), 3),
      );
      const points = new THREE.Points(
        geo,
        new THREE.PointsMaterial({
          color: "#2f7fe0",
          size: 0.025,
          transparent: true,
          opacity: 0.9,
        }),
      );
      group.add(points);
      rainAnim.current = {
        points,
        paths,
        t: paths.map(() => -Math.random() * 60),
      };
      if (files.includes("rain.glb")) {
        new GLTFLoader().load(`${fileUrl(id, "rain.glb")}?v=${stamp}`, (gltf) =>
          group.add(gltf.scene),
        );
      }
    } else {
      rainAnim.current = null;
    }
    scene.add(group);
    return () => {
      scene.remove(group);
      rainAnim.current = null;
    };
  }, [raining, rain, id, stamp, files]);

  useEffect(() => {
    if (!raining || !files.includes("rain.json")) return;
    fetch(`${fileUrl(id, "rain.json")}?v=${stamp}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setRain)
      .catch(() => setRain(null));
  }, [raining, id, stamp, files]);

  // drape: the sewn cover falling over the furniture (drape.json, drape.bin, drape.glb)
  useEffect(() => {
    if (!draping || !files.includes("drape.json")) return;
    let alive = true;
    const added: THREE.Object3D[] = [];
    Promise.all([
      fetch(`${fileUrl(id, "drape.json")}?v=${stamp}`).then(
        (r) => r.json() as Promise<Drape>,
      ),
      fetch(`${fileUrl(id, "drape.bin")}?v=${stamp}`).then((r) =>
        r.arrayBuffer(),
      ),
    ])
      .then(([doc, buf]) => {
        const scene = sceneRef.current;
        if (!alive || !scene) return;
        setDrape(doc);
        const n = doc.points_per_frame;
        const q = new Uint16Array(buf);
        const count = Math.floor(q.length / (n * 3));
        const [lo, hi] = doc.frame_box_mm;
        const frames: Float32Array[] = [];
        for (let f = 0; f < count; f++) {
          const out = new Float32Array(n * 3);
          for (let k = 0; k < n; k++) {
            const o = (f * n + k) * 3;
            const x = lo[0] + (q[o] / 65535) * (hi[0] - lo[0]);
            const y = lo[1] + (q[o + 1] / 65535) * (hi[1] - lo[1]);
            const z = lo[2] + (q[o + 2] / 65535) * (hi[2] - lo[2]);
            out[k * 3] = x / 1000; // mm Z up -> m Y up: x, z, -y
            out[k * 3 + 1] = z / 1000;
            out[k * 3 + 2] = -y / 1000;
          }
          frames.push(out);
        }
        const geo = new THREE.BufferGeometry();
        geo.setAttribute(
          "position",
          new THREE.BufferAttribute(frames[0].slice(), 3),
        );
        geo.setIndex(doc.faces.flat());
        geo.computeVertexNormals();
        const mesh = new THREE.Mesh(
          geo,
          new THREE.MeshStandardMaterial({
            color: "#85886f",
            side: THREE.DoubleSide,
            roughness: 0.9,
          }),
        );
        scene.add(mesh);
        added.push(mesh);
        drapeAnim.current = { mesh, frames, t: 0, final: null, wet: null };
        if (files.includes("drape_rain.glb"))
          new GLTFLoader().load(
            `${fileUrl(id, "drape_rain.glb")}?v=${stamp}`,
            (gltf) => {
              if (!alive || !sceneRef.current) return;
              gltf.scene.traverse((o) => {
                const m = o as THREE.Mesh;
                if (m.isMesh)
                  (m.material as THREE.MeshStandardMaterial).side =
                    THREE.DoubleSide;
              });
              gltf.scene.visible = false;
              sceneRef.current.add(gltf.scene);
              added.push(gltf.scene);
              if (drapeAnim.current) drapeAnim.current.wet = gltf.scene;
            },
          );
        new GLTFLoader().load(
          `${fileUrl(id, "drape.glb")}?v=${stamp}`,
          (gltf) => {
            if (!alive || !sceneRef.current) return;
            gltf.scene.traverse((o) => {
              const m = o as THREE.Mesh;
              if (m.isMesh)
                (m.material as THREE.MeshStandardMaterial).side =
                  THREE.DoubleSide;
            });
            gltf.scene.visible = false;
            sceneRef.current.add(gltf.scene);
            added.push(gltf.scene);
            if (drapeAnim.current) drapeAnim.current.final = gltf.scene;
          },
        );
      })
      .catch(() => setDrape(null));
    // the designed surface and the panels make way for the real cover
    for (const f of ["preview.glb", "panels.glb"])
      if (groups.current[f]) groups.current[f].visible = false;
    return () => {
      alive = false;
      drapeAnim.current = null;
      for (const o of added) sceneRef.current?.remove(o);
      for (const [file, obj] of Object.entries(groups.current))
        obj.visible = !!shownRef.current[file];
    };
  }, [draping, id, stamp, files]);

  useEffect(() => {
    const fall = drapeAnim.current;
    if (!fall || fall.t < fall.frames.length - 1 || !fall.final) return;
    const wetShown = water && !!fall.wet;
    fall.final.visible = !wetShown;
    if (fall.wet) fall.wet.visible = wetShown;
  }, [water]);

  // the air vents, on request (remembered in this browser)
  useEffect(() => {
    const scene = sceneRef.current;
    if (!showVents || !scene || !files.includes("vents.json")) return;
    let alive = true;
    let group: THREE.Group | null = null;
    fetch(`${fileUrl(id, "vents.json")}?v=${stamp}`)
      .then((r) => (r.ok ? r.json() : { vents: [] }))
      .then((doc: { vents: Vent[] }) => {
        if (!alive || !sceneRef.current) return;
        group = ventGroup(doc.vents ?? []);
        sceneRef.current.add(group);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (group) scene.remove(group);
    };
  }, [showVents, id, stamp, files]);

  // the overall dimensions, on request: measured on the cover (its pieces, else its surface)
  useEffect(() => {
    const scene = sceneRef.current;
    if (!showDims || !scene) return;
    let group: THREE.Group | null = null;
    let tries = 0;
    const timer = setInterval(() => {
      const cover =
        groups.current["panels.glb"] ??
        groups.current["preview.glb"] ??
        groups.current["hull.glb"] ??
        groups.current["model.glb"];
      tries += 1;
      if (!cover && tries < 40) return; // still loading
      clearInterval(timer);
      if (!cover || !sceneRef.current) return;
      const box = new THREE.Box3().setFromObject(cover);
      if (box.isEmpty()) return;
      group = dimGroup(box);
      sceneRef.current.add(group);
    }, 250);
    return () => {
      clearInterval(timer);
      if (group) scene.remove(group);
    };
  }, [showDims, id, stamp, files]);

  const shownRef = useRef(shown);
  shownRef.current = shown;
  useEffect(() => {
    for (const [file, obj] of Object.entries(groups.current))
      obj.visible = !!shown[file];
  }, [shown]);

  if (!available.length)
    return (
      <p className="muted">Nothing to show yet: the model is being imported.</p>
    );
  return (
    <div className="viewer">
      <div className="layers">
        {available.map((l) => (
          <label key={l.file}>
            <input
              type="checkbox"
              checked={!!shown[l.file]}
              onChange={(e) =>
                setShown({ ...shown, [l.file]: e.target.checked })
              }
            />
            {l.label}
          </label>
        ))}
        {files.includes("vents.json") && (
          <label title="Where the air vents sit on the cover: the opening and its hood">
            <input
              type="checkbox"
              checked={showVents}
              onChange={(e) => {
                setShowVents(e.target.checked);
                try {
                  localStorage.setItem(VENTS_KEY, e.target.checked ? "1" : "0");
                } catch {
                  /* a private window: not remembered */
                }
              }}
            />
            Show air vents
          </label>
        )}
        <label title="The cover's overall length, depth and height in cm, to compare with the drawing">
          <input
            type="checkbox"
            checked={showDims}
            onChange={(e) => {
              setShowDims(e.target.checked);
              try {
                localStorage.setItem(DIMS_KEY, e.target.checked ? "1" : "0");
              } catch {
                /* a private window: not remembered */
              }
            }}
          />
          Show dimensions
        </label>
        <span className="muted">
          Drag to turn, scroll to zoom, right-drag to move.
        </span>
        {files.includes("finished.json") && files.includes("panels.glb") && (
          <span className="rain-buttons">
            <button
              className={unfolding ? "primary" : ""}
              title="Every piece pulled apart and laid flat on a table: its net and cut size, the seam and hem allowances, and where the fabric goes"
              onClick={() => setUnfolding(!unfolding)}
            >
              {unfolding ? "Back to the cover" : "Unfold"}
            </button>
          </span>
        )}
        <span className="rain-buttons">
          {files.includes("rain.json") && (
            <button
              className={raining ? "primary" : ""}
              onClick={() => setRaining(!raining)}
            >
              {raining ? "Stop the rain" : "Rain"}
            </button>
          )}
          {onRain && (
            <button
              disabled={rainBusy}
              onClick={() => {
                setRaining(true);
                onRain();
              }}
            >
              {rainBusy
                ? "Simulating…"
                : files.includes("rain.json")
                  ? "Simulate again"
                  : "Rain simulation"}
            </button>
          )}
        </span>
        <span className="rain-buttons">
          {files.includes("drape.json") && (
            <button
              className={draping ? "primary" : ""}
              onClick={() => setDraping(!draping)}
            >
              {draping ? "Back to the design" : "Drape"}
            </button>
          )}
          {draping && files.includes("drape_rain.glb") && (
            <label>
              <input
                type="checkbox"
                checked={water}
                onChange={(e) => setWater(e.target.checked)}
              />{" "}
              Water
            </label>
          )}
          {onDrape && (
            <button
              disabled={drapeBusy}
              title="The cut pieces sewn and dropped over the furniture (Style3D, lifelike): folds where there is too much fabric, then the rain on it. About 40 minutes for a sofa; the result is kept, and other work goes on meanwhile."
              onClick={() => {
                setDraping(false);
                onDrape("default");
              }}
            >
              {drapeBusy
                ? "Draping… (about 40 min)"
                : files.includes("drape.json")
                  ? "Drape again"
                  : "Drape simulation"}
            </button>
          )}
        </span>
      </div>
      <div className="canvas" ref={host}>
        {glError && (
          <p className="gl-error" role="alert">
            The 3D view needs WebGL, which this browser does not give ({glError}
            ). Turn on “Use graphics acceleration when available” in the
            browser’s settings, or use Chrome or Firefox.
          </p>
        )}
      </div>
      {unfolding && (
        <UnfoldView
          id={id}
          stamp={stamp}
          scene={sceneRef.current}
          frameHooks={frameHooks}
          camera={cameraRef.current}
          controls={controlsRef.current}
          hideLayers={(hide) => {
            for (const [file, obj] of Object.entries(groups.current))
              obj.visible = hide ? false : !!shownRef.current[file];
          }}
        />
      )}
      {raining && rain && <RainReport rain={rain} />}
      {draping && drape && <DrapeReport drape={drape} water={water} />}
    </div>
  );
}

function DrapeReport({ drape, water }: { drape: Drape; water: boolean }) {
  const ai = drape.ai;
  const wet = drape.wet;
  const folds = ai?.verdict ? ai.verdict !== "good" : drape.fold_share_pct > 10;
  return (
    <section className={`card rain ${folds ? "risk" : "dry"}`}>
      <div className="rain-head">
        <strong>The sewn cover, dropped over the furniture</strong>
        <span className="muted">
          {drape.engine === "style3d"
            ? "Style3D (lifelike), "
            : "quick solver, "}
          {drape.points.toLocaleString()} points, {drape.seconds_simulated} s of
          falling, worked out in {Math.round(drape.run_s)} s
        </span>
      </div>
      <ul>
        <li>
          <span className="swatch fold" /> Folds (red): {drape.fold_area_m2} m²
          ({drape.fold_share_pct} % of the cover), sharpest {drape.max_fold_deg}
          °. Folds show where a piece has more fabric than the shape needs.
        </li>
        <li>
          Tightest: {drape.max_stretch_pct} % stretch; {drape.tight_share_pct} %
          of the cover near the fabric's limit.
        </li>
        <li>
          Sags up to {(drape.max_sag_mm / 10).toFixed(1)} cm below the designed
          surface (where nothing holds it).
        </li>
        <li>
          Lies on the furniture over {drape.touching_share_pct} % of its points.
        </li>
      </ul>
      {wet && (
        <div className="wet">
          <strong>Rain on the cover as it lies:</strong>{" "}
          {wet.dry
            ? "dry: the water runs off."
            : `${wet.ponds} pond(s), ${wet.pond_volume_l} l (deepest ${(wet.deepest_mm / 10).toFixed(1)} cm), ` +
              `${wet.flat_area_m2} m² flat where water stands` +
              (wet.growing_ponds
                ? `; ${wet.growing_ponds} keep growing under their weight`
                : "") +
              "."}
          {water && (
            <div className="legend">
              <span className="swatch" style={{ background: "#85886f" }} /> runs
              off
              <span className="swatch" style={{ background: "#e6be3c" }} />{" "}
              water streams past
              <span className="swatch" style={{ background: "#e67828" }} />{" "}
              flat: water stands
              <span className="swatch" style={{ background: "#b2281e" }} /> pond
            </div>
          )}
        </div>
      )}
      <p className="muted">
        The fabric values are best guesses until the fabric is measured: the
        places of the folds are right, their size is an estimate.
      </p>
    </section>
  );
}

function RainReport({ rain }: { rain: Rain }) {
  const ai = rain.ai;
  const verdict = ai?.verdict ?? (rain.dry ? "dry" : "risk");
  return (
    <section className={`card rain ${verdict}`}>
      <div className="rain-head">
        <strong>
          {verdict === "dry"
            ? "Dry: the rain runs off"
            : verdict === "wet"
              ? "Water stays on this cover"
              : "Risk of standing water"}
        </strong>
        <span className="muted">
          {rain.ponds.length} pond{rain.ponds.length === 1 ? "" : "s"} (
          {rain.pond_volume_l} l) · flat {rain.flat_area_m2} m² · off at{" "}
          {Object.entries(rain.exits)
            .filter(([, n]) => n)
            .map(([k, n]) => `${k} ${n}`)
            .join(", ")}
        </span>
      </div>
      {ai?.summary && <p>{ai.summary}</p>}
      {rain.ponds.length > 0 && (
        <ul>
          {rain.ponds.slice(0, 6).map((p, i) => (
            <li key={i}>
              Pond {i + 1}: {p.area_m2} m², up to {p.max_depth_mm} mm deep,{" "}
              {p.volume_l} l; with the fabric sagging {p.volume_with_sag_l} l
              {p.keeps_growing ? " — keeps growing under its weight" : ""}
            </li>
          ))}
        </ul>
      )}
      {rain.seams_along.length > 0 && (
        <p className="muted">
          Water runs along{" "}
          {rain.seams_along
            .map((s) => `${s.seam} (${Math.round(s.run_mm / 10)} cm)`)
            .join(", ")}
          : seams soak there.
        </p>
      )}
      {ai?.risks && ai.risks.length > 0 && (
        <>
          <h4>Risks</h4>
          <ul>
            {ai.risks.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </>
      )}
      {ai?.suggestions && ai.suggestions.length > 0 && (
        <>
          <h4>What would help</h4>
          <ul>
            {ai.suggestions.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </>
      )}
      <p className="muted small">
        Streams and ponds computed from the cover's shape; the sag estimate uses
        a fabric tension still to be measured. The verdict and advice are
        DeepSeek's.
      </p>
    </section>
  );
}
