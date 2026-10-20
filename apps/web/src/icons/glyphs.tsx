// Cover Studio's own icons (owner, 13 Oct 2026: "maak zelf unieke icons voor de backend"; ADR-130).
// Drawn for the studio on a 24-px grid in the manner of SF Symbols: one stroke (round caps and
// joins), no fills, currentColor, 2 px of air on every side. Built around covers, fabric and the
// workshop: the draped cover silhouette, pattern pieces, a stitched seam, the vent hood, the
// cutting table, needle and thread. Ours, no licence needed (docs/LICENSES.md).
//
// Each glyph is the inside of <svg viewBox="0 0 24 24">; Icon (index.tsx) draws it with the stroke
// of its optical size (16, 20 or 24 px). Every glyph was looked at on the sheet at 16, 20 and 24 px,
// light and dark (out/studio2-built/icon-sheet-*.png).
import type { ReactElement } from "react";

// the cover's silhouette, shared: a lounge chair under its cover seen from the side (low seat at
// the front, the back behind it), the hem flaring onto the ground
const DRAPE =
  "M4 19.5 4.6 12.3a2 2 0 0 1 2-1.8H10V6.6a2 2 0 0 1 2-2h5.2a2 2 0 0 1 2 1.9l.8 13";
const HEM = "M3 19.5h18";

