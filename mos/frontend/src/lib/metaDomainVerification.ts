type UnknownRecord = Record<string, unknown>;

export type MetaDomainVerificationState = {
  status: string | null;
  provider: string | null;
  recordType: string | null;
  host: string | null;
  domain: string | null;
  fqdn: string | null;
  value: string | null;
  ttl: number | null;
  metaConfirmationRequired: boolean;
  funnelIds: string[];
  provisionedAt: string | null;
  lastSyncedAt: string | null;
};

function readTrimmedString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalizeHostname(value: string | null | undefined): string | null {
  const cleaned = readTrimmedString(value);
  if (!cleaned) return null;
  try {
    if (cleaned.includes("://")) {
      return new URL(cleaned).hostname.trim().toLowerCase();
    }
  } catch {
    return null;
  }
  return cleaned.toLowerCase().replace(/\.$/, "");
}

export function resolveMetaVerifiedDomainCandidate(
  verifiedDomain?: string | null,
  reviewBaseUrl?: string | null,
): string | null {
  return normalizeHostname(verifiedDomain) || normalizeHostname(reviewBaseUrl) || null;
}

export function readMetaDomainVerification(
  metadata: Record<string, unknown> | null | undefined,
): MetaDomainVerificationState | null {
  if (!metadata || typeof metadata !== "object") return null;
  const raw = metadata["metaDomainVerification"];
  if (!raw || typeof raw !== "object") return null;
  const state = raw as UnknownRecord;
  const rawFunnelIds = Array.isArray(state.funnelIds) ? state.funnelIds : [];
  return {
    status: readTrimmedString(state.status),
    provider: readTrimmedString(state.provider),
    recordType: readTrimmedString(state.recordType),
    host: readTrimmedString(state.host),
    domain: readTrimmedString(state.domain),
    fqdn: readTrimmedString(state.fqdn),
    value: readTrimmedString(state.value),
    ttl: typeof state.ttl === "number" ? state.ttl : null,
    metaConfirmationRequired: state.metaConfirmationRequired === true,
    funnelIds: rawFunnelIds.filter((value): value is string => typeof value === "string" && value.trim().length > 0),
    provisionedAt: readTrimmedString(state.provisionedAt),
    lastSyncedAt: readTrimmedString(state.lastSyncedAt),
  };
}
