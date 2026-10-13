// Studio 2.0 (ADR-130): the studio's icons, the (i) popover that holds an explanation instead of
// a line of text, and the status chip.
//
// The icons are our own (glyphs.tsx: every section, page, tab, toolbar action, status and
// Settings tile, drawn for Cover Studio, owner 13 Oct 2026). Lucide (ISC; Feather-derived icons
// MIT, docs/LICENSES.md) only for generic utility glyphs: chevrons, close, the (i), copy, an
// external link, more, undo, delete. One table by a short name, so a menu item, a tab and a toolbar
// action use the same glyph everywhere (nav.ts names the icons of the map).
//
// Rules for every page (docs/plans/studio-v2.md §3):
//   1. A page or section explains itself in an (i) beside its title, never in a line under it.
//   2. A field's help is its (i); a setting's key is the label's tooltip, not a second line.
//   3. A label that would repeat on every row is the column head; a state is a chip with an icon.
//   4. A toolbar action is an icon with a tooltip and an aria-label (the full words); a page's
//      one main action may keep a short label (two words at most) beside its icon.
//   5. Visible stays: empty states, errors, live status, numbers.
import {
  type AnchorHTMLAttributes,
  type ButtonHTMLAttributes,
  type PointerEvent as RPointerEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  ArrowLeft,
  Ban,
  ChartColumn,
  ChevronDown,
  CirclePlus,
  CircleUser,
  Copy,
  Download,
  Ellipsis,
  ExternalLink,
  Eye,
  FileText,
  FileUp,
  Info as InfoGlyph,
  LayoutGrid,
  Link,
  Lock,
  LogOut,
  Moon,
  PencilLine,
  Plus,
  Printer,
  RefreshCw,
  RotateCcw,
  Sun,
  SunMoon,
  Table2,
  Trash2,
  Truck,
  Undo2,
  Upload,
  X,
  Camera,
  Send,
  FileSpreadsheet,
  type LucideIcon,
} from "lucide-react";
import { GLYPHS, type GlyphName } from "./glyphs";

/** Generic utility glyphs from Lucide (not the studio's own subjects). */
const UTILITY = {
  "theme-auto": SunMoon,
  "theme-light": Sun,
  "theme-dark": Moon,
  me: CircleUser,
  logout: LogOut,
  edit: PencilLine,
  open: ExternalLink,
  undo: Undo2,
  more: Ellipsis,
  table: Table2,
  cards: LayoutGrid,
  new: CirclePlus,
  add: Plus,
  csv: FileSpreadsheet,
  pdf: FileText,
  stats: ChartColumn,
  info: InfoGlyph,
  download: Download,
  upload: Upload,
  "file-up": FileUp,
  delete: Trash2,
  refresh: RefreshCw,
  "roll-back": RotateCcw,
  send: Send,
  delivery: Truck,
  copy: Copy,
  link: Link,
  close: X,
  back: ArrowLeft,
  print: Printer,
  view: Eye,
  camera: Camera,
  lock: Lock,
  block: Ban,
  menu: ChevronDown,
} satisfies Record<string, LucideIcon>;

/** Other names for our own glyphs, where the same drawing means the same thing. */
const ALIAS = {
  save: "approve",
  production: "send-production",
} satisfies Record<string, GlyphName>;

export type IconName = GlyphName | keyof typeof UTILITY | keyof typeof ALIAS;

/** Every name, for the icon sheet (e2e/iconsheet.py) and a check that none is missing. */
export const ICON_NAMES = [
  ...Object.keys(GLYPHS),
  ...Object.keys(UTILITY),
  ...Object.keys(ALIAS),
] as IconName[];
export const isOwnIcon = (n: IconName): boolean => n in GLYPHS || n in ALIAS;

/** The stroke in the 24-unit grid for an icon drawn at `size` px: about 1.5 px at 16, 1.65 px at
 * 20 and 1.75 px at 24 (optical sizes: a small icon is drawn a little heavier, as SF Symbols). */
export const strokeFor = (size: number): number => {
  const px = size <= 16 ? 1.5 : size <= 20 ? 1.65 : 1.75;
  return +((px * 24) / size).toFixed(2);
};

