export type SiteImportTargetTemplate = "sales-pdp" | "pre-sales-listicle";

export type SiteImportSalesWiringMode = "none" | "shared" | "paired";

export type SiteImportSharedSalesTarget = "new" | "existing";

export type SiteImportBatchItem = {
  id: string;
  referenceHtml: string;
  referenceLabel: string;
  pageName: string;
  slug: string;
};

function stripImportExtension(value: string): string {
  return value.replace(/\.(html?|txt)$/i, "");
}

function capitalizeToken(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function slugifySiteImportValue(value: string): string {
  const normalized = String(value || "").trim().toLowerCase();
  const slug = normalized.replace(/[^a-z0-9]+/g, "-").replace(/-{2,}/g, "-").replace(/^-+|-+$/g, "");
  return slug || "page";
}

export function makeUniqueSiteImportSlug(desiredSlug: string, usedSlugs: Iterable<string>): string {
  const base = slugifySiteImportValue(desiredSlug);
  const taken = new Set(
    Array.from(usedSlugs, (slug) => slugifySiteImportValue(slug)).filter((slug) => Boolean(slug)),
  );
  if (!taken.has(base)) {
    return base;
  }
  let suffix = 2;
  while (taken.has(`${base}-${suffix}`)) {
    suffix += 1;
  }
  return `${base}-${suffix}`;
}

export function defaultSiteImportPageName(referenceLabel: string): string {
  const baseLabel = stripImportExtension(String(referenceLabel || "")).trim();
  const normalized = baseLabel.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "Imported Page";
  }
  if (slugifySiteImportValue(normalized) === "pasted-html") {
    return "Imported Page";
  }
  return normalized
    .split(" ")
    .map((token) => capitalizeToken(token))
    .join(" ");
}

export function defaultPairedSalesPageName(pageName: string): string {
  const normalized = String(pageName || "").trim() || "Imported Page";
  return `${normalized} Sales Page`;
}

export function defaultPairedSalesPageSlug(pageSlug: string): string {
  const base = slugifySiteImportValue(pageSlug || "sales");
  return base.endsWith("-sales") ? base : `${base}-sales`;
}

export function defaultSharedSalesPageName(): string {
  return "Sales Page";
}

export function defaultSharedSalesPageSlug(): string {
  return "sales";
}

export function buildSiteImportBatchItem(args: {
  id: string;
  referenceHtml: string;
  referenceLabel: string;
  usedSlugs?: Iterable<string>;
}): SiteImportBatchItem {
  const pageName = defaultSiteImportPageName(args.referenceLabel);
  const slug = makeUniqueSiteImportSlug(stripImportExtension(args.referenceLabel), args.usedSlugs || []);
  return {
    id: args.id,
    referenceHtml: args.referenceHtml,
    referenceLabel: args.referenceLabel,
    pageName,
    slug,
  };
}
