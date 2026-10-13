// node e2e/iconsheet.mjs OUT.html: the icon sheet (e2e/iconsheet.tsx) as one static page (ADR-130).
import { build } from "esbuild";
import { rmSync, writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const out = process.argv[2] ?? "iconsheet.html";
const tmp = fileURLToPath(new URL("./.iconsheet.tmp.mjs", import.meta.url));
await build({
  entryPoints: [fileURLToPath(new URL("./iconsheet.tsx", import.meta.url))],
  bundle: true,
  packages: "external", // react, react-dom and lucide-react from node_modules
  platform: "node",
  format: "esm",
  outfile: tmp,
  jsx: "automatic",
  logLevel: "error",
});
try {
  const { sheet } = await import(pathToFileURL(tmp).href);
  writeFileSync(out, sheet());
} finally {
  rmSync(tmp, { force: true });
}
console.log("icon sheet:", out);
