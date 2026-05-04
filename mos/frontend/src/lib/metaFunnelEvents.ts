import type { RuntimeTrackingEvent } from "./funnelTracking";

export type MetaPixelRuntimeEvent = {
  eventName: string;
  params?: Record<string, unknown>;
  method?: "track" | "trackCustom";
};

export const CTA_LINK_CLICK_EVENT_NAME = "CTA Link Click";

function pageViewParams(event: RuntimeTrackingEvent) {
  const pageStage =
    typeof event.props?.pageStage === "string" ? event.props.pageStage.trim() : "";
  return pageStage ? { page_stage: pageStage } : undefined;
}

function isFromPresale(event: RuntimeTrackingEvent): boolean {
  return event.props?.fromPresale === true;
}

function checkoutParams(event: RuntimeTrackingEvent) {
  const params: Record<string, unknown> = {
    content_type: "product",
    num_items: 1,
  };
  const variantId =
    typeof event.props?.variantId === "string" ? event.props.variantId.trim() : "";
  if (variantId) {
    params.content_ids = [variantId];
  }
  return params;
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
      isFromPresale(event)
        ? {
            eventName: "EnteredSales",
            method: "trackCustom",
            params: pageViewParams(event),
          }
        : {
            eventName: "ViewContent",
            params: pageViewParams(event),
          },
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
  if (event.eventType === "custom_page_click") {
    return [{
      eventName: CTA_LINK_CLICK_EVENT_NAME,
      method: "trackCustom",
      params: event.props || {},
    }];
  }
  if (event.eventType === "checkout_started") {
    return [{ eventName: "InitiateCheckout", params: checkoutParams(event) }];
  }
  return [];
}
