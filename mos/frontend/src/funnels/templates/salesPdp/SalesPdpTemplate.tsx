import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";
import { Container } from "./Container";
import { Marquee } from "./Marquee";
import { Modal } from "./Modal";
import type { ThemeConfig, UiCopy } from "./siteTypes";
import type {
  CalloutConfig,
  ColorOption,
  ComparisonConfig,
  FaqConfig,
  FooterConfig,
  GuaranteeConfig,
  HeaderConfig,
  HeroConfig,
  ImageAsset,
  ImportComparisonConfig,
  ImportGuaranteeConfig,
  ImportReviewWallConfig,
  ImportStoryRow,
  ImportStorySectionConfig,
  ImportVideoSectionConfig,
  MarqueeConfig,
  ModalsConfig,
  OfferOption,
  PdpConfig,
  ReviewWallConfig,
  SalesPdpSchemaVersion,
  SizeOption,
  StorySectionConfig,
  VideoItem,
  VideoSectionConfig,
} from "./types";
import defaults from "./defaults.json";
import styles from "./pdpPage.module.css";
import baseStyles from "./salesPdpTemplate.module.css";
import { useDesignSystemTokens } from "@/components/design-system/DesignSystemProvider";
import { resolveRuntimePagePath, useFunnelRuntime } from "@/funnels/funnelRuntime";
import { resolvePublicApiBaseUrl } from "@/funnels/runtimeRouting";
import {
  resolveDesignSystemBrandLogoVariant,
  withDesignSystemBrandLogo,
} from "@/funnels/templates/shared/designSystemBrandLogo";
import { useTemplateFonts } from "@/funnels/templates/templateFonts";
import { PaymentIconStrip } from "@/funnels/templates/shared/PaymentIconStrip";
import {
  appendCheckoutTrackingUrlParams,
  buildCheckoutTimingProps,
  buildCheckoutAttributionProps,
  buildCheckoutTransitionId,
} from "@/lib/checkoutAttribution";
import { checkoutClickEventForStage } from "@/lib/funnelTracking";
import { pendingMetaPurchaseStorageKey, writePendingMetaPurchase } from "@/lib/metaCheckout";

export const salesPdpDefaults = defaults as {
  config: PdpConfig;
  copy: UiCopy;
  theme?: ThemeConfig;
};

type Props = {
  id?: string;
  config?: PdpConfig;
  copy?: UiCopy;
  theme?: ThemeConfig;
  configJson?: string;
  copyJson?: string;
  themeJson?: string;
};

const apiBaseUrl = resolvePublicApiBaseUrl();
const MOBILE_BREAKPOINT_QUERY = "(max-width: 980px)";
const ORDER_NOW_SCROLL_TARGET_ID = "order-now";
const URGENCY_MONTH_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "long",
  timeZone: "UTC",
});

// Keep layout geometry consistent with the base template.
// Brand design systems can still change colors and font families.
const LOCKED_TEMPLATE_CSS_VARS = new Set([
  "--radius-sm",
  "--radius-md",
  "--radius-lg",
  "--container-max",
  "--container-pad",
  "--section-pad-y",
  "--section-pad-y-mobile",
  "--heading-line",
  "--heading-size",
  "--heading-size-mobile",
  "--heading-weight",
  "--hero-min-height",
  "--hero-pad-x",
  "--hero-pad-y",
  "--hero-title-max",
  "--hero-subtitle-max",
  "--hero-title-line",
  "--marquee-border",
  "--marquee-font-size",
  "--marquee-font-weight",
  "--marquee-gap",
  "--marquee-height",
  "--marquee-letter-spacing",
  "--marquee-pad-x",
  "--badge-strip-pad-y",
  "--badge-strip-gap",
  "--pitch-pad-y",
  "--pitch-gap",
  "--pitch-content-max",
  "--pitch-media-max",
  "--reviews-height",
  "--reviews-card-width",
  "--reviews-card-pad",
  "--wall-pad-y",
  "--wall-pad-top",
  "--wall-height",
  "--wall-gap",
  "--wall-pad-x",
  "--wall-fade-height",
  "--pdp-radius-5",
  "--pdp-radius-8",
  "--pdp-radius-12",
  "--pdp-radius-pill",
  "--pdp-urgency-bg",
  "--pdp-urgency-border",
  "--pdp-urgency-text",
  "--pdp-urgency-muted-bg",
  "--pdp-urgency-highlight-bg",
  "--pdp-urgency-highlight-text",
  "--pdp-urgency-muted-text",
  "--pdp-urgency-row-border",
  "--pdp-urgency-icon-bg",
  "--pdp-urgency-icon-border",
  "--pdp-urgency-highlight-border",
  "--faq-card-gap",
  "--faq-heading-margin-bottom",
  "--footer-pad-y",
  "--footer-logo-height",
  "--footer-gap",
  "--listicle-title-font",
  "--listicle-title-color",
]);

function toCssVarName(key: string): string {
  const trimmed = key.trim();
  if (trimmed.startsWith("--")) return trimmed;
  if (trimmed.includes("-")) return `--${trimmed}`;
  return `--${trimmed.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase()}`;
}

function parseJson<T>(raw?: string): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

type JsonRecord = Record<string, unknown>

const SalesPdpSchemaContext = createContext<SalesPdpSchemaVersion>("legacy")

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0
}

function toStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => isNonEmptyString(item))
  }
  if (isNonEmptyString(value)) return [value]
  return []
}

function readImageAsset(value: unknown): ImageAsset | null {
  if (!isRecord(value) || !isNonEmptyString(value.alt)) return null
  const src = typeof value.src === "string" ? value.src : ""
  const image: ImageAsset = { alt: value.alt, src }
  if (typeof value.assetPublicId === "string") image.assetPublicId = value.assetPublicId
  if (typeof value.referenceAssetPublicId === "string") image.referenceAssetPublicId = value.referenceAssetPublicId
  return image
}

function isImportVideoSectionConfig(config: unknown): config is ImportVideoSectionConfig {
  return isRecord(config) && Array.isArray(config.cards)
}

function isImportStorySectionConfig(config: unknown): config is ImportStorySectionConfig {
  return isRecord(config) && isNonEmptyString(config.headline) && (Array.isArray(config.steps) || Array.isArray(config.ingredients) || Array.isArray(config.timeline) || "body" in config)
}

function isImportComparisonConfig(config: unknown): config is ImportComparisonConfig {
  return isRecord(config) && isNonEmptyString(config.headline) && "emberColumn" in config && "competitorColumn" in config
}

function isImportGuaranteeConfig(config: unknown): config is ImportGuaranteeConfig {
  return isRecord(config) && isNonEmptyString(config.headline) && ("stats" in config || "iconAlt" in config || "iconAssetPublicId" in config)
}

function isImportReviewWallConfig(config: unknown): config is ImportReviewWallConfig {
  return isRecord(config) && isNonEmptyString(config.headline) && Array.isArray(config.reviews)
}

function requireImportSchemaConfig<T>(
  componentName: string,
  config: unknown,
  guard: (value: unknown) => value is T,
  pageSchemaVersion: SalesPdpSchemaVersion
): T | null {
  if (guard(config)) return config
  if (pageSchemaVersion === "import-v1") {
    throw new Error(`${componentName} requires import-v1 config when SalesPdpPage.schemaVersion is import-v1.`)
  }
  return null
}

function extractSectionId(config: JsonRecord): string | undefined {
  const ids = [config.id, config.anchorId]
  return ids.find((value): value is string => isNonEmptyString(value))
}

function normalizeImportStoryRows(value: unknown): ImportStoryRow[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!isRecord(item)) return []
    const title = isNonEmptyString(item.title)
      ? item.title
      : isNonEmptyString(item.label)
        ? item.label
        : isNonEmptyString(item.value)
          ? item.value
          : ""
    if (!title) return []
    return [
      {
        label: isNonEmptyString(item.label) ? item.label : undefined,
        title,
        body: isNonEmptyString(item.body)
          ? item.body
          : isNonEmptyString(item.detail)
            ? item.detail
            : isNonEmptyString(item.description)
              ? item.description
              : undefined,
      },
    ]
  })
}

function normalizeImportComparisonColumn(value: unknown, fallbackTitle: string) {
  if (isNonEmptyString(value)) return { title: value }
  if (isRecord(value) && isNonEmptyString(value.title)) {
    return {
      title: value.title,
      subtitle: isNonEmptyString(value.subtitle) ? value.subtitle : undefined,
    }
  }
  return { title: fallbackTitle }
}

function normalizeImportMetricList(value: unknown) {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!isRecord(item) || !isNonEmptyString(item.label) || !isNonEmptyString(item.value)) return []
    return [
      {
        label: item.label,
        value: item.value,
        detail: isNonEmptyString(item.detail)
          ? item.detail
          : isNonEmptyString(item.body)
            ? item.body
            : isNonEmptyString(item.description)
              ? item.description
              : undefined,
      },
    ]
  })
}

function selectionFromIds(selection: Record<string, string | undefined>) {
  const entries = Object.entries(selection).filter(([, value]) => typeof value === "string" && value);
  return Object.fromEntries(entries);
}

function matchesOptionValues(
  optionValues: Record<string, unknown> | null | undefined,
  selection: Record<string, unknown>
) {
  if (!optionValues || typeof optionValues !== "object") return false;
  const optionEntries = Object.entries(optionValues);
  const selectionEntries = Object.entries(selection);
  if (optionEntries.length !== selectionEntries.length) return false;
  for (const [key, value] of optionEntries) {
    if (selection[key] !== value) return false;
  }
  return true;
}

function getUtmParams(): Record<string, string> {
  const params = new URLSearchParams(window.location.search);
  const utm: Record<string, string> = {};
  for (const [key, value] of params.entries()) {
    if (key.startsWith("utm_")) utm[key] = value;
  }
  return utm;
}

function normalizeFallbackAssetSrc(fallback?: string): string | undefined {
  if (!fallback) return fallback;
  const trimmedFallback = fallback.trim();
  if (!trimmedFallback) return undefined;
  if (/^https?:\/\//i.test(trimmedFallback)) return trimmedFallback;

  // Legacy funnel payloads may store root-relative public asset paths.
  // In deployed artifact mode, assets are served from /api/public/assets.
  if (trimmedFallback.startsWith("/public/assets/")) {
    return `${apiBaseUrl.replace(/\/+$/, "")}${trimmedFallback}`;
  }
  if (trimmedFallback.startsWith("public/assets/")) {
    return `${apiBaseUrl.replace(/\/+$/, "")}/${trimmedFallback}`;
  }
  return trimmedFallback;
}

function resolveAssetSrc(assetPublicId?: string, fallback?: string): string | undefined {
  if (assetPublicId) return `${apiBaseUrl}/public/assets/${assetPublicId}`;
  return normalizeFallbackAssetSrc(fallback);
}

function resolveImageSrc(image?: ImageAsset): string | undefined {
  if (!image) return undefined;
  return resolveAssetSrc(image.assetPublicId ?? image.referenceAssetPublicId, image.src);
}

function clampIndex(next: number, length: number) {
  if (length <= 0) return 0
  if (next < 0) return length - 1
  if (next >= length) return 0
  return next
}

function currency(n: number) {
  return `$${Math.round(n)}`
}

function normalizeStepTitle(title: string): string {
  return title.replace(/^\s*\d+\s*[\.\):-]?\s*/, "").replace(/\s*:\s*$/, "").trim()
}

function formatStepTitle(title: string, stepNumber: number | null) {
  const baseTitle = normalizeStepTitle(title)
  return stepNumber ? `${stepNumber}. ${baseTitle}` : baseTitle
}

const COMPARISON_VS_RE = /\s+vs\.?\s+/i

