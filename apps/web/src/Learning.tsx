import { useCallback, useEffect, useState } from "react";
import { fileUrl } from "./api";
import { modelHref } from "./nav";
import { Tpl } from "./layout";
import { ProductsSummary, type ProductsResult } from "./DeskProducts";

// Learning: the owner's drawings and their 3D models, paired by name (1.step + 1.pdf), each pair
// calculated and shown next to its drawing. The zip is uploaded on Covers → New cover (ADR-124).

interface Batch {
  id: string;
  file: string;
  pairs: { model_id: string; name: string; note: string; status: string }[];
  unpaired: string[];
  drawings_only?: string[];
}

/** The reference pairs' upload (Covers → New cover, ADR-124): one zip with drawings and their 3D
 * models, paired by name. Was the top of Learning. */
export function ReferenceUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  // a zip with the product list and no drawings goes to the Desk's product list (ADR-091)
  const [products, setProducts] = useState<ProductsResult | null>(null);

  const send = () => {
    if (!file) return;
    setError("");
    setDone("");
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest(); // XHR for upload progress on a large zip
    xhr.open("POST", "/api/references");
    xhr.upload.onprogress = (e) =>
      e.lengthComputable && setProgress(Math.round((100 * e.loaded) / e.total));
    xhr.onload = () => {
      setProgress(null);
      if (xhr.status >= 300) {
        try {
          setError(JSON.parse(xhr.responseText).detail ?? xhr.statusText);
        } catch {
          setError(xhr.statusText);
        }
      } else {
        setFile(null);
        try {
          const doc = JSON.parse(xhr.responseText);
          setProducts(doc.kind === "products" ? doc : null);
          if (doc.kind !== "products") setDone(file.name);
        } catch {
          setProducts(null);
          setDone(file.name);
        }
      }
    };
    xhr.onerror = () => {
      setProgress(null);
      setError("The upload failed. Check the connection and try again.");
    };
    xhr.send(form);
  };

  return (
    <section className="card upload">
      <h2>Reference pairs (learn from your own covers)</h2>
      <p className="muted">
        One zip with your drawings and their 3D models, with the same name for
        each pair: <code>1.step</code> + <code>1.pdf</code>, <code>2.stp</code>{" "}
        + <code>2.pdf</code>, or <code>kota.glb</code> + <code>kota.pdf</code>.
        Folders inside the zip do not matter. Every pair is calculated and shown
        next to your drawing on <a href="#/covers/learning">Learning</a>.
      </p>
      <div className="row">
        <input
          type="file"
          accept=".zip"
          aria-label="Reference pairs (zip)"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button
          className="primary"
          disabled={!file || progress !== null}
          onClick={send}
        >
          {progress !== null
            ? `Uploading ${progress} %`
            : "Upload and calculate"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {done && (
        <p className="muted">
          {done} is uploaded; the pairs are being calculated. See them on{" "}
          <a href="#/covers/learning">Learning</a>.
        </p>
      )}
      {products && (
        <div className="desk dp-host">
          <p className="muted">
            This zip held the product list and no drawings: it was linked to the
            drawing covers. See them at <a href="#/work/desk">the Desk</a>.
          </p>
          <ProductsSummary res={products} onClose={() => setProducts(null)} />
        </div>
      )}
    </section>
  );
}

