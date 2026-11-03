// The studio's 3D views, loaded when a page shows one (ADR-154). three.js is 614 kB; the Desk's
// list, Settings, the shop pages and the login never need it, so the first page of the studio
// (and the iPad on a slow line) does not wait for it. Every page that shows 3D imports the view
// from here, never from its own module, or the bundler pulls three.js back into the first load.
import { lazy, Suspense, type ComponentProps } from "react";

const ViewerImpl = lazy(() =>
  import("./Viewer").then((m) => ({ default: m.Viewer })),
);
const ConfigureImpl = lazy(() => import("./Configure"));
const SceneImpl = lazy(() =>
  import("./shop/Scene").then((m) => ({ default: m.Scene })),
);

/** The box a 3D view sits in while its code loads (the same height, so nothing jumps). */
export function Loading3D({ className = "" }: { className?: string }) {
  return (
    <div
      className={`loading-3d ${className}`}
      role="status"
      aria-busy="true"
      data-testid="loading-3d"
    >
      Loading 3D…
    </div>
  );
}

type ViewerProps = ComponentProps<typeof import("./Viewer").Viewer>;
type SceneProps = ComponentProps<typeof import("./shop/Scene").Scene>;

export function Viewer(props: ViewerProps) {
  return (
    <Suspense fallback={<Loading3D className="viewer" />}>
      <ViewerImpl {...props} />
    </Suspense>
  );
}

export function Configure() {
  return (
    <Suspense fallback={<Loading3D />}>
      <ConfigureImpl />
    </Suspense>
  );
}

export function Scene(props: SceneProps) {
  return (
    <Suspense fallback={<Loading3D />}>
      <SceneImpl {...props} />
    </Suspense>
  );
}
