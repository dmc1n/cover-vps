// A 3D view for the shop: a GLB (the furniture with the cover), optionally with overlays (the
// water in blue), turning slowly on the landing page.
//
// Light on the device (ADR-101): one WebGL renderer per view, kept while the model changes (the
// configurator swaps models on every size), so a new quote never flashes an empty box; a frame is
// drawn only when something moved; nothing is drawn while the view is off screen; a phone draws
// at most 1.5 pixels per CSS pixel. The canvas fades in once the first model is there.
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

interface View {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  renderer: THREE.WebGLRenderer;
  controls: OrbitControls;
  ground: THREE.Mesh;
  loader: GLTFLoader;
  model: THREE.Object3D | null;
}

const setSolid = (mat: THREE.MeshStandardMaterial, o: number) => {
  mat.transparent = o < 0.999;
  mat.opacity = o;
  mat.depthWrite = o >= 0.9; // see-through: what is under it shows
  // see-through: only the side facing you, so you look through one layer, not two
  mat.side = o < 0.999 ? THREE.FrontSide : THREE.DoubleSide;
  mat.needsUpdate = true;
};

function dispose(o: THREE.Object3D) {
  o.traverse((x) => {
    const m = x as THREE.Mesh;
    if (!m.isMesh) return;
    m.geometry.dispose();
    for (const mat of ([] as THREE.Material[]).concat(m.material))
      mat.dispose();
  });
}

