// After sewing (ADR-111): what the workshop measured on the sewn cover, against the check
// list's points. The values go with "Fits" / "Does not fit"; the Desk keeps measured,
// calculated and the difference per point in desk.json, for the learning step (ADR-082) to
// see deviations that come back on many covers.
import { useEffect, useMemo, useState } from "react";

export interface CheckPoint {
  key: string;
  group: string;
  label: string;
  mm: number;
}
export interface MeasuredRow {
  key: string;
  label: string;
  expected_mm: number;
  measured_mm: number;
  diff_mm: number;
}

const GROUPS = ["Overall", "Skirt", "Air vents", "Pieces", "Seams"];
const cm = (mm: number) => (mm / 10).toFixed(1);

/** The check list as a form: one cm field per point. `onChange` gets the filled values in mm. */
export function MeasuredForm({
  id,
  onChange,
}: {
  id: string;
  onChange: (mm: Record<string, number>) => void;
}) {
  const [points, setPoints] = useState<CheckPoint[] | null>(null);
  const [err, setErr] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [more, setMore] = useState(false);
  useEffect(() => {
    let alive = true;
    setPoints(null);
    setValues({});
    fetch(`/api/models/${id}/checkpoints`)
      .then(async (r) => {
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.detail ?? `${r.status}`);
        return d as { points: CheckPoint[] };
      })
      .then((d) => alive && setPoints(d.points))
      .catch((e) => alive && setErr(String(e.message ?? e)));
    return () => {
      alive = false;
    };
  }, [id]);
  const parsed = useMemo(() => {
    const out: Record<string, number> = {};
    for (const [k, v] of Object.entries(values)) {
      const x = parseFloat(v.replace(",", "."));
      if (v.trim() && Number.isFinite(x)) out[k] = Math.round(x * 100) / 10; // cm -> mm
    }
    return out;
  }, [values]);
  useEffect(() => onChange(parsed), [parsed, onChange]);

  if (err) return <p className="d-muted">No check list: {err}</p>;
  if (!points) return <p className="d-muted">Loading the check list…</p>;
  const shown = points.filter(
    (p) => more || !["Pieces", "Seams"].includes(p.group),
  );
  return (
    <div className="d-measured" data-testid="measured-form">
      <p className="d-muted">
        Write what you measured on the sewn cover, in cm, along the fabric (the
        same points as the check list). Leave a field empty when you did not
        measure it. Then press Fits or Does not fit.
      </p>
      {GROUPS.map((g) => {
        const rows = shown.filter((p) => p.group === g);
        if (!rows.length) return null;
        return (
          <table key={g} className="d-table d-measured-table">
            <caption>{g}</caption>
            <tbody>
              {rows.map((p) => {
                const got = parsed[p.key];
                const d = got === undefined ? null : got - p.mm;
                return (
                  <tr key={p.key}>
                    <td>{p.label}</td>
                    <td className="num">{cm(p.mm)} cm</td>
                    <td>
                      <input
                        inputMode="decimal"
                        aria-label={`measured: ${p.label}`}
                        data-key={p.key}
                        value={values[p.key] ?? ""}
                        placeholder="cm"
                        onChange={(e) =>
                          setValues({ ...values, [p.key]: e.target.value })
                        }
                      />
                    </td>
                    <td
                      className={`num ${d === null ? "" : Math.abs(d) <= 5 ? "ok" : "off"}`}
                    >
                      {d === null ? "" : `${d > 0 ? "+" : ""}${cm(d)}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        );
      })}
      <button className="d-more" onClick={() => setMore(!more)}>
        {more ? "Only the main sizes" : "Also the pieces and seams"}
      </button>
    </div>
  );
}

/** A fit's measured values in the history: how many, and the largest differences. */
export function MeasuredSummary({ rows }: { rows: MeasuredRow[] }) {
  const worst = [...rows]
    .sort((a, b) => Math.abs(b.diff_mm) - Math.abs(a.diff_mm))
    .slice(0, 3);
  return (
    <em className="d-measured-sum">
      {" "}
      · measured {rows.length} size{rows.length === 1 ? "" : "s"}; largest
      difference{worst.length > 1 ? "s" : ""}:{" "}
      {worst
        .map((r) => `${r.label} ${r.diff_mm > 0 ? "+" : ""}${cm(r.diff_mm)} cm`)
        .join(", ")}
    </em>
  );
}
