import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development `npm run dev` forwards /api to the Python server (cover-web on 8080).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8080" } },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
    modulePreload: { polyfill: false }, // every browser the shop supports preloads modules itself
    // two front doors: Cover Studio (index.html) and the cover webshop (shop.html, ADR-062)
    rollupOptions: {
      input: { main: "index.html", shop: "shop.html" },
      // three.js and React in chunks of their own (ADR-101): the shop's pages load three.js only
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
