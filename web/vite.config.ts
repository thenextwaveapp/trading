import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The data comes from the existing backend (runtime.server.app). In dev we
// proxy /api + /candles to it so the React app hits the same source as prod.
// Default is the live VPS — nobody runs the python server locally anymore;
// override with VITE_API_TARGET (e.g. http://127.0.0.1:8787 or a tunnel).
const API_TARGET = process.env.VITE_API_TARGET || "https://fleet.presencenet.io";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Allow Cloudflare quick-tunnel hosts so the dev server can be reached over
    // HTTPS (a secure context) from a phone — required for Supabase auth, which
    // needs crypto.subtle and so breaks over a bare-IP http origin.
    allowedHosts: [".trycloudflare.com"],
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
