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
import {
  Heading,
  Icon,
  IconLink,
  Info,
  StatusChip,
  type IconName,
} from "./icons";
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
// the files as icons with a short word beside each (a tablet has no tooltips) and the full words
// as their name (Studio 2.0, ADR-130); an approved copy also carries a tick, not only a colour
const FILE_SHORT: Record<string, string> = {
  "cutting-list.pdf": "List",
  "sizes.pdf": "Sizes",
  "checklist.pdf": "Check",
  "cut.svg": "SVG",
};
function FileLink({
  icon,
  label,
  short,
  href,
  approved = false,
}: {
  icon: IconName;
  label: string;
  short: string;
  href: string;
  approved?: boolean;
}) {
  return (
    <a
      className={`icon-btn tinted ws-file ${approved ? "approved" : ""}`}
      href={href}
      target="_blank"
      rel="noreferrer"
      title={label}
      aria-label={label}
    >
      <Icon name={icon} />
      {approved && <Icon name="st-ok" size={13} className="ws-file-ok" />}
      <span className="ws-file-label" aria-hidden="true">
        {short}
      </span>
    </a>
  );
}
const FILE_ICON: Record<string, IconName> = {
  "cutting-list.pdf": "cutting-list",
  "sizes.pdf": "sizes",
  "checklist.pdf": "checklist",
  "cut.svg": "cut-svg",
  "cut.dxf": "dxf",
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
                <th title="Fit on the sewn cover">Fit</th>
                <th>
                  Customers
                  {!editor && (
                    <Info label="About the customers' answers">
                      The customers' fit answers are shown to editors and
                      admins.
                    </Info>
                  )}
                </th>
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
      <div className="head-row ws-h">
        <Heading level={2} icon="orders">
          Orders
        </Heading>
        <StatusChip status="waiting">
          {waiting.length} waiting for production
        </StatusChip>
        <StatusChip status="in-production">
          {orders.length - waiting.length} in production
        </StatusChip>
      </div>
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
                    <StatusChip
                      status={
                        o.status === "waiting_production"
                          ? "waiting"
                          : o.status === "in_production"
                            ? "in-production"
                            : o.status
                      }
                    >
                      {ORDER_STATUS[o.status] ?? o.status}
                    </StatusChip>
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
                          <Icon name="send-production" />
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
                        <StatusChip
                          status={o.desk_status ?? "waiting"}
                          title="On the Desk"
                        >
                          {o.desk_status ?? "?"}
                        </StatusChip>
                        <div className="ws-files">
                          {o.dxf_ok ? (
                            <a
                              className="btn dxf"
                              href={fileUrl(o.model_id, "cut.dxf")}
                              download
                              title="Cutting table (DXF)"
                              aria-label="Cutting table (DXF)"
                            >
                              <Icon name="dxf" size={16} />
                              DXF
                            </a>
                          ) : (
                            <StatusChip
                              status="waiting"
                              className="dxf-locked"
                              title="DXF waits for the Desk's approval"
                            >
                              <Icon name="lock" size={13} /> DXF
                            </StatusChip>
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
            <IconLink
              icon="desk"
              label="Desk card"
              href={deskHref(w.id)}
              className="sm"
              size={15}
            />
            {w.arrangement && <span className="badge">arrangement</span>}
            <div className="muted small">
              {w.pieces} pieces · {w.vents} vents
              {w.products.length > 0 && ` · ${w.products.join(", ")}`}
            </div>
          </div>
        </div>
      </td>
      <td className="nowrap">
        <StatusChip status={w.status} />
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
              <FileLink
                key={f}
                icon={FILE_ICON[f] ?? "pdf"}
                label={FILE_LABEL[f] ?? f}
                short={FILE_SHORT[f] ?? f}
                href={fileUrl(w.id, f)}
              />
            ))}
          {(w.stamped ?? []).map((f) => (
            <FileLink
              key={`approved-${f}`}
              icon={f === "sizes.pdf" ? "sizes" : "cutting-list"}
              label={
                f === "sizes.pdf"
                  ? "Approved size drawing (stamped APPROVED by the Desk)"
                  : "Approved cutting list (stamped APPROVED by the Desk)"
              }
              short={f === "sizes.pdf" ? "Sizes ✓" : "List ✓"}
              href={`/api/models/${w.id}/approved/${f}`}
              approved
            />
          ))}
          {w.files.includes("cut.dxf") &&
            (w.dxf_ok ? (
              <a
                className="btn dxf"
                href={fileUrl(w.id, "cut.dxf")}
                download
                title={FILE_LABEL["cut.dxf"]}
                aria-label={FILE_LABEL["cut.dxf"]}
              >
                <Icon name="dxf" size={16} />
                DXF
              </a>
            ) : (
              <StatusChip
                status="waiting"
                className="dxf-locked"
                title="DXF waits for the Desk's (re)approval (the approval gate, ADR-079)"
              >
                <Icon name="lock" size={13} /> DXF
              </StatusChip>
            ))}
          {w.revision &&
            (w.revision.dxf_ok ? (
              <a
                className="btn dxf"
                href={revisionUrl(w.id, w.revision.n, "cut.dxf")}
                download
                title={`Revision ${w.revision.n} to cut (DXF)`}
              >
                <Icon name="dxf" size={16} />
                Rev. {w.revision.n}
              </a>
            ) : (
              <StatusChip
                status="waiting"
                className="dxf-locked"
                title={`Revision ${w.revision.n} to cut: not approved`}
              >
                <Icon name="lock" size={13} /> Rev. {w.revision.n}
              </StatusChip>
            ))}
        </div>
      </td>
      <td>
        {w.fit ? (
          <>
            <StatusChip status={w.fit.fits ? "fits" : "does-not-fit"}>
              {w.fit.fits ? "fits" : "does not fit"}
            </StatusChip>{" "}
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
          <span className="muted small" title="not measured yet">
            —
          </span>
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
          <span className="muted small" title="no answers">
            —
          </span>
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
