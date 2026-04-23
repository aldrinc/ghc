import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Callout } from "@/components/ui/callout";
import { useMetaPublishContext, buildAdSetForm, formatDate, shortId } from "./MetaPublishProvider";
import { MetaPublishValidationResults } from "./MetaPublishValidationResults";
import { MetaPublishHistoryPanel } from "./MetaPublishHistoryPanel";
import { SelectWithCustom } from "./SelectWithCustom";
import { SpecialAdCategoriesCheckboxGroup } from "./SpecialAdCategoriesCheckboxGroup";
import { CountryTierButtons } from "./CountryTierButtons";
import { PlacementPresetButtons } from "./PlacementPresetButtons";
import {
  META_CAMPAIGN_OBJECTIVES,
  META_BUYING_TYPES,
  META_OPTIMIZATION_GOALS,
  META_BILLING_EVENTS,
  META_CUSTOM_EVENT_TYPES,
  META_DEFAULT_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS,
} from "@/lib/metaAdsConstants";

type MetaPublishBudgetScope = "campaign" | "adset" | "mixed";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <div className="text-xs font-medium text-content-muted">{label}</div>
      {children}
    </label>
  );
}

function resolveDraftBudgetScope(
  forms: Record<string, ReturnType<typeof buildAdSetForm>>,
  specs: ReturnType<typeof useMetaPublishContext>["includedAdSetSpecs"],
  pageName?: string | null,
): MetaPublishBudgetScope {
  let sawCampaignBudget = false;
  let sawAdSetBudget = false;
  specs.forEach((spec) => {
    const form = forms[spec.id] || buildAdSetForm(spec, { pageName });
    const hasAdSetBudget = form.dailyBudget.trim() !== "" || form.lifetimeBudget.trim() !== "";
    if (hasAdSetBudget) {
      sawAdSetBudget = true;
    } else {
      sawCampaignBudget = true;
    }
  });
  if (sawCampaignBudget && sawAdSetBudget) return "mixed";
  if (sawAdSetBudget) return "adset";
  return "campaign";
}

function formatBudgetScopeLabel(scope: MetaPublishBudgetScope): string {
  if (scope === "campaign") return "Campaign budget (CBO)";
  if (scope === "adset") return "Ad set budgets (ABO)";
  return "Mixed budget scopes";
}

function formatMinorUnitsBudget(value: string | number | null | undefined): string | null {
  if (value == null) return null;
  if (typeof value === "string") {
    const cleaned = value.trim();
    if (!/^-?\d+$/.test(cleaned)) return null;
    const numericValue = Number(cleaned);
    return Number.isFinite(numericValue) ? `$${(numericValue / 100).toFixed(2)}/day (${numericValue} minor units)` : null;
  }
  const numericValue = value;
  if (!Number.isFinite(numericValue)) return null;
  return `$${(numericValue / 100).toFixed(2)}/day (${numericValue} minor units)`;
}

