import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "hsl(var(--bg) / <alpha-value>)",
        surface: "hsl(var(--surface) / <alpha-value>)",
        "surface-hover": "hsl(var(--surface-hover) / <alpha-value>)",
        border: "hsl(var(--border) / <alpha-value>)",
        text: "hsl(var(--text) / <alpha-value>)",
        "text-muted": "hsl(var(--text-muted) / <alpha-value>)",
        status: {
          green: "hsl(var(--status-green) / <alpha-value>)",
          yellow: "hsl(var(--status-yellow) / <alpha-value>)",
          red: "hsl(var(--status-red) / <alpha-value>)",
          gray: "hsl(var(--status-gray) / <alpha-value>)",
        },
      },
      fontFamily: {
        mono: ["Menlo", "Consolas", "monospace"],
      },
      borderRadius: {
        DEFAULT: "6px",
      },
    },
  },
  plugins: [],
} satisfies Config;
