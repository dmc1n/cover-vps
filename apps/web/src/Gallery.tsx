import { useEffect, useMemo, useState } from "react";
import { api, fileUrl, ModelBrief } from "./api";

// The catalogue: every product with its photo and a picture of its cover, the key numbers and
// how far the cover is. A click opens the model.

type Sort = "name" | "grade" | "stretch" | "size";
const GRADE_ORDER = { ready: 0, check: 1, failed: 2 };

const title = (id: string) =>
  id
    .replace(/^suns-/, "")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

export function Gallery() {
  const [models, setModels] = useState<ModelBrief[] | null>(null);
  const [q, setQ] = useState("");
  const [grade, setGrade] = useState("");
  const [family, setFamily] = useState("");
  const [tag, setTag] = useState("");
  const [sort, setSort] = useState<Sort>("name");
  useEffect(() => {
    api.models().then(setModels);
  }, []);
  const tags = useMemo(() => [...new Set((models ?? []).flatMap((m) => m.tags))].sort(), [models]);
  const cats = useMemo(
    () => [...new Set((models ?? []).map((m) => m.category).filter(Boolean))].sort() as string[],
    [models],
  );
  const shown = useMemo(() => {
    const f = q.toLowerCase();
    const list = (models ?? []).filter(
      (m) =>
        (!f || m.id.includes(f.replace(/\s+/g, "-")) || m.notes.toLowerCase().includes(f)) &&
        (!grade || m.grade === grade) &&
        (!family ||
          (family === "-" ? !m.category : m.category === family || (m.category ?? "").startsWith(`${family} ›`))) &&
        (!tag || m.tags.includes(tag)),
    );
    const vol = (m: ModelBrief) => (m.size_mm ? m.size_mm[0] * m.size_mm[1] * m.size_mm[2] : 0);
    list.sort((a, b) =>
      sort === "grade"
        ? GRADE_ORDER[a.grade] - GRADE_ORDER[b.grade] || a.id.localeCompare(b.id)
        : sort === "stretch"
          ? (a.max_stretch_pct ?? 999) - (b.max_stretch_pct ?? 999)
          : sort === "size"
            ? vol(b) - vol(a)
            : a.id.localeCompare(b.id),
    );
    return list;
  }, [models, q, grade, family, tag, sort]);
  if (!models) return <p className="muted">Loading the catalogue…</p>;
  const count = (g: string) => models.filter((m) => m.grade === g).length;
  return (
    <>
      <h2>
        Catalogue{" "}
        <span className="muted">
          {models.length} products · {count("ready")} ready · {count("check")} to check · {count("failed")} failed
        </span>
      </h2>
      <div className="row">
        <input className="search" placeholder="Search products…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={grade} onChange={(e) => setGrade(e.target.value)}>
          <option value="">every cover</option>
          <option value="ready">ready</option>
          <option value="check">to check</option>
          <option value="failed">failed</option>
        </select>
        <select value={family} onChange={(e) => setFamily(e.target.value)}>
          <option value="">all categories</option>
          {[...new Set(cats.map((c) => c.split(" › ")[0]))].map((g) => (
            <optgroup key={g} label={g}>
              <option value={g}>all {g}</option>
              {cats
                .filter((c) => c.startsWith(`${g} ›`))
                .map((c) => (
                  <option key={c} value={c}>
                    {c.split(" › ")[1]}
                  </option>
                ))}
            </optgroup>
          ))}
          <option value="-">no category</option>
        </select>
        <select value={tag} onChange={(e) => setTag(e.target.value)}>
          <option value="">all tags</option>
          {tags.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="name">sort by name</option>
          <option value="grade">sort by cover (ready first)</option>
          <option value="stretch">sort by stretch</option>
          <option value="size">sort by size</option>
        </select>
        <span className="muted">{shown.length} shown</span>
      </div>
      <div className="gallery">
        {shown.map((m) => (
          <a key={m.id} className="product" href={`#/model/${m.id}`} title={m.reasons.join("\n")}>
            <div className="pics">
              {m.files.includes("product.jpg") ? (
                <img loading="lazy" src={fileUrl(m.id, "product.jpg")} alt="product" />
              ) : (
                <div className="nopic">no photo</div>
              )}
              {m.files.includes("cover.png") ? (
                <img loading="lazy" src={fileUrl(m.id, "cover.png")} alt="cover" />
              ) : (
                <div className="nopic">no cover yet</div>
              )}
            </div>
            <div className="name">{title(m.id)}</div>
            <div className="facts">
              <span className={`badge grade-${m.grade}`}>{m.grade === "check" ? "to check" : m.grade}</span>
              {m.category && <span className="badge">{m.category.split(" › ")[1]}</span>}
              {m.size_mm && <span>{m.size_mm.map((v) => Math.round(v / 10)).join("×")} cm</span>}
              {m.panels != null && <span>{m.panels} panels</span>}
              {m.max_stretch_pct != null && (
                <span className={m.max_stretch_pct > 2 ? "bad" : "ok"}>{m.max_stretch_pct.toFixed(1)} %</span>
              )}
              {m.roll_length_mm ? <span>{(m.roll_length_mm / 1000).toFixed(1)} m fabric</span> : null}
            </div>
          </a>
        ))}
      </div>
    </>
  );
}
