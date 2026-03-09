const DEFAULT_LOCAL_API_BASE_URL = "http://localhost:8008";
const LOOPBACK_HOSTNAMES = new Set(["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"]);

function trimTrailingSlashes(value: string): string {
  return value.replace(/\/+$/, "");
}

function isLoopbackHostname(value: string): boolean {
  return LOOPBACK_HOSTNAMES.has(value.trim().toLowerCase());
}

export function resolveApiBaseUrl(
  configuredBaseUrl?: string | null,
  fallbackBaseUrl: string = DEFAULT_LOCAL_API_BASE_URL,
): string {
  const trimmedConfiguredBaseUrl = typeof configuredBaseUrl === "string" ? configuredBaseUrl.trim() : "";
  const baseUrl = trimTrailingSlashes(trimmedConfiguredBaseUrl || fallbackBaseUrl);
  if (!baseUrl) {
    return baseUrl;
  }

  if (typeof window === "undefined" || window.location.protocol !== "http:") {
    return baseUrl;
  }

  try {
    const currentUrl = new URL(window.location.href);
    const resolvedUrl = new URL(baseUrl, currentUrl.origin);
    if (!isLoopbackHostname(currentUrl.hostname) && isLoopbackHostname(resolvedUrl.hostname)) {
      resolvedUrl.hostname = currentUrl.hostname;
    }
    return trimTrailingSlashes(resolvedUrl.toString());
  } catch {
    return baseUrl;
  }
}

export function resolveRequiredApiBaseUrl(): string {
  return resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL);
}

export function resolveOptionalApiBaseUrl(): string | undefined {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL;
  if (typeof configuredBaseUrl !== "string" || !configuredBaseUrl.trim()) {
    return undefined;
  }
  return resolveApiBaseUrl(configuredBaseUrl);
}
