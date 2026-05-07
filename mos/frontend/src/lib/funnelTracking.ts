import type { PublicFunnelStage } from "@/types/funnels";

export type RuntimeTrackingEvent =
  | { eventType: "presell_page_view"; props?: Record<string, unknown> }
  | { eventType: "pre_sales_page_view"; props?: Record<string, unknown> }
  | { eventType: "sales_page_view"; props?: Record<string, unknown> }
  | { eventType: "checkout_page_view"; props?: Record<string, unknown> }
  | { eventType: "thank_you_page_view"; props?: Record<string, unknown> }
  | { eventType: "custom_page_view"; props?: Record<string, unknown> }
  | { eventType: "pre_sales_to_sales_click"; props?: Record<string, unknown> }
  | { eventType: "sales_to_checkout_click"; props?: Record<string, unknown> }
  | { eventType: "checkout_click"; props?: Record<string, unknown> }
  | { eventType: "checkout_redirect_started"; props?: Record<string, unknown> }
  | { eventType: "checkout_pagehide"; props?: Record<string, unknown> }
  | { eventType: "checkout_visibility_hidden"; props?: Record<string, unknown> }
  | { eventType: "custom_page_click"; props?: Record<string, unknown> }
  | { eventType: "qualified_session"; props?: Record<string, unknown> }
  | { eventType: "scroll_depth"; props?: Record<string, unknown> }
  | { eventType: "section_view"; props?: Record<string, unknown> }
  | { eventType: "proof_view"; props?: Record<string, unknown> }
  | { eventType: "cta_view"; props?: Record<string, unknown> }
  | { eventType: "offer_stack_view"; props?: Record<string, unknown> }
  | { eventType: "value_stack_view"; props?: Record<string, unknown> }
  | { eventType: "price_reveal_view"; props?: Record<string, unknown> }
  | { eventType: "selector_interaction"; props?: Record<string, unknown> }
  | { eventType: "subscription_selected"; props?: Record<string, unknown> }
  | { eventType: "guarantee_view"; props?: Record<string, unknown> }
  | { eventType: "trust_element_view"; props?: Record<string, unknown> }
  | { eventType: "product_detail_interaction"; props?: Record<string, unknown> }
  | { eventType: "quiz_lead_viewed"; props?: Record<string, unknown> }
  | { eventType: "quiz_question_viewed"; props?: Record<string, unknown> }
  | { eventType: "quiz_option_presented"; props?: Record<string, unknown> }
  | { eventType: "quiz_option_selected"; props?: Record<string, unknown> }
  | { eventType: "quiz_option_deselected"; props?: Record<string, unknown> }
  | { eventType: "quiz_question_submitted"; props?: Record<string, unknown> }
  | { eventType: "quiz_completed"; props?: Record<string, unknown> }
  | { eventType: "quiz_result_viewed"; props?: Record<string, unknown> }
  | { eventType: "quiz_mechanism_viewed"; props?: Record<string, unknown> }
  | { eventType: "quiz_proof_viewed"; props?: Record<string, unknown> }
  | { eventType: "quiz_recommendation_viewed"; props?: Record<string, unknown> }
  | { eventType: "quiz_cta_viewed"; props?: Record<string, unknown> };

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
