// Admin → Photo test (ADR-111): the shop's "start from a photo" on a photo of your own, with
// every step's own result: Google's search by image, the identification, the web searches, each
// found picture held against the photo, the final answer. Nothing is kept: the photo lives only
// for the request, the result only in this page.
import { useState } from "react";
import { PhotoTest as Result, shopAdmin } from "./api";

const host = (u: string) => {
  try {
    return new URL(u).hostname.replace(/^www\./, "");
  } catch {
    return u;
  }
};

function Link({ url, text }: { url: string; text?: string }) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer nofollow">
      {text || url}
    </a>
  );
}

export function PhotoTest() {
  const [photos, setPhotos] = useState<File[]>([]);
  const [url, setUrl] = useState("");
  const [lang, setLang] = useState("nl");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [got, setGot] = useState<Result | null>(null);

  const run = async () => {
    setBusy(true);
    setError("");
    setGot(null);
    try {
      setGot(await shopAdmin.photoTest(photos, url.trim(), lang));
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const t = got?.trace ?? {};
  const vis = t.image_search;
  const ident = t.identify ?? {};
  return (
    <div className="photo-test">
      <section className="card">
        <h3>Photo test</h3>
        <p className="muted">
          The shop's “start from a photo or a link”, step by step. Nothing is
          kept: the photo is only used for this test and the result only shows
          here. Each test costs what a customer's does (about €0.03), on the
          month's AI budget.
        </p>
        <div className="photo-test-form">
          <input
            type="file"
            accept="image/*"
            multiple
            onChange={(e) =>
              setPhotos(Array.from(e.target.files ?? []).slice(0, 3))
            }
          />
          <input
            type="url"
            placeholder="or a link to a product page"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <select value={lang} onChange={(e) => setLang(e.target.value)}>
            {["nl", "en", "de", "fr"].map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
          <button
            className="primary"
            disabled={busy || (!photos.length && !url.trim())}
            onClick={run}
          >
            {busy ? "Testing… (up to a minute)" : "Test"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      {got && (
        <>
          <section className="card">
            <h3>Result</h3>
            {got.error && <p className="error">{got.error}</p>}
            {got.proposal && (
              <>
                <p>
                  <b>{got.proposal.label}</b>{" "}
                  {Object.entries(got.proposal.sizes)
                    .map(([k, v]) => `${k} ${v}`)
                    .join(", ")}
                </p>
                <p>{got.proposal.summary}</p>
                {got.proposal.recognised ? (
                  <p>
                    Recognised:{" "}
                    <Link
                      url={got.proposal.recognised.url}
                      text={got.proposal.recognised.name}
                    />
                  </p>
                ) : got.proposal.comparable ? (
                  <p>
                    Comparable:{" "}
                    <Link
                      url={got.proposal.comparable.url}
                      text={got.proposal.comparable.title}
                    />
                  </p>
                ) : (
                  <p className="muted">
                    Nothing recognised: the photo's own estimates.
                  </p>
                )}
                <p className="muted">
                  To check: {got.proposal.check.join(", ") || "nothing"}
                </p>
              </>
            )}
            <p className="muted">
              {got.seconds} s · €{got.cost_eur.toFixed(4)} · settings{" "}
              {JSON.stringify(got.settings)}
            </p>
          </section>

          <section className="card">
            <h3>1. Search by image (Google Cloud Vision)</h3>
            {!vis ? (
              <p className="muted">Not run (a link was given).</p>
            ) : vis.off ? (
              <p className="muted">Switched off (suggest.reverse_search).</p>
            ) : (
              <>
                {vis.error && <p className="error">{vis.error}</p>}
                <p>
                  <b>Best guess:</b> {vis.labels.join(", ") || "—"}{" "}
                  <span className="muted">(not used as a query)</span>
                </p>
                <p>
                  <b>Entities:</b>{" "}
                  {vis.entities
                    .map((e) => `${e.name} (${e.score})`)
                    .join(", ") || "—"}
                </p>
                <p>
                  <b>Names of the matching pictures and pages</b> (given to the
                  identification):
                </p>
                <ul>
                  {vis.names.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
                <p>
                  <b>Pages showing the photo</b> ({vis.pages.length}; and{" "}
                  {vis.other_pages} pages about the label only, dropped):
                </p>
                <ol>
                  {vis.pages.map((p) => (
                    <li key={p.url}>
                      [{p.match}] <Link url={p.url} text={p.title || p.url} />{" "}
                      <span className="muted">{host(p.url)}</span>
                    </li>
                  ))}
                </ol>
                <details>
                  <summary>
                    Matching pictures ({vis.images.full.length} full,{" "}
                    {vis.images.partial.length} partial) and{" "}
                    {vis.similar.length} visually similar
                  </summary>
                  <ul>
                    {vis.images.full.map((u) => (
                      <li key={"f" + u}>
                        full: <Link url={u} />
                      </li>
                    ))}
                    {vis.images.partial.map((u) => (
                      <li key={"p" + u}>
                        partial: <Link url={u} />
                      </li>
                    ))}
                    {vis.similar.map((u) => (
                      <li key={"s" + u}>
                        similar: <Link url={u} />
                      </li>
                    ))}
                  </ul>
                </details>
              </>
            )}
          </section>

          <section className="card">
            <h3>2. Identification (Gemini)</h3>
            {t.identify_error && <p className="error">{t.identify_error}</p>}
            <p>
              <b>
                {String(ident.brand || "—")} {String(ident.model || "")}
              </b>{" "}
              (confidence {String(ident.brand_confidence ?? "—")}) ·{" "}
              {String(ident.type || "")}
            </p>
            <pre className="photo-test-json">
              {JSON.stringify(ident, null, 1)}
            </pre>
          </section>

          <section className="card">
            <h3>3. Web searches (Gemini + Google Search)</h3>
            {Object.entries(t.searches ?? {}).map(([k, pages]) => (
              <div key={k}>
                <p>
                  <b>By {k}</b> ({pages.length})
                </p>
                <ol>
                  {pages.map((p) => (
                    <li key={p.url}>
                      <Link url={p.url} text={p.title || p.url} />{" "}
                      <span className="muted">
                        {host(p.url)}
                        {p.same ? " · says: the same" : ""}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
            {!t.searches && <p className="muted">Not run.</p>}
          </section>

          <section className="card">
            <h3>4. Each found picture held against the photo</h3>
            {(t.candidates ?? []).length === 0 && (
              <p className="muted">No candidates.</p>
            )}
            <div className="photo-test-cands">
              {(t.candidates ?? []).map((c) => (
                <div
                  key={c.url}
                  className={`photo-test-cand ${c.same ? "same" : ""}`}
                >
                  {c.thumb ? (
                    <img src={c.thumb} alt="" />
                  ) : (
                    <div className="photo-test-nopic">no picture</div>
                  )}
                  <div>
                    <Link url={c.url} text={c.title || c.url} />
                    <p className="muted">
                      {c.from}
                      {c.match ? ` (${c.match} match)` : ""} · picture:{" "}
                      {c.picture || "—"}
                    </p>
                    <p>
                      similarity{" "}
                      <b>{c.similarity === null ? "—" : c.similarity}</b>
                      {c.same ? " · the same product" : ""} {c.why}
                    </p>
                    {Object.keys(c.sizes).length > 0 && (
                      <p className="muted">
                        sizes:{" "}
                        {Object.entries(c.sizes)
                          .map(([k, v]) => `${k} ${v}`)
                          .join(", ")}
                      </p>
                    )}
                    {c.sizes_text.length > 0 && (
                      <p className="muted">“{c.sizes_text[0]}”</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {t.basis && (
              <p>
                <b>Picked:</b> {JSON.stringify(t.basis)}
              </p>
            )}
          </section>

          <section className="card">
            <h3>5. The final answer (Gemini)</h3>
            {t.page && (
              <details>
                <summary>The link's page as read</summary>
                <pre className="photo-test-json">
                  {JSON.stringify(t.page, null, 1)}
                </pre>
              </details>
            )}
            <pre className="photo-test-json">
              {JSON.stringify(t.answer ?? {}, null, 1)}
            </pre>
          </section>
        </>
      )}
    </div>
  );
}
