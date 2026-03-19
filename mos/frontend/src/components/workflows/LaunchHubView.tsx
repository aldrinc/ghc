import { useState } from "react";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { StatusBadge } from "@/components/StatusBadge";
import {
  DEFAULT_ASSET_BRIEF_TYPES,
  type AssetBriefType,
} from "@/lib/assetBriefTypes";
import type { StrategyV2LaunchRecord } from "@/types/common";
import type { StrategyV2LaunchActionResponse } from "@/api/workflows";

type ProductImageLaunchState = "ready" | "blocked" | "unknown";

type LaunchHubViewProps = {
  /** Launch history */
  launches: StrategyV2LaunchRecord[];

  /** Additional angle options */
  angleOptions: Array<{ id: string; label: string }>;
  launchedAngleIds: Set<string>;

  /** Additional UMS options */
  umsOptions: Array<{ id: string; label: string }>;
  launchedUmsIds: Set<string>;
  defaultCampaignId: string;

  /** Shopify state */
  isShopifyReady: boolean;
  shopifyBlockedReason: string | null;
  productImageState: ProductImageLaunchState;
  productImageStatusMessage: string | null;
  onRefreshProductImage: () => void;
  isLoadingProductImage: boolean;
  productId?: string;

  /** Handlers */
  onLaunchAdditionalAngles: (config: {
    selectedAngleIds: string[];
    channels: string[];
    assetBriefTypes: AssetBriefType[];
  }) => void;
  onLaunchAdditionalUms: (config: {
    campaignId: string;
    umsSelectionIds: string[];
    launchNamePrefix: string;
    channels?: string[];
    assetBriefTypes?: AssetBriefType[];
  }) => void;
  isLaunching: boolean;
  launchError: string | null;
  latestLaunchResponse: StrategyV2LaunchActionResponse | null;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const LAUNCH_TYPE_LABELS: Record<
  StrategyV2LaunchRecord["launch_type"],
  string
> = {
  initial_angle: "Initial",
  additional_angle: "Additional angle",
  additional_ums: "UMS iteration",
};

const LAUNCH_TYPE_TONE: Record<
  StrategyV2LaunchRecord["launch_type"],
  "accent" | "neutral"
> = {
  initial_angle: "accent",
  additional_angle: "neutral",
  additional_ums: "neutral",
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function truncate(value: string, max = 24): string {
  return value.length > max ? `${value.slice(0, max)}...` : value;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LaunchHubView({
  launches,
  angleOptions,
  launchedAngleIds,
  umsOptions,
  launchedUmsIds,
  defaultCampaignId,
  isShopifyReady,
  shopifyBlockedReason,
  productImageState,
  productImageStatusMessage,
  onRefreshProductImage,
  isLoadingProductImage,
  productId,
  onLaunchAdditionalAngles,
  onLaunchAdditionalUms,
  isLaunching,
  launchError,
  latestLaunchResponse,
}: LaunchHubViewProps) {
  // ----- Local state for additional angles -----
  const [selectedAngleIds, setSelectedAngleIds] = useState<string[]>([]);

  // ----- Local state for additional UMS -----
  const [selectedUmsIds, setSelectedUmsIds] = useState<string[]>([]);
  const [launchNamePrefix, setLaunchNamePrefix] = useState("");

  // ----- Derived -----
  const unlaunchedAngles = angleOptions.filter(
    (a) => !launchedAngleIds.has(a.id),
  );
  const unlaunchedUms = umsOptions.filter((u) => !launchedUmsIds.has(u.id));

  const canLaunchAngles =
    isShopifyReady && productImageState !== "blocked" && !isLaunching && selectedAngleIds.length > 0;
  const canLaunchUms =
    isShopifyReady &&
    productImageState !== "blocked" &&
    !isLaunching &&
    selectedUmsIds.length > 0 &&
    launchNamePrefix.trim().length > 0;

  // ----- Handlers -----
  const toggleAngle = (id: string) => {
    setSelectedAngleIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const toggleUms = (id: string) => {
    setSelectedUmsIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const handleLaunchAngles = () => {
    onLaunchAdditionalAngles({
      selectedAngleIds,
      channels: ["facebook"],
      assetBriefTypes: DEFAULT_ASSET_BRIEF_TYPES,
    });
  };

  const handleLaunchUms = () => {
    onLaunchAdditionalUms({
      campaignId: defaultCampaignId,
      umsSelectionIds: selectedUmsIds,
      launchNamePrefix: launchNamePrefix.trim(),
    });
  };

  // ----- Campaign links from latest response -----
  const responseCampaignIds = latestLaunchResponse?.campaign_ids ?? [];

  return (
    <div className="space-y-6">
      {/* ----------------------------------------------------------------- */}
      {/* Error / success feedback                                          */}
      {/* ----------------------------------------------------------------- */}
      {launchError ? (
        <Callout variant="danger" title="Launch failed">
          {launchError}
        </Callout>
      ) : null}

      {latestLaunchResponse ? (
        <Callout variant="success" title="Launch started">
          <div className="mt-1 space-y-2">
            {responseCampaignIds.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {responseCampaignIds.map((cid) => (
                  <Link
                    key={cid}
                    to={`/campaigns/${cid}`}
                    className={buttonClasses({
                      variant: "primary",
                      size: "sm",
                    })}
                  >
                    Go to campaign
                  </Link>
                ))}
              </div>
            ) : null}
          </div>
        </Callout>
      ) : null}

      {/* Shopify warning (non-blocking, just informational) */}
      {!isShopifyReady ? (
        <Callout variant="warning" title="Shopify not ready">
          {shopifyBlockedReason ??
            "Shopify must be connected and ready before launching."}
        </Callout>
      ) : null}

      {productImageState !== "ready" ? (
        <Callout
          variant={productImageState === "unknown" ? "info" : "warning"}
          title={productImageState === "unknown" ? "Primary product image status unavailable" : "Primary product image not ready"}
          actions={
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="xs"
                onClick={onRefreshProductImage}
                disabled={isLoadingProductImage}
              >
                {isLoadingProductImage ? (
                  <>
                    <Loader2 className="animate-spin" />
                    Checking...
                  </>
                ) : (
                  "Refresh"
                )}
              </Button>
              {productId ? (
                <Link
                  to={`/workspaces/products/${productId}`}
                  className={buttonClasses({ variant: "secondary", size: "xs" })}
                >
                  Go to product setup
                </Link>
              ) : null}
            </div>
          }
        >
          {productImageStatusMessage ??
            (productImageState === "unknown"
              ? "We could not verify product image readiness here. Launch will still be validated by the backend."
              : "Add a primary product image in product setup before launching.")}
        </Callout>
      ) : null}

      {/* ----------------------------------------------------------------- */}
      {/* Section 1 — Launch history                                        */}
      {/* ----------------------------------------------------------------- */}
      <div className="ds-card space-y-3">
        <h3 className="text-sm font-semibold text-content">Launch history</h3>

        {launches.length === 0 ? (
          <p className="text-sm text-content-muted">
            No campaigns launched yet.
          </p>
        ) : (
          <div className="space-y-2">
            {launches.map((launch) => (
              <div
                key={launch.id}
                className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-surface-2/50 px-3 py-2 text-xs"
              >
                <Badge tone={LAUNCH_TYPE_TONE[launch.launch_type]}>
                  {LAUNCH_TYPE_LABELS[launch.launch_type]}
                </Badge>

                {launch.campaign_id ? (
                  <Link
                    to={`/campaigns/${launch.campaign_id}`}
                    className="truncate font-medium text-accent hover:underline"
                    title={launch.campaign_id}
                  >
                    {truncate(launch.campaign_id)}
                  </Link>
                ) : (
                  <span className="text-content-muted">No campaign</span>
                )}

                <span
                  className="truncate text-content-muted"
                  title={launch.angle_id}
                >
                  {truncate(launch.angle_id, 18)}
                </span>

                {launch.launch_status ? (
                  <StatusBadge status={launch.launch_status} />
                ) : null}

                <span className="ml-auto whitespace-nowrap text-content-muted">
                  {formatDate(launch.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Section 2 — Launch additional angles                              */}
      {/* ----------------------------------------------------------------- */}
      {unlaunchedAngles.length > 0 ? (
        <div className="ds-card space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-content">
              Launch additional angles
            </h3>
            <p className="mt-0.5 text-xs text-content-muted">
              Launch campaigns for other angles generated during strategy review.
              Each creates a separate campaign.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {angleOptions.map((angle) => {
              const launched = launchedAngleIds.has(angle.id);
              const selected = selectedAngleIds.includes(angle.id);

              return (
                <label
                  key={angle.id}
                  className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors ${
                    launched
                      ? "cursor-default border-border bg-surface-2/40 text-content-muted opacity-60"
                      : selected
                        ? "border-accent bg-accent/5 text-content"
                        : "border-border bg-surface text-content hover:border-accent/40"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border border-border bg-surface text-accent"
                    checked={launched || selected}
                    disabled={launched}
                    onChange={() => toggleAngle(angle.id)}
                  />
                  <span className="min-w-0 truncate">{angle.label}</span>
                  {launched ? (
                    <Badge tone="neutral" className="ml-auto shrink-0">
                      Launched
                    </Badge>
                  ) : null}
                </label>
              );
            })}
          </div>

          <Button
            variant="primary"
            className="w-full"
            disabled={!canLaunchAngles}
            onClick={handleLaunchAngles}
          >
            {isLaunching ? (
              <>
                <Loader2 className="animate-spin" />
                Launching...
              </>
            ) : (
              `Launch selected angles (${selectedAngleIds.length})`
            )}
          </Button>
        </div>
      ) : null}

      {/* ----------------------------------------------------------------- */}
      {/* Section 3 — Add UMS iterations                                    */}
      {/* ----------------------------------------------------------------- */}
      {unlaunchedUms.length > 0 ? (
        <div className="ds-card space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-content">
              Add messaging variations
            </h3>
            <p className="mt-0.5 text-xs text-content-muted">
              Test different messaging propositions on an existing campaign.
              Creates new funnels within the campaign.
            </p>
          </div>

          {/* Target campaign (read-only) */}
          <div>
            <div className="mb-1 text-xs font-medium text-content-muted">
              Target campaign
            </div>
            <div className="truncate rounded-md border border-border bg-surface-2/50 px-3 py-1.5 text-xs text-content-muted">
              {defaultCampaignId || "\u2014"}
            </div>
          </div>

          {/* Launch name prefix */}
          <label className="block">
            <div className="mb-1 text-xs font-medium text-content-muted">
              Launch name prefix <span className="text-danger">*</span>
            </div>
            <input
              type="text"
              className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm placeholder:text-content-muted/50"
              placeholder="e.g. ums-iteration-2"
              value={launchNamePrefix}
              onChange={(e) => setLaunchNamePrefix(e.target.value)}
            />
          </label>

          {/* UMS selection grid */}
          <div className="grid grid-cols-2 gap-2">
            {umsOptions.map((ums) => {
              const launched = launchedUmsIds.has(ums.id);
              const selected = selectedUmsIds.includes(ums.id);

              return (
                <label
                  key={ums.id}
                  className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors ${
                    launched
                      ? "cursor-default border-border bg-surface-2/40 text-content-muted opacity-60"
                      : selected
                        ? "border-accent bg-accent/5 text-content"
                        : "border-border bg-surface text-content hover:border-accent/40"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border border-border bg-surface text-accent"
                    checked={launched || selected}
                    disabled={launched}
                    onChange={() => toggleUms(ums.id)}
                  />
                  <span className="min-w-0 truncate">{ums.label}</span>
                  {launched ? (
                    <Badge tone="neutral" className="ml-auto shrink-0">
                      Launched
                    </Badge>
                  ) : null}
                </label>
              );
            })}
          </div>

          <Button
            variant="primary"
            className="w-full"
            disabled={!canLaunchUms}
            onClick={handleLaunchUms}
          >
            {isLaunching ? (
              <>
                <Loader2 className="animate-spin" />
                Launching...
              </>
            ) : (
              `Launch selected iterations (${selectedUmsIds.length})`
            )}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
