// Work → Workshop (ADR-124): every cover the Desk approved or marked produced, what the workshop
// cuts and sews from, and how it fitted. Read-only for every role (a workshop login of its own is
// open owner question 92). The cutting table's DXF is offered only when the approval gate lets it
// through (ADR-079/115/120); the server checks again on download. Approving, Produced and the
// measured sizes stay on the Desk card (After sewing).
import { useEffect, useMemo, useState } from "react";
import {
  fileUrl,
  revisionUrl,
  shopAdmin,
  workshop,
  type FitFeedback,
  type WorkshopItem,
} from "./api";
import { FilterRow, Tpl } from "./layout";
import { deskHref, modelHref } from "./nav";
import { useSession } from "./Session";

const FILE_LABEL: Record<string, string> = {
  "cutting-list.pdf": "Cutting list",
  "sizes.pdf": "Size drawing",
  "checklist.pdf": "Check list",
  "cut.svg": "Cut pieces (SVG)",
  "cut.dxf": "Cutting table (DXF)",
};
const day = (t?: number | null) =>
  t ? new Date(t * 1000).toLocaleDateString() : "";

/** The customers' fit answers per cover (the order's cover, joined on the server, so no answer
 * is lost however old its order). null: loading; "error": could not be read. */
function useCustomerFits(enabled: boolean) {
  const [fits, setFits] = useState<
    Record<string, FitFeedback[]> | "error" | null
  >(null);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    shopAdmin
      .feedback()
      .then((f) => {
        const by: Record<string, FitFeedback[]> = {};
        for (const a of f.feedback)
          if (a.model_id) (by[a.model_id] ??= []).push(a);
        if (live) setFits(by);
      })
      .catch(() => live && setFits("error"));
    return () => {
      live = false;
    };
  }, [enabled]);
  return fits;
}

