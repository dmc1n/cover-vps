// "Have a photo or a link to your furniture?" (ADR-086): the customer's photo(s) or a webshop
// page, read by the AI into the configurator's product and sizes, to check before ordering.
import { useState } from "react";

export interface Suggestion {
  product: string;
  label: string;
  sizes: Record<string, number | boolean>;
  flags: Record<string, string[]>;
  check: string[];
  summary: string;
  source: { url: string | null; title: string | null; photos: number };
  match: { model_id: string; name?: string; score_pct?: number } | null;
}

const MAX_PHOTOS = 3;

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
        📷 {w("suggest_open")}
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
      {error && <p className="s-error">{error}</p>}
      {got && (
        <div className="s-suggest-card">
          <p>
            <b>{productName(got.product)}</b>
          </p>
          {got.summary && <p>{got.summary}</p>}
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
