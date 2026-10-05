// A 3D view for the shop: a GLB (the furniture with the cover), optionally with overlays (the
// water in blue), turning slowly on the landing page.
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export function Scene({
  url,
  overlays = [],
  spin = false,
  dark = false,
}: {
  url: string | null;
  overlays?: string[];
  spin?: boolean;
  dark?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const keyOver = overlays.join("|");
  useEffect(() => {
    const el = host.current;
    if (!el || !url) return;
    const scene = new THREE.Scene();
    scene.background = dark ? null : new THREE.Color("#f3f1ea");
    const camera = new THREE.PerspectiveCamera(
      35,
      el.clientWidth / Math.max(el.clientHeight, 1),
      0.01,
      100,
    );
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: dark });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    renderer.shadowMap.enabled = true;
    el.appendChild(renderer.domElement);
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
    scene.add(sun);
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(6, 64),
      new THREE.ShadowMaterial({ opacity: dark ? 0.35 : 0.18 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.autoRotate = spin;
    controls.autoRotateSpeed = 0.8;
    controls.enableZoom = !spin;
    controls.enablePan = false;
    let alive = true;
    const loader = new GLTFLoader();
    loader.load(url, (gltf) => {
      if (!alive) return;
      const named = (o: THREE.Object3D, n: string) =>
        o.name.includes(n) || !!o.parent?.name.includes(n);
      // balloons under the cover: show the cover see-through so they can be seen
      let balloons = false;
      gltf.scene.traverse((o) => {
        if (named(o, "balloon")) balloons = true;
      });
      gltf.scene.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        m.castShadow = true;
        m.receiveShadow = true;
        const mat = m.material as THREE.MeshStandardMaterial;
        mat.side = THREE.DoubleSide;
        if (named(m, "cover")) {
          mat.roughness = 0.9;
          mat.transparent = true;
          mat.opacity = balloons ? 0.55 : 0.93;
          mat.depthWrite = !balloons;
          m.renderOrder = 1;
        } else if (named(m, "balloon")) {
          mat.roughness = 0.35;
          mat.metalness = 0;
        }
      });
      scene.add(gltf.scene);
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const size = box.getSize(new THREE.Vector3()).length();
      const c = box.getCenter(new THREE.Vector3());
      controls.target.copy(c);
      camera.position
        .copy(c)
        .add(new THREE.Vector3(0.75, 0.55, 0.95).multiplyScalar(size * 1.25));
      ground.position.y = box.min.y;
      for (const o of overlays)
        loader.load(o, (w) => {
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
          scene.add(w.scene);
        });
    });
    renderer.setAnimationLoop(() => {
      controls.update();
      renderer.render(scene, camera);
    });
    const onResize = () => {
      camera.aspect = el.clientWidth / Math.max(el.clientHeight, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(el.clientWidth, el.clientHeight);
    };
    window.addEventListener("resize", onResize);
    return () => {
      alive = false;
      window.removeEventListener("resize", onResize);
      renderer.setAnimationLoop(null);
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, keyOver, spin, dark]);
  return <div className="s-scene" ref={host} />;
}
