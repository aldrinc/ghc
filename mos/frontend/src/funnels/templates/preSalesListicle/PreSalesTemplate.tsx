import {
  Children,
  createContext,
  isValidElement,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import { useDesignSystemTokens } from "@/components/design-system/DesignSystemProvider";
import { BadgeRow } from "./components/BadgeRow/BadgeRow";
import { Container } from "./components/Container/Container";
import { FloatingCta } from "./components/FloatingCta/FloatingCta";
import { Footer } from "./components/Footer/Footer";
import { Hero } from "./components/Hero/Hero";
import { Marquee } from "./components/Marquee/Marquee";
import { Modal } from "./components/Modal/Modal";
import { Pitch } from "./components/Pitch/Pitch";
import { Reasons } from "./components/Reasons/Reasons";
import { ReviewWall } from "./components/ReviewWall/ReviewWall";
import { Reviews } from "./components/Reviews/Reviews";
import type { ListicleConfig } from "./types";
import type { ThemeConfig, UiCopy } from "./siteTypes";
import defaults from "./defaults.json";
import baseStyles from "./preSalesTemplate.module.css";
import { useTemplateFonts } from "@/funnels/templates/templateFonts";

export const preSalesDefaults = defaults as {
  config: ListicleConfig;
  copy: UiCopy;
  theme?: ThemeConfig;
};

const PRE_SALES_REVIEW_COUNT_MIN = 12;
const PRE_SALES_REVIEW_COUNT_MAX = 15000;

type PreSalesSocialProof = {
  reviewCount: number;
  reviewTitle: string;
};

const PreSalesSocialProofContext = createContext<PreSalesSocialProof | null>(null);

function parsePreSalesReviewCount(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    const normalized = Math.round(value);
    if (normalized >= PRE_SALES_REVIEW_COUNT_MIN && normalized <= PRE_SALES_REVIEW_COUNT_MAX) {
      return normalized;
    }
  }
  if (typeof value !== "string") return null;
  const match = value.match(/\b([\d,]{2,})\b/);
  if (!match) return null;
  const normalized = Number.parseInt(match[1].replace(/,/g, ""), 10);
  if (!Number.isFinite(normalized)) return null;
  if (normalized < PRE_SALES_REVIEW_COUNT_MIN || normalized > PRE_SALES_REVIEW_COUNT_MAX) return null;
  return normalized;
}

function formatPreSalesReviewTitle(count: number): string {
  return `Over ${count.toLocaleString()} — 5 Star Reviews`;
}

