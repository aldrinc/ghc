const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";

type AssetRef = {
  src?: string;
  assetPublicId?: string;
};

export function resolveAssetSrc(assetPublicId?: string, fallback?: string): string | undefined {
  if (assetPublicId) return `${apiBaseUrl}/public/assets/${assetPublicId}`;
  return fallback;
}

export function resolveImageSrc(image?: AssetRef | null): string | undefined {
  if (!image) return undefined;
  return resolveAssetSrc(image.assetPublicId, image.src);
}
