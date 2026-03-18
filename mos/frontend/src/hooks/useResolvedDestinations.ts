import { useMemo } from "react";
import type { CampaignDeliveryConfig, DestinationType } from "@/types/delivery";
import { resolveConfiguredShopHostedOrigin, resolveWindowShopHostedOrigin } from "@/lib/shopHostedFunnels";

type ResolvedDestinations = {
  destinations: Map<DestinationType, string>;
  isResolved: boolean;
  validationStatus: CampaignDeliveryConfig["validationStatus"];
};

/**
 * Resolves destination URLs regardless of delivery mode.
 *
 * For internal_funnel: resolves via shop-hosted funnel URL pattern.
 * For external_urls: returns the validated config URLs.
 *
 * Consumed by publish platform adapters to populate ad destination URLs.
 */
export function useResolvedDestinations(
  deliveryConfig: CampaignDeliveryConfig,
  funnelSlug?: string | null,
  productSlug?: string | null,
  shopDomain?: string | null,
): ResolvedDestinations {
  return useMemo(() => {
    const destinations = new Map<DestinationType, string>();

    if (deliveryConfig.deliveryMode === "external_urls") {
      if (deliveryConfig.preSalesUrl) destinations.set("pre_sales", deliveryConfig.preSalesUrl);
      if (deliveryConfig.salesUrl) destinations.set("sales", deliveryConfig.salesUrl);
      if (deliveryConfig.checkoutUrl) destinations.set("checkout", deliveryConfig.checkoutUrl);
      if (deliveryConfig.thankYouUrl) destinations.set("thank_you", deliveryConfig.thankYouUrl);

      return {
        destinations,
        isResolved: destinations.size > 0 && deliveryConfig.validationStatus === "valid",
        validationStatus: deliveryConfig.validationStatus,
      };
    }

    // internal_funnel: resolve via shop-hosted origin
    const origin =
      resolveConfiguredShopHostedOrigin(shopDomain ?? null) || resolveWindowShopHostedOrigin();

    if (origin && productSlug && funnelSlug) {
      destinations.set("pre_sales", `${origin}/f/${productSlug}/${funnelSlug}`);
    }

    return {
      destinations,
      isResolved: destinations.size > 0,
      validationStatus: destinations.size > 0 ? "valid" : "not_validated",
    };
  }, [deliveryConfig, funnelSlug, productSlug, shopDomain]);
}
