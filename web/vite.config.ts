import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API + server-rendered shells to the FastAPI backend on :8000,
// so the SPA can use same-origin relative paths in dev and behind a reverse proxy in prod.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/dashboard": "http://localhost:8000",
      "/onboarding": "http://localhost:8000",
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
