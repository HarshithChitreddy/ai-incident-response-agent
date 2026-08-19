import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev server proxies /api to the local backend; in docker, nginx does the same
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
