import { mapRuntimeEventToMetaPixelEvents } from "./metaFunnelEvents";
import type { RuntimeTrackingEvent } from "./funnelTracking";

declare global {
  interface Window {
    posthog?: PostHogRoot;
  }
}

type PostHogTrackingConfig = {
  posthogProjectApiKey?: string | null;
  posthogApiHost?: string | null;
  posthogUiHost?: string | null;
  posthogDefaults?: string | null;
  posthogPersonProfiles?: "identified_only" | "always" | null;
};

type PostHogInstance = {
  capture?: (eventName: string, props?: Record<string, unknown>) => void;
  register?: (props: Record<string, unknown>) => void;
  __mosFunnelConfigured?: string;
  people?: unknown[];
  push?: (...items: unknown[]) => number;
  toString?: (stub?: number) => string;
  [key: string]: unknown;
};

type PostHogRoot = {
  __SV?: number;
  __loaded?: boolean;
  _i?: unknown[];
  init?: (
    apiKey: string,
    config: Record<string, unknown>,
    instanceName?: string,
  ) => void;
  people?: unknown[];
  push?: (...items: unknown[]) => number;
  toString?: (stub?: number) => string;
  [key: string]: unknown;
};

const POSTHOG_INSTANCE_NAME = "mosFunnel";

function cleanText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function buildPostHogEventId({
  eventName,
  eventType,
  publicationId,
  pageId,
  sessionId,
  index,
}: {
  eventName: string;
  eventType: string;
  publicationId: string | null;
  pageId: string | null;
  sessionId: string | null;
  index: number;
}) {
  return [
    cleanText(eventName) || "capture",
    cleanText(eventType) || "event",
    publicationId || "publication",
    pageId || "page",
    sessionId || "session",
    String(index),
    String(Date.now()),
  ].join(":");
}

function resolvePostHogContentCategory(pageStage: string | null): string | null {
  if (pageStage === "pre_sales") return "pre_sales_page";
  if (pageStage === "sales") return "sales_page";
  if (pageStage === "checkout") return "checkout_page";
  if (pageStage === "thank_you") return "thank_you_page";
  if (pageStage === "custom") return "custom_page";
  return null;
}

function isRuntimeTrackingEventType(value: string): value is RuntimeTrackingEvent["eventType"] {
  return (
    value === "Entered Funnel"
    || value === "pre_sales_page_view"
    || value === "sales_page_view"
    || value === "checkout_page_view"
    || value === "thank_you_page_view"
    || value === "custom_page_view"
    || value === "pre_sales_to_sales_click"
    || value === "sales_to_checkout_click"
    || value === "custom_page_click"
  );
}

function sanitizePostHogProps(props?: Record<string, unknown>) {
  if (!isRecord(props)) {
    return {};
  }
  const nextProps = { ...props };
  delete nextProps.fromPresale;
  return nextProps;
}

function resolvePostHogCaptures({
  eventType,
  publicationId,
  pageId,
  pageStage,
  sessionId,
  props,
  baseProps,
}: {
  eventType: string;
  publicationId: string | null;
  pageId: string | null;
  pageStage: string | null;
  sessionId: string | null;
  props?: Record<string, unknown>;
  baseProps: Record<string, unknown>;
}) {
  const sanitizedProps = sanitizePostHogProps(props);
  if (!isRuntimeTrackingEventType(eventType)) {
    return [
      {
        eventName: eventType,
        eventProps: {
          ...baseProps,
          ...sanitizedProps,
          internal_event_type: eventType,
          $event_id: buildPostHogEventId({
            eventName: eventType,
            eventType,
            publicationId,
            pageId,
            sessionId,
            index: 0,
          }),
        },
      },
    ];
  }

  const contentCategory = resolvePostHogContentCategory(pageStage);
  const metaMappedEvents = mapRuntimeEventToMetaPixelEvents({
    eventType,
    props,
  });
  if (metaMappedEvents.length === 0) {
    return [
      {
        eventName: eventType,
        eventProps: {
          ...baseProps,
          ...sanitizedProps,
          internal_event_type: eventType,
          $event_id: buildPostHogEventId({
            eventName: eventType,
            eventType,
            publicationId,
            pageId,
            sessionId,
            index: 0,
          }),
        },
      },
    ];
  }

  return metaMappedEvents.map((mappedEvent, index) => {
    const eventProps: Record<string, unknown> = {
      ...baseProps,
      ...sanitizedProps,
      ...(mappedEvent.params || {}),
      internal_event_type: eventType,
      $event_id: buildPostHogEventId({
        eventName: mappedEvent.eventName,
        eventType,
        publicationId,
        pageId,
        sessionId,
        index,
      }),
    };
    if (contentCategory) {
      eventProps.content_category = contentCategory;
    }
    if (eventType === "sales_page_view") {
      eventProps.from_presale = props?.fromPresale === true;
    }
    return {
      eventName: mappedEvent.eventName,
      eventProps,
    };
  });
}

