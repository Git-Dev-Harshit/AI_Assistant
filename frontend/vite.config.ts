import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The UI calls `/api/*`; Vite forwards those requests to the FastAPI backend, so the
// browser only ever talks to one origin (no CORS, no separate web server needed).
// Natively the backend is on localhost:8000; inside Docker Compose it is `backend:8000`.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

const proxy = {
  "/api": {
    target: apiTarget,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
    // LLM answers on CPU can take a while; keep this above the backend's LLM timeout.
    timeout: 180_000,
    proxyTimeout: 180_000,
  },
};

export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173, strictPort: true, proxy },
  preview: { host: true, port: 5173, strictPort: true, proxy },
});
