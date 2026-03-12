import { useEffect, useState } from "react";
import { useApiClient, type ApiError } from "@/api/client";
import {
  PAID_ADS_QA_RULESET_VERSION,
  type PaidAdsPlatformProfile,
  type PaidAdsPlatformProfileUpsertPayload,
  type PaidAdsQaFinding,
  type PaidAdsQaRun,
} from "@/api/paidAdsQa";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MarkdownViewer } from "@/components/ui/MarkdownViewer";
import { Select, type SelectOption } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { resolveWindowShopHostedOrigin } from "@/lib/shopHostedFunnels";
import type { Campaign } from "@/types/common";

type CampaignPaidAdsQaCardProps = {
  campaign: Campaign;
};

type BooleanSelectValue = "" | "true" | "false";

type ProfileFormState = {
  businessManagerId: string;
  pageId: string;
  adAccountId: string;
  paymentMethodType: string;
  paymentMethodStatus: string;
  pixelId: string;
  dataSetId: string;
  dataSetShopifyPartnerInstalled: BooleanSelectValue;
  dataSetDataSharingLevel: string;
  dataSetAssignedToAdAccount: BooleanSelectValue;
  verifiedDomain: string;
  verifiedDomainStatus: string;
  attributionClickWindow: string;
  attributionViewWindow: string;
  viewThroughEnabled: BooleanSelectValue;
  trackingProvider: string;
  trackingUrlParameters: string;
};

const BOOLEAN_OPTIONS: SelectOption[] = [
  { label: "Unset", value: "" },
  { label: "Yes", value: "true" },
  { label: "No", value: "false" },
];

const PAYMENT_TYPE_OPTIONS: SelectOption[] = [
  { label: "Unset", value: "" },
  { label: "Credit card", value: "credit_card" },
  { label: "PayPal", value: "paypal" },
];

const PAYMENT_STATUS_OPTIONS: SelectOption[] = [
  { label: "Unset", value: "" },
  { label: "Active", value: "active" },
  { label: "Configured", value: "configured" },
  { label: "Inactive", value: "inactive" },
];

const DATA_SHARING_OPTIONS: SelectOption[] = [
  { label: "Unset", value: "" },
  { label: "Maximum", value: "maximum" },
  { label: "Standard", value: "standard" },
  { label: "Limited", value: "limited" },
];

const DOMAIN_STATUS_OPTIONS: SelectOption[] = [
  { label: "Unset", value: "" },
  { label: "Verified", value: "verified" },
  { label: "Pending", value: "pending" },
  { label: "Unverified", value: "unverified" },
];

const CLICK_WINDOW_OPTIONS: SelectOption[] = [
  { label: "Unset", value: "" },
  { label: "7d", value: "7d" },
  { label: "1d", value: "1d" },
];

const VIEW_WINDOW_OPTIONS: SelectOption[] = [
  { label: "Unset", value: "" },
  { label: "1d", value: "1d" },
  { label: "0d", value: "0d" },
];

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function getErrorMessage(err: unknown) {
  if (typeof err === "string") return err;
  if (err && typeof err === "object" && "message" in err) return (err as ApiError).message || "Request failed";
  return "Request failed";
}

function runStatusTone(status: PaidAdsQaRun["status"]): "neutral" | "accent" | "success" | "danger" {
  if (status === "passed") return "success";
  if (status === "needs_manual_review") return "accent";
  return "danger";
}

function severityTone(severity: PaidAdsQaFinding["severity"]): "neutral" | "accent" | "success" | "danger" {
  if (severity === "blocker" || severity === "high") return "danger";
  if (severity === "medium") return "accent";
  return "neutral";
}

