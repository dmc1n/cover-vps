// The scroll story's 3D scene (ADR-067): one SUNS model's cover as three shapes of the same
// points (the designed cover in its pieces, every piece flat on the roll, the cover as it falls
// over the furniture), morphed by how far the visitor has scrolled. `progress` runs 0..1 over six
// chapters: the furniture, the cover, its pieces, flat on the roll, sewn and fitted, the rain.
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

interface Meta {
  points: number;
  triangles: number;
  pieces: { name: string; index: number }[];
  roll_m: [number, number];
  size_m: number[];
}

const CHAPTERS = 6;
// sand tones for the pieces, and the sand of the finished cover (the workshop's standard)
const PIECE = [
  "#cbb999",
  "#bfab88",
  "#d6c7aa",
  "#b39f7d",
  "#c6b392",
  "#ddd0b6",
  "#a99474",
];
const FINISHED = new THREE.Color("#c4b08e"); // the sand cover (the owner, 5 Oct)
const BG = "#f1f2f2";

const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const ease = (x: number) => x * x * (3 - 2 * x);
// how far into chapter k (0..1): each change is done at 60 % of its chapter, so the visitor
// sees every stage at rest before the next one starts
const into = (p: number, k: number) => clamp((p * CHAPTERS - k) / 0.6);

