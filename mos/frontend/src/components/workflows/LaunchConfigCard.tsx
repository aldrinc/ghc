import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Loader2 } from "lucide-react";
import { Button, buttonClasses } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import type { AssetBriefType } from "@/lib/assetBriefTypes";
import {
  DEFAULT_ASSET_BRIEF_TYPES,
  ASSET_BRIEF_TYPE_OPTIONS,
} from "@/lib/assetBriefTypes";
import type { StrategyV2LaunchActionResponse } from "@/api/workflows";

type ProductImageLaunchState = "ready" | "blocked" | "unknown";

type LaunchConfigCardProps = {
  selectedAngleName: string;
  isShopifyReady: boolean;
  shopifyBlockedReason: string | null;
  productImageState: ProductImageLaunchState;
  productImageStatusMessage: string | null;
  isLaunching: boolean;
  onLaunch: (config: {
    channels: string[];
    assetBriefTypes: AssetBriefType[];
    experimentVariantPolicy: string;
  }) => void;
  onRefreshShopify: () => void;
  isLoadingShopify: boolean;
  onRefreshProductImage: () => void;
  isLoadingProductImage: boolean;
  productId?: string;
  latestLaunchResponse: StrategyV2LaunchActionResponse | null;
  launchError: string | null;
};

export function LaunchConfigCard({
  selectedAngleName,
  isShopifyReady,
  shopifyBlockedReason,
  productImageState,
  productImageStatusMessage,
  isLaunching,
  onLaunch,
  onRefreshShopify,
  isLoadingShopify,
  onRefreshProductImage,
  isLoadingProductImage,
  productId,
  latestLaunchResponse,
  launchError,
}: LaunchConfigCardProps) {
  const [assetBriefTypes, setAssetBriefTypes] =
    useState<AssetBriefType[]>(DEFAULT_ASSET_BRIEF_TYPES);
  const [experimentVariantPolicy, setExperimentVariantPolicy] =
    useState("angle_launch_standard_v1");

  const toggleAssetBriefType = (value: AssetBriefType) => {
    setAssetBriefTypes((prev) =>
      prev.includes(value)
        ? prev.filter((item) => item !== value)
        : [...prev, value],
    );
  };

  const canLaunch =
    isShopifyReady && productImageState !== "blocked" && !isLaunching && assetBriefTypes.length > 0;

  const handleLaunch = () => {
    onLaunch({
      channels: ["facebook"],
      assetBriefTypes,
      experimentVariantPolicy,
    });
  };

  const campaignId = latestLaunchResponse?.campaign_ids?.[0];

  return (
    <div className="ds-card space-y-4">
      {/* Shopify status */}
      {isShopifyReady ? (
        <div className="flex items-center gap-2 text-sm text-success">
          <CheckCircle2 className="size-4 shrink-0" />
          <span className="font-medium">Shopify connected</span>
        </div>
      ) : (
        <Callout
          variant="warning"
          title="Shopify not ready"
          actions={
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="xs"
                onClick={onRefreshShopify}
                disabled={isLoadingShopify}
              >
                {isLoadingShopify ? (
                  <>
                    <Loader2 className="animate-spin" />
                    Checking…
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
          {shopifyBlockedReason ||
            "Shopify must be connected and ready before launching."}
        </Callout>
      )}

      {productImageState === "ready" ? (
        <div className="flex items-center gap-2 text-sm text-success">
          <CheckCircle2 className="size-4 shrink-0" />
          <span className="font-medium">Primary product image ready</span>
        </div>
      ) : (
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
                    Checking…
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
          {productImageStatusMessage ||
            (productImageState === "unknown"
              ? "We could not verify product image readiness here. Launch will still be validated by the backend."
              : "Add a primary product image in product setup before launching.")}
        </Callout>
      )}

      {/* Channel */}
      <div>
        <div className="mb-1 text-xs font-medium text-content-muted">
          Channel
        </div>
        <Badge tone="accent">facebook</Badge>
      </div>

      {/* Creative brief types (collapsed by default) */}
      <details className="group">
        <summary className="cursor-pointer text-xs font-medium text-content-muted hover:text-content">
          Customize brief types
        </summary>
        <div className="mt-2 flex flex-wrap gap-3 rounded-md border border-border bg-surface px-3 py-2 text-xs">
          {ASSET_BRIEF_TYPE_OPTIONS.map((option) => (
            <label
              key={option.value}
              className="flex items-center gap-2 text-content"
            >
              <input
                type="checkbox"
                className="h-4 w-4 rounded border border-border bg-surface text-accent"
                checked={assetBriefTypes.includes(option.value)}
                onChange={() => toggleAssetBriefType(option.value)}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
        {!assetBriefTypes.length ? (
          <div className="mt-1 text-[11px] text-danger">
            Select at least one brief type.
          </div>
        ) : null}
      </details>

      {/* Advanced settings (collapsed by default) */}
      <details className="group">
        <summary className="cursor-pointer text-xs font-medium text-content-muted hover:text-content">
          Advanced settings
        </summary>
        <div className="mt-2">
          <label className="block">
            <div className="mb-1 text-[11px] text-content-muted">
              Experiment variant policy
            </div>
            <input
              className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-xs"
              value={experimentVariantPolicy}
              onChange={(event) =>
                setExperimentVariantPolicy(event.target.value)
              }
            />
          </label>
        </div>
      </details>

      {/* Error state */}
      {launchError ? (
        <Callout variant="danger" title="Launch failed">
          {launchError}
        </Callout>
      ) : null}

      {/* Post-launch success */}
      {latestLaunchResponse ? (
        <Callout variant="success" title="Campaign launched">
          <div className="mt-1 space-y-2">
            {campaignId ? (
              <Link
                to={`/campaigns/${campaignId}`}
                className={buttonClasses({ variant: "primary", size: "sm" })}
              >
                Go to campaign
              </Link>
            ) : null}
            <div className="text-xs text-content-muted">
              Stay here to launch more angles.
            </div>
          </div>
        </Callout>
      ) : null}

      {/* Launch button */}
      <div className="space-y-1">
        <Button
          variant="primary"
          className="w-full"
          onClick={handleLaunch}
          disabled={!canLaunch}
        >
          {isLaunching ? (
            <>
              <Loader2 className="animate-spin" />
              Launching…
            </>
          ) : (
            `Launch campaign for ${selectedAngleName || "selected angle"}`
          )}
        </Button>
        <div className="text-center text-[11px] text-content-muted">
          Creates a campaign with funnels, experiments, and creative briefs.
        </div>
      </div>
    </div>
  );
}