export function MetaPublishConfigPanel() {
  const {
    includedPackageItems,
    excludedPackageCount,
    requiresFunnelScope,
    activeFunnelId,
    latestGenerationKey,
    selectionLoading,
    availableBucketCount,
    includedAdSetSpecs,
    config,
    publishCampaignForm,
    publishBucketCount,
    updatePublishCampaignField,
    setPublishBucketCount,
    updatePublishBucketDestinationUrl,
    publishAdSetForms,
    updatePublishAdSetField,
    publishFormError,
    publishValidation,
    publishValidationPending,
    publishPending,
    handleValidatePublishPlan,
    handlePublishToMeta,
  } = useMetaPublishContext();
  const hasValidatedWorkspacePixel = Boolean(config?.pixelId && config?.validationStatus === "valid" && config?.lastValidatedAt);
  const draftBudgetScope = useMemo(
    () => resolveDraftBudgetScope(publishAdSetForms, includedAdSetSpecs, config?.pageName),
    [config?.pageName, includedAdSetSpecs, publishAdSetForms],
  );
  const campaignBudgetSummary = publishCampaignForm.campaignDailyBudget.trim()
    ? formatMinorUnitsBudget(publishCampaignForm.campaignDailyBudget) || "Enter a whole-number budget in minor units."
    : (formatMinorUnitsBudget(META_DEFAULT_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS) || "Enter a campaign budget.");

  if (selectionLoading) {
    return <div className="px-4 py-3 text-sm text-content-muted">Loading final Meta package…</div>;
  }
  if (!latestGenerationKey) {
    return <div className="px-4 py-3 text-sm text-content-muted">No latest generation is available yet.</div>;
  }
  if (requiresFunnelScope && !activeFunnelId) {
    return (
      <Callout variant="warning" size="sm">
        Pick one funnel to configure and publish the Meta package for this generation.
      </Callout>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary */}
      <Callout variant={includedPackageItems.length > 0 ? "info" : "warning"} size="sm">
        {includedPackageItems.length > 0
          ? `${includedPackageItems.length} creative(s) included in the final package.${excludedPackageCount ? ` ${excludedPackageCount} excluded.` : ""}`
          : "All latest-generation creatives are currently excluded. Return to Review and restore the creatives you want to send to Meta."}
      </Callout>

      {/* Header + actions */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold text-content">Publish setup</div>
          <div className="text-sm text-content-muted">
            Configure campaign and ad set settings, then validate and publish paused to Meta.
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={() => void handleValidatePublishPlan()} disabled={publishValidationPending || publishPending}>
            {publishValidationPending ? "Validating…" : "Validate publish plan"}
          </Button>
          <Button variant="primary" size="sm" onClick={() => void handlePublishToMeta()} disabled={publishPending || publishValidationPending}>
            {publishPending ? "Publishing…" : "Publish paused to Meta"}
          </Button>
        </div>
      </div>

      {/* Campaign config */}
      <section className="space-y-3">
        <div className="text-xs font-semibold uppercase tracking-wider text-content-muted">Campaign</div>
        <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
          <Field label="Campaign name">
            <Input
              value={publishCampaignForm.campaignName}
              onChange={(e) => updatePublishCampaignField("campaignName", e.target.value)}
              placeholder="[3/19/26] - [Campaign] - [CBO] - [Broad/Int]"
            />
          </Field>
          <Field label="Publish base URL">
            <Input value={publishCampaignForm.publishBaseUrl} onChange={(e) => updatePublishCampaignField("publishBaseUrl", e.target.value)} placeholder="https://shop.example.com" />
          </Field>
          <Field label="Objective">
            <SelectWithCustom
              options={META_CAMPAIGN_OBJECTIVES}
              value={publishCampaignForm.campaignObjective}
              onValueChange={(v) => updatePublishCampaignField("campaignObjective", v)}
              placeholder="Select objective"
            />
          </Field>
          <Field label="Buying type">
            <SelectWithCustom
              options={META_BUYING_TYPES}
              value={publishCampaignForm.buyingType}
              onValueChange={(v) => updatePublishCampaignField("buyingType", v)}
              placeholder="Select buying type"
            />
          </Field>
          <Field label="Budget scope">
            <div className="flex h-10 items-center rounded-md border border-border bg-surface-2 px-3 text-sm text-content">
              {formatBudgetScopeLabel(draftBudgetScope)}
            </div>
          </Field>
          <Field label="Campaign daily budget">
            <Input
              type="number"
              min="101"
              step="1"
              value={publishCampaignForm.campaignDailyBudget}
              onChange={(e) => updatePublishCampaignField("campaignDailyBudget", e.target.value)}
              placeholder={String(META_DEFAULT_CAMPAIGN_DAILY_BUDGET_MINOR_UNITS)}
            />
          </Field>
          <Field label="Bucket count">
            <Input
              type="number"
              min="1"
              max="5"
              step="1"
              value={publishCampaignForm.bucketCount}
              onChange={(e) => setPublishBucketCount(e.target.value)}
              placeholder="5"
            />
          </Field>
          <div className="sm:col-span-2 space-y-1">
            <div className="text-xs font-medium text-content-muted">Special ad categories</div>
            <SpecialAdCategoriesCheckboxGroup
              value={publishCampaignForm.specialAdCategories}
              onChange={(v) => updatePublishCampaignField("specialAdCategories", v)}
            />
          </div>
        </div>
        <Callout variant={draftBudgetScope === "mixed" ? "warning" : "info"} size="sm">
          {draftBudgetScope === "campaign"
            ? `This draft will publish as a campaign-budgeted CBO launch. Current campaign daily budget: ${campaignBudgetSummary}.`
            : draftBudgetScope === "adset"
              ? "This draft currently uses ad set budgets because at least one linked ad set has its own daily or lifetime budget. The campaign daily budget stays visible here, but Meta will ignore it until all ad set budgets are blank."
              : "This draft mixes campaign-level and ad-set budgets. Publish validation will block until every linked ad set uses the same budget scope."}
        </Callout>
        <Callout variant="info" size="sm">
          This temporary launch path can use {publishBucketCount} bucket{publishBucketCount === 1 ? "" : "s"} instead of the default five. The current package exposes {availableBucketCount} reusable bucket spec{availableBucketCount === 1 ? "" : "s"}.
        </Callout>
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-content-muted">Bucket Destination Overrides</div>
          <div className="text-sm text-content-muted">
            Optional temporary routing override. If you fill one bucket URL, fill all {publishBucketCount}. mOS will apply these URLs at creative publish time, one per bucket.
          </div>
          <div className="grid gap-3">
            {Array.from({ length: publishBucketCount }, (_, index) => {
              const bucketIndex = index + 1;
              const bucketSpec = includedAdSetSpecs[index];
              return (
                <Field
                  key={`bucket-destination-${bucketIndex}`}
                  label={`${bucketSpec?.name || `CBO Bucket ${bucketIndex}`} destination URL`}
                >
                  <Input
                    value={publishCampaignForm.bucketDestinationUrls[index] || ""}
                    onChange={(e) => updatePublishBucketDestinationUrl(bucketIndex, e.target.value)}
                    placeholder="https://example.com/presales-variant"
                  />
                </Field>
              );
            })}
          </div>
        </div>
      </section>

      {/* Divider */}
      <hr className="border-border" />

      {/* Ad set specs */}
      <section className="space-y-4">
        <div className="text-xs font-semibold uppercase tracking-wider text-content-muted">Ad Sets</div>
        <Callout variant={hasValidatedWorkspacePixel ? "info" : "warning"} size="sm">
          {hasValidatedWorkspacePixel
            ? `Active workspace Meta config last synced from Meta on ${formatDate(config?.lastValidatedAt)}. If Pixel ID is left blank, mOS will use that validated pixel (${config?.pixelId}).`
            : config?.validationStatus === "invalid"
              ? `Active workspace Meta config validation is invalid${config?.lastValidationError ? `: ${config.lastValidationError}` : ""}. mOS will not auto-fill Pixel ID until the workspace config is revalidated.`
              : "Active workspace Meta config has not been validated against Meta yet. mOS will not auto-fill Pixel ID until that validation runs."}
        </Callout>
        {includedAdSetSpecs.length ? (
          <Callout variant="info" size="sm">
            mOS auto-distributes included creatives across these {includedAdSetSpecs.length} campaign-scoped CBO buckets at publish time. One ad goes to one bucket, and the split is deterministic rather than experiment-bound.
          </Callout>
        ) : null}
        {includedAdSetSpecs.length ? (
          <div className="space-y-5">
            {includedAdSetSpecs.map((spec) => {
              const form = publishAdSetForms[spec.id] || buildAdSetForm(spec, { pageName: config?.pageName });
              const usesWebsiteConversions = form.optimizationGoal.trim().toUpperCase() === "OFFSITE_CONVERSIONS";
              return (
                <div key={`publish-adset-${spec.id}`} className="space-y-3 rounded-lg border border-border p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-sm font-semibold text-content">{spec.name || spec.id}</div>
                    <Badge tone="neutral">{shortId(spec.id, 5)}</Badge>
                  </div>

                  <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                    <Field label="Name">
                      <Input value={form.name} onChange={(e) => updatePublishAdSetField(spec.id, "name", e.target.value)} />
                    </Field>
                    <Field label="Optimization goal">
                      <SelectWithCustom
                        options={META_OPTIMIZATION_GOALS}
                        value={form.optimizationGoal}
                        onValueChange={(v) => updatePublishAdSetField(spec.id, "optimizationGoal", v)}
                        placeholder="Select goal"
                      />
                    </Field>
                    <Field label="Billing event">
                      <SelectWithCustom
                        options={META_BILLING_EVENTS}
                        value={form.billingEvent}
                        onValueChange={(v) => updatePublishAdSetField(spec.id, "billingEvent", v)}
                        placeholder="Select event"
                      />
                    </Field>
                    <Field label="Conversion domain">
                      <Input value={form.conversionDomain} onChange={(e) => updatePublishAdSetField(spec.id, "conversionDomain", e.target.value)} placeholder="Optional" />
                    </Field>
                    <Field label="Daily budget">
                      <Input value={form.dailyBudget} onChange={(e) => updatePublishAdSetField(spec.id, "dailyBudget", e.target.value)} placeholder="Leave blank for campaign CBO" />
                    </Field>
                    <Field label="Lifetime budget">
                      <Input value={form.lifetimeBudget} onChange={(e) => updatePublishAdSetField(spec.id, "lifetimeBudget", e.target.value)} placeholder="Leave blank for campaign CBO" />
                    </Field>
                    <Field label="DSA beneficiary">
                      <Input
                        value={form.dsaBeneficiary}
                        onChange={(e) => updatePublishAdSetField(spec.id, "dsaBeneficiary", e.target.value)}
                        placeholder={config?.pageName || "Defaults to page name"}
                      />
                    </Field>
                    <Field label="DSA payor">
                      <Input
                        value={form.dsaPayor}
                        onChange={(e) => updatePublishAdSetField(spec.id, "dsaPayor", e.target.value)}
                        placeholder={config?.pageName || "Defaults to page name"}
                      />
                    </Field>
                    <Field label="Start time">
                      <Input type="datetime-local" value={form.startTime} onChange={(e) => updatePublishAdSetField(spec.id, "startTime", e.target.value)} />
                    </Field>
                    <Field label="End time">
                      <Input type="datetime-local" value={form.endTime} onChange={(e) => updatePublishAdSetField(spec.id, "endTime", e.target.value)} />
                    </Field>
                  </div>

                  <div className="text-xs text-content-muted">
                    Bid caps are no longer used in mOS. Saving this publish config clears any legacy bid-cap value on the linked ad set spec.
                  </div>

                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <div className="text-xs font-medium text-content-muted">Attribution spec JSON</div>
                      <Textarea
                        value={form.attributionSpecJson}
                        onChange={(e) => updatePublishAdSetField(spec.id, "attributionSpecJson", e.target.value)}
                        placeholder='[{"event_type":"CLICK_THROUGH","window_days":7}]'
                      />
                      <div className="text-xs text-content-muted">
                        Broad/Int default is 7-day click, 1-day view, and 1-day engaged video view. This JSON is stored on the ad set spec and sent during publish.
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <div className="text-xs font-medium text-content-muted">Targeting JSON</div>
                      <CountryTierButtons
                        targetingJson={form.targetingJson}
                        onTargetingJsonChange={(v) => updatePublishAdSetField(spec.id, "targetingJson", v)}
                      />
                      <Textarea value={form.targetingJson} onChange={(e) => updatePublishAdSetField(spec.id, "targetingJson", e.target.value)} placeholder='{"geo_locations":{"countries":["US"]}}' />
                    </div>
                    <div className="space-y-1.5">
                      <div className="text-xs font-medium text-content-muted">Placements</div>
                      <PlacementPresetButtons
                        placementsJson={form.placementsJson}
                        onPlacementsJsonChange={(v) => updatePublishAdSetField(spec.id, "placementsJson", v)}
                      />
                      <Textarea
                        value={form.placementsJson}
                        onChange={(e) => updatePublishAdSetField(spec.id, "placementsJson", e.target.value)}
                        placeholder="{}"
                      />
                      <div className="text-xs text-content-muted">
                        New ad sets default to the Broad/Int launch template: US, CA, GB, AU with Advantage Audience, relaxed brand safety, and Automatic placements. Edit the JSON only when you want to deviate from that baseline.
                      </div>
                    </div>
                    <div className="text-xs text-content-muted">
                      DSA beneficiary and payor default to the active Meta page name when left blank. Edit them here if the advertiser or payer should be different.
                    </div>
                    {usesWebsiteConversions ? (
                      <div className="space-y-3 rounded-md border border-border bg-surface-2 p-3">
                        <div className="space-y-1">
                          <div className="text-xs font-medium text-content-muted">Website conversion settings</div>
                          <div className="text-xs text-content-muted">
                            mOS builds Meta&apos;s promoted object from these fields instead of asking for raw JSON.
                          </div>
                        </div>
                        <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
                          <Field label="Pixel ID">
                            <Input
                              value={form.promotedPixelId}
                              onChange={(e) => updatePublishAdSetField(spec.id, "promotedPixelId", e.target.value)}
                              placeholder={hasValidatedWorkspacePixel ? (config?.pixelId || "Validated workspace pixel") : "Enter Pixel ID"}
                            />
                          </Field>
                          <Field label="Conversion event">
                            <SelectWithCustom
                              options={META_CUSTOM_EVENT_TYPES}
                              value={form.promotedCustomEventType}
                              onValueChange={(v) => updatePublishAdSetField(spec.id, "promotedCustomEventType", v)}
                              placeholder="Select event"
                            />
                          </Field>
                        </div>
                        <div className="text-xs text-content-muted">
                          {hasValidatedWorkspacePixel
                            ? `If Pixel ID is left blank, mOS will use the validated workspace pixel (${config?.pixelId}).`
                            : "If Pixel ID is left blank, validation will fail until the workspace config is validated against Meta or a pixel ID is entered explicitly."}
                        </div>
                        <div className="text-xs text-content-muted">
                          Conversion event is a saved mOS publish setting. It is not fetched from Meta, so it must already exist on the ad set spec or be chosen here explicitly.
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-content-muted">
                        Promoted object fields are hidden because this ad set is not optimizing for website conversions.
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-border px-4 py-4 text-sm text-content-muted">
            Included creatives do not have linked Meta ad set specs yet.
          </div>
        )}
      </section>

      {publishFormError ? <div className="text-sm text-danger">{publishFormError}</div> : null}
      {publishValidation ? <MetaPublishValidationResults /> : null}

      {/* Publish history */}
      <MetaPublishHistoryPanel />
    </div>
  );
}