/** Covers → Learning: what the reference pairs gave (the upload is on New cover). */
export function Learning() {
  const [batches, setBatches] = useState<Batch[] | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    fetch("/api/references")
      .then((r) => r.json())
      .then(setBatches)
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    const busy = batches?.some((b) =>
      b.pairs.some((p) => p.status === "queued" || p.status === "running"),
    );
    if (!busy) return;
    const t = window.setInterval(load, 5000);
    return () => window.clearInterval(t);
  }, [batches, load]);

  return (
    <Tpl
      kind="list"
      title="Learning"
      intro={
        <>
          Your covers against ours: every pair of your drawing and its 3D model,
          calculated and shown side by side. Upload pairs on{" "}
          <a href="#/covers/new">New cover</a>.
        </>
      }
    >
      {error && <p className="error">{error}</p>}
      <h2 className="count-line">Uploaded</h2>
      {!batches ? (
        <p className="muted">Loading…</p>
      ) : !batches.length ? (
        <p className="muted">Nothing uploaded yet.</p>
      ) : (
        batches.map((b) => (
          <section key={b.id} className="card">
            <strong>{b.file}</strong>{" "}
            <span className="muted">
              · {b.id} · {b.pairs.length} pairs
            </span>
            {(b.drawings_only ?? []).length > 0 && (
              <p className="muted">
                {b.drawings_only!.length} drawings without a 3D model: kept for
                the analysis of your covers.
              </p>
            )}
            {b.unpaired.length > 0 && (
              <p className="muted">
                Without a partner (not used): {b.unpaired.join(", ")}
              </p>
            )}
            <div className="gallery">
              {b.pairs.map((p) => (
                <a
                  key={p.model_id}
                  className="product"
                  href={modelHref(p.model_id)}
                >
                  <div className="pics">
                    <img
                      loading="lazy"
                      src={fileUrl(p.model_id, "reference.png")}
                      alt="your drawing"
                    />
                    {p.status === "done" ? (
                      <img
                        loading="lazy"
                        src={fileUrl(p.model_id, "cover.png")}
                        alt="calculated cover"
                      />
                    ) : (
                      <div className="nopic">
                        {p.status === "failed" ? "failed" : "calculating…"}
                      </div>
                    )}
                  </div>
                  <div className="name">{p.name}</div>
                  <div className="facts">
                    <span>{p.note}</span>
                  </div>
                </a>
              ))}
            </div>
          </section>
        ))
      )}
    </Tpl>
  );
}

export function Drawing({
  id,
  files,
  stamp,
}: {
  id: string;
  files: string[];
  stamp: number;
}) {
  const [ref, setRef] = useState<{
    sizes: { text: string; mm: number; line: string }[];
    vector_paths: number;
  } | null>(null);
  const [calc, setCalc] = useState<{ label: string; mm: number }[]>([]);
  useEffect(() => {
    fetch(`${fileUrl(id, "reference.json")}?v=${stamp}`)
      .then((r) => r.json())
      .then(setRef)
      .catch(() => setRef(null));
    fetch(`/api/models/${id}/sizes`)
      .then((r) => r.json())
      .then(setCalc)
      .catch(() => setCalc([]));
  }, [id, stamp]);
  if (!files.includes("reference.png"))
    return <p className="muted">No drawing for this product.</p>;
  return (
    <>
      <div className="side">
        <figure>
          <img
            src={`${fileUrl(id, "reference.png")}?v=${stamp}`}
            alt="your drawing"
          />
          <figcaption>
            Your drawing ·{" "}
            <a
              href={fileUrl(id, "reference.pdf")}
              target="_blank"
              rel="noreferrer"
            >
              PDF
            </a>
          </figcaption>
        </figure>
        <figure>
          {files.includes("cover.png") ? (
            <img
              src={`${fileUrl(id, "cover.png")}?v=${stamp}`}
              alt="calculated cover"
            />
          ) : (
            <div className="nopic">not calculated yet</div>
          )}
          <figcaption>Calculated cover</figcaption>
        </figure>
      </div>
      {ref && ref.vector_paths === 0 && (
        <p className="error">
          This drawing is a picture (a scan or photo): the program cannot read
          its lines, only its texts.
        </p>
      )}
      <div className="side">
        <section>
          <h3>Sizes in your drawing</h3>
          <table className="list">
            <tbody>
              {(ref?.sizes ?? [])
                .filter((s) => !s.text.toLowerCase().includes("in"))
                .map((s, i) => (
                  <tr key={i}>
                    <td>{s.text}</td>
                    <td className="muted">{s.line}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </section>
        <section>
          <h3>Calculated</h3>
          <table className="list">
            <tbody>
              {calc.map((c) => (
                <tr key={c.label}>
                  <td>{c.label}</td>
                  <td>{(c.mm / 10).toFixed(1)} cm</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </>
  );
}
