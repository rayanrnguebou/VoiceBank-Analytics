// Construction de l'interface avec Vite (remplace react-scripts, abandonné).
// Les variables REACT_APP_* existantes (Render, Docker) restent valables : import.meta.env.REACT_APP_API_URL.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  envPrefix: ["VITE_", "REACT_APP_"],
  server: { port: 3000, open: false },
  preview: { port: 3000 },
  // Navigateurs plus anciens que la cible par défaut de Vite (Safari 16.4, Chrome 111) : iPhone sous iOS 14-16,
  // téléphones Android dont le navigateur n'est plus mis à jour, Samsung Internet… La syntaxe récente est réécrite.
  build: {
    outDir: "build", sourcemap: false, chunkSizeWarningLimit: 1500,
    target: ["es2020", "chrome87", "edge88", "firefox78", "safari14", "ios14"],
    cssTarget: ["chrome87", "edge88", "firefox78", "safari14", "ios14"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/setupTests.js",
    css: false,
  },
});