export function Scene({
  url,
  overlays = [],
  spin = false,
  dark = false,
  coverOpacity,
}: {
  url: string | null;
  overlays?: string[];
  spin?: boolean;
  dark?: boolean;
  /** 0..1: how solid the cover is drawn (the configurator's slider); unset: the default */
  coverOpacity?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<View | null>(null);
  const dirty = useRef(true); // something changed: draw the next frame
  const covers = useRef<THREE.MeshStandardMaterial[]>([]);
  const opacity = useRef<number | undefined>(coverOpacity);
  opacity.current = coverOpacity;
  useEffect(() => {
    if (coverOpacity === undefined) return;
    for (const mat of covers.current) setSolid(mat, coverOpacity);
    dirty.current = true;
  }, [coverOpacity]);

  // the renderer, the light and the ground: made once per view
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const scene = new THREE.Scene();
    scene.background = dark ? null : new THREE.Color("#f3f1ea");
    const camera = new THREE.PerspectiveCamera(
      35,
      el.clientWidth / Math.max(el.clientHeight, 1),
      0.01,
      100,
    );
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: dark });
    const phone =
      window.matchMedia("(pointer: coarse)").matches || window.innerWidth < 820;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, phone ? 1.5 : 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    renderer.shadowMap.enabled = true;
    const canvas = renderer.domElement;
    canvas.style.opacity = "0";
    canvas.style.transition = "opacity 0.6s ease";
    el.dataset.state = "loading";
    el.appendChild(canvas);
    scene.add(
      new THREE.HemisphereLight(
        "#fffaf0",
        dark ? "#1d2219" : "#9aa08a",
        dark ? 1.2 : 1.7,
      ),
    );
    const sun = new THREE.DirectionalLight("#ffffff", dark ? 2.2 : 1.6);
    sun.position.set(3, 5, 4);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    scene.add(sun);
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(6, 64),
      new THREE.ShadowMaterial({ opacity: dark ? 0.35 : 0.18 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.autoRotate = spin;
    controls.autoRotateSpeed = 0.8;
    controls.enableZoom = !spin;
    controls.enablePan = false;
    const v: View = {
      scene,
      camera,
      renderer,
      controls,
      ground,
      loader: new GLTFLoader(),
      model: null,
    };
    view.current = v;
    dirty.current = true;

    let first = true;
    const frame = () => {
      // the controls report whether the camera moved (turning, damping after a drag)
      const moved = controls.update();
      if (!moved && !dirty.current) return;
      dirty.current = false;
      renderer.render(scene, camera);
      if (first && v.model) {
        first = false;
        canvas.style.opacity = "1";
        el.dataset.state = "ready";
        performance.mark("cover-3d-ready");
      }
    };
    // draw only while the view is on screen (the page hidden stops it by itself)
    let running = false;
    const run = (on: boolean) => {
      if (on === running) return;
      running = on;
      renderer.setAnimationLoop(on ? frame : null);
      dirty.current = true;
    };
    const io =
      "IntersectionObserver" in window
        ? new IntersectionObserver(([e]) => run(e.isIntersecting))
        : null;
    if (io) io.observe(el);
    else run(true);
    const onResize = () => {
      camera.aspect = el.clientWidth / Math.max(el.clientHeight, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(el.clientWidth, el.clientHeight);
      dirty.current = true;
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(el);
    return () => {
      io?.disconnect();
      ro.disconnect();
      renderer.setAnimationLoop(null);
      if (v.model) dispose(v.model);
      controls.dispose();
      renderer.dispose();
      el.removeChild(canvas);
      view.current = null;
    };
  }, [spin, dark]);

  // the model (and its overlays): swapped in the same view when the address changes
  const keyOver = overlays.join("|");
  useEffect(() => {
    const v = view.current;
    if (!v || !url) return;
    let alive = true;
    const added: THREE.Object3D[] = [];
    v.loader.load(url, (gltf) => {
      if (!alive) return;
      const named = (o: THREE.Object3D, n: string) =>
        o.name.includes(n) || !!o.parent?.name.includes(n);
      // balloons under the cover: show the cover see-through so they can be seen
      let balloons = false;
      gltf.scene.traverse((o) => {
        if (named(o, "balloon")) balloons = true;
      });
      const mine: THREE.MeshStandardMaterial[] = [];
      gltf.scene.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        m.castShadow = true;
        m.receiveShadow = true;
        let mat = m.material as THREE.MeshStandardMaterial;
        if (named(m, "cover")) {
          // the file's parts share one material: the cover gets its own, so only the cover
          // turns see-through (the owner, 6 Oct 2026)
          mat = mat.clone();
          m.material = mat;
        }
        mat.side = THREE.DoubleSide;
        if (!named(m, "cover")) {
          // the furniture (and balloons) always solid: only the cover turns see-through
          mat.transparent = false;
          mat.opacity = 1;
          mat.depthWrite = true;
        }
        if (named(m, "cover")) {
          mat.roughness = 0.9;
          setSolid(mat, opacity.current ?? (balloons ? 0.55 : 0.93));
          mine.push(mat);
          m.renderOrder = 1;
        } else if (named(m, "balloon")) {
          mat.roughness = 0.35;
          mat.metalness = 0;
        }
      });
      // frame the model: the first one from the front corner; a later one (new sizes) from
      // where the visitor turned the view to, at a distance that fits its size
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const size = box.getSize(new THREE.Vector3()).length();
      const c = box.getCenter(new THREE.Vector3());
      const dir = v.model
        ? v.camera.position.clone().sub(v.controls.target).normalize()
        : new THREE.Vector3(0.75, 0.55, 0.95).normalize();
      v.controls.target.copy(c);
      v.camera.position
        .copy(c)
        .add(dir.multiplyScalar(size * 1.25 * Math.hypot(0.75, 0.55, 0.95)));
      v.ground.position.y = box.min.y;
      if (v.model) {
        v.scene.remove(v.model);
        dispose(v.model);
      }
      v.model = gltf.scene;
      covers.current = mine;
      v.scene.add(gltf.scene);
      dirty.current = true;
      for (const o of overlays)
        v.loader.load(o, (w) => {
          if (!alive) return;
          w.scene.traverse((x) => {
            const m = x as THREE.Mesh;
            if (m.isMesh) {
              const mat = m.material as THREE.MeshStandardMaterial;
              mat.color = new THREE.Color("#3f8fd6");
              mat.emissive = new THREE.Color("#163a5c");
              mat.transparent = true;
              mat.opacity = 0.85;
              mat.side = THREE.DoubleSide;
              m.position.y += 0.004; // just above the cover
            }
          });
          v.scene.add(w.scene);
          added.push(w.scene);
          dirty.current = true;
        });
    });
    return () => {
      alive = false;
      for (const o of added) {
        v.scene.remove(o);
        dispose(o);
      }
      dirty.current = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, keyOver, spin, dark]);
  return <div className="s-scene" ref={host} />;
}
