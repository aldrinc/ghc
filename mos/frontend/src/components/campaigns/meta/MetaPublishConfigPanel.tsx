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
} from "@/lib/metaAdsConstants";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <div className="text-xs font-medium text-content-muted">{label}</div>
      {children}
    </label>
  );
}

export function MetaPublishConfigPanel() {
  const {
    includedPackageItems,
    excludedPackageCount,
    requiresFunnelScope,
    activeFunnelId,
    latestGenerationKey,
    selectionLoading,
    includedAdSetSpecs,
    config,
    publishCampaignForm,
    updatePublishCampaignField,
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
            <Input value={publishCampaignForm.campaignName} onChange={(e) => updatePublishCampaignField("campaignName", e.target.value)} placeholder="Honest Herbalist Launch" />
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
          <div className="sm:col-span-2 space-y-1">
            <div className="text-xs font-medium text-content-muted">Special ad categories</div>
            <SpecialAdCategoriesCheckboxGroup
              value={publishCampaignForm.specialAdCategories}
              onChange={(v) => updatePublishCampaignField("specialAdCategories", v)}
            />
          </div>
        </div>
        <p className="text-xs text-content-muted">
          Creates the Meta campaign, ad sets, and ads in <span className="font-semibold text-content">PAUSED</span> status.
        </p>
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
                      <Input value={form.dailyBudget} onChange={(e) => updatePublishAdSetField(spec.id, "dailyBudget", e.target.value)} placeholder="Leave blank for lifetime" />
                    </Field>
                    <Field label="Lifetime budget">
                      <Input value={form.lifetimeBudget} onChange={(e) => updatePublishAdSetField(spec.id, "lifetimeBudget", e.target.value)} placeholder="Leave blank for daily" />
                    </Field>
                    <Field label="Bid amount">
                      <Input value={form.bidAmount} onChange={(e) => updatePublishAdSetField(spec.id, "bidAmount", e.target.value)} placeholder="Optional" />
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

                  <div className="space-y-3">
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
                        placeholder='{"publisher_platforms":["facebook","instagram"],"facebook_positions":["feed"],"instagram_positions":["stream"]}'
                      />
                      <div className="text-xs text-content-muted">
                        New ad sets default to Facebook + Instagram feeds. Choose Automatic to let Meta decide placements, or edit the JSON for an advanced mix.
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
