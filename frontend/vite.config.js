import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { developmentHeaders, productionHeaders } from "./security-headers.js";

// In development the browser talks to Vite (port 5173); Vite forwards /api/* to FastAPI (port 8000).
// 127.0.0.1 is used on purpose: "localhost" can resolve to IPv6 (::1) and miss the backend.
const apiProxy = {
  "/api": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    // Pass the browser's real address on (X-Forwarded-For) so per-IP rate limits and the audit log see it.
    // uvicorn trusts this header only from 127.0.0.1 (its default --forwarded-allow-ips), i.e. from this proxy.
    xfwd: true,
  },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: apiProxy, headers: developmentHeaders },
  // `npm run build && npm run preview` serves the production build with the PRODUCTION headers (strict CSP).
  preview: { port: 4173, proxy: apiProxy, headers: productionHeaders },
  build: { sourcemap: false }, // don't publish the original source code
});
