import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// The shop's own font (Work Sans, self-hosted, ADR-105) is asked for before the stylesheet
// needs it, so the first paint already has it: a preload of the Latin file in shop.html.
function preloadShopFont(): Plugin {
  return {
    name: "preload-shop-font",
    transformIndexHtml(html, ctx) {
      if (!ctx.bundle || !ctx.filename.endsWith("shop.html")) return html;
      const font = Object.keys(ctx.bundle).find((f) =>
        /work-sans-latin-wght-normal-.*\.woff2$/.test(f),
      );
      if (!font) return html;
      return [
        {
          tag: "link",
          attrs: {
            rel: "preload",
            href: `/${font}`,
            as: "font",
            type: "font/woff2",
            crossorigin: "",
          },
          injectTo: "head-prepend",
        },
      ];
    },
  };
}

// During development `npm run dev` forwards /api to the Python server (cover-web on 8080).
export default defineConfig({
  plugins: [react(), preloadShopFont()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8080" } },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
    modulePreload: { polyfill: false }, // every browser the shop supports preloads modules itself
    // two front doors: Cover Studio (index.html) and the cover webshop (shop.html, ADR-062)
    rollupOptions: {
      // and the B2B shop for business customers (b2b.html, ADR-104)
      input: { main: "index.html", shop: "shop.html", b2b: "b2b.html" },
      // three.js and React in chunks of their own (ADR-106): the shop's pages load three.js only
      // where they show 3D, and both front doors share one cached copy of each
      output: {
        manualChunks(id) {
          if (/node_modules\/three\//.test(id)) return "three";
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id))
            return "react";
        },
      },
    },
  },
});
