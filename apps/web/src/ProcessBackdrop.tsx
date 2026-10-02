// The login page's background: the whole process in one loop, around the login card.
// 1 a pencil sketch of the cutting pattern, 2 the same pieces exact on the 150 cm roll,
// 3 the cutter going round them while the cover comes together in 3D, 4 the finished cover
// with the rain running off. Decoration only: hidden from screen readers, no pointer events;
// with "reduce motion" everything is shown at once, still.

// one sloped box cover (the Kota family), in cm: length, depth, back and front height, strip
const L = 200;
const D = 100;
const HB = 88;
const HF = 61;
const S = 30;
const SLOPE = Math.hypot(D - S, HB - HF); // the slope's true width

type P = [number, number];
const pts = (ps: P[]) =>
  ps.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
const path = (ps: P[]) =>
  "M" + ps.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(" L") + " Z";

// the flat pieces (the net, as sketched): the long pieces stacked, an end beside the slope on
// each side, upright as seen from the side (high at the back, low at the front)
const END: P[] = [
  [0, 0],
  [0, HB],
  [S, HB],
  [D, HF],
  [D, 0],
]; // y along the depth, z up
const rect = (x: number, y: number, w: number, h: number): P[] => [
  [x, y],
  [x + w, y],
  [x + w, y + h],
  [x, y + h],
];
const NET: P[][] = (() => {
  const base = HB + S + SLOPE; // the ends stand on the slope's lower edge
  return [
    rect(0, 0, L, HB),
    rect(0, HB, L, S),
    rect(0, HB + S, L, SLOPE),
    rect(0, base, L, HF),
    END.map(([y, z]) => [-12 - y, base - z] as P),
    END.map(([y, z]) => [L + 12 + y, base - z] as P),
  ];
})();

// the same pieces nested on the roll (150 cm across), as the cutting table lays them
const ROLL = 150;
const NEST: P[][] = [
  rect(0, 0, L, HB),
  rect(0, HB + 6, L, S),
  rect(L + 8, 0, L, SLOPE),
  rect(L + 8, SLOPE + 6, L, HF),
  END.map(([y, z]) => [2 * L + 16 + y, HB - z] as P),
  END.map(([y, z]) => [2 * L + 24 + D + (D - y), HB - z] as P), // the mirror image
];
const NEST_LENGTH = 2 * L + 24 + 2 * D;

// the 3D cover, seen from the front right and above (isometric), back at y = 0, front at y = D
const COS = Math.cos(Math.PI / 6);
const SIN = Math.sin(Math.PI / 6);
const iso = (x: number, y: number, z: number): P => [
  (x + y) * COS,
  (y - x) * SIN - z,
];
const C = {
  b0: iso(0, 0, HB),
  b1: iso(L, 0, HB),
  s0: iso(0, S, HB),
  s1: iso(L, S, HB),
  f0: iso(0, D, HF),
  f1: iso(L, D, HF),
  g0: iso(0, D, 0),
  g1: iso(L, D, 0),
  gb0: iso(0, 0, 0),
};
const FACES: { cls: string; ps: P[] }[] = [
  { cls: "strip", ps: [C.b0, C.b1, C.s1, C.s0] },
  { cls: "slope", ps: [C.s0, C.s1, C.f1, C.f0] },
  { cls: "front", ps: [C.f0, C.f1, C.g1, C.g0] },
  { cls: "end", ps: [C.b0, C.gb0, C.g0, C.f0, C.s0] }, // the left end faces the viewer
];

function Stage({
  x,
  y,
  n,
  label,
  dy,
  children,
}: {
  x: number;
  y: number;
  n: number;
  label: string;
  dy: number;
  children: React.ReactNode;
}) {
  return (
    <g transform={`translate(${x} ${y})`} className={`pb-stage pb-s${n}`}>
      <text className="pb-label" x={0} y={dy}>
        <tspan className="pb-n">{n}</tspan> {label}
      </text>
      {children}
    </g>
  );
}

