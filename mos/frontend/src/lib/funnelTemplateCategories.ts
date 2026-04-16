export type FunnelTemplateCategory = "presales" | "sales" | "compliance";

const TEMPLATE_CATEGORY_LABELS: Record<FunnelTemplateCategory, string> = {
  presales: "Pre-Sales Templates",
  sales: "Sales Templates",
  compliance: "Compliance Templates",
};

const TEMPLATE_CATEGORY_ALIASES: Record<string, FunnelTemplateCategory> = {
  presales: "presales",
  "pre-sales": "presales",
  pre_sales: "presales",
  sales: "sales",
  compliance: "compliance",
};

export function normalizeFunnelTemplateCategory(value: string | null | undefined): FunnelTemplateCategory | null {
  const cleaned = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (!cleaned) {
    return null;
  }
  return TEMPLATE_CATEGORY_ALIASES[cleaned] ?? null;
}

export function resolveFunnelTemplateCategory(templateId: string | null | undefined): FunnelTemplateCategory | null {
  const cleaned = typeof templateId === "string" ? templateId.trim().toLowerCase() : "";
  if (!cleaned) {
    return null;
  }
  if (cleaned === "pre-sales-listicle" || cleaned === "pre_sales_listicle") {
    return "presales";
  }
  if (cleaned === "sales-pdp" || cleaned === "sales_pdp") {
    return "sales";
  }
  if (cleaned.startsWith("presales-") || cleaned.startsWith("pre-sales-") || cleaned.startsWith("pre_sales_")) {
    return "presales";
  }
  if (cleaned.startsWith("sales-") || cleaned.startsWith("sales_")) {
    return "sales";
  }
  if (cleaned.startsWith("compliance-") || cleaned.startsWith("compliance_")) {
    return "compliance";
  }
  return null;
}

export function funnelTemplateCategoryLabel(category: FunnelTemplateCategory | null | undefined): string | null {
  if (!category) {
    return null;
  }
  return TEMPLATE_CATEGORY_LABELS[category];
}