function findingStatusTone(status: PaidAdsQaFinding["status"]): "neutral" | "accent" | "success" | "danger" {
  if (status === "needs_manual_review") return "accent";
  return "danger";
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function emptyProfileFormState(): ProfileFormState {
  return {
    businessManagerId: "",
    pageId: "",
    adAccountId: "",
    paymentMethodType: "",
    paymentMethodStatus: "",
    pixelId: "",
    dataSetId: "",
    dataSetShopifyPartnerInstalled: "",
    dataSetDataSharingLevel: "",
    dataSetAssignedToAdAccount: "",
    verifiedDomain: "",
    verifiedDomainStatus: "",
    attributionClickWindow: "",
    attributionViewWindow: "",
    viewThroughEnabled: "",
    trackingProvider: "",
    trackingUrlParameters: "",
  };
}

function booleanToSelect(value?: boolean | null): BooleanSelectValue {
  if (value === true) return "true";
  if (value === false) return "false";
  return "";
}

function selectToBoolean(value: BooleanSelectValue): boolean | undefined {
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}

function normalizeOptionalText(value: string): string | undefined {
  const cleaned = value.trim();
  return cleaned || undefined;
}

function buildProfileFormState(profile: PaidAdsPlatformProfile | null): ProfileFormState {
  if (!profile) return emptyProfileFormState();
  return {
    businessManagerId: profile.businessManagerId || "",
    pageId: profile.pageId || "",
    adAccountId: profile.adAccountId || "",
    paymentMethodType: profile.paymentMethodType || "",
    paymentMethodStatus: profile.paymentMethodStatus || "",
    pixelId: profile.pixelId || "",
    dataSetId: profile.dataSetId || "",
    dataSetShopifyPartnerInstalled: booleanToSelect(profile.dataSetShopifyPartnerInstalled),
    dataSetDataSharingLevel: profile.dataSetDataSharingLevel || "",
    dataSetAssignedToAdAccount: booleanToSelect(profile.dataSetAssignedToAdAccount),
    verifiedDomain: profile.verifiedDomain || "",
    verifiedDomainStatus: profile.verifiedDomainStatus || "",
    attributionClickWindow: profile.attributionClickWindow || "",
    attributionViewWindow: profile.attributionViewWindow || "",
    viewThroughEnabled: booleanToSelect(profile.viewThroughEnabled),
    trackingProvider: profile.trackingProvider || "",
    trackingUrlParameters: profile.trackingUrlParameters || "",
  };
}

function buildProfilePayload(form: ProfileFormState): PaidAdsPlatformProfileUpsertPayload {
  return {
    rulesetVersion: PAID_ADS_QA_RULESET_VERSION,
    businessManagerId: normalizeOptionalText(form.businessManagerId),
    pageId: normalizeOptionalText(form.pageId),
    adAccountId: normalizeOptionalText(form.adAccountId),
    paymentMethodType: normalizeOptionalText(form.paymentMethodType),
    paymentMethodStatus: normalizeOptionalText(form.paymentMethodStatus),
    pixelId: normalizeOptionalText(form.pixelId),
    dataSetId: normalizeOptionalText(form.dataSetId),
    dataSetShopifyPartnerInstalled: selectToBoolean(form.dataSetShopifyPartnerInstalled),
    dataSetDataSharingLevel: normalizeOptionalText(form.dataSetDataSharingLevel),
    dataSetAssignedToAdAccount: selectToBoolean(form.dataSetAssignedToAdAccount),
    verifiedDomain: normalizeOptionalText(form.verifiedDomain),
    verifiedDomainStatus: normalizeOptionalText(form.verifiedDomainStatus),
    attributionClickWindow: normalizeOptionalText(form.attributionClickWindow),
    attributionViewWindow: normalizeOptionalText(form.attributionViewWindow),
    viewThroughEnabled: selectToBoolean(form.viewThroughEnabled),
    trackingProvider: normalizeOptionalText(form.trackingProvider),
    trackingUrlParameters: normalizeOptionalText(form.trackingUrlParameters),
    metadata: {},
  };
}

export function CampaignPaidAdsQaCard({ campaign }: CampaignPaidAdsQaCardProps) {
  const { get, post, request } = useApiClient();
  const [runHistory, setRunHistory] = useState<PaidAdsQaRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runPending, setRunPending] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [profileForm, setProfileForm] = useState<ProfileFormState>(() => emptyProfileFormState());
  const [profileLoading, setProfileLoading] = useState(true);
  const [profilePending, setProfilePending] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileUpdatedAt, setProfileUpdatedAt] = useState<string | null>(null);

  const reviewBaseUrl = resolveWindowShopHostedOrigin();

  useEffect(() => {
    let cancelled = false;

    const loadProfile = async () => {
      setProfileLoading(true);
      setProfileError(null);
      try {
        const profile = await get<PaidAdsPlatformProfile>(
          `/clients/${campaign.client_id}/paid-ads-qa/platforms/meta/profile`,
        );
        if (cancelled) return;
        setProfileForm(buildProfileFormState(profile));
        setProfileUpdatedAt(profile.updatedAt);
      } catch (err) {
        if (cancelled) return;
        const apiError = err as ApiError;
        if (apiError.status === 404) {
          setProfileForm(emptyProfileFormState());
          setProfileUpdatedAt(null);
        } else {
          setProfileError(getErrorMessage(err));
        }
      } finally {
        if (!cancelled) setProfileLoading(false);
      }
    };

    void loadProfile();
    return () => {
      cancelled = true;
    };
  }, [campaign.client_id, get]);

  useEffect(() => {
    let cancelled = false;

    const loadRunHistory = async () => {
      setHistoryLoading(true);
      setHistoryError(null);
      try {
        const runs = await get<PaidAdsQaRun[]>(`/campaigns/${campaign.id}/paid-ads-qa/runs`);
        if (cancelled) return;
        setRunHistory(runs);
        setSelectedRunId((current) => {
          if (current && runs.some((run) => run.id === current)) return current;
          return runs[0]?.id || null;
        });
      } catch (err) {
        if (cancelled) return;
        setHistoryError(getErrorMessage(err));
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    };

    void loadRunHistory();
    return () => {
      cancelled = true;
    };
  }, [campaign.id, get]);

  const handleRunQa = async () => {
    setRunPending(true);
    setRunError(null);
    try {
      const response = await post<PaidAdsQaRun>(`/campaigns/${campaign.id}/paid-ads-qa/runs`, {
        platform: "meta",
        rulesetVersion: PAID_ADS_QA_RULESET_VERSION,
        reviewBaseUrl,
      });
      setRunHistory((current) => [response, ...current.filter((run) => run.id !== response.id)]);
      setSelectedRunId(response.id);
    } catch (err) {
      setRunError(getErrorMessage(err));
    } finally {
      setRunPending(false);
    }
  };

  const handleSaveProfile = async () => {
    setProfilePending(true);
    setProfileError(null);
    try {
      const saved = await request<PaidAdsPlatformProfile>(
        `/clients/${campaign.client_id}/paid-ads-qa/platforms/meta/profile`,
        {
          method: "PUT",
          body: JSON.stringify(buildProfilePayload(profileForm)),
        },
      );
      setProfileForm(buildProfileFormState(saved));
      setProfileUpdatedAt(saved.updatedAt);
      toast.success("Meta QA profile saved");
    } catch (err) {
      const message = getErrorMessage(err);
      setProfileError(message);
      toast.error(message);
    } finally {
      setProfilePending(false);
    }
  };

  const updateField = <K extends keyof ProfileFormState>(field: K, value: ProfileFormState[K]) => {
    setProfileForm((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const activeRun = runHistory.find((candidate) => candidate.id === selectedRunId) || runHistory[0] || null;

  return (
    <div className="border border-border bg-transparent p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-base font-semibold text-content">Meta paid ads QA</div>
          <div className="text-sm text-content-muted">
            Runs readiness, copy, and destination checks for the current campaign. This does not publish anything.
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="neutral">{PAID_ADS_QA_RULESET_VERSION}</Badge>
          <Button variant="secondary" size="sm" onClick={handleRunQa} disabled={runPending}>
            {runPending ? "Running QA…" : "Run Meta QA"}
          </Button>
        </div>
      </div>

      <div className="mt-2 space-y-1 text-sm text-content-muted">
        <div>Review base URL: {reviewBaseUrl || "Unavailable in this browser context."}</div>
        {historyLoading ? <div>Loading previous QA runs…</div> : null}
        {!historyLoading && !activeRun && !historyError && !runError ? (
          <div>No QA runs recorded for this campaign yet.</div>
        ) : null}
        {historyError ? <div className="text-danger">{historyError}</div> : null}
        {runError ? <div className="text-danger">{runError}</div> : null}
      </div>

      <details className="mt-4 rounded-lg border border-border bg-surface">
        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-content">
          Meta account readiness profile
        </summary>
        <div className="border-t border-border px-4 py-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm text-content-muted">
              {profileLoading
                ? "Loading profile…"
                : profileUpdatedAt
                  ? `Profile updated ${formatDate(profileUpdatedAt)}`
                  : "No saved Meta QA profile yet."}
            </div>
            <Button variant="secondary" size="sm" onClick={handleSaveProfile} disabled={profileLoading || profilePending}>
              {profilePending ? "Saving…" : "Save profile"}
            </Button>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Business Manager ID</label>
              <Input
                value={profileForm.businessManagerId}
                onChange={(event) => updateField("businessManagerId", event.target.value)}
                placeholder="bm-123"
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Page ID</label>
              <Input
                value={profileForm.pageId}
                onChange={(event) => updateField("pageId", event.target.value)}
                placeholder="123456"
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Ad Account ID</label>
              <Input
                value={profileForm.adAccountId}
                onChange={(event) => updateField("adAccountId", event.target.value)}
                placeholder="act_123456"
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Payment type</label>
              <Select
                value={profileForm.paymentMethodType}
                onValueChange={(value) => updateField("paymentMethodType", value)}
                options={PAYMENT_TYPE_OPTIONS}
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Payment status</label>
              <Select
                value={profileForm.paymentMethodStatus}
                onValueChange={(value) => updateField("paymentMethodStatus", value)}
                options={PAYMENT_STATUS_OPTIONS}
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Pixel ID</label>
              <Input
                value={profileForm.pixelId}
                onChange={(event) => updateField("pixelId", event.target.value)}
                placeholder="pixel-123"
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Data Set ID</label>
              <Input
                value={profileForm.dataSetId}
                onChange={(event) => updateField("dataSetId", event.target.value)}
                placeholder="dataset-123"
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Shopify partner installed</label>
              <Select
                value={profileForm.dataSetShopifyPartnerInstalled}
                onValueChange={(value) =>
                  updateField("dataSetShopifyPartnerInstalled", value as BooleanSelectValue)
                }
                options={BOOLEAN_OPTIONS}
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Data sharing level</label>
              <Select
                value={profileForm.dataSetDataSharingLevel}
                onValueChange={(value) => updateField("dataSetDataSharingLevel", value)}
                options={DATA_SHARING_OPTIONS}
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Data Set assigned</label>
              <Select
                value={profileForm.dataSetAssignedToAdAccount}
                onValueChange={(value) => updateField("dataSetAssignedToAdAccount", value as BooleanSelectValue)}
                options={BOOLEAN_OPTIONS}
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Verified domain</label>
              <Input
                value={profileForm.verifiedDomain}
                onChange={(event) => updateField("verifiedDomain", event.target.value)}
                placeholder="example.com"
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Domain status</label>
              <Select
                value={profileForm.verifiedDomainStatus}
                onValueChange={(value) => updateField("verifiedDomainStatus", value)}
                options={DOMAIN_STATUS_OPTIONS}
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Click window</label>
              <Select
                value={profileForm.attributionClickWindow}
                onValueChange={(value) => updateField("attributionClickWindow", value)}
                options={CLICK_WINDOW_OPTIONS}
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">View window</label>
              <Select
                value={profileForm.attributionViewWindow}
                onValueChange={(value) => updateField("attributionViewWindow", value)}
                options={VIEW_WINDOW_OPTIONS}
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">View-through enabled</label>
              <Select
                value={profileForm.viewThroughEnabled}
                onValueChange={(value) => updateField("viewThroughEnabled", value as BooleanSelectValue)}
                options={BOOLEAN_OPTIONS}
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-content">Tracking provider</label>
              <Input
                value={profileForm.trackingProvider}
                onChange={(event) => updateField("trackingProvider", event.target.value)}
                placeholder="triple_whale"
                disabled={profileLoading || profilePending}
              />
            </div>
            <div className="space-y-1 md:col-span-2 xl:col-span-2">
              <label className="text-xs font-semibold text-content">Tracking URL parameters</label>
              <Input
                value={profileForm.trackingUrlParameters}
                onChange={(event) => updateField("trackingUrlParameters", event.target.value)}
                placeholder="utm_source=meta&utm_medium=paid"
                disabled={profileLoading || profilePending}
              />
            </div>
          </div>

          {profileError ? <div className="mt-3 text-sm text-danger">{profileError}</div> : null}
        </div>
      </details>

      {runHistory.length ? (
        <div className="mt-4 space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-content-muted">Run history</div>
          <div className="space-y-2">
            {runHistory.map((historyRun) => {
              const selected = historyRun.id === activeRun?.id;
              return (
                <button
                  key={historyRun.id}
                  type="button"
                  onClick={() => setSelectedRunId(historyRun.id)}
                  className={[
                    "w-full rounded-lg border px-4 py-3 text-left transition",
                    selected ? "border-accent/40 bg-accent/5" : "border-border bg-surface hover:bg-surface-2",
                  ].join(" ")}
                >
                  <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={runStatusTone(historyRun.status)}>
                        {historyRun.status.replace(/_/g, " ")}
                      </Badge>
                    <Badge tone="neutral">Run {historyRun.id.slice(0, 8)}</Badge>
                    <div className="text-sm text-content-muted">
                      {formatDate(historyRun.completedAt || historyRun.createdAt)}
                    </div>
                  </div>
                  <div className="mt-2 grid gap-2 text-xs text-content-muted md:grid-cols-5">
                    <div>Blockers {historyRun.blockerCount}</div>
                    <div>High {historyRun.highCount}</div>
                    <div>Medium {historyRun.mediumCount}</div>
                    <div>Low {historyRun.lowCount}</div>
                    <div>Manual {historyRun.needsManualReviewCount}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {activeRun ? (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
<<<<<<< HEAD
            <Badge tone={runStatusTone(activeRun.status)}>Status {activeRun.status.replace(/_/g, " ")}</Badge>
            <Badge tone="neutral">Run {activeRun.id.slice(0, 8)}</Badge>
            <Badge tone="neutral">Completed {formatDate(activeRun.completedAt || activeRun.createdAt)}</Badge>
            {readString(activeRun.metadata.reviewBaseUrl) ? (
              <Badge tone="neutral">{readString(activeRun.metadata.reviewBaseUrl)}</Badge>
            ) : null}
          </div>

          <div className="grid gap-3 md:grid-cols-5">
            <div className="rounded-lg border border-border bg-surface px-3 py-2">
              <div className="text-xs uppercase tracking-wide text-content-muted">Blockers</div>
              <div className="mt-1 text-lg font-semibold text-content">{activeRun.blockerCount}</div>
            </div>
            <div className="rounded-lg border border-border bg-surface px-3 py-2">
              <div className="text-xs uppercase tracking-wide text-content-muted">High</div>
              <div className="mt-1 text-lg font-semibold text-content">{activeRun.highCount}</div>
            </div>
            <div className="rounded-lg border border-border bg-surface px-3 py-2">
              <div className="text-xs uppercase tracking-wide text-content-muted">Medium</div>
              <div className="mt-1 text-lg font-semibold text-content">{activeRun.mediumCount}</div>
            </div>
            <div className="rounded-lg border border-border bg-surface px-3 py-2">
              <div className="text-xs uppercase tracking-wide text-content-muted">Low</div>
              <div className="mt-1 text-lg font-semibold text-content">{activeRun.lowCount}</div>
            </div>
            <div className="rounded-lg border border-border bg-surface px-3 py-2">
              <div className="text-xs uppercase tracking-wide text-content-muted">Manual review</div>
              <div className="mt-1 text-lg font-semibold text-content">{activeRun.needsManualReviewCount}</div>
            </div>
          </div>

          {!activeRun.findings.length ? (
            <div className="rounded-lg border border-border bg-surface px-4 py-3 text-sm text-content">
              No findings. This run passed the implemented Meta QA checks.
            </div>
          ) : (
            <div className="space-y-3">
              {activeRun.findings.map((finding) => (
                <div key={finding.id} className="rounded-lg border border-border bg-surface px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={severityTone(finding.severity)}>{finding.severity}</Badge>
                    <Badge tone={findingStatusTone(finding.status)}>{finding.status.replace(/_/g, " ")}</Badge>
                    <div className="text-sm font-semibold text-content">{finding.ruleId}</div>
                    <div className="text-sm text-content">{finding.title}</div>
                  </div>
                  <div className="mt-2 text-sm text-content-muted">{finding.message}</div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-content-muted">
                    <span>Artifact {finding.artifactType}</span>
                    {finding.artifactRef ? <span className="font-mono">{finding.artifactRef}</span> : null}
                    <span>Source {finding.sourceTitle}</span>
                  </div>
                  {finding.fixGuidance.length ? (
                    <div className="mt-2 text-sm text-content-muted">
                      Fix: {finding.fixGuidance.join(" ")}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )}

          <details className="rounded-lg border border-border bg-surface">
            <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-content">
              Open full markdown report
            </summary>
            <div className="border-t border-border py-4">
              <div className="max-h-[560px] overflow-auto">
                <MarkdownViewer content={activeRun.reportMarkdown} className="max-w-none px-4 sm:px-4" />
              </div>
            </div>
          </details>
        </div>
      ) : null}
    </div>
  );
}