export const GLYPHS = {
  // ---- the sections and the header ------------------------------------------------------
  work: (
    <>
      <rect x="3" y="7.5" width="18" height="12.5" rx="2.5" />
      <path d="M9 7.5V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5v2" />
      <path d="M3 13h7.5M13.5 13H21" />
      <rect x="10.5" y="11.5" width="3" height="3" rx="0.8" />
    </>
  ),
  covers: (
    <>
      <path d={DRAPE} />
      <path d={HEM} />
      <path d="m10 10.5.4 9" />
    </>
  ),
  shop: (
    <>
      <path d="M5.2 8h13.6l-1 11.2a1.5 1.5 0 0 1-1.5 1.3H7.7a1.5 1.5 0 0 1-1.5-1.3z" />
      <path d="M9 10.5V7a3 3 0 0 1 6 0v3.5" />
    </>
  ),
  settings: (
    <>
      <path d="M19.06 10.57 21.12 10.81 21.12 13.19 19.06 13.43 18 15.98 19.29 17.61 17.61 19.29 15.98 18 13.43 19.06 13.19 21.12 10.81 21.12 10.57 19.06 8.02 18 6.39 19.29 4.71 17.61 6 15.98 4.94 13.43 2.88 13.19 2.88 10.81 4.94 10.57 6 8.02 4.71 6.39 6.39 4.71 8.02 6 10.57 4.94 10.81 2.88 13.19 2.88 13.43 4.94 15.98 6 17.61 4.71 19.29 6.39 18 8.02Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m15.3 15.3 5.2 5.2" />
    </>
  ),
  guide: (
    <>
      <path d="M12 6.5C10.4 5.2 8 4.5 3.5 4.5v13c4.5 0 6.9.7 8.5 2 1.6-1.3 4-2 8.5-2v-13c-4.5 0-6.9.7-8.5 2Z" />
      <path d="M12 6.5v13" />
    </>
  ),
  // ---- Work -------------------------------------------------------------------------------
  desk: (
    <>
      <path d="M3 13.5 5.4 5.6A1.5 1.5 0 0 1 6.8 4.5h10.4a1.5 1.5 0 0 1 1.4 1.1L21 13.5V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
      <path d="M3 13.5h5l1 2h6l1-2h5" />
      <path d="m9.3 9.3 1.9 1.9 3.6-3.7" />
    </>
  ),
  questions: (
    <>
      <path d="M12 3.5a8.5 8.5 0 1 1-4.3 15.8l-4.2 1.2 1.2-4.2A8.5 8.5 0 0 1 12 3.5Z" />
      <path d="M9.8 9.6a2.3 2.3 0 1 1 3.2 2.1c-.6.3-1 .8-1 1.4v.4" />
      <path d="M12 16.4h.01" />
    </>
  ),
  workshop: (
    <>
      <circle cx="6" cy="7" r="2.5" />
      <circle cx="6" cy="17" r="2.5" />
      <path d="M8.2 8.2 16 15M8.2 15.8 16 9" />
      <path d="M17.5 12H21" />
      <path d="M3 21.5h18" />
    </>
  ),
  // ---- Covers -----------------------------------------------------------------------------
  "all-covers": (
    <>
      <path d="M3.5 9.5V7.2a1 1 0 0 1 1-1h1V5a1 1 0 0 1 1-1h1.5a1 1 0 0 1 1 1v4.5" />
      <path d="M3.5 20v-2.3a1 1 0 0 1 1-1h1v-1.2a1 1 0 0 1 1-1h1.5a1 1 0 0 1 1 1V20" />
      <path d="M11.5 7h9.5M11.5 17.5h9.5" />
    </>
  ),
  arrangements: (
    <>
      <path d="M6 4h3.5a1.5 1.5 0 0 1 1.5 1.5V13h7.5a1.5 1.5 0 0 1 1.5 1.5v4a1.5 1.5 0 0 1-1.5 1.5H6a1.5 1.5 0 0 1-1.5-1.5v-13A1.5 1.5 0 0 1 6 4Z" />
      <path d="M11 13v7" />
    </>
  ),
  "new-cover": (
    <>
      <path d="M3.5 20.5 4 15a1.8 1.8 0 0 1 1.8-1.6H8.5V10a1.8 1.8 0 0 1 1.8-1.8h3.4a1.8 1.8 0 0 1 1.8 1.7l.6 10.6" />
      <path d="M2.5 20.5h15" />
      <path d="M18.5 3v6M15.5 6h6" />
    </>
  ),
  learning: (
    <>
      <path d="M2.5 9 12 4.5 21.5 9 12 13.5Z" />
      <path d="M6.5 11v4.6c1.5 1.4 3.5 2.1 5.5 2.1s4-.7 5.5-2.1V11" />
      <path d="M21.5 9v5" />
    </>
  ),
  // a drawing (a sheet with its folded corner) and a 3D model (a block) joined by a seam:
  // Covers → Links, a drawing cover and a 3D-model cover of the same product (ADR-132)
  links: (
    <>
      <path d="M3 3.5h5.5L11 6v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" />
      <path d="M8.5 3.5V6H11M5.5 8.5h3" />
      <path d="M17 11 21 13.2v4.6L17 20l-4-2.2v-4.6Z" />
      <path d="m13 13.2 4 2.2 4-2.2M17 15.4V20" />
      <path d="M7 13v1.5a2 2 0 0 0 2 2h4" />
    </>
  ),
  "product-list": (
    <>
      <rect x="3.5" y="4" width="17" height="16" rx="2" />
      <path d="M3.5 9h17M3.5 14.5h17M9.5 9v11" />
    </>
  ),
  // ---- a cover's tabs ----------------------------------------------------------------------
  "3d": (
    <>
      <path d="M12 3 20 7.5v9L12 21l-8-4.5v-9Z" />
      <path d="M4 7.5 12 12l8-4.5M12 12v9" />
    </>
  ),
  pieces: (
    <>
      <path d="M3.5 6.5 10.2 4.5l1.3 13.3-8 2Z" />
      <path d="M14.5 5h6v14h-6c1-2.3 1.5-4.6 1.5-7s-.5-4.7-1.5-7Z" />
    </>
  ),
  seams: (
    <>
      <path d="M4.5 19.5 19.5 4.5" />
      <path d="m6.3 13.8 3.9 3.9M9.9 10.1l3.9 3.9M13.6 6.4l3.9 3.9" />
    </>
  ),
  adjust: (
    <>
      <path d="M4 7h8.5M17.5 7H20M4 17h2.5M11.5 17H20" />
      <circle cx="15" cy="7" r="2.5" />
      <circle cx="9" cy="17" r="2.5" />
    </>
  ),
  compare: (
    <>
      <rect x="3" y="4.5" width="18" height="15" rx="2.5" />
      <path d="M12 4.5v15" />
      <path d="m8.5 9.5-2 2.5 2 2.5M15.5 9.5l2 2.5-2 2.5" />
    </>
  ),
  history: (
    <>
      <path d="M4.2 13.5A8 8 0 1 0 6.3 6.4L4 8.7" />
      <path d="M4 4.5v4.2h4.2" />
      <path d="M12 8v4.3l2.8 1.7" />
    </>
  ),
  price: (
    <>
      <path d="M17.8 6.8A6.5 6.5 0 1 0 17.8 17.2" />
      <path d="M4.5 10.3h8.5M4.5 13.7h8.5" />
    </>
  ),
  // ---- a Desk card's tabs -------------------------------------------------------------------
  check: (
    <>
      <path d="m4 6.5 1.8 1.8L9 5M4 12.5l1.8 1.8L9 11M4 18.5l1.8 1.8L9 17" />
      <path d="M12.5 7h8M12.5 13h8M12.5 19h8" />
    </>
  ),
  "desk-pieces": (
    <>
      <path d="M12 3.5 21 8l-9 4.5L3 8Z" />
      <path d="m3 12 9 4.5 9-4.5M3 16l9 4.5 9-4.5" />
    </>
  ),
  correct: (
    <>
      <path d="M15.5 4.5 19.5 8.5 8.5 19.5H4.5v-4Z" />
      <path d="m13 7 4 4" />
    </>
  ),
  // ---- the 3D toolbar ------------------------------------------------------------------------
  vents: (
    <>
      <path d="M5.5 15.5c0-4.2 2.9-7.5 6.5-7.5s6.5 3.3 6.5 7.5" />
      <path d="M4 15.5h16M9 12.2h6" />
      <path d="M3 19.5h18" />
    </>
  ),
  dimensions: (
    <>
      <path d="M4 7.5v9M20 7.5v9M4.5 12h15" />
      <path d="M7 9.5 4.5 12 7 14.5M17 9.5l2.5 2.5-2.5 2.5" />
    </>
  ),
  measure: (
    <>
      <path d="M3.3 15.6 15.6 3.3a1 1 0 0 1 1.4 0l3.7 3.7a1 1 0 0 1 0 1.4L8.4 20.7a1 1 0 0 1-1.4 0l-3.7-3.7a1 1 0 0 1 0-1.4Z" />
      <path d="m7 12 2.2 2.2M10.3 8.7l1.6 1.6M13.6 5.4l2.2 2.2" />
    </>
  ),
  sizes: (
    <>
      <path d="M6.5 3h7.5l4.5 4.5V20a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <path d="M14 3v4.5h4.5" />
      <path d="M8.5 16h7M8.5 14.3v3.4M15.5 14.3v3.4" />
    </>
  ),
  design: (
    <>
      <rect x="3.5" y="3.5" width="6.5" height="17" rx="1.5" />
      <path d="m10 8.2 4.2-2.6a1.2 1.2 0 0 1 1.7.4l4.4 7.2a1.2 1.2 0 0 1-.4 1.7L10 20.5" />
      <path d="M6.75 16.5h.01" />
    </>
  ),
  rain: (
    <>
      <path d="M3.5 20 4.6 14.3a3 3 0 0 1 3-2.3h8.8a3 3 0 0 1 3 2.3l1.1 5.7" />
      <path d="m8 3.5-1 3M13 3.5l-1 3M18 3.5l-1 3" />
    </>
  ),
  drape: (
    <>
      <path d="M4 4h16" />
      <path d="M5.5 4v9.5c1.4 0 1.4 6 3.2 6s1.6-6 3.3-6 1.5 6 3.3 6 1.8-6 3.2-6V4" />
    </>
  ),
  unfold: (
    <>
      <path d="M9 3.5h6v5.5h5.5v6H15v5.5H9V15H3.5V9H9Z" />
      <path d="M9 9h6v6H9" />
    </>
  ),
  simulate: (
    <>
      <path d="M8 3.5c2 2.6 3 4.3 3 5.6a3 3 0 0 1-6 0c0-1.3 1-3 3-5.6Z" />
      <path d="M3 16c3-2.5 6-2.5 9 0s6 2.5 9 0M3 20.5c3-2.5 6-2.5 9 0s6 2.5 9 0" />
    </>
  ),
  checklist: (
    <>
      <path d="M8.5 4.5H6.5A1.5 1.5 0 0 0 5 6v13.5A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5h-2" />
      <rect x="8.5" y="3" width="7" height="3" rx="1" />
      <path d="m8.3 11.3 1.4 1.4 2.3-2.4M8.3 16.3l1.4 1.4 2.3-2.4M14 12h2M14 17h2" />
    </>
  ),
  // ---- actions ----------------------------------------------------------------------------------
  approve: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  reject: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  comment: (
    <>
      <path d="M5.5 4.5h13a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H10l-4.5 3.5V17a2 2 0 0 1-2-2V6.5a2 2 0 0 1 2-2Z" />
      <path d="M8 9h8M8 12.5h5" />
    </>
  ),
  sewing: (
    <>
      <path d="M4.5 19.5 17.2 6.8" />
      <path d="M17.2 6.8a1.8 1.8 0 1 0 2.5-2.5 1.8 1.8 0 0 0-2.5 2.5Z" />
      <path d="M19.4 6.6c-2.6 3.6-7.4 3.4-9.9 7.4" />
    </>
  ),
  produced: (
    <>
      <path d={DRAPE} />
      <path d={HEM} />
      <path d="m9.2 13.6 2 2 3.8-3.9" />
    </>
  ),
  "send-production": (
    <>
      <rect x="3" y="12" width="18" height="3.5" rx="1" />
      <path d="M5.5 15.5V20M18.5 15.5V20" />
      <path d="M12 2.5v6.5M9.3 6.4 12 9l2.7-2.6" />
    </>
  ),
  run: (
    <>
      <path d="M20 12a8 8 0 1 1-2.3-5.7" />
      <path d="M20 4v4.3h-4.3" />
      <path d="M10.5 9.3v5.4l4.3-2.7Z" />
    </>
  ),
  dxf: (
    <>
      <path d="M6.5 3h7.5l4.5 4.5V20a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <path d="M14 3v4.5h4.5" />
      <path d="M12 10.5v7M9 14.5l3 3 3-3" />
    </>
  ),
  "cutting-list": (
    <>
      <path d="M6.5 3h7.5l4.5 4.5V20a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <path d="M14 3v4.5h4.5" />
      <path d="M8.5 11.5h7M8.5 14.5h7M8.5 17.5h4" />
    </>
  ),
  // the Cutting file view (ADR-147): the cutting table's sheet with a piece and its pen line
  "cutting-file": (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M6.5 16.5V8.5l5-1.5 5.5 2.5v7Z" />
      <path d="M9 13.5h5.5" strokeDasharray="1.6 1.8" />
    </>
  ),
  "cut-svg": (
    <>
      <path d="M6.5 3h7.5l4.5 4.5V20a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <path d="M14 3v4.5h4.5" />
      <path d="M8.5 17.5 9.5 11h3l1 6.5Z" />
    </>
  ),
  // ---- statuses (each its own shape, so they read without their colour) --------------------------
  "st-ok": (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m8.3 12.3 2.6 2.6 4.9-5" />
    </>
  ),
  "st-wait": (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  "st-bad": (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m9 9 6 6M15 9l-6 6" />
    </>
  ),
  "st-warn": (
    <>
      <path d="M10.3 4.3a2 2 0 0 1 3.4 0l7 12.2a2 2 0 0 1-1.7 3H5a2 2 0 0 1-1.7-3Z" />
      <path d="M12 9.5v4M12 16.5h.01" />
    </>
  ),
  "st-check": (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.8v4.6M12 16h.01" />
    </>
  ),
  "st-made": (
    <>
      <path d={DRAPE} />
      <path d={HEM} />
      <path d="m9.2 13.6 2 2 3.8-3.9" />
    </>
  ),
  "st-interrupted": (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M10 9v6M14 9v6" />
    </>
  ),
  "st-ai": (
    <>
      <path d="M11 3.5c.6 4.1 2.1 5.6 6.2 6.2-4.1.6-5.6 2.1-6.2 6.2-.6-4.1-2.1-5.6-6.2-6.2C8.9 9.1 10.4 7.6 11 3.5Z" />
      <path d="M18 15v5M15.5 17.5h5" />
    </>
  ),
  "st-draft": (
    <>
      <path d="M15.5 4.5 19.5 8.5 8.5 19.5H4.5v-4Z" />
    </>
  ),
  "st-running": <path d="M20.5 12A8.5 8.5 0 1 1 12 3.5" />,
  // ---- the Settings tiles ----------------------------------------------------------------------
  company: (
    <>
      <path d="M4.5 10.5V20h15v-9.5" />
      <path d="M3 9.5 4.6 4h14.8L21 9.5a2.25 2.25 0 0 1-4.5 0 2.25 2.25 0 0 1-4.5 0 2.25 2.25 0 0 1-4.5 0A2.25 2.25 0 0 1 3 9.5Z" />
      <path d="M10 20v-5h4v5" />
    </>
  ),
  selling: (
    <>
      <path d="M3.5 12V4.5a1 1 0 0 1 1-1H12l8.6 8.6a1.5 1.5 0 0 1 0 2.1l-6.4 6.4a1.5 1.5 0 0 1-2.1 0Z" />
      <circle cx="8" cy="8" r="1.4" />
    </>
  ),
  costs: (
    <>
      <ellipse cx="9" cy="6.5" rx="5.5" ry="2.5" />
      <path d="M3.5 6.5v8c0 1.4 2.5 2.5 5.5 2.5M3.5 10.5c0 1.4 2.5 2.5 5.5 2.5" />
      <circle cx="16" cy="15.5" r="4.5" />
    </>
  ),
  pricing: (
    <>
      <rect x="3.5" y="3.5" width="17" height="17" rx="4" />
      <path d="m8.5 15.5 7-7" />
      <circle cx="9" cy="9" r="1.3" />
      <circle cx="15" cy="15" r="1.3" />
    </>
  ),
  publish: (
    <>
      <path d="M7.5 18.5H7a4.5 4.5 0 0 1-.6-9A6 6 0 0 1 17.7 8.6a5 5 0 0 1-.2 9.9H16.5" />
      <path d="M12 20.5v-8M9 15.3l3-3 3 3" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.3" />
      <path d="M3 19.5a6 6 0 0 1 12 0" />
      <path d="M15.5 4.8a3.3 3.3 0 0 1 0 6.4M17.5 13.6a6 6 0 0 1 3.5 5.9" />
    </>
  ),
  defaults: (
    <>
      <path d="M6 4v3M6 11v9M12 4v9M12 17v3M18 4v2M18 10v10" />
      <circle cx="6" cy="9" r="2" />
      <circle cx="12" cy="15" r="2" />
      <circle cx="18" cy="8" r="2" />
    </>
  ),
  mail: (
    <>
      <rect x="3" y="5.5" width="18" height="13" rx="2" />
      <path d="m3.8 6.8 8.2 6.4 8.2-6.4" />
    </>
  ),
  keys: (
    <>
      <circle cx="8" cy="15.5" r="4.5" />
      <path d="m11.2 12.3 8.3-8.3M16 7.5l2.5 2.5M18.5 5l2 2" />
    </>
  ),
  ai: (
    <>
      <path d="M11 3.5c.6 4.1 2.1 5.6 6.2 6.2-4.1.6-5.6 2.1-6.2 6.2-.6-4.1-2.1-5.6-6.2-6.2C8.9 9.1 10.4 7.6 11 3.5Z" />
      <path d="M18 15v5M15.5 17.5h5" />
    </>
  ),
  system: (
    <>
      <rect x="3.5" y="4" width="17" height="7" rx="2" />
      <rect x="3.5" y="13" width="17" height="7" rx="2" />
      <path d="M7.5 7.5h.01M7.5 16.5h.01M11 7.5h5.5M11 16.5h5.5" />
    </>
  ),
  website: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17M12 3.5c-2.3 2.4-3.5 5.2-3.5 8.5s1.2 6.1 3.5 8.5c2.3-2.4 3.5-5.2 3.5-8.5S14.3 5.9 12 3.5Z" />
    </>
  ),
  // ---- the shop ---------------------------------------------------------------------------------
  orders: (
    <>
      <path d="M5.5 3h13v18l-2.2-1.5-2.1 1.5-2.2-1.5L9.8 21l-2.1-1.5L5.5 21Z" />
      <path d="M9 8h6M9 11.5h6M9 15h3.5" />
    </>
  ),
  requests: (
    <>
      <path d="M5.5 4.5h13a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2H10l-4.5 3.5V17a2 2 0 0 1-2-2V6.5a2 2 0 0 1 2-2Z" />
      <path d="M8 13.5V11a1 1 0 0 1 1-1h2V8.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v5" />
    </>
  ),
  b2b: (
    <>
      <path d="M4.5 20.5V5a1 1 0 0 1 1-1h7.5a1 1 0 0 1 1 1v15.5" />
      <path d="M14 9.5h4.5a1 1 0 0 1 1 1v10" />
      <path d="M2.5 20.5h19M7.5 8h3M7.5 11.5h3M7.5 15h3M16.5 13h.01M16.5 16.5h.01" />
    </>
  ),
  // the dealer embed (ADR-150): our configurator inside another website's page
  embed: (
    <>
      <path d="M4.5 4h15a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-15a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
      <path d="M2.5 8h19" />
      <path d="m9.5 11.5-2.5 2.5 2.5 2.5M14.5 11.5l2.5 2.5-2.5 2.5" />
    </>
  ),
} satisfies Record<string, ReactElement>;

export type GlyphName = keyof typeof GLYPHS;
