import { useEffect, useState } from "react";
import { ACTION_LABEL, AiReview, fileUrl, Job } from "./api";

// AI advice on the cover's layout: what the AI thinks, and its suggestions as buttons. The AI
// changes nothing itself; a button applies one suggestion and calculates the cover again.

export function AiAdvice({ id, files, stamp, onJob }: { id: string; files: string[]; stamp: number; onJob: (j: Job) => void }) {
  const [review, setReview] = useState<AiReview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!files.includes("ai_review.json")) {
      setReview(null);
      return;
    }
    fetch(`${fileUrl(id, "ai_review.json")}?v=${stamp}`)
      .then((r) => r.json())
      .then(setReview)
      .catch(() => setReview(null));
  }, [id, stamp, files.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const post = async (url: string, body: unknown) => {
    setError("");
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const out = await r.json();
    if (!r.ok) setError(out.detail ?? r.statusText);
    else onJob(out as Job);
  };
  const ask = () => post(`/api/models/${id}/run`, { steps: ["ai"], trial: {} });
  const apply = (action: string, value: number | null) => post(`/api/models/${id}/ai-apply`, { action, value });

  return (
    <div className="ai">
      <div className="row">
        <button className="primary" onClick={ask}>
          {review ? "Ask the AI again" : "Ask the AI"}
        </button>
        <span className="muted">
          The AI gets this cover as text (pieces, sizes, stretch, seams) and says how to make it simpler. It changes
          nothing by itself.
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      {!review ? (
        <p className="muted">No advice yet.</p>
      ) : (
        <section className="card">
          <p>{review.summary}</p>
          <p className="muted">
            Pieces now: <strong>{review.pieces_now}</strong> · the AI's target: <strong>{review.target_pieces ?? "–"}</strong> ·{" "}
            {review.model}, {new Date(review.time * 1000).toLocaleString()}
          </p>
          {review.problems.length > 0 && (
            <>
              <h3>Problems</h3>
              <ul className="warnings">
                {review.problems.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </>
          )}
          <h3>Suggestions</h3>
          {review.suggestions.length === 0 && <p className="muted">None: the AI finds the layout good.</p>}
          {review.suggestions.map((s, i) => {
            const done = review.applied.some((a) => a.action === s.action && a.value === s.value);
            return (
              <div key={i} className="suggestion">
                <button disabled={done} onClick={() => apply(s.action, s.value)}>
                  {done ? "Applied" : "Apply"}
                </button>
                <div>
                  <strong>
                    {ACTION_LABEL[s.action] ?? s.action}
                    {s.value != null ? `: ${s.value / 10} cm` : ""}
                  </strong>
                  <div className="muted">{s.reason}</div>
                </div>
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}
