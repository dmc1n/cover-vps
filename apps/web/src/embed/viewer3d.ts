// The dealer embed's 3D view (ADR-150): loaded only when the dealer's site shows 3D, as its own
// chunk next to configurator.js. One renderer per view, kept while the model changes; a frame is
// drawn only when something moved; nothing while the view is off screen.
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export interface Viewer {
  show(url: string): Promise<void>;
  dispose(): void;
}

function free(o: THREE.Object3D): void {
  o.traverse((x) => {
    const m = x as THREE.Mesh;
    if (!m.isMesh) return;
    m.geometry?.dispose();
    const mats = Array.isArray(m.material) ? m.material : [m.material];
    for (const mat of mats) mat?.dispose();
  });
}

export function mountViewer(el: HTMLElement, background: string): Viewer {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(background);
  const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  const phone = window.matchMedia("(pointer: coarse)").matches;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, phone ? 1.5 : 2));
  renderer.shadowMap.enabled = true;
  el.appendChild(renderer.domElement);
  scene.add(new THREE.HemisphereLight("#fffaf0", "#9aa08a", 1.7));
  const sun = new THREE.DirectionalLight("#ffffff", 1.6);
  sun.position.set(3, 5, 4);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  scene.add(sun);
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(6, 64),
    new THREE.ShadowMaterial({ opacity: 0.18 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.enablePan = false;
  const loader = new GLTFLoader();
  let model: THREE.Object3D | null = null;
  let dirty = true;
  const frame = () => {
    const moved = controls.update();
    if (!moved && !dirty) return;
    dirty = false;
    renderer.render(scene, camera);
  };
  let running = false;
  const run = (on: boolean) => {
    if (on === running) return;
    running = on;
    renderer.setAnimationLoop(on ? frame : null);
    dirty = true;
  };
  const io =
    "IntersectionObserver" in window
      ? new IntersectionObserver(([e]) => run(e.isIntersecting))
      : null;
  if (io) io.observe(el);
  else run(true);
  const resize = () => {
    const w = el.clientWidth || 300;
    const h = el.clientHeight || 240;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    dirty = true;
  };
  const ro = new ResizeObserver(resize);
  ro.observe(el);
  resize();
  return {
    show(url: string) {
      return new Promise((resolve, reject) => {
        loader.load(
          url,
          (gltf) => {
            gltf.scene.traverse((o) => {
              const m = o as THREE.Mesh;
              if (!m.isMesh) return;
              m.castShadow = true;
              m.receiveShadow = true;
              const mat = m.material as THREE.MeshStandardMaterial;
              mat.side = THREE.DoubleSide;
              if (o.name.includes("cover") || o.parent?.name.includes("cover")) {
                mat.roughness = 0.9;
              }
            });
            const box = new THREE.Box3().setFromObject(gltf.scene);
            const size = box.getSize(new THREE.Vector3()).length();
            const c = box.getCenter(new THREE.Vector3());
            const dir = model
              ? camera.position.clone().sub(controls.target).normalize()
              : new THREE.Vector3(0.75, 0.55, 0.95).normalize();
            controls.target.copy(c);
            camera.position.copy(c).add(dir.multiplyScalar(size * 1.6));
            ground.position.y = box.min.y;
            if (model) {
              scene.remove(model);
              free(model);
            }
            model = gltf.scene;
            scene.add(model);
            dirty = true;
            resolve();
          },
          undefined,
          (e) => reject(e),
        );
      });
    },
    dispose() {
      io?.disconnect();
      ro.disconnect();
      renderer.setAnimationLoop(null);
      if (model) free(model);
      controls.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
}
