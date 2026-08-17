import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          blue: "#3b82f6",
          "blue-light": "#60a5fa",
          "blue-dark": "#1d4ed8",
          cyan: "#06b6d4",
          gradient: "linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%)",
        },
        surface: {
          dark: "#0f172a",
          "dark-lighter": "#1e293b",
          sidebar: "#1e293b",
          code: "#1e293b",
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      animation: {
        "pulse-soft": "pulse-soft 2s ease-in-out infinite",
        "spin-slow": "spin 3s linear infinite",
        shimmer: "shimmer 2s linear infinite",
        "loader-bar": "loader-bar 2.5s ease-in-out forwards",
        "loader-fade-up": "loader-fade-up 0.6s ease-out forwards",
        "loader-letter": "loader-letter 0.5s ease-out forwards",
        "float": "float 6s ease-in-out infinite",
        "float-delayed": "float 6s ease-in-out infinite 1.5s",
        "glow-pulse": "glow-pulse 3s ease-in-out infinite",
        "shimmer-btn": "shimmer-btn 3s ease-in-out infinite",
        "blob": "blob 12s ease-in-out infinite",
        "message-in": "message-in 0.4s ease-out forwards",
        "block-in": "block-in 0.35s ease-out forwards",
        "thinking-dot": "thinking-dot 1.4s ease-in-out infinite both",
        "hero-title": "hero-title 4s ease-in-out infinite",
        "fade-in-up": "fade-in-up 0.6s ease-out 0.2s both",
        "bounce-soft": "bounce-soft 2s ease-in-out infinite",
        "modal-in": "modal-in 0.25s ease-out forwards",
        "sparkle-float": "sparkle-float 4s ease-in-out infinite",
        "dot-drift": "dot-drift 8s ease-in-out infinite",
        "backdrop-in": "backdrop-in 0.2s ease-out forwards",
        "bounce-in": "bounce-in 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) forwards",
        "logo-bounce": "logo-bounce 0.8s cubic-bezier(0.34, 1.56, 0.64, 1) forwards",
        "step-in": "step-in 0.4s ease-out forwards",
        "check-in": "check-in 0.3s ease-out forwards",
        "scan-line": "scan-line 2s linear infinite",
      },
      keyframes: {
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "loader-bar": {
          "0%": { transform: "scaleX(0)", transformOrigin: "left" },
          "40%": { transform: "scaleX(1)", transformOrigin: "left" },
          "60%": { transform: "scaleX(1)", transformOrigin: "right" },
          "100%": { transform: "scaleX(0)", transformOrigin: "right" },
        },
        "loader-fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "loader-letter": {
          "0%": { opacity: "0", transform: "translateY(100%)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0) translateX(0)" },
          "33%": { transform: "translateY(-12px) translateX(6px)" },
          "66%": { transform: "translateY(-6px) translateX(-4px)" },
        },
        "glow-pulse": {
          "0%, 100%": { opacity: "0.4", filter: "blur(40px)" },
          "50%": { opacity: "0.7", filter: "blur(50px)" },
        },
        "shimmer-btn": {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        blob: {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "25%": { transform: "translate(10%, -15%) scale(1.05)" },
          "50%": { transform: "translate(-10%, 10%) scale(0.95)" },
          "75%": { transform: "translate(-5%, -5%) scale(1.02)" },
        },
        "message-in": {
          "0%": { opacity: "0", transform: "translateY(8px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "block-in": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "thinking-dot": {
          "0%, 80%, 100%": { opacity: "0.3", transform: "scale(0.8)" },
          "40%": { opacity: "1", transform: "scale(1)" },
        },
        "hero-title": {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.03)" },
        },
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "bounce-soft": {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-4px)" },
        },
        "modal-in": {
          "0%": { opacity: "0", transform: "scale(0.94)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "sparkle-float": {
          "0%, 100%": { opacity: "0.6", transform: "translate(0, 0) scale(1)" },
          "33%": { opacity: "1", transform: "translate(3px, -6px) scale(1.05)" },
          "66%": { opacity: "0.8", transform: "translate(-2px, -3px) scale(0.98)" },
        },
        "dot-drift": {
          "0%, 100%": { transform: "translate(0, 0)", opacity: "0.4" },
          "50%": { transform: "translate(10px, -15px)", opacity: "0.8" },
        },
        "backdrop-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "bounce-in": {
          "0%": { opacity: "0", transform: "translateY(40px) scale(0.8)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "logo-bounce": {
          "0%": { opacity: "0", transform: "translateY(60px) scale(0.6)" },
          "50%": { transform: "translateY(-8px) scale(1.05)" },
          "70%": { transform: "translateY(4px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "step-in": {
          "0%": { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "check-in": {
          "0%": { opacity: "0", transform: "scale(0)" },
          "50%": { transform: "scale(1.2)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        "scan-line": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
      },
      animationDelay: {
        "100": "100ms",
        "200": "200ms",
        "300": "300ms",
      },
      backgroundSize: {
        "300%": "300%",
      },
    },
  },
  plugins: [],
};

export default config;
