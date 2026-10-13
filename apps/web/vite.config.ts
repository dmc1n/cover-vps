import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// The shop's font (Work Sans, self-hosted, ADR-105) and the studio's web fallback (Inter, where
// the device has no SF, ADR-130) are asked for before the stylesheet needs them, so the first
// paint already has them: a preload of the Latin file.
function preloadShopFont(): Plugin {
  return {
    name: "preload-shop-font",
    transformIndexHtml(html, ctx) {
      if (!ctx.bundle || !/(shop|index)\.html$/.test(ctx.filename)) return html;
      const file = /index\.html$/.test(ctx.filename)
        ? /inter-latin-wght-normal-.*\.woff2$/
        : /work-sans-latin-wght-normal-.*\.woff2$/;
      const font = Object.keys(ctx.bundle).find((f) => file.test(f));
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