export function Workshop() {
  const { user } = useSession();
  const editor = !!user && user.role !== "viewer";
  const [items, setItems] = useState<WorkshopItem[] | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [fit, setFit] = useState("");
  const customers = useCustomerFits(editor);
  useEffect(() => {
    workshop
      .list()
      .then((r) => setItems(r.items))
      .catch((e) => setErr(String(e).replace(/^Error: /, "")));
  }, []);
  const shown = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    return (items ?? []).filter((w) => {
      const text =
        `${w.code} ${w.id} ${w.products.join(" ")} ${w.fit?.note ?? ""}`.toLowerCase();
      return (
        words.every((x) => text.includes(x)) &&
        (!status || w.status === status) &&
        (!fit ||
          (fit === "none"
            ? !w.fit
            : fit === "fits"
              ? w.fit?.fits === true
              : w.fit?.fits === false))
      );
    });
  }, [items, q, status, fit]);
  const n = (s: string) => (items ?? []).filter((w) => w.status === s).length;
  return (
    <Tpl
      kind="list"
      title="Workshop"
      intro={
        <>
          Every cover the Desk approved or marked produced: what to cut and sew
          from, and how it fitted. Read-only: approving, <em>Produced</em> and
          the measured sizes stay on the Desk card (<em>After sewing</em>).
        </>
      }
    >
      {err && <p className="error">{err}</p>}
      <FilterRow
        count={
          items &&
          `${shown.length} of ${items.length} · ${n("approved")} approved, ${n("produced")} produced`
        }
      >
        <input
          className="search"
          type="search"
          placeholder="Search code, product or note…"
          aria-label="Search the workshop's covers"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          value={status}
          aria-label="Status"
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">approved and produced</option>
          <option value="approved">approved, not produced yet</option>
          <option value="produced">produced</option>
        </select>
        <select
          value={fit}
          aria-label="Fit"
          onChange={(e) => setFit(e.target.value)}
        >
          <option value="">any fit</option>
          <option value="fits">fits</option>
          <option value="bad">does not fit</option>
          <option value="none">not measured yet</option>
        </select>
      </FilterRow>
      {!items ? (
        !err && <p className="muted">Loading…</p>
      ) : !items.length ? (
        <p className="muted">
          Nothing approved yet: covers appear here once the Desk approves them.
        </p>
      ) : (
        <div className="table-wrap">
          <table className="list ws-table">
            <thead>
              <tr>
                <th>Cover</th>
                <th>Status</th>
                <th>Files</th>
                <th>Fit on the sewn cover</th>
                <th>Customers</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((w) => (
                <Row
                  key={w.id}
                  w={w}
                  customers={
                    !editor
                      ? null
                      : customers === "error"
                        ? "error"
                        : customers === null
                          ? "loading"
                          : (customers[w.id] ?? [])
                  }
                />
              ))}
              {shown.length === 0 && (
                <tr className="static">
                  <td colSpan={5} className="muted">
                    Nothing matches these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {!editor && (
        <p className="muted">
          The customers' fit answers are shown to editors and admins.
        </p>
      )}
    </Tpl>
  );
}

function Row({
  w,
  customers,
}: {
  w: WorkshopItem;
  customers: FitFeedback[] | "loading" | "error" | null;
}) {
  const who = w.produced ?? w.approved;
  return (
    <tr className="static" data-model={w.id}>
      <td>
        <div className="ws-cover">
          {w.has_picture ? (
            <img
              loading="lazy"
              src={fileUrl(w.id, "cover.png")}
              alt=""
              className="ws-pic"
            />
          ) : (
            <span className="ws-pic" />
          )}
          <div>
            <a href={modelHref(w.id)}>
              <strong>{w.code}</strong>
            </a>{" "}
            {w.arrangement && <span className="badge">arrangement</span>}
            <div className="muted small">
              {w.pieces} pieces · {w.vents} vents
              {w.products.length > 0 && ` · ${w.products.join(", ")}`}
            </div>
            <a className="small" href={deskHref(w.id)}>
              Desk card
            </a>
          </div>
        </div>
      </td>
      <td className="nowrap">
        <span
          className={`badge ${w.status === "produced" ? "status-production" : "status-checked"}`}
        >
          {w.status}
        </span>
        {who && (
          <div className="muted small">
            {who.by}, {day(who.time)}
          </div>
        )}
      </td>
      <td>
        <div className="ws-files">
          {w.files
            .filter((f) => f !== "cut.dxf")
            .map((f) => (
              <a
                key={f}
                href={fileUrl(w.id, f)}
                target="_blank"
                rel="noreferrer"
              >
                {FILE_LABEL[f] ?? f}
              </a>
            ))}
          {w.files.includes("cut.dxf") &&
            (w.dxf_ok ? (
              <a href={fileUrl(w.id, "cut.dxf")} download>
                {FILE_LABEL["cut.dxf"]}
              </a>
            ) : (
              <span className="dxf-locked" title="approval gate (ADR-079)">
                DXF waits for the Desk's (re)approval
              </span>
            ))}
          {w.revision &&
            (w.revision.dxf_ok ? (
              <a href={revisionUrl(w.id, w.revision.n, "cut.dxf")} download>
                Revision {w.revision.n} to cut (DXF)
              </a>
            ) : (
              <span className="dxf-locked">
                Revision {w.revision.n} to cut: not approved
              </span>
            ))}
        </div>
      </td>
      <td>
        {w.fit ? (
          <>
            <span className={`badge ${w.fit.fits ? "ok" : "grade-failed"}`}>
              {w.fit.fits ? "fits" : "does not fit"}
            </span>{" "}
            <span className="muted small">
              {w.fit.by}, {day(w.fit.time)}
            </span>
            {w.fit.note && <div className="small">{w.fit.note}</div>}
            {w.fit.measured > 0 && (
              <div className="muted small">
                {w.fit.measured} size{w.fit.measured === 1 ? "" : "s"} measured
                {w.fit.worst &&
                  `; largest difference ${w.fit.worst.diff_mm > 0 ? "+" : ""}${(w.fit.worst.diff_mm / 10).toFixed(1)} cm (${w.fit.worst.label})`}
              </div>
            )}
          </>
        ) : (
          <span className="muted small">not measured yet</span>
        )}
      </td>
      <td>
        {customers === null ? (
          <span className="muted small">—</span>
        ) : customers === "loading" ? (
          <span className="muted small">…</span>
        ) : customers === "error" ? (
          <span className="error small">could not be read</span>
        ) : customers.length === 0 ? (
          <span className="muted small">no answers</span>
        ) : (
          customers.map((c) => (
            <div key={c.id} className="small">
              <span aria-label={`${c.score} of 5`}>
                {"★".repeat(c.score)}
                <span className="muted">{"★".repeat(5 - c.score)}</span>
              </span>{" "}
              order {c.order_id}
              {c.comment && <> · {c.comment}</>}
              {c.photo && (
                <>
                  {" "}
                  ·{" "}
                  <a
                    href={`/api/admin/feedback/photo/${c.photo}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    photo
                  </a>
                </>
              )}
            </div>
          ))
        )}
      </td>
    </tr>
  );
}