/** One icon, decorative: the words beside it (or the control's aria-label) say what it is. */
export function Icon({
  name,
  size = 17,
  className = "",
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  const own = (ALIAS as Record<string, GlyphName>)[name] ?? name;
  const cls = `ico ${className}`.trim();
  if (own in GLYPHS)
    return (
      <svg
        className={cls}
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeFor(size)}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
        data-icon={name}
      >
        {GLYPHS[own as GlyphName]}
      </svg>
    );
  const I = (UTILITY as Record<string, LucideIcon>)[name];
  return (
    <I
      className={cls}
      size={size}
      strokeWidth={strokeFor(size)}
      aria-hidden="true"
      focusable="false"
      data-icon={name}
    />
  );
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: IconName;
  /** the action in words: the tooltip and the accessible name */
  label: string;
  size?: number;
};
/** A toolbar action as an icon: its words are the tooltip and the name a screen reader says. */
export function IconButton({
  icon,
  label,
  size = 17,
  className = "",
  ...rest
}: BtnProps) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      className={`icon-btn ${className}`.trim()}
      {...rest}
    >
      <Icon name={icon} size={size} />
    </button>
  );
}

type LinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  icon: IconName;
  label: string;
  size?: number;
};
/** A link shown as an icon (a file, a Desk card, the cover's page): words in its tooltip. */
export function IconLink({
  icon,
  label,
  size = 17,
  className = "",
  ...rest
}: LinkProps) {
  return (
    <a
      title={label}
      aria-label={label}
      className={`icon-btn ${className}`.trim()}
      {...rest}
    >
      <Icon name={icon} size={size} />
    </a>
  );
}

// ---- the (i) popover -----------------------------------------------------------------------
// A button (keyboard: Tab, then Enter or Space; a finger: a tap) that shows the explanation in a
// small card; Escape, a tap outside or the button again closes it. A mouse also opens it by
// hovering. While open, the text sits right after the button, so Tab reaches a link inside it.
// Where the browser has the popover API (Chrome/Edge 114, Safari 17,
// Firefox 125) the card is in the top layer, so no scrolling box or table clips it. The text is
// in the page only while the card is open (a closed (i) adds nothing to the page's text).
const hasPopover =
  typeof HTMLElement !== "undefined" &&
  typeof (HTMLElement.prototype as { showPopover?: unknown }).showPopover ===
    "function";

