import { describe, it, expect } from "vitest";
import {
  buildComplianceProfileFormState,
  parseComplianceBusinessModels,
  normalizeComplianceOptionalText,
} from "../complianceUtils";

describe("buildComplianceProfileFormState", () => {
  it("returns defaults for null profile", () => {
    const state = buildComplianceProfileFormState(null);
    expect(state.businessModelsCsv).toBe("ecommerce");
    expect(state.legalBusinessName).toBe("");
    expect(state.supportEmail).toBe("");
  });

  it("uses workspace name as fallback for legal name", () => {
    const state = buildComplianceProfileFormState(null, "Acme Corp");
    expect(state.legalBusinessName).toBe("Acme Corp");
  });

  it("populates from saved profile", () => {
    const profile = {
      id: "p1",
      orgId: "org1",
      clientId: "c1",
      rulesetVersion: "v1",
      businessModels: ["ecommerce" as const, "saas_subscription" as const],
      legalBusinessName: "  The Honest Herbalist  ",
      companyAddressText: "123 Main St",
      supportEmail: "help@example.com",
      supportPhone: "+1 555 000 0000",
      supportHoursText: "Mon-Fri 9-5",
      metadata: {},
      createdAt: "2025-01-01",
      updatedAt: "2025-06-01",
    };
    const state = buildComplianceProfileFormState(profile, "Fallback");
    expect(state.businessModelsCsv).toBe("ecommerce, saas_subscription");
    expect(state.legalBusinessName).toBe("The Honest Herbalist");
    expect(state.companyAddressText).toBe("123 Main St");
    expect(state.supportEmail).toBe("help@example.com");
  });

  it("uses workspace name when profile legal name is empty", () => {
    const profile = {
      id: "p1",
      orgId: "org1",
      clientId: "c1",
      rulesetVersion: "v1",
      businessModels: ["ecommerce" as const],
      legalBusinessName: "",
      companyAddressText: "",
      supportEmail: "",
      supportPhone: "",
      supportHoursText: "",
      metadata: {},
      createdAt: "2025-01-01",
      updatedAt: "2025-06-01",
    };
    const state = buildComplianceProfileFormState(profile, "Workspace Co");
    expect(state.legalBusinessName).toBe("Workspace Co");
  });
});

describe("parseComplianceBusinessModels", () => {
  it("parses valid comma-separated models", () => {
    const result = parseComplianceBusinessModels("ecommerce, saas_subscription");
    expect(result).toEqual(["ecommerce", "saas_subscription"]);
  });

  it("deduplicates models", () => {
    const result = parseComplianceBusinessModels("ecommerce, ecommerce");
    expect(result).toEqual(["ecommerce"]);
  });

  it("throws on empty input", () => {
    expect(() => parseComplianceBusinessModels("")).toThrow("At least one business model is required.");
  });

  it("throws on invalid models", () => {
    expect(() => parseComplianceBusinessModels("ecommerce, invalid_model")).toThrow(
      "Unsupported business model(s): invalid_model",
    );
  });

  it("trims whitespace", () => {
    const result = parseComplianceBusinessModels("  ecommerce  ,  digital_product  ");
    expect(result).toEqual(["ecommerce", "digital_product"]);
  });
});

describe("normalizeComplianceOptionalText", () => {
  it("returns trimmed string for non-empty input", () => {
    expect(normalizeComplianceOptionalText("  hello  ")).toBe("hello");
  });

  it("returns undefined for empty or whitespace-only input", () => {
    expect(normalizeComplianceOptionalText("")).toBeUndefined();
    expect(normalizeComplianceOptionalText("   ")).toBeUndefined();
  });
});
