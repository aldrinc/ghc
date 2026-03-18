import type { RuntimeTrackingEvent } from "./funnelTracking";

export type MetaPixelRuntimeEvent = {
  eventName: string;
  params?: Record<string, unknown>;
  method?: "track" | "trackCustom";
};

function pageViewParams(event: RuntimeTrackingEvent) {
  const pageStage =
    typeof event.props?.pageStage === "string" ? event.props.pageStage.trim() : "";
  return pageStage ? { page_stage: pageStage } : undefined;
}

export function mapRuntimeEventToMetaPixelEvents(
  event: RuntimeTrackingEvent,
): MetaPixelRuntimeEvent[] {
  if (event.eventType === "Entered Funnel") {
    return [{ eventName: "Entered Funnel", method: "trackCustom", params: pageViewParams(event) }];
  }
  if (event.eventType === "pre_sales_page_view" || event.eventType === "custom_page_view") {
    return [{ eventName: "PageView", params: pageViewParams(event) }];
  }
  if (event.eventType === "sales_page_view") {
    return [
      { eventName: "PageView", params: pageViewParams(event) },
      { eventName: "ViewContent", params: pageViewParams(event) },
    ];
  }
  if (event.eventType === "checkout_page_view") {
    return [{ eventName: "PageView", params: pageViewParams(event) }];
  }
  if (event.eventType === "thank_you_page_view") {
    return [{ eventName: "PageView", params: pageViewParams(event) }];
  }
  if (event.eventType === "pre_sales_to_sales_click") {
    return [
      {
        eventName: "PreSalesToSalesClick",
        method: "trackCustom",
        params: {
          from_stage: "pre_sales",
          to_stage: "sales",
        },
      },
    ];
  }
  if (event.eventType === "sales_to_checkout_click") {
    const variantId =
      typeof event.props?.variantId === "string" ? event.props.variantId.trim() : "";
    if (variantId) {
      return [{
        eventName: "AddToCart",
        params: {
          content_ids: [variantId],
          content_type: "product",
          num_items: 1,
        },
      }];
    }
  }
  return [];
}
