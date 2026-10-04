// The customer's configurator (#/configure, ADR-061): no login, made to sit in an iframe on a
// webshop. The customer picks what to cover, gives rough sizes and options, and sees at once a
// 3D proposal, the pieces, the fabric and the price; then can send it as a request.
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

interface Field {
  key: string;
  default: number | boolean;
  min: number | null;
  max: number | null;
  unit: string | null;
}
interface Options {
  products: Record<string, { label: string; fields: Field[] }>;
  options: { colours: string[] };
}
interface Quote {
  id: string;
  product: string;
  shape: string;
  pieces: { name: string; width_cm: number; height_cm: number }[];
  cover_area_m2: number;
  fabric_m2: number;
  roll_m: number;
  vents: number;
  balloons: number;
  drawcord_m: number;
  colour: string;
  price: {
    sale_eur: number;
    sale_ex_vat_eur: number;
    vat_eur: number;
    indicative: boolean;
  };
  near: {
    model_id: string;
    name: string;
    size_cm: number[];
    difference_cm: number;
  }[];
  preview: string;
}

const API = "/api/public/v1";
const label = (k: string) =>
  k
    .replace(/_cm$/, "")
    .replace(/_/g, " ")
    .replace(/^./, (c) => c.toUpperCase());
const euro = (n: number) =>
  new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" }).format(
    n,
  );

async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok)
    throw new Error(
      (data as { detail?: string }).detail ?? `error ${r.status}`,
    );
  return data as T;
}

function Preview({ url }: { url: string | null }) {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = host.current;
    if (!el || !url) return;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#f9f6e8");
    const camera = new THREE.PerspectiveCamera(
      40,
      el.clientWidth / el.clientHeight,
      0.01,
      100,
    );
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(el.clientWidth, el.clientHeight);
    el.appendChild(renderer.domElement);
    scene.add(new THREE.HemisphereLight("#fffdf6", "#85886f", 1.6));
    const sun = new THREE.DirectionalLight("#ffffff", 1.3);
    sun.position.set(2, 4, 3);
    scene.add(sun);
    const grid = new THREE.GridHelper(6, 60, "#d6cdb6", "#ebe4d2");
    scene.add(grid);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    let alive = true;
    new GLTFLoader().load(url, (gltf) => {
      if (!alive) return;
      gltf.scene.traverse((o) => {
        const m = o as THREE.Mesh;
        if (m.isMesh)
          (m.material as THREE.MeshStandardMaterial).side = THREE.DoubleSide;
      });
      scene.add(gltf.scene);
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const size = box.getSize(new THREE.Vector3()).length();
      const c = box.getCenter(new THREE.Vector3());
      controls.target.copy(c);
      camera.position
        .copy(c)
        .add(new THREE.Vector3(0.7, 0.55, 1.0).multiplyScalar(size));
      grid.position.y = box.min.y;
    });
    renderer.setAnimationLoop(() => {
      controls.update();
      renderer.render(scene, camera);
    });
    const onResize = () => {
      camera.aspect = el.clientWidth / el.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(el.clientWidth, el.clientHeight);
    };
    window.addEventListener("resize", onResize);
    return () => {
      alive = false;
      window.removeEventListener("resize", onResize);
      renderer.setAnimationLoop(null);
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
  }, [url]);
  return <div className="cfg-preview" ref={host} />;
}

