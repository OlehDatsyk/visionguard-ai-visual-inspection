/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#0a111d", 900: "#0d1524", 850: "#111a2b", 800: "#162136", 700: "#1e2c45", 600: "#2a3a57" },
        text: { 1: "#e8edf4", 2: "#a9b5c6", 3: "#7c8aa0" },
        accent: { DEFAULT: "#3cc6dd", strong: "#7fdcec", dim: "#123b4a" },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "-apple-system", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "Cascadia Mono", "Consolas", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
