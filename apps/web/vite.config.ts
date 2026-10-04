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
    // two front doors: Cover Studio (index.html) and the cover webshop (shop.html, ADR-062)
    rollupOptions: { input: { main: "index.html", shop: "shop.html" } },
  },
});
