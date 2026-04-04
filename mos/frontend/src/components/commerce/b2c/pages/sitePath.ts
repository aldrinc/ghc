import { parseSitePath } from "@/funnels/runtimeRouting";

type B2CRuntimePathContext = {
  productSlug?: string | null;
  funnelSlug?: string | null;
};

function stripKnownBasePath(pathname: string, basePath: string): string | null {
  if (!basePath) {
    return null;
  }
  if (pathname === basePath) {
    return "";
  }
  if (pathname.startsWith(`${basePath}/`)) {
    return pathname.slice(basePath.length + 1);
  }
  return null;
}

export function extractB2CSitePath(
  pathname: string,
  runtime: B2CRuntimePathContext | null | undefined,
): string {
  const normalizedPathname = (pathname || "").trim();
  const previewMatch = normalizedPathname.match(/^\/workspaces\/sites\/[^/]+\/preview(?:\/(.*))?$/);
  if (previewMatch) {
    return previewMatch[1] || "";
  }

  const productSlug = (runtime?.productSlug || "").trim();
  const funnelSlug = (runtime?.funnelSlug || "").trim();

  if (productSlug && funnelSlug) {
    const hostedPath = stripKnownBasePath(normalizedPathname, `/f/${productSlug}/${funnelSlug}`);
    if (hostedPath !== null) {
      return hostedPath;
    }

    const bundlePath = stripKnownBasePath(normalizedPathname, `/${productSlug}/${funnelSlug}`);
    if (bundlePath !== null) {
      return bundlePath;
    }
  }

  return normalizedPathname.replace(/^\/+/, "");
}

export function resolveB2CSitePath(
  pathname: string,
  runtime: B2CRuntimePathContext | null | undefined,
) {
  return parseSitePath(extractB2CSitePath(pathname, runtime));
}
