import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The data comes from the existing dashboard backend (fleet_dashboard.py),
// which proxies the live Hetzner paper fleet. In dev we proxy /api + /candles
// to it so the React app hits the exact same source as :8787 / :8789.
// Override the target with VITE_API_TARGET (e.g. a tunnelled port).
const API_TARGET = process.env.VITE_API_TARGET || "http://127.0.0.1:8787";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
      "/candles": { target: API_TARGET, changeOrigin: true },
      "/yf": {
        target: "https://query1.finance.yahoo.com",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/yf/, ""),
      },
    },
  },
});