function looksLikePrimaryComparisonLabel(value: string) {
  const normalized = value.trim().toLowerCase()
  if (!normalized) return false
  return ["our ", "workflow", "triage", "structured", "system", "handbook", "approach"].some((token) =>
    normalized.includes(token)
  )
}

function looksLikeAlternativeComparisonLabel(value: string) {
  const normalized = value.trim().toLowerCase()
  if (!normalized) return false
  return ["typical", "standard", "generic", "other", "alternative", "old way", "scattered", "checking"].some(
    (token) => normalized.includes(token)
  )
}

function normalizeComparisonTitle(title: string, columns: ComparisonConfig["columns"]) {
  const cleaned = title.trim()
  if (!cleaned) return `${columns.pup} vs. ${columns.disposable}`
  const parts = cleaned.split(COMPARISON_VS_RE)
  if (parts.length !== 2) return cleaned
  const [left, right] = parts.map((value) => value.trim())
  const leftPrimary = looksLikePrimaryComparisonLabel(left)
  const rightPrimary = looksLikePrimaryComparisonLabel(right)
  const leftAlternative = looksLikeAlternativeComparisonLabel(left)
  const rightAlternative = looksLikeAlternativeComparisonLabel(right)
  if ((rightPrimary && !leftPrimary) || (leftAlternative && !rightAlternative)) {
    return `${right} vs. ${left}`
  }
  return `${left} vs. ${right}`
}

function resolveUrgencyMonthLabels(now: Date = new Date()) {
  const currentYear = now.getUTCFullYear();
  const currentMonthIndex = now.getUTCMonth();
  const previousYear = currentMonthIndex === 0 ? currentYear - 1 : currentYear;
  const previousMonthIndex = currentMonthIndex === 0 ? 11 : currentMonthIndex - 1;
  const currentMonthDate = new Date(Date.UTC(currentYear, currentMonthIndex, 1));
  const previousMonthDate = new Date(Date.UTC(previousYear, previousMonthIndex, 1));
  return {
    previousMonthLabel: URGENCY_MONTH_FORMATTER.format(previousMonthDate).toUpperCase(),
    currentMonthLabel: URGENCY_MONTH_FORMATTER.format(currentMonthDate).toUpperCase(),
  };
}

function isRuleMatch(
  rules: Array<{ sizeId: string; colorId: string }> | undefined,
  sizeId: string,
  colorId: string
) {
  if (!rules?.length) return false
  return rules.some((r) => r.sizeId === sizeId && r.colorId === colorId)
}