export function StoryScene({
  model,
  progress,
}: {
  model: string;
  progress: React.MutableRefObject<number>;
}) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let alive = true;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(BG);
    scene.fog = new THREE.Fog(BG, 14, 34);
    const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 80);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    // a phone draws at most 1.5 pixels per CSS pixel (ADR-106)
    const phone =
      window.matchMedia("(pointer: coarse)").matches || window.innerWidth < 820;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, phone ? 1.5 : 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    el.appendChild(renderer.domElement);
    scene.add(new THREE.HemisphereLight("#ffffff", "#c9cdc6", 1.6));
    const sun = new THREE.DirectionalLight("#fff8ee", 2.4);
    sun.position.set(3, 6, 4);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = sun.shadow.camera.bottom = -6;
    sun.shadow.camera.right = sun.shadow.camera.top = 6;
    sun.shadow.radius = 4;
    scene.add(sun);
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(80, 80),
      new THREE.ShadowMaterial({ opacity: 0.16 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    let furniture: THREE.Object3D | null = null;
    let cover: THREE.Mesh | null = null;
    let roll: THREE.Mesh | null = null;
    let design: Float32Array, flat: Float32Array, drape: Float32Array;
    let pieceOf: Uint8Array;
    let centre = new Float32Array(0); // per piece: its centre, to step the pieces apart
    let base = new Float32Array(0); // per point: its piece colour
    const rain = new THREE.Group();

    const resize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight || 1;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      // on a wide screen the text is on the left: the furniture stands right of centre
      if (w > 860) camera.setViewOffset(w, h, -w * 0.17, 0, w, h);
      else camera.clearViewOffset();
      camera.updateProjectionMatrix();
    };
    resize();
    window.addEventListener("resize", resize);

    const load = async () => {
      const [meta, bin] = await Promise.all([
        fetch(`/api/shop/story/${model}.json`).then(
          (r) => r.json() as Promise<Meta>,
        ),
        fetch(`/api/shop/story/${model}.bin`).then((r) => r.arrayBuffer()),
      ]);
      if (!alive) return;
      const n = meta.points;
      const m = meta.triangles;
      let at = 0;
      const f32 = (len: number) => {
        const a = new Float32Array(bin, at, len);
        at += len * 4;
        return a;
      };
      design = f32(n * 3);
      flat = f32(n * 3);
      drape = f32(n * 3);
      pieceOf = new Uint8Array(bin, at, n);
      at += n;
      const faces = new Uint32Array(bin.slice(at, at + m * 12)); // copied: may not be aligned
      // per piece: its centre (to part the pieces) and its colour
      const count = meta.pieces.length;
      centre = new Float32Array(count * 3);
      const seen = new Float32Array(count);
      for (let i = 0; i < n; i++) {
        const k = pieceOf[i];
        centre[k * 3] += design[i * 3];
        centre[k * 3 + 1] += design[i * 3 + 1];
        centre[k * 3 + 2] += design[i * 3 + 2];
        seen[k] += 1;
      }
      for (let k = 0; k < count; k++)
        for (let j = 0; j < 3; j++) centre[k * 3 + j] /= Math.max(seen[k], 1);
      base = new Float32Array(n * 3);
      const c = new THREE.Color();
      for (let i = 0; i < n; i++) {
        c.set(PIECE[pieceOf[i] % PIECE.length]);
        base.set([c.r, c.g, c.b], i * 3);
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute(
        "position",
        new THREE.BufferAttribute(new Float32Array(design), 3),
      );
      geo.setAttribute(
        "color",
        new THREE.BufferAttribute(new Float32Array(base), 3),
      );
      geo.setIndex(new THREE.BufferAttribute(faces, 1));
      geo.computeVertexNormals();
      const mat = new THREE.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.78,
        metalness: 0,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0,
      });
      cover = new THREE.Mesh(geo, mat);
      cover.castShadow = true;
      cover.receiveShadow = true;
      scene.add(cover);
      // the roll of fabric the flat pieces lie on (152 cm wide)
      roll = new THREE.Mesh(
        new THREE.PlaneGeometry(meta.roll_m[0] + 0.3, meta.roll_m[1] + 0.12),
        new THREE.MeshStandardMaterial({
          color: "#e4e7e3",
          roughness: 0.95,
          transparent: true,
          opacity: 0,
        }),
      );
      roll.rotation.x = -Math.PI / 2;
      roll.position.y = 0.001;
      roll.receiveShadow = true;
      scene.add(roll);
      // rain: thin streaks falling, only in the last chapter
      const streak = new THREE.CylinderGeometry(0.0015, 0.0015, 0.16, 3);
      const water = new THREE.MeshBasicMaterial({
        color: "#aab8c2",
        transparent: true,
        opacity: 0.32,
      });
      for (let i = 0; i < 260; i++) {
        const d = new THREE.Mesh(streak, water);
        d.position.set(
          (Math.random() - 0.5) * 3.2,
          Math.random() * 3,
          (Math.random() - 0.5) * 2.2,
        );
        rain.add(d);
      }
      rain.visible = false;
      scene.add(rain);
      new GLTFLoader().load(`/api/shop/story/${model}-furniture.glb`, (g) => {
        if (!alive) return;
        furniture = g.scene;
        furniture.traverse((o) => {
          const mesh = o as THREE.Mesh;
          if (!mesh.isMesh) return;
          mesh.castShadow = mesh.receiveShadow = true;
          const mm = mesh.material as THREE.MeshStandardMaterial;
          mm.roughness = 0.9;
          mm.transparent = true;
        });
        scene.add(furniture);
      });
    };
    load().catch(() => undefined);

    // the camera per chapter: in front, then closer, then high above the roll, then back
    const shots = [
      { pos: [2.9, 1.5, 3.2], look: [0, 0.4, 0] },
      { pos: [2.5, 1.35, 2.7], look: [0, 0.42, 0] },
      { pos: [3.2, 1.9, 2.4], look: [0, 0.4, 0] },
      { pos: [1.2, 12.5, 4.6], look: [1.0, 0, 0] },
      { pos: [-2.6, 1.4, 3.0], look: [0, 0.4, 0] },
      { pos: [2.7, 1.35, 3.4], look: [0, 0.4, 0] },
    ];
    const v3 = (a: number[]) => new THREE.Vector3(a[0], a[1], a[2]);
    const look = new THREE.Vector3();
    let shown = -1;
    const tick = () => {
      if (!alive) return;
      const p = progress.current;
      // the camera between this chapter's shot and the next
      const x = clamp(p * CHAPTERS - 0.5, 0, CHAPTERS - 1);
      const k = Math.floor(x);
      const t = ease(x - k);
      const a = shots[k];
      const b = shots[Math.min(k + 1, CHAPTERS - 1)];
      camera.position.copy(v3(a.pos).lerp(v3(b.pos), t));
      look.copy(v3(a.look).lerp(v3(b.look), t));
      camera.lookAt(look);
      if (cover && Math.abs(p - shown) > 1e-4) {
        shown = p;
        const appear = ease(into(p, 1)); // 2: the cover appears around the furniture
        const apart = ease(into(p, 2)) * (1 - ease(into(p, 3))); // 3: the pieces part
        const unfold = ease(into(p, 3)); // 4: flat on the roll
        const fall = ease(into(p, 4)); // 5: sewn, over the furniture as it falls
        const wet = ease(into(p, 5)); // 6: the rain
        const pos = cover.geometry.getAttribute(
          "position",
        ) as THREE.BufferAttribute;
        const col = cover.geometry.getAttribute(
          "color",
        ) as THREE.BufferAttribute;
        const P = pos.array as Float32Array;
        const C = col.array as Float32Array;
        const n = P.length / 3;
        const one = Math.max(apart, 0) * 0.22;
        const lift = Math.sin(Math.PI * fall) * 0.75; // over the furniture, not through it
        for (let i = 0; i < n; i++) {
          const kk = pieceOf[i] * 3;
          for (let j = 0; j < 3; j++) {
            const d =
              design[i * 3 + j] + centre[kk + j] * one * (j === 1 ? 0.6 : 1);
            const s = d + (flat[i * 3 + j] - d) * unfold;
            P[i * 3 + j] =
              s + (drape[i * 3 + j] - s) * fall + (j === 1 ? lift : 0);
            C[i * 3 + j] =
              base[i * 3 + j] +
              ((j === 0 ? FINISHED.r : j === 1 ? FINISHED.g : FINISHED.b) -
                base[i * 3 + j]) *
                fall;
          }
        }
        pos.needsUpdate = true;
        col.needsUpdate = true;
        cover.geometry.computeVertexNormals();
        const mat = cover.material as THREE.MeshStandardMaterial;
        mat.opacity = appear * 0.94 + 0.06 * fall;
        mat.roughness = 0.78 - wet * 0.38;
        mat.transparent = mat.opacity < 0.999;
        if (roll)
          (roll.material as THREE.MeshStandardMaterial).opacity =
            unfold * (1 - fall);
        if (furniture) {
          // gone while the pieces lie flat; back quickly once they rise to be sewn on
          const shownF = 1 - unfold * (1 - clamp(fall * 3));
          furniture.visible = shownF > 0.04;
          furniture.traverse((o) => {
            const mesh = o as THREE.Mesh;
            if (!mesh.isMesh) return;
            const fm = mesh.material as THREE.MeshStandardMaterial;
            fm.opacity = shownF;
            fm.depthWrite = shownF > 0.98;
          });
        }
        rain.visible = wet > 0.02;
      }
      if (rain.visible)
        for (const d of rain.children) {
          d.position.y -= 0.12;
          if (d.position.y < 0) d.position.y += 3;
        }
      renderer.render(scene, camera);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    return () => {
      alive = false;
      window.removeEventListener("resize", resize);
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
  }, [model, progress]);
  return <div className="st-scene" ref={host} />;
}
