import type { DesignSystemTokens } from "@/types/designSystems";
import { normalizeImportedHeadAssets } from "@/components/imported-site/importedRuntime";

type ImportedThemePayload = {
  palette?: Record<string, unknown>;
  fonts?: Record<string, unknown>;
  cta?: Record<string, unknown>;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function parseImportedTheme(theme: unknown, themeJson?: string): ImportedThemePayload | null {
  if (isRecord(theme)) {
    return theme as ImportedThemePayload;
  }
  if (typeof themeJson === "string" && themeJson.trim()) {
    try {
      const parsed = JSON.parse(themeJson);
      return isRecord(parsed) ? (parsed as ImportedThemePayload) : null;
    } catch {
      return null;
    }
  }
  return null;
}

function pickColor(
  palette: Record<string, unknown> | undefined,
  ...keys: string[]
): string | undefined {
  for (const key of keys) {
    const value = asString(palette?.[key]);
    if (value) {
      return value;
    }
  }
  return undefined;
}

function pickFont(
  fonts: Record<string, unknown> | undefined,
  ...keys: string[]
): string | undefined {
  for (const key of keys) {
    const value = asString(fonts?.[key]);
    if (value) {
      return value;
    }
  }
  return undefined;
}

function isFontStylesheetHref(href: string): boolean {
  return /fontshare|fonts\.googleapis|fonts\.gstatic|use\.typekit|fonts\.adobe/i.test(href);
}

function resolveBorderColor(baseColor: string | undefined): string | undefined {
  if (!baseColor) {
    return undefined;
  }
  return `color-mix(in srgb, ${baseColor} 14%, transparent)`;
}

function resolveMutedTextColor(baseColor: string | undefined): string | undefined {
  if (!baseColor) {
    return undefined;
  }
  return `color-mix(in srgb, ${baseColor} 68%, transparent)`;
}

function mixWithWhite(baseColor: string | undefined, weight: number): string | undefined {
  if (!baseColor) {
    return undefined;
  }
  const safeWeight = Math.min(100, Math.max(0, Math.round(weight)));
  return `color-mix(in srgb, ${baseColor} ${safeWeight}%, white)`;
}

export function buildImportedDesignSystemTokens({
  theme,
  themeJson,
  headAssets,
  brandName,
}: {
  theme?: unknown;
  themeJson?: string;
  headAssets?: unknown;
  brandName?: string | null;
}): DesignSystemTokens | null {
  const parsedTheme = parseImportedTheme(theme, themeJson);
  if (!parsedTheme) {
    return null;
  }

  const palette = isRecord(parsedTheme.palette) ? parsedTheme.palette : undefined;
  const fonts = isRecord(parsedTheme.fonts) ? parsedTheme.fonts : undefined;
  const cta = isRecord(parsedTheme.cta) ? parsedTheme.cta : undefined;
  const normalizedHeadAssets = normalizeImportedHeadAssets(headAssets);

  const headingFont = pickFont(fonts, "heading", "body");
  const bodyFont = pickFont(fonts, "body", "heading");
  const brandColor = pickColor(palette, "secondary", "primary");
  const primaryColor = pickColor(palette, "primary", "secondary");
  const backgroundColor = pickColor(palette, "background", "surface");
  const surfaceColor = pickColor(palette, "surface", "background");
  const textColor = pickColor(palette, "text", "secondary");
  const radiusFull = asString(cta?.borderRadius);
  const fontUrls = normalizedHeadAssets.stylesheetHrefs.filter(isFontStylesheetHref);

  const cssVars: Record<string, string> = {};
  if (headingFont) cssVars["--font-heading"] = headingFont;
  if (bodyFont) {
    cssVars["--font-sans"] = bodyFont;
    cssVars["--font-body"] = bodyFont;
  }
  if (brandColor) {
    cssVars["--color-brand"] = brandColor;
    cssVars["--color-heading"] = brandColor;
  }
  if (primaryColor) {
    cssVars["--color-cta"] = primaryColor;
    cssVars["--pdp-cta-bg"] = primaryColor;
  }
  if (backgroundColor) {
    // Imported one-product pages often use a tinted section background on the home page.
    // Do not promote that directly into the generic account/cart/checkout page canvas.
    cssVars["--color-page-bg"] = backgroundColor;
    cssVars["--b2c-shell-bg"] = mixWithWhite(backgroundColor, 88) || backgroundColor;
    cssVars["--b2c-footer-bg"] = mixWithWhite(backgroundColor, 88) || backgroundColor;
    cssVars["--b2c-panel-muted-bg"] =
      mixWithWhite(backgroundColor, 72) || backgroundColor;
  }
  if (surfaceColor) {
    cssVars["--color-page-bg-secondary"] = surfaceColor;
    cssVars["--hero-bg"] = surfaceColor;
  }
  cssVars["--b2c-page-canvas-bg"] = "#ffffff";
  cssVars["--b2c-panel-bg"] = surfaceColor || "#ffffff";
  cssVars["--b2c-field-bg"] = "#ffffff";
  if (textColor) {
    cssVars["--color-text"] = textColor;
    cssVars["--color-text-muted"] = resolveMutedTextColor(textColor) || textColor;
    cssVars["--color-muted"] = resolveMutedTextColor(textColor) || textColor;
  }
  if (brandColor || textColor) {
    const borderColor = resolveBorderColor(brandColor || textColor);
    if (borderColor) {
      cssVars["--color-border"] = borderColor;
    }
  }
  if (primaryColor) {
    cssVars["--color-cta-text"] = "#ffffff";
    cssVars["--color-cta-icon"] = brandColor || primaryColor;
  }
  if (radiusFull) {
    cssVars["--radius-full"] = radiusFull;
    cssVars["--pdp-radius-pill"] = radiusFull;
  }

  if (!Object.keys(cssVars).length && !fontUrls.length && !brandName?.trim()) {
    return null;
  }

  return {
    dataTheme: "light",
    fontUrls,
    cssVars,
    brand: brandName?.trim()
      ? {
          name: brandName.trim(),
        }
      : undefined,
  };
}
