// Construction de l'interface avec Vite (remplace react-scripts, abandonné).
// Les variables REACT_APP_* existantes (Render, Docker) restent valables : import.meta.env.REACT_APP_API_URL.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  envPrefix: ["VITE_", "REACT_APP_"],
  server: { port: 3000, open: false },
  preview: { port: 3000 },
  build: { outDir: "build", sourcemap: false, chunkSizeWarningLimit: 1500 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/setupTests.js",
    css: false,
  },
});
