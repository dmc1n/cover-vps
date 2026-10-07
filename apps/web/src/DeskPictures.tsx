// Pictures at the Desk (ADR-096): the approver attaches pictures to a reject or a comment
// himself, instead of mailing a screenshot. A picture comes from a snapshot of the 3D view or
// of the drawing, a file, a drop or a paste (Ctrl+V); it is then marked in red (arrow, circle,
// freehand line) and kept as a PNG. The server checks each one and keeps it in the model's
// desk/ folder; the history shows them as thumbnails.
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface Pending {
  key: number;
  blob: Blob; // the marked picture, PNG
  url: string; // an object URL of the blob, for the thumbnail
  source: string; // the unmarked picture, to mark again
  name?: string; // the server's name once uploaded
}

export const pictureUrl = (id: string, name: string) =>
  `/api/models/${encodeURIComponent(id)}/files/desk/${encodeURIComponent(name)}`;

const ACCEPT = ["image/jpeg", "image/png", "image/webp"];
const RED = "#e0241b";

/** Upload the marked pictures; the names the server gives back go with the action. */
export async function uploadPictures(
  id: string,
  pics: Pending[],
): Promise<string[]> {
  if (!pics.length) return [];
  const form = new FormData();
  pics.forEach((p, i) => form.append("files", p.blob, `picture-${i + 1}.png`));
  const r = await fetch(`/api/desk/${encodeURIComponent(id)}/pictures`, {
    method: "POST",
    body: form,
  });
  if (r.status === 401) window.dispatchEvent(new Event("login-needed"));
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail ?? `${r.status}`);
  return data.pictures as string[];
}

const readAsDataUrl = (f: Blob) =>
  new Promise<string>((ok, fail) => {
    const rd = new FileReader();
    rd.onload = () => ok(String(rd.result));
    rd.onerror = () => fail(rd.error);
    rd.readAsDataURL(f);
  });

let nextKey = 1;

