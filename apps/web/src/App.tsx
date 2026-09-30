import { useCallback, useEffect, useState } from "react";
import { api, cm, fileUrl, Job, ModelBrief, ModelDetail, Scalar, Step, STEP_LABEL, STEPS } from "./api";
import { BatchBar, ModelInfo, Revisions } from "./Catalogue";
import { SeamEditor } from "./SeamEditor";
import { Settings } from "./Settings";
import { Viewer } from "./Viewer";

// Pages: #/ (all models, upload) and #/model/<id> (one model).

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

export function App() {
  const hash = useHash();
  const m = hash.match(/^#\/model\/([a-z0-9-]+)/);
  return (
    <div className="app">
      <header>
        <a href="#/" className="brand">
          Cover patterns
        </a>
        {m && <span className="crumb">/ {m[1]}</span>}
      </header>
      <main>{m ? <ModelPage id={m[1]} /> : <ModelList />}</main>
    </div>
  );
}

function ModelList() {
  const [models, setModels] = useState<ModelBrief[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState("");
  const [status, setStatus] = useState("");
  const [grade, setGrade] = useState("");
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const load = useCallback(() => {
    api.models().then(setModels).catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);
  const q = query.toLowerCase();
  const shown = (models ?? []).filter(
    (m) =>
      (!q || m.id.includes(q) || m.tags.some((t) => t.toLowerCase().includes(q)) || m.notes.toLowerCase().includes(q)) &&
      (!family || (m.family ?? "") === (family === "-" ? "" : family)) &&
      (!status || m.status === status) &&
      (!grade || m.grade === grade),
  );
  const families = [...new Set((models ?? []).map((m) => m.family).filter(Boolean))] as string[];
  const selected = shown.filter((m) => picked[m.id]);
  return (
    <>
      <Upload />
      <h2>
        Models{" "}
        {models && (
          <span className="muted">
            ({models.length}: {models.filter((m) => m.grade === "ready").length} ready,{" "}
            {models.filter((m) => m.grade === "check").length} to check,{" "}
            {models.filter((m) => m.grade === "failed").length} failed)
          </span>
        )}
      </h2>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <input className="search" placeholder="Search name, tag or note…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select value={family} onChange={(e) => setFamily(e.target.value)}>
          <option value="">all families</option>
          <option value="-">no family</option>
          {families.map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
        <select value={grade} onChange={(e) => setGrade(e.target.value)}>
          <option value="">any cover</option>
          <option value="ready">ready</option>
          <option value="check">to check</option>
          <option value="failed">failed</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">any status</option>
          <option>draft</option>
          <option>checked</option>
          <option>production</option>
        </select>
      </div>
      {selected.length > 0 && <BatchBar selected={selected} onDone={load} />}
      {!models ? (
        <p className="muted">Loading…</p>
      ) : !models.length ? (
        <p className="muted">No models yet. Upload a 3D file above.</p>
      ) : (
        <table className="list">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  checked={shown.length > 0 && shown.every((m) => picked[m.id])}
                  onChange={(e) => setPicked(Object.fromEntries(shown.map((m) => [m.id, e.target.checked])))}
                />
              </th>
              <th>Model</th>
              <th>Cover</th>
              <th>Family</th>
              <th>Status</th>
              <th>Size (cm)</th>
              <th>Steps done</th>
              <th>Panels</th>
              <th>Worst stretch</th>
              <th>Warnings</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((m) => (
              <tr key={m.id} onClick={() => (window.location.hash = `#/model/${m.id}`)}>
                <td onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={!!picked[m.id]} onChange={(e) => setPicked({ ...picked, [m.id]: e.target.checked })} />
                </td>
                <td>
                  <a href={`#/model/${m.id}`}>{m.id}</a>
                  {m.tags.map((t) => (
                    <span key={t} className="badge">
                      {t}
                    </span>
                  ))}
                </td>
                <td title={m.reasons.join("\n")}>
                  <span className={`badge grade-${m.grade}`}>{m.grade}</span>
                </td>
                <td>{m.family ?? ""}</td>
                <td>
                  <span className={`badge status-${m.status}`}>{m.status}</span>
                </td>
                <td>{m.size_mm ? m.size_mm.map((v) => (v / 10).toFixed(0)).join(" × ") : "–"}</td>
                <td>
                  <Steps done={m.steps_done} />
                </td>
                <td>{m.panels ?? "–"}</td>
                <td>{m.max_stretch_pct != null ? `${m.max_stretch_pct.toFixed(1)} %` : "–"}</td>
                <td>{m.warnings.length || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function Steps({ done }: { done: Step[] }) {
  return (
    <span className="steps">
      {STEPS.map((s) => (
        <span key={s} className={done.includes(s) ? "step done" : "step"} title={STEP_LABEL[s]} />
      ))}
    </span>
  );
}

function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [units, setUnits] = useState("");
  const [up, setUp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const send = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const r = await api.upload(file, units, up);
      window.location.hash = `#/model/${r.model_id}`;
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  };
  return (
    <section className="card upload">
      <h2>New model</h2>
      <p className="muted">
        STEP, IGES, STL, OBJ, PLY or GLB. Everything runs by itself: import, cover, seams, patterns and the
        cut pieces.
      </p>
      <div className="row">
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <label>
          Units{" "}
          <select value={units} onChange={(e) => setUnits(e.target.value)}>
            <option value="">from the file</option>
            <option>mm</option>
            <option>cm</option>
            <option>m</option>
            <option>in</option>
          </select>
        </label>
        <label>
          Up{" "}
          <select value={up} onChange={(e) => setUp(e.target.value)}>
            <option value="">automatic</option>
            <option>z</option>
            <option>y</option>
            <option>x</option>
            <option>-z</option>
            <option>-y</option>
            <option>-x</option>
          </select>
        </label>
        <button className="primary" disabled={!file || busy} onClick={send}>
          {busy ? "Uploading…" : "Upload and run"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

type Tab = "3d" | "seams" | "patterns" | "sizes" | "cut" | "settings" | "revisions" | "files" | "log";
const TABS: [Tab, string][] = [
  ["3d", "3D"],
  ["seams", "Seams"],
  ["patterns", "Patterns"],
  ["sizes", "Size drawing"],
  ["cut", "Cut pieces"],
  ["settings", "Settings"],
  ["revisions", "Revisions"],
  ["files", "Downloads"],
  ["log", "Warnings and log"],
];

function ModelPage({ id }: { id: string }) {
  const [model, setModel] = useState<ModelDetail | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [tab, setTab] = useState<Tab>("3d");
  const [error, setError] = useState("");
  const [stamp, setStamp] = useState(Date.now());

  const load = useCallback(() => {
    api
      .model(id)
      .then((m) => {
        setModel(m);
        setJob(m.job ?? null);
      })
      .catch((e) => setError(String(e)));
  }, [id]);
  useEffect(load, [load]);

  // follow a running job
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const t = window.setInterval(async () => {
      const j = await api.job(job.id);
      setJob(j);
      if (j.status === "done" || j.status === "failed") {
        setStamp(Date.now());
        load();
      }
    }, 1500);
    return () => window.clearInterval(t);
  }, [job, load]);

  const run = async (steps: Step[] | null, trial: Record<string, Scalar>) => {
    try {
      setJob(await api.run(id, steps, trial));
    } catch (e) {
      setError(String(e));
    }
  };

  if (error && !model) return <p className="error">{error}</p>;
  if (!model) return <p className="muted">Loading…</p>;
  const running = job && (job.status === "queued" || job.status === "running");
  const has = (f: string) => model.files.includes(f);

  return (
    <>
      <section className="card summary">
        <div>
          <h2>{model.id}</h2>
          <p className="muted">
            {model.source}
            {model.size_mm && ` · ${model.size_mm.map((v) => (v / 10).toFixed(1)).join(" × ")} cm`}
            {model.cut && ` · hem ${cm(model.cut.hem_length_mm)}`}
            {model.cut?.skirt_height_mm && ` · skirt ${cm(model.cut.skirt_height_mm[0])}`}
            {model.pattern && ` · ${model.pattern.summary.panels} panels`}
            {model.finished?.sheet && ` · about ${(model.finished.sheet.roll_length_mm / 1000).toFixed(2)} m of roll`}
          </p>
        </div>
        <div className="actions">
          <button className="primary" disabled={!!running || !has("model.json")} onClick={() => run(null, {})}>
            Run again
          </button>
        </div>
      </section>
      <ModelInfo key={`${model.id}-${model.family}-${model.status}`} model={model} onSaved={load} />
      {job && <JobBar job={job} />}
      {error && <p className="error">{error}</p>}
      {model.diff && (model.diff.panels.length > 0 || model.diff.settings.length > 0) && (
        <section className="card diff">
          <strong>Since the run before:</strong>{" "}
          {model.diff.settings.map((s) => (
            <span key={s.key} className="chip">
              {s.key}: {String(s.before)} → {String(s.after)}
            </span>
          ))}
          {model.diff.panels.length === 0
            ? " no panel changed by more than 1 mm."
            : model.diff.panels.map((p) => (
                <span key={p.name} className="chip">
                  {p.name}:{" "}
                  {p.change === "size" && p.before_mm && p.after_mm
                    ? `${p.before_mm.map((v) => v.toFixed(0)).join("×")} → ${p.after_mm.map((v) => v.toFixed(0)).join("×")} mm`
                    : p.change}
                </span>
              ))}
        </section>
      )}
      <nav className="tabs">
        {TABS.map(([t, label]) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {label}
            {t === "log" && model.warnings.length > 0 && <span className="count">{model.warnings.length}</span>}
          </button>
        ))}
      </nav>
      <section className="tab">
        {tab === "3d" && <Viewer id={id} files={model.files} stamp={stamp} />}
        {tab === "seams" && <SeamEditor id={id} stamp={stamp} onJob={setJob} />}
        {tab === "patterns" && <Patterns model={model} stamp={stamp} />}
        {tab === "sizes" && <Pdf id={id} name="sizes.pdf" has={has("sizes.pdf")} stamp={stamp} />}
        {tab === "cut" && <CutPieces model={model} stamp={stamp} />}
        {tab === "settings" && <Settings id={id} onRun={(steps, trial) => run(steps, trial)} />}
        {tab === "revisions" && <Revisions model={model} />}
        {tab === "files" && <Files model={model} />}
        {tab === "log" && <Log model={model} job={job} />}
      </section>
    </>
  );
}

function JobBar({ job }: { job: Job }) {
  const trial = Object.keys(job.trial || {}).length;
  return (
    <section className={`card job ${job.status}`}>
      <span>
        {job.status === "queued" && "Waiting to run…"}
        {job.status === "running" && "Running…"}
        {job.status === "done" && "Last run finished."}
        {job.status === "failed" && `Last run failed: ${job.error ?? ""}`}
        {trial > 0 && ` (trial with ${trial} changed setting${trial > 1 ? "s" : ""}, not saved)`}
      </span>
      <span className="steps">
        {job.steps.map((s) => (
          <span key={s.name} className={`jobstep ${s.status}`}>
            {STEP_LABEL[s.name]}
          </span>
        ))}
      </span>
    </section>
  );
}

function Patterns({ model, stamp }: { model: ModelDetail; stamp: number }) {
  const [view, setView] = useState("pattern.svg");
  if (!model.pattern) return <p className="muted">No patterns yet.</p>;
  return (
    <>
      <div className="row">
        {[
          ["pattern.svg", "Flat pieces"],
          ["pattern-stretch.svg", "Stretch (red stretched, blue squeezed; full colour 2 %)"],
        ].map(([f, l]) => (
          <label key={f}>
            <input type="radio" checked={view === f} onChange={() => setView(f)} /> {l}
          </label>
        ))}
      </div>
      <div className="svgbox">
        <img src={`${fileUrl(model.id, view)}?v=${stamp}`} alt={view} />
      </div>
      <table className="list">
        <thead>
          <tr>
            <th>Panel</th>
            <th>Flat (narrowest × length)</th>
            <th>Stretch</th>
            <th>Roll</th>
          </tr>
        </thead>
        <tbody>
          {model.pattern.panels.map((p) => (
            <tr key={p.id}>
              <td>
                {p.id} {p.name}
              </td>
              <td>
                {cm(p.flat_width_mm)} × {cm(p.flat_length_mm)}
              </td>
              <td className={p.stretch.quantile_pct > 2 ? "bad" : "ok"}>{p.stretch.quantile_pct.toFixed(1)} %</td>
              <td className={p.fits_roll ? "ok" : "bad"}>{p.fits_roll ? "fits" : "too wide"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function CutPieces({ model, stamp }: { model: ModelDetail; stamp: number }) {
  if (!model.finished) return <p className="muted">No cut pieces yet.</p>;
  return (
    <>
      <p>
        <a href={fileUrl(model.id, "cut.dxf")} download>
          Download cut.dxf for the cutting table
        </a>{" "}
        ·{" "}
        <a href={fileUrl(model.id, "cutting-list.pdf")} target="_blank" rel="noreferrer">
          cutting list (PDF)
        </a>
      </p>
      <div className="svgbox">
        <img src={`${fileUrl(model.id, "cut.svg")}?v=${stamp}`} alt="cut pieces" />
      </div>
      <table className="list">
        <thead>
          <tr>
            <th>Piece</th>
            <th>Qty</th>
            <th>Size</th>
            <th>Area</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {model.finished.pieces.map((p) => (
            <tr key={p.id}>
              <td>
                {p.id} {p.name}
              </td>
              <td>{p.quantity}</td>
              <td>
                {cm(p.size_mm[0])} × {cm(p.size_mm[1])}
              </td>
              <td>{p.area_m2.toFixed(3)} m²</td>
              <td className="muted">{p.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Pdf({ id, name, has, stamp }: { id: string; name: string; has: boolean; stamp: number }) {
  if (!has) return <p className="muted">Not made yet.</p>;
  return <iframe className="pdf" title={name} src={`${fileUrl(id, name)}?v=${stamp}`} />;
}

const FILE_HELP: Record<string, string> = {
  "cut.dxf": "for the cutting table: pieces with allowances",
  "cut.svg": "the cut pieces, to view or print",
  "cutting-list.pdf": "every piece and the fabric needed",
  "sizes.pdf": "size drawing, seam to seam",
  "pattern.dxf": "flat pieces seam to seam (no allowances)",
  "pattern.svg": "flat pieces, to view or print",
  "pattern-stretch.svg": "stretch per piece",
  "model.glb": "the furniture (3D)",
  "hull.glb": "the cover surface (3D)",
  "preview.glb": "furniture and cover, water spots red (3D)",
  "panels.glb": "the panels in colour (3D)",
  "cover.json": "this model's own settings",
  "seams.json": "seams placed by hand",
};

function Files({ model }: { model: ModelDetail }) {
  return (
    <table className="list">
      <tbody>
        {model.files.map((f) => (
          <tr key={f}>
            <td>
              <a href={fileUrl(model.id, f)} download>
                {f}
              </a>
            </td>
            <td className="muted">{FILE_HELP[f] ?? ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Log({ model, job }: { model: ModelDetail; job: Job | null }) {
  return (
    <>
      <h3>Warnings</h3>
      {model.warnings.length ? (
        <ul className="warnings">
          {model.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">None.</p>
      )}
      {job && (
        <>
          <h3>Last run</h3>
          {job.steps.map((s) => (
            <details key={s.name} open={s.status === "failed"}>
              <summary>
                {STEP_LABEL[s.name]}: {s.status}
              </summary>
              <pre>{s.log || "(no output)"}</pre>
            </details>
          ))}
        </>
      )}
    </>
  );
}
