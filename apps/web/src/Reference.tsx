// The workshop's own reference for this model (ADR-070): upload a 3D model of the cover or a PDF
// (the drawing or pattern), and see how the program's cover compares: the deviation in mm with a
// coloured 3D view, the PDF's sizes found or not, the AI's differences, and lessons to accept.
import { useCallback, useEffect, useState } from "react";
import { Scene } from "./shop/Scene";

interface Surface {
  mean_mm: number;
  p95_mm: number;
  max_mm: number;
  within_fit_pct: number;
  roomier_pct: number;
  tighter_pct: number;
  size_mm: { ours: number[]; theirs: number[] };
  reference: string;
  error?: string;
}
interface Drawing {
  reference: string;
  written_mm: number[];
  matched: { written_mm: number; ours: string; ours_mm: number }[];
  missing_mm: number[];
  ai?: {
    summary?: string;
    differences?: {
      what: string;
      reference: string;
      program: string;
      matters: string;
    }[];
    lessons?: { rule: string; check: string; applies_to: string }[];
  };
  ai_error?: string;
  error?: string;
}
interface State {
  files: string[];
  compare: { surface?: Surface; drawing?: Drawing };
  running: boolean;
  has_view: boolean;
}

export function Reference({ id, canEdit }: { id: string; canEdit: boolean }) {
  const [s, setS] = useState<State | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [stamp, setStamp] = useState(0);
  const load = useCallback(
    () =>
      fetch(`/api/models/${id}/reference`)
        .then((r) => r.json())
        .then(setS)
        .catch((e) => setMsg(String(e))),
    [id],
  );
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (!s?.running) return;
    const t = setTimeout(() => {
      load();
      setStamp(Date.now());
    }, 4000);
    return () => clearTimeout(t);
  }, [s, load]);

  const upload = async (file: File) => {
    setBusy(true);
    setMsg("");
    const body = new FormData();
    body.append("file", file);
    try {
      const r = await fetch(`/api/models/${id}/reference`, {
        method: "POST",
        body,
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ?? r.status);
      setS(d);
      setMsg(`${file.name} received: comparing…`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };
  const accept = async (i: number) => {
    const r = await fetch(`/api/models/${id}/reference/lessons/${i}`, {
      method: "POST",
    });
    const d = await r.json();
    setMsg(
      r.ok
        ? `Lesson kept (${d.lessons} in all): the AI follows it from now on.`
        : d.detail,
    );
  };
  if (!s) return <p className="muted">{msg || "Loading…"}</p>;
  const sf = s.compare.surface;
  const dr = s.compare.drawing;
  return (
    <div className="reference">
      <section className="card">
        <h3>Your reference</h3>
        <p className="muted">
          Upload what you know is right for this model: a 3D model of the cover
          (STEP, IGES, STL, OBJ, GLB: a surface model) and/or a PDF (your
          drawing or pattern). The program compares it with its own cover; the
          differences are kept, and what you accept becomes a lesson for all
          covers.
        </p>
        {canEdit && (
          <label className="button">
            {busy ? "Uploading…" : "Upload a reference"}
            <input
              type="file"
              hidden
              accept=".pdf,.step,.stp,.iges,.igs,.stl,.obj,.ply,.glb"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            />
          </label>
        )}
        {s.running && (
          <p>Comparing… (a PDF with the AI takes about a minute)</p>
        )}
        {msg && <p className="muted">{msg}</p>}
        {s.files.length > 0 && (
          <p className="muted">
            Kept:{" "}
            {s.files
              .filter((f) => !f.endsWith(".json"))
              .map((f) => (
                <a
                  key={f}
                  href={`/api/models/${id}/reference/${f.split(".")[0]}`}
                >
                  {f}{" "}
                </a>
              ))}
          </p>
        )}
      </section>

      {sf && (
        <section className="card">
          <h3>Your 3D model against the program's cover</h3>
          {sf.error ? (
            <p className="error">{sf.error}</p>
          ) : (
            <>
              <table className="list">
                <tbody>
                  <tr>
                    <td>Within ±5 mm</td>
                    <td>
                      <b>{sf.within_fit_pct} %</b> of the cover
                    </td>
                  </tr>
                  <tr>
                    <td>Deviation</td>
                    <td>
                      mean {sf.mean_mm} mm · 95 % within {sf.p95_mm} mm ·
                      largest {sf.max_mm} mm
                    </td>
                  </tr>
                  <tr>
                    <td>Ours roomier / tighter</td>
                    <td>
                      {sf.roomier_pct} % / {sf.tighter_pct} %
                    </td>
                  </tr>
                  <tr>
                    <td>Size (mm)</td>
                    <td>
                      ours {sf.size_mm.ours.join(" × ")} · yours{" "}
                      {sf.size_mm.theirs.join(" × ")}
                    </td>
                  </tr>
                </tbody>
              </table>
              {s.has_view && (
                <>
                  <p className="muted">
                    The program's cover coloured by the deviation: green within
                    ±5 mm, sand where it is roomier, red where it is tighter
                    than yours.
                  </p>
                  <div style={{ height: 420 }}>
                    <Scene
                      url={`/api/models/${id}/reference/compare.glb?${stamp}`}
                    />
                  </div>
                </>
              )}
            </>
          )}
        </section>
      )}

      {dr && (
        <section className="card">
          <h3>Your PDF against the program's pattern</h3>
          {dr.error ? (
            <p className="error">{dr.error}</p>
          ) : (
            <>
              <p>
                <b>
                  {dr.matched.length} of {dr.written_mm.length}
                </b>{" "}
                sizes on your PDF are found in the program's pattern
                {dr.missing_mm.length > 0 && (
                  <>
                    ; not found:{" "}
                    <b>{dr.missing_mm.map((x) => `${x / 10} cm`).join(", ")}</b>
                  </>
                )}
                .
              </p>
              {dr.ai?.summary && <p>{dr.ai.summary}</p>}
              {dr.ai_error && <p className="error">AI: {dr.ai_error}</p>}
              {(dr.ai?.differences?.length ?? 0) > 0 && (
                <table className="list">
                  <thead>
                    <tr>
                      <th>Difference</th>
                      <th>Yours</th>
                      <th>The program's</th>
                      <th>Matters</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dr.ai!.differences!.map((d, i) => (
                      <tr key={i}>
                        <td>{d.what}</td>
                        <td>{d.reference}</td>
                        <td>{d.program}</td>
                        <td>{d.matters}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {(dr.ai?.lessons?.length ?? 0) > 0 && (
                <>
                  <h4>What the program could learn</h4>
                  <ul>
                    {dr.ai!.lessons!.map((l, i) => (
                      <li key={i}>
                        {l.rule}{" "}
                        <span className="muted">(check: {l.check})</span>{" "}
                        {canEdit && (
                          <button className="link" onClick={() => accept(i)}>
                            Accept
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
