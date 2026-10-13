// Work → Workshop (ADR-124, ADR-128): the shop's orders that wait for production (Send to
// production, editors and admins) or are in it, and every cover the Desk approved or marked
// produced: what the workshop cuts and sews from, and how it fitted. The workshop login (role
// "workshop", owner question 92) starts here. The cutting table's DXF is offered only when the
// Desk approved the cover (every cover since ADR-128); the server checks again on download.
// Approving and Produced stay on the Desk card; the fit and what was measured too (After sewing).
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fileUrl,
  revisionUrl,
  shopAdmin,
  workshop,
  type FitFeedback,
  type WorkshopItem,
  type WorkshopOrder,
} from "./api";
import { FilterRow, Tpl } from "./layout";
import { deskHref, isEditor, isWorkshop, modelHref } from "./nav";
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
  const editor = isEditor(user);
  const [items, setItems] = useState<WorkshopItem[] | null>(null);
  const [orders, setOrders] = useState<WorkshopOrder[]>([]);
  const [canProduce, setCanProduce] = useState(false);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [fit, setFit] = useState("");
  const customers = useCustomerFits(editor);
  const load = useCallback(
    () =>
      workshop
        .list()
        .then((r) => {
          setItems(r.items);
          setOrders(r.orders ?? []);
          setCanProduce(!!r.can_produce);
        })
        .catch((e) => setErr(String(e).replace(/^Error: /, ""))),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);
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
          The orders to make, and every cover the Desk approved or marked
          produced: what to cut and sew from, and how it fitted. A paid order
          waits until someone in the studio sends it to production; its cover
          then goes to the Desk for a quick approval, and the DXF follows it.
          The fit and the measured sizes go on the Desk card (
          <em>After sewing</em>).
        </>
      }
    >
      {err && <p className="error">{err}</p>}
      {items && (
        <Orders orders={orders} canProduce={canProduce} onChanged={load} />
      )}
      <h2 className="ws-h">Approved covers</h2>
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

const ORDER_STATUS: Record<string, string> = {
  waiting_production: "waiting for production",
  in_production: "in production",
  paid: "waiting for production",
  on_account: "waiting for production",
};

/** The shop's orders that wait for production or are in it (ADR-128): what to make, no prices.
 * "Send to production" is the studio's click: only then the cover is made, goes to the Desk as
 * an order (first in its queue, one click approves) and the production mail goes out. */
function Orders({
  orders,
  canProduce,
  onChanged,
}: {
  orders: WorkshopOrder[];
  canProduce: boolean;
  onChanged: () => void;
}) {
  const { user } = useSession();
  const [busy, setBusy] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const send = async (o: WorkshopOrder) => {
    setBusy(o.id);
    setMsg("");
    try {
      const r = await shopAdmin.produce(o.id);
      setMsg(`Order ${o.id} sent to production: ${r.model_id} is on the Desk.`);
      onChanged();
    } catch (e) {
      setMsg(String(e).replace(/^Error: /, ""));
    } finally {
      setBusy(null);
    }
  };
  const waiting = orders.filter((o) => o.status === "waiting_production");
  return (
    <section className="ws-orders" data-testid="ws-orders">
      <h2 className="ws-h">
        Orders{" "}
        <span className="muted small">
          {waiting.length} waiting for production ·{" "}
          {orders.length - waiting.length} in production
        </span>
      </h2>
      {msg && (
        <p className="muted" role="status">
          {msg}
        </p>
      )}
      {!orders.length ? (
        <p className="muted">No order waits for production.</p>
      ) : (
        <div className="table-wrap">
          <table className="list ws-table">
            <thead>
              <tr>
                <th>Order</th>
                <th>What</th>
                <th>Status</th>
                <th>Cover and DXF</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="static" data-order={o.id}>
                  <td className="nowrap">
                    <strong>#{o.id}</strong>
                    <div className="muted small">
                      {day(o.created)}
                      {o.company ? ` · ${o.company}` : ""}
                      {o.customer ? ` · ${o.customer}` : ""}
                      {o.city ? `, ${o.city}` : ""}
                    </div>
                  </td>
                  <td>
                    {o.qty > 1 && `${o.qty} × `}
                    {o.stock ?? o.product ?? "cover"}
                    {o.colour && ` · ${o.colour}`}
                    {o.sizes_cm && !o.stock && (
                      <div className="muted small">
                        {Object.entries(o.sizes_cm)
                          .filter(([, v]) => typeof v === "number")
                          .map(([k, v]) => `${k} ${v}`)
                          .join(" · ")}{" "}
                        cm
                      </div>
                    )}
                  </td>
                  <td className="nowrap">
                    <span
                      className={`badge ${o.status === "waiting_production" ? "warn" : "status-checked"}`}
                    >
                      {ORDER_STATUS[o.status] ?? o.status}
                    </span>
                    {o.released_by && (
                      <div className="muted small">
                        sent by {o.released_by}, {day(o.released)}
                      </div>
                    )}
                  </td>
                  <td>
                    {o.status === "waiting_production" ? (
                      canProduce && !isWorkshop(user) ? (
                        <button
                          className="primary"
                          disabled={busy !== null}
                          onClick={() => send(o)}
                        >
                          {busy === o.id ? "Sending…" : "Send to production"}
                        </button>
                      ) : (
                        <span className="muted small">
                          waits for the studio's Send to production
                        </span>
                      )
                    ) : o.model_id ? (
                      <>
                        <a href={deskHref(o.model_id)}>{o.model_id}</a>{" "}
                        <span className="muted small">
                          Desk: {o.desk_status ?? "?"}
                        </span>
                        <div>
                          {o.dxf_ok ? (
                            <a href={fileUrl(o.model_id, "cut.dxf")} download>
                              Cutting table (DXF)
                            </a>
                          ) : (
                            <span className="dxf-locked">
                              DXF waits for the Desk's approval
                            </span>
                          )}
                        </div>
                      </>
                    ) : (
                      <span className="muted small">being made…</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
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
  const { user } = useSession();
  const cover = !isWorkshop(user); // the cover's page is not the workshop login's (ADR-128)
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
            {cover ? (
              <a href={modelHref(w.id)}>
                <strong>{w.code}</strong>
              </a>
            ) : (
              <strong>{w.code}</strong>
            )}{" "}
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
          {(w.stamped ?? []).map((f) => (
            <a
              key={`approved-${f}`}
              href={`/api/models/${w.id}/approved/${f}`}
              target="_blank"
              rel="noreferrer"
              title="Stamped APPROVED by the Desk's approval (ADR-128)"
            >
              {f === "sizes.pdf"
                ? "Approved size drawing"
                : "Approved cutting list"}
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
