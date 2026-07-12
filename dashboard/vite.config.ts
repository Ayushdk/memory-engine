import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev mode proxies /api to the engine so the browser never needs CORS
// (production build is served BY the engine at /dashboard, same origin).
export default defineConfig({
  base: "/dashboard/",
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/setupTests.ts",
  },
});
