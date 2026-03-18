import type { ClientComplianceProfile, ComplianceBusinessModel } from "@/api/compliance";

export type ComplianceProfileFormState = {
  businessModelsCsv: string;
  legalBusinessName: string;
  companyAddressText: string;
  supportEmail: string;
  supportPhone: string;
  supportHoursText: string;
};

export const ALLOWED_COMPLIANCE_BUSINESS_MODELS: ComplianceBusinessModel[] = [
  "ecommerce",
  "saas_subscription",
  "digital_product",
  "online_service",
  "lead_generation",
];

export function buildComplianceProfileFormState(
  profile: ClientComplianceProfile | null | undefined,
  workspaceName?: string,
): ComplianceProfileFormState {
  const businessModels =
    profile?.businessModels.length ? profile.businessModels : (["ecommerce"] as ComplianceBusinessModel[]);
  return {
    businessModelsCsv: businessModels.join(", "),
    legalBusinessName: profile?.legalBusinessName?.trim() || workspaceName?.trim() || "",
    companyAddressText: profile?.companyAddressText?.trim() || "",
    supportEmail: profile?.supportEmail?.trim() || "",
    supportPhone: profile?.supportPhone?.trim() || "",
    supportHoursText: profile?.supportHoursText?.trim() || "",
  };
}

export function parseComplianceBusinessModels(input: string): ComplianceBusinessModel[] {
  const requested = input
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (!requested.length) {
    throw new Error("At least one business model is required.");
  }

  const deduped = Array.from(new Set(requested));
  const invalid = deduped.filter(
    (value) => !ALLOWED_COMPLIANCE_BUSINESS_MODELS.includes(value as ComplianceBusinessModel),
  );
  if (invalid.length) {
    throw new Error(
      `Unsupported business model(s): ${invalid.join(", ")}. Allowed: ${ALLOWED_COMPLIANCE_BUSINESS_MODELS.join(", ")}.`,
    );
  }
  return deduped as ComplianceBusinessModel[];
}

export function normalizeComplianceOptionalText(value: string): string | undefined {
  const normalized = value.trim();
  return normalized ? normalized : undefined;
}
