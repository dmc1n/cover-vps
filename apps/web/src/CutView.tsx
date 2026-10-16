// The Cutting file view (ADR-147): what the cutting table gets, drawn on the server from the
// cover's cut.dxf itself (never cut.svg), on the Desk card and the cover page. Viewing is not
// downloading: the drawing is an SVG, with "PREVIEW – NOT FOR CUTTING" across it until the Desk
// approved this very cut file, and the DXF stays behind the approval gate.
//
// One viewer (CutViewer): the layers CUT, PEN and the pen texts switched on and off, the piece
// names, zoom and pan with a mouse, a trackpad or two fingers (an iPad), fit, a scale bar in cm,
// a click on a piece for its box and the length of each edge, a measuring tool. CuttingFile puts
// an older revision's drawing beside the current one and marks what changed.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cutview,
  type CutDiff,
  type CutDiffRow,
  type CutMeta,
  type CutPiece,
  type CutStatus,
} from "./api";
import { Icon, IconButton, Info, StatusChip } from "./icons";

type VB = { x: number; y: number; w: number; h: number };
type Pt = [number, number];
type Layers = { cut: boolean; pen: boolean; text: boolean; names: boolean };
const LAYERS_KEY = "cutview-layers";
const ALL_ON: Layers = { cut: true, pen: true, text: true, names: true };

/** Changes marked on a drawing: the piece's index → its status in the comparison. */
export type Marks = Record<number, CutStatus>;

const cmText = (mm: number) => `${(mm / 10).toFixed(1)} cm`;
const STATUS_WORDS: Record<CutStatus, string> = {
  added: "New piece",
  removed: "Piece gone",
  size: "Size changed",
  outline: "Outline changed",
  pen: "Pen marks changed",
  same: "Same",
};
const STATUS_TONE: Record<CutStatus, string> = {
  added: "approved",
  removed: "rejected",
  size: "warning",
  outline: "warning",
  pen: "waiting",
  same: "draft",
};

function readLayers(): Layers {
  try {
    const v = JSON.parse(localStorage.getItem(LAYERS_KEY) ?? "null");
    return v && typeof v === "object" ? { ...ALL_ON, ...v } : ALL_ON;
  } catch {
    return ALL_ON;
  }
}

/** A bar 1, 2 or 5 × 10ⁿ cm long, about `px` pixels on the screen. */
function scaleBar(mmPerPx: number, px = 110): { cm: number; px: number } {
  const want = (px * mmPerPx) / 10;
  const pow = 10 ** Math.floor(Math.log10(Math.max(want, 1e-6)));
  const cm = [1, 2, 5, 10]
    .map((k) => k * pow)
    .filter((c) => c <= want)
    .pop();
  const c = cm ?? pow;
  return { cm: c, px: (c * 10) / mmPerPx };
}