function derivePreSalesReviewCount(seedSource: string): number {
  let hash = 2166136261;
  for (let i = 0; i < seedSource.length; i += 1) {
    hash ^= seedSource.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  const span = PRE_SALES_REVIEW_COUNT_MAX - PRE_SALES_REVIEW_COUNT_MIN + 1;
  return PRE_SALES_REVIEW_COUNT_MIN + ((hash >>> 0) % span);
}

function buildPreSalesReviewSeed(anchorId: string): string {
  const seedParts: string[] = [];
  if (typeof window !== "undefined" && window.location.pathname) seedParts.push(window.location.pathname);
  if (typeof document !== "undefined" && document.title) seedParts.push(document.title);
  if (anchorId) seedParts.push(anchorId);
  return seedParts.join("::") || "pre-sales-listicle";
}

function extractPreSalesReviewCountFromNode(node: ReactNode): number | null {
  let resolved: number | null = null;

  function visit(current: ReactNode): void {
    if (resolved !== null) return;
    Children.forEach(current, (child) => {
      if (resolved !== null || !isValidElement(child)) return;
      const props = child.props as Record<string, unknown>;
      const config = props.config;
      if (config && typeof config === "object" && !Array.isArray(config)) {
        const configRecord = config as Record<string, unknown>;
        const titleCount = parsePreSalesReviewCount(configRecord.title);
        if (titleCount !== null) {
          resolved = titleCount;
          return;
        }
        const badges = configRecord.badges;
        if (Array.isArray(badges) && badges.length > 0) {
          const firstBadge = badges[0];
          if (firstBadge && typeof firstBadge === "object" && !Array.isArray(firstBadge)) {
            const badgeCount = parsePreSalesReviewCount((firstBadge as Record<string, unknown>).value);
            if (badgeCount !== null) {
              resolved = badgeCount;
              return;
            }
          }
        }
      }
      if (props.children !== undefined) visit(props.children as ReactNode);
    });
  }

  visit(node);
  return resolved;
}

function useResolvedPreSalesSocialProof(): PreSalesSocialProof {
  const contextValue = useContext(PreSalesSocialProofContext);
  if (contextValue) return contextValue;
  const reviewCount = derivePreSalesReviewCount(buildPreSalesReviewSeed("top"));
  return {
    reviewCount,
    reviewTitle: formatPreSalesReviewTitle(reviewCount),
  };
}

function normalizePreSalesBadges(
  badges: ListicleConfig["badges"],
  reviewCount: number,
): ListicleConfig["badges"] {
  const standards = [
    {
      value: reviewCount.toLocaleString(),
      label: "5-Star Reviews",
      iconAlt: "5 star reviews",
    },
    {
      value: "24/7",
      label: "Customer Support",
      iconAlt: "24/7 customer support",
    },
    {
      value: undefined,
      label: "Risk Free Trial",
      iconAlt: "Risk free trial",
    },
  ] as const;

  return badges.slice(0, standards.length).map((badge, index) => {
    const standard = standards[index];
    const normalized = {
      ...badge,
      label: standard.label,
      iconAlt: standard.iconAlt,
    };
    if (standard.value) {
      return { ...normalized, value: standard.value };
    }
    const { value: _unusedValue, ...rest } = normalized;
    return rest;
  });
}

type Props = {
  id?: string;
  config?: ListicleConfig;
  copy?: UiCopy;
  theme?: ThemeConfig;
  configJson?: string;
  copyJson?: string;
  themeJson?: string;
};

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
  "--heading-size",
  "--heading-size-mobile",
  "--hero-min-height",
  "--hero-min-height-mobile",
  "--hero-pad-x",
  "--hero-pad-y",
  "--hero-copy-pad-right",
  "--hero-title-max",
  "--hero-title-line",
  "--hero-subtitle-max",
  "--hero-media-frame-size",
  "--hero-media-frame-size-mobile",
  "--hero-title-size",
  "--hero-subtitle-size",
  "--hero-subtitle-line",
  "--hero-subtitle-gap",
  "--badge-strip-pad-y",
  "--badge-strip-gap",
  "--badge-icon-size",
  "--badge-value-size",
  "--badge-label-size",
  "--badge-text-size",
  "--listicle-card-gap",
  "--listicle-card-radius",
  "--listicle-card-border",
  "--listicle-media-width",
  "--listicle-media-min-height",
  "--listicle-media-min-height-mobile",
  "--listicle-media-frame-height",
  "--listicle-media-frame-height-mobile",
  "--listicle-media-max-width",
  "--listicle-media-max-height",
  "--listicle-content-pad-x",
  "--listicle-content-pad-y",
  "--listicle-content-pad-x-mobile",
  "--listicle-content-pad-y-mobile",
  "--listicle-number-size",
  "--listicle-number-offset",
  "--listicle-number-font-size",
  "--listicle-title-font",
  "--listicle-title-size",
  "--listicle-title-size-mobile",
  "--listicle-title-color",
  "--listicle-title-margin-bottom",
  "--listicle-body-size",
  "--listicle-body-line",
  "--listicle-body-gap",
  "--reviews-height",
  "--reviews-card-width",
  "--reviews-card-pad",
  "--reviews-card-radius",
  "--marquee-border",
  "--marquee-font-size",
  "--marquee-font-weight",
  "--marquee-gap",
  "--marquee-height",
  "--marquee-letter-spacing",
  "--marquee-pad-y",
  "--marquee-pad-x",
  "--pitch-pad-y",
  "--pitch-gap",
  "--pitch-content-max",
  "--pitch-title-size",
  "--pitch-bullets-top",
  "--pitch-bullets-bottom",
  "--pitch-bullet-gap",
  "--pitch-bullet-size",
  "--pitch-bullet-line",
  "--pitch-check-size",
  "--pitch-check-gap",
  "--pitch-media-max",
  "--pitch-media-frame-height",
  "--pitch-media-frame-height-mobile",
  "--pitch-media-image-max-width",
  "--pitch-media-image-max-height",
  "--wall-pad-y",
  "--wall-pad-top",
  "--wall-height",
  "--wall-gap",
  "--wall-pad-x",
  "--wall-fade-height",
  "--footer-pad-y",
  "--footer-logo-height",
  "--footer-gap",
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

function parseJsonMaybeNested(raw?: string): unknown | null {
  const parsed = parseJson<unknown>(raw);
  if (typeof parsed !== "string") return parsed;
  const trimmed = parsed.trim();
  if (!trimmed) return parsed;
  const looksLikeJson =
    (trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"));
  if (!looksLikeJson) return parsed;
  return parseJson<unknown>(trimmed) ?? parsed;
}

function coerceJsonProp(value: unknown): unknown {
  if (typeof value !== "string") return value;
  return parseJsonMaybeNested(value) ?? value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function describeValue(value: unknown): string {
  if (value === null) return "null";
  if (value === undefined) return "undefined";
  if (Array.isArray(value)) return `array(len=${value.length})`;
  if (typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>).slice(0, 12);
    return `object(keys=${keys.join(",")}${keys.length === 12 ? ",…" : ""})`;
  }
  return `${typeof value}(${String(value).slice(0, 120)})`;
}

function invariant(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function resolveCopy(copy?: UiCopy, copyJson?: string): UiCopy {
  const base = preSalesDefaults.copy;
  const parsed = parseJson<UiCopy>(copyJson);
  const candidate = parsed ?? copy;
  if (!candidate) return base;

  return {
    ...base,
    ...candidate,
    common: { ...base.common, ...(candidate.common ?? {}) },
    modal: { ...base.modal, ...(candidate.modal ?? {}) },
    reviews: { ...base.reviews, ...(candidate.reviews ?? {}) },
    reviewWall: { ...base.reviewWall, ...(candidate.reviewWall ?? {}) },
  };
}

type HeroSectionConfig = {
  hero: ListicleConfig["hero"];
  badges: ListicleConfig["badges"];
};

function isHeroSectionConfig(value: unknown): value is HeroSectionConfig {
  if (!isRecord(value)) return false;
  const hero = value.hero;
  if (!isRecord(hero)) return false;
  if (typeof hero.title !== "string") return false;
  if (typeof hero.subtitle !== "string") return false;
  return Array.isArray(value.badges);
}

type PreSalesPageProps = {
  anchorId?: string;
  theme?: ThemeConfig;
  themeJson?: string;
  content?: (props?: Record<string, unknown>) => ReactNode;
  children?: ReactNode;
};

export function PreSalesPage({ anchorId, theme, themeJson, content, children }: PreSalesPageProps) {
  useTemplateFonts();
  const designSystemTokens = useDesignSystemTokens() as { cssVars?: Record<string, string | number>; dataTheme?: string } | null;
  const themeFromJson = parseJson<ThemeConfig>(themeJson);
  const defaultTheme = preSalesDefaults.theme;
  const themeIsDefault =
    theme && defaultTheme ? JSON.stringify(theme) === JSON.stringify(defaultTheme) : Boolean(!theme && defaultTheme);
  const explicitTheme = themeFromJson ?? (theme && !themeIsDefault ? theme : undefined);
  const resolvedTheme = explicitTheme ?? defaultTheme;
  const themeStyle = useMemo(() => {
    const style: Record<string, string> = {};
    if (defaultTheme?.tokens) {
      for (const [rawKey, rawValue] of Object.entries(defaultTheme.tokens)) {
        if (rawValue === undefined || rawValue === null) continue;
        style[toCssVarName(rawKey)] = String(rawValue);
      }
    }
    if (designSystemTokens?.cssVars) {
      for (const [rawKey, rawValue] of Object.entries(designSystemTokens.cssVars)) {
        if (rawValue === undefined || rawValue === null) continue;
        const cssVarName = toCssVarName(rawKey);
        if (LOCKED_TEMPLATE_CSS_VARS.has(cssVarName)) continue;
        style[cssVarName] = String(rawValue);
      }
    }
    if (explicitTheme?.tokens) {
      for (const [rawKey, rawValue] of Object.entries(resolvedTheme.tokens ?? {})) {
        if (rawValue === undefined || rawValue === null) continue;
        const cssVarName = toCssVarName(rawKey);
        if (LOCKED_TEMPLATE_CSS_VARS.has(cssVarName)) continue;
        style[cssVarName] = String(rawValue);
      }
    }
    return style;
  }, [defaultTheme, designSystemTokens, explicitTheme, resolvedTheme]);

  const resolvedAnchorId = anchorId && anchorId.trim() ? anchorId : "top";
  const body = content ? content({}) : children;
  const socialProof = useMemo<PreSalesSocialProof>(() => {
    const explicitCount = extractPreSalesReviewCountFromNode(body);
    const reviewCount = explicitCount ?? derivePreSalesReviewCount(buildPreSalesReviewSeed(resolvedAnchorId));
    return {
      reviewCount,
      reviewTitle: formatPreSalesReviewTitle(reviewCount),
    };
  }, [body, resolvedAnchorId]);

  return (
    <PreSalesSocialProofContext.Provider value={socialProof}>
      <div
        className={baseStyles.root}
        id={resolvedAnchorId}
        data-theme={explicitTheme?.dataTheme ?? designSystemTokens?.dataTheme ?? resolvedTheme?.dataTheme}
        style={themeStyle}
      >
        {body}
      </div>
    </PreSalesSocialProofContext.Provider>
  );
}

type PreSalesHeroProps = {
  config?: HeroSectionConfig;
  configJson?: string;
};

export function PreSalesHero({ config, configJson }: PreSalesHeroProps) {
  const parsed = parseJsonMaybeNested(configJson);
  if (parsed !== null) {
    invariant(
      isHeroSectionConfig(parsed),
      `PreSalesHero.configJson must be a JSON object like { hero: { title, subtitle, media? }, badges: [] }. Received ${describeValue(parsed)}.`
    );
  }
  const coercedConfig = coerceJsonProp(config);
  const resolvedConfig =
    (parsed as HeroSectionConfig | null) ??
    (coercedConfig as HeroSectionConfig | undefined) ??
    ({
      hero: preSalesDefaults.config.hero,
      badges: preSalesDefaults.config.badges,
    } satisfies HeroSectionConfig);
  invariant(
    isHeroSectionConfig(resolvedConfig),
    `PreSalesHero.config must be an object like { hero: { title, subtitle, media? }, badges: [] }. Received ${describeValue(resolvedConfig)}.`
  );
  const socialProof = useResolvedPreSalesSocialProof();
  const normalizedBadges = useMemo(
    () => normalizePreSalesBadges(resolvedConfig.badges, socialProof.reviewCount),
    [resolvedConfig.badges, socialProof.reviewCount]
  );

  return (
    <Hero
      title={resolvedConfig.hero.title}
      subtitle={resolvedConfig.hero.subtitle}
      media={resolvedConfig.hero.media}
      badges={normalizedBadges}
    />
  );
}

type PreSalesReasonsProps = {
  config?: ListicleConfig["reasons"];
  configJson?: string;
};

export function PreSalesReasons({ config, configJson }: PreSalesReasonsProps) {
  const parsed = parseJsonMaybeNested(configJson);
  if (parsed !== null) {
    invariant(
      Array.isArray(parsed),
      `PreSalesReasons.configJson must be a JSON array of reasons. Received ${describeValue(parsed)}.`
    );
  }
  const coercedConfig = coerceJsonProp(config);
  const resolvedConfig =
    (parsed as ListicleConfig["reasons"] | null) ??
    (coercedConfig as ListicleConfig["reasons"] | undefined) ??
    preSalesDefaults.config.reasons;
  invariant(
    Array.isArray(resolvedConfig),
    `PreSalesReasons.config must be an array of reasons. Received ${describeValue(resolvedConfig)}.`
  );
  return <Reasons reasons={resolvedConfig} />;
}

type PreSalesReviewsProps = {
  config?: ListicleConfig["reviews"];
  configJson?: string;
  copy?: UiCopy;
  copyJson?: string;
};

export function PreSalesReviews({ config, configJson, copy, copyJson }: PreSalesReviewsProps) {
  const parsed = parseJsonMaybeNested(configJson);
  if (parsed !== null) {
    invariant(
      isRecord(parsed) && Array.isArray(parsed.slides),
      `PreSalesReviews.configJson must be a JSON object like { slides: [] }. Received ${describeValue(parsed)}.`
    );
  }
  const coercedConfig = coerceJsonProp(config);
  const resolvedConfig =
    (parsed as ListicleConfig["reviews"] | null) ??
    (coercedConfig as ListicleConfig["reviews"] | undefined) ??
    preSalesDefaults.config.reviews;
  invariant(
    isRecord(resolvedConfig) && Array.isArray(resolvedConfig.slides),
    `PreSalesReviews.config must be an object like { slides: [] }. Received ${describeValue(resolvedConfig)}.`
  );
  const resolvedCopy = resolveCopy(copy, copyJson);
  return (
    <Reviews
      reviews={resolvedConfig}
      copy={resolvedCopy.reviews}
      starsAriaLabelTemplate={resolvedCopy.common.starsAriaLabelTemplate}
    />
  );
}

type PreSalesMarqueeProps = {
  config?: ListicleConfig["marquee"];
  configJson?: string;
};

export function PreSalesMarquee({ config, configJson }: PreSalesMarqueeProps) {
  const parsed = parseJsonMaybeNested(configJson);
  if (parsed !== null) {
    invariant(
      Array.isArray(parsed),
      `PreSalesMarquee.configJson must be a JSON array of strings. Received ${describeValue(parsed)}.`
    );
  }
  const coercedConfig = coerceJsonProp(config);
  const resolvedConfig =
    (parsed as ListicleConfig["marquee"] | null) ??
    (coercedConfig as ListicleConfig["marquee"] | undefined) ??
    preSalesDefaults.config.marquee;
  invariant(
    Array.isArray(resolvedConfig),
    `PreSalesMarquee.config must be an array of strings. Received ${describeValue(resolvedConfig)}.`
  );
  return <Marquee items={resolvedConfig} />;
}

type PreSalesPitchProps = {
  config?: ListicleConfig["pitch"];
  configJson?: string;
};

export function PreSalesPitch({ config, configJson }: PreSalesPitchProps) {
  const parsed = parseJsonMaybeNested(configJson);
  if (parsed !== null) {
    invariant(
      isRecord(parsed) && typeof parsed.title === "string" && Array.isArray(parsed.bullets) && isRecord(parsed.image),
      `PreSalesPitch.configJson must be a JSON object like { title: string, bullets: string[], image: {...} }. Received ${describeValue(parsed)}.`
    );
  }
  const coercedConfig = coerceJsonProp(config);
  const resolvedConfig =
    (parsed as ListicleConfig["pitch"] | null) ??
    (coercedConfig as ListicleConfig["pitch"] | undefined) ??
    preSalesDefaults.config.pitch;
  invariant(
    isRecord(resolvedConfig) &&
      typeof resolvedConfig.title === "string" &&
      Array.isArray(resolvedConfig.bullets) &&
      isRecord(resolvedConfig.image),
    `PreSalesPitch.config must be an object like { title: string, bullets: string[], image: {...} }. Received ${describeValue(resolvedConfig)}.`
  );
  return <Pitch pitch={resolvedConfig} />;
}

type PreSalesReviewWallProps = {
  config?: ListicleConfig["reviewsWall"];
  configJson?: string;
  copy?: UiCopy;
  copyJson?: string;
};

export function PreSalesReviewWall({ config, configJson, copy, copyJson }: PreSalesReviewWallProps) {
  const parsed = parseJsonMaybeNested(configJson);
  if (parsed !== null) {
    invariant(
      isRecord(parsed) && typeof parsed.title === "string" && Array.isArray(parsed.columns),
      `PreSalesReviewWall.configJson must be a JSON object like { title: string, columns: [...] }. Received ${describeValue(parsed)}.`
    );
  }
  const coercedConfig = coerceJsonProp(config);
  const resolvedConfig =
    (parsed as ListicleConfig["reviewsWall"] | null) ??
    (coercedConfig as ListicleConfig["reviewsWall"] | undefined) ??
    preSalesDefaults.config.reviewsWall;
  invariant(
    isRecord(resolvedConfig) && typeof resolvedConfig.title === "string" && Array.isArray(resolvedConfig.columns),
    `PreSalesReviewWall.config must be an object like { title: string, columns: [...] }. Received ${describeValue(resolvedConfig)}.`
  );
  const socialProof = useResolvedPreSalesSocialProof();
  const resolvedCopy = resolveCopy(copy, copyJson);
  const normalizedWall = useMemo(
    () => ({ ...resolvedConfig, title: socialProof.reviewTitle }),
    [resolvedConfig, socialProof.reviewTitle]
  );
  return <ReviewWall wall={normalizedWall} modalCopy={resolvedCopy.modal} />;
}

type PreSalesFooterProps = {
  config?: ListicleConfig["footer"];
  configJson?: string;
};

export function PreSalesFooter({ config, configJson }: PreSalesFooterProps) {
  const parsed = parseJsonMaybeNested(configJson);
  if (parsed !== null) {
    invariant(
      isRecord(parsed) && isRecord(parsed.logo) && typeof parsed.logo.alt === "string",
      `PreSalesFooter.configJson must be a JSON object like { logo: { alt: string, ... } }. Received ${describeValue(parsed)}.`
    );
  }
  const coercedConfig = coerceJsonProp(config);
  const resolvedConfig =
    (parsed as ListicleConfig["footer"] | null) ??
    (coercedConfig as ListicleConfig["footer"] | undefined) ??
    preSalesDefaults.config.footer;
  invariant(
    isRecord(resolvedConfig) && isRecord(resolvedConfig.logo) && typeof resolvedConfig.logo.alt === "string",
    `PreSalesFooter.config must be an object like { logo: { alt: string, ... } }. Received ${describeValue(resolvedConfig)}.`
  );
  return <Footer footer={resolvedConfig} />;
}

type PreSalesFloatingCtaProps = {
  config?: ListicleConfig["floatingCta"];
  configJson?: string;
};

export function PreSalesFloatingCta({ config, configJson }: PreSalesFloatingCtaProps) {
  const parsed = parseJsonMaybeNested(configJson);
  if (parsed !== null) {
    invariant(
      isRecord(parsed) && typeof parsed.label === "string",
      `PreSalesFloatingCta.configJson must be a JSON object like { label: string, ... }. Received ${describeValue(parsed)}.`
    );
  }
  const coercedConfig = coerceJsonProp(config);
  const resolvedConfig =
    (parsed as ListicleConfig["floatingCta"] | null) ??
    (coercedConfig as ListicleConfig["floatingCta"] | undefined) ??
    preSalesDefaults.config.floatingCta;
  invariant(
    isRecord(resolvedConfig) && typeof resolvedConfig.label === "string",
    `PreSalesFloatingCta.config must be an object like { label: string, ... }. Received ${describeValue(resolvedConfig)}.`
  );
  return <FloatingCta cta={resolvedConfig} />;
}

export function PreSalesTemplate(props: Props) {
  const parsed = parseJsonMaybeNested(props.configJson);
  if (parsed !== null) {
    invariant(
      isRecord(parsed) &&
        isRecord(parsed.hero) &&
        typeof parsed.hero.title === "string" &&
        Array.isArray(parsed.badges) &&
        Array.isArray(parsed.reasons) &&
        Array.isArray(parsed.marquee) &&
        isRecord(parsed.pitch) &&
        isRecord(parsed.reviewsWall) &&
        isRecord(parsed.footer) &&
        isRecord(parsed.floatingCta),
      `PreSalesTemplate.configJson must be a JSON object like ListicleConfig. Received ${describeValue(parsed)}.`
    );
  }
  const coercedConfig = coerceJsonProp(props.config);
  const resolvedConfig =
    (parsed as ListicleConfig | null) ?? (coercedConfig as ListicleConfig | undefined) ?? preSalesDefaults.config;
  invariant(
    isRecord(resolvedConfig) &&
      isRecord(resolvedConfig.hero) &&
      typeof resolvedConfig.hero.title === "string" &&
      Array.isArray(resolvedConfig.badges) &&
      Array.isArray(resolvedConfig.reasons) &&
      Array.isArray(resolvedConfig.marquee) &&
      isRecord(resolvedConfig.pitch) &&
      isRecord(resolvedConfig.reviewsWall) &&
      isRecord(resolvedConfig.footer) &&
      isRecord(resolvedConfig.floatingCta),
    `PreSalesTemplate.config must be a ListicleConfig object. Received ${describeValue(resolvedConfig)}.`
  );
  const resolvedCopy = resolveCopy(props.copy, props.copyJson);
  const resolvedTheme = parseJson<ThemeConfig>(props.themeJson) ?? props.theme ?? preSalesDefaults.theme;

  return (
    <PreSalesPage anchorId="top" theme={resolvedTheme}>
      <>
        <PreSalesHero config={{ hero: resolvedConfig.hero, badges: resolvedConfig.badges }} />
        <main>
          <PreSalesReasons config={resolvedConfig.reasons} />
          <PreSalesMarquee config={resolvedConfig.marquee} />
          <PreSalesPitch config={resolvedConfig.pitch} />
          <PreSalesReviewWall config={resolvedConfig.reviewsWall} copy={resolvedCopy} />
          <PreSalesFooter config={resolvedConfig.footer} />
        </main>
        <PreSalesFloatingCta config={resolvedConfig.floatingCta} />
      </>
    </PreSalesPage>
  );
}

export { BadgeRow, Container, Modal };