/** The row of buttons, the drop zone and the thumbnails of the pictures still to send. */
export function PictureTray({
  pending,
  onChange,
  snapshot3d,
  drawingUrl,
  max,
}: {
  pending: Pending[];
  onChange: (p: Pending[]) => void;
  snapshot3d: () => string | null;
  drawingUrl: string | null;
  max: number;
}) {
  const [marking, setMarking] = useState<{
    source: string;
    replace?: number;
  } | null>(null);
  const [over, setOver] = useState(false);
  const [note, setNote] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const pendingRef = useRef(pending);
  pendingRef.current = pending;
  const full = pending.length >= max;

  const fromFile = useCallback(
    async (f: File | Blob) => {
      setNote("");
      if (!ACCEPT.includes(f.type)) {
        setNote("Only JPG, PNG or WebP pictures.");
        return;
      }
      if (pendingRef.current.length >= max) {
        setNote(`At most ${max} pictures.`);
        return;
      }
      setMarking({ source: await readAsDataUrl(f) });
    },
    [max],
  );

  // Ctrl+V while the dialog is open: a picture from the clipboard
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if (marking) return;
      const item = [...(e.clipboardData?.items ?? [])].find((i) =>
        i.type.startsWith("image/"),
      );
      const f = item?.getAsFile();
      if (!f) return;
      e.preventDefault();
      fromFile(f);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [fromFile, marking]);

  const done = (blob: Blob, source: string) => {
    const url = URL.createObjectURL(blob);
    if (marking?.replace != null) {
      onChange(
        pending.map((p) => {
          if (p.key !== marking.replace) return p;
          URL.revokeObjectURL(p.url);
          return { ...p, blob, url, name: undefined }; // marked again: send again
        }),
      );
    } else {
      onChange([...pending, { key: nextKey++, blob, url, source }]);
    }
    setMarking(null);
  };

  return (
    <div
      className={`d-pics ${over ? "over" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) fromFile(f);
      }}
    >
      <div className="d-pics-bar">
        <span className="d-pics-label">Pictures</span>
        <button
          type="button"
          className="d-btn d-ghost d-small"
          disabled={full}
          onClick={() => {
            setNote("");
            const shot = snapshot3d();
            if (shot) setMarking({ source: shot });
            else setNote("The 3D view is not ready yet.");
          }}
        >
          Snapshot 3D
        </button>
        {drawingUrl && (
          <button
            type="button"
            className="d-btn d-ghost d-small"
            disabled={full}
            onClick={() => setMarking({ source: drawingUrl })}
          >
            Snapshot drawing
          </button>
        )}
        <button
          type="button"
          className="d-btn d-ghost d-small"
          disabled={full}
          onClick={() => fileRef.current?.click()}
        >
          Upload…
        </button>
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT.join(",")}
          hidden
          aria-label="Upload a picture"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) fromFile(f);
          }}
        />
        <span className="d-pics-hint">
          or drop / paste (Ctrl+V) a picture here
        </span>
      </div>
      {pending.length > 0 && (
        <ul className="d-pics-list">
          {pending.map((p) => (
            <li key={p.key}>
              <img
                src={p.url}
                alt="picture to send"
                title="Mark again"
                onClick={() => setMarking({ source: p.source, replace: p.key })}
              />
              <button
                type="button"
                aria-label="Remove this picture"
                onClick={() => {
                  URL.revokeObjectURL(p.url);
                  onChange(pending.filter((x) => x.key !== p.key));
                }}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      {note && <span className="d-pics-note">{note}</span>}
      {marking && (
        <Marker
          source={marking.source}
          onDone={done}
          onCancel={() => setMarking(null)}
        />
      )}
    </div>
  );
}

type Tool = "arrow" | "circle" | "pen";
interface Shape {
  tool: Tool;
  pts: [number, number][];
}

function drawShape(g: CanvasRenderingContext2D, s: Shape, lw: number) {
  const [a, b] = [s.pts[0], s.pts[s.pts.length - 1]];
  g.strokeStyle = RED;
  g.fillStyle = RED;
  g.lineWidth = lw;
  g.lineCap = "round";
  g.lineJoin = "round";
  g.beginPath();
  if (s.tool === "pen") {
    g.moveTo(a[0], a[1]);
    for (const p of s.pts.slice(1)) g.lineTo(p[0], p[1]);
    g.stroke();
  } else if (s.tool === "circle") {
    const rx = Math.abs(b[0] - a[0]) / 2;
    const ry = Math.abs(b[1] - a[1]) / 2;
    if (rx < 1 && ry < 1) return;
    g.ellipse((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, rx, ry, 0, 0, Math.PI * 2);
    g.stroke();
  } else {
    // an arrow from where the drag began to its point, where the drag ended
    const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (len < 2) return;
    const head = Math.min(lw * 5, len * 0.6);
    const back = [
      b[0] - Math.cos(ang) * head * 0.8,
      b[1] - Math.sin(ang) * head * 0.8,
    ];
    g.moveTo(a[0], a[1]);
    g.lineTo(back[0], back[1]);
    g.stroke();
    g.beginPath();
    g.moveTo(b[0], b[1]);
    g.lineTo(
      b[0] - Math.cos(ang - 0.45) * head,
      b[1] - Math.sin(ang - 0.45) * head,
    );
    g.lineTo(
      b[0] - Math.cos(ang + 0.45) * head,
      b[1] - Math.sin(ang + 0.45) * head,
    );
    g.closePath();
    g.fill();
  }
}

/** The marking editor: red arrows, circles and freehand lines on a picture; undo, clear. */
export function Marker({
  source,
  onDone,
  onCancel,
}: {
  source: string;
  onDone: (png: Blob, source: string) => void;
  onCancel: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [err, setErr] = useState("");
  const [tool, setTool] = useState<Tool>("arrow");
  const [shapes, setShapes] = useState<Shape[]>([]);
  const drag = useRef<Shape | null>(null);

  useEffect(() => {
    const im = new Image();
    im.onload = () => setImg(im);
    im.onerror = () => setErr("This picture could not be opened.");
    im.src = source;
  }, [source]);

  const lw = img
    ? Math.max(3, Math.round(Math.max(img.width, img.height) / 220))
    : 3;
  const paint = useCallback(() => {
    const c = canvas.current;
    if (!c || !img) return;
    const g = c.getContext("2d");
    if (!g) return;
    g.clearRect(0, 0, c.width, c.height);
    g.drawImage(img, 0, 0);
    for (const s of shapes) drawShape(g, s, lw);
    if (drag.current) drawShape(g, drag.current, lw);
  }, [img, shapes, lw]);
  useEffect(() => {
    const c = canvas.current;
    if (c && img) {
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
    }
    paint();
  }, [img, paint]);

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        setShapes((s) => s.slice(0, -1));
      }
      e.stopPropagation();
    };
    window.addEventListener("keydown", on, true);
    return () => window.removeEventListener("keydown", on, true);
  }, [onCancel]);

  const at = (e: React.PointerEvent): [number, number] => {
    const c = canvas.current!;
    const r = c.getBoundingClientRect();
    return [
      ((e.clientX - r.left) / r.width) * c.width,
      ((e.clientY - r.top) / r.height) * c.height,
    ];
  };

  // outside the action bar: its backdrop blur would hold a fixed overlay inside the bar
  return createPortal(
    <div className="d-marker" role="dialog" aria-label="Mark the picture">
      <div className="d-marker-box">
        <div className="d-marker-bar">
          <strong>Mark the picture</strong>
          <span className="d-seg-ctl">
            {(["arrow", "circle", "pen"] as const).map((t) => (
              <button
                key={t}
                type="button"
                className={tool === t ? "on" : ""}
                onClick={() => setTool(t)}
              >
                {t === "arrow"
                  ? "➚ Arrow"
                  : t === "circle"
                    ? "◯ Circle"
                    : "✎ Line"}
              </button>
            ))}
          </span>
          <button
            type="button"
            className="d-btn d-ghost d-small"
            disabled={!shapes.length}
            onClick={() => setShapes(shapes.slice(0, -1))}
          >
            Undo
          </button>
          <button
            type="button"
            className="d-btn d-ghost d-small"
            disabled={!shapes.length}
            onClick={() => setShapes([])}
          >
            Clear
          </button>
          <span className="d-marker-grow" />
          <button
            type="button"
            className="d-btn d-ghost d-small"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            className="d-btn d-primary d-small"
            disabled={!img}
            onClick={() =>
              canvas.current?.toBlob((b) => b && onDone(b, source), "image/png")
            }
          >
            Use this picture
          </button>
        </div>
        {err ? (
          <p className="d-err">{err}</p>
        ) : (
          <div className="d-marker-stage">
            <canvas
              ref={canvas}
              aria-label="the picture to mark"
              onPointerDown={(e) => {
                (e.target as HTMLCanvasElement).setPointerCapture(e.pointerId);
                const p = at(e);
                drag.current = { tool, pts: [p, p] };
                paint();
              }}
              onPointerMove={(e) => {
                const s = drag.current;
                if (!s) return;
                const p = at(e);
                if (s.tool === "pen") s.pts.push(p);
                else s.pts[1] = p;
                paint();
              }}
              onPointerUp={() => {
                const s = drag.current;
                drag.current = null;
                if (s) setShapes((all) => [...all, s]);
              }}
            />
          </div>
        )}
        <p className="d-marker-help">
          Drag to draw: an arrow points where you let go. Ctrl+Z undoes, Esc
          closes.
        </p>
      </div>
    </div>,
    document.querySelector(".desk") ?? document.body,
  );
}

/** The pictures of a history entry, as thumbnails. */
export function PictureThumbs({
  id,
  names,
  onOpen,
}: {
  id: string;
  names: string[];
  onOpen: (url: string) => void;
}) {
  return (
    <span className="d-thumbs">
      {names.map((n) => (
        <img
          key={n}
          src={pictureUrl(id, n)}
          alt="attached picture"
          loading="lazy"
          title="Click to enlarge"
          onClick={() => onOpen(pictureUrl(id, n))}
        />
      ))}
    </span>
  );
}