export function CutViewer({
  modelId,
  revision = null,
  marks,
  focus,
  label,
  testId = "cutview",
  onMeta,
}: {
  modelId: string;
  revision?: number | null;
  marks?: Marks;
  /** a piece to select and zoom to (the comparison's list); the nonce repeats a click */
  focus?: { index: number | null; nonce: number };
  label?: string;
  testId?: string;
  onMeta?: (m: CutMeta | null) => void;
}) {
  const [meta, setMeta] = useState<CutMeta | null>(null);
  const [inner, setInner] = useState("");
  const [box, setBox] = useState<VB | null>(null); // the whole drawing (with the band)
  const [vb, setVb] = useState<VB | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [layers, setLayers] = useState<Layers>(readLayers);
  const [sel, setSel] = useState<number | null>(null);
  const [measuring, setMeasuring] = useState(false);
  const [pts, setPts] = useState<Pt[]>([]);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const stage = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const vbRef = useRef<VB | null>(null);
  vbRef.current = vb;

  // the drawing and its meta, again when the cover or the revision changes
  useEffect(() => {
    let live = true;
    setErr(null);
    setMeta(null);
    setInner("");
    setSel(null);
    setPts([]);
    onMeta?.(null);
    cutview
      .meta(modelId, revision)
      .then(async (m) => {
        const text = await cutview.svg(modelId, revision, m.fingerprint);
        if (!live) return;
        const doc = new DOMParser().parseFromString(text, "image/svg+xml");
        const root = doc.documentElement;
        if (root.nodeName !== "svg" || !root.getAttribute("viewBox"))
          throw new Error("The drawing could not be read: reload the page");
        const [x, y, w, h] = (root.getAttribute("viewBox") ?? "0 0 1 1")
          .split(/\s+/)
          .map(Number);
        setBox({ x, y, w, h });
        setInner(root.innerHTML);
        setMeta(m);
        onMeta?.(m);
      })
      .catch((e: Error) => live && setErr(e.message));
    return () => {
      live = false;
    };
    // onMeta is a callback of the parent; a new one need not load the drawing again
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, revision]);

  // the stage's size: the view keeps the stage's proportions, so a pixel is the same
  // number of millimetres across and down
  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const ro = new ResizeObserver(() =>
      setSize({ w: el.clientWidth, h: el.clientHeight }),
    );
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const fitTo = useCallback(
    (b: VB, margin = 0.03): VB | null => {
      if (!size.w || !size.h) return null;
      const aspect = size.h / size.w;
      let { x, y, w, h } = b;
      x -= w * margin;
      y -= h * margin;
      w *= 1 + 2 * margin;
      h *= 1 + 2 * margin;
      if (h / w > aspect) {
        const nw = h / aspect;
        x -= (nw - w) / 2;
        w = nw;
      } else {
        const nh = w * aspect;
        y -= (nh - h) / 2;
        h = nh;
      }
      return { x, y, w, h };
    },
    [size],
  );
  const fit = useCallback(() => box && setVb(fitTo(box)), [box, fitTo]);

  // fit when the drawing arrives; on a resize keep the centre and the scale
  const fitted = useRef<string | null>(null);
  useEffect(() => {
    if (!box || !size.w || !size.h) return;
    const key = `${modelId}/${revision}/${meta?.fingerprint}`;
    if (fitted.current !== key || !vbRef.current) {
      fitted.current = key;
      setVb(fitTo(box));
      return;
    }
    const v = vbRef.current;
    const h = (v.w * size.h) / size.w;
    setVb({ ...v, y: v.y + (v.h - h) / 2, h });
  }, [box, size, fitTo, modelId, revision, meta?.fingerprint]);

  const mmPerPx = vb && size.w ? vb.w / size.w : 1;

  const toSvg = useCallback((cx: number, cy: number): Pt | null => {
    const el = stage.current;
    const v = vbRef.current;
    if (!el || !v) return null;
    const r = el.getBoundingClientRect();
    return [
      v.x + ((cx - r.left) * v.w) / r.width,
      v.y + ((cy - r.top) * v.h) / r.height,
    ];
  }, []);

  const zoomAt = useCallback(
    (cx: number, cy: number, factor: number) => {
      const v = vbRef.current;
      const p = toSvg(cx, cy);
      if (!v || !p || !box) return;
      const most = Math.max(box.w, box.h) * 4;
      const f = Math.min(Math.max(factor, 20 / v.w), most / v.w); // 2 cm .. 4 sheets
      const next = {
        x: p[0] - (p[0] - v.x) * f,
        y: p[1] - (p[1] - v.y) * f,
        w: v.w * f,
        h: v.h * f,
      };
      vbRef.current = next;
      setVb(next);
    },
    [toSvg, box],
  );
  const zoomCentre = (factor: number) => {
    const r = stage.current?.getBoundingClientRect();
    if (r) zoomAt(r.left + r.width / 2, r.top + r.height / 2, factor);
  };

  // the wheel (and a trackpad's pinch, which arrives as a wheel with ctrl): zoom at the pointer
  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const k = e.deltaMode === 1 ? 16 : 1;
      zoomAt(
        e.clientX,
        e.clientY,
        Math.exp((e.deltaY * k) / (e.ctrlKey ? 100 : 400)),
      );
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, [zoomAt]);

  // pan with one pointer, pinch with two; a press that hardly moved is a click
  const pointers = useRef(new Map<number, Pt>());
  const moved = useRef(0);
  const pinch = useRef<{ d: number; mid: Pt } | null>(null);
  const onDown = (e: React.PointerEvent) => {
    if (e.button !== 0 && e.pointerType === "mouse") return;
    try {
      stage.current?.setPointerCapture(e.pointerId);
    } catch {
      /* a pointer the browser no longer tracks: follow it without capture */
    }
    pointers.current.set(e.pointerId, [e.clientX, e.clientY]);
    if (pointers.current.size === 1) moved.current = 0;
    pinch.current = null;
  };
  const onMove = (e: React.PointerEvent) => {
    const prev = pointers.current.get(e.pointerId);
    if (!prev) return;
    pointers.current.set(e.pointerId, [e.clientX, e.clientY]);
    const v = vbRef.current;
    const el = stage.current;
    if (!v || !el) return;
    const scale = v.w / el.getBoundingClientRect().width;
    if (pointers.current.size === 1) {
      const dx = e.clientX - prev[0];
      const dy = e.clientY - prev[1];
      moved.current += Math.abs(dx) + Math.abs(dy);
      const next = { ...v, x: v.x - dx * scale, y: v.y - dy * scale };
      vbRef.current = next;
      setVb(next);
    } else if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      const mid: Pt = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      moved.current += 100;
      if (pinch.current && d > 0) {
        const pan = {
          ...v,
          x: v.x - (mid[0] - pinch.current.mid[0]) * scale,
          y: v.y - (mid[1] - pinch.current.mid[1]) * scale,
        };
        vbRef.current = pan;
        zoomAt(mid[0], mid[1], pinch.current.d / d);
      }
      pinch.current = { d, mid };
    }
  };
  const nearestCorner = (p: Pt): Pt => {
    if (!meta) return p;
    let best: Pt = p;
    let dist = 14 * mmPerPx; // snap within 14 px
    for (const pc of meta.pieces)
      for (const e of pc.edges) {
        const d = Math.hypot(e.a[0] - p[0], e.a[1] - p[1]);
        if (d < dist) {
          dist = d;
          best = e.a;
        }
      }
    return best;
  };
  const onUp = (e: React.PointerEvent) => {
    const was = pointers.current.size;
    pointers.current.delete(e.pointerId);
    pinch.current = null;
    if (was !== 1 || moved.current > 6) return;
    if (measuring) {
      const p = toSvg(e.clientX, e.clientY);
      if (!p) return;
      const q = nearestCorner(p);
      setPts((old) => (old.length === 1 ? [old[0], q] : [q]));
      return;
    }
    const hit = document
      .elementFromPoint(e.clientX, e.clientY)
      ?.closest("[data-piece]");
    const n = hit ? Number(hit.getAttribute("data-piece")) : null;
    setSel((old) => (n === null || old === n ? null : n));
  };
  const onCancel = (e: React.PointerEvent) => {
    pointers.current.delete(e.pointerId);
    pinch.current = null;
  };

  const zoomToPiece = useCallback(
    (pc: CutPiece) => {
      const [x0, y0, x1, y1] = pc.box;
      const pad = Math.max(x1 - x0, y1 - y0) * 0.25;
      const v = fitTo(
        {
          x: x0 - pad,
          y: y0 - pad,
          w: x1 - x0 + 2 * pad,
          h: y1 - y0 + 2 * pad,
        },
        0,
      );
      if (v) setVb(v);
    },
    [fitTo],
  );
  useEffect(() => {
    if (!focus || !meta) return;
    setSel(focus.index);
    const pc = focus.index === null ? null : meta.pieces[focus.index];
    if (pc) zoomToPiece(pc);
    // only when the parent asks (a new nonce)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce, meta]);

  // the selected piece and the comparison's marks on the server's own paths
  useEffect(() => {
    const root = svg.current;
    if (!root) return;
    root.querySelectorAll(".cv-piece").forEach((el) => {
      const n = Number(el.getAttribute("data-piece"));
      el.classList.toggle("cv-on", n === sel);
      for (const s of ["added", "removed", "size", "outline", "pen"])
        el.classList.toggle(`cv-m-${s}`, marks?.[n] === s);
    });
  }, [inner, sel, marks]);

  const toggle = (k: keyof Layers) =>
    setLayers((old) => {
      const next = { ...old, [k]: !old[k] };
      try {
        localStorage.setItem(LAYERS_KEY, JSON.stringify(next));
      } catch {
        /* a private window: the choice lasts this page only */
      }
      return next;
    });

  const picked = sel !== null && meta ? meta.pieces[sel] : null;
  const bar = scaleBar(mmPerPx);
  const fs = 12.5 * mmPerPx; // overlay type, 12.5 px on the screen at any zoom
  const measured =
    pts.length === 2
      ? Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
      : null;
  const hidden = Object.entries(layers)
    .filter(([, on]) => !on)
    .map(([k]) => `cv-hide-${k}`)
    .join(" ");
  const names = useMemo(
    () =>
      meta?.pieces.filter(
        (p) =>
          (p.box[2] - p.box[0]) / mmPerPx > p.name.length * 7.5 &&
          // the DXF's own label is still too small to read at this zoom
          (p.label_mm ?? 0) / mmPerPx < 9,
      ) ?? [],
    [meta, mmPerPx],
  );

  if (err)
    return (
      <div className="cv cv-empty" data-testid={testId}>
        <p className="muted">
          <Icon name="lock" size={14} /> {err}
        </p>
      </div>
    );

  return (
    <div
      className={`cv ${hidden}`.trim()}
      data-testid={testId}
      data-ready={meta && vb ? "1" : undefined}
      data-watermark={meta ? (meta.watermark ? "1" : "0") : undefined}
      data-pieces={meta?.pieces.length}
      data-selected={sel ?? undefined}
    >
      <div
        className="cv-bar"
        role="toolbar"
        aria-label={`Cutting file${label ? ` ${label}` : ""}`}
      >
        {label && <span className="cv-label">{label}</span>}
        {meta &&
          (meta.watermark ? (
            <StatusChip
              status="waiting"
              title="Not approved at the Desk: a preview only"
            >
              Preview
            </StatusChip>
          ) : (
            <StatusChip
              status="approved"
              title="The Desk approved this cut file"
            >
              Approved
            </StatusChip>
          ))}
        <span className="cv-layers seg" role="group" aria-label="Layers">
          {(
            [
              ["cut", "Cut", meta?.layers.cut],
              ["pen", "Pen", meta?.layers.pen],
              ["text", "Texts", meta?.layers.texts],
              ["names", "Names", meta?.pieces.length],
            ] as [keyof Layers, string, number | undefined][]
          ).map(([k, words, n]) => (
            <button
              key={k}
              type="button"
              className={layers[k] ? "on" : ""}
              aria-pressed={layers[k]}
              data-layer={k}
              title={`${layers[k] ? "Hide" : "Show"} ${words.toLowerCase()}`}
              onClick={() => toggle(k)}
            >
              <span className={`cv-swatch cv-sw-${k}`} aria-hidden="true" />
              {words}
              {n !== undefined && <span className="cv-n">{n}</span>}
            </button>
          ))}
        </span>
        <span className="cv-tools">
          <IconButton
            icon="zoom-out"
            label="Zoom out"
            onClick={() => zoomCentre(1.5)}
          />
          <IconButton
            icon="zoom-in"
            label="Zoom in"
            onClick={() => zoomCentre(1 / 1.5)}
          />
          <IconButton icon="fit" label="Fit to screen" onClick={fit} />
          <button
            type="button"
            className={`icon-btn ${measuring ? "on" : ""}`}
            aria-pressed={measuring}
            title="Measure a distance: click two points (corners snap)"
            aria-label="Measure a distance"
            onClick={() => {
              setMeasuring(!measuring);
              setPts([]);
            }}
          >
            <Icon name="measure" />
          </button>
        </span>
      </div>
      <div
        ref={stage}
        className={`cv-stage ${measuring ? "cv-measuring" : ""}`}
        data-testid={`${testId}-stage`}
        data-vb={
          vb
            ? [vb.x, vb.y, vb.w, vb.h].map((n) => n.toFixed(1)).join(" ")
            : undefined
        }
        tabIndex={0}
        aria-label="The cutting file: drag to move, pinch or scroll to zoom, click a piece"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onCancel}
        onKeyDown={(e) => {
          if (e.key === "+" || e.key === "=") zoomCentre(1 / 1.5);
          else if (e.key === "-") zoomCentre(1.5);
          else if (e.key === "0") fit();
          else if (e.key === "Escape") {
            setSel(null);
            setPts([]);
          } else return;
          e.preventDefault();
        }}
      >
        {!meta && <p className="cv-loading muted">Drawing the cutting file…</p>}
        {vb && (
          <svg
            ref={svg}
            className="cv-svg"
            viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
            preserveAspectRatio="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <g
              className="cv-drawing"
              dangerouslySetInnerHTML={{ __html: inner }}
            />
            <g className="cv-over" pointerEvents="none">
              {marks &&
                meta?.pieces.map((p) =>
                  marks[p.index] && marks[p.index] !== "same" ? (
                    <rect
                      key={`m${p.index}`}
                      className={`cv-mark cv-mark-${marks[p.index]}`}
                      x={p.box[0] - 8 * mmPerPx}
                      y={p.box[1] - 8 * mmPerPx}
                      width={p.box[2] - p.box[0] + 16 * mmPerPx}
                      height={p.box[3] - p.box[1] + 16 * mmPerPx}
                      rx={6 * mmPerPx}
                      vectorEffect="non-scaling-stroke"
                    />
                  ) : null,
                )}
              {names.map((p) => (
                <text
                  key={`n${p.index}`}
                  className="cv-name"
                  x={p.centre[0]}
                  y={p.centre[1]}
                  fontSize={fs * 1.15}
                  textAnchor="middle"
                  dominantBaseline="middle"
                >
                  {p.name}
                </text>
              ))}
              {picked && (
                <g className="cv-pick">
                  <rect
                    x={picked.box[0]}
                    y={picked.box[1]}
                    width={picked.box[2] - picked.box[0]}
                    height={picked.box[3] - picked.box[1]}
                    className="cv-pick-box"
                    vectorEffect="non-scaling-stroke"
                  />
                  {picked.edges.map((e, i) => (
                    <g key={i}>
                      <circle
                        cx={e.a[0]}
                        cy={e.a[1]}
                        r={3.5 * mmPerPx}
                        className="cv-corner"
                      />
                      <text
                        x={e.mid[0]}
                        y={e.mid[1]}
                        fontSize={fs}
                        className="cv-edge"
                        textAnchor="middle"
                        dominantBaseline="middle"
                        data-edge={i}
                      >
                        {`E${i + 1} ${(e.length_mm / 10).toFixed(1)}`}
                      </text>
                    </g>
                  ))}
                </g>
              )}
              {pts.length > 0 && (
                <g className="cv-measure">
                  {pts.length === 2 && (
                    <line
                      x1={pts[0][0]}
                      y1={pts[0][1]}
                      x2={pts[1][0]}
                      y2={pts[1][1]}
                      vectorEffect="non-scaling-stroke"
                    />
                  )}
                  {pts.map((p, i) => (
                    <circle key={i} cx={p[0]} cy={p[1]} r={4 * mmPerPx} />
                  ))}
                  {measured !== null && (
                    <text
                      x={(pts[0][0] + pts[1][0]) / 2}
                      y={(pts[0][1] + pts[1][1]) / 2 - 10 * mmPerPx}
                      fontSize={fs * 1.1}
                      textAnchor="middle"
                    >
                      {cmText(measured)}
                    </text>
                  )}
                </g>
              )}
            </g>
          </svg>
        )}
        {vb && (
          <div
            className="cv-scale"
            aria-label={`Scale: the bar is ${bar.cm} cm`}
          >
            <span className="cv-scale-bar" style={{ width: `${bar.px}px` }} />
            <span>{bar.cm >= 100 ? `${bar.cm / 100} m` : `${bar.cm} cm`}</span>
          </div>
        )}
        {measured !== null && (
          <div className="cv-readout" data-testid={`${testId}-distance`}>
            <Icon name="measure" size={14} /> {cmText(measured)} (
            {Math.round(measured)} mm)
          </div>
        )}
      </div>
      {picked ? (
        <aside className="cv-piece-card" data-testid={`${testId}-piece`}>
          <div className="cv-piece-head">
            <strong>{picked.name}</strong>
            <IconButton
              icon="close"
              label="Close the piece"
              onClick={() => setSel(null)}
            />
          </div>
          <dl className="cv-facts">
            <dt>Box</dt>
            <dd data-testid={`${testId}-size`}>
              {cmText(picked.size_mm[0])} × {cmText(picked.size_mm[1])}
            </dd>
            <dt>Area</dt>
            <dd>{picked.area_m2.toFixed(3)} m²</dd>
            <dt>Outline</dt>
            <dd>{cmText(picked.perimeter_mm)}</dd>
            {picked.openings > 0 && (
              <>
                <dt>Openings</dt>
                <dd>{picked.openings}</dd>
              </>
            )}
          </dl>
          <ol className="cv-edges">
            {picked.edges.map((e, i) => (
              <li key={i}>
                <span>E{i + 1}</span> {cmText(e.length_mm)}
              </li>
            ))}
          </ol>
        </aside>
      ) : (
        meta && (
          <p className="cv-hint muted">
            {meta.pieces.length} pieces · sheet {cmText(meta.sheet_mm[0] - 40)}{" "}
            × {cmText(meta.sheet_mm[1] - 40)}
            {Object.keys(meta.skipped).length > 0 &&
              ` · not drawn: ${Object.entries(meta.skipped)
                .map(([t, n]) => `${n} ${t}`)
                .join(", ")}`}
            {meta.layers.other > 0 &&
              ` · ${meta.layers.other} on other layers (grey)`}
          </p>
        )
      )}
    </div>
  );
}

