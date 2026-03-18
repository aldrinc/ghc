import { useMemo } from "react";
import type { PaidAdsQaFinding, PaidAdsQaRun } from "@/api/paidAdsQa";
import type { CardViolationSummary } from "@/types/creativeReview";
import { EMPTY_VIOLATION_SUMMARY } from "@/types/creativeReview";

/**
 * Builds a lookup from creative_spec ID → QA findings.
 */
export function buildFindingsBySpec(
  runs: PaidAdsQaRun[],
): Map<string, PaidAdsQaFinding[]> {
  const map = new Map<string, PaidAdsQaFinding[]>();
  for (const run of runs) {
    if (run.status === "needs_manual_review") continue;
    for (const finding of run.findings) {
      if (finding.artifactType === "creative_spec" && finding.artifactRef) {
        const list = map.get(finding.artifactRef) ?? [];
        list.push(finding);
        map.set(finding.artifactRef, list);
      }
    }
  }
  return map;
}

/**
 * Returns campaign-level findings (not tied to a specific creative spec).
 */
export function getCampaignLevelFindings(
  runs: PaidAdsQaRun[],
): PaidAdsQaFinding[] {
  const findings: PaidAdsQaFinding[] = [];
  for (const run of runs) {
    if (run.status === "needs_manual_review") continue;
    for (const finding of run.findings) {
      if (finding.artifactType === "campaign") {
        findings.push(finding);
      }
    }
  }
  return findings;
}

/**
 * Summarises QA violations for a list of findings.
 */
export function summarizeViolations(
  findings: PaidAdsQaFinding[],
): CardViolationSummary {
  if (!findings.length) return EMPTY_VIOLATION_SUMMARY;

  let blocker = 0;
  let high = 0;
  let medium = 0;
  let low = 0;

  for (const f of findings) {
    switch (f.severity) {
      case "blocker":
        blocker++;
        break;
      case "high":
        high++;
        break;
      case "medium":
        medium++;
        break;
      case "low":
        low++;
        break;
    }
  }

  const total = blocker + high + medium + low;
  const maxSeverity: CardViolationSummary["maxSeverity"] = blocker
    ? "blocker"
    : high
      ? "high"
      : medium
        ? "medium"
        : low
          ? "low"
          : null;

  return { total, blocker, high, medium, low, maxSeverity };
}

/**
 * React hook that maps QA run findings to creative spec IDs.
 * Returns a Map<specId, findings[]> and campaign-level findings.
 */
export function useFindingsBySpec(runs: PaidAdsQaRun[]) {
  return useMemo(() => {
    const bySpec = buildFindingsBySpec(runs);
    const campaignLevel = getCampaignLevelFindings(runs);
    return { bySpec, campaignLevel };
  }, [runs]);
}
