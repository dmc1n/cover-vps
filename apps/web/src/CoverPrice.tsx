// A cover's own commerce on its own page (ADR-126, docs/plans/studio-ui.md §12): the tab
// "Price & shop" (#/model/<id>/price) and the summary at the top of every cover's page.
//
// Price & shop: the cover's prices per channel (live, and the draft beside it), where each comes
// from (a fixed price or the rule), the margin; its costing line by line; whether the shop offers
// it as an existing cover and how its direct-order price is made; for admins its B2B companies,
// orders, quotes and match requests. Admins set or remove its fixed price **in the draft** (the
// same row Settings → Price rules used to hold); publishing stays one explicit action, here with
// the preview's count first and a confirmation. Editors look; viewers see no prices (as before).
import { useCallback, useEffect, useState } from "react";
import { CoverPrices, ModelDetail, prices } from "./api";
import { deskHref, modelHref, questionHref } from "./nav";
import { CostingSheet } from "./Prices";
import type { Question } from "./Questions";
import { useSession } from "./Session";

const eur = (x: number | null | undefined) =>
  x === null || x === undefined
    ? "–"
    : `€ ${x.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const when = (t: number | null | undefined) =>
  t ? new Date(t * 1000).toLocaleDateString() : "";
const QUOTE_SOURCE: Record<string, string> = {
  fixed: "fixed B2C price",
  stock: "configurator price",
  list: "B2B list price",
  list_fixed: "fixed list price",
  company_fixed: "the company's own price",
};
const KIND: Record<string, string> = {
  sofa: "sofa",
  corner_sofa: "corner sofa",
  dining_set: "dining set",
  round_set: "round dining set",
  lounger: "lounger",
  item: "single item",
};

/** The summary under a cover's head: the Desk, the workshop's fit and revision, its open
 * questions — so nobody has to open three pages to know where a cover stands. */
export function CoverSummary({ model }: { model: ModelDetail }) {
  const [qs, setQs] = useState<Question[] | null>(null);
  useEffect(() => {
    let live = true;
    fetch("/api/questions")
      .then((r) => (r.ok ? r.json() : null))
      .then(
        (d: { items: Question[] } | null) =>
          live &&
          setQs(
            (d?.items ?? []).filter(
              (q) =>
                q.status === "open" && q.models.some((m) => m.id === model.id),
            ),
          ),
      )
      .catch(() => live && setQs(null));
    return () => {
      live = false;
    };
  }, [model.id]);
  const w = model.workshop;
  return (
    <dl className="cv-summary" data-testid="cover-summary">
      <div>
        <dt>Desk</dt>
        <dd>
          {model.desk_status ? (
            <a href={deskHref(model.id)}>{model.desk_status}</a>
          ) : (
            "–"
          )}
          {w?.approved && (
            <span className="muted">
              {" "}
              · approved by {w.approved.by}, {when(w.approved.time)}
            </span>
          )}
          {w?.produced && (
            <span className="muted"> · produced {when(w.produced.time)}</span>
          )}
        </dd>
      </div>
      <div>
        <dt>Fit</dt>
        <dd>
          {w?.fit ? (
            <>
              <span className={`badge ${w.fit.fits ? "ok" : "warn"}`}>
                {w.fit.fits ? "fits" : "does not fit"}
              </span>
              {w.fit.measured > 0 && (
                <span className="muted">
                  {" "}
                  {w.fit.measured} sizes measured
                  {w.fit.worst &&
                    `, largest difference ${w.fit.worst.diff_mm} mm (${w.fit.worst.label})`}
                </span>
              )}
            </>
          ) : (
            <span className="muted">not measured yet</span>
          )}
        </dd>
      </div>
      <div>
        <dt>Workshop</dt>
        <dd>
          {w ? (
            <>
              {w.pieces} pieces, {w.vents} vents
              {w.revision && <> · cut revision {w.revision.n}</>}
              {" · "}
              <a href={modelHref(model.id, "pieces", "files")}>files</a>
              {!w.dxf_ok && <span className="muted"> (DXF locked)</span>}
            </>
          ) : (
            <span className="muted">not approved yet</span>
          )}
        </dd>
      </div>
      <div>
        <dt>Questions</dt>
        <dd>
          {qs === null ? (
            <span className="muted">–</span>
          ) : qs.length === 0 ? (
            <span className="muted">none open</span>
          ) : (
            qs.slice(0, 3).map((q, i) => (
              <span key={q.id}>
                {i > 0 && " · "}
                <a href={questionHref(q.id)}>
                  #{q.id} {q.title}
                </a>
              </span>
            ))
          )}
          {qs && qs.length > 3 && (
            <span className="muted"> and {qs.length - 3} more</span>
          )}
        </dd>
      </div>
    </dl>
  );
}

export function CoverPrice({ id }: { id: string; model?: ModelDetail }) {
  const { user } = useSession();
  const [c, setC] = useState<CoverPrices | null>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [set, setSet] = useState<"current" | "draft">("current");
  const [moves, setMoves] = useState<number | null>(null);
  const load = useCallback(() => {
    prices
      .cover(id)
      .then((x) => {
        setC(x);
        setErr("");
        setTyped({});
        setMoves(null);
        if (!x.draft) setSet("current");
      })
      .catch((e) => setErr(String(e)));
  }, [id]);
  useEffect(() => {
    setC(null);
    if (user?.role !== "viewer") load();
  }, [load, user?.role]);
  if (user?.role === "viewer")
    return (
      <p className="muted">
        Prices and the shop are for editors and admins (your account looks at
        covers).
      </p>
    );
  if (err && !c) return <p className="error">{err}</p>;
  if (!c) return <p className="muted">Loading…</p>;
  const edit = c.can_edit;
  const run = async (what: () => Promise<string | void>) => {
    setBusy(true);
    setMsg("");
    try {
      const m = await what();
      if (m) setMsg(m);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };
  const live = c.costing;
  const dc = c.costing_draft;
  const nDraft = c.draft ? c.draft.fixed.length + (c.draft.other ? 1 : 0) : 0;
  const mine = c.draft?.fixed.filter((f) => f.key === id) ?? [];
  const sheet = set === "draft" && dc ? dc : live;
  const qs = new URLSearchParams({ model: id, set }).toString();
  return (
    <div className="prices cover-price">
      {c.draft && (
        <section className="card attention" data-testid="draft-bar">
          <strong>
            The draft has {c.draft.fixed.length} fixed-price change
            {c.draft.fixed.length === 1 ? "" : "s"}
            {c.draft.other ? " and other changed numbers" : ""}
          </strong>{" "}
          <span className="muted">
            (by {c.draft.by}, {when(c.draft.time)}
            {mine.length > 0 ? `; ${mine.length} of them this cover's` : ""}) —
            not live until it is published.
          </span>{" "}
          {edit ? (
            <>
              <button
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const p = await prices.preview();
                    if (p.errors.length)
                      return "The draft has errors: " + p.errors.join("; ");
                    setMoves(p.changed);
                  })
                }
              >
                Preview
              </button>
              {moves !== null && (
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      if (
                        !window.confirm(
                          `Publish the whole draft (${nDraft} change${nDraft === 1 ? "" : "s"}, ${moves} price${moves === 1 ? "" : "s"} move)? The shop uses it at once; the version before is kept and can be rolled back.`,
                        )
                      )
                        return;
                      const r = await prices.publish(
                        c.draft?.note ? "" : `Published from the cover ${id}`,
                        c.draft?.time ?? null,
                      );
                      load();
                      return `Published version ${r.version}: ${r.prices_changed} prices changed.`;
                    })
                  }
                >
                  Publish ({moves} price{moves === 1 ? "" : "s"} move)
                </button>
              )}{" "}
            </>
          ) : null}
          <a href="#/settings/publish">all changes, versions</a>
        </section>
      )}
      {msg && <p className="muted">{msg}</p>}
      <section className="card" data-testid="cover-prices">
        <h3>Prices</h3>
        {!c.calculated && (
          <p className="muted">
            No calculated cover yet (no finished pieces): no cost and no
            calculated price. A fixed price can still be set.
          </p>
        )}
        <table className="list cover-prices">
          <thead>
            <tr>
              <th>Channel</th>
              <th>Live price</th>
              <th>Comes from</th>
              <th>Margin</th>
              {c.draft && <th>In the draft</th>}
              {edit && <th>Fixed price in the draft</th>}
            </tr>
          </thead>
          <tbody>
            {Object.entries(c.channels).map(([k, ch]) => {
              const lp = live?.channels[k];
              const dp = dc?.channels[k];
              const vat = ch.show_vat ? "incl. VAT" : "ex VAT";
              // the fixed price that applies in the draft (or live when there is no draft)
              const fx = c.draft ? ch.fixed_draft : ch.fixed_live;
              const shownLive = lp?.shown_eur ?? ch.fixed_live;
              const shownDraft = dp?.shown_eur ?? ch.fixed_draft;
              const differs =
                c.draft &&
                (shownDraft ?? null) !== (shownLive ?? null) &&
                !(
                  shownDraft != null &&
                  shownLive != null &&
                  Math.abs(shownDraft - shownLive) < 0.005
                );
              return (
                <tr key={k} className="static" data-channel={k}>
                  <td>
                    <b>{k.toUpperCase()}</b> {ch.name}
                    <div className="muted">{vat}</div>
                  </td>
                  <td>
                    <b>{eur(shownLive)}</b>
                    {lp && (
                      <div className="muted">
                        {ch.show_vat
                          ? `${eur(lp.net_eur)} ex VAT`
                          : `${eur(lp.gross_eur)} incl. VAT`}
                      </div>
                    )}
                  </td>
                  <td>
                    {ch.fixed_live ? (
                      <span className="pill">fixed price</span>
                    ) : (
                      <span className="pill muted-pill">calculated</span>
                    )}
                    {lp && !ch.fixed_live && (
                      <div className="muted">
                        {lp.method} {lp.pct} % on the{" "}
                        {lp.base === "landed" ? "landed cost" : "cost price"}
                      </div>
                    )}
                  </td>
                  <td>
                    {lp ? (
                      <>
                        {eur(lp.margin_eur)}{" "}
                        <span className="muted">({lp.margin_pct} %)</span>
                      </>
                    ) : (
                      "–"
                    )}
                  </td>
                  {c.draft && (
                    <td>
                      {differs ? (
                        <b>{eur(shownDraft)}</b>
                      ) : (
                        <span className="muted">unchanged</span>
                      )}
                      {differs && (
                        <div className="muted">
                          {ch.fixed_draft ? "fixed" : "calculated"}
                          {dp ? `, margin ${dp.margin_pct} %` : ""}
                        </div>
                      )}
                    </td>
                  )}
                  {edit && (
                    <td>
                      <div className="row">
                        <input
                          type="number"
                          className="num"
                          step="any"
                          min="0"
                          inputMode="decimal"
                          aria-label={`${k} fixed price`}
                          placeholder={fx ? String(fx) : "none"}
                          value={typed[k] ?? (fx ? String(fx) : "")}
                          onChange={(e) =>
                            setTyped({ ...typed, [k]: e.target.value })
                          }
                        />
                        <button
                          disabled={
                            busy ||
                            !(Number(typed[k]) > 0) ||
                            Number(typed[k]) === fx
                          }
                          onClick={() =>
                            run(async () => {
                              const r = await prices.setFixed(
                                id,
                                k,
                                Number(typed[k]),
                              );
                              load();
                              return r.errors.length
                                ? "Saved in the draft, but the draft has errors: " +
                                    r.errors.join("; ")
                                : `${k.toUpperCase()} fixed price ${eur(Number(typed[k]))} (${vat}) saved in the draft — not live until it is published.`;
                            })
                          }
                        >
                          Save in draft
                        </button>
                        {fx ? (
                          <button
                            disabled={busy}
                            title="The calculated price applies again (in the draft)"
                            onClick={() =>
                              run(async () => {
                                await prices.setFixed(id, k, null);
                                load();
                                return `${k.toUpperCase()} fixed price removed in the draft: the calculated price applies once published.`;
                              })
                            }
                          >
                            Remove
                          </button>
                        ) : null}
                      </div>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="help">
          A fixed price wins over the channel's rule, without rounding (B2C
          incl. VAT, B2B ex VAT). The rules, VAT and rounding:{" "}
          <a href="#/settings/pricing">Settings → Price rules</a>; materials and
          labour: <a href="#/settings/costs">Settings → Costs</a>.
          {!edit && " An admin changes prices."}
        </p>
      </section>
      {sheet && (
        <section className="cover-cost" data-testid="cover-cost">
          <div className="row">
            <h3>Cost</h3>
            <span className="spacer" />
            {dc && (
              <span className="seg" role="group" aria-label="Price set">
                <button
                  className={set === "current" ? "on" : ""}
                  onClick={() => setSet("current")}
                >
                  live
                </button>
                <button
                  className={set === "draft" ? "on" : ""}
                  onClick={() => setSet("draft")}
                >
                  draft
                </button>
              </span>
            )}
          </div>
          {c.costing_draft_error && (
            <p className="error">{c.costing_draft_error}</p>
          )}
          <CostingSheet
            c={{ ...sheet, name: live?.name ?? id, model: id }}
            qs={qs}
          />
        </section>
      )}
      <ShopPart c={c} id={id} />
      {c.companies !== undefined && (
        <section className="card" data-testid="cover-b2b">
          <h3>B2B: companies with their own price</h3>
          {c.companies.length === 0 ? (
            <p className="muted">
              None: business customers buy it at their price list's price (
              {c.channels.b2b ? eur(live?.channels.b2b?.shown_eur) : "–"} ex VAT
              on the B2B list).
            </p>
          ) : (
            <table className="list">
              <tbody>
                {c.companies.map((x) => (
                  <tr key={x.id} className="static">
                    <td>
                      <a href="#/shop/b2b">{x.name}</a>{" "}
                      <span className="muted">({x.status})</span>
                    </td>
                    <td>{eur(x.price_eur)} ex VAT</td>
                    <td className="muted">list: {x.price_list_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="help">
            A company's own prices are set on the company: Shop →{" "}
            <a href="#/shop/b2b">B2B customers</a>.
          </p>
        </section>
      )}
      {c.orders !== undefined && <OrdersPart c={c} />}
    </div>
  );
}

function ShopPart({ c, id }: { c: CoverPrices; id: string }) {
  const s = c.shop;
  const d = s.direct;
  const notes = Object.entries(d.delivery_note);
  return (
    <section className="card" data-testid="cover-shop">
      <h3>Shop</h3>
      <p>
        {s.offered ? (
          <span className="badge ok">offered as an existing cover</span>
        ) : (
          <span className="badge">not offered as an existing cover</span>
        )}{" "}
        {!s.offered && s.why_not && (
          <span className="muted">— {s.why_not}</span>
        )}
      </p>
      {s.card && (
        <p className="muted">
          {s.card.name}
          {s.card.kind && ` · ${KIND[s.card.kind] ?? s.card.kind}`}
          {s.card.size_cm?.length === 3 &&
            ` · fits furniture ${s.card.size_cm.join(" × ")} cm`}
          {s.card.height_max && " (height: up to)"}
          {s.card.side && ` · ${s.card.side}`}
          {s.card.chairs && " · with chairs"}
          {s.card.category && ` · category ${s.card.category}`}
        </p>
      )}
      {s.price_list.length > 0 && (
        <>
          <h4>In the price list</h4>
          <table className="list">
            <thead>
              <tr>
                <th>Code</th>
                <th>Section</th>
                <th>Item</th>
                <th>Suits</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              {s.price_list.map((r, i) => (
                <tr key={i} className="static">
                  <td>
                    {r.code}
                    {!r.used && <span className="muted"> (not used)</span>}
                  </td>
                  <td>{r.section ?? ""}</td>
                  <td>{r.item ?? ""}</td>
                  <td className="muted">{r.suitable ?? ""}</td>
                  <td className="muted">{r.size ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {s.doubts.length > 0 && (
        <p className="muted">Doubts: {s.doubts.join("; ")}</p>
      )}
      <h4>Ordered directly ("Bestel direct")</h4>
      <p>
        {d.price_source === "fixed" ? (
          <>
            At its fixed B2C price, <b>{eur(d.fixed_eur)}</b> incl. VAT (no
            discount on top).
          </>
        ) : (
          <>
            At the configurator's price for its own sizes
            {d.discount_pct > 0
              ? `, minus the direct-order discount of ${d.discount_pct} %`
              : " (no direct-order discount set)"}
            . Set a fixed B2C price above to sell it at a price of its own.
          </>
        )}
      </p>
      <p className="muted">
        Delivery promise:{" "}
        {notes.length ? (
          notes.map(([lang, t]) => (
            <span key={lang}>
              <b>{lang}</b> “{t}”{" "}
            </span>
          ))
        ) : (
          <>none (hidden in the shop)</>
        )}
        . The discount and the promise are the same for every cover: Settings →{" "}
        <a href="#/settings/selling">Selling</a>,{" "}
        <a href="#/settings/company">Company &amp; shop</a>.
      </p>
      {!s.offered && id.startsWith("drawing-") && (
        <p className="help">
          A drawing cover is offered once the Desk approved it and its kind is
          sure (ADR-114).
        </p>
      )}
    </section>
  );
}

function OrdersPart({ c }: { c: CoverPrices }) {
  const orders = c.orders ?? [];
  const quotes = c.quotes ?? [];
  const matches = c.matches ?? [];
  return (
    <section className="card" data-testid="cover-orders">
      <h3>Orders, quotes and requests</h3>
      {orders.length === 0 && quotes.length === 0 && matches.length === 0 && (
        <p className="muted">None yet for this cover.</p>
      )}
      {orders.length > 0 && (
        <>
          <h4>Orders</h4>
          <table className="list">
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="static">
                  <td>
                    <a href={`#/shop/orders/${o.id}`}>Order {o.id}</a>
                  </td>
                  <td>{when(o.created)}</td>
                  <td>
                    {o.customer}
                    {o.b2b && <span className="pill">B2B</span>}
                    {o.qty ? ` × ${o.qty}` : ""}
                  </td>
                  <td>{eur(o.total_eur)}</td>
                  <td>{o.status}</td>
                  <td className="muted">
                    {o.stock ? "existing cover" : "produced as this model"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {quotes.length > 0 && (
        <>
          <h4>Recent quotes</h4>
          <table className="list">
            <tbody>
              {quotes.map((q) => (
                <tr key={q.where + q.id} className="static">
                  <td className="muted">{q.id.slice(0, 8)}</td>
                  <td>{when(q.time)}</td>
                  <td>{q.where === "b2b" ? "B2B shop" : "shop"}</td>
                  <td>
                    {eur(q.price_eur)}{" "}
                    <span className="muted">{q.vat} VAT</span>
                  </td>
                  <td className="muted">
                    {QUOTE_SOURCE[q.source ?? ""] ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {matches.length > 0 && (
        <>
          <h4>Match requests</h4>
          <table className="list">
            <tbody>
              {matches.map((m) => (
                <tr key={m.id} className="static">
                  <td>
                    <a href="#/shop/requests">Request {m.id}</a>
                  </td>
                  <td>{when(m.created)}</td>
                  <td>
                    {m.product}, {m.best_pct} %
                  </td>
                  <td>
                    {m.status}
                    {m.chosen
                      ? ` → ${m.chosen === c.model ? "this cover" : m.chosen}`
                      : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <p className="help">
        All orders and requests: Shop → <a href="#/shop/orders">Orders</a>,{" "}
        <a href="#/shop/requests">Requests</a>.
      </p>
    </section>
  );
}
