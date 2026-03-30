type MedusaRuntimeSiteOptions = {
  siteFamily?: string | null;
  commerceProvider?: string | null;
};

export function isMedusaB2CRuntimeSite({
  siteFamily,
  commerceProvider,
}: MedusaRuntimeSiteOptions): boolean {
  const normalizedFamily = (siteFamily || "").trim();
  if (normalizedFamily === "medusa-b2b-starter") {
    return false;
  }
  if (normalizedFamily === "medusa-b2c-starter") {
    return true;
  }
  return (commerceProvider || "").trim().toLowerCase() === "medusa";
}
