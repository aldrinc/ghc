import { useEffect } from "react";
import { optimizeImportedHtmlDocument } from "@/funnels/importedHtmlRuntime";
import { resolvePublicApiBaseUrl } from "@/funnels/runtimeRouting";
import type { PublicCommerceVariant } from "@/types/commerce";
import type {
  ImportedHtmlInstrumentationManifest,
  ImportedHtmlTrackEventType,
  PublicFunnelPage,
  PublicFunnelStage,
} from "@/types/funnels";

const apiBaseUrl = resolvePublicApiBaseUrl();

declare global {
  interface Window {
    __mosImportedHtmlStandalonePageId?: string;
  }
}

type StandaloneImportedHtmlPageProps = {
  page: PublicFunnelPage;
  productSlug: string;
  funnelSlug: string;
  visitorId: string;
  sessionId: string;
  htmlDocument: string;
  instrumentationManifest: ImportedHtmlInstrumentationManifest;
  variants: PublicCommerceVariant[];
  pagePathById: Record<string, string>;
  pageStageById: Record<string, PublicFunnelStage>;
};

type SerializedVariant = {
  id: string;
  provider: string | null;
  price: number | null;
  currency: string | null;
  optionValues: Record<string, string> | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeVariantOptionValues(
  optionValues: Record<string, unknown> | null | undefined,
): Record<string, string> | null {
  if (!isRecord(optionValues)) return null;
  const normalizedEntries = Object.entries(optionValues)
    .map(([key, value]) => {
      if (typeof key !== "string") return null;
      const normalizedKey = key.trim();
      if (!normalizedKey || typeof value !== "string") return null;
      const normalizedValue = value.trim();
      if (!normalizedValue) return null;
      return [normalizedKey, normalizedValue] as const;
    })
    .filter((entry): entry is readonly [string, string] => Boolean(entry));
  if (!normalizedEntries.length) return null;
  return Object.fromEntries(normalizedEntries);
}

function serializeVariants(variants: PublicCommerceVariant[]): SerializedVariant[] {
  return variants.map((variant) => ({
    id: variant.id,
    provider: typeof variant.provider === "string" ? variant.provider.trim().toLowerCase() || null : null,
    price: typeof variant.price === "number" ? variant.price : null,
    currency: typeof variant.currency === "string" ? variant.currency.trim() || null : null,
    optionValues: normalizeVariantOptionValues(variant.option_values ?? null),
  }));
}

function buildStandaloneImportedHtmlRuntimeScript({
  page,
  productSlug,
  funnelSlug,
  visitorId,
  sessionId,
  instrumentationManifest,
  variants,
  pagePathById,
  pageStageById,
}: Omit<StandaloneImportedHtmlPageProps, "htmlDocument">): string {
  const scriptConfig = {
    apiBaseUrl,
    pageId: page.pageId,
    pageSlug: page.slug,
    pageStage: page.stage,
    funnelId: page.funnelId,
    publicationId: page.publicationId,
    productSlug,
    funnelSlug,
    visitorId,
    sessionId,
    tracking: page.tracking ?? null,
    manifest: instrumentationManifest,
    htmlArtifactKind: instrumentationManifest.htmlArtifactKind,
    htmlDeploySchemaVersion: instrumentationManifest.schemaVersion,
    variants: serializeVariants(variants),
    pagePathById,
    pageStageById,
  };

  return `
<script>
(() => {
  const config = ${JSON.stringify(scriptConfig)};

  const META_PIXEL_SCRIPT_ID = "mos-meta-pixel-script";
  const META_PIXEL_SCRIPT_SRC = "https://connect.facebook.net/en_US/fbevents.js";
  const META_PIXEL_DEFER_TIMEOUT_MS = 1500;
  const POSTHOG_INSTANCE_NAME = "mosFunnel";
  const META_ATTRIBUTION_WAIT_TIMEOUT_MS = 1500;
  const META_ATTRIBUTION_WAIT_POLL_MS = 50;
  const META_EMAIL_HASH_STORAGE_KEY = "mos_meta_em";
  const TRACKING_NAVIGATION_FLUSH_DELAY_MS = 250;
  const RMBC_SESSION_PARAM = "rmbc_session_id";
  const RMBC_ANONYMOUS_PARAM = "rmbc_anonymous_id";
  const RMBC_CLICK_PARAM = "rmbc_click_id";

  const cleanText = (value) => {
    if (typeof value !== "string") return null;
    const trimmed = value.trim();
    return trimmed || null;
  };

  const normalizeText = (value) =>
    String(value || "")
      .replace(/\\s+/g, " ")
      .trim();

  const isRecord = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);

  const isNonEmptyRecord = (value) => isRecord(value) && Object.keys(value).length > 0;

  const waitForTrackingNavigationFlush = () =>
    new Promise((resolve) => {
      window.setTimeout(resolve, TRACKING_NAVIGATION_FLUSH_DELAY_MS);
    });

  const readCookie = (name) => {
    const prefix = String(name || "") + "=";
    const match = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(prefix));
    return match ? cleanText(match.slice(prefix.length)) : null;
  };

  const assignCleanProp = (target, key, value) => {
    const cleaned = cleanText(value);
    if (cleaned) target[key] = cleaned;
  };

  const assignNumberProp = (target, key, value) => {
    if (value === null || value === undefined || value === "") return;
    const numberValue = Number(value);
    if (Number.isFinite(numberValue)) target[key] = numberValue;
  };

  const assignBooleanProp = (target, key, value) => {
    if (typeof value === "boolean") target[key] = value;
  };

  const assignStringListProp = (target, key, value) => {
    if (!Array.isArray(value)) return;
    const cleaned = value.map((item) => cleanText(item)).filter(Boolean);
    if (cleaned.length) target[key] = cleaned;
  };

  const getSearchParam = (name) => {
    try {
      return cleanText(new URLSearchParams(window.location.search).get(name));
    } catch (_) {
      return null;
    }
  };

  const resolveCanonicalSessionId = () =>
    getSearchParam("session_id") || getSearchParam(RMBC_SESSION_PARAM) || cleanText(config.sessionId);

  const resolveCanonicalAnonymousId = () =>
    getSearchParam("anonymous_id") ||
    getSearchParam("visitor_id") ||
    getSearchParam(RMBC_ANONYMOUS_PARAM) ||
    cleanText(config.visitorId);

  const resolvePresalesSourcePageType = () => {
    const explicitType = getSearchParam("source_page_type") || getSearchParam("sourcePageType");
    if (explicitType) return explicitType;
    const artifactKind = cleanText(config.htmlArtifactKind);
    if (artifactKind === "quiz") return "quiz_presell";
    if (artifactKind === "listicle" || artifactKind === "listicle_hybrid") return "listical_presell";
    return cleanText(config.pageStage) === "pre_sales" ? "pre_sales" : null;
  };

  const buildDeclaredTargetProps = (target) => {
    const props = {};
    if (!target || typeof target !== "object") return props;
    assignCleanProp(props, "quizId", target.quizId);
    assignCleanProp(props, "quiz_id", target.quizId);
    assignCleanProp(props, "quizVersion", target.quizVersion);
    assignCleanProp(props, "quiz_version", target.quizVersion);
    assignCleanProp(props, "quizVariant", target.quizVariant);
    assignCleanProp(props, "quiz_variant", target.quizVariant);
    assignCleanProp(props, "questionId", target.questionId);
    assignCleanProp(props, "question_id", target.questionId);
    assignCleanProp(props, "questionText", target.questionText);
    assignCleanProp(props, "question_text", target.questionText);
    assignNumberProp(props, "questionIndex", target.questionIndex);
    assignNumberProp(props, "question_index", target.questionIndex);
    assignCleanProp(props, "questionType", target.questionType);
    assignCleanProp(props, "question_type", target.questionType);
    assignCleanProp(props, "questionRole", target.questionRole);
    assignCleanProp(props, "question_role", target.questionRole);
    assignBooleanProp(props, "isRequired", target.isRequired);
    assignBooleanProp(props, "is_required", target.isRequired);
    assignCleanProp(props, "optionId", target.optionId);
    assignCleanProp(props, "option_id", target.optionId);
    assignCleanProp(props, "optionText", target.optionText);
    assignCleanProp(props, "option_text", target.optionText);
    assignNumberProp(props, "optionIndex", target.optionIndex);
    assignNumberProp(props, "option_index", target.optionIndex);
    assignNumberProp(props, "optionPosition", target.optionPosition || target.optionIndex);
    assignNumberProp(props, "option_position", target.optionPosition || target.optionIndex);
    assignCleanProp(props, "optionRole", target.optionRole);
    assignCleanProp(props, "option_role", target.optionRole);
    assignNumberProp(props, "selectionOrder", target.selectionOrder);
    assignNumberProp(props, "selection_order", target.selectionOrder);
    assignBooleanProp(props, "submitOnSelect", target.submitOnSelect);
    assignBooleanProp(props, "submit_on_select", target.submitOnSelect);
    assignCleanProp(props, "resultId", target.resultId);
    assignCleanProp(props, "result_id", target.resultId);
    assignCleanProp(props, "segmentId", target.segmentId);
    assignCleanProp(props, "segment_id", target.segmentId);
    assignCleanProp(props, "recommendationId", target.recommendationId);
    assignCleanProp(props, "recommendation_id", target.recommendationId);
    assignCleanProp(props, "answerPathId", target.answerPathId);
    assignCleanProp(props, "answer_path_id", target.answerPathId);
    assignCleanProp(props, "angle", target.angle);
    assignCleanProp(props, "awarenessLevel", target.awarenessLevel);
    assignCleanProp(props, "awareness_level", target.awarenessLevel);
    assignCleanProp(props, "sophisticationLevel", target.sophisticationLevel);
    assignCleanProp(props, "sophistication_level", target.sophisticationLevel);
    assignCleanProp(props, "angleFamily", target.angleFamily);
    assignCleanProp(props, "angle_family", target.angleFamily);
    assignCleanProp(props, "hookId", target.hookId);
    assignCleanProp(props, "hook_id", target.hookId);
    assignCleanProp(props, "promiseId", target.promiseId);
    assignCleanProp(props, "promise_id", target.promiseId);
    assignCleanProp(props, "mechanismName", target.mechanismName);
    assignCleanProp(props, "mechanism_name", target.mechanismName);
    assignCleanProp(props, "offerId", target.offerId);
    assignCleanProp(props, "offer_id", target.offerId);
    assignCleanProp(props, "sku", target.sku);
    assignCleanProp(props, "bundleId", target.bundleId);
    assignCleanProp(props, "bundle_id", target.bundleId);
    assignStringListProp(props, "contentIds", target.contentIds);
    assignStringListProp(props, "content_ids", target.content_ids || target.contentIds);
    assignNumberProp(props, "numItems", target.numItems);
    assignNumberProp(props, "num_items", target.num_items || target.numItems);
    assignCleanProp(props, "pricePoint", target.pricePoint);
    assignCleanProp(props, "price_point", target.pricePoint);
    assignCleanProp(props, "guaranteeId", target.guaranteeId);
    assignCleanProp(props, "guarantee_id", target.guaranteeId);
    assignCleanProp(props, "guaranteeType", target.guaranteeType);
    assignCleanProp(props, "guarantee_type", target.guaranteeType);
    assignCleanProp(props, "guaranteeDuration", target.guaranteeDuration);
    assignCleanProp(props, "guarantee_duration", target.guaranteeDuration);
    assignNumberProp(props, "valueTotal", target.valueTotal);
    assignNumberProp(props, "value_total", target.valueTotal);
    assignNumberProp(props, "actualPrice", target.actualPrice);
    assignNumberProp(props, "actual_price", target.actualPrice);
    assignNumberProp(props, "valueRatio", target.valueRatio);
    assignNumberProp(props, "value_ratio", target.valueRatio);
    assignCleanProp(props, "clickType", target.clickType);
    assignCleanProp(props, "click_type", target.clickType);
    assignCleanProp(props, "targetOfferId", target.targetOfferId);
    assignCleanProp(props, "target_offer_id", target.targetOfferId);
    assignCleanProp(props, "destinationUrl", target.destinationUrl);
    assignCleanProp(props, "destination_url", target.destinationUrl);
    assignCleanProp(props, "elementId", target.elementId);
    assignCleanProp(props, "element_id", target.elementId);
    assignCleanProp(props, "interactionType", target.interactionType);
    assignCleanProp(props, "interaction_type", target.interactionType);
    assignCleanProp(props, "selectedValue", target.selectedValue);
    assignCleanProp(props, "selected_value", target.selectedValue);
    assignBooleanProp(props, "subscriptionFlag", target.subscriptionFlag);
    assignBooleanProp(props, "subscription_flag", target.subscriptionFlag);
    return props;
  };

  const quizAnswerStateByQuestionId = {};
  const manifestTargets = (key) => {
    const manifest = config.manifest && typeof config.manifest === "object" ? config.manifest : {};
    const targets = manifest[key];
    return Array.isArray(targets) ? targets.filter((target) => target && typeof target === "object") : [];
  };
  const firstCleanProp = (source, names) => {
    if (!source || typeof source !== "object" || !Array.isArray(names)) return null;
    for (const name of names) {
      const value = cleanText(source[name]);
      if (value) return value;
    }
    return null;
  };
  const targetQuestionId = (target) => firstCleanProp(target, ["questionId", "question_id", "id"]);
  const targetOptionId = (target) => firstCleanProp(target, ["optionId", "option_id", "id"]);
  const findQuizQuestionTarget = (questionId) => {
    const normalizedQuestionId = cleanText(questionId);
    if (!normalizedQuestionId) return null;
    return manifestTargets("quizQuestions").find((target) => targetQuestionId(target) === normalizedQuestionId) || null;
  };
  const normalizeQuestionType = (value) => {
    const normalized = cleanText(value);
    return normalized ? normalized.toLowerCase().replace(/[\\s-]+/g, "_") : "single_select";
  };
  const isMultiSelectQuestion = (questionTarget, props) => {
    const explicitType = firstCleanProp(props, ["questionType", "question_type"]) ||
      firstCleanProp(questionTarget, ["questionType", "question_type"]);
    const normalizedType = normalizeQuestionType(explicitType);
    return (
      normalizedType === "multi_select" ||
      normalizedType === "multiple_select" ||
      normalizedType === "checkbox" ||
      normalizedType === "checkbox_group"
    );
  };
  const cleanStringArray = (value) => {
    if (!Array.isArray(value)) return [];
    return value.map((item) => cleanText(item)).filter(Boolean);
  };
  const quizOptionTextForId = (questionId, optionId) => {
    const normalizedQuestionId = cleanText(questionId);
    const normalizedOptionId = cleanText(optionId);
    if (!normalizedOptionId) return null;
    const match = manifestTargets("quizOptions").find((target) => (
      targetOptionId(target) === normalizedOptionId &&
      (!normalizedQuestionId || targetQuestionId(target) === normalizedQuestionId)
    ));
    return firstCleanProp(match, ["optionText", "option_text"]);
  };
  const buildQuizAnswerSnapshot = (questionId, state) => {
    if (!questionId || !state) return null;
    const selectedOptionIds = cleanStringArray(state.selected_option_ids);
    const selectedOptionTexts = cleanStringArray(state.selected_option_texts);
    return {
      question_id: questionId,
      questionId,
      question_text: cleanText(state.question_text),
      questionText: cleanText(state.question_text),
      question_index: state.question_index,
      questionIndex: state.question_index,
      question_type: cleanText(state.question_type),
      questionType: cleanText(state.question_type),
      selected_option_ids: selectedOptionIds,
      selectedOptionIds: selectedOptionIds,
      selected_option_texts: selectedOptionTexts,
      selectedOptionTexts: selectedOptionTexts,
    };
  };
  const allQuizAnswers = () => Object.keys(quizAnswerStateByQuestionId)
    .map((questionId) => buildQuizAnswerSnapshot(questionId, quizAnswerStateByQuestionId[questionId]))
    .filter(Boolean);
  const answerStateProps = (questionId) => {
    const state = questionId ? quizAnswerStateByQuestionId[questionId] : null;
    const answers = allQuizAnswers();
    const snapshot = buildQuizAnswerSnapshot(questionId, state);
    return {
      ...(snapshot || {}),
      ...(answers.length ? {
        answers,
        answersByQuestion: quizAnswerStateByQuestionId,
        answers_by_question: quizAnswerStateByQuestionId,
        questionCountAnswered: answers.length,
        question_count_answered: answers.length,
      } : {}),
    };
  };
  const updateQuizAnswerState = (eventType, props) => {
    const normalizedEventType = cleanText(eventType);
    const questionId = firstCleanProp(props, ["question_id", "questionId"]);
    if (!questionId) return {};
    const questionTarget = findQuizQuestionTarget(questionId);
    const questionProps = buildDeclaredTargetProps(questionTarget);
    const questionText = firstCleanProp(props, ["question_text", "questionText"]) ||
      firstCleanProp(questionProps, ["question_text", "questionText"]);
    const questionIndex = Number(
      (props && (props.question_index || props.questionIndex)) ||
      questionProps.question_index ||
      questionProps.questionIndex ||
      0
    ) || undefined;
    const questionType = normalizeQuestionType(
      firstCleanProp(props, ["question_type", "questionType"]) ||
      firstCleanProp(questionProps, ["question_type", "questionType"])
    );
    const selectedOptionIds = cleanStringArray(props && (props.selected_option_ids || props.selectedOptionIds));
    const optionId = firstCleanProp(props, ["option_id", "optionId"]);
    const nextSelectedIds = selectedOptionIds.length ? selectedOptionIds : (optionId ? [optionId] : []);
    const selectedOptionTexts = cleanStringArray(props && (props.selected_option_texts || props.selectedOptionTexts));
    const optionText = firstCleanProp(props, ["option_text", "optionText"]);
    const nextSelectedTexts = selectedOptionTexts.length
      ? selectedOptionTexts
      : nextSelectedIds.map((selectedOptionId) => (
          optionText && selectedOptionId === optionId
            ? optionText
            : (quizOptionTextForId(questionId, selectedOptionId) || selectedOptionId)
        ));
    const current = quizAnswerStateByQuestionId[questionId] || {
      question_id: questionId,
      question_text: questionText,
      question_index: questionIndex,
      question_type: questionType,
      selected_option_ids: [],
      selected_option_texts: [],
    };
    current.question_text = current.question_text || questionText;
    current.question_index = current.question_index || questionIndex;
    current.question_type = current.question_type || questionType;
    if (normalizedEventType === "quiz_option_selected" || normalizedEventType === "QuizOptionSelected") {
      if (isMultiSelectQuestion(questionTarget, props)) {
        nextSelectedIds.forEach((selectedOptionId, index) => {
          if (!current.selected_option_ids.includes(selectedOptionId)) {
            current.selected_option_ids.push(selectedOptionId);
            current.selected_option_texts.push(nextSelectedTexts[index] || selectedOptionId);
          }
        });
      } else {
        current.selected_option_ids = nextSelectedIds;
        current.selected_option_texts = nextSelectedTexts;
      }
      quizAnswerStateByQuestionId[questionId] = current;
    }
    if (normalizedEventType === "quiz_question_submitted" || normalizedEventType === "QuizQuestionSubmitted") {
      if (nextSelectedIds.length) {
        current.selected_option_ids = nextSelectedIds;
        current.selected_option_texts = nextSelectedTexts;
      }
      quizAnswerStateByQuestionId[questionId] = current;
    }
    return answerStateProps(questionId);
  };

  const readStoredMetaEmailHash = () => {
    try {
      return cleanText(window.localStorage && window.localStorage.getItem(META_EMAIL_HASH_STORAGE_KEY));
    } catch (_) {
      return null;
    }
  };

  const resolveMetaExternalId = () => resolveCanonicalAnonymousId();

  const resolveMetaAdvancedMatchingProps = () => {
    const props = {};
    assignCleanProp(props, "external_id", resolveMetaExternalId());
    assignCleanProp(props, "em", readStoredMetaEmailHash());
    return props;
  };

  const resolveMetaAttributionProps = (eventSourceUrl) => {
    const props = { action_source: "website" };
    assignCleanProp(props, "external_id", resolveMetaExternalId());
    assignCleanProp(props, "em", readStoredMetaEmailHash());
    assignCleanProp(props, "fbp", readCookie("_fbp"));
    assignCleanProp(props, "fbc", readCookie("_fbc"));
    const currentUrl = new URL(cleanText(eventSourceUrl) || window.location.href);
    assignCleanProp(props, "fbclid", currentUrl.searchParams.get("fbclid"));
    assignCleanProp(props, "session_id", currentUrl.searchParams.get("session_id") || currentUrl.searchParams.get(RMBC_SESSION_PARAM) || resolveCanonicalSessionId());
    assignCleanProp(props, "anonymous_id", currentUrl.searchParams.get("anonymous_id") || currentUrl.searchParams.get("visitor_id") || currentUrl.searchParams.get(RMBC_ANONYMOUS_PARAM) || resolveCanonicalAnonymousId());
    assignCleanProp(props, "visitor_id", currentUrl.searchParams.get("visitor_id") || currentUrl.searchParams.get("anonymous_id") || currentUrl.searchParams.get(RMBC_ANONYMOUS_PARAM) || resolveCanonicalAnonymousId());
    assignCleanProp(props, "click_id", currentUrl.searchParams.get("click_id") || currentUrl.searchParams.get(RMBC_CLICK_PARAM));
    assignCleanProp(props, "source_page_type", currentUrl.searchParams.get("source_page_type") || currentUrl.searchParams.get("sourcePageType"));
    assignCleanProp(props, "from_stage", currentUrl.searchParams.get("from_stage") || currentUrl.searchParams.get("fromStage"));
    assignCleanProp(props, "to_stage", currentUrl.searchParams.get("to_stage") || currentUrl.searchParams.get("toStage"));
    assignCleanProp(props, "rmbc_session_id", currentUrl.searchParams.get(RMBC_SESSION_PARAM));
    assignCleanProp(props, "rmbc_anonymous_id", currentUrl.searchParams.get(RMBC_ANONYMOUS_PARAM));
    assignCleanProp(props, "rmbc_click_id", currentUrl.searchParams.get(RMBC_CLICK_PARAM));
    assignCleanProp(props, "event_source_url", currentUrl.href);
    assignCleanProp(props, "$raw_user_agent", window.navigator && window.navigator.userAgent);
    return props;
  };

  const resolveMetaAttributionReady = (eventSourceUrl) => {
    const eventUrl = new URL(cleanText(eventSourceUrl) || window.location.href);
    const hasFbclid = Boolean(cleanText(eventUrl.searchParams.get("fbclid")));
    const hasFbp = Boolean(readCookie("_fbp"));
    const hasFbc = Boolean(readCookie("_fbc"));
    return hasFbp && (!hasFbclid || hasFbc);
  };

  const waitForMetaAttribution = (eventSourceUrl) => {
    const startedAt = Date.now();
    return new Promise((resolve) => {
      const poll = () => {
        const elapsedMs = Date.now() - startedAt;
        if (resolveMetaAttributionReady(eventSourceUrl)) {
          resolve({ elapsedMs, timedOut: false });
          return;
        }
        if (elapsedMs >= META_ATTRIBUTION_WAIT_TIMEOUT_MS) {
          resolve({ elapsedMs, timedOut: true });
          return;
        }
        window.setTimeout(poll, META_ATTRIBUTION_WAIT_POLL_MS);
      };
      window.setTimeout(poll, META_ATTRIBUTION_WAIT_POLL_MS);
    });
  };

  const randomEventIdSegment = () => {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return String(Date.now()) + "-" + Math.random().toString(16).slice(2);
  };

  const buildMetaEventId = (eventName, eventType, index) => {
    return [
      cleanText(eventName) || "meta",
      cleanText(eventType) || "event",
      cleanText(config.publicationId) || "publication",
      cleanText(config.pageId) || "page",
      resolveCanonicalSessionId() || "session",
      String(index),
      randomEventIdSegment(),
    ].join(":");
  };

  const buildMetaAddToCartHandoffEventId = (variantId) => {
    return [
      "mos",
      "meta",
      "AddToCart",
      cleanText(config.publicationId) || "publication",
      cleanText(config.pageId) || "page",
      resolveCanonicalSessionId() || "session",
      cleanText(variantId) || "variant",
      randomEventIdSegment(),
    ].join(":");
  };

  const buildMetaInitiateCheckoutHandoffEventId = (transitionId) => {
    const cleanedTransitionId = cleanText(transitionId);
    return cleanedTransitionId ? "checkout_started:" + cleanedTransitionId : "";
  };

  const metaAddToCartCheckoutEventIds = {};
  const metaAddToCartNextEventIds = {};
  const metaAddToCartVariantKey = (variantId) => cleanText(variantId) || "default";
  const resolveMetaAddToCartCheckoutEventId = (variantId) => {
    const key = metaAddToCartVariantKey(variantId);
    if (!metaAddToCartCheckoutEventIds[key]) {
      metaAddToCartCheckoutEventIds[key] =
        metaAddToCartNextEventIds[key] || buildMetaAddToCartHandoffEventId(variantId);
      metaAddToCartNextEventIds[key] = metaAddToCartCheckoutEventIds[key];
    }
    return metaAddToCartCheckoutEventIds[key];
  };

  const CLICK_ID_KEYS = ["fbclid", "gclid", "ttclid", "msclkid", "twclid", "li_fat_id"];
  const CHECKOUT_TRACKING_PARAM_KEYS = new Set([
    ...CLICK_ID_KEYS,
    "experiment_id",
    "experiment",
    "exp",
    "src",
  ]);

  const buildCanonicalEventId = (eventType) => {
    return [
      "mos",
      cleanText(eventType) || "event",
      cleanText(config.publicationId) || "publication",
      cleanText(config.pageId) || "page",
      resolveCanonicalSessionId() || "session",
      randomEventIdSegment(),
    ].join(":");
  };

  const resolveClickAttribution = () => {
    const params = new URLSearchParams(window.location.search);
    const rmbcClickId = cleanText(params.get(RMBC_CLICK_PARAM));
    if (rmbcClickId) {
      const attribution = {
        clickId: rmbcClickId,
        clickIdType: RMBC_CLICK_PARAM,
        rmbcClickId,
        rmbc_click_id: rmbcClickId,
        bridgeClickId: rmbcClickId,
        bridge_click_id: rmbcClickId,
      };
      for (const key of CLICK_ID_KEYS) {
        const value = cleanText(params.get(key));
        if (value) {
          attribution.paidClickId = value;
          attribution.paid_click_id = value;
          attribution.paidClickIdType = key;
          attribution.paid_click_id_type = key;
          attribution[key] = value;
          break;
        }
      }
      return attribution;
    }
    for (const key of CLICK_ID_KEYS) {
      const value = cleanText(params.get(key));
      if (value) {
        return {
          clickId: value,
          clickIdType: key,
          [key]: value,
        };
      }
    }
    return {};
  };

  const resolvePageType = (stage) => {
    if (stage === "pre_sales") return "presell";
    if (stage === "sales") return "offer";
    if (stage === "checkout") return "checkout";
    if (stage === "thank_you") return "thank_you";
    return "custom";
  };

  const resolveExperimentId = () => {
    const params = new URLSearchParams(window.location.search);
    return (
      cleanText(params.get("experiment_id")) ||
      cleanText(params.get("experiment")) ||
      cleanText(params.get("exp"))
    );
  };

  const resolveDeviceType = () => {
    const width = window.innerWidth || (document.documentElement && document.documentElement.clientWidth) || 0;
    if (width > 0 && width < 768) return "mobile";
    if (width >= 768 && width < 1024) return "tablet";
    return "desktop";
  };

  const resolveRuntimeContextProps = (props) => {
    const pageStage = cleanText((props && props.pageStage) || config.pageStage);
    const experimentId = resolveExperimentId();
    const externalId = resolveMetaExternalId();
    const emailHash = readStoredMetaEmailHash();
    const pageType = resolvePageType(pageStage);
    const pageVariant = cleanText(config.pageSlug);
    const visitorId = resolveCanonicalAnonymousId();
    const sessionId = resolveCanonicalSessionId();
    const deviceType = resolveDeviceType();
    const clickAttribution = resolveClickAttribution();
    const sourcePageType = resolvePresalesSourcePageType();
    const fromStage = getSearchParam("from_stage") || getSearchParam("fromStage");
    const toStage = getSearchParam("to_stage") || getSearchParam("toStage");
    return {
      productSlug: cleanText(config.productSlug),
      product_slug: cleanText(config.productSlug),
      funnelSlug: cleanText(config.funnelSlug),
      funnel_slug: cleanText(config.funnelSlug),
      publicationId: cleanText(config.publicationId),
      publication_id: cleanText(config.publicationId),
      pageId: cleanText(config.pageId),
      page_id: cleanText(config.pageId),
      pageSlug: cleanText(config.pageSlug),
      page_slug: cleanText(config.pageSlug),
      pageStage,
      page_stage: pageStage,
      pageType,
      page_type: pageType,
      htmlArtifactKind: cleanText(config.htmlArtifactKind),
      html_artifact_kind: cleanText(config.htmlArtifactKind),
      htmlDeploySchemaVersion: cleanText(config.htmlDeploySchemaVersion),
      html_deploy_schema_version: cleanText(config.htmlDeploySchemaVersion),
      pageVariant,
      page_variant: pageVariant,
      visitorId,
      visitor_id: visitorId,
      anonymous_id: visitorId,
      sessionId,
      session_id: sessionId,
      path: window.location.pathname + window.location.search,
      referrer: document.referrer || undefined,
      deviceType,
      device_type: deviceType,
      browserUserAgent: window.navigator && window.navigator.userAgent,
      browser_user_agent: window.navigator && window.navigator.userAgent,
      ...(externalId ? { external_id: externalId } : {}),
      ...(emailHash ? { em: emailHash } : {}),
      ...(experimentId ? { experimentId, experiment_id: experimentId } : {}),
      ...(sourcePageType ? { sourcePageType, source_page_type: sourcePageType } : {}),
      ...(fromStage ? { fromStage, from_stage: fromStage } : {}),
      ...(toStage ? { toStage, to_stage: toStage } : {}),
      ...clickAttribution,
      ...(clickAttribution.clickId ? { click_id: clickAttribution.clickId } : {}),
      ...(clickAttribution.clickIdType ? { click_id_type: clickAttribution.clickIdType } : {}),
      ...(getSearchParam(RMBC_SESSION_PARAM)
        ? { rmbc_session_id: getSearchParam(RMBC_SESSION_PARAM) }
        : {}),
      ...(getSearchParam(RMBC_ANONYMOUS_PARAM)
        ? { rmbc_anonymous_id: getSearchParam(RMBC_ANONYMOUS_PARAM) }
        : {}),
    };
  };

  const posthogTrackingConfig = isRecord(config.tracking) ? config.tracking : null;
  const PRESALE_SOURCE_PARAM = "src";
  const PRESALE_SOURCE_VALUE = "presale";

  const isPresaleToSalesNavigation = (fromStage, toStage) =>
    cleanText(fromStage) === "pre_sales" && cleanText(toStage) === "sales";

  const presaleAttributionStorageKey = () => {
    const product = cleanText(config.productSlug);
    const funnel = cleanText(config.funnelSlug);
    if (!product || !funnel) return null;
    return "from_presale:" + product + ":" + funnel;
  };

  const markPresaleAttribution = () => {
    const key = presaleAttributionStorageKey();
    if (!key) return;
    try {
      window.sessionStorage.setItem(key, "1");
    } catch (_) {
      // ignore storage write failures
    }
  };

  const hasPresaleSourceParam = () =>
    new URLSearchParams(window.location.search).get(PRESALE_SOURCE_PARAM) === PRESALE_SOURCE_VALUE;

  const hasStoredPresaleAttribution = () => {
    const key = presaleAttributionStorageKey();
    if (!key) return false;
    try {
      return window.sessionStorage.getItem(key) === "1";
    } catch (_) {
      return false;
    }
  };

  const hasPresaleReferrerAttribution = () => {
    if (!document.referrer) return false;
    try {
      const referrerUrl = new URL(document.referrer, window.location.href);
      if (referrerUrl.origin !== window.location.origin) {
        return false;
      }
      const preSalesPaths = Object.entries(config.pageStageById || {})
        .filter(([, stage]) => cleanText(stage) === "pre_sales")
        .map(([pageId]) => cleanText(config.pagePathById && config.pagePathById[pageId]))
        .filter(Boolean);
      return preSalesPaths.some((path) => new URL(path, window.location.href).pathname === referrerUrl.pathname);
    } catch (_) {
      return false;
    }
  };

  const resolvePresaleAttribution = () => {
    if (hasPresaleSourceParam()) return "url";
    if (hasStoredPresaleAttribution()) return "session";
    if (hasPresaleReferrerAttribution()) return "referrer";
    return null;
  };

  const buildBridgeClickId = (bindingId, ctaPosition) => {
    return [
      "click",
      cleanText(config.publicationId) || "publication",
      cleanText(config.pageId) || "page",
      cleanText(bindingId) || "cta",
      String(ctaPosition || 1),
      randomEventIdSegment(),
    ].join("_");
  };

  const buildInternalNavigationUrl = (targetPath, options) => {
    const normalizedTargetPath = cleanText(targetPath);
    if (!normalizedTargetPath) return window.location.href;
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.delete("checkout");
    const nextUrl = new URL(normalizedTargetPath, window.location.href);
    nextUrl.search = currentUrl.search;
    if (isPresaleToSalesNavigation(options && options.fromStage, options && options.toStage)) {
      nextUrl.searchParams.set(PRESALE_SOURCE_PARAM, PRESALE_SOURCE_VALUE);
      const bridgeSessionId = cleanText(options && options.sessionId) || cleanText(config.sessionId);
      const bridgeAnonymousId = cleanText(options && options.anonymousId) || cleanText(config.visitorId);
      const bridgeClickId = cleanText(options && options.clickId);
      const sourcePageType = cleanText(options && options.sourcePageType) || resolvePresalesSourcePageType();
      if (bridgeSessionId) nextUrl.searchParams.set(RMBC_SESSION_PARAM, bridgeSessionId);
      if (bridgeSessionId) nextUrl.searchParams.set("session_id", bridgeSessionId);
      if (bridgeAnonymousId) nextUrl.searchParams.set(RMBC_ANONYMOUS_PARAM, bridgeAnonymousId);
      if (bridgeAnonymousId) nextUrl.searchParams.set("anonymous_id", bridgeAnonymousId);
      if (bridgeAnonymousId) nextUrl.searchParams.set("visitor_id", bridgeAnonymousId);
      if (bridgeClickId) nextUrl.searchParams.set(RMBC_CLICK_PARAM, bridgeClickId);
      if (bridgeClickId) nextUrl.searchParams.set("click_id", bridgeClickId);
      if (bridgeClickId) nextUrl.searchParams.set("click_id_type", RMBC_CLICK_PARAM);
      if (sourcePageType) nextUrl.searchParams.set("source_page_type", sourcePageType);
      nextUrl.searchParams.set("from_stage", "pre_sales");
      nextUrl.searchParams.set("to_stage", "sales");
      if (cleanText(config.pageSlug)) nextUrl.searchParams.set("source_page", cleanText(config.pageSlug));
    }
    return nextUrl.toString();
  };

  const getUtmParams = () => {
    const params = new URLSearchParams(window.location.search);
    const utm = {};
    for (const [key, value] of params.entries()) {
      if (key.startsWith("utm_")) {
        utm[key] = value;
      }
    }
    return utm;
  };

  const isCheckoutTrackingParam = (key) => {
    const normalized = String(key || "").trim();
    return normalized.startsWith("utm_") || CHECKOUT_TRACKING_PARAM_KEYS.has(normalized);
  };

  const pendingMetaPurchaseStorageKey = (resolvedSessionId, resolvedFunnelSlug) => {
    const cleanSessionId = cleanText(resolvedSessionId);
    const cleanFunnelSlug = cleanText(resolvedFunnelSlug);
    if (!cleanSessionId || !cleanFunnelSlug) {
      return null;
    }
    return "mos-meta-purchase:" + cleanSessionId + ":" + cleanFunnelSlug;
  };

  const writePendingMetaPurchase = (key, purchase) => {
    if (!key) return;
    sessionStorage.setItem(
      key,
      JSON.stringify({
        ...purchase,
        createdAt: Date.now(),
      }),
    );
  };

  const loadMetaPixelScript = () => {
    if (document.getElementById(META_PIXEL_SCRIPT_ID)) {
      return;
    }
    const script = document.createElement("script");
    script.id = META_PIXEL_SCRIPT_ID;
    script.async = true;
    script.src = META_PIXEL_SCRIPT_SRC;
    document.head.appendChild(script);
  };

  const scheduleMetaPixelScriptLoad = () => {
    if (window.__mosMetaPixelLoadScheduled || document.getElementById(META_PIXEL_SCRIPT_ID)) {
      return;
    }
    window.__mosMetaPixelLoadScheduled = true;
    const flush = () => {
      window.__mosMetaPixelLoadScheduled = false;
      loadMetaPixelScript();
    };
    const listenerOptions = { capture: true, once: true };
    window.addEventListener("pointerdown", flush, listenerOptions);
    window.addEventListener("keydown", flush, listenerOptions);
    window.addEventListener("touchstart", flush, listenerOptions);
    if (typeof window.requestIdleCallback === "function") {
      window.requestIdleCallback(flush, { timeout: META_PIXEL_DEFER_TIMEOUT_MS });
      return;
    }
    window.setTimeout(flush, META_PIXEL_DEFER_TIMEOUT_MS);
  };

  const ensureMetaPixelBootstrap = () => {
    if (!config.tracking || !config.tracking.metaPixelId) {
      return null;
    }
    const pixelId = String(config.tracking.metaPixelId || "").trim();
    if (!pixelId) return null;

    if (!window.fbq) {
      const fbq = function (...args) {
        if (typeof fbq.callMethod === "function") {
          fbq.callMethod(...args);
          return;
        }
        fbq.queue = fbq.queue || [];
        fbq.queue.push(args);
      };
      fbq.queue = [];
      fbq.loaded = true;
      fbq.version = "2.0";
      window.fbq = fbq;
      window._fbq = fbq;
    }

    scheduleMetaPixelScriptLoad();

    if (!Array.isArray(window.__mosMetaPixelIds)) {
      window.__mosMetaPixelIds = [];
    }
    if (!window.__mosMetaPixelIds.includes(pixelId)) {
      const advancedMatching = resolveMetaAdvancedMatchingProps();
      if (isNonEmptyRecord(advancedMatching)) {
        window.fbq("init", pixelId, advancedMatching);
      } else {
        window.fbq("init", pixelId);
      }
      window.__mosMetaPixelIds.push(pixelId);
    }
    return pixelId;
  };

  const ensurePostHogInstance = () => {
    const apiKey = cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogProjectApiKey);
    const apiHost = cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogApiHost);
    const uiHost = cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogUiHost);
    if (!apiKey || !apiHost) {
      return null;
    }

    const defaults = cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogDefaults) || "2026-01-30";
    const personProfiles =
      cleanText(posthogTrackingConfig && posthogTrackingConfig.posthogPersonProfiles) || "identified_only";
    const distinctId = cleanText(config.visitorId) || "anonymous-funnel-visitor";

    !function(t,e){var o,n,p,r,d;e.__SV||(window.posthog&&window.posthog.__loaded)||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0])&&r.parentNode?r.parentNode.insertBefore(p,r):(d=t.head||t.body||t.documentElement)&&d.appendChild(p);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="Ir Sr init jr $r Ci qr Hr Dr capture calculateEventProperties Wr register register_once register_for_session unregister unregister_for_session Qr getFeatureFlag getFeatureFlagPayload getFeatureFlagResult isFeatureEnabled reloadFeatureFlags updateFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSurveysLoaded onSessionId getSurveys getActiveMatchingSurveys renderSurvey displaySurvey cancelPendingSurvey canRenderSurvey canRenderSurveyAsync tn identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset setIdentity clearIdentity get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException captureLog startExceptionAutocapture stopExceptionAutocapture loadToolbar get_property getSessionProperty Jr Yr createPersonProfile setInternalOrTestUser Kr Pr nn opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing get_explicit_consent_status is_capturing clear_opt_in_out_capturing zr debug ki Xr getPageViewId captureTraceFeedback captureTraceMetric Mr".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);

    const existingInstance = window.posthog && window.posthog[POSTHOG_INSTANCE_NAME];
    if (
      existingInstance &&
      (existingInstance.__mosFunnelConfigured === "true" || window.__mosFunnelPostHogConfigured === "true")
    ) {
      window.__mosFunnelPostHogConfigured = "true";
      return existingInstance;
    }

    window.posthog.init(
      apiKey,
      {
        api_host: apiHost,
        ...(uiHost ? { ui_host: uiHost } : {}),
        defaults,
        person_profiles: personProfiles,
        autocapture: false,
        capture_pageview: true,
        capture_pageleave: true,
        bootstrap: {
          distinctID: distinctId,
          isIdentifiedID: false,
        },
      },
      POSTHOG_INSTANCE_NAME,
    );

    const instance = window.posthog && window.posthog[POSTHOG_INSTANCE_NAME];
    if (!instance) {
      return null;
    }

    if (typeof instance.register === "function") {
      instance.register({
        productSlug: cleanText(config.productSlug),
        funnelSlug: cleanText(config.funnelSlug),
        publicationId: cleanText(config.publicationId),
      });
    }
    instance.__mosFunnelConfigured = "true";
    window.__mosFunnelPostHogConfigured = "true";
    return instance;
  };

  const trackPostHogEvent = (eventType, props, mappedCaptures) => {
    const eventSourceUrl = window.location.href;
    const baseEventProps = {
      ...resolveRuntimeContextProps(props),
      utm: getUtmParams(),
    };

    const emitCaptures = (additionalEventProps) => {
      const captures = resolvePostHogCaptures(eventType, props, baseEventProps, mappedCaptures, eventSourceUrl);
      let sent = false;
      const sendCaptures = () => {
        if (sent) return;
        const posthog = ensurePostHogInstance();
        if (!posthog || posthog.__loaded !== true || typeof posthog.capture !== "function") return;
        sent = true;
        captures.forEach((capture) => {
          posthog.capture(capture.eventName, {
            ...capture.eventProps,
            ...(additionalEventProps || {}),
          });
        });
      };
      sendCaptures();
      if (!sent) {
        window.setTimeout(sendCaptures, 100);
        window.setTimeout(sendCaptures, 500);
        window.setTimeout(sendCaptures, 1500);
        window.setTimeout(sendCaptures, 3000);
        window.setTimeout(sendCaptures, 5000);
      }
    };

    if (Array.isArray(mappedCaptures) && mappedCaptures.length && !resolveMetaAttributionReady(eventSourceUrl)) {
      waitForMetaAttribution(eventSourceUrl).then(({ elapsedMs, timedOut }) => {
        emitCaptures({
          meta_cookie_wait_ms: elapsedMs,
          ...(timedOut ? { meta_cookie_wait_timed_out: true } : {}),
        });
      });
      return;
    }

    emitCaptures();
  };

  const resolveMetaPixelPageStage = (props) => {
    const pageStage = cleanText(props && props.pageStage);
    return pageStage || cleanText(config.pageStage);
  };

  const resolvePostHogContentCategory = (pageStage) => {
    if (pageStage === "pre_sales") return "pre_sales_page";
    if (pageStage === "sales") return "sales_page";
    if (pageStage === "checkout") return "checkout_page";
    if (pageStage === "thank_you") return "thank_you_page";
    if (pageStage === "custom") return "custom_page";
    return null;
  };

  const buildPostHogEventId = (eventName, eventType, index) => {
    return [
      cleanText(eventName) || "capture",
      cleanText(eventType) || "event",
      cleanText(config.publicationId) || "publication",
      cleanText(config.pageId) || "page",
      cleanText(config.sessionId) || "session",
      String(index),
      String(Date.now()),
    ].join(":");
  };

  const sanitizePostHogProps = (props) => {
    if (!isRecord(props)) {
      return {};
    }
    const nextProps = { ...props };
    delete nextProps.fromPresale;
    return nextProps;
  };

  const trackMetaPixel = (method, eventName, params, eventId) => {
    if (typeof window.fbq !== "function") {
      return;
    }
    const options = cleanText(eventId) ? { eventID: cleanText(eventId) } : null;
    if (isNonEmptyRecord(params)) {
      if (options) {
        window.fbq(method, eventName, params, options);
        return;
      }
      window.fbq(method, eventName, params);
      return;
    }
    if (options) {
      window.fbq(method, eventName, {}, options);
      return;
    }
    window.fbq(method, eventName);
  };

  const resolveProductMetaParams = (props) => {
    const explicitContentIds = cleanStringArray(props && (props.content_ids || props.contentIds));
    const variantId = cleanText(
      props &&
        (
          props.variantId ||
          props.variant_id ||
          props.contentId ||
          props.content_id
        ),
    );
    const contentIds = explicitContentIds.length ? explicitContentIds : (variantId ? [variantId] : []);
    const explicitNumItems = Number(props && (props.num_items || props.numItems));
    const params = {
      content_type: "product",
      num_items: Number.isFinite(explicitNumItems) && explicitNumItems > 0
        ? explicitNumItems
        : Math.max(1, contentIds.length || 1),
    };
    if (contentIds.length) {
      params.content_ids = contentIds;
    }
    return params;
  };

  const resolveMappedMetaEvents = (eventType, props) => {
    const pageStage = resolveMetaPixelPageStage(props);
    const pageViewParams = pageStage ? { page_stage: pageStage } : undefined;
    if (eventType === "pre_sales_page_view" || eventType === "custom_page_view") {
      return [{ method: "track", eventName: "PageView", params: pageViewParams }];
    }
    if (eventType === "sales_page_view") {
      return [
        { method: "track", eventName: "PageView", params: pageViewParams },
        { method: "trackCustom", eventName: "Entered Sales Page", params: pageViewParams },
        { method: "trackCustom", eventName: "EnteredSales", params: pageViewParams },
        { method: "track", eventName: "ViewContent", params: pageViewParams },
      ];
    }
    if (eventType === "checkout_page_view" || eventType === "thank_you_page_view") {
      return [{ method: "track", eventName: "PageView", params: pageViewParams }];
    }
    if (eventType === "pre_sales_to_sales_click") {
      return [{
        method: "trackCustom",
        eventName: "PreSalesToSalesClick",
        params: {
          from_stage: "pre_sales",
          to_stage: "sales",
        },
      }];
    }
    if (eventType === "add_to_cart") {
      const variantId = cleanText(props && (props.variantId || props.variant_id || props.contentId || props.content_id));
      const metaAddToCartEventId =
        cleanText(props && (props.metaAddToCartEventId || props.meta_add_to_cart_event_id)) ||
        resolveMetaAddToCartCheckoutEventId(variantId);
      return [{
        method: "track",
        eventName: "AddToCart",
        params: resolveProductMetaParams(props),
        ...(metaAddToCartEventId ? { eventId: metaAddToCartEventId } : {}),
      }];
    }
    if (eventType === "sales_to_checkout_click") {
      return [
        {
          method: "trackCustom",
          eventName: "SalesToCheckoutClick",
          params: {
            from_stage: "sales",
            to_stage: "checkout",
          },
        },
        {
          method: "trackCustom",
          eventName: "SalesToCheckoutClicked",
          params: {
            from_stage: "sales",
            to_stage: "checkout",
          },
        },
      ];
    }
    if (eventType === "checkout_started") {
      const transitionId = cleanText(props && (props.transitionId || props.transition_id));
      const metaInitiateCheckoutEventId =
        cleanText(props && (props.metaInitiateCheckoutEventId || props.meta_initiate_checkout_event_id)) ||
        buildMetaInitiateCheckoutHandoffEventId(transitionId);
      return [{
        method: "track",
        eventName: "InitiateCheckout",
        params: resolveProductMetaParams(props),
        ...(metaInitiateCheckoutEventId ? { eventId: metaInitiateCheckoutEventId } : {}),
      }];
    }
    if (eventType === "presell_page_view") {
      return [
        { method: "trackCustom", eventName: "EnteredPresales", params: pageViewParams },
        { method: "trackCustom", eventName: "Entered Presales Page", params: pageViewParams },
      ];
    }
    return [];
  };

  const resolveCanonicalPostHogEventNames = (eventType) => {
    const normalized = cleanText(eventType);
    if (!normalized) return [];
    const rmbcAliasesByEventType = {
      quiz_lead_viewed: ["QuizLeadViewed"],
      quiz_question_viewed: ["QuizQuestionViewed"],
      quiz_option_presented: ["QuizOptionPresented"],
      quiz_option_selected: ["QuizOptionSelected"],
      quiz_option_deselected: ["QuizOptionDeselected"],
      quiz_question_submitted: ["QuizQuestionSubmitted"],
      quiz_completed: ["QuizCompleted"],
      quiz_result_viewed: ["QuizResultViewed"],
      quiz_mechanism_viewed: ["QuizMechanismViewed"],
      quiz_proof_viewed: ["QuizProofViewed"],
      quiz_recommendation_viewed: ["QuizRecommendationViewed"],
      quiz_cta_viewed: ["QuizCtaViewed"],
    };
    const names = [normalized];
    if (normalized === "pre_sales_page_view") {
      names.push("presell_page_view");
    }
    if (normalized === "pre_sales_to_sales_click") {
      names.push("cta_click");
    }
    if (Array.isArray(rmbcAliasesByEventType[normalized])) {
      rmbcAliasesByEventType[normalized].forEach((alias) => names.push(alias));
    }
    return names;
  };

  const resolvePostHogCaptures = (eventType, props, baseEventProps, providedMappedCaptures, eventSourceUrl) => {
    const sanitizedProps = sanitizePostHogProps(props);
    const canonicalEventId = cleanText(props && props.eventId);
    const pageStage = cleanText((props && props.pageStage) || config.pageStage);
    const contentCategory = resolvePostHogContentCategory(pageStage);
    const attributionProps = resolveMetaAttributionProps(eventSourceUrl);
    const canonicalEventNames = resolveCanonicalPostHogEventNames(eventType);
    const mappedCaptures = Array.isArray(providedMappedCaptures)
      ? providedMappedCaptures
      : resolveMappedMetaEvents(eventType, props);
    const buildEventProps = (eventName, role, eventId, extraProps) => {
      const eventProps = {
        ...baseEventProps,
        ...sanitizedProps,
        ...(isRecord(extraProps) ? extraProps : {}),
        internal_event_type: eventType,
        canonical_event_type: role === "platform_alias" ? eventType : eventName,
        posthog_event_role: role,
        ...(canonicalEventId ? { mos_event_id: canonicalEventId } : {}),
        ...attributionProps,
        $event_id: eventId,
      };
      if (contentCategory) {
        eventProps.content_category = contentCategory;
      }
      if (eventType === "sales_page_view") {
        eventProps.from_presale = props && props.fromPresale === true;
      }
      return eventProps;
    };
    const captures = canonicalEventNames.map((eventName, index) => {
      const eventId = index === 0 && canonicalEventId
        ? canonicalEventId
        : buildPostHogEventId(eventName, eventType, index);
      return {
        eventName,
        eventProps: buildEventProps(eventName, index === 0 ? "canonical" : "rmbc_alias", eventId),
      };
    });
    mappedCaptures.forEach((capture, index) => {
      if (canonicalEventNames.includes(capture.eventName)) {
        return;
      }
      const metaEventId = cleanText(capture.eventId) || buildMetaEventId(capture.eventName, eventType, index);
      captures.push({
        eventName: capture.eventName,
        eventProps: {
          ...buildEventProps(capture.eventName, "platform_alias", metaEventId, capture.params),
          canonical_event_type: eventType,
          meta_event_name: capture.eventName,
          meta_event_id: metaEventId,
        },
      });
    });
    return captures;
  };

  const trackMetaPixelCaptures = (mappedCaptures) => {
    const pixelId = ensureMetaPixelBootstrap();
    if (!pixelId || typeof window.fbq !== "function") {
      return;
    }
    const attributionParams = resolveMetaAttributionProps(window.location.href);
    mappedCaptures.forEach((capture) => {
      trackMetaPixel(capture.method, capture.eventName, {
        ...(isRecord(capture.params) ? capture.params : {}),
        ...attributionParams,
      }, capture.eventId);
    });
  };

  const trackEvent = (eventType, props) => {
    const canonicalEventId = cleanText(props && props.eventId) || buildCanonicalEventId(eventType);
    const eventProps = {
      eventId: canonicalEventId,
      ...(props || {}),
    };
    const mappedCaptures = resolveMappedMetaEvents(eventType, eventProps).map((capture, index) => ({
      ...capture,
      eventId: cleanText(capture.eventId) || buildMetaEventId(capture.eventName, eventType, index),
    }));
    trackMetaPixelCaptures(mappedCaptures);
    trackPostHogEvent(eventType, eventProps, mappedCaptures);
    try {
      const runtimeContextProps = resolveRuntimeContextProps(eventProps);
      void fetch(config.apiBaseUrl + "/public/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          events: [
            {
              eventId: canonicalEventId,
              eventType,
              occurredAt: new Date().toISOString(),
              publicationId: config.publicationId,
              pageId: config.pageId,
              visitorId: resolveCanonicalAnonymousId(),
              sessionId: resolveCanonicalSessionId(),
              path: window.location.pathname + window.location.search,
              referrer: document.referrer || undefined,
              utm: getUtmParams(),
              props: {
                ...runtimeContextProps,
                ...resolveMetaAttributionProps(window.location.href),
                fromPageId: config.pageId,
                slug: config.pageSlug,
                pageStage: config.pageStage,
                artifactMode: "html_deploy",
                htmlArtifactKind: cleanText(config.htmlArtifactKind),
                htmlDeploySchemaVersion: cleanText(config.htmlDeploySchemaVersion),
                metaEvents: mappedCaptures.map((capture) => ({
                  eventName: capture.eventName,
                  eventId: capture.eventId,
                })),
                ...eventProps,
              },
            },
          ],
        }),
        keepalive: true,
      }).catch((error) => {
        console.error("[HtmlDeployPage] Tracking failed.", error);
      });
    } catch (error) {
      console.error("[HtmlDeployPage] Tracking failed.", error);
    }
  };

  const installTrackEventBridge = () => {
    if (window.__mosStandaloneTrackEventBridgeInstalled) return;
    window.__mosStandaloneTrackEventBridgeInstalled = true;
    window.MOSStandaloneAnalytics = {
      trackEvent,
    };
    window.addEventListener("mos:track-event", (event) => {
      const detail = event && event.detail;
      if (!isRecord(detail)) return;
      const eventType = cleanText(detail.eventType);
      if (!eventType) return;
      const props = isRecord(detail.props) ? detail.props : {};
      trackEvent(eventType, props);
    });
  };

  const normalizeSelection = (selection) => {
    if (!isRecord(selection)) return null;
    const entries = Object.entries(selection)
      .map(([key, value]) => {
        const normalizedKey = cleanText(key);
        const normalizedValue = cleanText(typeof value === "string" ? value : null);
        if (!normalizedKey || !normalizedValue) return null;
        return [normalizedKey, normalizedValue];
      })
      .filter(Boolean);
    if (!entries.length) return null;
    return Object.fromEntries(entries);
  };

  const normalizePurchaseMode = (value) => {
    const normalized = cleanText(typeof value === "string" ? value : null);
    if (!normalized) return null;
    const lowered = normalized.toLowerCase();
    if (lowered === "subscribe") return "subscribe";
    if (["one-time", "one_time", "one time", "onetime"].includes(lowered)) return "one-time";
    return null;
  };

  const detectCheckoutPurchaseMode = () => {
    const hiddenInput = document.getElementById("mos-selected-purchase-mode");
    if (
      hiddenInput instanceof HTMLInputElement ||
      hiddenInput instanceof HTMLTextAreaElement ||
      hiddenInput instanceof HTMLSelectElement
    ) {
      const hiddenMode = normalizePurchaseMode(hiddenInput.value);
      if (hiddenMode) return hiddenMode;
    }

    const quantitySelector = document.getElementById("quantity-selector");
    if (quantitySelector instanceof HTMLElement) {
      const attributeMode = normalizePurchaseMode(quantitySelector.getAttribute("data-mode"));
      if (attributeMode) return attributeMode;
    }
    return null;
  };

  const augmentSelectionWithCheckoutContext = (selection) => {
    const normalizedSelection = normalizeSelection(selection) || {};
    const explicitPurchaseMode = normalizePurchaseMode(normalizedSelection.PurchaseMode);
    if (explicitPurchaseMode) {
      return {
        ...normalizedSelection,
        PurchaseMode: explicitPurchaseMode,
      };
    }

    const detectedPurchaseMode = detectCheckoutPurchaseMode();
    if (detectedPurchaseMode) {
      return {
        ...normalizedSelection,
        PurchaseMode: detectedPurchaseMode,
      };
    }

    return Object.keys(normalizedSelection).length ? normalizedSelection : null;
  };

  const stripCheckoutSelectionContext = (selection) => {
    const normalizedSelection = normalizeSelection(selection);
    if (!normalizedSelection) return null;
    const entries = Object.entries(normalizedSelection).filter(
      ([key]) => key.trim().toLowerCase() !== "purchasemode",
    );
    if (!entries.length) return null;
    return Object.fromEntries(entries);
  };

  const serializeVariant = (variant) => {
    if (!isRecord(variant)) return null;
    const id = cleanText(variant.id);
    if (!id) return null;
    const provider = cleanText(typeof variant.provider === "string" ? variant.provider.toLowerCase() : null);
    const currency = cleanText(variant.currency);
    const optionValues = normalizeSelection(variant.optionValues || variant.option_values || null);
    return {
      id,
      provider,
      price: typeof variant.price === "number" ? variant.price : null,
      currency,
      optionValues,
    };
  };

  let cachedVariants = Array.isArray(config.variants)
    ? config.variants.map(serializeVariant).filter(Boolean)
    : [];
  let cachedCommercePromise = null;
  const preparedCheckoutCache = {};
  const preparedCheckoutInFlight = {};
  const preparedCheckoutTransitionIds = {};
  const checkoutOriginPreconnects = {};
  const checkoutUrlPrefetches = {};
  const checkoutBindingElements = {};
  const checkoutBindingState = {};
  const PREPARED_CHECKOUT_TTL_MS = 10 * 60 * 1000;
  const PREPARED_CHECKOUT_POLL_INTERVAL_MS = 150;
  const PREPARED_CHECKOUT_POLL_TIMEOUT_MS = 10 * 1000;
  const CHECKOUT_LOADING_LABEL = "Preparing secure checkout...";
  const CHECKOUT_CLICK_LOADING_LABEL = "Opening secure checkout...";
  const CHECKOUT_ERROR_LABEL = "Secure checkout is unavailable right now.";
  let warmCheckoutBindingsTimeout = null;
  let checkoutNavigationInProgress = false;

  const resolvePageViewEventType = () => {
    if (config.pageStage === "pre_sales") return "pre_sales_page_view";
    if (config.pageStage === "sales") return "sales_page_view";
    if (config.pageStage === "checkout") return "checkout_page_view";
    if (config.pageStage === "thank_you") return "thank_you_page_view";
    return "custom_page_view";
  };

  const trackInitialPageView = () => {
    const trackedPageViewIds = window.__mosStandaloneImportedHtmlTrackedPageViewIds || [];
    if (trackedPageViewIds.includes(config.pageId)) {
      return;
    }
    trackedPageViewIds.push(config.pageId);
    window.__mosStandaloneImportedHtmlTrackedPageViewIds = trackedPageViewIds;
    const presaleSignal = config.pageStage === "sales" ? resolvePresaleAttribution() : null;
    const pageViewProps = {
      pageStage: config.pageStage,
      ...(presaleSignal
        ? {
            fromPresale: true,
            presaleSignal,
          }
        : {}),
    };
    trackEvent(resolvePageViewEventType(), pageViewProps);
    if (config.pageStage === "pre_sales") {
      trackEvent("presell_page_view", {
        ...pageViewProps,
        rmbcEventName: "EnteredPresales",
      });
    }
    if (config.pageStage === "sales") {
      trackEvent("offer_page_view", pageViewProps);
    }
  };

  const scheduleInitialPageView = () => {
    const run = () => {
      try {
        trackInitialPageView();
      } catch (error) {
        console.error("[HtmlDeployPage] Failed to track initial page view.", error);
      }
    };
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(run);
      return;
    }
    window.setTimeout(run, 0);
  };

  const SCROLL_DEPTH_MILESTONES = [10, 25, 50, 75, 90, 100];
  const QUALIFIED_ACTIVE_TIME_MS = 3000;
  const QUALIFIED_SCROLL_DEPTH_PCT = 25;
  const scrollDepthStateByKey = {};
  const observedViewTargetKeys = {};
  const interactionListenerKeys = {};
  let interactionSequence = 0;
  let maxScrollDepthPct = 0;
  let scrollTrackingScheduled = false;
  let qualifiedSessionTracked = false;
  let engagementTrackingInitialized = false;
  let activeStartedAt = Date.now();
  let activeAccumulatedMs = 0;

  const currentActiveTimeMs = () => {
    if (document.visibilityState === "hidden") {
      return activeAccumulatedMs;
    }
    return activeAccumulatedMs + Math.max(0, Date.now() - activeStartedAt);
  };

  const pauseActiveTime = () => {
    if (document.visibilityState === "hidden") {
      return;
    }
    activeAccumulatedMs = currentActiveTimeMs();
  };

  const resumeActiveTime = () => {
    activeStartedAt = Date.now();
  };

  const trackQualifiedSession = (reason) => {
    if (qualifiedSessionTracked) return;
    qualifiedSessionTracked = true;
    trackEvent("qualified_session", {
      reason,
      activeTimeMs: Math.round(currentActiveTimeMs()),
      maxScrollDepthPct,
      qualificationActiveTimeMs: QUALIFIED_ACTIVE_TIME_MS,
      qualificationScrollDepthPct: QUALIFIED_SCROLL_DEPTH_PCT,
    });
  };

  const evaluateQualifiedSession = (reason) => {
    if (currentActiveTimeMs() >= QUALIFIED_ACTIVE_TIME_MS || maxScrollDepthPct >= QUALIFIED_SCROLL_DEPTH_PCT) {
      trackQualifiedSession(reason);
    }
  };

  let lastScrollDepthElement = null;
  const resolveScrollDepthStateKey = () => {
    return [
      cleanText(config.pageId) || "page",
      window.location.pathname || "",
      window.location.search || "",
      window.location.hash || "",
    ].join("|");
  };
  const resolveScrollDepthState = () => {
    const key = resolveScrollDepthStateKey();
    if (!scrollDepthStateByKey[key]) {
      scrollDepthStateByKey[key] = {
        maxScrollDepthPct: 0,
        trackedMilestones: {},
      };
    }
    return scrollDepthStateByKey[key];
  };
  const calculateElementScrollDepthPct = (element) => {
    if (!(element instanceof HTMLElement)) return null;
    if (element.isConnected === false) return null;
    const scrollHeight = element.scrollHeight || 0;
    const viewportHeight = element.clientHeight || 0;
    if (!scrollHeight || !viewportHeight) return null;
    if (viewportHeight >= scrollHeight) return null;
    const scrollTop = element.scrollTop || 0;
    return Math.max(0, Math.min(100, Math.round(((scrollTop + viewportHeight) / scrollHeight) * 100)));
  };

  const calculateWindowScrollDepthPct = () => {
    const doc = document.documentElement;
    const body = document.body;
    const scrollTop = window.scrollY || doc.scrollTop || (body && body.scrollTop) || 0;
    const viewportHeight = window.innerHeight || doc.clientHeight || 0;
    const scrollHeight = Math.max(
      doc.scrollHeight || 0,
      body ? body.scrollHeight || 0 : 0,
      doc.offsetHeight || 0,
      body ? body.offsetHeight || 0 : 0,
      viewportHeight,
    );
    if (!scrollHeight || viewportHeight >= scrollHeight) return null;
    return Math.max(0, Math.min(100, Math.round(((scrollTop + viewportHeight) / scrollHeight) * 100)));
  };

  const calculateScrollDepthPct = () => {
    const windowPct = calculateWindowScrollDepthPct();
    const elementPct = calculateElementScrollDepthPct(lastScrollDepthElement);
    if (typeof elementPct === "number" && Number.isFinite(elementPct)) {
      return typeof windowPct === "number" && Number.isFinite(windowPct)
        ? Math.max(windowPct, elementPct)
        : elementPct;
    }
    return windowPct;
  };

  const resolveScrollDepthElement = (event) => {
    const target = event && event.target;
    if (!(target instanceof HTMLElement)) return null;
    const maxScroll = Math.max(0, (target.scrollHeight || 0) - (target.clientHeight || 0));
    if (maxScroll <= 8) return null;
    return target;
  };

  const handleScrollDepthTracking = () => {
    scrollTrackingScheduled = false;
    const scrollDepthPct = calculateScrollDepthPct();
    if (typeof scrollDepthPct !== "number" || !Number.isFinite(scrollDepthPct)) {
      return;
    }
    const scrollDepthState = resolveScrollDepthState();
    scrollDepthState.maxScrollDepthPct = Math.max(
      scrollDepthState.maxScrollDepthPct,
      scrollDepthPct,
    );
    maxScrollDepthPct = Math.max(maxScrollDepthPct, scrollDepthState.maxScrollDepthPct);
    for (const milestone of SCROLL_DEPTH_MILESTONES) {
      if (
        scrollDepthState.maxScrollDepthPct >= milestone &&
        scrollDepthState.trackedMilestones[milestone] !== true
      ) {
        scrollDepthState.trackedMilestones[milestone] = true;
        trackEvent("scroll_depth", {
          scrollDepthPct: milestone,
          maxScrollDepthPct: scrollDepthState.maxScrollDepthPct,
          activeTimeMs: Math.round(currentActiveTimeMs()),
        });
      }
    }
    evaluateQualifiedSession("scroll_depth");
  };

  const scheduleScrollDepthTracking = (event) => {
    const scrollElement = resolveScrollDepthElement(event);
    if (scrollElement) {
      lastScrollDepthElement = scrollElement;
    }
    if (scrollTrackingScheduled) return;
    scrollTrackingScheduled = true;
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(handleScrollDepthTracking);
      return;
    }
    window.setTimeout(handleScrollDepthTracking, 0);
  };

  const initializeEngagementTracking = () => {
    if (engagementTrackingInitialized) return;
    engagementTrackingInitialized = true;
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        pauseActiveTime();
        return;
      }
      resumeActiveTime();
    });
    window.addEventListener("pagehide", pauseActiveTime);
    window.addEventListener("scroll", scheduleScrollDepthTracking, { passive: true, capture: true });
    document.addEventListener("scroll", scheduleScrollDepthTracking, { passive: true, capture: true });
    window.addEventListener("resize", scheduleScrollDepthTracking);
    window.setInterval(() => evaluateQualifiedSession("active_time"), 1000);
  };

  const observationTargetsFromManifest = () => {
    const targets = [];
    const addTarget = (eventType, kind, target) => {
      if (!target || typeof target !== "object") return;
      const id = cleanText(target.id);
      const selector = cleanText(target.selector);
      if (!id || !selector) return;
      targets.push({
        eventType,
        kind,
        id,
        selector,
        label: cleanText(target.label),
        proofType: cleanText(target.proofType),
        sectionId: cleanText(target.sectionId),
        ctaPosition: Number.isFinite(Number(target.ctaPosition)) ? Number(target.ctaPosition) : undefined,
        declaredProps: buildDeclaredTargetProps(target),
      });
    };

    const manifest = config.manifest || {};
    const htmlArtifactKind = cleanText(config.htmlArtifactKind);
    const hasExplicitCtaTargets = Array.isArray(manifest.ctas) && manifest.ctas.length > 0;
    if (Array.isArray(manifest.sections)) {
      manifest.sections.forEach((target) => addTarget("section_view", "section", target));
    }
    if (Array.isArray(manifest.proofs)) {
      manifest.proofs.forEach((target) => addTarget("proof_view", "proof", target));
      if (htmlArtifactKind === "quiz") {
        manifest.proofs.forEach((target) => addTarget("quiz_proof_viewed", "quiz_proof", target));
      }
    }
    if (Array.isArray(manifest.ctas)) {
      manifest.ctas.forEach((target) => addTarget("cta_view", "cta", target));
      if (htmlArtifactKind === "quiz") {
        manifest.ctas.forEach((target) => addTarget("quiz_cta_viewed", "quiz_cta", target));
      }
    }
    if (Array.isArray(manifest.offerStacks)) {
      manifest.offerStacks.forEach((target) => addTarget("offer_stack_view", "offer_stack", target));
    }
    if (Array.isArray(manifest.valueStacks)) {
      manifest.valueStacks.forEach((target) => addTarget("value_stack_view", "value_stack", target));
    }
    if (Array.isArray(manifest.priceReveals)) {
      manifest.priceReveals.forEach((target) => addTarget("price_reveal_view", "price_reveal", target));
    }
    if (Array.isArray(manifest.guarantees)) {
      manifest.guarantees.forEach((target) => addTarget("guarantee_view", "guarantee", target));
    }
    if (Array.isArray(manifest.trustElements)) {
      manifest.trustElements.forEach((target) => addTarget("trust_element_view", "trust_element", target));
    }
    if (Array.isArray(manifest.quizLeads)) {
      manifest.quizLeads.forEach((target) => addTarget("quiz_lead_viewed", "quiz_lead", target));
    }
    if (Array.isArray(manifest.quizQuestions)) {
      manifest.quizQuestions.forEach((target) => addTarget("quiz_question_viewed", "quiz_question", target));
    }
    if (Array.isArray(manifest.quizOptions)) {
      manifest.quizOptions.forEach((target) => addTarget("quiz_option_presented", "quiz_option", target));
    }
    if (Array.isArray(manifest.quizResults)) {
      manifest.quizResults.forEach((target) => addTarget("quiz_result_viewed", "quiz_result", target));
    }
    if (Array.isArray(manifest.quizMechanisms)) {
      manifest.quizMechanisms.forEach((target) => addTarget("quiz_mechanism_viewed", "quiz_mechanism", target));
    }
    if (Array.isArray(manifest.quizRecommendations)) {
      manifest.quizRecommendations.forEach((target) => addTarget("quiz_recommendation_viewed", "quiz_recommendation", target));
    }
    if (!hasExplicitCtaTargets && Array.isArray(manifest.bindings)) {
      manifest.bindings.forEach((binding) => {
        if (!binding || typeof binding !== "object") return;
        const id = cleanText(binding.id);
        const selector = cleanText(binding.selector);
        if (!id || !selector) return;
        targets.push({
          eventType: "cta_view",
          kind: "cta",
          id,
          selector,
          bindingType: cleanText(binding.type),
          trackEventType: cleanText(binding.trackEventType),
        });
      });
    }
    return targets;
  };

  const trackObservedViewTarget = (target, element, index) => {
    const key = [target.eventType, target.id, String(index)].join(":");
    if (observedViewTargetKeys[key] === true) return;
    observedViewTargetKeys[key] = true;
    trackEvent(target.eventType, {
      targetKind: target.kind,
      targetId: target.id,
      selector: target.selector,
      label: target.label || undefined,
      bindingType: target.bindingType || undefined,
      trackEventType: target.trackEventType || undefined,
      text: normalizeText(element.textContent || "").slice(0, 160) || undefined,
      activeTimeMs: Math.round(currentActiveTimeMs()),
      maxScrollDepthPct,
      depthPct: maxScrollDepthPct,
      depth_pct: maxScrollDepthPct,
      ...(target.kind === "cta"
        ? {
            ctaId: target.id,
            cta_id: target.id,
            ctaPosition: target.ctaPosition || index + 1,
            cta_position: target.ctaPosition || index + 1,
          }
        : {}),
      ...(target.kind === "section"
        ? {
            sectionId: target.sectionId || target.id,
            section_id: target.sectionId || target.id,
          }
        : {}),
      ...(target.kind === "proof"
        ? {
            proofId: target.id,
            proof_id: target.id,
            proofType: target.proofType || undefined,
            proof_type: target.proofType || undefined,
            sectionId: target.sectionId || undefined,
            section_id: target.sectionId || undefined,
          }
        : {}),
      ...(target.kind === "offer_stack" ? { offerStackId: target.id, offer_id: target.id } : {}),
      ...(target.kind === "value_stack" ? { valueStackId: target.id } : {}),
      ...(target.kind === "price_reveal" ? { priceRevealId: target.id } : {}),
      ...(target.kind === "guarantee" ? { guaranteeId: target.id, guarantee_id: target.id } : {}),
      ...(target.kind === "trust_element" ? { trustElementId: target.id } : {}),
      ...(target.kind === "quiz_lead" ? { quizLeadId: target.id, quiz_lead_id: target.id } : {}),
      ...(target.kind === "quiz_question" ? { questionId: target.id, question_id: target.id } : {}),
      ...(target.kind === "quiz_option" ? { optionId: target.id, option_id: target.id } : {}),
      ...(target.kind === "quiz_result" ? { resultId: target.id, result_id: target.id } : {}),
      ...(target.kind === "quiz_mechanism" ? { mechanismId: target.id, mechanism_id: target.id } : {}),
      ...(target.kind === "quiz_proof" ? { proofId: target.id, proof_id: target.id } : {}),
      ...(target.kind === "quiz_recommendation"
        ? { recommendationId: target.id, recommendation_id: target.id }
        : {}),
      ...(target.kind === "quiz_cta"
        ? {
            ctaId: target.id,
            cta_id: target.id,
            ctaPosition: target.ctaPosition || index + 1,
            cta_position: target.ctaPosition || index + 1,
          }
        : {}),
      ...(target.declaredProps || {}),
    });
  };

  const initializeViewTracking = () => {
    if (typeof window.IntersectionObserver !== "function") return;
    const targets = observationTargetsFromManifest();
    if (!targets.length) return;
    const observer = new window.IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting || entry.intersectionRatio < 0.5) return;
          const targetConfig = entry.target.__mosViewTrackingTarget;
          const targetIndex = entry.target.__mosViewTrackingIndex || 0;
          if (targetConfig) {
            trackObservedViewTarget(targetConfig, entry.target, targetIndex);
          }
          observer.unobserve(entry.target);
        });
      },
      { threshold: [0.5] },
    );
    targets.forEach((target) => {
      const matches = Array.from(document.querySelectorAll(target.selector));
      matches.forEach((element, index) => {
        if (!(element instanceof HTMLElement)) return;
        const key = [target.eventType, target.id, String(index)].join(":");
        if (observedViewTargetKeys[key] === true) return;
        element.__mosViewTrackingTarget = target;
        element.__mosViewTrackingIndex = index;
        observer.observe(element);
      });
    });
  };

  const interactionTargetsFromManifest = () => {
    const targets = [];
    const addTarget = (eventType, kind, target) => {
      if (!target || typeof target !== "object") return;
      const id = cleanText(target.id);
      const selector = cleanText(target.selector);
      if (!id || !selector) return;
      targets.push({
        eventType,
        kind,
        id,
        selector,
        label: cleanText(target.label),
        event: target.event === "input" || target.event === "change" ? target.event : "click",
        source: target.source === "text" || target.source === "checked" ? target.source : "value",
        interactionType: cleanText(target.interactionType) || kind,
        submitOnSelect: target.submitOnSelect === true,
        declaredProps: buildDeclaredTargetProps(target),
      });
    };
    const manifest = config.manifest || {};
    if (Array.isArray(manifest.quizOptions)) {
      manifest.quizOptions.forEach((target) => addTarget("quiz_option_selected", "quiz_option", target));
    }
    if (Array.isArray(manifest.quizSubmissions)) {
      manifest.quizSubmissions.forEach((target) => addTarget("quiz_question_submitted", "quiz_submission", target));
    }
    if (Array.isArray(manifest.selectors)) {
      manifest.selectors.forEach((target) => addTarget("selector_interaction", "selector", target));
    }
    if (Array.isArray(manifest.productDetails)) {
      manifest.productDetails.forEach((target) =>
        addTarget("product_detail_interaction", "product_detail", target),
      );
    }
    return targets;
  };

  const readInteractionValue = (element, source) => {
    if (source === "checked") {
      return element instanceof HTMLInputElement ? (element.checked ? "checked" : "unchecked") : undefined;
    }
    if (source === "text") {
      return normalizeText(element.textContent || "") || undefined;
    }
    if (element instanceof HTMLInputElement || element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) {
      return normalizeText(element.value || "") || undefined;
    }
    return normalizeText(element.textContent || "") || undefined;
  };

  const selectedValueLooksSubscribed = (value) => {
    const normalized = String(value || "").trim().toLowerCase();
    return normalized === "subscribe" || normalized === "subscription" || normalized.includes("subscribe");
  };

  const trackInteractionTarget = (target, element) => {
    interactionSequence += 1;
    const selectedValue = readInteractionValue(element, target.source);
    const props = {
      targetKind: target.kind,
      targetId: target.id,
      selector: target.selector,
      label: target.label || undefined,
      interactionType: target.interactionType,
      ...(target.declaredProps || {}),
      selectedValue,
      selected_value: selectedValue,
      text: normalizeText(element.textContent || "").slice(0, 160) || undefined,
      activeTimeMs: Math.round(currentActiveTimeMs()),
      maxScrollDepthPct,
      interactionSequence,
      ...(target.kind === "selector" ? { selectorId: target.id } : {}),
      ...(target.kind === "product_detail" ? { productDetailId: target.id } : {}),
      ...(target.kind === "quiz_option" ? { optionId: target.id, option_id: target.id } : {}),
      ...(target.kind === "quiz_submission" ? { questionSubmitId: target.id, question_submit_id: target.id } : {}),
    };
    const enrichedProps = {
      ...props,
      ...((target.kind === "quiz_option" || target.kind === "quiz_submission")
        ? updateQuizAnswerState(target.eventType, props)
        : {}),
    };
    trackEvent(target.eventType, enrichedProps);
    if (target.eventType === "quiz_option_selected") {
      const autoSubmit = target.submitOnSelect === true || !isMultiSelectQuestion(null, enrichedProps);
      if (autoSubmit) {
        trackEvent("quiz_question_submitted", {
          ...enrichedProps,
          ...updateQuizAnswerState("quiz_question_submitted", enrichedProps),
        });
      }
    }
    if (target.eventType === "selector_interaction" && selectedValueLooksSubscribed(selectedValue)) {
      trackEvent("subscription_selected", {
        ...enrichedProps,
        subscription_flag: true,
      });
    }
    evaluateQualifiedSession("element_interaction");
  };

  const initializeInteractionTracking = () => {
    const targets = interactionTargetsFromManifest();
    if (!targets.length) return;
    targets.forEach((target) => {
      const matches = Array.from(document.querySelectorAll(target.selector));
      matches.forEach((element, index) => {
        if (!(element instanceof HTMLElement)) return;
        const key = [target.eventType, target.id, String(index), target.event].join(":");
        if (interactionListenerKeys[key] === true) return;
        interactionListenerKeys[key] = true;
        if (target.kind === "quiz_option" || target.kind === "quiz_submission") {
          element.dataset.mosDirectControlTracking = "true";
        }
        element.addEventListener(target.event, () => trackInteractionTarget(target, element), {
          passive: true,
        });
      });
    });
  };

  const initializeEngagementTrackingSafely = () => {
    try {
      initializeEngagementTracking();
    } catch (error) {
      console.error("[HtmlDeployPage] Failed to initialize engagement tracking.", error);
    }
  };

  const initializeViewTrackingSafely = () => {
    try {
      initializeViewTracking();
    } catch (error) {
      console.error("[HtmlDeployPage] Failed to initialize view tracking.", error);
    }
  };

  const initializeInteractionTrackingSafely = () => {
    try {
      initializeInteractionTracking();
    } catch (error) {
      console.error("[HtmlDeployPage] Failed to initialize interaction tracking.", error);
    }
  };

  const selectionsMatch = (left, right) => {
    const normalizedLeft = stripCheckoutSelectionContext(left);
    const normalizedRight = stripCheckoutSelectionContext(right);
    if (!normalizedLeft || !normalizedRight) return false;
    const leftEntries = Object.entries(normalizedLeft);
    const rightEntries = Object.entries(normalizedRight);
    if (leftEntries.length !== rightEntries.length) return false;
    return leftEntries.every(([key, value]) => normalizedRight[key] === value);
  };

  const buildPreparedCheckoutCacheKey = (variantId, selection) => {
    const normalizedSelection = normalizeSelection(selection) || {};
    const selectionEntries = Object.entries(normalizedSelection).sort(([left], [right]) =>
      left.localeCompare(right),
    );
    return JSON.stringify({
      variantId: cleanText(variantId) || "",
      selection: selectionEntries,
    });
  };

  const getPreparedCheckoutRecord = (cacheKey) => {
    const record = cacheKey ? preparedCheckoutCache[cacheKey] : null;
    if (!record) return null;
    if (Date.now() - record.createdAt > PREPARED_CHECKOUT_TTL_MS) {
      delete preparedCheckoutCache[cacheKey];
      return null;
    }
    return record;
  };

  const ensureCheckoutOriginPreconnect = (checkoutUrl) => {
    const href = cleanText(checkoutUrl);
    if (!href) return;
    let origin = "";
    try {
      origin = new URL(href, window.location.href).origin;
    } catch (_) {
      return;
    }
    if (!origin || checkoutOriginPreconnects[origin]) return;
    checkoutOriginPreconnects[origin] = true;
    const preconnect = document.createElement("link");
    preconnect.rel = "preconnect";
    preconnect.href = origin;
    preconnect.crossOrigin = "anonymous";
    document.head.appendChild(preconnect);
    const dnsPrefetch = document.createElement("link");
    dnsPrefetch.rel = "dns-prefetch";
    dnsPrefetch.href = origin;
    document.head.appendChild(dnsPrefetch);
  };

  const ensureCheckoutUrlPrefetch = (checkoutUrl) => {
    const href = cleanText(checkoutUrl);
    if (!href || checkoutUrlPrefetches[href]) return;
    checkoutUrlPrefetches[href] = true;
    const prefetch = document.createElement("link");
    prefetch.rel = "prefetch";
    prefetch.as = "document";
    prefetch.href = href;
    prefetch.crossOrigin = "anonymous";
    document.head.appendChild(prefetch);
  };

  const ensureCheckoutStatusNote = (bindingId, element) => {
    const existingId = cleanText(element.dataset.mosCheckoutStatusNoteId);
    if (existingId) {
      const existing = document.getElementById(existingId);
      if (existing) return existing;
    }
    const noteId =
      "mos-checkout-status-" +
      String(bindingId || "unknown") +
      "-" +
      String((checkoutBindingElements[bindingId] || []).length);
    const note = document.createElement("span");
    note.id = noteId;
    note.style.display = "none";
    note.style.width = "100%";
    note.style.marginTop = "0.5rem";
    note.style.fontSize = "0.75rem";
    note.style.lineHeight = "1.4";
    note.style.fontWeight = "600";
    note.style.letterSpacing = "normal";
    note.style.textTransform = "none";
    note.style.textAlign = "center";
    note.style.opacity = "0.82";
    note.style.color = "inherit";
    note.setAttribute("aria-live", "polite");
    element.insertAdjacentElement("afterend", note);
    element.dataset.mosCheckoutStatusNoteId = noteId;
    return note;
  };

  const CHECKOUT_INLINE_LABEL_SELECTOR =
    "[data-tenor-cart-checkout-label], [data-mos-checkout-label], [data-checkout-label]";

  const checkoutInlineLoadingLabel = (labelElement, label) => {
    if (labelElement && labelElement.hasAttribute("data-tenor-cart-checkout-label")) {
      return "Loading...";
    }
    return cleanText(label) || CHECKOUT_LOADING_LABEL;
  };

  const setCheckoutElementVisualWaiting = (element, waiting, label) => {
    if (!(element instanceof HTMLElement)) return;
    const labelTargets = Array.from(element.querySelectorAll(CHECKOUT_INLINE_LABEL_SELECTOR)).filter(
      (target) => target instanceof HTMLElement,
    );
    if (waiting) {
      if (!("mosCheckoutSavedIsLoadingClass" in element.dataset)) {
        element.dataset.mosCheckoutSavedIsLoadingClass = element.classList.contains("is-loading") ? "true" : "false";
      }
      if (!("mosCheckoutSavedLoadingClass" in element.dataset)) {
        element.dataset.mosCheckoutSavedLoadingClass = element.classList.contains("loading") ? "true" : "false";
      }
      element.classList.add("is-loading");
      if (element.querySelector(".loading__spinner")) {
        element.classList.add("loading");
      }
      labelTargets.forEach((target) => {
        if (!("mosCheckoutSavedLabel" in target.dataset)) {
          target.dataset.mosCheckoutSavedLabel = target.textContent || "";
        }
        target.textContent = checkoutInlineLoadingLabel(target, label);
      });
      return;
    }
    if (element.dataset.mosCheckoutSavedIsLoadingClass !== "true") {
      element.classList.remove("is-loading");
    }
    if (element.dataset.mosCheckoutSavedLoadingClass !== "true") {
      element.classList.remove("loading");
    }
    delete element.dataset.mosCheckoutSavedIsLoadingClass;
    delete element.dataset.mosCheckoutSavedLoadingClass;
    labelTargets.forEach((target) => {
      if ("mosCheckoutSavedLabel" in target.dataset) {
        target.textContent = target.dataset.mosCheckoutSavedLabel || "";
        delete target.dataset.mosCheckoutSavedLabel;
      }
    });
  };

  const setCheckoutElementWaiting = (bindingId, element, waiting, label) => {
    const note = ensureCheckoutStatusNote(bindingId, element);
    if (waiting) {
      if (!("mosCheckoutSavedPointerEvents" in element.dataset)) {
        element.dataset.mosCheckoutSavedPointerEvents = element.style.pointerEvents || "";
      }
      if (!("mosCheckoutSavedOpacity" in element.dataset)) {
        element.dataset.mosCheckoutSavedOpacity = element.style.opacity || "";
      }
      if (!("mosCheckoutSavedCursor" in element.dataset)) {
        element.dataset.mosCheckoutSavedCursor = element.style.cursor || "";
      }
      if (element instanceof HTMLButtonElement && !("mosCheckoutSavedDisabled" in element.dataset)) {
        element.dataset.mosCheckoutSavedDisabled = element.disabled ? "true" : "false";
      }
      element.dataset.mosCheckoutWaiting = "true";
      element.setAttribute("aria-busy", "true");
      element.setAttribute("aria-disabled", "true");
      element.style.pointerEvents = "none";
      element.style.opacity = "0.72";
      element.style.cursor = "progress";
      if (element instanceof HTMLButtonElement) {
        element.disabled = true;
      }
      setCheckoutElementVisualWaiting(element, true, label);
      note.textContent = cleanText(label) || CHECKOUT_LOADING_LABEL;
      note.style.display = "block";
      return;
    }

    setCheckoutElementVisualWaiting(element, false, label);
    delete element.dataset.mosCheckoutWaiting;
    element.removeAttribute("aria-busy");
    element.removeAttribute("aria-disabled");
    element.style.pointerEvents = element.dataset.mosCheckoutSavedPointerEvents || "";
    element.style.opacity = element.dataset.mosCheckoutSavedOpacity || "";
    element.style.cursor = element.dataset.mosCheckoutSavedCursor || "";
    delete element.dataset.mosCheckoutSavedPointerEvents;
    delete element.dataset.mosCheckoutSavedOpacity;
    delete element.dataset.mosCheckoutSavedCursor;
    if (element instanceof HTMLButtonElement) {
      const wasDisabled = element.dataset.mosCheckoutSavedDisabled === "true";
      element.disabled = wasDisabled;
      delete element.dataset.mosCheckoutSavedDisabled;
    }
    note.textContent = "";
    note.style.display = "none";
  };

  const renderCheckoutBindingState = (bindingId) => {
    const state = checkoutBindingState[bindingId] || { status: "idle", message: null };
    const waiting = state.status === "loading";
    const elements = checkoutBindingElements[bindingId] || [];
    for (const element of elements) {
      setCheckoutElementWaiting(bindingId, element, waiting, state.message || CHECKOUT_LOADING_LABEL);
    }
  };

  const setCheckoutBindingState = (bindingId, nextState) => {
    checkoutBindingState[bindingId] = {
      ...(checkoutBindingState[bindingId] || { status: "idle", cacheKey: null, message: null }),
      ...nextState,
    };
    renderCheckoutBindingState(bindingId);
  };

  const registerCheckoutElement = (bindingId, element) => {
    const list = checkoutBindingElements[bindingId] || [];
    if (!list.includes(element)) {
      list.push(element);
      checkoutBindingElements[bindingId] = list;
    }
    if (element.dataset.mosCheckoutWarmBound !== "true") {
      element.dataset.mosCheckoutWarmBound = "true";
      element.addEventListener("pointerenter", () => scheduleWarmCheckoutBindings(75), { passive: true });
      element.addEventListener("touchstart", () => scheduleWarmCheckoutBindings(0), { passive: true });
      element.addEventListener("mousedown", () => scheduleWarmCheckoutBindings(0), { passive: true });
      element.addEventListener("focus", () => scheduleWarmCheckoutBindings(0));
    }
    renderCheckoutBindingState(bindingId);
  };

  const resolveExternalCheckoutUrlForVariant = (items, variantId) => {
    if (!Array.isArray(items) || !variantId) return null;
    const match = items.find((item) => item && item.variantId === variantId && typeof item.url === "string");
    return match ? cleanText(match.url) : null;
  };

  const parseResponseError = async (response) => {
    try {
      const payload = await response.clone().json();
      const firstError = Array.isArray(payload && payload.errors) ? payload.errors[0] : null;
      const errorDetail = cleanText(firstError && firstError.detail);
      if (errorDetail) return errorDetail;
      const errorTitle = cleanText(firstError && firstError.title);
      if (errorTitle) return errorTitle;
      const detail = cleanText(payload && payload.detail);
      if (detail) return detail;
      const message = cleanText(payload && payload.message);
      if (message) return message;
    } catch (_) {
      // ignore and fall back to plain text
    }
    try {
      const text = cleanText(await response.text());
      if (text) return text;
    } catch (_) {
      // ignore and fall back to status text
    }
    return cleanText(response.statusText) || "Request failed.";
  };

  const delay = (durationMs) =>
    new Promise((resolve) => {
      window.setTimeout(resolve, durationMs);
    });

  const loadCommerceVariants = async () => {
    if (cachedVariants.length) {
      return cachedVariants;
    }
    if (cachedCommercePromise) {
      return cachedCommercePromise;
    }
    cachedCommercePromise = fetch(
      config.apiBaseUrl +
        "/public/funnels/" +
        encodeURIComponent(config.productSlug) +
        "/" +
        encodeURIComponent(config.funnelSlug) +
        "/commerce",
    )
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(await parseResponseError(response));
        }
        const payload = await response.json();
        const product = payload && payload.product;
        const variants = Array.isArray(product && product.variants)
          ? product.variants.map(serializeVariant).filter(Boolean)
          : [];
        cachedVariants = variants;
        return cachedVariants;
      })
      .finally(() => {
        cachedCommercePromise = null;
      });
    return cachedCommercePromise;
  };

  const resolveCheckoutUrls = () => {
    const checkoutReturnUrl = new URL(window.location.href);
    const checkoutCancelUrl = new URL(window.location.href);
    checkoutReturnUrl.searchParams.set("checkout", "success");
    checkoutCancelUrl.searchParams.set("checkout", "cancel");
    return {
      successUrl: checkoutReturnUrl.toString(),
      cancelUrl: checkoutCancelUrl.toString(),
    };
  };

  const serializeCheckoutAttributeValue = (value) => {
    if (value === undefined || value === null) return null;
    if (typeof value === "string") return cleanText(value);
    return JSON.stringify(value);
  };

  const checkoutAttributionProps = ({ ctaId, transitionId, resolvedVariantId } = {}) => {
    const metaProps = resolveMetaAttributionProps(window.location.href);
    const clickProps = resolveClickAttribution();
    const experimentId = resolveExperimentId();
    const metaAddToCartEventId = resolveMetaAddToCartCheckoutEventId(resolvedVariantId);
    const metaInitiateCheckoutEventId = buildMetaInitiateCheckoutHandoffEventId(transitionId);
    return {
      ...(clickProps.clickId ? { clickId: clickProps.clickId, clickIdType: clickProps.clickIdType } : {}),
      ...(metaProps.fbp ? { fbp: metaProps.fbp } : {}),
      ...(metaProps.fbc ? { fbc: metaProps.fbc } : {}),
      ...(metaProps.external_id ? { externalId: metaProps.external_id } : {}),
      ...(metaProps.em ? { em: metaProps.em } : {}),
      ...(metaProps.event_source_url ? { eventSourceUrl: metaProps.event_source_url } : {}),
      pageVariant: cleanText(config.pageSlug),
      ...(experimentId ? { experimentId } : {}),
      ...(cleanText(ctaId) ? { ctaId: cleanText(ctaId) } : {}),
      ...(cleanText(transitionId) ? { transitionId: cleanText(transitionId) } : {}),
      ...(metaAddToCartEventId ? { mosMetaAddToCartEventId: metaAddToCartEventId } : {}),
      ...(metaInitiateCheckoutEventId ? { mosMetaInitiateCheckoutEventId: metaInitiateCheckoutEventId } : {}),
    };
  };

  const checkoutAttributeMap = ({ resolvedVariantId, resolvedSelection, ctaId, transitionId }) => {
    const attribution = checkoutAttributionProps({ ctaId, transitionId, resolvedVariantId });
    return {
      funnel_slug: cleanText(config.funnelSlug),
      funnel_id: cleanText(config.funnelId),
      publication_id: cleanText(config.publicationId),
      page_id: cleanText(config.pageId),
      visitor_id: cleanText(config.visitorId),
      session_id: cleanText(config.sessionId),
      variant_id: cleanText(resolvedVariantId),
      price_point_id: cleanText(resolvedVariantId),
      selection: resolvedSelection || {},
      utm: getUtmParams(),
      quantity: "1",
      click_id: attribution.clickId,
      click_id_type: attribution.clickIdType,
      fbp: attribution.fbp,
      fbc: attribution.fbc,
      external_id: attribution.externalId,
      em: attribution.em,
      event_source_url: attribution.eventSourceUrl,
      page_variant: attribution.pageVariant,
      experiment_id: attribution.experimentId,
      cta_id: attribution.ctaId,
      transition_id: attribution.transitionId,
      mos_meta_add_to_cart_event_id: attribution.mosMetaAddToCartEventId,
      mos_meta_initiate_checkout_event_id: attribution.mosMetaInitiateCheckoutEventId,
    };
  };

  const appendCheckoutAttributesToCartUrl = (checkoutUrl, attributes) => {
    const href = cleanText(checkoutUrl);
    if (!href) return href;
    let url;
    try {
      url = new URL(href, window.location.href);
    } catch (_) {
      return href;
    }
    if (!url.pathname.startsWith("/cart/")) {
      return href;
    }
    Object.entries(attributes || {}).forEach(([key, value]) => {
      const serialized = serializeCheckoutAttributeValue(value);
      if (serialized) {
        url.searchParams.set("attributes[" + key + "]", serialized);
      }
    });
    return url.toString();
  };

  const appendCheckoutTrackingUrlParams = (targetUrl) => {
    const href = cleanText(targetUrl);
    if (!href) return href;
    const url = new URL(href, window.location.href);
    const params = new URLSearchParams(window.location.search);
    for (const [key, value] of params.entries()) {
      if (isCheckoutTrackingParam(key)) {
        url.searchParams.set(key, value);
      }
    }
    return url.toString();
  };

  const checkoutUrlHost = (checkoutUrl) => {
    const href = cleanText(checkoutUrl);
    if (!href) return null;
    try {
      return new URL(href, window.location.href).host;
    } catch (_) {
      return null;
    }
  };

  const checkoutTimingProps = ({ transitionId, ctaId, checkoutUrl, resolvedVariantId, resolvedSelection }) => {
    const connection = window.navigator && window.navigator.connection;
    const props = {
      transitionId: cleanText(transitionId),
      ctaId: cleanText(ctaId),
      checkout_url_host: checkoutUrlHost(checkoutUrl),
      selected_offer: cleanText(resolvedSelection && (resolvedSelection.offerId || resolvedSelection.Offer || resolvedSelection.Pack)),
      variant_ids: cleanText(resolvedVariantId) ? [cleanText(resolvedVariantId)] : undefined,
      user_agent: window.navigator && window.navigator.userAgent,
      device_type: resolveDeviceType(),
      connection_effective_type: connection && connection.effectiveType,
      connection_rtt: connection && typeof connection.rtt === "number" ? connection.rtt : undefined,
      connection_downlink: connection && typeof connection.downlink === "number" ? connection.downlink : undefined,
      device_memory: window.navigator && typeof window.navigator.deviceMemory === "number" ? window.navigator.deviceMemory : undefined,
      performance_now_ms: window.performance && typeof window.performance.now === "function"
        ? Math.round(window.performance.now())
        : undefined,
      client_timestamp_ms: Date.now(),
    };
    return Object.fromEntries(Object.entries(props).filter(([, value]) => value !== undefined && value !== null && value !== ""));
  };

  let checkoutHandoffContext = null;
  let checkoutPagehideTracked = false;
  let checkoutVisibilityHiddenTracked = false;

  const trackCheckoutTimingEvent = (eventType, context) => {
    const props = isRecord(context) ? context : checkoutHandoffContext;
    if (!props) return;
    trackEvent(eventType, {
      ...props,
      performance_now_ms: window.performance && typeof window.performance.now === "function"
        ? Math.round(window.performance.now())
        : undefined,
      client_timestamp_ms: Date.now(),
    });
  };

  const installCheckoutHandoffTracking = () => {
    if (window.__mosCheckoutHandoffTrackingInstalled === true) return;
    window.__mosCheckoutHandoffTrackingInstalled = true;
    window.addEventListener("pagehide", () => {
      if (!checkoutHandoffContext || checkoutPagehideTracked !== false) return;
      checkoutPagehideTracked = true;
      trackCheckoutTimingEvent("checkout_pagehide", checkoutHandoffContext);
    });
    document.addEventListener("visibilitychange", () => {
      if (!checkoutHandoffContext || checkoutVisibilityHiddenTracked !== false) return;
      if (document.visibilityState !== "hidden") return;
      checkoutVisibilityHiddenTracked = true;
      trackCheckoutTimingEvent("checkout_visibility_hidden", checkoutHandoffContext);
    });
  };

  const createCheckoutPayload = ({ resolvedVariantId, resolvedSelection, ctaId, transitionId }) => {
    const checkoutUrls = resolveCheckoutUrls();
    return {
      funnelSlug: config.funnelSlug,
      variantId: resolvedVariantId || undefined,
      selection: resolvedSelection,
      quantity: 1,
      successUrl: checkoutUrls.successUrl,
      cancelUrl: checkoutUrls.cancelUrl,
      pageId: config.pageId,
      visitorId: config.visitorId,
      sessionId: config.sessionId,
      utm: getUtmParams(),
      ...checkoutAttributionProps({ ctaId, transitionId, resolvedVariantId }),
    };
  };

  const normalizePreparedCheckoutResponse = (data) => {
    if (!isRecord(data)) {
      throw new Error("Prepared checkout response is invalid.");
    }
    const preparedCheckoutId = cleanText(data.preparedCheckoutId);
    const status = cleanText(data.status);
    if (!preparedCheckoutId || !status) {
      throw new Error("Prepared checkout response is incomplete.");
    }
    return {
      preparedCheckoutId,
      status,
      checkoutUrl: cleanText(data.checkoutUrl),
      sessionId: cleanText(data.sessionId),
      error: cleanText(data.error),
      pollAfterMs: typeof data.pollAfterMs === "number" ? data.pollAfterMs : PREPARED_CHECKOUT_POLL_INTERVAL_MS,
    };
  };

  const requestCheckout = async ({ resolvedVariantId, resolvedSelection, ctaId, transitionId }) => {
    const response = await fetch(config.apiBaseUrl + "/public/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(createCheckoutPayload({ resolvedVariantId, resolvedSelection, ctaId, transitionId })),
    });

    if (!response.ok) {
      throw new Error((await response.text()) || response.statusText || "Checkout failed.");
    }

    const data = await response.json();
    const checkoutUrl = cleanText(data && data.checkoutUrl);
    if (!checkoutUrl) {
      throw new Error("Checkout URL is missing.");
    }
    ensureCheckoutOriginPreconnect(checkoutUrl);
    ensureCheckoutUrlPrefetch(checkoutUrl);
    return {
      checkoutUrl,
      sessionId: cleanText(data && data.sessionId) || null,
    };
  };

  const requestPreparedCheckout = async ({ resolvedVariantId, resolvedSelection, ctaId, transitionId }) => {
    const response = await fetch(config.apiBaseUrl + "/public/checkout/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(createCheckoutPayload({ resolvedVariantId, resolvedSelection, ctaId, transitionId })),
    });

    if (!response.ok) {
      throw new Error(await parseResponseError(response));
    }

    return normalizePreparedCheckoutResponse(await response.json());
  };

  const requestPreparedCheckoutStatus = async (preparedCheckoutId) => {
    const response = await fetch(
      config.apiBaseUrl + "/public/checkout/prepare/" + encodeURIComponent(preparedCheckoutId),
      {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      },
    );

    if (!response.ok) {
      throw new Error(await parseResponseError(response));
    }

    return normalizePreparedCheckoutResponse(await response.json());
  };

  const consumePreparedCheckout = async (preparedCheckoutId) => {
    const response = await fetch(
      config.apiBaseUrl + "/public/checkout/prepare/" + encodeURIComponent(preparedCheckoutId) + "/consume",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      },
    );

    if (!response.ok) {
      throw new Error(await parseResponseError(response));
    }

    const data = await response.json();
    const checkoutUrl = cleanText(data && data.checkoutUrl);
    if (!checkoutUrl) {
      throw new Error("Checkout URL is missing.");
    }
    ensureCheckoutOriginPreconnect(checkoutUrl);
    ensureCheckoutUrlPrefetch(checkoutUrl);
    return {
      checkoutUrl,
      sessionId: cleanText(data && data.sessionId) || null,
    };
  };

  const markPreparedCheckoutConsumed = (preparedCheckoutId) => {
    const cleanedId = cleanText(preparedCheckoutId);
    if (!cleanedId) return;
    try {
      void fetch(
        config.apiBaseUrl + "/public/checkout/prepare/" + encodeURIComponent(cleanedId) + "/consume",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          keepalive: true,
        },
      ).catch((error) => {
        console.error("[HtmlDeployPage] Failed to mark prepared checkout consumed.", error);
      });
    } catch (error) {
      console.error("[HtmlDeployPage] Failed to mark prepared checkout consumed.", error);
    }
  };

  const resolveVariantForCheckout = (checkout, selectionFromDom, variants) => {
    const resolver = checkout && checkout.variantResolver;
    if (!resolver || typeof resolver.type !== "string") {
      throw new Error("Checkout binding is missing a variantResolver.");
    }
    if (resolver.type === "fixed") {
      const variantId = cleanText(resolver.variantId);
      const variant = variants.find((candidate) => candidate.id === variantId) || null;
      return {
        variantId,
        variant,
        selection: selectionFromDom || (variant && variant.optionValues ? variant.optionValues : null),
      };
    }
    if (resolver.type === "option_values") {
      return {
        variantId: null,
        variant: variants.find((candidate) => selectionsMatch(candidate.optionValues, selectionFromDom)) || null,
        selection: selectionFromDom,
      };
    }
    throw new Error("Unsupported checkout resolver type.");
  };

  const resolveCheckoutBindingState = async (binding) => {
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    const selectionFromDom = augmentSelectionWithCheckoutContext(
      readSelectionFromResolver(binding.checkout.variantResolver, bindingId),
    );
    const checkoutVariants =
      selectionFromDom && !cachedVariants.length ? await loadCommerceVariants() : cachedVariants;
    const { variantId, variant, selection } = resolveVariantForCheckout(
      binding.checkout,
      selectionFromDom,
      checkoutVariants,
    );
    const resolvedVariantId = cleanText(variant && variant.id ? variant.id : variantId);
    const resolvedSelection = normalizeSelection(selection) || {};
    const cacheKey = buildPreparedCheckoutCacheKey(resolvedVariantId, resolvedSelection);
    if (cacheKey && !preparedCheckoutTransitionIds[cacheKey]) {
      preparedCheckoutTransitionIds[cacheKey] = buildCanonicalEventId("checkout_transition");
    }
    return {
      variant,
      resolvedVariantId,
      resolvedSelection,
      ctaId: bindingId,
      cacheKey,
      transitionId: cacheKey ? preparedCheckoutTransitionIds[cacheKey] : buildCanonicalEventId("checkout_transition"),
    };
  };

  const finalizePreparedCheckoutRecord = ({
    cacheKey,
    preparedCheckout,
    resolvedVariantId,
    resolvedSelection,
  }) => {
    const checkoutUrl = cleanText(preparedCheckout && preparedCheckout.checkoutUrl);
    if (!checkoutUrl) {
      throw new Error("Prepared checkout is missing checkoutUrl.");
    }
    const record = {
      preparedCheckoutId: cleanText(preparedCheckout.preparedCheckoutId) || "",
      checkoutUrl,
      sessionId: cleanText(preparedCheckout.sessionId) || null,
      variantId: resolvedVariantId || "",
      selection: resolvedSelection,
      createdAt: Date.now(),
    };
    ensureCheckoutOriginPreconnect(record.checkoutUrl);
    ensureCheckoutUrlPrefetch(record.checkoutUrl);
    preparedCheckoutCache[cacheKey] = record;
    return record;
  };

  const waitForPreparedCheckoutStatus = async (preparedCheckoutId, initialPollAfterMs) => {
    const deadline = Date.now() + PREPARED_CHECKOUT_POLL_TIMEOUT_MS;
    let pollAfterMs = initialPollAfterMs || PREPARED_CHECKOUT_POLL_INTERVAL_MS;
    while (Date.now() < deadline) {
      await delay(pollAfterMs);
      const preparedCheckout = await requestPreparedCheckoutStatus(preparedCheckoutId);
      if (preparedCheckout.status === "ready") {
        return preparedCheckout;
      }
      if (preparedCheckout.status === "failed") {
        throw new Error(preparedCheckout.error || "Prepared checkout failed.");
      }
      if (preparedCheckout.status === "expired") {
        throw new Error("Prepared checkout expired before it was used.");
      }
      pollAfterMs = preparedCheckout.pollAfterMs || PREPARED_CHECKOUT_POLL_INTERVAL_MS;
    }
    throw new Error("Prepared checkout timed out.");
  };

  const prepareCheckoutInBackground = async ({
    variant,
    resolvedVariantId,
    resolvedSelection,
    cacheKey,
    ctaId,
    transitionId,
  }) => {
    if (!cacheKey || !variant || variant.provider !== "shopify") {
      return null;
    }
    const cachedRecord = getPreparedCheckoutRecord(cacheKey);
    if (cachedRecord) {
      return cachedRecord;
    }
    if (preparedCheckoutInFlight[cacheKey]) {
      return preparedCheckoutInFlight[cacheKey];
    }
    const promise = (async () => {
      try {
        let preparedCheckout = await requestPreparedCheckout({
          resolvedVariantId,
          resolvedSelection,
          ctaId,
          transitionId,
        });
        if (preparedCheckout.status === "pending") {
          preparedCheckout = await waitForPreparedCheckoutStatus(
            preparedCheckout.preparedCheckoutId,
            preparedCheckout.pollAfterMs,
          );
        }
        if (preparedCheckout.status !== "ready") {
          throw new Error(preparedCheckout.error || "Prepared checkout is unavailable.");
        }
        return finalizePreparedCheckoutRecord({
          cacheKey,
          preparedCheckout,
          resolvedVariantId,
          resolvedSelection,
        });
      } catch (error) {
        console.error("[HtmlDeployPage] Failed to prepare checkout in background.", error);
        return null;
      }
    })()
      .finally(() => {
        delete preparedCheckoutInFlight[cacheKey];
      });
    preparedCheckoutInFlight[cacheKey] = promise;
    return promise;
  };

  const waitForPreparedCheckout = async (cacheKey) => {
    if (!cacheKey || !preparedCheckoutInFlight[cacheKey]) {
      return null;
    }
    return preparedCheckoutInFlight[cacheKey];
  };

  const syncCheckoutBindingWarmState = async (binding) => {
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    const checkoutState = await resolveCheckoutBindingState(binding);
    const isWarmable =
      Boolean(checkoutState.cacheKey) &&
      Boolean(checkoutState.variant) &&
      checkoutState.variant.provider === "shopify";

    if (!isWarmable) {
      setCheckoutBindingState(bindingId, {
        status: "idle",
        cacheKey: checkoutState.cacheKey || null,
        message: null,
      });
      return checkoutState;
    }

    const preparedCheckout = getPreparedCheckoutRecord(checkoutState.cacheKey);
    if (preparedCheckout) {
      setCheckoutBindingState(bindingId, {
        status: "ready",
        cacheKey: checkoutState.cacheKey,
        message: null,
      });
      return checkoutState;
    }

    setCheckoutBindingState(bindingId, {
      status: "loading",
      cacheKey: checkoutState.cacheKey,
      message: CHECKOUT_LOADING_LABEL,
    });

    void prepareCheckoutInBackground(checkoutState).then(() => {
      const currentState = checkoutBindingState[bindingId];
      if (!currentState || currentState.cacheKey !== checkoutState.cacheKey) {
        return;
      }
      if (getPreparedCheckoutRecord(checkoutState.cacheKey)) {
        setCheckoutBindingState(bindingId, {
          status: "ready",
          cacheKey: checkoutState.cacheKey,
          message: null,
        });
        return;
      }
      setCheckoutBindingState(bindingId, {
        status: "error",
        cacheKey: checkoutState.cacheKey,
        message: CHECKOUT_ERROR_LABEL,
      });
    });

    return checkoutState;
  };

  const ensurePreparedCheckoutForClick = async ({
    bindingId,
    cacheKey,
    variant,
    resolvedVariantId,
    resolvedSelection,
    transitionId,
  }) => {
    const isWarmableShopifyCheckout = Boolean(cacheKey) && Boolean(variant) && variant.provider === "shopify";
    if (!isWarmableShopifyCheckout) {
      return requestCheckout({ resolvedVariantId, resolvedSelection, ctaId: bindingId, transitionId });
    }
    let preparedCheckout = getPreparedCheckoutRecord(cacheKey);
    if (preparedCheckout) {
      markPreparedCheckoutConsumed(preparedCheckout.preparedCheckoutId);
      return {
        checkoutUrl: preparedCheckout.checkoutUrl,
        sessionId: preparedCheckout.sessionId || null,
      };
    }
    setCheckoutBindingState(bindingId, {
      status: "loading",
      cacheKey,
      message: CHECKOUT_LOADING_LABEL,
    });
    preparedCheckout =
      (await waitForPreparedCheckout(cacheKey)) ||
      (await prepareCheckoutInBackground({
        variant,
        resolvedVariantId,
        resolvedSelection,
        cacheKey,
        ctaId: bindingId,
        transitionId,
      }));
    if (!preparedCheckout) {
      setCheckoutBindingState(bindingId, {
        status: "error",
        cacheKey,
        message: CHECKOUT_ERROR_LABEL,
      });
      throw new Error("Prepared checkout is unavailable.");
    }
    markPreparedCheckoutConsumed(preparedCheckout.preparedCheckoutId);
    setCheckoutBindingState(bindingId, {
      status: "ready",
      cacheKey,
      message: null,
    });
    return {
      checkoutUrl: preparedCheckout.checkoutUrl,
      sessionId: preparedCheckout.sessionId || null,
    };
  };

  const isCheckoutBindingTarget = (target) => {
    if (!(target instanceof Node)) {
      return false;
    }
    return Object.values(checkoutBindingElements).some((elements) =>
      Array.isArray(elements) && elements.some((element) => element instanceof HTMLElement && element.contains(target)),
    );
  };

  const readNodeValue = (node, source) => {
    if (!node) return "";
    if (source === "text") {
      return normalizeText(node.textContent || "");
    }
    if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement) {
      return normalizeText(node.value || "");
    }
    return normalizeText(node.textContent || "");
  };

  const readSelectionFromResolver = (resolver, bindingId) => {
    if (!resolver || resolver.type !== "option_values") return null;
    const selection = {};
    const optionSelectors = Array.isArray(resolver.optionSelectors) ? resolver.optionSelectors : [];
    for (const option of optionSelectors) {
      const selector = cleanText(option && option.selector);
      const optionName = cleanText(option && option.name);
      const source = option && option.source === "text" ? "text" : "value";
      if (!selector || !optionName) {
        throw new Error("Checkout binding '" + bindingId + "' has an invalid option selector.");
      }
      const matches = Array.from(document.querySelectorAll(selector));
      if (matches.length !== 1) {
        throw new Error(
          "Checkout binding '" +
            bindingId +
            "' option selector '" +
            selector +
            "' matched " +
            String(matches.length) +
            " elements.",
        );
      }
      const value = readNodeValue(matches[0], source);
      if (!value) {
        throw new Error(
          "Checkout binding '" + bindingId + "' could not resolve a non-empty option value for '" + optionName + "'.",
        );
      }
      selection[optionName] = value;
    }
    return selection;
  };

  const findSmallestElementContainingText = (text) => {
    const target = cleanText(text);
    if (!target || !document.body) return null;

    let match = null;
    let matchLength = Number.POSITIVE_INFINITY;
    const elements = Array.from(document.body.querySelectorAll("*"));
    for (const element of elements) {
      const content = normalizeText(element.textContent || "");
      if (!content || !content.includes(target)) continue;
      if (content.length < matchLength) {
        match = element;
        matchLength = content.length;
      }
    }
    return match;
  };

  const applyMobileSpacingFixes = () => {
    if (window.innerWidth >= 768 || !document.body) return;

    const loadMoreComments = findSmallestElementContainingText("Load more comments...");
    const healthDisclaimer = findSmallestElementContainingText("HEALTH DISCLAIMER:");
    if (loadMoreComments && healthDisclaimer) {
      healthDisclaimer.style.marginTop = "1rem";
      healthDisclaimer.style.paddingBottom = "1rem";
      healthDisclaimer.style.color = "rgba(45, 41, 38, 0.4)";
      healthDisclaimer.style.opacity = "1";

      const copyright = findSmallestElementContainingText("All Rights Reserved.");
      if (copyright) {
        copyright.style.marginBottom = "1.25rem";
        copyright.style.color = "rgba(45, 41, 38, 0.35)";
        copyright.style.opacity = "1";
      }
    }

    const footer = document.querySelector("footer");
    const newsletterHeading = findSmallestElementContainingText("Join 14,000+ Women");
    const footerFinePrint = findSmallestElementContainingText("These statements have not been evaluated");
    if (footer && newsletterHeading && footerFinePrint) {
      footer.style.paddingTop = "2.5rem";
      footer.style.paddingBottom = "2rem";

      const newsletterBlock = newsletterHeading.parentElement;
      if (newsletterBlock) {
        newsletterBlock.style.marginBottom = "2.5rem";
      }

      footerFinePrint.style.marginTop = "1.5rem";
      footerFinePrint.style.color = "#6b7280";
      footerFinePrint.style.opacity = "1";
    }
  };

  const EMAIL_CAPTURE_LOADING_LABEL = "Saving your email...";
  const EMAIL_CAPTURE_SUCCESS_LABEL = "You're subscribed.";
  const EMAIL_CAPTURE_ERROR_LABEL = "We couldn't save your email. Please try again.";
  const KLAVIYO_CLIENT_SUBSCRIPTION_ENDPOINT = "https://a.klaviyo.com/client/subscriptions";

  const isLikelyEmailAddress = (value) => {
    const text = String(value || "");
    if (!text) return false;
    for (let index = 0; index < text.length; index += 1) {
      const code = text.charCodeAt(index);
      if (code <= 32 || code === 127) return false;
    }
    const parts = text.split("@");
    if (parts.length !== 2) return false;
    const local = parts[0];
    const domain = parts[1];
    return Boolean(local && domain && domain.includes(".") && !domain.startsWith(".") && !domain.endsWith("."));
  };
  const isPrivateKlaviyoApiKey = (value) => cleanText(value).toLowerCase().startsWith("pk_");

  const ensureEmailCaptureStatusNote = (bindingId, element) => {
    const existingId = cleanText(element.dataset.mosEmailCaptureStatusNoteId);
    if (existingId) {
      const existing = document.getElementById(existingId);
      if (existing) return existing;
    }
    const noteId =
      "mos-email-capture-status-" +
      String(bindingId || "unknown") +
      "-" +
      String(Date.now()) +
      "-" +
      String(Math.floor(Math.random() * 100000));
    const note = document.createElement("p");
    note.id = noteId;
    note.style.display = "none";
    note.style.width = "100%";
    note.style.margin = "0.65rem 0 0";
    note.style.fontSize = "0.875rem";
    note.style.lineHeight = "1.35";
    note.style.fontWeight = "600";
    note.style.letterSpacing = "normal";
    note.style.textTransform = "none";
    note.style.color = "inherit";
    note.setAttribute("aria-live", "polite");
    element.insertAdjacentElement("afterend", note);
    element.dataset.mosEmailCaptureStatusNoteId = noteId;
    return note;
  };

  const setEmailCaptureStatus = (bindingId, element, status, message) => {
    const note = ensureEmailCaptureStatusNote(bindingId, element);
    const cleanedMessage = cleanText(message);
    if (!status || !cleanedMessage) {
      note.textContent = "";
      note.style.display = "none";
      note.removeAttribute("role");
      return;
    }
    note.textContent = cleanedMessage;
    note.style.display = "block";
    note.style.color = status === "error" ? "#b42318" : status === "success" ? "#047857" : "inherit";
    note.setAttribute("role", status === "error" ? "alert" : "status");
  };

  const setEmailCaptureSubmitting = (element, busy) => {
    if (!(element instanceof HTMLElement)) return;
    const controls = Array.from(
      element.querySelectorAll("button[type='submit'], button:not([type]), input[type='submit']"),
    );
    element.setAttribute("aria-busy", busy ? "true" : "false");
    controls.forEach((control) => {
      if (!(control instanceof HTMLElement)) return;
      if (busy) {
        if (!("mosEmailCaptureSavedDisabled" in control.dataset)) {
          const disabled =
            control instanceof HTMLButtonElement || control instanceof HTMLInputElement
              ? control.disabled
              : control.getAttribute("aria-disabled") === "true";
          control.dataset.mosEmailCaptureSavedDisabled = disabled ? "true" : "false";
        }
        control.setAttribute("aria-disabled", "true");
        control.setAttribute("aria-busy", "true");
        if (control instanceof HTMLButtonElement || control instanceof HTMLInputElement) {
          control.disabled = true;
        }
        return;
      }
      const wasDisabled = control.dataset.mosEmailCaptureSavedDisabled === "true";
      control.removeAttribute("aria-busy");
      if (wasDisabled) {
        control.setAttribute("aria-disabled", "true");
      } else {
        control.removeAttribute("aria-disabled");
      }
      if (control instanceof HTMLButtonElement || control instanceof HTMLInputElement) {
        control.disabled = wasDisabled;
      }
      delete control.dataset.mosEmailCaptureSavedDisabled;
    });
    if (!busy) {
      element.removeAttribute("aria-busy");
    }
  };

  const queryEmailCaptureElement = (rootElement, selector, label) => {
    const cleanedSelector = cleanText(selector);
    if (!cleanedSelector) {
      throw new Error(label + " selector is missing.");
    }
    try {
      if (rootElement && typeof rootElement.querySelector === "function") {
        const scopedMatch = rootElement.querySelector(cleanedSelector);
        if (scopedMatch) return scopedMatch;
      }
      return document.querySelector(cleanedSelector);
    } catch (_) {
      throw new Error(label + " selector '" + cleanedSelector + "' is invalid.");
    }
  };

  const readEmailCaptureElementValue = (element, source) => {
    if (
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement ||
      element instanceof HTMLSelectElement
    ) {
      return cleanText(element.value);
    }
    if (source === "text") {
      return cleanText(element.textContent || "");
    }
    return cleanText(element.getAttribute("value")) || cleanText(element.textContent || "");
  };

  const readEmailCaptureEmail = (binding, element) => {
    const emailCapture = binding && binding.emailCapture;
    if (!emailCapture || emailCapture.provider !== "klaviyo") {
      throw new Error("Email capture binding '" + String(binding && binding.id ? binding.id : "unknown") + "' is missing Klaviyo configuration.");
    }
    const emailElement = queryEmailCaptureElement(element, emailCapture.emailSelector, "Email capture email");
    const email = readEmailCaptureElementValue(emailElement, "value");
    if (!email || !isLikelyEmailAddress(email)) {
      throw new Error("Please enter a valid email address.");
    }
    return email.toLowerCase();
  };

  const readEmailCaptureProfileProperties = (binding, element) => {
    const emailCapture = binding && binding.emailCapture;
    const fields = Array.isArray(emailCapture && emailCapture.profileFields) ? emailCapture.profileFields : [];
    const properties = {};
    fields.forEach((field) => {
      const name = cleanText(field && field.name);
      const selector = cleanText(field && field.selector);
      if (!name || !selector) return;
      const fieldElement = queryEmailCaptureElement(element, selector, "Email capture profile field '" + name + "'");
      const value = readEmailCaptureElementValue(fieldElement, field.source === "text" ? "text" : "value");
      if (value) {
        properties[name] = value;
      }
    });
    return properties;
  };

  const buildKlaviyoSubscriptionPayload = (binding, element, email) => {
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    const emailCapture = binding && binding.emailCapture;
    if (!emailCapture || emailCapture.provider !== "klaviyo") {
      throw new Error("Email capture binding '" + bindingId + "' is missing Klaviyo configuration.");
    }
    const source = cleanText(emailCapture.source);
    if (!source) {
      throw new Error("Email capture binding '" + bindingId + "' is missing a Klaviyo source.");
    }
    const profileProperties = {
      source,
      capture_source: source,
      product_slug: cleanText(config.productSlug),
      funnel_slug: cleanText(config.funnelSlug),
      page_slug: cleanText(config.pageSlug),
      page_stage: cleanText(config.pageStage),
      page_id: cleanText(config.pageId),
      publication_id: cleanText(config.publicationId),
      visitor_id: cleanText(config.visitorId),
      session_id: cleanText(config.sessionId),
      binding_id: bindingId,
      url: window.location.href,
      utm: getUtmParams(),
      ...readEmailCaptureProfileProperties(binding, element),
    };
    const payload = {
      data: {
        type: "subscription",
        attributes: {
          custom_source: source,
          profile: {
            data: {
              type: "profile",
              attributes: {
                email,
                properties: profileProperties,
                subscriptions: {
                  email: {
                    marketing: {
                      consent: "SUBSCRIBED",
                    },
                  },
                },
              },
            },
          },
        },
      },
    };
    const listId = cleanText(emailCapture.klaviyo && emailCapture.klaviyo.listId);
    if (listId) {
      payload.data.relationships = {
        list: {
          data: {
            type: "list",
            id: listId,
          },
        },
      };
    }
    return payload;
  };

  const requestKlaviyoEmailSubscription = async (binding, element, email) => {
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    const emailCapture = binding && binding.emailCapture;
    const klaviyo = emailCapture && emailCapture.klaviyo;
    const publicApiKey = cleanText(klaviyo && klaviyo.publicApiKey);
    if (!publicApiKey) {
      throw new Error("Email capture binding '" + bindingId + "' is missing the Klaviyo public API key.");
    }
    if (isPrivateKlaviyoApiKey(publicApiKey)) {
      throw new Error("Email capture binding '" + bindingId + "' must use the Klaviyo public Site ID, not a private API key.");
    }
    const revision = cleanText(klaviyo && klaviyo.revision);
    if (!revision) {
      throw new Error("Email capture binding '" + bindingId + "' is missing the Klaviyo API revision.");
    }
    const url = new URL(KLAVIYO_CLIENT_SUBSCRIPTION_ENDPOINT);
    url.searchParams.set("company_id", publicApiKey);
    const response = await fetch(url.toString(), {
      method: "POST",
      headers: {
        Accept: "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        revision,
      },
      body: JSON.stringify(buildKlaviyoSubscriptionPayload(binding, element, email)),
    });
    if (!response.ok) {
      throw new Error(await parseResponseError(response));
    }
  };

  const loadKlaviyoOnsiteScript = (publicApiKey) => {
    const key = cleanText(publicApiKey);
    if (!key) return;
    if (isPrivateKlaviyoApiKey(key)) return;
    if (!window.klaviyo) {
      window.klaviyo = [];
    }
    const scriptId = "mos-klaviyo-onsite-" + key.replace(/[^A-Za-z0-9_-]/g, "-");
    if (document.getElementById(scriptId)) return;
    const script = document.createElement("script");
    script.id = scriptId;
    script.async = true;
    script.type = "text/javascript";
    script.src = "https://static.klaviyo.com/onsite/js/" + encodeURIComponent(key) + "/klaviyo.js";
    (document.body || document.head || document.documentElement).appendChild(script);
  };

  const loadKlaviyoOnsiteScriptForBinding = (binding) => {
    const key =
      binding &&
      binding.emailCapture &&
      binding.emailCapture.klaviyo &&
      binding.emailCapture.klaviyo.publicApiKey;
    loadKlaviyoOnsiteScript(key);
  };

  const sendKlaviyoBrowserSignals = (binding, email) => {
    const source = cleanText(binding && binding.emailCapture && binding.emailCapture.source);
    const props = {
      email,
      source,
      capture_source: source,
      product_slug: cleanText(config.productSlug),
      funnel_slug: cleanText(config.funnelSlug),
      page_slug: cleanText(config.pageSlug),
      page_stage: cleanText(config.pageStage),
      binding_id: String(binding && binding.id ? binding.id : "unknown"),
    };
    try {
      const klaviyo = window.klaviyo;
      if (Array.isArray(klaviyo)) {
        klaviyo.push(["identify", { email }]);
        klaviyo.push(["track", "Email Capture Submitted", props]);
        return;
      }
      if (klaviyo && typeof klaviyo.identify === "function") {
        klaviyo.identify({ email });
      }
      if (klaviyo && typeof klaviyo.track === "function") {
        klaviyo.track("Email Capture Submitted", props);
      }
    } catch (error) {
      console.error("[HtmlDeployPage] Klaviyo browser signal failed.", error);
    }
  };

  const sha256Hex = async (value) => {
    if (!window.crypto || !window.crypto.subtle || typeof TextEncoder === "undefined") {
      throw new Error("Browser SHA-256 hashing is unavailable.");
    }
    const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  };

  const persistMetaEmailHash = async (email) => {
    const normalizedEmail = cleanText(email) ? String(email).trim().toLowerCase() : null;
    if (!normalizedEmail) return null;
    let emailHash = null;
    try {
      emailHash = await sha256Hex(normalizedEmail);
      window.localStorage.setItem(META_EMAIL_HASH_STORAGE_KEY, emailHash);
    } catch (error) {
      console.error("[HtmlDeployPage] Failed to persist Meta email hash.", error);
    }
    return emailHash;
  };

  const identifyPostHogEmailCapture = (binding, email, emailHash) => {
    const normalizedEmail = cleanText(email) ? String(email).trim().toLowerCase() : null;
    if (!normalizedEmail) return;
    const posthog = ensurePostHogInstance();
    if (!posthog || typeof posthog.identify !== "function") return;
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    const source = cleanText(binding && binding.emailCapture && binding.emailCapture.source);
    const personProps = {
      email: normalizedEmail,
      capture_source: source,
      product_slug: cleanText(config.productSlug),
      funnel_slug: cleanText(config.funnelSlug),
      page_slug: cleanText(config.pageSlug),
      page_stage: cleanText(config.pageStage),
      page_id: cleanText(config.pageId),
      publication_id: cleanText(config.publicationId),
      visitor_id: cleanText(config.visitorId),
      session_id: cleanText(config.sessionId),
      binding_id: bindingId,
      external_id: resolveMetaExternalId(),
    };
    assignCleanProp(personProps, "em", emailHash);
    assignCleanProp(personProps, "email_sha256", emailHash);
    posthog.identify(normalizedEmail, personProps);
  };

  const completeEmailCaptureSuccess = (binding, element) => {
    const emailCapture = binding && binding.emailCapture;
    if (
      element instanceof HTMLFormElement &&
      emailCapture &&
      emailCapture.successBehavior === "redispatch_submit"
    ) {
      element.dataset.mosEmailCaptureSucceeded = "true";
      element.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      if (element.dataset.mosEmailCaptureSucceeded === "true") {
        delete element.dataset.mosEmailCaptureSucceeded;
      }
      return;
    }
    setEmailCaptureStatus(
      String(binding && binding.id ? binding.id : "unknown"),
      element,
      "success",
      cleanText(emailCapture && emailCapture.successMessage) || EMAIL_CAPTURE_SUCCESS_LABEL,
    );
  };

  const handleEmailCaptureSubmit = async (binding, element, event) => {
    const bindingId = String(binding && binding.id ? binding.id : "unknown");
    if (event && event.__mosEmailCaptureBypass === true) {
      return;
    }
    if (element.dataset.mosEmailCaptureSucceeded === "true") {
      if (event) {
        event.__mosEmailCaptureBypass = true;
      }
      delete element.dataset.mosEmailCaptureSucceeded;
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === "function") {
      event.stopImmediatePropagation();
    }
    if (element instanceof HTMLFormElement && typeof element.reportValidity === "function" && !element.reportValidity()) {
      return;
    }

    const emailCapture = binding && binding.emailCapture;
    const source = cleanText(emailCapture && emailCapture.source) || bindingId;
    try {
      const email = readEmailCaptureEmail(binding, element);
      setEmailCaptureSubmitting(element, true);
      setEmailCaptureStatus(bindingId, element, "loading", EMAIL_CAPTURE_LOADING_LABEL);
      trackEvent(binding.trackEventType || "email_capture_submit", {
        bindingId,
        source,
        provider: "klaviyo",
      });
      await requestKlaviyoEmailSubscription(binding, element, email);
      const emailHash = await persistMetaEmailHash(email);
      identifyPostHogEmailCapture(binding, email, emailHash);
      sendKlaviyoBrowserSignals(binding, email);
      trackEvent("email_capture_success", {
        bindingId,
        source,
        provider: "klaviyo",
      });
      completeEmailCaptureSuccess(binding, element);
    } catch (error) {
      console.error("[HtmlDeployPage] Email capture binding '" + bindingId + "' failed.", error);
      trackEvent("email_capture_failed", {
        bindingId,
        source,
        provider: "klaviyo",
        errorMessage: cleanText(error && error.message) || "Email capture failed.",
      });
      setEmailCaptureStatus(
        bindingId,
        element,
        "error",
        cleanText(emailCapture && emailCapture.errorMessage) || EMAIL_CAPTURE_ERROR_LABEL,
      );
    } finally {
      setEmailCaptureSubmitting(element, false);
    }
  };

  const emailCaptureFormBindings = [];
  let emailCaptureDocumentSubmitListenerBound = false;

  const registerEmailCaptureSubmitBinding = (binding, element) => {
    emailCaptureFormBindings.push({ binding, element });
    if (!emailCaptureDocumentSubmitListenerBound) {
      emailCaptureDocumentSubmitListenerBound = true;
      document.addEventListener("submit", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLFormElement)) return;
        const match = emailCaptureFormBindings.find((entry) => entry && entry.element === target);
        if (!match) return;
        void handleEmailCaptureSubmit(match.binding, match.element, event);
      }, true);
    }
    element.addEventListener("submit", (event) => {
      void handleEmailCaptureSubmit(binding, element, event);
    }, true);
  };

  const bindManifest = () => {
    if (!config.manifest || !Array.isArray(config.manifest.bindings)) return;

    for (const binding of config.manifest.bindings) {
      if (!binding || typeof binding !== "object") continue;
      const selector = cleanText(binding.selector);
      if (!selector) continue;

      const matches = Array.from(document.querySelectorAll(selector));
      if (matches.length < 1) {
        console.error(
          "[HtmlDeployPage] Binding '" +
            String(binding.id || "unknown") +
            "' selector '" +
            selector +
            "' matched no elements.",
        );
        continue;
      }

      for (const [matchIndex, element] of matches.entries()) {
        if (!(element instanceof HTMLElement)) {
          continue;
        }
        if (element.__mosStandaloneImportedHtmlBound === true) {
          continue;
        }
        element.__mosStandaloneImportedHtmlBound = true;
        if (binding.type === "checkout" && binding.checkout) {
          registerCheckoutElement(String(binding.id || "unknown"), element);
        }
        if (binding.type === "internal_navigation" && element instanceof HTMLAnchorElement) {
          const targetPath = config.pagePathById[String(binding.targetPageId || "")];
          const targetStage = cleanText(config.pageStageById && config.pageStageById[String(binding.targetPageId || "")]);
          if (targetPath) {
            element.href = buildInternalNavigationUrl(targetPath, {
              fromStage: config.pageStage,
              toStage: targetStage || "custom",
              sessionId: resolveCanonicalSessionId(),
              anonymousId: resolveCanonicalAnonymousId(),
            });
          }
        }
        element.dataset.mosStandaloneImportedHtmlBound = "true";
        if (binding.type === "email_capture") {
          if (!(element instanceof HTMLFormElement)) {
            console.error(
              "[HtmlDeployPage] Email capture binding '" +
                String(binding.id || "unknown") +
                "' must target a form element.",
            );
            continue;
          }
          loadKlaviyoOnsiteScriptForBinding(binding);
          registerEmailCaptureSubmitBinding(binding, element);
          continue;
        }
        const handleBindingClick = async (event) => {
          if (event.__mosStandaloneImportedHtmlBindingHandled === true) {
            return;
          }
          event.__mosStandaloneImportedHtmlBindingHandled = true;
          const modifiedClick =
            event instanceof MouseEvent &&
            (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0);
          if (binding.type === "internal_navigation" && modifiedClick) {
            return;
          }
          event.preventDefault();
          event.stopPropagation();

          const buttonText = normalizeText(element.textContent || "");
          try {
            if (binding.type === "internal_navigation") {
              const targetPath = config.pagePathById[String(binding.targetPageId || "")];
              const targetStage = cleanText(config.pageStageById && config.pageStageById[String(binding.targetPageId || "")]);
              if (!targetPath) {
                throw new Error("Target page path is missing for binding '" + String(binding.id || "unknown") + "'.");
              }
              const ctaPosition = matchIndex + 1;
              const isPresaleSalesClick = isPresaleToSalesNavigation(config.pageStage, targetStage || "custom");
              const bridgeClickId = isPresaleSalesClick ? buildBridgeClickId(binding.id, ctaPosition) : null;
              const sourcePageType = isPresaleSalesClick ? resolvePresalesSourcePageType() : null;
              const destinationUrl = buildInternalNavigationUrl(targetPath, {
                fromStage: config.pageStage,
                toStage: targetStage || "custom",
                sessionId: resolveCanonicalSessionId(),
                anonymousId: resolveCanonicalAnonymousId(),
                clickId: bridgeClickId,
                sourcePageType,
              });
              trackEvent(binding.trackEventType || "custom_page_click", {
                fromStage: config.pageStage,
                from_stage: config.pageStage,
                toStage: targetStage || "custom",
                to_stage: targetStage || "custom",
                ...(sourcePageType ? { sourcePageType, source_page_type: sourcePageType } : {}),
                sourcePage: config.pageSlug,
                source_page: config.pageSlug,
                sessionId: resolveCanonicalSessionId(),
                session_id: resolveCanonicalSessionId(),
                visitorId: resolveCanonicalAnonymousId(),
                visitor_id: resolveCanonicalAnonymousId(),
                anonymous_id: resolveCanonicalAnonymousId(),
                targetPageId: binding.targetPageId,
                target_page_id: binding.targetPageId,
                bindingId: binding.id,
                binding_id: binding.id,
                ctaId: binding.id,
                cta_id: binding.id,
                ctaPosition,
                cta_position: ctaPosition,
                ctaText: buttonText || undefined,
                cta_text: buttonText || undefined,
                buttonText: buttonText || undefined,
                destinationUrl,
                destination_url: destinationUrl,
                ...(bridgeClickId
                  ? {
                      clickId: bridgeClickId,
                      click_id: bridgeClickId,
                      clickIdType: RMBC_CLICK_PARAM,
                      click_id_type: RMBC_CLICK_PARAM,
                      rmbcClickId: bridgeClickId,
                      rmbc_click_id: bridgeClickId,
                    }
                  : {}),
              });
              if (isPresaleSalesClick) {
                markPresaleAttribution();
              }
              await waitForTrackingNavigationFlush();
              window.location.href = destinationUrl;
              return;
            }

            if (binding.type === "track_only") {
              const ctaPosition = matchIndex + 1;
              trackEvent(binding.trackEventType || "custom_page_click", {
                fromStage: config.pageStage,
                pageId: config.pageId,
                buttonText: buttonText || undefined,
                bindingId: binding.id,
                ctaId: binding.id,
                cta_id: binding.id,
                ctaPosition,
                cta_position: ctaPosition,
                ctaText: buttonText || undefined,
                cta_text: buttonText || undefined,
              });
              return;
            }

            if (binding.type !== "checkout" || !binding.checkout) {
              throw new Error("Unsupported binding type.");
            }

            const bindingId = String(binding.id || "unknown");
            setCheckoutBindingState(bindingId, {
              status: "loading",
              cacheKey: null,
              message: CHECKOUT_CLICK_LOADING_LABEL,
            });
            const {
              variant,
              resolvedVariantId,
              resolvedSelection,
              cacheKey,
              transitionId: resolvedTransitionId,
            } = await syncCheckoutBindingWarmState(binding);
            const transitionId = cleanText(resolvedTransitionId) || buildCanonicalEventId("checkout_transition");
            const checkoutEventProps = {
              fromStage: config.pageStage,
              from_stage: config.pageStage,
              toStage: "checkout",
              to_stage: "checkout",
              bindingId,
              binding_id: bindingId,
              ctaId: bindingId,
              cta_id: bindingId,
              transitionId,
              transition_id: transitionId,
              buttonText: buttonText || undefined,
              button_text: buttonText || undefined,
              ...(resolvedVariantId ? { variantId: resolvedVariantId } : {}),
              ...(variant && typeof variant.price === "number" ? { value: Math.round(variant.price) / 100 } : {}),
              ...(variant && variant.currency ? { currency: variant.currency } : {}),
              ...checkoutTimingProps({
                transitionId,
                ctaId: bindingId,
                resolvedVariantId,
                resolvedSelection,
              }),
            };

            void trackEvent("checkout_click", checkoutEventProps);
            const checkoutTrackEventType =
              cleanText(window.__mosCheckoutTrackEventTypeOverride) ||
              binding.trackEventType ||
              "sales_to_checkout_click";
            if (cleanText(window.__mosCheckoutTrackEventTypeOverride)) {
              window.__mosCheckoutTrackEventTypeOverride = "";
            }
            void trackEvent(checkoutTrackEventType, checkoutEventProps);

            if (binding.checkout.mode === "external_checkout_url") {
              const checkoutUrl = resolveExternalCheckoutUrlForVariant(
                binding.checkout.externalUrlsByVariant || [],
                resolvedVariantId,
              );
              if (!checkoutUrl) {
                throw new Error("Missing external checkout URL for binding '" + String(binding.id || "unknown") + "'.");
              }
              const finalCheckoutUrl = appendCheckoutTrackingUrlParams(
                appendCheckoutAttributesToCartUrl(
                  checkoutUrl,
                  checkoutAttributeMap({
                    resolvedVariantId,
                    resolvedSelection,
                    ctaId: bindingId,
                    transitionId,
                  }),
                ),
              );
              checkoutHandoffContext = {
                ...checkoutEventProps,
                ...checkoutTimingProps({
                  transitionId,
                  ctaId: bindingId,
                  checkoutUrl: finalCheckoutUrl,
                  resolvedVariantId,
                  resolvedSelection,
                }),
              };
              checkoutPagehideTracked = false;
              checkoutVisibilityHiddenTracked = false;
              checkoutNavigationInProgress = true;
              trackCheckoutTimingEvent("checkout_redirect_started", checkoutHandoffContext);
              window.location.href = finalCheckoutUrl;
              return;
            }

            const checkout = await ensurePreparedCheckoutForClick({
              bindingId,
              cacheKey,
              variant,
              resolvedVariantId,
              resolvedSelection,
              transitionId,
            });

            if (variant && variant.provider === "stripe") {
              const pendingKey = pendingMetaPurchaseStorageKey(config.sessionId, config.funnelSlug);
              if (pendingKey) {
                writePendingMetaPurchase(pendingKey, {
                  funnelSlug: config.funnelSlug,
                  pageId: config.pageId,
                  variantId: variant.id,
                  value: typeof variant.price === "number" ? variant.price : null,
                  currency: variant.currency || null,
                  quantity: 1,
                  provider: variant.provider,
                });
              }
            }

            const finalCheckoutUrl = appendCheckoutTrackingUrlParams(checkout.checkoutUrl);
            checkoutHandoffContext = {
              ...checkoutEventProps,
              ...checkoutTimingProps({
                transitionId,
                ctaId: bindingId,
                checkoutUrl: finalCheckoutUrl,
                resolvedVariantId,
                resolvedSelection,
              }),
            };
            checkoutPagehideTracked = false;
            checkoutVisibilityHiddenTracked = false;
            checkoutNavigationInProgress = true;
            trackCheckoutTimingEvent("checkout_redirect_started", checkoutHandoffContext);
            window.location.href = finalCheckoutUrl;
          } catch (error) {
            console.error(
              "[HtmlDeployPage] Binding '" + String(binding.id || "unknown") + "' failed.",
              error,
            );
            setCheckoutBindingState(String(binding.id || "unknown"), {
              status: "error",
              cacheKey: null,
              message: CHECKOUT_ERROR_LABEL,
            });
          }
        };
        if (binding.type === "internal_navigation") {
          if (element.__mosStandaloneImportedHtmlClickOverrideBound !== true) {
            element.__mosStandaloneImportedHtmlClickOverrideBound = true;
            try {
              element.click = () => {
                const syntheticClick = new MouseEvent("click", {
                  bubbles: true,
                  cancelable: true,
                  view: window,
                });
                void handleBindingClick(syntheticClick);
              };
            } catch (_error) {}
          }
          document.addEventListener("click", (event) => {
            const target = event && event.target instanceof Element
              ? event.target.closest(selector)
              : null;
            if (!target) {
              return;
            }
            void handleBindingClick(event);
          }, { capture: true });
        }
        element.addEventListener("click", handleBindingClick);
      }
    }
  };

  const bindManifestSafely = () => {
    try {
      bindManifest();
    } catch (error) {
      console.error("[HtmlDeployPage] Failed to bind manifest.", error);
    }
  };

  const applyMobileSpacingFixesSafely = () => {
    try {
      applyMobileSpacingFixes();
    } catch (error) {
      console.error("[HtmlDeployPage] Failed to apply mobile spacing fixes.", error);
    }
  };

  const warmCheckoutBindings = async () => {
    if (!config.manifest || !Array.isArray(config.manifest.bindings)) return;
    await Promise.all(
      config.manifest.bindings.map(async (binding) => {
        if (!binding || typeof binding !== "object") return;
        if (binding.type !== "checkout" || !binding.checkout) return;
        if (binding.checkout.mode === "external_checkout_url") return;
        try {
          await syncCheckoutBindingWarmState(binding);
        } catch (_) {
          setCheckoutBindingState(String(binding.id || "unknown"), {
            status: "error",
            cacheKey: null,
            message: CHECKOUT_ERROR_LABEL,
          });
        }
      }),
    );
  };

  const warmCheckoutBindingsSafely = () => {
    try {
      void warmCheckoutBindings();
    } catch (error) {
      console.error("[HtmlDeployPage] Failed to warm checkout bindings.", error);
    }
  };

  const scheduleWarmCheckoutBindings = (delayMs = 75) => {
    if (warmCheckoutBindingsTimeout !== null) {
      window.clearTimeout(warmCheckoutBindingsTimeout);
    }
    warmCheckoutBindingsTimeout = window.setTimeout(() => {
      warmCheckoutBindingsTimeout = null;
      warmCheckoutBindingsSafely();
    }, delayMs);
  };

  const scheduleInitialWarmCheckoutBindings = () => {
    scheduleWarmCheckoutBindings(0);
    window.setTimeout(() => scheduleWarmCheckoutBindings(0), 250);
    window.setTimeout(() => scheduleWarmCheckoutBindings(0), 1000);
  };

  installTrackEventBridge();
  installCheckoutHandoffTracking();
  bindManifestSafely();
  applyMobileSpacingFixesSafely();
  scheduleInitialWarmCheckoutBindings();
  scheduleInitialPageView();
  initializeEngagementTrackingSafely();
  initializeViewTrackingSafely();
  initializeInteractionTrackingSafely();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindManifestSafely, { once: true });
    document.addEventListener("DOMContentLoaded", applyMobileSpacingFixesSafely, { once: true });
    document.addEventListener("DOMContentLoaded", initializeViewTrackingSafely, { once: true });
    document.addEventListener("DOMContentLoaded", initializeInteractionTrackingSafely, { once: true });
    document.addEventListener("DOMContentLoaded", scheduleInitialWarmCheckoutBindings, { once: true });
    document.addEventListener("DOMContentLoaded", scheduleInitialPageView, { once: true });
  }
  window.addEventListener("load", bindManifestSafely, { once: true });
  window.addEventListener("load", applyMobileSpacingFixesSafely, { once: true });
  window.addEventListener("load", initializeViewTrackingSafely, { once: true });
  window.addEventListener("load", initializeInteractionTrackingSafely, { once: true });
  window.addEventListener("load", scheduleInitialWarmCheckoutBindings, { once: true });
  window.addEventListener("load", scheduleInitialPageView, { once: true });
  window.setTimeout(bindManifestSafely, 0);
  window.setTimeout(bindManifestSafely, 250);
  window.setTimeout(bindManifestSafely, 1000);
  window.setTimeout(applyMobileSpacingFixesSafely, 0);
  window.setTimeout(applyMobileSpacingFixesSafely, 250);
  window.setTimeout(applyMobileSpacingFixesSafely, 1000);
  window.setTimeout(initializeViewTrackingSafely, 0);
  window.setTimeout(initializeViewTrackingSafely, 250);
  window.setTimeout(initializeViewTrackingSafely, 1000);
  window.setTimeout(initializeInteractionTrackingSafely, 0);
  window.setTimeout(initializeInteractionTrackingSafely, 250);
  window.setTimeout(initializeInteractionTrackingSafely, 1000);
  window.addEventListener("resize", applyMobileSpacingFixesSafely);
  document.addEventListener("input", () => scheduleWarmCheckoutBindings(), true);
  document.addEventListener("change", () => scheduleWarmCheckoutBindings(), true);
})();
</script>`;
}

function injectStandaloneRuntimeScript(
  htmlDocument: string,
  runtimeScript: string,
): string {
  if (/<\/body>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/body>/i, `${runtimeScript}</body>`);
  }
  if (/<\/html>/i.test(htmlDocument)) {
    return htmlDocument.replace(/<\/html>/i, `${runtimeScript}</html>`);
  }
  return `${htmlDocument}${runtimeScript}`;
}

export function StandaloneImportedHtmlPage(props: StandaloneImportedHtmlPageProps) {
  useEffect(() => {
    const normalizedHtml = optimizeImportedHtmlDocument(props.htmlDocument);
    if (!normalizedHtml) {
      throw new Error("HTML deploy page is empty.");
    }
    if (window.__mosImportedHtmlStandalonePageId === props.page.pageId) {
      return;
    }
    window.__mosImportedHtmlStandalonePageId = props.page.pageId;
    const runtimeScript = buildStandaloneImportedHtmlRuntimeScript(props);
    const nextDocument = injectStandaloneRuntimeScript(normalizedHtml, runtimeScript);
    document.open();
    document.write(nextDocument);
    document.close();
  }, [props]);

  return null;
}

export const HtmlDeployPage = StandaloneImportedHtmlPage;
