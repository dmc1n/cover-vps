import { useEffect, useState } from "react";
import { api, Diff, Job, ModelBrief, ModelDetail, revisionUrl, Status, Step, STEP_LABEL } from "./api";

// M7: family, status, tags and notes of a model; its revisions; running many models at once.

const STATUS_HELP: Record<Status, string> = {
  draft: "being worked on",
  checked: "patterns looked over",
  production: "cut from",
};

export function ModelInfo({ model, onSaved }: { model: ModelDetail; onSaved: () => void }) {
  const [families, setFamilies] = useState<string[]>([]);
  const [family, setFamily] = useState(model.family ?? "");
  const [status, setStatus] = useState<Status>(model.status);
  const [tags, setTags] = useState(model.tags.join(", "));
  const [notes, setNotes] = useState(model.notes);
  const [message, setMessage] = useState("");
  useEffect(() => {
    api.families().then(setFamilies);
  }, []);
  const changed =
    family !== (model.family ?? "") || status !== model.status || tags !== model.tags.join(", ") || notes !== model.notes;
  const save = async () => {
    try {
      await api.setInfo(model.id, {
        family: family || null,
        status,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
        notes,
      });
      setMessage(
        family !== (model.family ?? "")
          ? "Saved. The family's settings apply from the next run (Run again)."
          : "Saved.",
      );
      onSaved();
    } catch (e) {
      setMessage(String(e));
    }
  };
  return (
    <section className="card info">
      <div className="row">
        <label>
          Family{" "}
          <select value={family} onChange={(e) => setFamily(e.target.value)}>
            <option value="">none</option>
            {families.map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
        </label>
        <label>
          Status{" "}
          <select value={status} onChange={(e) => setStatus(e.target.value as Status)}>
            {(["draft", "checked", "production"] as Status[]).map((s) => (
              <option key={s} value={s}>
                {s} ({STATUS_HELP[s]})
              </option>
            ))}
          </select>
        </label>
        <label>
          Tags <input value={tags} placeholder="lounge, outdoor" onChange={(e) => setTags(e.target.value)} />
        </label>
        <button className="primary" disabled={!changed} onClick={save}>
          Save
        </button>
        {message && <span className="muted">{message}</span>}
      </div>
      <textarea
        className="notes"
        placeholder="Notes for the machine operator"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
    </section>
  );
}

export function Revisions({ model }: { model: ModelDetail }) {
  const revs = [...(model.revisions ?? [])].reverse();
  const [a, setA] = useState<number | null>(null);
  const [b, setB] = useState<number | null>(null);
  const [diff, setDiff] = useState<Diff | null>(null);
  useEffect(() => {
    if (a != null && b != null && a !== b) api.compare(model.id, a, b).then(setDiff);
    else setDiff(null);
  }, [a, b, model.id]);
  if (!revs.length) return <p className="muted">No revisions yet: every export keeps one.</p>;
  return (
    <>
      <p className="muted">
        Every run that makes cut pieces is kept here with its settings. Pick two (A and B) to see what changed.
      </p>
      <table className="list">
        <thead>
          <tr>
            <th>A</th>
            <th>B</th>
            <th>Revision</th>
            <th>When</th>
            <th>Status</th>
            <th>Panels</th>
            <th>Worst stretch</th>
            <th>Roll</th>
            <th>Warnings</th>
            <th>Files</th>
          </tr>
        </thead>
        <tbody>
          {revs.map((r) => (
            <tr key={r.number}>
              <td>
                <input type="radio" name="a" checked={a === r.number} onChange={() => setA(r.number)} />
              </td>
              <td>
                <input type="radio" name="b" checked={b === r.number} onChange={() => setB(r.number)} />
              </td>
              <td>
                {r.number}
                {r.trial.length > 0 && <span className="badge changed" title={r.trial.join(", ")}>trial</span>}
              </td>
              <td>{new Date(r.time * 1000).toLocaleString()}</td>
              <td>{r.status}</td>
              <td>{r.panels}</td>
              <td className={r.max_stretch_pct > 2 ? "bad" : "ok"}>{r.max_stretch_pct.toFixed(1)} %</td>
              <td>{r.roll_length_mm != null ? `${(r.roll_length_mm / 1000).toFixed(2)} m` : "–"}</td>
              <td>{r.warnings}</td>
              <td>
                <a href={revisionUrl(model.id, r.number, "cut.dxf")} download>
                  cut.dxf
                </a>{" "}
                <a href={revisionUrl(model.id, r.number, "pattern.json")} target="_blank" rel="noreferrer">
                  pattern.json
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {diff && (
        <section className="card diff">
          <strong>
            Revision {a} → {b}:
          </strong>{" "}
          {diff.settings.map((s) => (
            <span key={s.key} className="chip">
              {s.key}: {String(s.before)} → {String(s.after)}
            </span>
          ))}
          {diff.panels.length === 0
            ? " no panel changed by more than 1 mm."
            : diff.panels.map((p) => (
                <span key={p.name} className="chip">
                  {p.name}:{" "}
                  {p.before_mm && p.after_mm
                    ? `${p.before_mm.map((v) => v.toFixed(0)).join("×")} → ${p.after_mm.map((v) => v.toFixed(0)).join("×")} mm`
                    : p.change}
                </span>
              ))}
        </section>
      )}
    </>
  );
}

export function BatchBar({ selected, onDone }: { selected: ModelBrief[]; onDone: () => void }) {
  const [steps, setSteps] = useState<Step[]>(["hull", "cut", "flatten", "export"]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  const running = jobs.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(async () => {
      const next = await Promise.all(jobs.map((j) => api.job(j.id)));
      setJobs(next);
      if (!next.some((j) => j.status === "queued" || j.status === "running")) onDone();
    }, 2000);
    return () => window.clearInterval(t);
  }, [jobs, running, onDone]);
  const start = async () => {
    setError("");
    try {
      setJobs((await api.batch(selected.map((m) => m.id), steps)).jobs);
    } catch (e) {
      setError(String(e));
    }
  };
  const all: Step[] = ["hull", "cut", "flatten", "export"];
  return (
    <section className="card batch">
      <div className="row">
        <strong>{selected.length} selected:</strong>
        {all.map((s) => (
          <label key={s}>
            <input
              type="checkbox"
              checked={steps.includes(s)}
              onChange={(e) => setSteps(e.target.checked ? all.filter((x) => x === s || steps.includes(x)) : steps.filter((x) => x !== s))}
            />
            {STEP_LABEL[s]}
          </label>
        ))}
        <button className="primary" disabled={!selected.length || !steps.length || running} onClick={start}>
          Run these
        </button>
        {error && <span className="error">{error}</span>}
      </div>
      {jobs.length > 0 && (
        <p className="muted">
          {jobs.map((j) => (
            <span key={j.id} className={`jobstep ${j.status === "done" ? "done" : j.status === "failed" ? "failed" : "running"}`}>
              {j.model_id}: {j.status}
            </span>
          ))}{" "}
          {!running && "Open a model to see what changed (Revisions)."}
        </p>
      )}
    </section>
  );
}
