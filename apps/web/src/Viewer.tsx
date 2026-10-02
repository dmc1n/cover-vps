import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { fileUrl, Rain } from "./api";

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
const toScene = (p: number[]) => new THREE.Vector3(p[0] / 1000, p[2] / 1000, -p[1] / 1000);
const DROP_SPEED = 0.6; // path points per frame
const DROPS_SHOWN = 160;

export function Viewer({
  id,
  files,
  stamp,
  onRain,
  rainBusy,
}: {
  id: string;
  files: string[];
  stamp: number;
  onRain?: () => void;
  rainBusy?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rainAnim = useRef<{ points: THREE.Points; paths: THREE.Vector3[][]; t: number[] } | null>(null);
  const [rain, setRain] = useState<Rain | null>(null);
  const [raining, setRaining] = useState(false);
  const groups = useRef<Record<string, THREE.Object3D>>({});
  const available = LAYERS.filter((l) => files.includes(l.file));
  const [shown, setShown] = useState<Record<string, boolean>>((): Record<string, boolean> => {
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
    return { "model.glb": !panels, "preview.glb": false, "panels.glb": panels };
  });

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color("#f9f6e8"); // SUNS cream
    const camera = new THREE.PerspectiveCamera(40, el.clientWidth / el.clientHeight, 0.01, 100);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
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
          const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
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
          camera.position.copy(centre).add(new THREE.Vector3(0.6, 0.5, 1.0).multiplyScalar(size));
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
        const pos = anim.points.geometry.getAttribute("position") as THREE.BufferAttribute;
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
      renderer.render(scene, camera);
    });
    return () => {
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
      geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(paths.length * 3), 3));
      const points = new THREE.Points(
        geo,
        new THREE.PointsMaterial({ color: "#2f7fe0", size: 0.025, transparent: true, opacity: 0.9 }),
      );
      group.add(points);
      rainAnim.current = { points, paths, t: paths.map(() => -Math.random() * 60) };
      if (files.includes("rain.glb")) {
        new GLTFLoader().load(`${fileUrl(id, "rain.glb")}?v=${stamp}`, (gltf) => group.add(gltf.scene));
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

  const shownRef = useRef(shown);
  shownRef.current = shown;
  useEffect(() => {
    for (const [file, obj] of Object.entries(groups.current)) obj.visible = !!shown[file];
  }, [shown]);

  if (!available.length) return <p className="muted">Nothing to show yet: the model is being imported.</p>;
  return (
    <div className="viewer">
      <div className="layers">
        {available.map((l) => (
          <label key={l.file}>
            <input
              type="checkbox"
              checked={!!shown[l.file]}
              onChange={(e) => setShown({ ...shown, [l.file]: e.target.checked })}
            />
            {l.label}
          </label>
        ))}
        <span className="muted">Drag to turn, scroll to zoom, right-drag to move.</span>
        <span className="rain-buttons">
          {files.includes("rain.json") && (
            <button className={raining ? "primary" : ""} onClick={() => setRaining(!raining)}>
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
              {rainBusy ? "Simulating…" : files.includes("rain.json") ? "Simulate again" : "Rain simulation"}
            </button>
          )}
        </span>
      </div>
      <div className="canvas" ref={host} />
      {raining && rain && <RainReport rain={rain} />}
    </div>
  );
}

function RainReport({ rain }: { rain: Rain }) {
  const ai = rain.ai;
  const verdict = ai?.verdict ?? (rain.dry ? "dry" : "risk");
  return (
    <section className={`card rain ${verdict}`}>
      <div className="rain-head">
        <strong>
          {verdict === "dry" ? "Dry: the rain runs off" : verdict === "wet" ? "Water stays on this cover" : "Risk of standing water"}
        </strong>
        <span className="muted">
          {rain.ponds.length} pond{rain.ponds.length === 1 ? "" : "s"} ({rain.pond_volume_l} l) · flat {rain.flat_area_m2} m² ·
          off at {Object.entries(rain.exits).filter(([, n]) => n).map(([k, n]) => `${k} ${n}`).join(", ")}
        </span>
      </div>
      {ai?.summary && <p>{ai.summary}</p>}
      {rain.ponds.length > 0 && (
        <ul>
          {rain.ponds.slice(0, 6).map((p, i) => (
            <li key={i}>
              Pond {i + 1}: {p.area_m2} m², up to {p.max_depth_mm} mm deep, {p.volume_l} l; with the fabric sagging{" "}
              {p.volume_with_sag_l} l{p.keeps_growing ? " — keeps growing under its weight" : ""}
            </li>
          ))}
        </ul>
      )}
      {rain.seams_along.length > 0 && (
        <p className="muted">
          Water runs along {rain.seams_along.map((s) => `${s.seam} (${Math.round(s.run_mm / 10)} cm)`).join(", ")}: seams
          soak there.
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
        Streams and ponds computed from the cover's shape; the sag estimate uses a fabric tension still to be measured.
        The verdict and advice are DeepSeek's.
      </p>
    </section>
  );
}