function IconPlus({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function IconDiamondStar({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M12 2l2.8 5.8 5.8 2.2-5.8 2.2L12 18l-2.8-5.8L3.4 10l5.8-2.2L12 2z"
        fill="currentColor"
      />
    </svg>
  )
}

function IconMinus({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path d="M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function IconCheck({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M20 6L9 17l-5-5"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconArrow({
  dir,
  size = 16,
}: {
  dir: 'left' | 'right'
  size?: number
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d={dir === 'left' ? 'M19 12H7' : 'M5 12h12'}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d={dir === 'left' ? 'M11 6l-6 6 6 6' : 'M13 6l6 6-6 6'}
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconPlayTriangle({ size = 10 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path d="M9 7l10 5-10 5V7z" fill="currentColor" />
    </svg>
  )
}

function IconScrollIndicator({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M12 3v18"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M8 7l4-4 4 4"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8 17l4 4 4-4"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconWarning({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="var(--pdp-warning-bg)" />
      <path d="M12 7v7" stroke="var(--color-bg)" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="12" cy="17.5" r="1.3" fill="var(--color-bg)" />
    </svg>
  )
}

function IconClose({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M18 6L6 18"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path
        d="M6 6l12 12"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function StarRow({ rating, ariaLabel }: { rating: number; ariaLabel: string }) {
  const stars = Array.from({ length: 5 }).map((_, i) => i < rating)
  return (
    <span className={styles.stars} aria-label={ariaLabel}>
      {stars.map((on, i) => (
        <svg
          key={i}
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill={on ? 'var(--pdp-rating-color)' : 'var(--pdp-rating-muted)'}
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path d="M12 17.3l-5.5 3 1-6.1L3 9.8l6.2-.9L12 3.3l2.8 5.6 6.2.9-4.5 4.4 1 6.1-5.7-3z" />
        </svg>
      ))}
    </span>
  )
}

function HeaderBar({
  config,
  visible,
  activeSectionId,
}: {
  config: PdpConfig['hero']['header']
  visible: boolean
  activeSectionId?: string | null
}) {
  const handleHeaderCtaClick = (event: ReactMouseEvent<HTMLAnchorElement>) => {
    if (config.cta.href !== "#top") return
    if (!window.matchMedia(MOBILE_BREAKPOINT_QUERY).matches) return

    const target = document.getElementById(ORDER_NOW_SCROLL_TARGET_ID)
    if (!target) {
      console.error(
        `SalesPdpHeader: cannot find section #${ORDER_NOW_SCROLL_TARGET_ID}. ` +
          "Mobile header CTA cannot scroll to the purchase section."
      )
      return
    }

    event.preventDefault()
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    target.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", block: "center" })
  }

  const designSystemTokens = useDesignSystemTokens()
  const resolvedLogo = useMemo(
    () => withDesignSystemBrandLogo(designSystemTokens, config.logo),
    [config.logo, designSystemTokens]
  )

  return (
    <div className={styles.header} aria-hidden={!visible}>
      <Container className={styles.headerContainer}>
        <div className={`${styles.headerInner} ${visible ? styles.headerVisible : styles.headerHidden}`}>
          <a className={styles.logo} href={resolvedLogo.href ?? '#top'}>
            <img className={styles.logoImg} src={resolveImageSrc(resolvedLogo)} alt={resolvedLogo.alt} />
          </a>

          <nav className={styles.nav} aria-label="Primary">
            {config.nav.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className={activeSectionId && item.href === `#${activeSectionId}` ? styles.navLinkActive : undefined}
              >
                {item.label}
              </a>
            ))}
          </nav>

          <a className={styles.headerCta} href={config.cta.href} onClick={handleHeaderCtaClick}>
            {config.cta.label}
            <span className={styles.headerCtaIcon} aria-hidden="true">
              <IconArrow dir="right" size={14} />
            </span>
          </a>
        </div>
      </Container>
    </div>
  )
}

function Gallery({
  slides,
}: {
  slides: PdpConfig['hero']['gallery']['slides']
}) {
  const [index, setIndex] = useState(0)
  const active = slides[index]

  return (
    <div className={styles.galleryCard}>
      <div className={styles.galleryMain}>
        <img src={resolveImageSrc(active)} alt={active.alt} loading="eager" decoding="async" fetchPriority="high" />
      </div>

      <div className={styles.galleryControls}>
        <button
          type="button"
          className={styles.circleIconBtn}
          onClick={() => setIndex((v) => clampIndex(v - 1, slides.length))}
          aria-label="Previous image"
        >
          <IconArrow dir="left" size={14} />
        </button>
        <span className={styles.galleryCounter}>
          {index + 1} / {slides.length}
        </span>
        <button
          type="button"
          className={styles.circleIconBtn}
          onClick={() => setIndex((v) => clampIndex(v + 1, slides.length))}
          aria-label="Next image"
        >
          <IconArrow dir="right" size={14} />
        </button>
      </div>

      <div className={styles.thumbRow} role="tablist" aria-label="Image thumbnails">
        {slides.map((s, i) => (
          <button
            key={`${s.assetPublicId ?? s.src ?? 'slide'}-${i}`}
            type="button"
            className={`${styles.thumb} ${i === index ? styles.thumbSelected : ''}`}
            onClick={() => setIndex(i)}
            aria-label={`View image ${i + 1}`}
          >
            <img src={resolveAssetSrc(s.thumbAssetPublicId, s.thumbSrc ?? resolveImageSrc(s))} alt={s.alt} />
          </button>
        ))}
      </div>
    </div>
  )
}

function SizeCard({
  option,
  selected,
  onClick,
}: {
  option: SizeOption
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className={`${styles.optionCard} ${styles.sizeCard} ${selected ? styles.optionCardSelected : ''}`}
      onClick={onClick}
      aria-pressed={selected}
    >
	      {selected ? (
	        <span className={styles.selectedCheck} aria-hidden="true">
	          <span
	            style={{
	              display: 'grid',
	              placeItems: 'center',
	              width: 22,
	              height: 22,
	              borderRadius: 999,
	              background: 'var(--pdp-check-bg)',
	              color: 'var(--color-bg)',
	            }}
	          >
	            <IconCheck size={18} />
	          </span>
	        </span>
	      ) : null}
      <p className={styles.optionLabel}>{option.label}</p>
      <p className={styles.optionMeta}>
        {option.sizeIn}
        <br />
        {option.sizeCm}
      </p>
    </button>
  )
}

function OfferCard({
  option,
  selected,
  onClick,
}: {
  option: OfferOption
  selected: boolean
  onClick: () => void
}) {
  const hasSave = Boolean(option.saveLabel)

  return (
    <button
      type="button"
      className={`${styles.optionCard} ${styles.offerCard} ${hasSave ? styles.offerCardHasSave : ''} ${
        selected ? styles.optionCardSelected : ''
      }`}
      onClick={onClick}
      aria-pressed={selected}
    >
	      {selected ? (
	        <span className={styles.selectedCheck} aria-hidden="true">
	          <span
	            style={{
	              display: 'grid',
	              placeItems: 'center',
	              width: 22,
	              height: 22,
	              borderRadius: 999,
	              background: 'var(--pdp-check-bg)',
	              color: 'var(--color-bg)',
	            }}
	          >
	            <IconCheck size={18} />
	          </span>
	        </span>
      ) : null}

      <div className={styles.offerCardMedia}>
        <img className={styles.offerCardImage} src={resolveImageSrc(option.image)} alt={option.image.alt} />
      </div>
      <p className={styles.offerLabel}>{option.title}</p>
      <div className={styles.price}>
        {typeof option.compareAt === 'number' && option.compareAt > option.price ? (
          <span className={styles.compareAt}>{currency(option.compareAt)}</span>
        ) : null}
        {currency(option.price)}
      </div>
      {option.saveLabel ? <div className={styles.saveBar}>{option.saveLabel}</div> : null}
    </button>
  )
}

function ColorSwatch({
  option,
  selected,
  onClick,
}: {
  option: ColorOption
  selected: boolean
  onClick: () => void
}) {
  const background = option.swatch ? option.swatch : undefined

  return (
    <button type="button" className={styles.swatchBtn} onClick={onClick} aria-pressed={selected}>
      <div className={styles.swatchCircleWrap}>
        <div
          className={`${styles.swatchCircle} ${selected ? styles.swatchCircleSelected : ''}`}
          style={background ? { background } : undefined}
        >
          {option.swatchImageSrc || option.swatchAssetPublicId ? (
            <img
              src={resolveAssetSrc(option.swatchAssetPublicId, option.swatchImageSrc)}
              alt=""
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          ) : null}
        </div>

        {selected ? (
          <span className={`${styles.selectedCheck} ${styles.selectedCheckSwatch}`} aria-hidden="true">
            <span
              style={{
                display: 'grid',
                placeItems: 'center',
                width: 22,
                height: 22,
                borderRadius: 999,
                background: 'var(--pdp-check-bg)',
                color: 'var(--color-bg)',
              }}
            >
              <IconCheck size={18} />
            </span>
          </span>
        ) : null}
      </div>
      <div className={styles.swatchLabel}>{option.label}</div>
    </button>
  )
}

function VideoGrid({ videos }: { videos: VideoItem[] }) {
  return (
    <div className={styles.videoGrid}>
      {videos.map((v) => (
        <div key={v.id} className={styles.videoCard}>
          <img src={resolveImageSrc(v.thumbnail)} alt={v.thumbnail.alt} />
          <div className={styles.videoPlay} aria-hidden="true">
            <IconPlayTriangle size={14} />
          </div>
        </div>
      ))}
    </div>
  )
}

type SalesPdpPageProps = {
  anchorId?: string
  schemaVersion?: SalesPdpSchemaVersion
  theme?: ThemeConfig
  themeJson?: string
  content?: (props?: Record<string, unknown>) => ReactNode
  children?: ReactNode
}

export function SalesPdpPage({ anchorId, schemaVersion, theme, themeJson, content, children }: SalesPdpPageProps) {
  useTemplateFonts();
  const designSystemTokens = useDesignSystemTokens() as { cssVars?: Record<string, string | number>; dataTheme?: string } | null
  const themeFromJson = parseJson<ThemeConfig>(themeJson)
  const defaultTheme = salesPdpDefaults.theme
  const themeIsDefault =
    theme && defaultTheme ? JSON.stringify(theme) === JSON.stringify(defaultTheme) : Boolean(!theme && defaultTheme)
  const explicitTheme = themeFromJson ?? (theme && !themeIsDefault ? theme : undefined)
  const resolvedTheme = explicitTheme ?? defaultTheme
  const themeStyle = useMemo(() => {
    const style: Record<string, string> = {}
    if (defaultTheme?.tokens) {
      for (const [rawKey, rawValue] of Object.entries(defaultTheme.tokens)) {
        if (rawValue === undefined || rawValue === null) continue
        style[toCssVarName(rawKey)] = String(rawValue)
      }
    }
    if (designSystemTokens?.cssVars) {
      for (const [rawKey, rawValue] of Object.entries(designSystemTokens.cssVars)) {
        if (rawValue === undefined || rawValue === null) continue
        const cssVarName = toCssVarName(rawKey)
        if (LOCKED_TEMPLATE_CSS_VARS.has(cssVarName)) continue
        style[cssVarName] = String(rawValue)
      }
    }
    if (explicitTheme?.tokens) {
      for (const [rawKey, rawValue] of Object.entries(explicitTheme.tokens)) {
        if (rawValue === undefined || rawValue === null) continue
        const cssVarName = toCssVarName(rawKey)
        if (LOCKED_TEMPLATE_CSS_VARS.has(cssVarName)) continue
        style[cssVarName] = String(rawValue)
      }
    }
    return style
  }, [defaultTheme, designSystemTokens, explicitTheme, resolvedTheme])

  const resolvedAnchorId = anchorId && anchorId.trim() ? anchorId : 'top'
  const body = content ? content({}) : children

  return (
    <SalesPdpSchemaContext.Provider value={schemaVersion ?? "legacy"}>
      <div
        className={`${baseStyles.root} ${styles.page}`}
        id={resolvedAnchorId}
        data-theme={explicitTheme?.dataTheme ?? designSystemTokens?.dataTheme ?? resolvedTheme?.dataTheme}
        data-schema-version={schemaVersion ?? "legacy"}
        style={themeStyle}
      >
        {body}
      </div>
    </SalesPdpSchemaContext.Provider>
  )
}

type SalesPdpHeaderProps = {
  config?: HeaderConfig
  configJson?: string
}

export function SalesPdpHeader({ config, configJson }: SalesPdpHeaderProps) {
  const resolvedConfig = parseJson<HeaderConfig>(configJson) ?? config ?? salesPdpDefaults.config.hero.header
  const navSectionIds = useMemo(
    () =>
      resolvedConfig.nav
        .map((item) => item.href)
        .filter((href) => href.startsWith('#'))
        .map((href) => href.slice(1)),
    [resolvedConfig.nav]
  )
  // The Sales PDP template treats the story "problem" section as the "how-it-works" anchor.
  // Multiple parts of the template rely on this (e.g. styling), so we use it as the trigger
  // for the floating CTA bar.
  const showAfterSectionId = 'how-it-works'

  const [activeSection, setActiveSection] = useState<string | null>(navSectionIds[0] ?? null)
  const [showHeader, setShowHeader] = useState(false)
  const sectionRatioRef = useRef<Map<string, number>>(new Map())

  useEffect(() => {
    const el = document.getElementById(showAfterSectionId)
    if (!el) {
      console.error(
        `SalesPdpHeader: cannot find section #${showAfterSectionId}. ` +
          "The Sales PDP floating CTA bar is configured to show after the story problem section."
      )
      setShowHeader(false)
      return
    }

    const updateHeaderVisibility = () => {
      const rect = el.getBoundingClientRect()
      const triggerOffset = Math.min(Math.max(el.offsetHeight * 0.28, 140), 240)
      setShowHeader(rect.top <= -triggerOffset)
    }

    updateHeaderVisibility()
    window.addEventListener("scroll", updateHeaderVisibility, { passive: true })
    window.addEventListener("resize", updateHeaderVisibility)

    return () => {
      window.removeEventListener("scroll", updateHeaderVisibility)
      window.removeEventListener("resize", updateHeaderVisibility)
    }
  }, [showAfterSectionId])

  useEffect(() => {
    if (!navSectionIds.length) return
    const targets = navSectionIds
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => Boolean(el))
    if (!targets.length) return

    const ratios = sectionRatioRef.current
    ratios.clear()
    targets.forEach((target) => ratios.set(target.id, 0))

    const observer = new IntersectionObserver(
      (entries) => {
        let changed = false
        entries.forEach((entry) => {
          if (!entry.target.id) return
          ratios.set(entry.target.id, entry.isIntersecting ? entry.intersectionRatio : 0)
          changed = true
        })
        if (!changed) return
        let bestId: string | null = null
        let bestRatio = 0
        ratios.forEach((ratio, id) => {
          if (ratio > bestRatio) {
            bestRatio = ratio
            bestId = id
          }
        })
        if (bestId) {
          setActiveSection((prev) => (prev === bestId ? prev : bestId))
        }
      },
      {
        threshold: [0, 0.15, 0.3, 0.5, 0.7, 1],
        rootMargin: '-25% 0px -55% 0px',
      }
    )

    targets.forEach((target) => observer.observe(target))

    return () => observer.disconnect()
  }, [navSectionIds])

  return <HeaderBar config={resolvedConfig} visible={showHeader} activeSectionId={activeSection} />
}

type SalesPdpHeroProps = {
  config?: HeroConfig
  configJson?: string
  modals?: ModalsConfig
  modalsJson?: string
  copy?: UiCopy
  copyJson?: string
}

export function SalesPdpHero({ config, configJson, modals, modalsJson, copy, copyJson }: SalesPdpHeroProps) {
  const runtime = useFunnelRuntime();
  const checkoutHandoffContextRef = useRef<Record<string, unknown> | null>(null);
  const checkoutPagehideTrackedRef = useRef(false);
  const checkoutVisibilityHiddenTrackedRef = useRef(false);
  const resolvedHero = parseJson<HeroConfig>(configJson) ?? config ?? salesPdpDefaults.config.hero
  const resolvedModals = parseJson<ModalsConfig>(modalsJson) ?? modals ?? salesPdpDefaults.config.modals
  const resolvedCopy = parseJson<UiCopy>(copyJson) ?? copy ?? salesPdpDefaults.copy

  const sizeOptions = resolvedHero.purchase.size.options
  const colorOptions = resolvedHero.purchase.color.options
  const offerOptions = resolvedHero.purchase.offer.options
  const variantSchemaDimensions = resolvedHero.purchase.variantSchema?.dimensions
  const hasExplicitVariantSchema = Array.isArray(variantSchemaDimensions) && variantSchemaDimensions.length > 0
  const hasSchemaDimensionType = (type: string) =>
    hasExplicitVariantSchema && variantSchemaDimensions.some((item) => item?.type === type)
  const showSizeSelector = !hasExplicitVariantSchema || hasSchemaDimensionType("size")
  const showColorSelector = !hasExplicitVariantSchema || hasSchemaDimensionType("color")
  const showOfferSelector = true

  const defaultSelection = resolvedHero.purchase.variantSchema?.defaults
  const [selectedSize, setSelectedSize] = useState(defaultSelection?.sizeId ?? sizeOptions[0]?.id)
  const [selectedColor, setSelectedColor] = useState(defaultSelection?.colorId ?? colorOptions[0]?.id)
  const [selectedOffer, setSelectedOffer] = useState(defaultSelection?.offerId ?? offerOptions[0]?.id)

  const [openPillIndex, setOpenPillIndex] = useState<number | null>(null)
  const [isPillDragging, setIsPillDragging] = useState(false)
  const pillViewportRef = useRef<HTMLDivElement | null>(null)
  const ctaButtonRef = useRef<HTMLButtonElement | null>(null)
  const ctaHighlightTimeoutRef = useRef<number | null>(null)
  const ctaObserverRef = useRef<IntersectionObserver | null>(null)
  const [pillHintMounted, setPillHintMounted] = useState(false);
  const [pillHintVisible, setPillHintVisible] = useState(false);
  const pillHintHasShownRef = useRef(false);
  const pillHintTimeoutIdsRef = useRef<number[]>([]);
  const pillDragState = useRef({
    pointerDown: false,
    dragging: false,
    startX: 0,
    startY: 0,
    scrollLeft: 0,
    wasDragged: false,
  })

  const clearPillHintTimeouts = () => {
    pillHintTimeoutIdsRef.current.forEach((id) => window.clearTimeout(id));
    pillHintTimeoutIdsRef.current = [];
  };

  const dismissPillHint = (immediate = false) => {
    pillHintHasShownRef.current = true;
    clearPillHintTimeouts();
    setPillHintVisible(false);
    if (immediate || !pillHintMounted) {
      setPillHintMounted(false);
      return;
    }
    pillHintTimeoutIdsRef.current = [
      window.setTimeout(() => {
        setPillHintMounted(false);
      }, 260),
    ];
  };

  const flashCtaButton = () => {
    const el = ctaButtonRef.current;
    if (!el) {
      console.error("SalesPdpHero: cannot highlight CTA because ctaButtonRef is null.");
      return;
    }

    const cls = styles.ctaButtonHighlight;
    el.classList.remove(cls);
    // Force a reflow so repeated selections restart the CSS animation.
    el.getBoundingClientRect();
    el.classList.add(cls);

    if (ctaHighlightTimeoutRef.current) window.clearTimeout(ctaHighlightTimeoutRef.current);
    ctaHighlightTimeoutRef.current = window.setTimeout(() => {
      el.classList.remove(cls);
      ctaHighlightTimeoutRef.current = null;
    }, 1300);
  };

  const scrollToCtaAndHighlight = () => {
    const el = ctaButtonRef.current;
    if (!el) {
      console.error("SalesPdpHero: cannot scroll to CTA because ctaButtonRef is null.");
      return;
    }

    ctaObserverRef.current?.disconnect();
    ctaObserverRef.current = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry?.isIntersecting) return;
        flashCtaButton();
        ctaObserverRef.current?.disconnect();
        ctaObserverRef.current = null;
      },
      { threshold: 0.6 }
    );
    ctaObserverRef.current.observe(el);

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", block: "center" });
  };

  const handleOfferSelect = (offerId: OfferOption["id"]) => {
    setSelectedOffer(offerId);
    scrollToCtaAndHighlight();
  };

  const [openSizeChart, setOpenSizeChart] = useState(false)
  const [openWhyBundle, setOpenWhyBundle] = useState(false)
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  const [isCheckingOut, setIsCheckingOut] = useState(false)

  useEffect(() => {
    const emitCheckoutHandoffEvent = (
      eventType: "checkout_pagehide" | "checkout_visibility_hidden",
    ) => {
      const context = checkoutHandoffContextRef.current;
      if (!context) return;
      runtime?.trackEvent?.({
        eventType,
        props: {
          ...context,
          ...buildCheckoutTimingProps({}),
        },
      });
    };
    const handlePagehide = () => {
      if (checkoutPagehideTrackedRef.current) return;
      checkoutPagehideTrackedRef.current = true;
      emitCheckoutHandoffEvent("checkout_pagehide");
    };
    const handleVisibilityChange = () => {
      if (checkoutVisibilityHiddenTrackedRef.current) return;
      if (document.visibilityState !== "hidden") return;
      checkoutVisibilityHiddenTrackedRef.current = true;
      emitCheckoutHandoffEvent("checkout_visibility_hidden");
    };
    window.addEventListener("pagehide", handlePagehide);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("pagehide", handlePagehide);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [runtime]);

  useEffect(() => {
    return () => {
      if (ctaHighlightTimeoutRef.current) window.clearTimeout(ctaHighlightTimeoutRef.current);
      ctaObserverRef.current?.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!sizeOptions.length) return
    if (!sizeOptions.some((o) => o.id === selectedSize)) {
      setSelectedSize(sizeOptions[0].id)
    }
  }, [sizeOptions, selectedSize])

  useEffect(() => {
    if (!colorOptions.length) return
    if (!colorOptions.some((o) => o.id === selectedColor)) {
      setSelectedColor(colorOptions[0].id)
    }
  }, [colorOptions, selectedColor])

  useEffect(() => {
    if (!offerOptions.length) return
    if (!offerOptions.some((o) => o.id === selectedOffer)) {
      setSelectedOffer(offerOptions[0].id)
    }
  }, [offerOptions, selectedOffer])

  useEffect(() => {
    if (pillHintHasShownRef.current) return;
    if (!resolvedHero.purchase.faqPills.length) return;

    const ENTER_DELAY_MS = 200;
    const VISIBLE_MS = 3500;
    const EXIT_MS = 260;

    setPillHintMounted(true);
    const timeoutIds: number[] = [];
    timeoutIds.push(
      window.setTimeout(() => {
        pillHintHasShownRef.current = true;
        setPillHintVisible(true);
      }, ENTER_DELAY_MS)
    );
    timeoutIds.push(
      window.setTimeout(() => {
        setPillHintVisible(false);
      }, ENTER_DELAY_MS + VISIBLE_MS)
    );
    timeoutIds.push(
      window.setTimeout(() => {
        setPillHintMounted(false);
      }, ENTER_DELAY_MS + VISIBLE_MS + EXIT_MS)
    );
    pillHintTimeoutIdsRef.current = timeoutIds;

    return () => {
      timeoutIds.forEach((id) => window.clearTimeout(id));
      pillHintTimeoutIdsRef.current = [];
    };
  }, [resolvedHero.purchase.faqPills.length]);

  const selectedSizeObj = useMemo(
    () => sizeOptions.find((o) => o.id === selectedSize) ?? sizeOptions[0],
    [sizeOptions, selectedSize]
  )
  const selectedColorObj = useMemo(
    () => colorOptions.find((o) => o.id === selectedColor) ?? colorOptions[0],
    [colorOptions, selectedColor]
  )
  const selectedOfferObj = useMemo(
    () => offerOptions.find((o) => o.id === selectedOffer) ?? offerOptions[0],
    [offerOptions, selectedOffer]
  )
  const selectorTitleMap = useMemo(() => {
    const visibleSelectors = [
      showSizeSelector ? "size" : null,
      showColorSelector ? "color" : null,
      showOfferSelector ? "offer" : null,
    ].filter(Boolean) as Array<"size" | "color" | "offer">
    const showNumbers = visibleSelectors.length > 1
    const sequence = new Map<"size" | "color" | "offer", number | null>()
    visibleSelectors.forEach((key, index) => {
      sequence.set(key, showNumbers ? index + 1 : null)
    })
    return {
      size: formatStepTitle(resolvedHero.purchase.size.title, sequence.get("size") ?? null),
      color: formatStepTitle(resolvedHero.purchase.color.title, sequence.get("color") ?? null),
      offer: formatStepTitle(resolvedHero.purchase.offer.title, sequence.get("offer") ?? null),
    }
  }, [
    resolvedHero.purchase.color.title,
    resolvedHero.purchase.offer.title,
    resolvedHero.purchase.size.title,
    showColorSelector,
    showOfferSelector,
    showSizeSelector,
  ])

  const showOutOfStock = isRuleMatch(resolvedHero.purchase.outOfStock, selectedSize, selectedColor)
  const showShippingDelay = isRuleMatch(resolvedHero.purchase.shippingDelay, selectedSize, selectedColor)

  const ctaLabel = resolvedHero.purchase.cta.labelTemplate.replace('{price}', currency(selectedOfferObj.price))
  const urgencyMessage = resolvedHero.purchase.cta.urgency.message
  const urgencyHighlight = 'Order now before we run out again.'
  const urgencyHighlightIndex = urgencyMessage.indexOf(urgencyHighlight)
  const urgencyLead =
    urgencyHighlightIndex >= 0 ? urgencyMessage.slice(0, urgencyHighlightIndex) : urgencyMessage
  const urgencyTail =
    urgencyHighlightIndex >= 0
      ? urgencyMessage.slice(urgencyHighlightIndex + urgencyHighlight.length)
      : ''
  const visibleCtaSubBullets = resolvedHero.purchase.cta.subBullets.filter(
    (text) => !/\bbonus(?:es)?\b|\bgift(?:s)?\b/i.test(text)
  )
  const urgencyRows = useMemo(() => {
    const rows = resolvedHero.purchase.cta.urgency.rows
    if (rows.length < 2) return rows
    const { previousMonthLabel, currentMonthLabel } = resolveUrgencyMonthLabels()
    return rows.map((row, index) => {
      if (index === 0) return { ...row, label: previousMonthLabel }
      if (index === 1) return { ...row, label: currentMonthLabel }
      return row
    })
  }, [resolvedHero.purchase.cta.urgency.rows])

  const handleCheckout = async () => {
    setCheckoutError(null);
    if (!runtime) {
      setCheckoutError("Checkout is unavailable.");
      return;
    }
    if (runtime.commerceError) {
      setCheckoutError(runtime.commerceError);
      return;
    }
    if (!runtime.commerce) {
      setCheckoutError("Commerce data is not available.");
      return;
    }
    const variants = runtime.commerce.product?.variants || [];
    if (!variants.length) {
      setCheckoutError("Checkout is not configured for this funnel product. No product variants were found.");
      return;
    }
    const selection = selectionFromIds({
      offerId: selectedOfferObj?.id,
      ...(showSizeSelector ? { sizeId: selectedSizeObj?.id } : {}),
      ...(showColorSelector ? { colorId: selectedColorObj?.id } : {}),
    });
    const variant = variants.find((item) => matchesOptionValues(item.option_values, selection));
    if (!variant) {
      setCheckoutError("No variant matches the selected options.");
      return;
    }
    if (!variant.provider) {
      setCheckoutError("Checkout is not configured for this funnel product. Variant provider is missing.");
      return;
    }

    setIsCheckingOut(true);
    try {
      const checkoutReturnUrl = new URL(window.location.href);
      const checkoutCancelUrl = new URL(window.location.href);
      checkoutReturnUrl.searchParams.set("checkout", "success");
      checkoutCancelUrl.searchParams.set("checkout", "cancel");
      const transitionId = buildCheckoutTransitionId();
      const ctaId = "sales_pdp_purchase_cta";
      const checkoutAttribution = buildCheckoutAttributionProps({
        pageVariant: (runtime.pageId ? runtime.pageMap[runtime.pageId] : null) || runtime.entrySlug || null,
        ctaId,
        transitionId,
      });
      const checkoutEventProps = {
        ctaId,
        transitionId,
        variantId: variant.id,
        value: Math.round(variant.price) / 100,
        currency: variant.currency,
        ...buildCheckoutTimingProps({
          transitionId,
          ctaId,
          selectedOffer: selectedOfferObj?.id,
          variantIds: [variant.id],
        }),
      };
      runtime.trackEvent?.({
        eventType: "checkout_click",
        props: checkoutEventProps,
      });
      runtime.trackEvent?.(
        checkoutClickEventForStage({
          fromStage: runtime.pageStage || "custom",
          props: checkoutEventProps,
        }),
      );
      const response = await fetch(`${apiBaseUrl}/public/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          funnelSlug: runtime.funnelSlug,
          variantId: variant.id,
          selection,
          quantity: 1,
          successUrl: checkoutReturnUrl.toString(),
          cancelUrl: checkoutCancelUrl.toString(),
          pageId: runtime.pageId || undefined,
          visitorId: runtime.visitorId || undefined,
          sessionId: runtime.sessionId || undefined,
          utm: getUtmParams(),
          ...checkoutAttribution,
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || response.statusText);
      }
      const data = await response.json();
      if (!data?.checkoutUrl) {
        throw new Error("Checkout URL is missing.");
      }
      const normalizedProvider = typeof variant.provider === "string" ? variant.provider.trim().toLowerCase() : "";
      const pendingPurchaseKey = pendingMetaPurchaseStorageKey(runtime.sessionId || null, runtime.funnelSlug);
      if (normalizedProvider === "stripe" && pendingPurchaseKey) {
        writePendingMetaPurchase(sessionStorage, pendingPurchaseKey, {
          funnelSlug: runtime.funnelSlug,
          pageId: runtime.pageId || null,
          variantId: variant.id,
          value: variant.price,
          currency: variant.currency || null,
          quantity: 1,
          provider: normalizedProvider,
        });
      }
      const finalCheckoutUrl = appendCheckoutTrackingUrlParams(data.checkoutUrl as string);
      checkoutHandoffContextRef.current = {
        ...checkoutEventProps,
        ...buildCheckoutTimingProps({
          transitionId,
          ctaId,
          checkoutUrl: finalCheckoutUrl,
          selectedOffer: selectedOfferObj?.id,
          variantIds: [variant.id],
        }),
      };
      checkoutPagehideTrackedRef.current = false;
      checkoutVisibilityHiddenTrackedRef.current = false;
      runtime.trackEvent?.({
        eventType: "checkout_redirect_started",
        props: checkoutHandoffContextRef.current,
      });
      window.location.href = finalCheckoutUrl;
    } catch (err) {
      setCheckoutError(err instanceof Error ? err.message : "Checkout failed.");
      setIsCheckingOut(false);
    }
  }

  const handlePillPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    dismissPillHint()
    const viewport = pillViewportRef.current
    if (!viewport) return
    pillDragState.current.pointerDown = true
    pillDragState.current.dragging = false
    pillDragState.current.wasDragged = false
    pillDragState.current.startX = event.clientX
    pillDragState.current.startY = event.clientY
    pillDragState.current.scrollLeft = viewport.scrollLeft
  }

  const handlePillPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const state = pillDragState.current
    if (!state.pointerDown) return
    const viewport = pillViewportRef.current
    if (!viewport) return
    const deltaX = event.clientX - state.startX
    const deltaY = event.clientY - state.startY
    if (!state.dragging) {
      if (Math.abs(deltaX) < 6 || Math.abs(deltaX) < Math.abs(deltaY)) return
      state.dragging = true
      state.wasDragged = true
      setIsPillDragging(true)
      viewport.setPointerCapture(event.pointerId)
    }
    viewport.scrollLeft = state.scrollLeft - deltaX
  }

  const handlePillPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const state = pillDragState.current
    if (!state.pointerDown) return
    const viewport = pillViewportRef.current
    if (state.dragging && viewport?.hasPointerCapture(event.pointerId)) {
      viewport.releasePointerCapture(event.pointerId)
    }
    state.pointerDown = false
    state.dragging = false
    setIsPillDragging(false)
    if (state.wasDragged) {
      window.setTimeout(() => {
        state.wasDragged = false
      }, 0)
    }
  }

  const handlePillClick = (idx: number) => {
    if (pillDragState.current.wasDragged) return
    dismissPillHint()
    setOpenPillIndex(idx)
  }

  return (
    <>
      <section className={`${styles.sectionPeach} ${styles.heroSection}`}>
        <Container>
              <div className={styles.heroGrid}>
                <div>
              <Gallery slides={resolvedHero.gallery.slides} />
                </div>

            <div id={ORDER_NOW_SCROLL_TARGET_ID}>
              {/*
                Auto-sliding FAQ pills (marquee-style)
                - Continuously scrolls horizontally like the marquee band.
                - Pauses on hover/focus and when an answer is open.
                - Clicking a pill always opens the answer panel.
              */}
              <div className={styles.pillMarqueeWrap}>
                <div
                  className={`${styles.pillMarquee} ${openPillIndex !== null ? styles.pillMarqueePaused : ''} ${
                    isPillDragging ? styles.pillMarqueeDragging : ''
                  }`}
                  aria-label="Quick questions"
                >
                  <div
                    className={styles.pillMarqueeViewport}
                    ref={pillViewportRef}
                    onPointerDown={handlePillPointerDown}
                    onPointerMove={handlePillPointerMove}
                    onPointerUp={handlePillPointerUp}
                    onPointerCancel={handlePillPointerUp}
                  >
                    <div className={styles.pillMarqueeTrack}>
                      {/* Primary group */}
                      <div className={styles.pillGroup}>
                        {resolvedHero.purchase.faqPills.map((p, idx) => {
                          const active = openPillIndex === idx
                          return (
                            <button
                              key={`pill-a-${p.label}-${idx}`}
                              type="button"
                              className={`${styles.pill} ${active ? styles.pillActive : ''}`}
                              onClick={() => handlePillClick(idx)}
                              aria-pressed={active}
                            >
                              <IconDiamondStar size={14} />
                              {p.label}
                            </button>
                          )
                        })}
                      </div>

                      {/* Duplicate group for seamless looping */}
                      <div className={styles.pillGroup} aria-hidden="true">
                        {resolvedHero.purchase.faqPills.map((p, idx) => {
                          const active = openPillIndex === idx
                          return (
                            <button
                              key={`pill-b-${p.label}-${idx}`}
                              type="button"
                              className={`${styles.pill} ${active ? styles.pillActive : ''}`}
                              onClick={() => handlePillClick(idx)}
                              aria-pressed={active}
                              tabIndex={-1}
                            >
                              <IconDiamondStar size={14} />
                              {p.label}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                </div>

                {pillHintMounted ? (
                  <div
                    className={`${styles.pillHint} ${pillHintVisible ? styles.pillHintVisible : ''}`}
                    aria-hidden="true"
                  >
                    <span className={styles.pillHintPointer}>👆</span>
                    <span className={styles.pillHintText}>Click any question</span>
                  </div>
                ) : null}
              </div>

              {openPillIndex !== null ? (
                <div className={styles.pillAnswer}>
                  <div className={styles.pillAnswerHeader}>
                    <h3 className={styles.pillAnswerTitle}>
                      {resolvedHero.purchase.faqPills[openPillIndex]?.label}
                    </h3>
                    <button
                      type="button"
                      className={styles.pillAnswerClose}
                      onClick={() => setOpenPillIndex(null)}
                      aria-label="Close"
                    >
                      <IconClose size={18} />
                    </button>
                  </div>
                  <p className={styles.pillAnswerBody}>
                    {resolvedHero.purchase.faqPills[openPillIndex]?.answer}
                  </p>
                </div>
              ) : null}

              <h1 className={styles.h1}>{resolvedHero.purchase.title}</h1>

              <div className={styles.benefitsGrid}>
                {resolvedHero.purchase.benefits.map((b) => (
                  <div key={b.text} className={styles.benefit}>
                    <span className={styles.checkCircle} aria-hidden="true">
                      <IconCheck size={18} />
                    </span>
                    {b.text}
                  </div>
                ))}
              </div>

              <div className={styles.divider} />

              {showSizeSelector ? (
                <div>
                  <div className={styles.sectionTitleRow}>
                    <div className={styles.stepTitle}>{selectorTitleMap.size}</div>
                    <button type="button" className={styles.helpLink} onClick={() => setOpenSizeChart(true)}>
                      {resolvedHero.purchase.size.helpLinkLabel}
                    </button>
                  </div>

                  <div className={styles.optionGrid3}>
                    {sizeOptions.map((o) => (
                      <SizeCard
                        key={o.id}
                        option={o}
                        selected={o.id === selectedSize}
                        onClick={() => setSelectedSize(o.id)}
                      />
                    ))}
                  </div>

                  {showShippingDelay ? (
                    <div className={styles.delayBar}>
                      <span aria-hidden="true">⚠️</span>
                      <span className={styles.delayText}>{resolvedHero.purchase.size.shippingDelayLabel}</span>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {showSizeSelector && (showColorSelector || showOfferSelector) ? (
                <div className={styles.divider} />
              ) : null}

              {showColorSelector ? (
                <div>
                  <div className={styles.sectionTitleRow}>
                    <div className={styles.stepTitle}>{selectorTitleMap.color}</div>
                  </div>
                  <div className={styles.colorRow}>
                    {colorOptions.map((c) => (
                      <ColorSwatch
                        key={c.id}
                        option={c}
                        selected={c.id === selectedColor}
                        onClick={() => setSelectedColor(c.id)}
                      />
                    ))}
                  </div>

                  {showOutOfStock ? (
                    <div className={styles.stockNotice}>
                      <div style={{ fontWeight: 900, marginBottom: 6 }}>{resolvedHero.purchase.color.outOfStockTitle}</div>
                      <div style={{ color: 'var(--color-muted)' }}>{resolvedHero.purchase.color.outOfStockBody}</div>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {showColorSelector && showOfferSelector ? <div className={styles.divider} /> : null}

              {/* Offer */}
              {showOfferSelector ? (
                <div>
                  <div className={styles.sectionTitleRow}>
                    <div className={styles.stepTitle}>{selectorTitleMap.offer}</div>
                  </div>
                  <div className={styles.offerHelper}>
                    {resolvedHero.purchase.offer.helperText}
                    {resolvedHero.purchase.offer.seeWhyLabel.trim() ? (
                      <>
                        {" "}
                        <button type="button" className={styles.seeWhy} onClick={() => setOpenWhyBundle(true)}>
                          {resolvedHero.purchase.offer.seeWhyLabel}
                        </button>
                      </>
                    ) : null}
                  </div>

                  <div className={styles.offerGrid}>
                    {offerOptions.map((o) => (
                      <OfferCard
                        key={o.id}
                        option={o}
                        selected={o.id === selectedOffer}
                        onClick={() => handleOfferSelect(o.id)}
                      />
                    ))}
                  </div>

                  <button
                    type="button"
                    className={styles.ctaButton}
                    onClick={handleCheckout}
                    disabled={isCheckingOut}
                    aria-busy={isCheckingOut ? "true" : undefined}
                    ref={ctaButtonRef}
                  >
                    {isCheckingOut ? "Opening secure checkout..." : ctaLabel}
                    <span className={styles.ctaIconCircle} aria-hidden="true">
                      <IconArrow dir="right" size={24} />
                    </span>
                  </button>
                  {checkoutError ? (
                    <div className={styles.stockNotice} role="alert">
                      {checkoutError}
                    </div>
                  ) : null}

                  {visibleCtaSubBullets.length > 0 ? (
                    <div className={styles.ctaSubBullets}>
                      {visibleCtaSubBullets.map((t) => (
                        <span key={t}>
                          <span className={styles.checkCircle} aria-hidden="true">
                            <IconCheck size={18} />
                          </span>
                          {t}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  <div className={styles.urgency}>
                    <div className={styles.urgencyTop}>
                      <span className={styles.urgencyIcon} aria-hidden="true">
                        <IconWarning size={28} />
                      </span>
                      <div className={styles.urgencyMessage}>
                        {urgencyHighlightIndex >= 0 ? (
                          <>
                            {urgencyLead}
                            <strong>{urgencyHighlight}</strong>
                            {urgencyTail}
                          </>
                        ) : (
                          urgencyMessage
                        )}
                      </div>
                    </div>
                    <div className={styles.urgencyRows}>
                      {urgencyRows.map((r, index) => (
                        <div
                          key={`${r.label}-${index}`}
                          className={`${styles.urgencyRow} ${
                            r.tone === "highlight"
                              ? styles.urgencyRowHighlight
                              : r.tone === "muted"
                                ? styles.urgencyRowMuted
                                : ""
                          }`}
                        >
                          <span>{r.label}</span>
                          <span>{r.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </Container>
      </section>

      <Modal
        open={openSizeChart}
        onClose={() => setOpenSizeChart(false)}
        ariaLabel={resolvedModals.sizeChart.title}
        copy={resolvedCopy.modal}
      >
        <h2 style={{ marginTop: 0 }}>{resolvedModals.sizeChart.title}</h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', minWidth: 560, borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: 10, borderBottom: '1px solid var(--pdp-black-12)' }}>Size</th>
                <th style={{ textAlign: 'left', padding: 10, borderBottom: '1px solid var(--pdp-black-12)' }}>Dimensions</th>
                <th style={{ textAlign: 'left', padding: 10, borderBottom: '1px solid var(--pdp-black-12)' }}>Ideal for</th>
                <th style={{ textAlign: 'left', padding: 10, borderBottom: '1px solid var(--pdp-black-12)' }}>Weight</th>
              </tr>
            </thead>
            <tbody>
              {resolvedModals.sizeChart.sizes.map((s) => (
                <tr key={s.label}>
                  <td style={{ padding: 10, borderBottom: '1px solid var(--pdp-black-08)', fontWeight: 700 }}>{s.label}</td>
                  <td style={{ padding: 10, borderBottom: '1px solid var(--pdp-black-08)' }}>{s.size}</td>
                  <td style={{ padding: 10, borderBottom: '1px solid var(--pdp-black-08)' }}>{s.idealFor}</td>
                  <td style={{ padding: 10, borderBottom: '1px solid var(--pdp-black-08)' }}>{s.weight}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p style={{ color: 'var(--pdp-black-65)' }}>{resolvedModals.sizeChart.note}</p>
      </Modal>

      <Modal
        open={openWhyBundle}
        onClose={() => setOpenWhyBundle(false)}
        ariaLabel={resolvedModals.whyBundle.title}
        copy={resolvedCopy.modal}
      >
        <h2 style={{ marginTop: 0 }}>{resolvedModals.whyBundle.title}</h2>
        <p style={{ color: 'var(--pdp-black-70)' }}>{resolvedModals.whyBundle.body}</p>
        <div style={{ display: 'grid', gap: 12, marginTop: 14 }}>
          {resolvedModals.whyBundle.quotes.map((q, i) => (
            <div
              key={q.author + i}
              style={{
                border: '1px solid var(--pdp-black-10)',
                borderRadius: 12,
                padding: 14,
                background: 'var(--pdp-black-03)',
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: 6 }}>&ldquo;{q.text}&rdquo;</div>
              <div style={{ color: 'var(--pdp-black-65)' }}>— {q.author}</div>
            </div>
          ))}
        </div>
      </Modal>
    </>
  )
}

type SalesPdpVideosProps = {
  config?: VideoSectionConfig | ImportVideoSectionConfig
  configJson?: string
}

export function SalesPdpVideos({ config, configJson }: SalesPdpVideosProps) {
  const pageSchemaVersion = useContext(SalesPdpSchemaContext)
  const resolvedConfig = parseJson<VideoSectionConfig | ImportVideoSectionConfig>(configJson) ?? config

  if (!resolvedConfig) return null

  const importConfig = requireImportSchemaConfig(
    "SalesPdpVideos",
    resolvedConfig,
    isImportVideoSectionConfig,
    pageSchemaVersion
  )

  if (importConfig) {
    const stats = normalizeImportMetricList(importConfig.stats)
    return (
      <section id={importConfig.id} className={`${styles.sectionPeach} ${styles.sectionPad}`}>
        <Container>
          <div className={styles.reviewWallHeader}>
            {importConfig.badgeText ? <div className={styles.sectionBadge}>{importConfig.badgeText}</div> : null}
            <h2 className={styles.sectionHeading}>{importConfig.sectionTitle}</h2>
            {importConfig.sectionSubtitle ? <p className={styles.importSectionSubtitle}>{importConfig.sectionSubtitle}</p> : null}
          </div>

          <div className={styles.importCardGrid}>
            {importConfig.cards.map((card: ImportVideoSectionConfig["cards"][number], index: number) => {
              const image = readImageAsset(card.image)
              const cardKey = card.id ?? `${card.title}-${index}`
              return (
                <article key={cardKey} className={styles.importCard}>
                  {image ? (
                    <div className={styles.importCardImageWrap}>
                      <img className={styles.importCardImage} src={resolveImageSrc(image)} alt={image.alt} />
                    </div>
                  ) : null}
                  <div className={styles.importCardBody}>
                    {card.eyebrow ? <div className={styles.importCardEyebrow}>{card.eyebrow}</div> : null}
                    <h3 className={styles.importCardTitle}>{card.title}</h3>
                    {card.body ? <p className={styles.importCardText}>{card.body}</p> : null}
                  </div>
                </article>
              )
            })}
          </div>

          {stats.length ? (
            <div className={styles.importMetricGrid}>
              {stats.map((metric) => (
                <div key={`${metric.label}-${metric.value}`} className={styles.importMetricCard}>
                  <div className={styles.importMetricValue}>{metric.value}</div>
                  <div className={styles.importMetricLabel}>{metric.label}</div>
                  {metric.detail ? <div className={styles.importMetricDetail}>{metric.detail}</div> : null}
                </div>
              ))}
            </div>
          ) : null}

          {importConfig.footnote ? <p className={styles.importSectionFootnote}>{importConfig.footnote}</p> : null}
        </Container>
      </section>
    )
  }

  const legacyConfig = resolvedConfig as VideoSectionConfig
  return (
    <section className={`${styles.sectionPeach} ${styles.sectionPad}`}>
      <Container>
        <div className={styles.reviewWallHeader}>
          <div className={styles.sectionBadge}>{legacyConfig.badge}</div>
          <h2 className={styles.sectionHeading}>{legacyConfig.title}</h2>
        </div>
        <VideoGrid videos={legacyConfig.videos} />
      </Container>
    </section>
  )
}

type SalesPdpMarqueeProps = {
  config?: MarqueeConfig
  configJson?: string
}

export function SalesPdpMarquee({ config, configJson }: SalesPdpMarqueeProps) {
  const resolvedConfig = parseJson<MarqueeConfig>(configJson) ?? config ?? salesPdpDefaults.config.marquee
  return <Marquee items={resolvedConfig.items} repeat={resolvedConfig.repeat} />
}

type SalesPdpStoryProblemProps = {
  config?: StorySectionConfig | ImportStorySectionConfig
  configJson?: string
}

type SalesPdpStorySolutionProps = {
  config?: (StorySectionConfig & { callout: CalloutConfig }) | ImportStorySectionConfig
  configJson?: string
}

function SalesPdpStorySection({
  section,
  callout,
  className,
}: {
  section: StorySectionConfig
  callout?: CalloutConfig
  className?: string
}) {
  const sectionBg = section.bg === 'blue' ? styles.sectionBlue : styles.sectionPeach
  const layout = section.layout === 'textRight' ? 'textRight' : 'textLeft'
  const gridLayoutClass = layout === 'textRight' ? styles.storyGridTextRight : styles.storyGridTextLeft
  return (
    <section id={section.id} className={`${sectionBg} ${styles.sectionPad} ${className ?? ''}`.trim()}>
      <Container className={styles.storyContainerTight}>
        <div className={`${styles.storyGrid} ${gridLayoutClass}`}>
          {layout === 'textRight' ? (
            <>
              <div className={styles.storyMediaFrame}>
                <img className={styles.storyImage} src={resolveImageSrc(section.image)} alt={section.image.alt} />
              </div>
              <StoryText section={section} />
            </>
          ) : (
            <>
              <StoryText section={section} />
              <div className={styles.storyMediaFrame}>
                <img className={styles.storyImage} src={resolveImageSrc(section.image)} alt={section.image.alt} />
              </div>
            </>
          )}
        </div>

        {callout ? (
          <div className={styles.callout}>
            <div>
              <p className={styles.calloutTitle}>{callout.leftTitle}</p>
              <p className={styles.calloutBody}>{callout.leftBody}</p>
            </div>
            <div>
              <p className={styles.calloutTitle}>{callout.rightTitle}</p>
              <p className={styles.calloutBody}>{callout.rightBody}</p>
            </div>
          </div>
        ) : null}
      </Container>
    </section>
  )
}

export function SalesPdpStoryProblem({ config, configJson }: SalesPdpStoryProblemProps) {
  const pageSchemaVersion = useContext(SalesPdpSchemaContext)
  const resolvedConfig =
    parseJson<StorySectionConfig | ImportStorySectionConfig>(configJson) ?? config ?? salesPdpDefaults.config.story.problem
  const importConfig = requireImportSchemaConfig(
    "SalesPdpStoryProblem",
    resolvedConfig,
    isImportStorySectionConfig,
    pageSchemaVersion
  )
  if (importConfig) {
    return <SalesPdpImportStorySection section={importConfig} backgroundClass={styles.sectionPeach} />
  }
  return <SalesPdpStorySection section={resolvedConfig as StorySectionConfig} />
}

export function SalesPdpStorySolution({ config, configJson }: SalesPdpStorySolutionProps) {
  const pageSchemaVersion = useContext(SalesPdpSchemaContext)
  const resolvedConfig =
    parseJson<(StorySectionConfig & { callout: CalloutConfig }) | ImportStorySectionConfig>(configJson) ??
    config ??
    salesPdpDefaults.config.story.solution
  const importConfig = requireImportSchemaConfig(
    "SalesPdpStorySolution",
    resolvedConfig,
    isImportStorySectionConfig,
    pageSchemaVersion
  )
  if (importConfig) {
    return <SalesPdpImportStorySection section={importConfig} backgroundClass={styles.sectionBlue} />
  }
  const legacyConfig = resolvedConfig as StorySectionConfig & { callout: CalloutConfig }
  return (
    <SalesPdpStorySection
      section={legacyConfig}
      callout={legacyConfig.callout}
      className={styles.solutionSection}
    />
  )
}

function SalesPdpImportStorySection({
  section,
  backgroundClass,
}: {
  section: ImportStorySectionConfig
  backgroundClass: string
}) {
  const rows = [
    ...normalizeImportStoryRows(section.steps),
    ...normalizeImportStoryRows(section.ingredients),
    ...normalizeImportStoryRows(section.timeline),
  ]
  const bodyParagraphs = toStringList(section.body)
  const image = readImageAsset(section.image)
  return (
    <section
      id={extractSectionId(section)}
      className={`${backgroundClass} ${styles.sectionPad} ${styles.importStorySection}`.trim()}
    >
      <Container className={styles.storyContainerTight}>
        <div className={`${styles.storyGrid} ${styles.storyGridTextLeft}`}>
          <div className={styles.storyText}>
            {section.eyebrow ? (
              <div className={styles.sectionBadge} style={{ marginLeft: 0 }}>
                {section.eyebrow}
              </div>
            ) : null}
            <h2 className={styles.storyTitle}>{section.headline}</h2>
            {bodyParagraphs.map((paragraph) => (
              <p key={paragraph} className={styles.storyPara}>
                {paragraph}
              </p>
            ))}
            {rows.length ? (
              <div className={styles.importStoryRowList}>
                {rows.map((row, index) => (
                  <div key={`${row.title}-${index}`} className={styles.importStoryRow}>
                    {row.label ? <div className={styles.importStoryRowLabel}>{row.label}</div> : null}
                    <div className={styles.importStoryRowTitle}>{row.title}</div>
                    {row.body ? <div className={styles.importStoryRowBody}>{row.body}</div> : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          {image ? (
            <div className={styles.storyMediaFrame}>
              <img className={styles.storyImage} src={resolveImageSrc(image)} alt={image.alt} />
            </div>
          ) : null}
        </div>
      </Container>
    </section>
  )
}

type SalesPdpComparisonProps = {
  config?: ComparisonConfig | ImportComparisonConfig
  configJson?: string
}

export function SalesPdpComparison({ config, configJson }: SalesPdpComparisonProps) {
  const pageSchemaVersion = useContext(SalesPdpSchemaContext)
  const resolvedConfig =
    parseJson<ComparisonConfig | ImportComparisonConfig>(configJson) ?? config ?? salesPdpDefaults.config.comparison

  const importConfig = requireImportSchemaConfig(
    "SalesPdpComparison",
    resolvedConfig,
    isImportComparisonConfig,
    pageSchemaVersion
  )

  if (importConfig) {
    const emberColumn = normalizeImportComparisonColumn(importConfig.emberColumn, "Our approach")
    const competitorColumn = normalizeImportComparisonColumn(importConfig.competitorColumn, "Typical alternative")
    return (
      <section
        id={extractSectionId(importConfig)}
        className={`${styles.sectionPeach} ${styles.sectionPad} ${styles.comparisonSection}`}
      >
        <Container>
          <div style={{ textAlign: "center" }}>
            {importConfig.badgeText ? <div className={styles.sectionBadge}>{importConfig.badgeText}</div> : null}
            <h2 className={styles.sectionHeading}>{importConfig.headline}</h2>
            {importConfig.subheadline ? <div className={styles.comparisonHint}>{importConfig.subheadline}</div> : null}
          </div>

          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th style={{ width: 240 }} />
                  <th>
                    <div>{emberColumn.title}</div>
                    {emberColumn.subtitle ? <div className={styles.importColumnSubtitle}>{emberColumn.subtitle}</div> : null}
                  </th>
                  <th>
                    <div>{competitorColumn.title}</div>
                    {competitorColumn.subtitle ? (
                      <div className={styles.importColumnSubtitle}>{competitorColumn.subtitle}</div>
                    ) : null}
                  </th>
                </tr>
              </thead>
              <tbody>
                {importConfig.rows.map((row) => {
                  const leftValue = row.ember ?? row.left ?? ""
                  const rightValue = row.competitor ?? row.right ?? ""
                  return (
                    <tr key={row.label}>
                      <td className={styles.tableLabel}>{row.label}</td>
                      <td>
                        <div className={styles.cell}>
                          <span className={`${styles.comparisonIcon} ${styles.comparisonIconGood}`} aria-hidden="true">
                            <IconCheck size={12} />
                          </span>
                          {leftValue}
                        </div>
                      </td>
                      <td>
                        <div className={styles.cell}>
                          <span className={`${styles.comparisonIcon} ${styles.comparisonIconBad}`} aria-hidden="true">
                            <IconClose size={12} />
                          </span>
                          {rightValue}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Container>
      </section>
    )
  }

  const legacyConfig = resolvedConfig as ComparisonConfig
  const comparisonTitle = normalizeComparisonTitle(legacyConfig.title, legacyConfig.columns)
  return (
    <section id={legacyConfig.id} className={`${styles.sectionPeach} ${styles.sectionPad} ${styles.comparisonSection}`}>
      <Container>
        <div style={{ textAlign: 'center' }}>
          <div className={styles.sectionBadge}>{legacyConfig.badge}</div>
          <h2 className={styles.sectionHeading}>{comparisonTitle}</h2>
          <div className={styles.comparisonHint}>{legacyConfig.swipeHint}</div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th style={{ width: 240 }} />
                <th>{legacyConfig.columns.pup}</th>
                <th>{legacyConfig.columns.disposable}</th>
              </tr>
            </thead>
            <tbody>
              {legacyConfig.rows.map((r) => (
                <tr key={r.label}>
                  <td className={styles.tableLabel}>{r.label}</td>
                  <td>
                    <div className={styles.cell}>
                      <span className={`${styles.comparisonIcon} ${styles.comparisonIconGood}`} aria-hidden="true">
                        <IconCheck size={12} />
                      </span>
                      {r.pup}
                    </div>
                  </td>
                  <td>
                    <div className={styles.cell}>
                      <span className={`${styles.comparisonIcon} ${styles.comparisonIconBad}`} aria-hidden="true">
                        <IconClose size={12} />
                      </span>
                      {r.disposable}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Container>
    </section>
  )
}

type SalesPdpGuaranteeProps = {
  config?: GuaranteeConfig | ImportGuaranteeConfig
  configJson?: string
  feedImages?: ImageAsset[]
  feedImagesJson?: string
}

export function SalesPdpGuarantee({ config, configJson, feedImages, feedImagesJson }: SalesPdpGuaranteeProps) {
  const pageSchemaVersion = useContext(SalesPdpSchemaContext)
  const resolvedConfig =
    parseJson<GuaranteeConfig | ImportGuaranteeConfig>(configJson) ?? config ?? salesPdpDefaults.config.guarantee
  const defaultFeedImages = salesPdpDefaults.config.reviewWall?.tiles?.map((t) => t.image) ?? []
  const resolvedFeedImages =
    parseJson<ImageAsset[]>(feedImagesJson) ?? feedImages ?? defaultFeedImages
  const isImportSchema = pageSchemaVersion === "import-v1" || isImportGuaranteeConfig(resolvedConfig)
  const importConfig = requireImportSchemaConfig(
    "SalesPdpGuarantee",
    resolvedConfig,
    isImportGuaranteeConfig,
    pageSchemaVersion
  )
  const legacyFallbackImage =
    !isImportSchema && isRecord(resolvedConfig.right) ? readImageAsset(resolvedConfig.right.image) : null

  const guaranteeImages = useMemo(() => {
    if (resolvedFeedImages.length) return resolvedFeedImages
    if (legacyFallbackImage) return [legacyFallbackImage]
    return []
  }, [legacyFallbackImage, resolvedFeedImages])

  const guaranteeFeedColumns = useMemo(() => {
    const left: typeof guaranteeImages = []
    const right: typeof guaranteeImages = []

    guaranteeImages.forEach((img, idx) => {
      ;(idx % 2 === 0 ? left : right).push(img)
    })

    return { left, right }
  }, [guaranteeImages])

  const manualScrollPanelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (isImportSchema) return
    const panel = manualScrollPanelRef.current
    if (!panel) return

    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (media.matches) return

    let rafId = 0
    let lastTime = 0
    let paused = false
    let scrollPos = panel.scrollTop

    const step = (time: number) => {
      if (!lastTime) lastTime = time
      const delta = time - lastTime
      lastTime = time

      if (!paused) {
        const maxScroll = panel.scrollHeight - panel.clientHeight
        if (maxScroll > 0) {
          scrollPos += delta * 0.008
          if (scrollPos >= maxScroll) {
            scrollPos = 0
          }
          panel.scrollTop = scrollPos
        }
      } else {
        scrollPos = panel.scrollTop
      }

      rafId = window.requestAnimationFrame(step)
    }

    const pause = () => {
      paused = true
    }

    const resume = () => {
      paused = false
      lastTime = 0
      scrollPos = panel.scrollTop
    }

    panel.addEventListener('pointerenter', pause)
    panel.addEventListener('pointerleave', resume)
    panel.addEventListener('focusin', pause)
    panel.addEventListener('focusout', resume)
    panel.addEventListener('pointerdown', pause)
    panel.addEventListener('pointerup', resume)

    rafId = window.requestAnimationFrame(step)

    return () => {
      window.cancelAnimationFrame(rafId)
      panel.removeEventListener('pointerenter', pause)
      panel.removeEventListener('pointerleave', resume)
      panel.removeEventListener('focusin', pause)
      panel.removeEventListener('focusout', resume)
      panel.removeEventListener('pointerdown', pause)
      panel.removeEventListener('pointerup', resume)
    }
  }, [isImportSchema])

  if (isImportSchema) {
    if (!importConfig) {
      throw new Error("SalesPdpGuarantee requires import-v1 config when rendering import schema.")
    }
    const bodyParagraphs = toStringList(importConfig.body)
    const stats = normalizeImportMetricList(importConfig.stats)
    const iconImage =
      readImageAsset(importConfig.image) ??
      (importConfig.iconAlt
        ? {
            alt: importConfig.iconAlt,
            src: typeof importConfig.iconSrc === "string" ? importConfig.iconSrc : "",
            assetPublicId: typeof importConfig.iconAssetPublicId === "string" ? importConfig.iconAssetPublicId : undefined,
          }
        : null)
    return (
      <section
        id={extractSectionId(importConfig)}
        className={`${styles.sectionBlue} ${styles.sectionPad} ${styles.guaranteeSection}`}
      >
        <Container className={styles.guaranteeContainer}>
          <div className={styles.guaranteeGrid}>
            <div className={styles.guaranteeText}>
              {importConfig.badgeText ? (
                <div className={styles.sectionBadge} style={{ marginLeft: 0 }}>
                  {importConfig.badgeText}
                </div>
              ) : null}
              <h2>{importConfig.headline}</h2>
              {bodyParagraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </div>

            <div className={styles.importGuaranteePanel}>
              {iconImage ? (
                <div className={styles.importGuaranteeIconWrap}>
                  <img className={styles.importGuaranteeIcon} src={resolveImageSrc(iconImage)} alt={iconImage.alt} />
                </div>
              ) : null}

              {stats.length ? (
                <div className={styles.importMetricGrid}>
                  {stats.map((stat) => (
                    <div key={`${stat.label}-${stat.value}`} className={styles.importMetricCard}>
                      <div className={styles.importMetricValue}>{stat.value}</div>
                      <div className={styles.importMetricLabel}>{stat.label}</div>
                      {stat.detail ? <div className={styles.importMetricDetail}>{stat.detail}</div> : null}
                    </div>
                  ))}
                </div>
              ) : null}

              {importConfig.statsFootnote ? (
                <p className={styles.importSectionFootnote}>{importConfig.statsFootnote}</p>
              ) : null}
            </div>
          </div>
        </Container>
      </section>
    )
  }

  const legacyConfig = resolvedConfig as GuaranteeConfig
  return (
    <section id={legacyConfig.id} className={`${styles.sectionBlue} ${styles.sectionPad} ${styles.guaranteeSection}`}>
      <Container className={styles.guaranteeContainer}>
        <div className={styles.guaranteeGrid}>
          <div className={styles.guaranteeText}>
            <div className={styles.sectionBadge} style={{ marginLeft: 0 }}>
              {legacyConfig.badge}
            </div>
            <h2>{legacyConfig.title}</h2>
            {legacyConfig.paragraphs.map((p) => (
              <p key={p} className={p === 'No hoops. No hassles. No questions.' ? styles.guaranteeBold : undefined}>
                {p}
              </p>
            ))}
            <div className={styles.whyTitle}>{legacyConfig.whyTitle}</div>
            <p>{legacyConfig.whyBody}</p>
            <p className={styles.guaranteeClosing}>{legacyConfig.closingLine}</p>
          </div>

          <div className={styles.manualScrollPanelWrap}>
            <div className={styles.manualScrollHint} aria-hidden="true">
              <IconScrollIndicator size={16} />
              {legacyConfig.right.commentThread.label}
            </div>

            <div
              className={styles.manualScrollPanel}
              aria-label="Customer image feed"
              tabIndex={0}
              ref={manualScrollPanelRef}
            >
              <div className={styles.manualScrollColumn}>
                {guaranteeFeedColumns.left.map((img, idx) => (
                  <div key={`left-${img.src}-${idx}`} className={styles.imageTile}>
                    <img className={styles.panelImg} src={resolveImageSrc(img)} alt={img.alt} />
                  </div>
                ))}
              </div>

              <div className={styles.manualScrollColumn}>
                {guaranteeFeedColumns.right.map((img, idx) => (
                  <div key={`right-${img.src}-${idx}`} className={styles.imageTile}>
                    <img className={styles.panelImg} src={resolveImageSrc(img)} alt={img.alt} />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </Container>
    </section>
  )
}

type SalesPdpFaqProps = {
  config?: FaqConfig
  configJson?: string
}

export function SalesPdpFaq({ config, configJson }: SalesPdpFaqProps) {
  const resolvedConfig = parseJson<FaqConfig>(configJson) ?? config ?? salesPdpDefaults.config.faq
  const sectionId = resolvedConfig.id || resolvedConfig.anchorId
  return (
    <section id={sectionId} className={`${styles.sectionPeach} ${styles.sectionPad}`}>
      <Container>
        <div className={styles.faqWrap}>
          <h2 className={styles.faqHeading}>{resolvedConfig.title || "Frequently Asked Questions"}</h2>
          <FaqAccordion items={resolvedConfig.items} />
        </div>
      </Container>
    </section>
  )
}

type SalesPdpReviewWallProps = {
  config?: ReviewWallConfig | ImportReviewWallConfig
  configJson?: string
  hidden?: boolean
}

export function SalesPdpReviewWall({ config, configJson, hidden }: SalesPdpReviewWallProps) {
  if (hidden) return null
  const pageSchemaVersion = useContext(SalesPdpSchemaContext)
  const resolvedConfig =
    parseJson<ReviewWallConfig | ImportReviewWallConfig>(configJson) ?? config ?? salesPdpDefaults.config.reviewWall

  const importConfig = requireImportSchemaConfig(
    "SalesPdpReviewWall",
    resolvedConfig,
    isImportReviewWallConfig,
    pageSchemaVersion
  )

  if (importConfig) {
    return (
      <section id={extractSectionId(importConfig)} className={`${styles.sectionBlue} ${styles.sectionPad}`}>
        <Container>
          <div className={styles.reviewWallHeader}>
            {importConfig.badgeText ? <div className={styles.sectionBadge}>{importConfig.badgeText}</div> : null}
            <h2 className={styles.sectionHeading} style={{ marginBottom: 10 }}>
              {importConfig.headline}
            </h2>
            {importConfig.body ? <p className={styles.importSectionSubtitle}>{importConfig.body}</p> : null}
          </div>

          <div className={styles.importReviewGrid}>
            {importConfig.reviews.map((review: ImportReviewWallConfig["reviews"][number], index: number) => {
              const image = readImageAsset(review.image)
              const author = review.name ?? review.author
              return (
                <article key={review.id ?? `${author ?? "review"}-${index}`} className={styles.importReviewCard}>
                  <div className={styles.importReviewHeader}>
                    {review.title ? <h3 className={styles.importReviewTitle}>{review.title}</h3> : null}
                    {typeof review.rating === "number" && review.rating > 0 ? (
                      <StarRow rating={Math.max(1, Math.min(5, Math.round(review.rating)))} ariaLabel={`${review.rating} out of 5 stars`} />
                    ) : null}
                  </div>
                  <p className={styles.importReviewBody}>{review.body}</p>
                  {image ? (
                    <div className={styles.importReviewImageWrap}>
                      <img className={styles.importReviewImage} src={resolveImageSrc(image)} alt={image.alt} />
                    </div>
                  ) : null}
                  {author || review.meta ? (
                    <div className={styles.importReviewMeta}>
                      {author ? <span>{author}</span> : null}
                      {review.meta ? <span>{review.meta}</span> : null}
                    </div>
                  ) : null}
                </article>
              )
            })}
          </div>

          {importConfig.ctaLabel ? (
            <button type="button" className={styles.showMore}>
              {importConfig.ctaLabel}
            </button>
          ) : null}
        </Container>
      </section>
    )
  }

  const legacyConfig = resolvedConfig as ReviewWallConfig
  return (
    <section id={legacyConfig.id} className={`${styles.sectionBlue} ${styles.sectionPad}`}>
      <Container>
        <div className={styles.reviewWallHeader}>
          <div className={styles.sectionBadge}>{legacyConfig.badge}</div>
          <h2 className={styles.sectionHeading} style={{ marginBottom: 10 }}>
            {legacyConfig.title}
          </h2>
          <div className={styles.ratingRow}>
            <img
              className={styles.ratingImage}
              src="https://cdn.shopify.com/s/files/1/0433/0510/7612/files/StarRating.svg?v=1754231046"
              alt="5 star rating"
            />
            {legacyConfig.ratingLabel}
          </div>
        </div>

        <div className={styles.masonry}>
          {legacyConfig.tiles.map((t) => (
            <div key={t.id} className={styles.tile}>
              <img src={resolveImageSrc(t.image)} alt={t.image.alt} />
            </div>
          ))}
        </div>

        <button type="button" className={styles.showMore}>
          {legacyConfig.showMoreLabel}
        </button>
      </Container>
    </section>
  )
}

type SalesPdpFooterProps = {
  config?: FooterConfig
  configJson?: string
}

export function SalesPdpFooter({ config, configJson }: SalesPdpFooterProps) {
  const designSystemTokens = useDesignSystemTokens()
  const runtime = useFunnelRuntime()
  const resolvedConfig = parseJson<FooterConfig>(configJson) ?? config ?? salesPdpDefaults.config.footer
  const logoVariant = resolveDesignSystemBrandLogoVariant(resolvedConfig.logoVariant, "onDark")
  const resolvedLogo = useMemo(
    () => withDesignSystemBrandLogo(designSystemTokens, resolvedConfig.logo, logoVariant),
    [designSystemTokens, logoVariant, resolvedConfig.logo]
  )
  const links = useMemo(() => {
    const configuredLinks = Array.isArray(resolvedConfig.links) ? resolvedConfig.links : []
    if (configuredLinks.length > 0 || !runtime?.pageTypeMap) {
      return configuredLinks
    }
    const complianceLinks = [
      { label: "Terms", pageType: "terms_of_service" },
      { label: "Privacy", pageType: "privacy_policy" },
      { label: "Refunds", pageType: "returns_refunds_policy" },
    ] as const
    return complianceLinks.flatMap(({ label, pageType }) => {
      const targetPageId = Object.entries(runtime.pageTypeMap ?? {}).find(([, value]) => value === pageType)?.[0]
      if (!targetPageId) {
        return []
      }
      const targetSlug = runtime.pageMap[targetPageId]
      if (!targetSlug) {
        return []
      }
      return [{ label, href: resolveRuntimePagePath(runtime, targetSlug) }]
    })
  }, [resolvedConfig.links, runtime])
  const paymentIcons = Array.isArray(resolvedConfig.paymentIcons) ? resolvedConfig.paymentIcons : []
  return (
    <footer className={`${styles.sectionPeach} ${styles.footer}`}>
      <Container>
        <img className={styles.footerLogo} src={resolveImageSrc(resolvedLogo)} alt={resolvedLogo.alt} />
        <div className={styles.footerText}>{resolvedConfig.copyright}</div>
        {links.length > 0 ? (
          <nav className={styles.footerLinks} aria-label="Policy links">
            {links.map((link) => {
              const isExternalLink = /^https?:\/\//i.test(link.href)
              return (
                <a
                  key={`${link.label}-${link.href}`}
                  href={link.href}
                  className={styles.footerLink}
                  target={isExternalLink ? "_blank" : undefined}
                  rel={isExternalLink ? "noreferrer noopener" : undefined}
                >
                  {link.label}
                </a>
              )
            })}
          </nav>
        ) : null}
        {paymentIcons.length > 0 ? (
          <PaymentIconStrip iconKeys={paymentIcons} className={styles.footerPaymentIcons} />
        ) : null}
      </Container>
    </footer>
  )
}

type SalesPdpReviewSliderProps = {
  config?: PdpConfig['reviewSlider']
  configJson?: string
}

export function SalesPdpReviewSlider({ config, configJson }: SalesPdpReviewSliderProps) {
  const resolvedConfig =
    parseJson<PdpConfig['reviewSlider']>(configJson) ?? config ?? salesPdpDefaults.config.reviewSlider
  return <ReviewSliderSection config={resolvedConfig} />
}

export function SalesPdpTemplate(props: Props) {
  const resolvedConfig = parseJson<PdpConfig>(props.configJson) ?? props.config ?? salesPdpDefaults.config
  const resolvedCopy = parseJson<UiCopy>(props.copyJson) ?? props.copy ?? salesPdpDefaults.copy
  const resolvedTheme = parseJson<ThemeConfig>(props.themeJson) ?? props.theme ?? salesPdpDefaults.theme
  const reviewWallFeed = resolvedConfig.reviewWall?.tiles?.map((tile) => tile.image) ?? []

  return (
    <SalesPdpPage anchorId="top" theme={resolvedTheme}>
      <>
        <SalesPdpHeader config={resolvedConfig.hero.header} />
        <SalesPdpHero config={resolvedConfig.hero} modals={resolvedConfig.modals} copy={resolvedCopy} />
        <SalesPdpMarquee config={resolvedConfig.marquee} />
        <SalesPdpStoryProblem config={resolvedConfig.story.problem} />
        <SalesPdpStorySolution config={resolvedConfig.story.solution} />
        <SalesPdpComparison config={resolvedConfig.comparison} />
        <SalesPdpGuarantee config={resolvedConfig.guarantee} feedImages={reviewWallFeed} />
        <SalesPdpFaq config={resolvedConfig.faq} />
        <SalesPdpReviewWall config={resolvedConfig.reviewWall} />
        <SalesPdpFooter config={resolvedConfig.footer} />
      </>
    </SalesPdpPage>
  )
}

function StoryText({ section }: { section: PdpConfig['story']['problem'] }) {
  const isProblem = section.id === 'how-it-works'
  return (
    <div className={styles.storyText}>
      <div className={styles.sectionBadge} style={{ marginLeft: 0 }}>
        {section.badge}
      </div>
      <h2 className={styles.storyTitle}>{section.title}</h2>
      {section.paragraphs.map((p, idx) => (
        <p
          key={p}
          className={`${styles.storyPara} ${
            isProblem && (idx === 0 || idx === 2) ? styles.storyParaStrong : ''
          }`}
        >
          {p}
        </p>
      ))}
      {section.emphasisLine ? <div className={styles.storyEmphasis}>{section.emphasisLine}</div> : null}

      {section.bullets?.length ? (
        <div className={styles.bulletList}>
          {section.bullets.map((b) => (
            <div key={b.title} className={styles.bulletItem}>
              <span className={styles.checkCircle} aria-hidden="true" style={{ marginTop: 2 }}>
                <IconCheck size={16} />
              </span>
              <div>
                <span className={styles.bulletItemTitle}>{b.title} </span>
                <span className={styles.bulletItemBody}>{b.body}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function FaqAccordion({ items }: { items: Array<{ question: string; answer: string }> }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  return (
    <div>
      {items.map((it, idx) => {
        const open = openIndex === idx
        return (
          <div key={it.question} className={`${styles.faqCard} ${open ? styles.faqCardOpen : ''}`}>
            <div
              className={styles.faqItem}
              role="button"
              tabIndex={0}
              onClick={() => setOpenIndex(open ? null : idx)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  setOpenIndex(open ? null : idx)
                }
              }}
              aria-expanded={open}
            >
              <div className={styles.faqQ}>{it.question}</div>
              <div aria-hidden="true" style={{ color: 'var(--color-brand)' }}>
                {open ? <IconMinus size={16} /> : <IconPlus size={16} />}
              </div>
            </div>
            <div className={`${styles.faqAnswer} ${open ? styles.faqAnswerOpen : ''}`}>
              <div className={styles.faqA}>{it.answer}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function ReviewSliderSection({ config }: { config: PdpConfig['reviewSlider'] }) {
  if (!config?.toggle?.auto || !config?.toggle?.manual) {
    throw new Error(
      "SalesPdpReviewSlider config.toggle.auto/manual is required. Regenerate the sales page config."
    )
  }
  if (!config?.slides?.length) {
    throw new Error("SalesPdpReviewSlider config.slides must be a non-empty list. Regenerate the sales page config.")
  }
  const [mode, setMode] = useState<'auto' | 'manual'>('auto')
  const panelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const panel = panelRef.current
    if (!panel) return
    if (mode !== 'auto') return

    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (media.matches) return

    let rafId = 0
    let lastTime = 0
    let paused = false

    const step = (time: number) => {
      if (!lastTime) lastTime = time
      const delta = time - lastTime
      lastTime = time

      if (!paused) {
        const maxScroll = panel.scrollHeight - panel.clientHeight
        if (maxScroll > 0) {
          panel.scrollTop += delta * 0.01
          if (panel.scrollTop >= maxScroll) {
            panel.scrollTop = 0
          }
        }
      }

      rafId = window.requestAnimationFrame(step)
    }

    const pause = () => {
      paused = true
    }

    const resume = () => {
      paused = false
      lastTime = 0
    }

    panel.addEventListener('pointerenter', pause)
    panel.addEventListener('pointerleave', resume)
    panel.addEventListener('focusin', pause)
    panel.addEventListener('focusout', resume)
    panel.addEventListener('pointerdown', pause)
    panel.addEventListener('pointerup', resume)

    rafId = window.requestAnimationFrame(step)

    return () => {
      window.cancelAnimationFrame(rafId)
      panel.removeEventListener('pointerenter', pause)
      panel.removeEventListener('pointerleave', resume)
      panel.removeEventListener('focusin', pause)
      panel.removeEventListener('focusout', resume)
      panel.removeEventListener('pointerdown', pause)
      panel.removeEventListener('pointerup', resume)
    }
  }, [mode, config.slides.length])

  return (
    <section id={config.id} className={`${styles.sectionBlue} ${styles.sectionPad}`}>
      <Container>
        <div className={styles.reviewSliderHeader}>
          <h2>{config.title}</h2>
          <p>{config.body}</p>
          <div className={styles.toggle} data-mode={mode} role="tablist" aria-label="Review feed mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'auto'}
              data-active={mode === 'auto'}
              onClick={() => setMode('auto')}
            >
              {config.toggle.auto}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'manual'}
              data-active={mode === 'manual'}
              onClick={() => setMode('manual')}
            >
              {config.toggle.manual}
            </button>
          </div>
        </div>

        <div className={styles.reviewScrollWrap}>
          <div className={styles.reviewScrollHint} aria-hidden="true">
            {config.hint}
          </div>

          <div
            className={styles.reviewScrollPanel}
            aria-label="Customer reviews feed"
            tabIndex={0}
            ref={panelRef}
          >
            <div className={styles.reviewScrollStack}>
              {config.slides.map((slide, idx) => {
                const src = resolveImageSrc(slide)
                if (!src) {
                  throw new Error(
                    `SalesPdpReviewSlider slide ${idx + 1} is missing src/assetPublicId. Regenerate the sales page config.`
                  )
                }
                return (
                  <a
                    key={`${src}-${idx}`}
                    className={styles.reviewTile}
                    href={src}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`Open review image ${idx + 1} in a new tab`}
                  >
                    <img src={src} alt={slide.alt} />
                  </a>
                )
              })}
            </div>
          </div>
        </div>
      </Container>
    </section>
  )
}
