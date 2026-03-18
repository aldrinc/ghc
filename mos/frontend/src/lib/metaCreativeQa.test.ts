import { describe, expect, it } from "vitest";
import type { PaidAdsQaRun } from "@/api/paidAdsQa";
import {
  filterMetaQaRunsForScope,
  hasCreativeSpecFindings,
  resolveMetaCreativeQaState,
} from "@/lib/metaCreativeQa";

function makeRun(
  id: string,
  overrides: Partial<PaidAdsQaRun> = {},
): PaidAdsQaRun {
  return {
    id,
    orgId: "org-1",
    clientId: "client-1",
    campaignId: "campaign-1",
    platform: "meta",
    subjectType: "campaign",
    subjectId: "campaign-1",
    rulesetVersion: "paid_ads_policy_ruleset_v2",
    status: "failed",
    blockerCount: 0,
    highCount: 0,
    mediumCount: 0,
    lowCount: 0,
    needsManualReviewCount: 0,
    checkedRuleIds: [],
    reportMarkdown: "",
    metadata: {},
    findings: [],
    createdAt: "2026-03-15T16:00:00Z",
    completedAt: "2026-03-15T16:01:00Z",
    ...overrides,
  };
}

describe("metaCreativeQa", () => {
  it("matches only runs for the active generation and funnel", () => {
    const matching = makeRun("matching", {
      metadata: { generationKey: "batch:new", funnelId: "funnel-1" },
    });
    const wrongGeneration = makeRun("wrong-generation", {
      metadata: { generationKey: "batch:old", funnelId: "funnel-1" },
    });
    const wrongFunnel = makeRun("wrong-funnel", {
      metadata: { generationKey: "batch:new", funnelId: "funnel-2" },
    });

    expect(
      filterMetaQaRunsForScope(
        [wrongFunnel, matching, wrongGeneration],
        { generationKey: "batch:new", funnelId: "funnel-1", requiresFunnelScope: true },
      ).map((run) => run.id),
    ).toEqual(["matching"]);
  });

  it("detects creative-spec findings and picks the newest creative run", () => {
    const platformOnly = makeRun("platform-only", {
      createdAt: "2026-03-15T16:10:00Z",
      completedAt: "2026-03-15T16:11:00Z",
      metadata: { generationKey: "batch:new", funnelId: "funnel-1" },
      findings: [
        {
          id: "finding-1",
          ruleId: "verified-domain",
          ruleType: "operational_readiness",
          platform: "meta",
          severity: "blocker",
          status: "failed",
          title: "Verified domain missing",
          message: "Missing verified domain",
          artifactType: "platform_profile",
          artifactRef: "meta",
          fixGuidance: [],
          evidence: {},
          needsVerification: false,
          sourceId: "source-1",
          sourceTitle: "Source",
          createdAt: "2026-03-15T16:11:00Z",
        },
      ],
    });
    const creativeRun = makeRun("creative-run", {
      createdAt: "2026-03-15T16:05:00Z",
      completedAt: "2026-03-15T16:06:00Z",
      metadata: { generationKey: "batch:new", funnelId: "funnel-1" },
      findings: [
        {
          id: "finding-2",
          ruleId: "policy-1",
          ruleType: "policy",
          platform: "meta",
          severity: "high",
          status: "failed",
          title: "Sensitive condition inference",
          message: "Uses sensitive condition language",
          artifactType: "creative_spec",
          artifactRef: "spec-1",
          fixGuidance: [],
          evidence: {},
          needsVerification: false,
          sourceId: "source-2",
          sourceTitle: "Source",
          createdAt: "2026-03-15T16:06:00Z",
        },
      ],
    });

    expect(hasCreativeSpecFindings(platformOnly)).toBe(false);
    expect(hasCreativeSpecFindings(creativeRun)).toBe(true);

    const state = resolveMetaCreativeQaState({
      runs: [platformOnly, creativeRun],
      generationKey: "batch:new",
      funnelId: "funnel-1",
      requiresFunnelScope: true,
      qaRunsLoading: false,
      qaRunsError: null,
    });

    expect(state.filteringEnabled).toBe(true);
    expect(state.reviewRuns.map((run) => run.id)).toEqual(["creative-run"]);
    expect(state.notice).toBeNull();
  });

  it("warns when matching runs exist but only contain campaign-level checks", () => {
    const platformOnly = makeRun("platform-only", {
      metadata: { generationKey: "batch:new", funnelId: "funnel-1" },
      findings: [
        {
          id: "finding-1",
          ruleId: "verified-domain",
          ruleType: "operational_readiness",
          platform: "meta",
          severity: "blocker",
          status: "failed",
          title: "Verified domain missing",
          message: "Missing verified domain",
          artifactType: "platform_profile",
          artifactRef: "meta",
          fixGuidance: [],
          evidence: {},
          needsVerification: false,
          sourceId: "source-1",
          sourceTitle: "Source",
          createdAt: "2026-03-15T16:11:00Z",
        },
      ],
    });

    const state = resolveMetaCreativeQaState({
      runs: [platformOnly],
      generationKey: "batch:new",
      funnelId: "funnel-1",
      requiresFunnelScope: true,
      qaRunsLoading: false,
      qaRunsError: null,
    });

    expect(state.filteringEnabled).toBe(false);
    expect(state.reviewRuns).toEqual([]);
    expect(state.notice).toContain("campaign or platform readiness");
  });
});
