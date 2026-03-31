import { useMemo, type CSSProperties } from "react";

import { useDesignSystemTokens } from "@/components/design-system/DesignSystemProvider";
import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";

type DesignSystemLike = {
  brand?: Record<string, unknown>;
  cssVars?: Record<string, string | number>;
};

export interface B2CThemeTokens {
  brandName?: string;
  logoUrl?: string;
  logoUrlDark?: string;
  fontHeading?: string;
  fontBody?: string;
  colorBackground?: string;
  colorBackgroundAlt?: string;
  colorText?: string;
  colorTextMuted?: string;
  colorTextInverse?: string;
  colorBorder?: string;
  colorPrimary?: string;
  colorPrimaryText?: string;
  colorPrimaryHover?: string;
  radiusSmall?: string;
  radiusMedium?: string;
  radiusLarge?: string;
  radiusFull?: string;
}

export interface B2CTheme {
  tokens: B2CThemeTokens;
  isThemed: boolean;
  hasTokens: boolean;
}

export const B2C_STANDALONE_BODY_FONT =
  'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
export const B2C_STANDALONE_HEADING_FONT = B2C_STANDALONE_BODY_FONT;
export const B2C_STANDALONE_ACTION_RADIUS = "8px";
export const B2C_STANDALONE_SURFACE_RADIUS = "12px";

export function resolveB2CBodyFont(tokens: Pick<B2CThemeTokens, "fontBody">): string {
  return tokens.fontBody || B2C_STANDALONE_BODY_FONT;
}

export function resolveB2CHeadingFont(
  tokens: Pick<B2CThemeTokens, "fontHeading" | "fontBody">,
): string {
  return tokens.fontHeading || tokens.fontBody || B2C_STANDALONE_HEADING_FONT;
}

export function resolveB2CActionRadius(
  tokens: Pick<B2CThemeTokens, "radiusMedium" | "radiusLarge">,
): string {
  return tokens.radiusMedium || tokens.radiusLarge || B2C_STANDALONE_ACTION_RADIUS;
}

export function resolveB2CSurfaceRadius(
  tokens: Pick<B2CThemeTokens, "radiusLarge" | "radiusMedium">,
): string {
  return tokens.radiusLarge || tokens.radiusMedium || B2C_STANDALONE_SURFACE_RADIUS;
}

export function resolveB2CPillRadius(
  tokens: Pick<B2CThemeTokens, "radiusFull" | "radiusMedium" | "radiusLarge">,
): string {
  return tokens.radiusFull || resolveB2CActionRadius(tokens);
}

const apiBaseUrl = resolveRequiredApiBaseUrl();

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function buildPublicAssetUrl(publicId: unknown): string | undefined {
  const id = asString(publicId);
  return id ? `${apiBaseUrl}/public/assets/${id}` : undefined;
}

function extractThemeTokens(rawTokens: unknown): B2CThemeTokens {
  if (!isRecord(rawTokens)) return {};

  const tokens = rawTokens as DesignSystemLike;
  const brand = isRecord(tokens.brand) ? tokens.brand : {};
  const cssVars = isRecord(tokens.cssVars) ? tokens.cssVars : rawTokens;

  return {
    brandName: asString(brand.name),
    logoUrl: buildPublicAssetUrl(brand.logoAssetPublicId),
    logoUrlDark: buildPublicAssetUrl(brand.logoOnDarkAssetPublicId),
    fontHeading: asString(cssVars["--font-heading"]),
    fontBody: asString(cssVars["--font-sans"] ?? cssVars["--font-body"]),
    colorBackground: asString(cssVars["--color-bg"]),
    colorBackgroundAlt: asString(
      cssVars["--color-page-bg-secondary"] ?? cssVars["--color-page-bg"] ?? cssVars["--hero-bg"],
    ),
    colorText: asString(cssVars["--color-text"]),
    colorTextMuted: asString(cssVars["--color-muted"] ?? cssVars["--color-text-muted"]),
    colorTextInverse: asString(cssVars["--color-cta-text"]),
    colorBorder: asString(cssVars["--color-border"]),
    colorPrimary: asString(cssVars["--color-cta"] ?? cssVars["--pdp-cta-bg"] ?? cssVars["--color-brand"]),
    colorPrimaryText: asString(cssVars["--color-cta-text"]),
    colorPrimaryHover: asString(cssVars["--color-cta-icon"] ?? cssVars["--color-brand"]),
    radiusSmall: asString(cssVars["--radius-sm"]),
    radiusMedium: asString(cssVars["--radius-md"]),
    radiusLarge: asString(cssVars["--radius-lg"]),
    radiusFull: asString(cssVars["--radius-full"] ?? cssVars["--pdp-radius-pill"]),
  };
}

export function useB2CTheme(): B2CTheme {
  const designSystemTokens = useDesignSystemTokens();

  return useMemo(() => {
    const tokens = extractThemeTokens(designSystemTokens);
    const hasTokens = Object.values(tokens).some(Boolean);
    const isThemed = Boolean(
      tokens.brandName ||
        tokens.logoUrl ||
        tokens.fontHeading ||
        tokens.fontBody ||
        tokens.colorPrimary ||
        tokens.colorBackground,
    );

    return {
      tokens,
      isThemed,
      hasTokens,
    };
  }, [designSystemTokens]);
}

export function useB2CThemeStyles(): CSSProperties | undefined {
  const { tokens, isThemed } = useB2CTheme();

  return useMemo(() => {
    if (!isThemed) return undefined;

    const styles: CSSProperties = {};
    if (tokens.fontBody) styles.fontFamily = tokens.fontBody;
    if (tokens.colorBackground) styles.backgroundColor = tokens.colorBackground;
    if (tokens.colorText) styles.color = tokens.colorText;

    return Object.keys(styles).length ? styles : undefined;
  }, [isThemed, tokens]);
}

export function useB2CHeaderTheme(): {
  style: CSSProperties | undefined;
  logo: { src?: string; alt?: string } | null;
  isThemed: boolean;
} {
  const { tokens, isThemed } = useB2CTheme();

  return useMemo(() => {
    const style: CSSProperties = {};
    if (tokens.colorBackground) style.backgroundColor = tokens.colorBackground;
    if (tokens.colorBorder) style.borderBottomColor = tokens.colorBorder;

    const logo = tokens.logoUrl
      ? {
          src: tokens.logoUrl,
          alt: tokens.brandName || "Store",
        }
      : null;

    return {
      style: Object.keys(style).length ? style : undefined,
      logo,
      isThemed,
    };
  }, [isThemed, tokens]);
}

export function useB2CCTATheme(): {
  style: CSSProperties | undefined;
  hoverStyle: CSSProperties | undefined;
  isThemed: boolean;
} {
  const { tokens, isThemed } = useB2CTheme();

  return useMemo(() => {
    const style: CSSProperties = {};
    const hoverStyle: CSSProperties = {};

    if (tokens.colorPrimary) {
      style.backgroundColor = tokens.colorPrimary;
      style.borderColor = tokens.colorPrimary;
    }
    if (tokens.colorPrimaryText) style.color = tokens.colorPrimaryText;
    if (tokens.colorPrimaryHover) {
      hoverStyle.backgroundColor = tokens.colorPrimaryHover;
      hoverStyle.borderColor = tokens.colorPrimaryHover;
    }
    style.borderRadius = resolveB2CPillRadius(tokens);

    return {
      style: Object.keys(style).length ? style : undefined,
      hoverStyle: Object.keys(hoverStyle).length ? hoverStyle : undefined,
      isThemed,
    };
  }, [isThemed, tokens]);
}

export default useB2CTheme;
