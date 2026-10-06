import { useEffect, useMemo, useState } from "react";
import { api, ModelParams, ParamSpec, Scalar, Step } from "./api";

// Every setting from config/defaults.yaml, in its group, with its comment as help and where
// the current value comes from. "Try" runs with the changes without saving them; "Save for this
// model" writes them to the model's cover.json.

const GROUP_LABEL: Record<string, string> = {
  hull: "Cover surface",
  seams: "Seams",
  roll: "Fabric roll",
  fabric: "Fabric",
  flatten: "Flat patterns",
  construction: "Construction",
  stitching: "Stitched seams",
  welding: "Welded seams",
  hem: "Hem",
  features: "Features (air vents, straps)",
  pen: "Pen marks",
  export: "Export",
  drawing: "Size drawing",
  import: "Import",
  tolerance: "Tolerances",
  units: "Units",
};


export function Settings({
  id,
  onRun,
}: {
  id: string;
  onRun: (steps: Step[], trial: Record<string, Scalar>) => void;
}) {
  const [specs, setSpecs] = useState<ParamSpec[]>([]);
  const [current, setCurrent] = useState<ModelParams | null>(null);
  const [edits, setEdits] = useState<Record<string, Scalar>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({ seams: true });
  const [filter, setFilter] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    api.specs().then(setSpecs);
    api.params(id).then(setCurrent);
  }, [id]);

  const groups = useMemo(() => {
    const out: Record<string, ParamSpec[]> = {};
    const f = filter.toLowerCase();
    for (const s of specs) {
      if (f && !(s.key.toLowerCase().includes(f) || s.comment.toLowerCase().includes(f))) continue;
      (out[s.group] ??= []).push(s);
    }
    return out;
  }, [specs, filter]);

  if (!current) return <p className="muted">Loading settings…</p>;
  const changed = Object.keys(edits).length > 0;

  // every step after import; the server skips the ones whose inputs did not change (ADR-080)
  const firstStep = (): Step[] => ["hull", "cut", "flatten", "export"];


  const save = async () => {
    const own: Record<string, Scalar> = {};
    for (const [k, v] of Object.entries(current.values)) if (current.sources[k] === "model") own[k] = v;
    try {
      const saved = await api.saveParams(id, { ...own, ...edits });
      setCurrent(saved);
      const steps = firstStep();
      setEdits({});
      setMessage("Saved for this model. Running again…");
      onRun(steps, {});
    } catch (e) {
      setMessage(String(e));
    }
  };

  const reset = async (key: string) => {
    const own: Record<string, Scalar> = {};
    for (const [k, v] of Object.entries(current.values))
      if (current.sources[k] === "model" && k !== key) own[k] = v;
    setCurrent(await api.saveParams(id, own));
    setMessage(`${key} is back to the company default (run again to see the effect).`);
  };

  return (
    <div className="settings">
      <div className="settings-bar">
        <input placeholder="Search settings…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button disabled={!changed} onClick={() => onRun(firstStep(), edits)}>
          Try without saving
        </button>
        <button className="primary" disabled={!changed} onClick={save}>
          Save for this model
        </button>
        <button disabled={!changed} onClick={() => setEdits({})}>
          Undo changes
        </button>
        {message && <span className="muted">{message}</span>}
      </div>
      {Object.entries(groups).map(([group, list]) => (
        <section key={group} className="group">
          <h3 onClick={() => setOpen({ ...open, [group]: !open[group] })}>
            {open[group] || filter ? "▾" : "▸"} {GROUP_LABEL[group] ?? group}
            <span className="muted"> ({list.length})</span>
          </h3>
          {(open[group] || filter) &&
            list.map((s) => {
              const value = s.key in edits ? edits[s.key] : current.values[s.key];
              const source = s.key in edits ? "changed" : current.sources[s.key];
              const set = (v: Scalar) => {
                const next = { ...edits };
                if (v === current.values[s.key]) delete next[s.key];
                else next[s.key] = v;
                setEdits(next);
              };
              return (
                <div key={s.key} className="param">
                  <div className="param-name">
                    <code>{s.key.slice(s.group.length + 1)}</code>
                    {s.to_confirm && <span className="badge warn" title="Still to confirm">to confirm</span>}
                    <span className={`badge ${source}`}>{source}</span>
                    {source === "model" && (
                      <button className="link" onClick={() => reset(s.key)}>
                        use default
                      </button>
                    )}
                  </div>
                  <div className="param-input">
                    <Input spec={s} value={value} onChange={set} />
                  </div>
                  <div className="param-help">{s.comment}</div>
                </div>
              );
            })}
        </section>
      ))}
    </div>
  );
}

function Input({ spec, value, onChange }: { spec: ParamSpec; value: Scalar; onChange: (v: Scalar) => void }) {
  if (spec.kind === "bool")
    return <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />;
  if (spec.kind === "choice" && spec.choices)
    return (
      <select value={String(value)} onChange={(e) => onChange(e.target.value)}>
        {spec.choices.map((c) => (
          <option key={c}>{c}</option>
        ))}
      </select>
    );
  if (spec.kind === "int" || spec.kind === "number")
    return (
      <input
        type="number"
        step={spec.kind === "int" ? 1 : "any"}
        value={String(value)}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (e.target.value !== "" && !Number.isNaN(n)) onChange(spec.kind === "int" ? Math.round(n) : n);
        }}
      />
    );
  return <input value={String(value)} onChange={(e) => onChange(e.target.value)} />;
}
