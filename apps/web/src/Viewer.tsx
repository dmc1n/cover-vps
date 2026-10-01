import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { fileUrl } from "./api";

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

export function Viewer({ id, files, stamp }: { id: string; files: string[]; stamp: number }) {
  const host = useRef<HTMLDivElement>(null);
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
      renderer.render(scene, camera);
    });
    return () => {
      alive = false;
      window.removeEventListener("resize", onResize);
      renderer.setAnimationLoop(null);
      renderer.dispose();
      el.removeChild(renderer.domElement);
      groups.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, stamp, files.join(",")]);

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
      </div>
      <div className="canvas" ref={host} />
    </div>
  );
}
