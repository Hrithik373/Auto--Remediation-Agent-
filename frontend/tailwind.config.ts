import type { Config } from "tailwindcss";

// SRE console aesthetic (FRONTEND_BLUEPRINT.md §8): dense, dark, information-first. Decision colors
// live in src/lib/decisionColors.ts as the single source of truth -- CLAUDE.md's frontend addendum
// forbids hardcoding allow/block colors anywhere else, including here; this palette only supplies the
// neutrals + one accent + the four decision hues those tokens are built from.
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        console: {
          bg: "#0B0F14",
          surface: "#11161D",
          "surface-2": "#171D26",
          border: "#232B36",
          text: "#E4E9EE",
          "text-muted": "#8A97A6",
        },
        accent: {
          DEFAULT: "#22D3EE",
          soft: "#0E2E36",
        },
        decision: {
          allow: "#34D399",
          "allow-soft": "#0F2A22",
          block: "#F87171",
          "block-soft": "#2E1416",
          revise: "#FBBF24",
          "revise-soft": "#2E2410",
          escalate: "#A78BFA",
          "escalate-soft": "#221A33",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["\"JetBrains Mono\"", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      keyframes: {
        "pulse-ring": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(-2px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 1.4s ease-in-out infinite",
        "fade-in": "fade-in 0.2s ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
