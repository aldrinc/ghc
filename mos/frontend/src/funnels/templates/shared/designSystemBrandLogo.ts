import type { DesignSystemTokens } from "@/types/designSystems";

export type DesignSystemBrandLogoVariant = "default" | "onDark";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function resolveDesignSystemBrandLogoVariant(
  rawVariant: unknown,
  defaultVariant: DesignSystemBrandLogoVariant = "default",
): DesignSystemBrandLogoVariant {
  if (rawVariant === undefined || rawVariant === null) return defaultVariant;
  if (rawVariant === "default" || rawVariant === "onDark") return rawVariant;
  throw new Error(`Unsupported logoVariant '${String(rawVariant)}'. Expected 'default' or 'onDark'.`);
}

export function withDesignSystemBrandLogo<
  T extends {
    alt?: string;
    src?: string;
    assetPublicId?: string;
    referenceAssetPublicId?: string;
  },
>(
  tokens: DesignSystemTokens | Record<string, unknown> | null | undefined,
  fallback: T,
  variant: DesignSystemBrandLogoVariant = "default",
): T {
  if (!isRecord(tokens)) return fallback;
  const brand = tokens.brand;
  if (!isRecord(brand)) return fallback;

  const primaryLogoAssetPublicId =
    typeof brand.logoAssetPublicId === "string" && brand.logoAssetPublicId.trim()
      ? brand.logoAssetPublicId.trim()
      : null;
  const darkLogoAssetPublicId =
    typeof brand.logoOnDarkAssetPublicId === "string" && brand.logoOnDarkAssetPublicId.trim()
      ? brand.logoOnDarkAssetPublicId.trim()
      : null;
  const logoAssetPublicId =
    variant === "onDark" ? darkLogoAssetPublicId ?? primaryLogoAssetPublicId : primaryLogoAssetPublicId;
  if (!logoAssetPublicId) return fallback;

  const logoAlt =
    typeof brand.logoAlt === "string" && brand.logoAlt.trim()
      ? brand.logoAlt.trim()
      : typeof brand.name === "string" && brand.name.trim()
        ? brand.name.trim()
        : fallback.alt;

  return {
    ...fallback,
    assetPublicId: logoAssetPublicId,
    referenceAssetPublicId: undefined,
    alt: logoAlt,
  };
}
