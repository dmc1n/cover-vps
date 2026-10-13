import * as THREE from "three";

export function disposeObject(root: THREE.Object3D): void {
  // Deduplicate within this tree. A disposed resource can be uploaded again,
  // e.g. three.js shares Sprite geometry across successive viewers.
  const disposed = new Set<object>();
  const once = (resource: { dispose(): void }) => {
    if (disposed.has(resource)) return;
    disposed.add(resource);
    resource.dispose();
  };
  root.traverse((object) => {
    const drawable = object as THREE.Mesh;
    if (drawable.geometry) once(drawable.geometry);
    const materials = Array.isArray(drawable.material)
      ? drawable.material
      : drawable.material
        ? [drawable.material]
        : [];
    for (const material of materials) {
      for (const value of Object.values(material)) {
        if (value instanceof THREE.Texture) once(value);
      }
      once(material);
    }
  });
}

const renderers = new Set<THREE.WebGLRenderer>();
declare global {
  interface Window {
    __three: { renderers: number; geometries: number; textures: number };
  }
}
if (typeof window !== "undefined") {
  Object.defineProperty(window, "__three", {
    configurable: true,
    get: () => ({
      renderers: renderers.size,
      geometries: [...renderers].reduce(
        (n, r) => n + r.info.memory.geometries,
        0,
      ),
      textures: [...renderers].reduce((n, r) => n + r.info.memory.textures, 0),
    }),
  });
}
export function trackRenderer(renderer: THREE.WebGLRenderer): () => void {
  renderers.add(renderer);
  return () => {
    renderers.delete(renderer);
  };
}
