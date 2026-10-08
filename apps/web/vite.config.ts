import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// The shop's own font (Work Sans, self-hosted, ADR-103) is asked for before the stylesheet
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
    // two front doors: Cover Studio (index.html) and the cover webshop (shop.html, ADR-062)
    rollupOptions: { input: { main: "index.html", shop: "shop.html" } },
  },
});