function ensurePostHogRoot() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return null;
  }

  const posthog = (window.posthog || []) as PostHogRoot & unknown[];
  if (!posthog.__SV && !(window.posthog && window.posthog.__loaded)) {
    window.posthog = posthog;
    posthog._i = [];
    posthog.init = function init(apiKey, config, instanceName) {
      function stub(target: PostHogInstance & unknown[], methodName: string) {
        const segments = methodName.split(".");
        if (segments.length === 2) {
          target = target[segments[0]] as PostHogInstance & unknown[];
          methodName = segments[1];
        }
        target[methodName] = (...args: unknown[]) => {
          target.push?.([methodName, ...args]);
        };
      }

      const script = document.createElement("script");
      script.type = "text/javascript";
      script.crossOrigin = "anonymous";
      script.async = true;
      script.src = String(config.api_host || "")
        .replace(".i.posthog.com", "-assets.i.posthog.com")
        .concat("/static/array.js");

      const firstScript = document.getElementsByTagName("script")[0];
      if (firstScript?.parentNode) {
        firstScript.parentNode.insertBefore(script, firstScript);
      } else {
        (document.head || document.body || document.documentElement)?.appendChild(script);
      }

      let target = posthog as PostHogInstance & unknown[];
      let resolvedName = "posthog";
      if (typeof instanceName !== "undefined") {
        target = ((posthog[instanceName] as PostHogInstance & unknown[]) || []) as PostHogInstance & unknown[];
        posthog[instanceName] = target;
        resolvedName = instanceName;
      } else {
        instanceName = "posthog";
      }
      target.people = target.people || [];
      target.toString = (stubbed?: number) => {
        let result = "posthog";
        if (resolvedName !== "posthog") {
          result += `.${resolvedName}`;
        }
        if (!stubbed) {
          result += " (stub)";
        }
        return result;
      };
      (target.people as { toString?: () => string }).toString = () => `${target.toString?.(1)}.people (stub)`;
      const methods =
        "Ir Sr init jr $r Ci qr Hr Dr capture calculateEventProperties Wr register register_once register_for_session unregister unregister_for_session Qr getFeatureFlag getFeatureFlagPayload getFeatureFlagResult isFeatureEnabled reloadFeatureFlags updateFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSurveysLoaded onSessionId getSurveys getActiveMatchingSurveys renderSurvey displaySurvey cancelPendingSurvey canRenderSurvey canRenderSurveyAsync tn identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset setIdentity clearIdentity get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException captureLog startExceptionAutocapture stopExceptionAutocapture loadToolbar get_property getSessionProperty Jr Yr createPersonProfile setInternalOrTestUser Kr Pr nn opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing get_explicit_consent_status is_capturing clear_opt_in_out_capturing zr debug ki Xr getPageViewId captureTraceFeedback captureTraceMetric Mr"
          .split(" ");
      for (const method of methods) {
        stub(target, method);
      }
      posthog._i?.push([apiKey, config, instanceName]);
    };
    posthog.__SV = 1;
  }
  return posthog;
}

