import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev server proxies the API; `npm run build` output is served by `revizorro-api` itself.
export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1500 },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
