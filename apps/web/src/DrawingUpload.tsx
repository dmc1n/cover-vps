// Route A (ADR-081): upload a drawing (PDF); the program reads it itself and builds the cover,
// or says why it could not ("needs a person"). Nothing is guessed.
import { useEffect, useState } from "react";
import { api, type DrawingRead, type Job } from "./api";

export function DrawingUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [model, setModel] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [read, setRead] = useState<DrawingRead | null>(null);

  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const t = setTimeout(async () => {
      try {
        const j = await api.job(job.id);
        setJob(j);
        if ((j.status === "done" || j.status === "failed") && model)
          setRead(await api.drawingRead(model).catch(() => null));
      } catch (e) {
        setError(String(e));
      }
    }, 1500);
    return () => clearTimeout(t);
  }, [job, model]);

  const send = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    setRead(null);
    try {
      const r = await api.uploadDrawing(file);
      setModel(r.model_id);
      setJob(r.job);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const running =
    !!job && (job.status === "queued" || job.status === "running");
  const conflicts = read?.outline?.conflicts ?? [];
  return (
    <section className="card upload">
      <h2>New cover from a drawing</h2>
      <p className="muted">
        Your drawing as a PDF. The program reads the views, the sizes (by their
        arrows) and the number of air vents itself, builds the cover, puts the
        vents by your rule and splits the pieces to fit the roll. When it is not
        sure it says why and builds nothing: the cover then waits at the top of
        the Desk for a person.
      </p>
      <div className="row">
        <input
          type="file"
          accept=".pdf,application/pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button
          className="primary"
          disabled={!file || busy || running}
          onClick={send}
        >
          {busy
            ? "Uploading…"
            : running
              ? "Reading the drawing…"
              : "Upload drawing (PDF)"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {job?.status === "failed" && (
        <p className="error">
          The build failed: {job.error ?? "see the model's job log"}
        </p>
      )}
      {read && read.status === "built" && model && (
        <p>
          <b>Built</b> from the{" "}
          {read.reader === "outline" ? "drawn outline" : "drawing's views"}:{" "}
          {read.pieces} pieces, {read.vents} air vents
          {read.features?.vents_from
            ? ` (count ${read.features.vents_from} on the drawing)`
            : ""}
          . <a href={`#/model/${model}`}>Open the cover</a> ·{" "}
          <a href={`#/desk/${model}`}>To the Desk</a>
          {conflicts.length > 0 && (
            <span className="error">
              {" "}
              Sizes on the drawing contradict each other (
              {conflicts.map((c) => `${c.written_cm} cm`).join(", ")}): the
              cover follows the written circumference; please check.
            </span>
          )}
        </p>
      )}
      {read && read.status === "needs a person" && (
        <div className="warn">
          <b>Needs a person:</b> the program could not read this drawing surely
          and built nothing.
          <ul>
            {read.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <a href={`#/desk/${model}`}>It waits at the top of the Desk.</a>
          <p className="muted">
            Or let the AI read it: a proposal (about 1–5 cents), marked
            "read by the AI", that a person approves at the Desk.
          </p>
          <button
            disabled={running || !model}
            onClick={async () => {
              if (!model) return;
              setError("");
              setRead(null);
              try {
                setJob((await api.aiReadDrawing(model)).job);
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            Let the AI read it
          </button>
        </div>
      )}
    </section>
  );
}
