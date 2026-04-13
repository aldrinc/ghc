import type { PublicFunnelStage } from "@/types/funnels";

export type RuntimeTrackingEvent =
  | { eventType: "Entered Funnel"; props?: Record<string, unknown> }
  | { eventType: "pre_sales_page_view"; props?: Record<string, unknown> }
  | { eventType: "sales_page_view"; props?: Record<string, unknown> }
  | { eventType: "checkout_page_view"; props?: Record<string, unknown> }
  | { eventType: "thank_you_page_view"; props?: Record<string, unknown> }
  | { eventType: "custom_page_view"; props?: Record<string, unknown> }
  | { eventType: "pre_sales_to_sales_click"; props?: Record<string, unknown> }
  | { eventType: "sales_to_checkout_click"; props?: Record<string, unknown> }
  | { eventType: "custom_page_click"; props?: Record<string, unknown> };

const FUNNEL_STAGE_ALIASES: Record<string, PublicFunnelStage> = {
  "pre-sales": "pre_sales",
  presales: "pre_sales",
  presale: "pre_sales",
  "pre-sale": "pre_sales",
  "pre-sales-listicle": "pre_sales",
  sales: "sales",
  "sales-page": "sales",
  "sales-pdp": "sales",
  "sales_pdp": "sales",
  checkout: "checkout",
  "checkout-page": "checkout",
  "thank-you": "thank_you",
  thankyou: "thank_you",
  thank_you: "thank_you",
  "thank-you-page": "thank_you",
};

export function resolvePublicFunnelStage(slug: string | null | undefined): PublicFunnelStage {
  const cleanedSlug = typeof slug === "string" ? slug.trim().toLowerCase() : "";
  if (!cleanedSlug) {
    return "custom";
  }
  if (
    cleanedSlug.startsWith("presales-") ||
    cleanedSlug.startsWith("pre-sales-") ||
    cleanedSlug.startsWith("pre_sales_")
  ) {
    return "pre_sales";
  }
  if (cleanedSlug.startsWith("sales-") || cleanedSlug.startsWith("sales_")) {
    return "sales";
  }
  return FUNNEL_STAGE_ALIASES[cleanedSlug] ?? "custom";
}

export function pageViewEventForStage(
  stage: PublicFunnelStage,
  props?: Record<string, unknown>,
): RuntimeTrackingEvent {
  if (stage === "pre_sales") {
    return { eventType: "pre_sales_page_view", props };
  }
  if (stage === "sales") {
    return { eventType: "sales_page_view", props };
  }
  if (stage === "checkout") {
    return { eventType: "checkout_page_view", props };
  }
  if (stage === "thank_you") {
    return { eventType: "thank_you_page_view", props };
  }
  return { eventType: "custom_page_view", props };
}

export function navigationClickEventForStages({
  fromStage,
  toStage,
  props,
}: {
  fromStage: PublicFunnelStage;
  toStage: PublicFunnelStage;
  props?: Record<string, unknown>;
}): RuntimeTrackingEvent {
  if (fromStage === "pre_sales" && toStage === "sales") {
    return {
      eventType: "pre_sales_to_sales_click",
      props: {
        fromStage,
        toStage,
        ...props,
      },
    };
  }
  return {
    eventType: "custom_page_click",
    props: {
      fromStage,
      toStage,
      ...props,
    },
  };
}

export function checkoutClickEventForStage({
  fromStage,
  props,
}: {
  fromStage: PublicFunnelStage;
  props?: Record<string, unknown>;
}): RuntimeTrackingEvent {
  if (fromStage === "sales") {
    return {
      eventType: "sales_to_checkout_click",
      props: {
        fromStage,
        toStage: "checkout",
        ...props,
      },
    };
  }
  return {
    eventType: "custom_page_click",
    props: {
      fromStage,
      toStage: "checkout",
      ...props,
    },
  };
}
