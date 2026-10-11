// An arrangement seen from above (ADR-089, 095, 114): each member's plan rectangle in its own
// colour with its number, the cover's footprint (follow, box or smooth) as a red outline. Used on
// the Desk's card; the Arrangements page draws the real footprints while placing.

export const MEMBER_COLOURS = [
  "#778074",
  "#b08d57",
  "#5f7a8a",
  "#8a6f5f",
  "#6e776b",
  "#9a8a5a",
];

export const FOOTPRINT_NAMES: Record<string, string> = {
  follow: "Follow the products (sharp corners)",
  box: "One rectangle around everything",
  smooth: "Smoothed outline",
};

export function ArrangementPlan({
  rects,
  outline,
  height = 260,
}: {
  rects: number[][][];
  outline?: number[][] | null;
  height?: number;
}) {
  const pts = [...(outline ?? []), ...rects.flat()];
  if (!pts.length) return null;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const y0 = Math.min(...ys);
  const y1 = Math.max(...ys);
  const pad = Math.max(x1 - x0, y1 - y0) * 0.06;
  const w = x1 - x0 + 2 * pad;
  const line = w / 220;
  // the plan's y runs to the back; the screen's down: the front is at the bottom
  const poly = (ring: number[][]) =>
    ring.map(([x, y]) => `${x},${-y}`).join(" ");
  const mid = (r: number[][]) => [
    r.reduce((s, p) => s + p[0], 0) / r.length,
    r.reduce((s, p) => s + p[1], 0) / r.length,
  ];
  return (
    <svg
      className="arr-plan"
      role="img"
      aria-label="the arrangement seen from above, the front at the bottom"
      viewBox={`${x0 - pad} ${-(y1 + pad)} ${w} ${y1 - y0 + 2 * pad}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ height }}
    >
      {rects.map((r, i) => {
        const [cx, cy] = mid(r);
        return (
          <g key={i}>
            <polygon
              points={poly(r)}
              fill={MEMBER_COLOURS[i % MEMBER_COLOURS.length]}
              fillOpacity={0.55}
              stroke="currentColor"
              strokeWidth={line}
            />
            <text
              x={cx}
              y={-cy}
              fontSize={w / 22}
              textAnchor="middle"
              dominantBaseline="central"
              fill="currentColor"
              fontWeight={700}
            >
              {i + 1}
            </text>
          </g>
        );
      })}
      {outline && outline.length > 2 && (
        <polygon
          points={poly(outline)}
          fill="none"
          stroke="#c0392b"
          strokeWidth={line * 1.6}
          strokeLinejoin="miter"
        />
      )}
    </svg>
  );
}
