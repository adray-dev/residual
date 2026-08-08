import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API is proxied rather than called cross-origin so the dev server and the built
// bundle speak the same relative URLs. /tiles is proxied too: FastAPI mounts the PMTiles
// there (api/main.py), and PMTiles fetches them with HTTP range requests, which only work
// against the real static mount.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      // Prefix matches, so "/scenario" also covers "/scenarios" and "/scenario/{id}/export".
      // Every API path the client can reach must be listed: an unproxied one silently
      // returns the dev server's index.html, which fails as "unexpected token '<'" rather
      // than as anything resembling a missing route.
      ["/meta", "/map", "/parcel", "/assumptions", "/scenario", "/tiles", "/health"].map((path) => [
        path,
        { target: process.env.API_ORIGIN ?? "http://127.0.0.1:8000", changeOrigin: true },
      ]),
    ),
  },
});
