import type { RuntimeTrackingEvent } from "./funnelTracking";

export type MetaPixelRuntimeEvent = {
  eventName: string;
  params?: Record<string, unknown>;
  method?: "track" | "trackCustom";
  eventId?: string;
};

export const CTA_LINK_CLICK_EVENT_NAME = "CTA Link Click";

type RuntimeTrackingEventLike = {
  eventType: RuntimeTrackingEvent["eventType"];
  props?: Record<string, unknown>;
};

function cleanText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function cleanStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => cleanText(item)).filter(Boolean) as string[];
}

function randomEventIdSegment(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function buildMetaEventId({
  eventName,
  eventType,
  publicationId,
  pageId,
  sessionId,
  index,
}: {
  eventName: string;
  eventType: string;
  publicationId?: string | null;
  pageId?: string | null;
  sessionId?: string | null;
  index: number;
}): string {
  return [
    cleanText(eventName) || "meta",
    cleanText(eventType) || "event",
    cleanText(publicationId) || "publication",
    cleanText(pageId) || "page",
    cleanText(sessionId) || "session",
    String(index),
    randomEventIdSegment(),
  ].join(":");
}

export function attachMetaEventIds(
  events: MetaPixelRuntimeEvent[],
  context: {
    eventType: string;
    publicationId?: string | null;
    pageId?: string | null;
    sessionId?: string | null;
  },
): MetaPixelRuntimeEvent[] {
  return events.map((event, index) => ({
    ...event,
    eventId:
      cleanText(event.eventId) ||
      buildMetaEventId({
        ...context,
        eventName: event.eventName,
        index,
      }),
  }));
}

function pageViewParams(event: RuntimeTrackingEventLike) {
  const pageStage =
    typeof event.props?.pageStage === "string" ? event.props.pageStage.trim() : "";
  return pageStage ? { page_stage: pageStage } : undefined;
}

function checkoutParams(event: RuntimeTrackingEvent) {
  const explicitContentIds = cleanStringArray(event.props?.content_ids || event.props?.contentIds);
  const variantId =
    cleanText(event.props?.variantId) ||
    cleanText(event.props?.variant_id) ||
    cleanText(event.props?.contentId) ||
    cleanText(event.props?.content_id);
  const contentIds = explicitContentIds.length ? explicitContentIds : (variantId ? [variantId] : []);
  const explicitNumItems = Number(event.props?.num_items || event.props?.numItems);
  const params: Record<string, unknown> = {
    content_type: "product",
    num_items: Number.isFinite(explicitNumItems) && explicitNumItems > 0
      ? explicitNumItems
      : Math.max(1, contentIds.length || 1),
  };
  if (contentIds.length) {
    params.content_ids = contentIds;
  }
  return params;
}

export function mapRuntimeEventToMetaPixelEvents(
  event: RuntimeTrackingEventLike,
): MetaPixelRuntimeEvent[] {
  if (event.eventType === "presell_page_view") {
    return [
      { eventName: "EnteredPresales", method: "trackCustom", params: pageViewParams(event) },
      { eventName: "Entered Presales Page", method: "trackCustom", params: pageViewParams(event) },
    ];
  }
  if (event.eventType === "Entered Funnel") {
    return [{ eventName: "Entered Funnel", method: "trackCustom", params: pageViewParams(event) }];
  }
  if (event.eventType === "pre_sales_page_view" || event.eventType === "custom_page_view") {
    return [{ eventName: "PageView", params: pageViewParams(event) }];
  }
  if (event.eventType === "sales_page_view") {
    return [
      { eventName: "PageView", params: pageViewParams(event) },
      { eventName: "Entered Sales Page", method: "trackCustom", params: pageViewParams(event) },
      { eventName: "EnteredSales", method: "trackCustom", params: pageViewParams(event) },
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
  if (event.eventType === "add_to_cart") {
    return [{ eventName: "AddToCart", params: checkoutParams(event as RuntimeTrackingEvent) }];
  }
  if (event.eventType === "sales_to_checkout_click") {
    return [
      {
        eventName: "SalesToCheckoutClick",
        method: "trackCustom",
        params: {
          from_stage: "sales",
          to_stage: "checkout",
        },
      },
      {
        eventName: "SalesToCheckoutClicked",
        method: "trackCustom",
        params: {
          from_stage: "sales",
          to_stage: "checkout",
        },
      },
    ];
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
