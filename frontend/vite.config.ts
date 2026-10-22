import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev: the API runs on 127.0.0.1:8000 and Vite proxies /api to it.
// Production: the backend serves the compiled files from frontend/dist (same origin, no proxy).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
