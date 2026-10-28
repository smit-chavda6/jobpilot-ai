import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

// Dev/preview servers proxy /api to the FastAPI app so session cookies stay same-origin.
const apiTarget = process.env.VITE_API_PROXY ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: 5173, proxy: { "/api": { target: apiTarget } } },
  preview: { port: 4173, proxy: { "/api": { target: apiTarget } } },
  build: {
    rollupOptions: {
      output: { manualChunks: { react: ["react", "react-dom", "react-router"], charts: ["recharts"] } },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
