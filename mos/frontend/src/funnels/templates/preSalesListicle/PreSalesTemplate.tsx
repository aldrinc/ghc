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
  const resolvedConfig =
    parseJson<HeroSectionConfig>(configJson) ??
    config ??
    {
      hero: preSalesDefaults.config.hero,
      badges: preSalesDefaults.config.badges,
    };

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
  const resolvedConfig =
    parseJson<ListicleConfig["reasons"]>(configJson) ?? config ?? preSalesDefaults.config.reasons;
  return <Reasons reasons={resolvedConfig} />;
}

type PreSalesReviewsProps = {
  config?: ListicleConfig["reviews"];
  configJson?: string;
  copy?: UiCopy;
  copyJson?: string;
};

export function PreSalesReviews({ config, configJson, copy, copyJson }: PreSalesReviewsProps) {
  const resolvedConfig =
    parseJson<ListicleConfig["reviews"]>(configJson) ?? config ?? preSalesDefaults.config.reviews;
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
  const resolvedConfig =
    parseJson<ListicleConfig["marquee"]>(configJson) ?? config ?? preSalesDefaults.config.marquee;
  return <Marquee items={resolvedConfig} />;
}

type PreSalesPitchProps = {
  config?: ListicleConfig["pitch"];
  configJson?: string;
};

export function PreSalesPitch({ config, configJson }: PreSalesPitchProps) {
  const resolvedConfig = parseJson<ListicleConfig["pitch"]>(configJson) ?? config ?? preSalesDefaults.config.pitch;
  return <Pitch pitch={resolvedConfig} />;
}

type PreSalesReviewWallProps = {
  config?: ListicleConfig["reviewsWall"];
  configJson?: string;
  copy?: UiCopy;
  copyJson?: string;
};

export function PreSalesReviewWall({ config, configJson, copy, copyJson }: PreSalesReviewWallProps) {
  const resolvedConfig =
    parseJson<ListicleConfig["reviewsWall"]>(configJson) ?? config ?? preSalesDefaults.config.reviewsWall;
  const resolvedCopy = resolveCopy(copy, copyJson);
  return <ReviewWall wall={resolvedConfig} modalCopy={resolvedCopy.modal} />;
}

type PreSalesFooterProps = {
  config?: ListicleConfig["footer"];
  configJson?: string;
};

export function PreSalesFooter({ config, configJson }: PreSalesFooterProps) {
  const resolvedConfig = parseJson<ListicleConfig["footer"]>(configJson) ?? config ?? preSalesDefaults.config.footer;
  return <Footer footer={resolvedConfig} />;
}

type PreSalesFloatingCtaProps = {
  config?: ListicleConfig["floatingCta"];
  configJson?: string;
};

export function PreSalesFloatingCta({ config, configJson }: PreSalesFloatingCtaProps) {
  const resolvedConfig =
    parseJson<ListicleConfig["floatingCta"]>(configJson) ?? config ?? preSalesDefaults.config.floatingCta;
  return <FloatingCta cta={resolvedConfig} />;
}

export function PreSalesTemplate(props: Props) {
  const resolvedConfig = parseJson<ListicleConfig>(props.configJson) ?? props.config ?? preSalesDefaults.config;
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
