/** @type {import('tailwindcss').Config} */
// Identité VoiceBank : vert « forêt » institutionnel, accent laiton, neutres légèrement verdis.
module.exports = {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        foret: {
          50: "#EEF5F2", 100: "#D5E7E0", 200: "#A9CFC0", 300: "#77B19A", 400: "#4A9277",
          500: "#2C7A5E", 600: "#1F654D", 700: "#185141", 800: "#12433A", 900: "#0E332D", 950: "#0A2420",
        },
        laiton: { 200: "#F0E1B0", 300: "#E2C877", 400: "#C9A13B", 500: "#A9852A", 600: "#86691F" },
        gray: {
          50: "#F4F6F5", 100: "#E9EDEB", 200: "#D7DDDA", 300: "#B8C1BD", 400: "#8F9A95", 500: "#6B7671",
          600: "#505A56", 700: "#37403C", 750: "#2D3532", 800: "#232B28", 900: "#18201D", 950: "#101715",
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
