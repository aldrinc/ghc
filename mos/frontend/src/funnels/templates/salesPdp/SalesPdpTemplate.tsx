import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
  MarqueeConfig,
  ModalsConfig,
  OfferOption,
  PdpConfig,
  ReviewWallConfig,
  SizeOption,
  StorySectionConfig,
  VideoItem,
  VideoSectionConfig,
} from "./types";
import defaults from "./defaults.json";
import styles from "./pdpPage.module.css";
import baseStyles from "./salesPdpTemplate.module.css";
import { useDesignSystemTokens } from "@/components/design-system/DesignSystemProvider";
import { useFunnelRuntime } from "@/funnels/puckConfig";

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

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";
const URGENCY_MONTH_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "long",
  timeZone: "UTC",
});

// Keep layout geometry consistent with the base template.
// Brand design systems can still change colors and font families.
const LOCKED_TEMPLATE_CSS_VARS = new Set([
  "--container-max",
  "--container-pad",
  "--marquee-border",
  "--marquee-font-size",
  "--marquee-font-weight",
  "--marquee-gap",
  "--marquee-height",
  "--marquee-letter-spacing",
  "--marquee-pad-x",
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

function resolveAssetSrc(assetPublicId?: string, fallback?: string): string | undefined {
  if (assetPublicId) return `${apiBaseUrl}/public/assets/${assetPublicId}`;
  return fallback;
}

function resolveImageSrc(image?: ImageAsset): string | undefined {
  if (!image) return undefined;
  return resolveAssetSrc(image.assetPublicId, image.src);
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
  return (
    <div className={styles.header} aria-hidden={!visible}>
      <Container className={styles.headerContainer}>
        <div className={`${styles.headerInner} ${visible ? styles.headerVisible : styles.headerHidden}`}>
          <a className={styles.logo} href={config.logo.href ?? '#top'}>
            <img className={styles.logoImg} src={resolveImageSrc(config.logo)} alt={config.logo.alt} />
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

          <a className={styles.headerCta} href={config.cta.href}>
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
  watchLabel,
  freeGifts,
  onFreeGiftsClick,
}: {
  slides: PdpConfig['hero']['gallery']['slides']
  watchLabel: string
  freeGifts?: PdpConfig['hero']['gallery']['freeGifts']
  onFreeGiftsClick?: () => void
}) {
  const [index, setIndex] = useState(0)
  const active = slides[index]

  return (
    <div className={styles.galleryCard}>
      <div className={styles.galleryMain}>
        <img src={resolveImageSrc(active)} alt={active.alt} />

        {freeGifts && index === 0 ? (
          <button
            type="button"
            className={styles.giftOverlay}
            onClick={onFreeGiftsClick}
            aria-label={freeGifts.ctaLabel}
          >
            <img
              className={styles.giftOverlayIcon}
              src={resolveImageSrc(freeGifts.icon)}
              alt={freeGifts.icon.alt}
            />
            <div className={styles.giftOverlayText}>
              <p className={styles.giftOverlayTitle}>{freeGifts.title}</p>
              <p className={styles.giftOverlayBody}>{freeGifts.body}</p>
            </div>
          </button>
        ) : null}

        <button type="button" className={styles.watchButton}>
          {watchLabel}
          <span className={styles.watchPlay} aria-hidden="true">
            <IconPlayTriangle size={10} />
          </span>
        </button>
      </div>

      <div className={styles.galleryControls}>
        <button
          type="button"
          className={styles.circleIconBtn}
          onClick={() => setIndex((v) => clampIndex(v - 1, slides.length))}
          aria-label="Previous image"
        >
          <IconArrow dir="left" size={18} />
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
          <IconArrow dir="right" size={18} />
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

      <img className={styles.offerCardImage} src={resolveImageSrc(option.image)} alt={option.image.alt} />
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
  theme?: ThemeConfig
  themeJson?: string
  content?: (props?: Record<string, unknown>) => ReactNode
  children?: ReactNode
}

export function SalesPdpPage({ anchorId, theme, themeJson, content, children }: SalesPdpPageProps) {
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
      for (const [rawKey, rawValue] of Object.entries(resolvedTheme.tokens)) {
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
    <div
      className={`${baseStyles.root} ${styles.page}`}
      id={resolvedAnchorId}
      data-theme={explicitTheme?.dataTheme ?? designSystemTokens?.dataTheme ?? resolvedTheme?.dataTheme}
      style={themeStyle}
    >
      {body}
    </div>
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

    const obs = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (!entry) return
        const pastTrigger = entry.isIntersecting || entry.boundingClientRect.top < 0
        setShowHeader(pastTrigger)
      },
      { threshold: 0 }
    )

    obs.observe(el)
    return () => obs.disconnect()
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
  const resolvedHero = parseJson<HeroConfig>(configJson) ?? config ?? salesPdpDefaults.config.hero
  const resolvedModals = parseJson<ModalsConfig>(modalsJson) ?? modals ?? salesPdpDefaults.config.modals
  const resolvedCopy = parseJson<UiCopy>(copyJson) ?? copy ?? salesPdpDefaults.copy

  const sizeOptions = resolvedHero.purchase.size.options
  const colorOptions = resolvedHero.purchase.color.options
  const offerOptions = resolvedHero.purchase.offer.options

  const [selectedSize, setSelectedSize] = useState(sizeOptions[0]?.id)
  const [selectedColor, setSelectedColor] = useState(colorOptions[0]?.id)
  const [selectedOffer, setSelectedOffer] = useState(offerOptions[1]?.id ?? offerOptions[0]?.id)

  const [openPillIndex, setOpenPillIndex] = useState<number | null>(null)
  const [isPillDragging, setIsPillDragging] = useState(false)
  const pillViewportRef = useRef<HTMLDivElement | null>(null)
  const pillDragState = useRef({
    pointerDown: false,
    dragging: false,
    startX: 0,
    startY: 0,
    scrollLeft: 0,
    wasDragged: false,
  })

  const [openSizeChart, setOpenSizeChart] = useState(false)
  const [openWhyBundle, setOpenWhyBundle] = useState(false)
  const [openFreeGifts, setOpenFreeGifts] = useState(false)
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  const [isCheckingOut, setIsCheckingOut] = useState(false)

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
      sizeId: selectedSizeObj?.id,
      colorId: selectedColorObj?.id,
      offerId: selectedOfferObj?.id,
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
      runtime.trackEvent?.({ eventType: "cta_click", props: { variantId: variant.id } });
      const response = await fetch(`${apiBaseUrl}/public/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          funnelSlug: runtime.funnelSlug,
          variantId: variant.id,
          selection,
          quantity: 1,
          successUrl: `${window.location.origin}${window.location.pathname}?checkout=success`,
          cancelUrl: `${window.location.origin}${window.location.pathname}?checkout=cancel`,
          pageId: runtime.pageId || undefined,
          visitorId: runtime.visitorId || undefined,
          sessionId: runtime.sessionId || undefined,
          utm: getUtmParams(),
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
      window.location.href = data.checkoutUrl as string;
    } catch (err) {
      setCheckoutError(err instanceof Error ? err.message : "Checkout failed.");
    } finally {
      setIsCheckingOut(false);
    }
  }

  const handlePillPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
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
    setOpenPillIndex(idx)
  }

  return (
    <>
      <section className={`${styles.sectionPeach} ${styles.heroSection}`}>
        <Container>
          <div className={styles.heroGrid}>
            <div>
              <Gallery
                slides={resolvedHero.gallery.slides}
                watchLabel={resolvedHero.gallery.watchInAction.label}
                freeGifts={resolvedHero.gallery.freeGifts}
                onFreeGiftsClick={() => setOpenFreeGifts(true)}
              />
            </div>

            <div>
              {/*
                Auto-sliding FAQ pills (marquee-style)
                - Continuously scrolls horizontally like the marquee band.
                - Pauses on hover/focus and when an answer is open.
                - Clicking a pill always opens the answer panel.
              */}
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

	              {/* Size */}
	              <div>
	                <div className={styles.sectionTitleRow}>
	                  <div className={styles.stepTitle}>{resolvedHero.purchase.size.title}</div>
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

              <div className={styles.divider} />

	              {/* Color */}
	              <div>
	                <div className={styles.sectionTitleRow}>
	                  <div className={styles.stepTitle}>{resolvedHero.purchase.color.title}</div>
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

              <div className={styles.divider} />

	              {/* Offer */}
	              <div>
	                <div className={styles.sectionTitleRow}>
	                  <div className={styles.stepTitle}>{resolvedHero.purchase.offer.title}</div>
	                </div>
	                <div className={styles.offerHelper}>
	                  {resolvedHero.purchase.offer.helperText}{' '}
	                  <button type="button" className={styles.seeWhy} onClick={() => setOpenWhyBundle(true)}>
	                    {resolvedHero.purchase.offer.seeWhyLabel}
                  </button>
                </div>

	                <div className={styles.offerGrid}>
	                  {offerOptions.map((o) => (
	                    <OfferCard
	                      key={o.id}
	                      option={o}
	                      selected={o.id === selectedOffer}
                      onClick={() => setSelectedOffer(o.id)}
                    />
                  ))}
                </div>

	                <button type="button" className={styles.ctaButton} onClick={handleCheckout} disabled={isCheckingOut}>
	                  {isCheckingOut ? "Starting checkout…" : ctaLabel}
	                  <span className={styles.ctaIconCircle} aria-hidden="true">
	                    <IconArrow dir="right" size={24} />
	                  </span>
	                </button>
                {checkoutError ? (
                  <div className={styles.stockNotice} role="alert">
                    {checkoutError}
                  </div>
                ) : null}

	                <div className={styles.ctaSubBullets}>
	                  {resolvedHero.purchase.cta.subBullets.map((t) => (
	                    <span key={t}>
	                      <span className={styles.checkCircle} aria-hidden="true">
	                        <IconCheck size={18} />
	                      </span>
	                      {t}
	                    </span>
	                  ))}
	                </div>

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
                          r.tone === 'highlight'
                            ? styles.urgencyRowHighlight
                            : r.tone === 'muted'
                              ? styles.urgencyRowMuted
                              : ''
                        }`}
                      >
                        <span>{r.label}</span>
                        <span>{r.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
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

      <Modal
        open={openFreeGifts}
        onClose={() => setOpenFreeGifts(false)}
        ariaLabel={resolvedModals.freeGifts.title}
        copy={resolvedCopy.modal}
      >
        <h2 style={{ marginTop: 0 }}>{resolvedModals.freeGifts.title}</h2>
        <p style={{ color: 'var(--pdp-black-70)' }}>{resolvedModals.freeGifts.body}</p>
      </Modal>
    </>
  )
}

type SalesPdpVideosProps = {
  config?: VideoSectionConfig
  configJson?: string
}

export function SalesPdpVideos({ config, configJson }: SalesPdpVideosProps) {
  const resolvedConfig = parseJson<VideoSectionConfig>(configJson) ?? config ?? salesPdpDefaults.config.videos

  return (
    <section className={`${styles.sectionBlue} ${styles.sectionPad}`}>
      <Container>
        <div style={{ textAlign: 'center' }}>
          <div className={styles.sectionBadge}>{resolvedConfig.badge}</div>
          <h2 className={styles.sectionHeading}>{resolvedConfig.title}</h2>
        </div>
        <VideoGrid videos={resolvedConfig.videos} />
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
  config?: StorySectionConfig
  configJson?: string
}

type SalesPdpStorySolutionProps = {
  config?: StorySectionConfig & { callout: CalloutConfig }
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
              <img className={styles.storyImage} src={resolveImageSrc(section.image)} alt={section.image.alt} />
              <StoryText section={section} />
            </>
          ) : (
            <>
              <StoryText section={section} />
              <img className={styles.storyImage} src={resolveImageSrc(section.image)} alt={section.image.alt} />
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
  const resolvedConfig = parseJson<StorySectionConfig>(configJson) ?? config ?? salesPdpDefaults.config.story.problem
  return <SalesPdpStorySection section={resolvedConfig} />
}

export function SalesPdpStorySolution({ config, configJson }: SalesPdpStorySolutionProps) {
  const resolvedConfig =
    parseJson<StorySectionConfig & { callout: CalloutConfig }>(configJson) ??
    config ??
    salesPdpDefaults.config.story.solution
  return (
    <SalesPdpStorySection
      section={resolvedConfig}
      callout={resolvedConfig.callout}
      className={styles.solutionSection}
    />
  )
}

type SalesPdpComparisonProps = {
  config?: ComparisonConfig
  configJson?: string
}

export function SalesPdpComparison({ config, configJson }: SalesPdpComparisonProps) {
  const resolvedConfig = parseJson<ComparisonConfig>(configJson) ?? config ?? salesPdpDefaults.config.comparison
  return (
    <section id={resolvedConfig.id} className={`${styles.sectionPeach} ${styles.sectionPad}`}>
      <Container>
        <div style={{ textAlign: 'center' }}>
          <div className={styles.sectionBadge}>{resolvedConfig.badge}</div>
          <h2 className={styles.sectionHeading}>{resolvedConfig.title}</h2>
          <div className={styles.comparisonHint}>{resolvedConfig.swipeHint}</div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th style={{ width: 240 }} />
                <th>{resolvedConfig.columns.pup}</th>
                <th>{resolvedConfig.columns.disposable}</th>
              </tr>
            </thead>
            <tbody>
              {resolvedConfig.rows.map((r) => (
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
  config?: GuaranteeConfig
  configJson?: string
  feedImages?: ImageAsset[]
  feedImagesJson?: string
}

export function SalesPdpGuarantee({ config, configJson, feedImages, feedImagesJson }: SalesPdpGuaranteeProps) {
  const resolvedConfig = parseJson<GuaranteeConfig>(configJson) ?? config ?? salesPdpDefaults.config.guarantee
  const defaultFeedImages = salesPdpDefaults.config.reviewWall?.tiles?.map((t) => t.image) ?? []
  const resolvedFeedImages =
    parseJson<ImageAsset[]>(feedImagesJson) ?? feedImages ?? defaultFeedImages

  const guaranteeImages = useMemo(() => {
    if (resolvedFeedImages.length) return resolvedFeedImages
    return [resolvedConfig.right.image]
  }, [resolvedFeedImages, resolvedConfig.right.image])

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
          // Use a separate accumulator so sub-pixel deltas still make progress on browsers
          // that quantize `scrollTop` to whole pixels.
          scrollPos += delta * 0.008
          if (scrollPos >= maxScroll) {
            scrollPos = 0
          }
          panel.scrollTop = scrollPos
        }
      } else {
        // Keep the accumulator aligned with manual scrolling while paused.
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
  }, [])

  return (
    <section id={resolvedConfig.id} className={`${styles.sectionBlue} ${styles.sectionPad} ${styles.guaranteeSection}`}>
      <Container className={styles.guaranteeContainer}>
        <div className={styles.guaranteeGrid}>
          <div className={styles.guaranteeText}>
            <div className={styles.sectionBadge} style={{ marginLeft: 0 }}>
              {resolvedConfig.badge}
            </div>
            <h2>{resolvedConfig.title}</h2>
            {resolvedConfig.paragraphs.map((p) => (
              <p key={p} className={p === 'No hoops. No hassles. No questions.' ? styles.guaranteeBold : undefined}>
                {p}
              </p>
            ))}
            <div className={styles.whyTitle}>{resolvedConfig.whyTitle}</div>
            <p>{resolvedConfig.whyBody}</p>
            <p className={styles.guaranteeClosing}>{resolvedConfig.closingLine}</p>
          </div>

          <div className={styles.manualScrollPanelWrap}>
            <div className={styles.manualScrollHint} aria-hidden="true">
              <IconScrollIndicator size={16} />
              {resolvedConfig.right.commentThread.label}
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
  return (
    <section id={resolvedConfig.id} className={`${styles.sectionPeach} ${styles.sectionPad}`}>
      <Container>
        <div className={styles.faqWrap}>
          <h2 className={styles.faqHeading}>{resolvedConfig.title}</h2>
          <FaqAccordion items={resolvedConfig.items} />
        </div>
      </Container>
    </section>
  )
}

type SalesPdpReviewWallProps = {
  config?: ReviewWallConfig
  configJson?: string
  hidden?: boolean
}

export function SalesPdpReviewWall({ config, configJson, hidden }: SalesPdpReviewWallProps) {
  if (hidden) return null
  const resolvedConfig = parseJson<ReviewWallConfig>(configJson) ?? config ?? salesPdpDefaults.config.reviewWall
  return (
    <section id={resolvedConfig.id} className={`${styles.sectionBlue} ${styles.sectionPad}`}>
      <Container>
        <div className={styles.reviewWallHeader}>
          <div className={styles.sectionBadge}>{resolvedConfig.badge}</div>
          <h2 className={styles.sectionHeading} style={{ marginBottom: 10 }}>
            {resolvedConfig.title}
          </h2>
          <div className={styles.ratingRow}>
            <img
              className={styles.ratingImage}
              src="https://cdn.shopify.com/s/files/1/0433/0510/7612/files/StarRating.svg?v=1754231046"
              alt="5 star rating"
            />
            {resolvedConfig.ratingLabel}
          </div>
        </div>

        <div className={styles.masonry}>
          {resolvedConfig.tiles.map((t) => (
            <div key={t.id} className={styles.tile}>
              <img src={resolveImageSrc(t.image)} alt={t.image.alt} />
            </div>
          ))}
        </div>

        <button type="button" className={styles.showMore}>
          {resolvedConfig.showMoreLabel}
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
  const resolvedConfig = parseJson<FooterConfig>(configJson) ?? config ?? salesPdpDefaults.config.footer
  return (
    <footer className={`${styles.sectionPeach} ${styles.footer}`}>
      <Container>
        <img className={styles.footerLogo} src={resolveImageSrc(resolvedConfig.logo)} alt={resolvedConfig.logo.alt} />
        <div className={styles.footerText}>{resolvedConfig.copyright}</div>
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
        <SalesPdpVideos config={resolvedConfig.videos} />
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