/** The cover's cutting file, and next to it an older revision's with what changed. */
export function CuttingFile({
  modelId,
  revisions,
  compare,
  onCompare,
}: {
  modelId: string;
  revisions: { number: number; time: number }[];
  compare?: number | null;
  onCompare?: (n: number | null) => void;
}) {
  const [own, setOwn] = useState<number | null>(null);
  const with_ = compare !== undefined ? compare : own;
  const setWith = (n: number | null) => (onCompare ? onCompare(n) : setOwn(n));
  const [diff, setDiff] = useState<CutDiff | null>(null);
  const [diffErr, setDiffErr] = useState<string | null>(null);
  const [focus, setFocus] = useState<{
    a: number | null;
    b: number | null;
    nonce: number;
  }>({
    a: null,
    b: null,
    nonce: 0,
  });
  useEffect(() => {
    setDiff(null);
    setDiffErr(null);
    if (with_ == null) return;
    let live = true;
    cutview
      .diff(modelId, with_, null)
      .then((d) => live && setDiff(d))
      .catch((e: Error) => live && setDiffErr(e.message));
    return () => {
      live = false;
    };
  }, [modelId, with_]);
  const marksA: Marks = {};
  const marksB: Marks = {};
  for (const r of diff?.pieces ?? []) {
    if (r.a !== null) marksA[r.a] = r.status;
    if (r.b !== null) marksB[r.b] = r.status;
  }
  const changed = (diff?.pieces ?? []).filter((r) => r.status !== "same");
  const older = [...revisions].sort((a, b) => b.number - a.number);
  const show = (r: CutDiffRow) =>
    setFocus((f) => ({ a: r.a, b: r.b, nonce: f.nonce + 1 }));
  return (
    <section className="cutfile" data-testid="cutting-file">
      <div className="cutfile-head">
        <h3>
          <Icon name="cutting-file" /> Cutting file
        </h3>
        <Info label="About the cutting file">
          Exactly what the cutting table gets: this cover's cut.dxf, drawn on
          the server from the DXF itself. Red is cut, blue is drawn by the pen.
          Until the Desk approves this very cut file it says PREVIEW – NOT FOR
          CUTTING across it, and the DXF stays locked; a saved picture keeps the
          words. Click a piece for its size and the length of each edge; drag to
          move, scroll or pinch to zoom.
        </Info>
        {older.length > 0 && (
          <label className="cutfile-compare">
            <Icon name="compare" size={15} />
            <span>Compare with</span>
            <select
              value={with_ ?? ""}
              onChange={(e) =>
                setWith(e.target.value ? Number(e.target.value) : null)
              }
              data-testid="cutfile-compare"
            >
              <option value="">no other revision</option>
              {older.map((r) => (
                <option key={r.number} value={r.number}>
                  r{r.number} · {new Date(r.time * 1000).toLocaleDateString()}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {with_ != null && (
        <div className="cutfile-diff" data-testid="cutfile-diff">
          {diffErr && <p className="muted">{diffErr}</p>}
          {!diff && !diffErr && <p className="muted">Comparing…</p>}
          {diff && (
            <>
              <p className="cutfile-sum">
                {diff.same_file ? (
                  <StatusChip status="draft">The same cutting file</StatusChip>
                ) : diff.pen_only ? (
                  <StatusChip status="waiting">
                    Pen marks only: every cut line the same
                  </StatusChip>
                ) : changed.length === 0 ? (
                  <StatusChip status="draft">No piece changed</StatusChip>
                ) : null}
                {(["added", "removed", "size", "outline", "pen"] as CutStatus[])
                  .filter((s) => diff.counts[s])
                  .map((s) => (
                    <StatusChip
                      key={s}
                      status={STATUS_TONE[s]}
                      className={`cv-chip-${s}`}
                    >
                      {diff.counts[s]} {STATUS_WORDS[s].toLowerCase()}
                    </StatusChip>
                  ))}
              </p>
              {changed.length > 0 && (
                <table className="list cutfile-changes">
                  <thead>
                    <tr>
                      <th>Piece</th>
                      <th>What changed</th>
                      <th>r{diff.from}</th>
                      <th>Now</th>
                    </tr>
                  </thead>
                  <tbody>
                    {changed.map((r, i) => (
                      <tr
                        key={`${r.name}-${i}`}
                        data-status={r.status}
                        onClick={() => show(r)}
                        className="cutfile-row"
                      >
                        <td>
                          <button
                            type="button"
                            className="d-link"
                            onClick={() => show(r)}
                          >
                            {r.name}
                          </button>
                        </td>
                        <td>
                          <StatusChip status={STATUS_TONE[r.status]}>
                            {STATUS_WORDS[r.status]}
                          </StatusChip>
                          {r.status === "pen" &&
                            ((r.texts_added?.length ?? 0) > 0 ||
                              (r.texts_removed?.length ?? 0) > 0) && (
                              <span className="muted cutfile-texts">
                                {r.texts_added?.length
                                  ? ` + ${r.texts_added.join(", ")}`
                                  : ""}
                                {r.texts_removed?.length
                                  ? ` − ${r.texts_removed.join(", ")}`
                                  : ""}
                              </span>
                            )}
                        </td>
                        <td>
                          {r.before_mm
                            ? `${cmText(r.before_mm[0])} × ${cmText(r.before_mm[1])}`
                            : "–"}
                        </td>
                        <td>
                          {r.after_mm
                            ? `${cmText(r.after_mm[0])} × ${cmText(r.after_mm[1])}`
                            : "–"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      )}
      <div className={with_ != null ? "cutfile-two" : "cutfile-one"}>
        {with_ != null && (
          <CutViewer
            modelId={modelId}
            revision={with_}
            marks={marksA}
            focus={{ index: focus.a, nonce: focus.nonce }}
            label={`r${with_}`}
            testId="cutview-old"
          />
        )}
        <CutViewer
          modelId={modelId}
          marks={with_ != null ? marksB : undefined}
          focus={
            with_ != null ? { index: focus.b, nonce: focus.nonce } : undefined
          }
          label={with_ != null ? "Now" : undefined}
        />
      </div>
    </section>
  );
}
