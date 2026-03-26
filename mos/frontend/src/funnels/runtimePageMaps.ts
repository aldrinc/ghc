import { resolvePublicFunnelStage } from "@/lib/funnelTracking";
import type { PublicFunnelStage, SitePageType } from "@/types/funnels";

type RuntimePageLike = {
  id?: string | null;
  slug?: string | null;
  name?: string | null;
  template_id?: string | null;
  templateId?: string | null;
  page_type?: string | null;
  pageType?: string | null;
};

const SITE_PAGE_TYPES = new Set<SitePageType>([
  "home",
  "store",
  "collection",
  "category",
  "product_detail",
  "cart",
  "checkout",
  "account_dashboard",
  "account_profile",
  "account_addresses",
  "account_orders",
  "account_order_detail",
  "order_confirmed",
  "order_transfer",
  "order_transfer_accept",
  "order_transfer_decline",
]);

const TEMPLATE_TO_PAGE_TYPE: Record<string, SitePageType> = {
  "medusa-b2b-home": "home",
  "medusa-b2b-category": "category",
  "medusa-b2b-pdp": "product_detail",
  "medusa-b2b-cart": "cart",
  "medusa-b2b-checkout": "checkout",
  "medusa-b2c-home": "home",
  "medusa-b2c-store": "store",
  "medusa-b2c-collection": "collection",
  "medusa-b2c-category": "category",
  "medusa-b2c-product": "product_detail",
  "medusa-b2c-cart": "cart",
  "medusa-b2c-checkout": "checkout",
  "medusa-b2c-account-dashboard": "account_dashboard",
  "medusa-b2c-account-profile": "account_profile",
  "medusa-b2c-account-addresses": "account_addresses",
  "medusa-b2c-account-orders": "account_orders",
  "medusa-b2c-account-order-detail": "account_order_detail",
  "medusa-b2c-order-confirmed": "order_confirmed",
  "medusa-b2c-order-transfer": "order_transfer",
  "medusa-b2c-order-transfer-accept": "order_transfer_accept",
  "medusa-b2c-order-transfer-decline": "order_transfer_decline",
};

function cleanOptionalText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function readTemplateId(page: RuntimePageLike): string | null {
  return cleanOptionalText(page.template_id ?? page.templateId);
}

function readPageName(page: RuntimePageLike): string | null {
  return cleanOptionalText(page.name);
}

function readRawSlug(page: RuntimePageLike): string | null {
  return cleanOptionalText(page.slug);
}

function readPageId(page: RuntimePageLike): string | null {
  return cleanOptionalText(page.id);
}

function resolveStageFromPage(page: RuntimePageLike): PublicFunnelStage {
  const templateId = readTemplateId(page);
  if (templateId === "pre-sales-listicle" || templateId === "pre_sales_listicle") {
    return "pre_sales";
  }
  if (templateId === "sales-pdp" || templateId === "sales_pdp") {
    return "sales";
  }

  const slugStage = resolvePublicFunnelStage(readRawSlug(page));
  if (slugStage !== "custom") {
    return slugStage;
  }

  const name = readPageName(page)?.toLowerCase();
  if (!name) {
    return "custom";
  }
  if (name.includes("pre-sales") || name.includes("presales") || name.includes("advertorial")) {
    return "pre_sales";
  }
  if (name.includes("sales") || name.includes("pdp") || name.includes("product page")) {
    return "sales";
  }
  if (name.includes("checkout")) {
    return "checkout";
  }
  if (name.includes("thank")) {
    return "thank_you";
  }
  return "custom";
}

function resolveCanonicalSlug(page: RuntimePageLike): string | null {
  const slug = readRawSlug(page);
  if (!slug) return null;
  return resolveStageFromPage(page) === "pre_sales" ? "presales" : slug;
}

function isSitePageType(value: string | null): value is SitePageType {
  return Boolean(value) && SITE_PAGE_TYPES.has(value as SitePageType);
}

function resolveSitePageType(page: RuntimePageLike): SitePageType | null {
  const explicitPageType = cleanOptionalText(page.page_type ?? page.pageType);
  if (isSitePageType(explicitPageType)) {
    return explicitPageType;
  }
  const templateId = readTemplateId(page);
  if (!templateId) {
    return null;
  }
  return TEMPLATE_TO_PAGE_TYPE[templateId] ?? null;
}

export function buildRuntimePageMap(pages: RuntimePageLike[] | null | undefined): Record<string, string> {
  const result: Record<string, string> = {};
  for (const page of pages ?? []) {
    const pageId = readPageId(page);
    const slug = resolveCanonicalSlug(page);
    if (!pageId || !slug) continue;
    result[pageId] = slug;
  }
  return result;
}

export function buildRuntimePageStageMap(
  pages: RuntimePageLike[] | null | undefined
): Record<string, PublicFunnelStage> {
  const result: Record<string, PublicFunnelStage> = {};
  for (const page of pages ?? []) {
    const pageId = readPageId(page);
    if (!pageId) continue;
    result[pageId] = resolveStageFromPage(page);
  }
  return result;
}

export function buildRuntimePageTypeMap(
  pages: RuntimePageLike[] | null | undefined
): Record<string, SitePageType> {
  const result: Record<string, SitePageType> = {};
  for (const page of pages ?? []) {
    const pageId = readPageId(page);
    const pageType = resolveSitePageType(page);
    if (!pageId || !pageType) continue;
    result[pageId] = pageType;
  }
  return result;
}
