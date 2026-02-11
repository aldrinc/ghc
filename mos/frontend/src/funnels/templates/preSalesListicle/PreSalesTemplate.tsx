import { useMemo, type ReactNode } from "react";
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

export const preSalesDefaults = defaults as {
  config: ListicleConfig;
  copy: UiCopy;
  theme?: ThemeConfig;
};

type Props = {
  id?: string;
  config?: ListicleConfig;
  copy?: UiCopy;
  theme?: ThemeConfig;
  configJson?: string;
  copyJson?: string;
  themeJson?: string;
};

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
        style[toCssVarName(rawKey)] = String(rawValue);
      }
    }
    if (explicitTheme?.tokens) {
      for (const [rawKey, rawValue] of Object.entries(resolvedTheme.tokens ?? {})) {
        if (rawValue === undefined || rawValue === null) continue;
        style[toCssVarName(rawKey)] = String(rawValue);
      }
    }
    return style;
  }, [defaultTheme, designSystemTokens, explicitTheme, resolvedTheme]);

  const resolvedAnchorId = anchorId && anchorId.trim() ? anchorId : "top";
  const body = content ? content({}) : children;

  return (
    <div
      className={baseStyles.root}
      id={resolvedAnchorId}
      data-theme={explicitTheme?.dataTheme ?? designSystemTokens?.dataTheme ?? resolvedTheme?.dataTheme}
      style={themeStyle}
    >
      {body}
    </div>
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

  return (
    <Hero
      title={resolvedConfig.hero.title}
      subtitle={resolvedConfig.hero.subtitle}
      media={resolvedConfig.hero.media}
      badges={resolvedConfig.badges}
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
  const resolvedCopy = resolveCopy(copy, copyJson);
  return <ReviewWall wall={resolvedConfig} modalCopy={resolvedCopy.modal} />;
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
        isRecord(parsed.reviews) &&
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
      isRecord(resolvedConfig.reviews) &&
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
          <PreSalesReviews config={resolvedConfig.reviews} copy={resolvedCopy} />
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
