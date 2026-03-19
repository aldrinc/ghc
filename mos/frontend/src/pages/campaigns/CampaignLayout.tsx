import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { useCampaign } from "@/api/campaigns";
import { CampaignProvider, useCampaignContextOptional } from "@/contexts/CampaignContext";
import { useProductContext } from "@/contexts/ProductContext";
import { useCampaignPipeline } from "@/hooks/useCampaignPipeline";
import { CampaignPipelineStepper } from "@/components/campaigns/CampaignPipelineStepper";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const TABS = [
  { to: "overview", label: "Overview" },
  { to: "strategy", label: "Strategy" },
  { to: "angles", label: "Angles" },
  { to: "delivery", label: "Delivery" },
  { to: "creative", label: "Creative" },
  { to: "publish", label: "Publish" },
] as const;

export function CampaignLayout() {
  const { campaignId } = useParams();

  if (!campaignId) {
    return (
      <div className="space-y-4 text-base">
        <PageHeader title="Campaign detail" description="Campaign ID is required to load this view." />
        <div className="border border-border bg-transparent px-4 py-3 text-base text-danger">
          Campaign ID missing from the URL.
        </div>
      </div>
    );
  }

  return (
    <CampaignProvider campaignId={campaignId}>
      <CampaignLayoutInner campaignId={campaignId} />
    </CampaignProvider>
  );
}

function CampaignLayoutInner({ campaignId }: { campaignId: string }) {
  const navigate = useNavigate();
  const ctx = useCampaignContextOptional();
  const { product, selectProduct } = useProductContext();
  const { data: campaign, isLoading, isError } = useCampaign(campaignId);

  if (isLoading) {
    return (
      <div className="space-y-6 text-base">
        <div className="space-y-2">
          <Skeleton className="h-7 w-64" />
          <Skeleton className="h-4 w-48" />
        </div>
        <div className="flex gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-20 rounded-full" />
          ))}
        </div>
        <div className="flex gap-1 border-b border-border pb-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-5 w-16" />
          ))}
        </div>
        <div className="space-y-4">
          <Skeleton className="h-32 w-full rounded-md" />
          <Skeleton className="h-24 w-full rounded-md" />
        </div>
      </div>
    );
  }

  if (isError || !campaign) {
    return (
      <div className="space-y-4 text-base">
        <PageHeader title="Campaign detail" description="Campaign detail could not be loaded." />
        <div className="border border-border bg-transparent px-4 py-3 text-base text-danger">
          Campaign not found.
        </div>
      </div>
    );
  }

  const workspaceName = ctx?.workspaceName;
  const campaignProductLabel = ctx?.campaignProductLabel;
  const strategyLaunch = ctx?.campaignLaunches?.find((l) => l.angle_run_id);
  const productMismatch =
    Boolean(campaign.product_id) && Boolean(product?.id) && campaign.product_id !== product?.id;
  const productMissing = Boolean(campaign.product_id) && !product?.id;

  return (
    <div className="space-y-6 text-base">
      <PageHeader
        title={campaign.name}
        description={
          workspaceName
            ? `${workspaceName}${campaignProductLabel ? ` · ${campaignProductLabel}` : ""} · Campaign detail`
            : "Campaign detail"
        }
        actions={
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => navigate("/campaigns")}>
              Back to campaigns
            </Button>
          </div>
        }
      >
        <button
          type="button"
          className="mt-1 inline-flex items-center gap-1 text-xs text-content-muted hover:text-content transition-colors"
          title="Copy campaign ID"
          onClick={() => navigator.clipboard.writeText(campaign.id)}
        >
          <span className="font-mono">{campaign.id.slice(0, 8)}…</span>
          <span className="text-[10px]">copy</span>
        </button>
      </PageHeader>

      {strategyLaunch?.angle_run_id ? (
        <div className="text-xs text-content-muted">
          From strategy:{" "}
          <Link to={`/strategy/${strategyLaunch.angle_run_id}`} className="text-accent hover:underline">
            {strategyLaunch.angle_id ? `Angle ${strategyLaunch.angle_id.slice(0, 8)}...` : "View strategy"}
          </Link>
        </div>
      ) : null}

      {ctx ? (
        <PipelineStepperSection campaignId={campaignId} />
      ) : null}

      {productMismatch || productMissing ? (
        <Callout
          variant="warning"
          title="This campaign is scoped to a different product"
          actions={
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                selectProduct(campaign.product_id || "", {
                  title: ctx?.campaignProductLabel ?? undefined,
                  client_id: campaign.client_id,
                })
              }
            >
              Switch to {campaignProductLabel || "campaign product"}
            </Button>
          }
        >
          <>
            This campaign is scoped to{" "}
            <span className="font-semibold text-content">{campaignProductLabel || "a product"}</span>. Switch products to
            review artifacts and planning in context.
          </>
        </Callout>
      ) : null}

      <nav className="flex gap-1 border-b border-border">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end
            className={({ isActive }) =>
              cn(
                "px-3 py-2 text-sm font-medium transition-colors",
                "border-b-2 -mb-px",
                isActive
                  ? "border-accent text-black"
                  : "border-transparent text-content-muted hover:text-content hover:border-border",
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  );
}

function PipelineStepperSection({ campaignId }: { campaignId: string }) {
  const ctx = useCampaignContextOptional();
  const phases = useCampaignPipeline({
    campaignWorkflows: ctx?.campaignWorkflows ?? [],
    hasStrategyArtifact: Boolean(ctx?.strategyArtifact),
    experimentSpecs: ctx?.experimentSpecs ?? [],
    assetBriefs: ctx?.assetBriefs ?? [],
    funnelCount: ctx?.funnels.length ?? 0,
    generatedAssetTotal: ctx?.generatedAssetTotal ?? 0,
  });

  return <CampaignPipelineStepper phases={phases} campaignId={campaignId} />;
}
