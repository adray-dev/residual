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
      // Every top-level prefix the API serves, checked against `/openapi.json` rather than
      // remembered. An unproxied route silently returns the dev server's index.html, so it
      // fails as "unexpected token '<'" instead of as a missing route — that has now cost
      // debugging time twice (/scenario, then /shortlists), which is why this list is
      // derived from the route table and not from whatever the last feature happened to add.
      [
        "/meta",
        "/map",
        "/parcel",      // also covers /parcels/search
        "/assumptions",
        "/scenario",    // also covers /scenarios
        "/shortlists",
        "/export.xlsx",
        "/tiles",
        "/health",
      ].map((path) => [
        path,
        { target: process.env.API_ORIGIN ?? "http://127.0.0.1:8000", changeOrigin: true },
      ]),
    ),
  },
});
