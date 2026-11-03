import { useEffect, useState } from "react";
import { Icon } from "./icons";

/** One open problem of the server's watchdog (GET /api/admin/problems, ADR-153). */
type Problem = {
  key: string;
  kind: string;
  subject: string;
  text: string;
  since: number;
};

const REFRESH_MS = 5 * 60 * 1000; // the watchdog itself checks every 10 minutes

function started(since: number): string {
  if (!since) return "";
  return new Date(since * 1000).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** The admins' red banner at the top of every page: the server's open problems, each with when
 * it started. Mounted for admins only; the API refuses everyone else. Nothing open: nothing. */
export function ProblemsBanner() {
  const [problems, setProblems] = useState<Problem[]>([]);
  useEffect(() => {
    let live = true;
    const load = () =>
      fetch("/api/admin/problems")
        .then((r) => (r.ok ? r.json() : { problems: [] }))
        .then((d: { problems?: Problem[] }) => {
          if (live) setProblems(d.problems ?? []);
        })
        .catch(() => undefined); // a missed refresh keeps the last list
    load();
    const t = window.setInterval(load, REFRESH_MS);
    return () => {
      live = false;
      window.clearInterval(t);
    };
  }, []);
  if (problems.length === 0) return null;
  return (
    <section
      className="card attention bad"
      role="alert"
      data-testid="server-problems"
    >
      <Icon name="st-bad" />
      <strong>
        {problems.length === 1
          ? "Server problem"
          : `${problems.length} server problems`}
      </strong>
      <ul style={{ margin: 0, paddingLeft: 18, flexBasis: "100%" }}>
        {problems.map((p) => (
          <li key={p.key}>
            {p.text}{" "}
            <span className="muted">since {started(p.since)}</span>
          </li>
        ))}
      </ul>
      <a className="btn sm" href="#/settings/system">
        System &amp; logs
      </a>
    </section>
  );
}
