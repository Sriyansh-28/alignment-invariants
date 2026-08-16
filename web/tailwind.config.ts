import type { Config } from "tailwindcss";

// Deliberately restrained: this is a research tool, not a landing page.
// Serif headings, a single accent colour, no animation utilities in use.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ["Georgia", "Cambria", "Times New Roman", "serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        ink: {
          DEFAULT: "#1a1a1a",
          muted: "#5c5c5c",
          faint: "#8a8a8a",
        },
        rule: "#d8d4cc",
        paper: "#faf9f6",
        accent: "#2f5d8a",
        warn: "#8a5a2f",
        bad: "#9b3d3d",
        good: "#3d6b4a",
      },
    },
  },
  plugins: [],
};

export default config;
