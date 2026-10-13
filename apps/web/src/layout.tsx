// The studio's four page templates (ADR-124, docs/plans/studio-ui.md §7): every page is one of
//   list    a head, one filter row, a table (or cards) with a sticky head, a selection bar
//   queue   a queue with its filters on the left, the detail beside it (Desk, Questions)
//   object  one thing: a head with its facts and main actions, a status strip, tabs (a cover)
//   form    settings: tabs, rows of name (its (i)) / control / where the value comes from, a Save bar
// A page explains itself in an (i) beside its title, never in a line under it (Studio 2.0, ADR-130).
// The styles are in studio.css under "the four page templates".
import type { ReactNode } from "react";
import { Info } from "./icons";

export type Template = "list" | "queue" | "object" | "form";

export function PageHead({
  title,
  children,
  actions,
}: {
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div className="head-row">
        <h1 className="page-title">{title}</h1>
        {children && <Info label={`About ${title}`}>{children}</Info>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

/** A page of one of the four templates, with its head when it has a title. */
export function Tpl({
  kind,
  title,
  intro,
  actions,
  children,
  className = "",
}: {
  kind: Template;
  title?: string;
  intro?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`tpl tpl-${kind} ${className}`.trim()}>
      {title && (
        <PageHead title={title} actions={actions}>
          {intro}
        </PageHead>
      )}
      {children}
    </div>
  );
}

/** A list's one filter row: search and choices on the left, a count on the right. */
export function FilterRow({
  children,
  count,
}: {
  children: ReactNode;
  count?: ReactNode;
}) {
  return (
    <div className="filter-row" role="group" aria-label="Filters">
      {children}
      {count != null && <span className="filter-count muted">{count}</span>}
    </div>
  );
}
