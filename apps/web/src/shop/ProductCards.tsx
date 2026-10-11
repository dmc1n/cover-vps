// What to cover: garden furniture or a barbecue (ADR-119), each group its own cards; a
// barbecue's cover goes on a cold barbecue only.
export function ProductCards({
  products,
  product,
  setProduct,
  w,
  name,
  bbq,
}: {
  products: Record<string, { group?: string | null }>;
  product: string;
  setProduct: (k: string) => void;
  w: (key: string) => string;
  name: (key: string) => string;
  /** the barbecues are on (the shop setting bbq_enabled, ADR-119) */
  bbq: boolean;
}) {
  const groupOf = (k: string) => products[k]?.group ?? "furniture";
  const keys = Object.keys(products).filter((k) => bbq || groupOf(k) !== "bbq");
  const groups = [...new Set(keys.map(groupOf))];
  const current = groupOf(product);
  return (
    <>
      {groups.length > 1 && (
        <div className="s-groups" role="tablist">
          {groups.map((g) => (
            <button
              key={g}
              role="tab"
              aria-selected={g === current}
              className={`s-chip ${g === current ? "on" : ""}`}
              onClick={() =>
                g !== current && setProduct(keys.find((k) => groupOf(k) === g)!)
              }
            >
              {w(`group_${g}`)}
            </button>
          ))}
        </div>
      )}
      <div className="s-products">
        {keys
          .filter((k) => groupOf(k) === current)
          .map((k) => (
            <button
              key={k}
              className={`s-card ${product === k ? "on" : ""}`}
              onClick={() => setProduct(k)}
            >
              {name(k)}
            </button>
          ))}
      </div>
      {current === "bbq" && <p className="s-advice s-cold">{w("bbq_cold")}</p>}
    </>
  );
}
