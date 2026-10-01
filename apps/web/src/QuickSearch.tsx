import { useEffect, useMemo, useRef, useState } from "react";
import { api, ModelBrief } from "./api";

// Quick search in the header: type part of a name, tag or note; arrows and Enter open a model.
// The list of models is fetched once, when the page opens, so results show while typing.
export function QuickSearch() {
  const [models, setModels] = useState<ModelBrief[] | null>(null);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  const hits = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length || !models) return [];
    return models
      .filter((m) => {
        const text = `${m.id} ${m.tags.join(" ")} ${m.notes} ${m.family ?? ""}`.toLowerCase();
        return words.every((w) => text.includes(w));
      })
      .slice(0, 10);
  }, [q, models]);

  useEffect(() => {
    api.models().then(setModels).catch(() => setModels([]));
  }, []);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const go = (id: string) => {
    window.location.hash = `#/model/${id}`;
    setOpen(false);
    setQ("");
  };

  return (
    <div className="quick-search" ref={box}>
      <input
        type="search"
        placeholder="Search models…"
        aria-label="Search models"
        value={q}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQ(e.target.value);
          setAt(0);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setAt((a) => Math.min(a + 1, hits.length - 1));
          else if (e.key === "ArrowUp") setAt((a) => Math.max(a - 1, 0));
          else if (e.key === "Enter" && hits[at]) go(hits[at].id);
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && q && (
        <ul className="hits">
          {models === null && <li className="muted">Loading…</li>}
          {models !== null && hits.length === 0 && <li className="muted">Nothing found</li>}
          {hits.map((m, i) => (
            <li
              key={m.id}
              className={i === at ? "active" : ""}
              onMouseEnter={() => setAt(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                go(m.id);
              }}
            >
              <span className="id">{m.id}</span>
              <span className={`badge grade-${m.grade}`}>{m.grade}</span>
              {m.panels !== undefined && <span className="muted">{m.panels} pieces</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