export default function Configure() {
  const [opts, setOpts] = useState<Options | null>(null);
  const [product, setProduct] = useState("dining_set");
  const [sizes, setSizes] = useState<Record<string, number | boolean>>({});
  const [colour, setColour] = useState("");
  const [vents, setVents] = useState(true);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [contact, setContact] = useState({
    name: "",
    email: "",
    phone: "",
    note: "",
  });
  const [sent, setSent] = useState("");

  useEffect(() => {
    fetch(`${API}/options`)
      .then((r) => r.json())
      .then((o: Options) => {
        setOpts(o);
        setColour(o.options.colours[0] ?? "");
      })
      .catch(() =>
        setError("The configurator could not load. Please try again later."),
      );
  }, []);
  useEffect(() => {
    if (!opts) return;
    const defaults: Record<string, number | boolean> = {};
    for (const f of opts.products[product].fields) defaults[f.key] = f.default;
    setSizes(defaults);
    setQuote(null);
    setSent("");
  }, [product, opts]);

  // a new proposal shortly after every change
  useEffect(() => {
    if (!opts || !Object.keys(sizes).length) return;
    const t = setTimeout(async () => {
      setBusy(true);
      setError("");
      try {
        setQuote(
          await post<Quote>(`${API}/quote`, { product, sizes, colour, vents }),
        );
      } catch (e) {
        setError(String(e).replace(/^Error: /, ""));
      } finally {
        setBusy(false);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [sizes, colour, vents, product, opts]);

  if (!opts) return <div className="cfg">{error || "Loading…"}</div>;
  const fields = opts.products[product].fields;
  return (
    <div className="cfg">
      <header className="cfg-head">
        <strong>Design your cover</strong>
        <span className="muted">
          Rough sizes are enough: we make the pattern for you.
        </span>
      </header>
      <div className="cfg-body">
        <section className="cfg-form">
          <label>
            What do you want to cover?
            <select
              value={product}
              onChange={(e) => setProduct(e.target.value)}
            >
              {Object.entries(opts.products).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>
          {fields.map((f) =>
            f.min === null ? (
              <label key={f.key} className="check">
                <input
                  type="checkbox"
                  checked={!!sizes[f.key]}
                  onChange={(e) =>
                    setSizes({ ...sizes, [f.key]: e.target.checked })
                  }
                />{" "}
                {f.key === "chairs"
                  ? "Cover the chairs too (room beside the table)"
                  : label(f.key)}
              </label>
            ) : (
              <label key={f.key}>
                {label(f.key)} ({f.unit})
                <input
                  type="number"
                  min={f.min}
                  max={f.max ?? undefined}
                  value={Number(sizes[f.key] ?? f.default)}
                  onChange={(e) =>
                    setSizes({ ...sizes, [f.key]: Number(e.target.value) })
                  }
                />
                <span className="muted">
                  {f.min}–{f.max} {f.unit}
                </span>
              </label>
            ),
          )}
          <label>
            Colour
            <select value={colour} onChange={(e) => setColour(e.target.value)}>
              {opts.options.colours.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={vents}
              onChange={(e) => setVents(e.target.checked)}
            />{" "}
            Air vents (recommended: against damp)
          </label>
          {error && <p className="error">{error}</p>}
        </section>
        <section className="cfg-result">
          <Preview url={quote ? quote.preview : null} />
          {quote && (
            <div className="cfg-price">
              <div className="cfg-amount">
                {euro(quote.price.sale_eur)}{" "}
                <span className="muted">incl. VAT</span>
              </div>
              {quote.price.indicative && (
                <p className="muted">
                  Indicative price: the final price follows with our proposal.
                </p>
              )}
              <ul>
                <li>
                  {quote.pieces.length} pieces, {quote.cover_area_m2} m² of
                  cover ({quote.fabric_m2} m² of fabric)
                </li>
                <li>
                  {quote.vents} air vent{quote.vents === 1 ? "" : "s"}, drawcord{" "}
                  {quote.drawcord_m} m
                  {quote.balloons
                    ? `, ${quote.balloons} support balloon${quote.balloons === 1 ? "" : "s"}`
                    : ""}
                </li>
                <li>Colour: {quote.colour}</li>
              </ul>
              {quote.near.length > 0 && quote.near[0].difference_cm < 30 && (
                <p className="muted">
                  Close to {quote.near[0].name}: a cover we have made and
                  tested.
                </p>
              )}
              {busy && <p className="muted">Updating…</p>}
            </div>
          )}
          {quote && !sent && (
            <form
              className="cfg-request"
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  const r = await post<{ message: string }>(`${API}/request`, {
                    quote_id: quote.id,
                    ...contact,
                  });
                  setSent(r.message);
                } catch (err) {
                  setError(String(err).replace(/^Error: /, ""));
                }
              }}
            >
              <strong>Ask for this cover</strong>
              <input
                placeholder="Name"
                required
                value={contact.name}
                onChange={(e) =>
                  setContact({ ...contact, name: e.target.value })
                }
              />
              <input
                placeholder="E-mail"
                type="email"
                required
                value={contact.email}
                onChange={(e) =>
                  setContact({ ...contact, email: e.target.value })
                }
              />
              <input
                placeholder="Phone (optional)"
                value={contact.phone}
                onChange={(e) =>
                  setContact({ ...contact, phone: e.target.value })
                }
              />
              <textarea
                placeholder="Anything we should know (optional)"
                value={contact.note}
                onChange={(e) =>
                  setContact({ ...contact, note: e.target.value })
                }
              />
              <button className="primary">Send request</button>
            </form>
          )}
          {sent && <p className="cfg-sent">{sent}</p>}
        </section>
      </div>
    </div>
  );
}