export default function ProcessBackdrop() {
  return (
    <svg
      className="process-backdrop"
      viewBox="0 0 1600 1000"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <filter id="pb-pencil">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.03"
            numOctaves="2"
            seed="7"
          />
          <feDisplacementMap in="SourceGraphic" scale="3.5" />
        </filter>
        <linearGradient id="pb-slope" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--sage-soft)" />
          <stop offset="1" stopColor="var(--sage)" />
        </linearGradient>
        <path id="pb-cutpath" d={NEST.map((ps) => path(ps)).join(" ")} />
      </defs>

      {/* the thread through the four steps */}
      <path
        className="pb-thread"
        d="M 260 470 C 220 560, 160 600, 150 650 M 860 840 C 960 880, 1060 880, 1130 840 M 1330 620 C 1360 590, 1360 520, 1330 470"
      />

      <Stage x={170} y={130} n={1} label="Sketch" dy={-22}>
        <g transform="scale(1.1)">
          <g filter="url(#pb-pencil)" className="pb-sketch">
            {NET.map((ps, i) => (
              <path
                key={i}
                d={path(ps)}
                pathLength={1}
                style={{ animationDelay: `${0.3 * i}s` }}
              />
            ))}
          </g>
          <g className="pb-hand">
            <text x={L / 2} y={-8} textAnchor="middle">
              200
            </text>
            <text x={L - 22} y={HB / 2 + 5}>
              88
            </text>
            <text x={L / 2} y={HB + S / 2 + 5} textAnchor="middle">
              strip 30
            </text>
            <text x={L / 2} y={HB + S + SLOPE / 2 + 5} textAnchor="middle">
              slope 75
            </text>
            <text x={L / 2} y={HB + S + SLOPE + HF / 2 + 5} textAnchor="middle">
              61
            </text>
            <text x={-12 - D / 2} y={HB + S + SLOPE + 20} textAnchor="middle">
              end ×2
            </text>
          </g>
        </g>
      </Stage>

      <Stage x={60} y={690} n={2} label="Pattern on the roll" dy={-22}>
        <g transform="scale(0.95)">
          <rect
            className="pb-roll"
            x={-10}
            y={-8}
            width={NEST_LENGTH + 20}
            height={ROLL + 8}
          />
          <text
            className="pb-dim"
            x={NEST_LENGTH + 18}
            y={ROLL / 2}
            transform={`rotate(90 ${NEST_LENGTH + 18} ${ROLL / 2})`}
            textAnchor="middle"
          >
            1500 mm
          </text>
          <g className="pb-exact">
            {NEST.map((ps, i) => (
              <polygon key={i} points={pts(ps)} />
            ))}
            <circle className="pb-knife" r={3.5}>
              <animateMotion dur="9s" repeatCount="indefinite">
                <mpath href="#pb-cutpath" />
              </animateMotion>
            </circle>
          </g>
        </g>
      </Stage>

      <Stage x={1150} y={880} n={3} label="Cut and sewn" dy={-290}>
        <g className="pb-wire" transform="scale(1.35)">
          {FACES.map((f, i) => (
            <path
              key={i}
              d={path(f.ps)}
              pathLength={1}
              style={{ animationDelay: `${0.4 * i}s` }}
            />
          ))}
        </g>
      </Stage>

      <Stage x={1150} y={400} n={4} label="The cover" dy={-290}>
        <g className="pb-cover" transform="scale(1.35)">
          {FACES.map((f, i) => (
            <polygon key={i} className={f.cls} points={pts(f.ps)} />
          ))}
          {/* an air vent with its hood on the front */}
          <polygon
            className="vent"
            points={pts([
              iso(140, D, 22),
              iso(165, D, 22),
              iso(165, D, 40),
              iso(140, D, 40),
            ])}
          />
          {[0, 1, 2, 3, 4].map((k) => {
            const x = 30 + k * 36;
            const a = iso(x, S + 4, HB + 60);
            const b = iso(x, S + 2, HB);
            const c = iso(x, D, HF);
            return (
              <path
                key={k}
                className="pb-drop"
                d={`M${a[0]} ${a[1]} L${b[0]} ${b[1]} L${c[0]} ${c[1]} l0 30`}
                pathLength={1}
                style={{ animationDelay: `${0.55 * k}s` }}
              />
            );
          })}
        </g>
      </Stage>
    </svg>
  );
}
