import { describe, expect, it } from "vitest";

import { readMetaDomainVerification, resolveMetaVerifiedDomainCandidate } from "@/lib/metaDomainVerification";

describe("resolveMetaVerifiedDomainCandidate", () => {
  it("normalizes an explicit verified domain to the apex domain", () => {
    expect(resolveMetaVerifiedDomainCandidate("shop.thehonestherbalist.com", "https://example.com")).toBe(
      "thehonestherbalist.com",
    );
  });

  it("normalizes the review base URL hostname to the apex domain", () => {
    expect(resolveMetaVerifiedDomainCandidate("", "https://shop.thehonestherbalist.com/products/tincture")).toBe(
      "thehonestherbalist.com",
    );
  });
});

describe("readMetaDomainVerification", () => {
  it("reads the persisted verification metadata", () => {
    expect(
      readMetaDomainVerification({
        metaDomainVerification: {
          status: "dns_record_written",
          provider: "namecheap",
          recordType: "TXT",
          host: "@",
          domain: "example.com",
          fqdn: "example.com",
          value: "facebook-domain-verification=xyz789",
          ttl: 300,
          metaConfirmationRequired: true,
          funnelIds: ["funnel-1"],
          provisionedAt: "2026-03-13T20:55:00+00:00",
          lastSyncedAt: "2026-03-13T20:55:30+00:00",
        },
      }),
    ).toEqual({
      status: "dns_record_written",
      provider: "namecheap",
      recordType: "TXT",
      host: "@",
      domain: "example.com",
      fqdn: "example.com",
      value: "facebook-domain-verification=xyz789",
      ttl: 300,
      metaConfirmationRequired: true,
      funnelIds: ["funnel-1"],
      provisionedAt: "2026-03-13T20:55:00+00:00",
      lastSyncedAt: "2026-03-13T20:55:30+00:00",
    });
  });
});
