export type RuntimeTrackingEvent = {
  eventType: string;
  props?: Record<string, unknown>;
};

export type MetaPixelRuntimeEvent = {
  eventName: string;
  params?: Record<string, unknown>;
};

export function mapRuntimeEventToMetaPixel(
  event: RuntimeTrackingEvent,
): MetaPixelRuntimeEvent | null {
  if (event.eventType === "page_view") {
    return { eventName: "PageView" };
  }
  if (event.eventType === "funnel_enter") {
    return { eventName: "ViewContent" };
  }
  if (event.eventType === "cta_click") {
    const variantId =
      typeof event.props?.variantId === "string" ? event.props.variantId.trim() : "";
    if (variantId) {
      return {
        eventName: "InitiateCheckout",
        params: {
          content_ids: [variantId],
          content_type: "product",
          num_items: 1,
        },
      };
    }
  }
  return null;
}
