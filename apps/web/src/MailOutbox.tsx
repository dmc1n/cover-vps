// Settings → System & logs: the mail outbox (ADR-129). Order notices, reviews and the Desk's
// digests are tried again until the mail server accepts them; what still waits or failed is
// listed here with its last error, and a failed mail can be sent again. The texts are not shown.
import { useCallback, useEffect, useState } from "react";
import { admin, type MailOutbox as Outbox } from "./api";

const when = (t: number) => new Date(t * 1000).toLocaleString();

export function MailOutbox() {
  const [o, setO] = useState<Outbox | null>(null);
  const [msg, setMsg] = useState("");
  const load = useCallback(() => {
    admin
      .mailOutbox()
      .then(setO)
      .catch((e) => setMsg(String(e)));
  }, []);
  useEffect(load, [load]);
  const again = async (id: number) => {
    setMsg("");
    try {
      await admin.mailRetry(id);
      setMsg("Back in the outbox: it is tried within half a minute.");
      load();
    } catch (e) {
      setMsg(String(e));
    }
  };
  if (!o) return msg ? <p className="error">{msg}</p> : null;
  return (
    <section className="card" data-testid="mail-outbox">
      <h3>Mail</h3>
      <p className="muted">
        Every mail the studio and the shop send is logged (to whom, the subject,
        sent or why not; never the text). Order notices, reviews and digests are
        tried again until the mail server accepts them.{" "}
        {o.failed > 0 ? (
          <b className="error">{o.failed} failed</b>
        ) : (
          "None failed"
        )}
        , {o.pending} waiting.{!o.configured && " No mail server is set."}
      </p>
      {o.outbox.length > 0 && (
        <table className="list">
          <thead>
            <tr>
              <th>Queued</th>
              <th>Kind</th>
              <th>To</th>
              <th>Subject</th>
              <th>Status</th>
              <th>Last error</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {o.outbox.map((m) => (
              <tr key={m.id} className="static">
                <td>{when(m.created)}</td>
                <td>{m.kind}</td>
                <td>{m.recipient}</td>
                <td>{m.subject}</td>
                <td className={m.status === "failed" ? "error" : ""}>
                  {m.status === "failed"
                    ? `failed after ${m.attempts} tries`
                    : `waiting (try ${m.attempts + 1} at ${when(m.next_try)})`}
                </td>
                <td>{m.last_error ?? ""}</td>
                <td>
                  {m.status === "failed" && m.can_retry ? (
                    <button type="button" onClick={() => again(m.id)}>
                      Send again
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <details>
        <summary>Last send attempts ({o.log.length})</summary>
        <table className="list">
          <tbody>
            {o.log.map((l, i) => (
              <tr key={i} className="static">
                <td>{when(l.time)}</td>
                <td>{l.kind}</td>
                <td>{l.recipient}</td>
                <td>{l.subject}</td>
                <td className={l.result === "sent" ? "" : "error"}>
                  {l.result}
                  {l.error ? `: ${l.error}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
      {msg && <p className="muted">{msg}</p>}
    </section>
  );
}
