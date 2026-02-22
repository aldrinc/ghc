const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";

type AssetRef = {
  src?: string;
  assetPublicId?: string;
};

function normalizeFallbackAssetSrc(fallback?: string): string | undefined {
  if (!fallback) return fallback;
  const trimmedFallback = fallback.trim();
  if (!trimmedFallback) return undefined;
  if (/^https?:\/\//i.test(trimmedFallback)) return trimmedFallback;

  // Legacy funnel payloads may store root-relative public asset paths.
  // In deployed artifact mode, assets are served from /api/public/assets.
  if (trimmedFallback.startsWith("/public/assets/")) {
    return `${apiBaseUrl.replace(/\/+$/, "")}${trimmedFallback}`;
  }
  if (trimmedFallback.startsWith("public/assets/")) {
    return `${apiBaseUrl.replace(/\/+$/, "")}/${trimmedFallback}`;
  }
  return trimmedFallback;
}

export function resolveAssetSrc(assetPublicId?: string, fallback?: string): string | undefined {
  if (assetPublicId) return `${apiBaseUrl}/public/assets/${assetPublicId}`;
  return normalizeFallbackAssetSrc(fallback);
}

export function resolveImageSrc(image?: AssetRef | null): string | undefined {
  if (!image) return undefined;
  return resolveAssetSrc(image.assetPublicId, image.src);
}
