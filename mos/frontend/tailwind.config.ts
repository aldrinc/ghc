import type { Config } from "tailwindcss";

function tokenColor(cssVar: string) {
  return ({ opacityValue }: { opacityValue?: string } = {}) => {
    // Tailwind will usually pass a CSS variable expression like `var(--tw-bg-opacity, 1)`
    // (or a literal like `0.5` for `/50` modifiers). We normalize this to a percentage
    // for `color-mix(...)`.
    if (opacityValue === undefined) return `var(${cssVar})`;
    return `color-mix(in srgb, var(${cssVar}) calc(${opacityValue} * 100%), transparent)`;
  };
}

const config: Config = {
  // Dark mode is opt-in via `data-theme="dark"` on an ancestor (we set it on <html>).
  // We intentionally avoid `media` so system dark mode doesn't unexpectedly flip
  // the UI without user intent.
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: tokenColor("--background"),
        foreground: tokenColor("--foreground"),
        canvas: tokenColor("--bg"),
        surface: tokenColor("--surface"),
        "surface-2": tokenColor("--surface-2"),
        "surface-hover": tokenColor("--surface-hover"),
        border: tokenColor("--border"),
        "border-strong": tokenColor("--border-strong"),
        divider: tokenColor("--divider"),
        muted: {
          DEFAULT: tokenColor("--muted"),
          foreground: tokenColor("--muted-foreground"),
        },
        card: {
          DEFAULT: tokenColor("--card"),
          foreground: tokenColor("--card-foreground"),
        },
        popover: {
          DEFAULT: tokenColor("--popover"),
          foreground: tokenColor("--popover-foreground"),
        },
        primary: {
          DEFAULT: tokenColor("--primary"),
          foreground: tokenColor("--primary-foreground"),
        },
        secondary: {
          DEFAULT: tokenColor("--secondary"),
          foreground: tokenColor("--secondary-foreground"),
        },
        accent: {
          DEFAULT: tokenColor("--accent"),
          hover: tokenColor("--accent-hover"),
          active: tokenColor("--accent-active"),
          foreground: tokenColor("--accent-contrast"),
        },
        selection: {
          DEFAULT: tokenColor("--selection"),
          foreground: tokenColor("--selection-foreground"),
        },
        hover: tokenColor("--hover"),
        active: tokenColor("--active"),
        disabled: {
          DEFAULT: tokenColor("--disabled"),
          foreground: tokenColor("--disabled-foreground"),
        },
        input: {
          DEFAULT: tokenColor("--input"),
          border: tokenColor("--input-border"),
          "border-focus": tokenColor("--input-border-focus"),
        },
        sidebar: {
          DEFAULT: tokenColor("--sidebar"),
          foreground: tokenColor("--sidebar-foreground"),
          accent: tokenColor("--sidebar-accent"),
          "accent-foreground": tokenColor("--sidebar-accent-foreground"),
          border: tokenColor("--sidebar-border"),
          primary: tokenColor("--sidebar-primary"),
          "primary-foreground": tokenColor("--sidebar-primary-foreground"),
          ring: tokenColor("--sidebar-ring"),
        },
        content: tokenColor("--text"),
        "content-muted": tokenColor("--text-muted"),
        "subtle-foreground": tokenColor("--subtle-foreground"),
        "accent-contrast": tokenColor("--accent-contrast"),
        danger: tokenColor("--danger"),
        success: tokenColor("--success"),
        warning: tokenColor("--warning"),
        overlay: tokenColor("--overlay"),
        "shadow-color": tokenColor("--shadow-color"),
        focus: tokenColor("--focus-outline"),
        manus: {
          ink: "#34322D",
          mist: "#F8F8F8",
          paper: "#FFFFFF",
          inkA: {
            5: "rgba(52, 50, 45, 0.05)",
            8: "rgba(52, 50, 45, 0.08)",
            12: "rgba(52, 50, 45, 0.12)",
            16: "rgba(52, 50, 45, 0.16)",
            20: "rgba(52, 50, 45, 0.2)",
            40: "rgba(52, 50, 45, 0.4)",
            60: "rgba(52, 50, 45, 0.6)",
            80: "rgba(52, 50, 45, 0.8)",
          },
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        serif: ["var(--font-serif)"],
        display: ["var(--font-display)"],
        mono: ["var(--font-mono)"],
      },
      fontSize: {
        xs: ["var(--text-xs)", { lineHeight: "var(--leading-tight)" }],
        sm: ["var(--text-sm)", { lineHeight: "var(--leading-tight)" }],
        base: ["var(--text-base)", { lineHeight: "var(--leading-normal)" }],
        lg: ["var(--text-lg)", { lineHeight: "var(--leading-normal)" }],
        xl: ["var(--text-xl)", { lineHeight: "var(--leading-tight)" }],
        "2xl": ["var(--text-2xl)", { lineHeight: "var(--leading-tight)" }],
      },
      lineHeight: {
        tight: "var(--leading-tight)",
        normal: "var(--leading-normal)",
        display: "var(--leading-display)",
      },
      letterSpacing: {
        display: "var(--tracking-display)",
      },
      borderRadius: {
        DEFAULT: "var(--radius-md)",
        xs: "var(--radius-sm)",
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-lg)",
        "2xl": "var(--radius-lg)",
        "3xl": "var(--radius-lg)",
        panel: "var(--radius-panel)",
        card: "var(--radius-card)",
        hero: "var(--radius-hero)",
        prompt: "var(--radius-prompt)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        "manus-sm": "0 2px 12px rgba(52, 50, 45, 0.08)",
        manus: "0 12px 40px rgba(52, 50, 45, 0.12)",
        "manus-lg": "0 20px 60px rgba(52, 50, 45, 0.14)",
      },
      spacing: {
        1: "var(--space-1)",
        2: "var(--space-2)",
        3: "var(--space-3)",
        4: "var(--space-4)",
        5: "var(--space-5)",
        6: "var(--space-6)",
      },
      zIndex: {
        dropdown: "var(--z-dropdown)",
        dialog: "var(--z-dialog)",
        toast: "var(--z-toast)",
      },
    },
  },
  plugins: [],
};

export default config;
