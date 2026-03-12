const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"]);

const MULTI_PART_PUBLIC_SUFFIXES = new Set([
  "ac.uk",
  "co.jp",
  "co.nz",
  "co.uk",
  "com.au",
  "com.br",
  "com.mx",
  "gov.uk",
  "net.au",
  "org.au",
  "org.uk",
]);

function isApexHostname(hostname: string): boolean {
  const labels = hostname.split(".").filter(Boolean);
  if (labels.length < 2) return false;
  if (labels.length === 2) return true;
  return MULTI_PART_PUBLIC_SUFFIXES.has(labels.slice(-2).join(".")) && labels.length === 3;
}

export function resolveShopHostedOrigin(rawOrigin?: string | null): string | null {
  if (!rawOrigin) return null;

  let url: URL;
  try {
    url = new URL(rawOrigin);
  } catch {
    return null;
  }

  const hostname = url.hostname.trim().toLowerCase();
  if (!hostname) return null;
  if (LOCAL_HOSTNAMES.has(hostname) || hostname.startsWith("shop.")) {
    return url.origin;
  }

  const canonicalHostname = hostname.startsWith("www.") ? hostname.slice(4) : hostname;
  if (!isApexHostname(canonicalHostname)) {
    return url.origin;
  }

  url.hostname = `shop.${canonicalHostname}`;
  return url.origin;
}

export function resolveShopHostedUrl(path?: string | null, rawOrigin?: string | null): string | null {
  const cleanedPath = (path || "").trim();
  if (!cleanedPath) return null;
  if (/^https?:\/\//i.test(cleanedPath)) return cleanedPath;

  const origin = resolveShopHostedOrigin(rawOrigin);
  if (!origin || !cleanedPath.startsWith("/")) return null;
  return new URL(cleanedPath, origin).toString();
}

export function resolveWindowShopHostedOrigin(): string | null {
  if (typeof window === "undefined" || !window.location?.origin) return null;
  return resolveShopHostedOrigin(window.location.origin);
}
