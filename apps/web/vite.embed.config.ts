import { defineConfig } from "vite";

// The dealer embed (ADR-150): <s2dio-configurator>, one module script for dealers' own websites,
// built after the pages into dist/embed/v1/. The entry keeps its name (the snippet names it);
// the 3D view (three.js) is a chunk of its own with a hashed name, loaded only where the dealer
// shows 3D. `base: "./"`: the chunk is found next to the script, whatever page loads it.
export default defineConfig({
  base: "./",
  publicDir: false,
  build: {
    outDir: "dist/embed/v1",
    emptyOutDir: true,
    target: "es2020",
    modulePreload: false,
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      input: { configurator: "src/embed/configurator.ts" },
      preserveEntrySignatures: "exports-only",
      output: {
        format: "es",
        entryFileNames: "[name].js",
        chunkFileNames: "[name]-[hash].js",
      },
    },
  },
});
