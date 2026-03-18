import type { PaidAdsQaRun } from "@/api/paidAdsQa";

type MetaCreativeQaScope = {
  generationKey: string | null;
  funnelId: string | null;
  requiresFunnelScope: boolean;
};

export type MetaCreativeQaState = {
  matchingRuns: PaidAdsQaRun[];
  reviewRuns: PaidAdsQaRun[];
  filteringEnabled: boolean;
  notice: string | null;
};

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function runTimestamp(run: PaidAdsQaRun): number {
  const date = new Date(run.completedAt || run.createdAt);
  return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

export function hasCreativeSpecFindings(run: PaidAdsQaRun): boolean {
  return run.findings.some(
    (finding) => finding.artifactType === "creative_spec" && typeof finding.artifactRef === "string" && finding.artifactRef.trim(),
  );
}

export function filterMetaQaRunsForScope(
  runs: PaidAdsQaRun[],
  { generationKey, funnelId, requiresFunnelScope }: MetaCreativeQaScope,
): PaidAdsQaRun[] {
  return [...runs]
    .filter((run) => {
      if (run.platform !== "meta" || run.subjectType !== "campaign") return false;

      const runGenerationKey =
        readString(run.metadata?.generationKey) || readString(run.metadata?.requestedGenerationKey);
      if (generationKey) {
        if (!runGenerationKey || runGenerationKey !== generationKey) return false;
      }

      if (requiresFunnelScope && funnelId) {
        const runFunnelId = readString(run.metadata?.funnelId);
        if (!runFunnelId || runFunnelId !== funnelId) return false;
      }

      return true;
    })
    .sort((left, right) => runTimestamp(right) - runTimestamp(left));
}

export function resolveMetaCreativeQaState({
  runs,
  generationKey,
  funnelId,
  requiresFunnelScope,
  qaRunsLoading,
  qaRunsError,
}: MetaCreativeQaScope & {
  runs: PaidAdsQaRun[];
  qaRunsLoading: boolean;
  qaRunsError: string | null;
}): MetaCreativeQaState {
  const matchingRuns =
    generationKey
      ? filterMetaQaRunsForScope(runs, { generationKey, funnelId, requiresFunnelScope })
      : [];
  const latestCreativeRun = matchingRuns.find(hasCreativeSpecFindings) ?? null;

  if (qaRunsLoading || !generationKey || (requiresFunnelScope && !funnelId)) {
    return {
      matchingRuns,
      reviewRuns: latestCreativeRun ? [latestCreativeRun] : [],
      filteringEnabled: Boolean(latestCreativeRun),
      notice: null,
    };
  }

  if (qaRunsError) {
    return {
      matchingRuns,
      reviewRuns: [],
      filteringEnabled: false,
      notice: `Failed to load Meta QA history: ${qaRunsError}. Clean and Has issues filters are disabled.`,
    };
  }

  if (!matchingRuns.length) {
    return {
      matchingRuns,
      reviewRuns: [],
      filteringEnabled: false,
      notice: "No Meta QA run exists for this generation yet. Clean and Has issues filters are disabled.",
    };
  }

  if (!latestCreativeRun) {
    return {
      matchingRuns,
      reviewRuns: [],
      filteringEnabled: false,
      notice:
        "Available Meta QA results only cover campaign or platform readiness. Clean and Has issues filters are disabled here and will not match external policy-review exports.",
    };
  }

  return {
    matchingRuns,
    reviewRuns: [latestCreativeRun],
    filteringEnabled: true,
    notice: null,
  };
}
