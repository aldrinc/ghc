import type { DesignSystemTokens } from "@/types/designSystems";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function withDesignSystemBrandLogo<
  T extends {
    alt?: string;
    src?: string;
    assetPublicId?: string;
    referenceAssetPublicId?: string;
  },
>(tokens: DesignSystemTokens | Record<string, unknown> | null | undefined, fallback: T): T {
  if (!isRecord(tokens)) return fallback;
  const brand = tokens.brand;
  if (!isRecord(brand)) return fallback;

  const logoAssetPublicId =
    typeof brand.logoAssetPublicId === "string" && brand.logoAssetPublicId.trim()
      ? brand.logoAssetPublicId.trim()
      : null;
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
