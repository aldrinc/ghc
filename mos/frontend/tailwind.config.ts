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
      screens: {
        "2xsmall": "320px",
        xsmall: "512px",
        small: "1024px",
        medium: "1280px",
        large: "1440px",
        xlarge: "1680px",
        "2xlarge": "1920px",
      },
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
        "danger-bg": tokenColor("--danger-bg"),
        success: tokenColor("--success"),
        "success-bg": tokenColor("--success-bg"),
        warning: tokenColor("--warning"),
        "warning-bg": tokenColor("--warning-bg"),
        info: tokenColor("--info"),
        "info-bg": tokenColor("--info-bg"),
        overlay: tokenColor("--overlay"),
        "shadow-color": tokenColor("--shadow-color"),
        focus: tokenColor("--focus-outline"),
        ink: {
          DEFAULT: tokenColor("--ink"),
          soft: tokenColor("--ink-soft"),
          muted: tokenColor("--ink-muted"),
        },
        blue: {
          50: tokenColor("--blue-50"),
          100: tokenColor("--blue-100"),
          200: tokenColor("--blue-200"),
          300: tokenColor("--blue-300"),
          400: tokenColor("--blue-400"),
          500: tokenColor("--blue-500"),
          600: tokenColor("--blue-600"),
          700: tokenColor("--blue-700"),
          800: tokenColor("--blue-800"),
          900: tokenColor("--blue-900"),
          950: tokenColor("--blue-950"),
        },
        slate: {
          50: tokenColor("--slate-50"),
          100: tokenColor("--slate-100"),
          200: tokenColor("--slate-200"),
          300: tokenColor("--slate-300"),
          400: tokenColor("--slate-400"),
          500: tokenColor("--slate-500"),
          600: tokenColor("--slate-600"),
          700: tokenColor("--slate-700"),
          800: tokenColor("--slate-800"),
          900: tokenColor("--slate-900"),
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        serif: ["var(--font-serif)"],
        display: ["var(--font-display)"],
        mono: ["var(--font-mono)"],
      },
      fontSize: {
        "2xs": ["var(--text-2xs)", { lineHeight: "var(--leading-tight)" }],
        xs: ["var(--text-xs)", { lineHeight: "var(--leading-tight)" }],
        sm: ["var(--text-sm)", { lineHeight: "var(--leading-tight)" }],
        md: ["var(--text-md)", { lineHeight: "var(--leading-normal)" }],
        base: ["var(--text-base)", { lineHeight: "var(--leading-normal)" }],
        lg: ["var(--text-lg)", { lineHeight: "var(--leading-normal)" }],
        xl: ["var(--text-xl)", { lineHeight: "var(--leading-tight)" }],
        "2xl": ["var(--text-2xl)", { lineHeight: "var(--leading-tight)" }],
        "3xl": ["var(--text-3xl)", { lineHeight: "var(--leading-display)" }],
        "4xl": ["var(--text-4xl)", { lineHeight: "var(--leading-display)" }],
        "5xl": ["var(--text-5xl)", { lineHeight: "var(--leading-display)" }],
        "6xl": ["var(--text-6xl)", { lineHeight: "var(--leading-display)" }],
        "7xl": ["var(--text-7xl)", { lineHeight: "var(--leading-display)" }],
      },
      lineHeight: {
        tight: "var(--leading-tight)",
        snug: "var(--lh-snug)",
        normal: "var(--leading-normal)",
        relaxed: "var(--lh-relaxed)",
        loose: "var(--lh-loose)",
        display: "var(--leading-display)",
      },
      letterSpacing: {
        tight: "var(--tracking-tight)",
        tighter: "var(--tracking-tighter)",
        normal: "var(--tracking-normal)",
        wide: "var(--tracking-wide)",
        caps: "var(--tracking-caps)",
        display: "var(--tracking-display)",
      },
      borderRadius: {
        DEFAULT: "var(--radius-md)",
        xs: "var(--radius-xs)",
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        "2xl": "var(--radius-2xl)",
        "3xl": "var(--radius-2xl)",
        pill: "var(--radius-pill)",
        panel: "var(--radius-panel)",
        card: "var(--radius-card)",
        hero: "var(--radius-hero)",
        prompt: "var(--radius-prompt)",
      },
      boxShadow: {
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        xl: "var(--shadow-xl)",
        blue: "var(--shadow-blue)",
        "blue-lg": "var(--shadow-blue-lg)",
        ink: "var(--shadow-ink)",
      },
      spacing: {
        1: "var(--space-1)",
        2: "var(--space-2)",
        3: "var(--space-3)",
        4: "var(--space-4)",
        5: "var(--space-5)",
        6: "var(--space-6)",
        7: "var(--space-7)",
        8: "var(--space-8)",
        9: "var(--space-9)",
        10: "var(--space-10)",
        11: "var(--space-11)",
        12: "var(--space-12)",
        13: "var(--space-13)",
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
