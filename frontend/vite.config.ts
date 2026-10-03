import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Phase P5 (FRONTEND_BLUEPRINT.md §2): Vite dev server proxies /api to the FastAPI gateway.
// In mock mode (default until Phase P5c wires the real gateway) MSW intercepts /api requests
// client-side, so this proxy only matters once src/sentinel/gateway/api.py is implemented and
// VITE_USE_MOCKS is turned off.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