export function ensurePostHogInstance({
  tracking,
  distinctId,
  productSlug,
  funnelSlug,
  publicationId,
}: {
  tracking: PostHogTrackingConfig | null | undefined;
  distinctId: string | null | undefined;
  productSlug: string | null | undefined;
  funnelSlug: string | null | undefined;
  publicationId: string | null | undefined;
}): PostHogInstance | null {
  const apiKey = cleanText(tracking?.posthogProjectApiKey);
  const apiHost = cleanText(tracking?.posthogApiHost);
  const uiHost = cleanText(tracking?.posthogUiHost);
  if (!apiKey || !apiHost) {
    return null;
  }

  const root = ensurePostHogRoot();
  if (!root?.init) {
    return null;
  }

  const existingInstance = root[POSTHOG_INSTANCE_NAME] as PostHogInstance | undefined;
  if (existingInstance?.__mosFunnelConfigured === "true") {
    return existingInstance;
  }

  root.init(
    apiKey,
    {
      api_host: apiHost,
      ...(uiHost ? { ui_host: uiHost } : {}),
      defaults: cleanText(tracking?.posthogDefaults) || "2026-01-30",
      person_profiles: cleanText(tracking?.posthogPersonProfiles) || "always",
      autocapture: false,
      capture_pageview: false,
      capture_pageleave: false,
      bootstrap: {
        distinctID: cleanText(distinctId) || "anonymous-funnel-visitor",
        isIdentifiedID: false,
      },
    },
    POSTHOG_INSTANCE_NAME,
  );

  const instance = root[POSTHOG_INSTANCE_NAME] as PostHogInstance | undefined;
  if (!instance) {
    return null;
  }

  if (typeof instance.register === "function") {
    instance.register({
      productSlug: cleanText(productSlug),
      funnelSlug: cleanText(funnelSlug),
      publicationId: cleanText(publicationId),
    });
  }
  instance.__mosFunnelConfigured = "true";
  return instance;
}

export function capturePostHogEvent({
  tracking,
  distinctId,
  productSlug,
  funnelSlug,
  publicationId,
  pageId,
  pageSlug,
  pageStage,
  sessionId,
  eventType,
  props,
  utm,
}: {
  tracking: PostHogTrackingConfig | null | undefined;
  distinctId: string | null | undefined;
  productSlug: string | null | undefined;
  funnelSlug: string | null | undefined;
  publicationId: string | null | undefined;
  pageId: string | null | undefined;
  pageSlug: string | null | undefined;
  pageStage: string | null | undefined;
  sessionId: string | null | undefined;
  eventType: string;
  props?: Record<string, unknown>;
  utm?: Record<string, string>;
}) {
  const instance = ensurePostHogInstance({
    tracking,
    distinctId,
    productSlug,
    funnelSlug,
    publicationId,
  });
  if (!instance || typeof instance.capture !== "function") {
    return;
  }

  const resolvedPageStage = cleanText(pageStage);
  const baseProps = {
    productSlug: cleanText(productSlug),
    funnelSlug: cleanText(funnelSlug),
    publicationId: cleanText(publicationId),
    pageId: cleanText(pageId),
    pageSlug: cleanText(pageSlug),
    pageStage: resolvedPageStage,
    visitorId: cleanText(distinctId),
    sessionId: cleanText(sessionId),
    path: typeof window === "undefined" ? undefined : window.location.pathname + window.location.search,
    referrer: typeof document === "undefined" ? undefined : document.referrer || undefined,
    utm: utm || {},
  };
  const resolvedCaptures = resolvePostHogCaptures({
    eventType,
    publicationId: cleanText(publicationId),
    pageId: cleanText(pageId),
    pageStage: resolvedPageStage,
    sessionId: cleanText(sessionId),
    props,
    baseProps,
  });
  for (const resolvedCapture of resolvedCaptures) {
    instance.capture(resolvedCapture.eventName, resolvedCapture.eventProps);
  }
}
