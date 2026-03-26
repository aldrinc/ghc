import { buildRuntimePageTypeMap } from "@/funnels/runtimePageMaps";
import { buildSitePath, parseSitePath } from "@/funnels/runtimeRouting";
import type { SitePage } from "@/api/sites";
import type { SitePageType } from "@/types/funnels";

const DEFAULT_SITE_COUNTRY_CODE = "us";

type SitePagePreviewOptions = {
  siteFamily?: string | null;
  countryCode?: string | null;
  productHandle?: string | null;
  collectionHandle?: string | null;
  categoryHandle?: string | null;
  orderId?: string | null;
  transferToken?: string | null;
};

function resolveSitePathPageType(routePath: string): SitePageType | null {
  const parsedSitePath = parseSitePath(routePath);
  const accountSection = parsedSitePath.handle;
  const orderAction = parsedSitePath.nestedPath[0];
  const orderTransferDecision = parsedSitePath.nestedPath[2];

  if (parsedSitePath.pageType === "store") return "store";
  if (parsedSitePath.pageType === "collections") return "collection";
  if (parsedSitePath.pageType === "categories") return "category";
  if (parsedSitePath.pageType === "products") return "product_detail";
  if (parsedSitePath.pageType === "cart") return "cart";
  if (parsedSitePath.pageType === "checkout") return "checkout";

  if (parsedSitePath.pageType === "account") {
    if (accountSection === "profile") return "account_profile";
    if (accountSection === "addresses") return "account_addresses";
    if (accountSection === "orders" && parsedSitePath.nestedPath[0] === "details") return "account_order_detail";
    if (accountSection === "orders") return "account_orders";
    return "account_dashboard";
  }

  if (parsedSitePath.pageType === "order") {
    if (orderAction === "confirmed") return "order_confirmed";
    if (orderAction === "transfer" && orderTransferDecision === "accept") return "order_transfer_accept";
    if (orderAction === "transfer" && orderTransferDecision === "decline") return "order_transfer_decline";
    if (orderAction === "transfer") return "order_transfer";
  }

  if (parsedSitePath.pageType === "home") return "home";
  if (!parsedSitePath.pageType || parsedSitePath.pageType === "home") return "home";

  return null;
}

export function buildSitePreviewPath(siteId: string, routePath?: string | null): string {
  const cleanedSiteId = (siteId || "").trim();
  if (!cleanedSiteId) {
    throw new Error("siteId is required to build a site preview path.");
  }

  const cleanedRoutePath = (routePath || "").trim().replace(/^\/+|\/+$/g, "");
  const basePath = `/workspaces/sites/${encodeURIComponent(cleanedSiteId)}/preview`;
  return cleanedRoutePath ? `${basePath}/${cleanedRoutePath}` : basePath;
}

export function buildSitePagePreviewPath(
  siteId: string,
  page: SitePage,
  options: SitePagePreviewOptions = {},
): string | null {
  if (options.siteFamily !== "medusa-b2c-starter") {
    return buildSitePreviewPath(siteId, page.slug);
  }

  const countryCode = (options.countryCode || DEFAULT_SITE_COUNTRY_CODE).trim().toLowerCase() || DEFAULT_SITE_COUNTRY_CODE;
  let routePath: string | null = null;

  switch (page.pageType) {
    case "home":
      routePath = buildSitePath({ countryCode });
      break;
    case "store":
      routePath = buildSitePath({ countryCode, pageType: "store" });
      break;
    case "collection":
      routePath = options.collectionHandle?.trim()
        ? buildSitePath({ countryCode, pageType: "collections", handle: options.collectionHandle.trim() })
        : null;
      break;
    case "category":
      routePath = options.categoryHandle?.trim()
        ? buildSitePath({ countryCode, pageType: "categories", handle: options.categoryHandle.trim() })
        : null;
      break;
    case "product_detail":
      routePath = options.productHandle?.trim()
        ? buildSitePath({ countryCode, pageType: "products", handle: options.productHandle.trim() })
        : null;
      break;
    case "cart":
      routePath = buildSitePath({ countryCode, pageType: "cart" });
      break;
    case "checkout":
      routePath = buildSitePath({ countryCode, pageType: "checkout" });
      break;
    case "account_dashboard":
      routePath = buildSitePath({ countryCode, pageType: "account" });
      break;
    case "account_profile":
      routePath = buildSitePath({ countryCode, pageType: "account", handle: "profile" });
      break;
    case "account_addresses":
      routePath = buildSitePath({ countryCode, pageType: "account", handle: "addresses" });
      break;
    case "account_orders":
      routePath = buildSitePath({ countryCode, pageType: "account", handle: "orders" });
      break;
    case "account_order_detail":
      routePath = options.orderId?.trim()
        ? buildSitePath({
            countryCode,
            pageType: "account",
            handle: "orders",
            nestedPath: ["details", options.orderId.trim()],
          })
        : null;
      break;
    case "order_confirmed":
      routePath = options.orderId?.trim()
        ? buildSitePath({
            countryCode,
            pageType: "order",
            handle: options.orderId.trim(),
            nestedPath: ["confirmed"],
          })
        : null;
      break;
    case "order_transfer":
      routePath = options.orderId?.trim() && options.transferToken?.trim()
        ? buildSitePath({
            countryCode,
            pageType: "order",
            handle: options.orderId.trim(),
            nestedPath: ["transfer", options.transferToken.trim()],
          })
        : null;
      break;
    case "order_transfer_accept":
      routePath = options.orderId?.trim() && options.transferToken?.trim()
        ? buildSitePath({
            countryCode,
            pageType: "order",
            handle: options.orderId.trim(),
            nestedPath: ["transfer", options.transferToken.trim(), "accept"],
          })
        : null;
      break;
    case "order_transfer_decline":
      routePath = options.orderId?.trim() && options.transferToken?.trim()
        ? buildSitePath({
            countryCode,
            pageType: "order",
            handle: options.orderId.trim(),
            nestedPath: ["transfer", options.transferToken.trim(), "decline"],
          })
        : null;
      break;
    default:
      routePath = null;
      break;
  }

  if (!routePath) {
    return null;
  }

  return buildSitePreviewPath(siteId, routePath);
}

export function resolveSitePreviewPage(
  pages: SitePage[],
  routePath: string | null | undefined,
  entryPageId?: string | null,
): SitePage | null {
  const normalizedRoutePath = (routePath || "").trim().replace(/^\/+|\/+$/g, "");
  const orderedPages = [...pages].sort((a, b) => a.ordering - b.ordering);

  if (!orderedPages.length) {
    return null;
  }

  if (!normalizedRoutePath) {
    return (
      orderedPages.find((page) => page.id === entryPageId) ||
      orderedPages.find((page) => page.isEntry) ||
      orderedPages[0] ||
      null
    );
  }

  const exactSlugMatch = orderedPages.find((page) => page.slug === normalizedRoutePath);
  if (exactSlugMatch) {
    return exactSlugMatch;
  }

  const pageTypeMap = buildRuntimePageTypeMap(orderedPages);
  const resolvedPageType = resolveSitePathPageType(normalizedRoutePath);
  const matchingPageId = Object.entries(pageTypeMap).find(([, pageType]) => pageType === resolvedPageType)?.[0];

  if (!matchingPageId) {
    return null;
  }

  return orderedPages.find((page) => page.id === matchingPageId) || null;
}