export function Info({
  children,
  label = "About this page",
  className = "",
  size = 16,
}: {
  children: ReactNode;
  /** what the button says to a screen reader: "About <the thing>" */
  label?: string;
  className?: string;
  size?: number;
}) {
  const id = useId();
  const [open, setOpen] = useState<false | "hover" | "pinned">(false);
  const wrap = useRef<HTMLSpanElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLSpanElement>(null);
  const timer = useRef<number | undefined>(undefined);

  const place = useCallback(() => {
    const b = btn.current?.getBoundingClientRect();
    const p = pop.current;
    if (!b || !p) return;
    const vw = document.documentElement.clientWidth;
    const vh = window.innerHeight;
    const w = Math.min(380, vw - 24);
    p.style.maxWidth = `${w}px`;
    const pw = Math.min(p.offsetWidth || w, w);
    const ph = p.offsetHeight;
    const left = Math.max(12, Math.min(b.left - 12, vw - pw - 12));
    const below = b.bottom + 6;
    const top =
      below + ph > vh - 8 && b.top - ph - 6 > 8 ? b.top - ph - 6 : below;
    p.style.left = `${left}px`;
    p.style.top = `${top}px`;
  }, []);

  useLayoutEffect(() => {
    const p = pop.current;
    if (!p) return;
    // the card is in the page only while open; in the top layer where the browser has it
    if (hasPopover && !p.hasAttribute("popover")) {
      p.setAttribute("popover", "manual");
      (p as HTMLElement & { showPopover(): void }).showPopover();
    }
    place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const outside = (e: Event) => {
      const t = e.target as Node;
      if (!wrap.current?.contains(t)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      btn.current?.focus();
    };
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", key);
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", key);
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, place]);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const hoverIn = (e: RPointerEvent) => {
    if (e.pointerType !== "mouse") return;
    window.clearTimeout(timer.current);
    if (!open) setOpen("hover");
  };
  const hoverOut = (e: RPointerEvent) => {
    if (e.pointerType !== "mouse") return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(
      () => setOpen((o) => (o === "hover" ? false : o)),
      150,
    );
  };
  return (
    <span
      ref={wrap}
      className={`infotip ${className}`.trim()}
      onPointerEnter={hoverIn}
      onPointerLeave={hoverOut}
      onBlur={(e) => {
        if (!wrap.current?.contains(e.relatedTarget as Node | null))
          setOpen(false);
      }}
    >
      <button
        ref={btn}
        type="button"
        className="info-btn"
        aria-label={label}
        aria-expanded={!!open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((o) => (o === "pinned" ? false : "pinned"))}
      >
        <InfoGlyph size={size} strokeWidth={1.9} aria-hidden="true" />
      </button>
      {open && (
        <span
          ref={pop}
          id={id}
          className="info-pop"
          role="note"
          aria-label={label}
          onPointerEnter={hoverIn}
          onPointerLeave={hoverOut}
        >
          {children}
        </span>
      )}
    </span>
  );
}

// ---- status chips ---------------------------------------------------------------------------
type Tone = "ok" | "wait" | "bad" | "warn" | "made" | "draft" | "plain";
const TONE: Record<string, [Tone, IconName]> = {
  // approved, ready, done
  approved: ["ok", "st-ok"],
  checked: ["ok", "st-ok"],
  ready: ["ok", "st-ok"],
  done: ["ok", "st-ok"],
  fits: ["ok", "st-ok"],
  paid: ["ok", "st-ok"],
  sent: ["ok", "st-ok"],
  delivered: ["ok", "st-ok"],
  active: ["ok", "st-ok"],
  published: ["ok", "st-ok"],
  production: ["ok", "st-ok"],
  // waiting for someone or something
  waiting: ["wait", "st-wait"],
  new: ["wait", "st-wait"],
  queued: ["wait", "st-wait"],
  pending: ["wait", "st-wait"],
  open: ["wait", "st-wait"],
  "ai-checked": ["wait", "st-ai"],
  running: ["wait", "st-running"],
  "in-production": ["made", "st-made"],
  // rejected, failed
  rejected: ["bad", "st-bad"],
  failed: ["bad", "st-bad"],
  interrupted: ["bad", "st-interrupted"],
  cancelled: ["bad", "st-bad"],
  blocked: ["bad", "st-bad"],
  "does-not-fit": ["bad", "st-bad"],
  // to look at
  check: ["warn", "st-check"],
  warning: ["warn", "st-warn"],
  stale: ["warn", "st-warn"],
  "needs-a-person": ["warn", "st-check"],
  // produced
  produced: ["made", "st-made"],
  shipped: ["made", "st-made"],
  // a draft
  draft: ["draft", "st-draft"],
};
/** The tone (colour) and icon of a state, by its name as the API spells it. */
export function statusTone(status: string): [Tone, IconName | null] {
  const key = status
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, "-");
  return TONE[key] ?? ["plain", null];
}

/** A state as a chip: an icon and the word, in the state's colour (approved green, waiting blue,
 * rejected red, a warning orange, produced purple). */
export function StatusChip({
  status,
  children,
  title,
  className = "",
}: {
  status: string;
  children?: ReactNode;
  title?: string;
  className?: string;
}) {
  const [tone, icon] = statusTone(status);
  return (
    <span className={`chip-s t-${tone} ${className}`.trim()} title={title}>
      {icon && <Icon name={icon} size={13} />}
      {children ?? status}
    </span>
  );
}

/** A heading with its icon and its (i) beside it (not inside: the heading's name stays its own
 * words). `info` is the explanation that used to be the line under the heading. */
export function Heading({
  level = 3,
  icon,
  info,
  infoLabel,
  className = "",
  id,
  children,
}: {
  level?: 1 | 2 | 3 | 4;
  icon?: IconName;
  info?: ReactNode;
  infoLabel?: string;
  className?: string;
  id?: string;
  children: ReactNode;
}) {
  const H = `h${level}` as "h1" | "h2" | "h3" | "h4";
  const words = typeof children === "string" ? children : "this";
  return (
    <div className={`head-row ${className}`.trim()}>
      <H id={id} className={level === 1 ? "page-title" : undefined}>
        {icon && <Icon name={icon} size={level === 1 ? 22 : 17} />}
        {children}
      </H>
      {info && <Info label={infoLabel ?? `About ${words}`}>{info}</Info>}
    </div>
  );
}
