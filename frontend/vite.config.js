import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser talks to /api; Vite forwards it to FastAPI on port 8000.
// The SQLite database is never exposed to the browser.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
