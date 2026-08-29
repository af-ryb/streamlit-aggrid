import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  base: "./",
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: "build",
    chunkSizeWarningLimit: 5000, // AG-Grid is large (~7MB bundled)
    lib: {
      entry: "src/index.tsx",
      formats: ["es"],
      // Content-hashed so the browser cache invalidates on a real change.
      // st_aggrid/component.py globs these as index-*.js / index-*.css, and a
      // glob must match exactly one file — the `build` script wipes outDir
      // first so stale hashes can't accumulate.
      fileName: "index-[hash]",
    },
    rollupOptions: {
      output: {
        assetFileNames: "index-[hash][extname]",
        inlineDynamicImports: true, // single JS bundle
      },
    },
  },
  server: { port: 3001 },
})
