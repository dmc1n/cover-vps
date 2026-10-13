// The studio's icon sheet (ADR-130): every icon at 16, 20 and 24 px, light and dark, to look at.
//   cd apps/web && node e2e/iconsheet.mjs OUT.html   (then a screenshot of OUT.html)
import { renderToStaticMarkup } from "react-dom/server";
import { ICON_NAMES, Icon, isOwnIcon, type IconName } from "../src/icons";

const SIZES = [16, 20, 24];
const THEMES = [
  ["light", "#ffffff", "#1c1c1e", "#636366", "#f2f2f7"],
  ["dark", "#1c1c1e", "#f5f5f7", "#aeaeb2", "#000000"],
] as const;

function cell(n: IconName) {
  return (
    <div className="c" key={n}>
      <div className="g">
        {SIZES.map((s) => (
          <Icon key={s} name={n} size={s} />
        ))}
      </div>
      <div className="n">
        {n}
        {isOwnIcon(n) ? "" : " (Lucide)"}
      </div>
    </div>
  );
}

export function sheet(): string {
  const own = ICON_NAMES.filter(isOwnIcon);
  const util = ICON_NAMES.filter((n) => !isOwnIcon(n));
  const body = THEMES.map(([t, card, ink, muted, bg]) => (
    <section
      key={t}
      style={{ background: bg, color: ink, padding: 16 }}
      data-theme={t}
    >
      <h2 style={{ margin: "0 0 10px" }}>
        Cover Studio icons · {t} · 16 / 20 / 24 px
      </h2>
      <div className="grid" style={{ background: card }}>
        {own.map(cell)}
      </div>
      <h3 style={{ color: muted }}>Generic utility glyphs (Lucide)</h3>
      <div className="grid" style={{ background: card }}>
        {util.map(cell)}
      </div>
    </section>
  ));
  return (
    "<!doctype html><meta charset=utf-8><style>" +
    "body{margin:0;font:12px -apple-system,Inter,system-ui,sans-serif}" +
    ".grid{display:grid;grid-template-columns:repeat(8,1fr);gap:0;border-radius:14px;padding:6px}" +
    ".c{padding:8px 6px;text-align:center}.g{display:flex;gap:10px;justify-content:center;align-items:flex-end;height:28px}" +
    ".n{margin-top:6px;opacity:.75;font-size:11px}</style>" +
    renderToStaticMarkup(<>{body}</>)
  );
}
