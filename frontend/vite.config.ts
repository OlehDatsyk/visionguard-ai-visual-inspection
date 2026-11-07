/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

function checkApiUrl(url: string | undefined): void {
  if (!url) throw new Error("VITE_API_BASE_URL must be set for a production build. See .env.example.");
  if (url === "/") return; // Same origin: the API serves this build (root Dockerfile).
  const local = /^http:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(url);
  if (!local && !url.startsWith("https://")) throw new Error("VITE_API_BASE_URL must use HTTPS outside local testing.");
}

export default defineConfig(({ command, mode }) => {
  if (command === "build") checkApiUrl(process.env.VITE_API_BASE_URL ?? loadEnv(mode, process.cwd(), "VITE_").VITE_API_BASE_URL);
  return {
    plugins: [react()],
    server: { port: 5173, host: "127.0.0.1", strictPort: true },
    build: {
      outDir: "dist",
      chunkSizeWarningLimit: 800,
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes("node_modules/recharts") || id.includes("node_modules/d3-")) return "charts";
            return undefined;
          },
        },
      },
    },
    test: { testTimeout: 30000, environment: "jsdom", globals: true, setupFiles: "./src/test/setup.ts", css: false, exclude: ["e2e/**", "node_modules/**"] },
  };
});
