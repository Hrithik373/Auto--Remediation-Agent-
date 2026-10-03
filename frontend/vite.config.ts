import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Phase P5 (FRONTEND_BLUEPRINT.md §2): in live mode (VITE_USE_MOCKS=false, e.g. `npm run dev:live`)
// the dev server proxies /api to the FastAPI gateway at VITE_API_TARGET. In mock mode MSW intercepts
// /api client-side and the proxy is never hit.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": "/src",
      },
    },
    server: {
      proxy: {
        "/api": {
          target: env.VITE_API_TARGET ?? "http://localhost:8080",
          changeOrigin: true,
        },
      },
    },
  };
});
