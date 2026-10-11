// The shop's few icons, drawn as lines in the text colour (ADR-105): no emoji, which every
// device draws differently.
const PATHS = {
  camera:
    "M4 8.5A1.5 1.5 0 0 1 5.5 7h2.1l1.4-2h6l1.4 2h2.1A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5zM12 16a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  drop: "M12 3.5s-6 6.6-6 10.9a6 6 0 0 0 12 0C18 10.1 12 3.5 12 3.5z",
  search: "M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13zM20 20l-4.8-4.8",
  // a delivery van: an existing cover's delivery promise (ADR-118)
  truck:
    "M3 6.5h11v9H3zM14 9.5h3.6l2.9 3.2v2.8H14zM7 18.5a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6zM17 18.5a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6z",
} as const;

export function Icon({ name }: { name: keyof typeof PATHS }) {
  return (
    <svg className="s-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}
