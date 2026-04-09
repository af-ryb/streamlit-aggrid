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
    cssMinify: false, // CRITICAL: Streamlit CCv2 inline CSS detection requires newlines
    chunkSizeWarningLimit: 5000, // AG-Grid is large (~3-5MB bundled)
    lib: {
      entry: "src/index.tsx",
      formats: ["es"],
      fileName: "index",
    },
    rollupOptions: {
      output: {
        assetFileNames: "[name][extname]", // predictable names: style.css
        inlineDynamicImports: true, // single JS bundle
      },
    },
  },
  server: { port: 3001 },
})
