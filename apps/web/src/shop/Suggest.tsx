// "Have a photo or a link to your furniture?" (ADR-086): the customer's photo(s) or a webshop
// page, read by the AI into the configurator's product and sizes, to check before ordering.
import { useEffect, useMemo, useState } from "react";
import { Icon } from "./Icons";

export interface Suggestion {
  product: string;
  label: string;
  sizes: Record<string, number | boolean>;
  flags: Record<string, string[]>;
  check: string[];
  summary: string;
  source: { url: string | null; title: string | null; photos: number };
  /** a photo alone: the very product, recognised (brand and model) and confirmed by
   * comparing its picture with the photo (ADR-092) */
  recognised?: {
    url: string;
    title: string;
    name: string;
    brand: string;
  } | null;
  /** a photo alone: a similar product the web search found, its sizes the basis */
  comparable?: { url: string; title: string | null } | null;
  match: { model_id: string; name?: string; score_pct?: number } | null;
}

const MAX_PHOTOS = 3;

// the steps a suggestion goes through, with roughly when each starts (s): shown while waiting
const WAIT_STEPS: [string, number][] = [
  ["suggest_step_look", 0],
  ["suggest_step_search", 5],
  ["suggest_step_compare", 18],
  ["suggest_step_propose", 32],
];

export function Suggest({
  w,
  lang,
  productName,
  onUse,
}: {
  w: (key: string, vars?: Record<string, string | number>) => string;
  lang: string;
  productName: (key: string) => string;
  onUse: (s: Suggestion, photos: File[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [got, setGot] = useState<Suggestion | null>(null);
  const [since, setSince] = useState(0); // seconds waited, for the waiting panel

  // while we look the furniture up (20-60 s): a counter of the seconds waited
  useEffect(() => {
    if (!busy) return;
    setSince(0);
    const t0 = Date.now();
    const id = window.setInterval(
      () => setSince(Math.floor((Date.now() - t0) / 1000)),
      1000,
    );
    return () => window.clearInterval(id);
  }, [busy]);
  const thumb = useMemo(
    () => (photos[0] ? URL.createObjectURL(photos[0]) : ""),
    [photos],
  );
  useEffect(
    () => () => {
      if (thumb) URL.revokeObjectURL(thumb);
    },
    [thumb],
  );

  const read = async () => {
    setBusy(true);
    setError("");
    setGot(null);
    const body = new FormData();
    body.append("url", url.trim());
    body.append("lang", lang);
    for (const p of photos) body.append("photos", p);
    try {
      const r = await fetch("/api/shop/suggest", { method: "POST", body });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? String(r.status));
      setGot(d);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  if (!open)
    return (
      <button className="s-suggest-open" onClick={() => setOpen(true)}>
        <Icon name="camera" /> {w("suggest_open")}
      </button>
    );
  return (
    <section className="s-suggest">
      <p className="s-suggest-title">{w("suggest_title")}</p>
      <p className="s-muted">{w("suggest_help")}</p>
      <label className="s-suggest-photo">
        <input
          type="file"
          accept="image/*"
          capture="environment"
          multiple
          onChange={(e) =>
            setPhotos(Array.from(e.target.files ?? []).slice(0, MAX_PHOTOS))
          }
        />
        <Icon name="camera" />
        <span>
          {photos.length
            ? w("suggest_photos", { n: photos.length })
            : w("suggest_photo")}
        </span>
      </label>
      <input
        className="s-suggest-url"
        type="url"
        inputMode="url"
        placeholder={w("suggest_link")}
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <button
        className="s-btn"
        disabled={busy || (!url.trim() && !photos.length)}
        onClick={read}
      >
        {busy ? w("suggest_reading") : w("suggest_go")}
      </button>
      {busy && (
        <div className="s-wait" role="status" aria-live="polite">
          {thumb && (
            <div className="s-wait-photo">
              <img src={thumb} alt="" />
              <span className="s-wait-scan" />
            </div>
          )}
          <ol className="s-wait-steps">
            {WAIT_STEPS.map(([key, from], i) => {
              const next = WAIT_STEPS[i + 1]?.[1] ?? Infinity;
              const state =
                since >= next ? "done" : since >= from ? "now" : "todo";
              return (
                <li key={key} className={state}>
                  {w(key)}
                </li>
              );
            })}
          </ol>
          <div className="s-wait-bar">
            <span />
          </div>
          <p className="s-muted">{w("suggest_waited", { n: since })}</p>
        </div>
      )}
      <p className="s-muted s-privacy">{w("suggest_privacy")}</p>
      {error && <p className="s-error">{error}</p>}
      {got && (
        <div className="s-suggest-card">
          <p>
            <b>{productName(got.product)}</b>
          </p>
          {got.summary && <p>{got.summary}</p>}
          {got.recognised && (
            <p className="s-muted">
              {w("suggest_recognised")}{" "}
              <a
                href={got.recognised.url}
                target="_blank"
                rel="noopener noreferrer nofollow"
              >
                {got.recognised.name || got.recognised.title}
              </a>
              . {w("suggest_recognised_note")}
            </p>
          )}
          {got.comparable && (
            <p className="s-muted">
              {w("suggest_comparable")}{" "}
              <a
                href={got.comparable.url}
                target="_blank"
                rel="noopener noreferrer nofollow"
              >
                {got.comparable.title || got.comparable.url}
              </a>
            </p>
          )}
          {got.check.length > 0 && (
            <p className="s-muted">{w("suggest_check")}</p>
          )}
          {got.match && (
            <p className="s-muted">
              {w("suggest_match", {
                name: got.match.name ?? got.match.model_id,
              })}
            </p>
          )}
          <button
            className="s-btn"
            onClick={() => {
              onUse(got, photos);
              setOpen(false);
            }}
          >
            {w("suggest_use")}
          </button>
        </div>
      )}
    </section>
  );
}
