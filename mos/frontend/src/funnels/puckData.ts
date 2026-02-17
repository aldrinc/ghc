import type { Data } from "@measured/puck";
import { defaultFunnelPuckData } from "@/funnels/puckConfig";

type NormalizePuckDataOptions = {
  /**
   * Optional design system tokens for a page. Used to repair legacy PreSales* configs that
   * omitted footer logo fields by inferring the brand logo.
   */
  designSystemTokens?: unknown;
};

function deepClone<T>(value: T): T {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value)) as T;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function makeBlockId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return Math.random().toString(36).slice(2);
}

function parseJsonAny(raw: unknown): unknown | null {
  if (typeof raw !== "string" || !raw.trim()) return null;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

function parseJsonMaybeNestedAny(raw: unknown): unknown | null {
  const parsed = parseJsonAny(raw);
  if (typeof parsed !== "string") return parsed;
  const trimmed = parsed.trim();
  if (!trimmed) return parsed;
  const looksLikeJson =
    (trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"));
  if (!looksLikeJson) return parsed;
  return parseJsonAny(trimmed) ?? parsed;
}

function parseJsonObject(raw: unknown): Record<string, unknown> | null {
  if (typeof raw !== "string" || !raw.trim()) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
  return null;
}

function coerceConfig<T>(raw: unknown, jsonRaw: unknown): T | null {
  if (raw && typeof raw === "object") return raw as T;
  const parsed = parseJsonObject(jsonRaw);
  if (parsed && typeof parsed === "object") return parsed as T;
  return null;
}

function pickString(obj: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === "string") return value;
  }
  return undefined;
}

function inferBrandLogoFromDesignSystemTokens(tokens: unknown): { assetPublicId: string; alt: string } | null {
  if (!isRecord(tokens)) return null;
  const brand = tokens.brand;
  if (!isRecord(brand)) return null;
  const logoAssetPublicId = brand.logoAssetPublicId;
  if (typeof logoAssetPublicId !== "string" || !logoAssetPublicId.trim()) return null;
  const logoAlt = typeof brand.logoAlt === "string" && brand.logoAlt.trim() ? brand.logoAlt.trim() : null;
  const nameAlt = typeof brand.name === "string" && brand.name.trim() ? brand.name.trim() : null;
  return {
    assetPublicId: logoAssetPublicId.trim(),
    alt: logoAlt ?? nameAlt ?? "Logo",
  };
}

function isHeroSectionConfig(value: unknown): boolean {
  if (!isRecord(value)) return false;
  const hero = value.hero;
  if (!isRecord(hero)) return false;
  if (typeof hero.title !== "string") return false;
  if (typeof hero.subtitle !== "string") return false;
  return Array.isArray(value.badges);
}

function migratePreSalesHeroConfig(raw: unknown): Record<string, unknown> | null {
  if (!isRecord(raw)) return null;
  if (isHeroSectionConfig(raw)) return null;

  const heroLike = isRecord(raw.hero) ? (raw.hero as Record<string, unknown>) : raw;
  const title = pickString(heroLike, ["title", "headline"]) ?? pickString(raw, ["title", "headline"]) ?? "";
  const subtitle =
    pickString(heroLike, ["subtitle", "subheadline"]) ?? pickString(raw, ["subtitle", "subheadline"]) ?? "";

  const badges = Array.isArray(raw.badges) ? raw.badges : [];

  const imageLike = (isRecord(heroLike.image) ? heroLike.image : null) ?? (isRecord(raw.image) ? raw.image : null);
  let media: Record<string, unknown> | undefined;
  if (isRecord(heroLike.media) && (heroLike.media.type === "image" || heroLike.media.type === "video")) {
    media = heroLike.media as Record<string, unknown>;
  } else if (imageLike) {
    const alt = typeof imageLike.alt === "string" ? imageLike.alt : "";
    if (typeof imageLike.srcMp4 === "string") {
      media = {
        type: "video",
        srcMp4: imageLike.srcMp4,
        poster: typeof imageLike.poster === "string" ? imageLike.poster : undefined,
        alt: alt || undefined,
        assetPublicId: typeof imageLike.assetPublicId === "string" ? imageLike.assetPublicId : undefined,
        posterAssetPublicId: typeof imageLike.posterAssetPublicId === "string" ? imageLike.posterAssetPublicId : undefined,
      };
    } else {
      media = {
        type: "image",
        src: typeof imageLike.src === "string" ? imageLike.src : undefined,
        alt,
        assetPublicId: typeof imageLike.assetPublicId === "string" ? imageLike.assetPublicId : undefined,
      };
    }
  }

  const looksLikeNewShape = isRecord(raw.hero) && typeof (raw.hero as Record<string, unknown>).title === "string";
  const looksLikeLegacyShape =
    typeof raw.headline === "string" ||
    typeof raw.subheadline === "string" ||
    typeof (heroLike as Record<string, unknown>).headline === "string" ||
    typeof (heroLike as Record<string, unknown>).subheadline === "string" ||
    Boolean(imageLike);

  if (!looksLikeNewShape && !looksLikeLegacyShape) return null;
  if (!title && !subtitle) return null;

  return { hero: { title, subtitle, media }, badges };
}

function migratePreSalesReasonsConfig(raw: unknown): unknown[] | null {
  if (Array.isArray(raw)) return null;
  if (!isRecord(raw) || !Array.isArray(raw.reasons)) return null;

  return raw.reasons.map((item, idx) => {
    if (!isRecord(item)) {
      return { number: idx + 1, title: "", body: "" };
    }
    const number = typeof item.number === "number" && Number.isFinite(item.number) ? item.number : idx + 1;
    const title = pickString(item, ["title", "headline", "heading"]) ?? "";
    const body = pickString(item, ["body", "text", "copy"]) ?? "";
    const image = isRecord(item.image) ? item.image : undefined;
    return { number, title, body, ...(image ? { image } : {}) };
  });
}

function migratePreSalesMarqueeConfig(raw: unknown): unknown[] | null {
  if (Array.isArray(raw)) return null;
  if (!isRecord(raw) || !Array.isArray(raw.items)) return null;
  return raw.items;
}

function migratePreSalesPitchConfig(raw: unknown): Record<string, unknown> | null {
  if (!isRecord(raw)) return null;
  const isAlready =
    typeof raw.title === "string" && Array.isArray(raw.bullets) && isRecord(raw.image);
  if (isAlready) return null;

  const hasLegacySignal =
    typeof raw.headline === "string" ||
    typeof raw.body === "string" ||
    Array.isArray(raw.body) ||
    typeof raw.ctaLabel === "string" ||
    typeof raw.ctaLinkType === "string";
  const hasNewSignal = typeof raw.title === "string" || Array.isArray(raw.bullets);
  const hasImageSignal = isRecord(raw.image) || typeof raw.image === "string";
  if ((!hasLegacySignal && !hasNewSignal) || !hasImageSignal) return null;

  const title = pickString(raw, ["title", "headline", "heading"]) ?? "";

  let bullets: unknown[] = [];
  if (Array.isArray(raw.bullets)) {
    bullets = raw.bullets;
  } else if (Array.isArray(raw.body)) {
    bullets = raw.body;
  } else if (typeof raw.body === "string") {
    const lines = raw.body
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    bullets = lines.length ? lines : [raw.body.trim()];
  }

  const image =
    typeof raw.image === "string"
      ? { src: raw.image, alt: "" }
      : isRecord(raw.image)
        ? raw.image
        : null;
  if (!image) return null;

  const next: Record<string, unknown> = { title, bullets, image };
  if (typeof raw.ctaLabel === "string" && raw.ctaLabel.trim()) {
    next.cta = {
      label: raw.ctaLabel,
      linkType: typeof raw.ctaLinkType === "string" ? raw.ctaLinkType : undefined,
      href: typeof raw.ctaHref === "string" ? raw.ctaHref : undefined,
      targetPageId: typeof raw.ctaTargetPageId === "string" ? raw.ctaTargetPageId : undefined,
    };
  }
  return next;
}

function migratePreSalesReviewsConfig(raw: unknown): Record<string, unknown> | null {
  if (!isRecord(raw)) return null;
  const isAlready = Array.isArray(raw.slides);
  if (isAlready) return null;
  if (!Array.isArray(raw.reviews)) return null;

  const slides = raw.reviews.map((item) => {
    if (!isRecord(item)) return item;
    if (Array.isArray(item.images)) return item;
    const image = isRecord(item.image) ? item.image : null;
    if (image) return { ...item, images: [image] };
    return { ...item, images: [] };
  });

  const next: Record<string, unknown> = { slides };
  if (typeof raw.autoAdvanceMs === "number" && Number.isFinite(raw.autoAdvanceMs)) next.autoAdvanceMs = raw.autoAdvanceMs;
  return next;
}

function migratePreSalesFooterConfig(raw: unknown, opts: NormalizePuckDataOptions | undefined): Record<string, unknown> | null {
  if (!isRecord(raw)) return null;
  const logo = raw.logo;
  if (isRecord(logo) && typeof logo.alt === "string") return null;

  const looksLikeLegacy = "links" in raw || "copyrightText" in raw || "logo" in raw || "image" in raw;
  if (!looksLikeLegacy) return null;

  const brandLogo = inferBrandLogoFromDesignSystemTokens(opts?.designSystemTokens);
  if (!brandLogo) return null;

  // Legacy footer configs often had { links, copyrightText } but no logo.
  // We repair into the current shape expected by the PreSales listicle footer.
  return {
    logo: {
      assetPublicId: brandLogo.assetPublicId,
      alt: brandLogo.alt,
    },
  };
}

function migratePreSalesListicleBlockConfigs(node: unknown, opts: NormalizePuckDataOptions | undefined): boolean {
  let changed = false;

  const walk = (value: unknown) => {
    if (Array.isArray(value)) {
      for (const v of value) walk(v);
      return;
    }
    if (!isRecord(value)) return;

    const type = value.type;
    const props = value.props;
    if (typeof type === "string" && isRecord(props)) {
      const rawJson = props.configJson;
      const hasConfigJson = typeof rawJson === "string" && rawJson.trim().length > 0;
      const parsedJson = parseJsonMaybeNestedAny(rawJson);
      const configFromJson = parsedJson !== null && typeof parsedJson === "object" ? parsedJson : null;
      let rawConfig: unknown = configFromJson ?? props.config;
      if (typeof rawConfig === "string") {
        const parsedConfig = parseJsonMaybeNestedAny(rawConfig);
        if (parsedConfig !== null && typeof parsedConfig === "object") rawConfig = parsedConfig;
      }

      let nextConfig: unknown | null = null;
      if (type === "PreSalesHero") nextConfig = migratePreSalesHeroConfig(rawConfig);
      else if (type === "PreSalesReasons") nextConfig = migratePreSalesReasonsConfig(rawConfig);
      else if (type === "PreSalesMarquee") nextConfig = migratePreSalesMarqueeConfig(rawConfig);
      else if (type === "PreSalesPitch") nextConfig = migratePreSalesPitchConfig(rawConfig);
      else if (type === "PreSalesReviews") nextConfig = migratePreSalesReviewsConfig(rawConfig);
      else if (type === "PreSalesFooter") nextConfig = migratePreSalesFooterConfig(rawConfig, opts);

      if (nextConfig !== null) {
        props.config = nextConfig;
        if (hasConfigJson) props.configJson = JSON.stringify(nextConfig);
        changed = true;
      }
    }

    for (const key of Object.keys(value)) walk(value[key]);
  };

  walk(node);
  return changed;
}

function migrateSalesPdpTemplate(content: unknown[]): unknown[] {
  if (!Array.isArray(content)) return content;
  let changed = false;

  const next = content.map((item) => {
    if (!item || typeof item !== "object") return item;
    const obj = item as Record<string, unknown>;
    if (obj.type !== "SalesPdpTemplate" || typeof obj.props !== "object") return item;

    const props = obj.props as Record<string, unknown>;
    const config = coerceConfig<Record<string, unknown>>(props.config, props.configJson);
    const copy = coerceConfig<Record<string, unknown>>(props.copy, props.copyJson);
    const theme = coerceConfig<Record<string, unknown>>(props.theme, props.themeJson);

    if (!config) return item;

    const hero = (config.hero as Record<string, unknown>) || {};
    const story = (config.story as Record<string, unknown>) || {};
    const reviewWall = (config.reviewWall as Record<string, unknown>) || {};
    const reviewTiles = Array.isArray(reviewWall.tiles) ? reviewWall.tiles : [];
    const feedImages = reviewTiles
      .map((tile) => (tile && typeof tile === "object" ? (tile as Record<string, unknown>).image : null))
      .filter(Boolean);

    changed = true;

    return {
      type: "SalesPdpPage",
      props: {
        id: typeof props.id === "string" && props.id ? props.id : makeBlockId(),
        anchorId: "top",
        theme: theme ?? undefined,
        themeJson: typeof props.themeJson === "string" ? props.themeJson : undefined,
        content: [
          {
            type: "SalesPdpHeader",
            props: {
              id: makeBlockId(),
              config: (hero as Record<string, unknown>).header,
            },
          },
          {
            type: "SalesPdpHero",
            props: {
              id: makeBlockId(),
              config: hero,
              modals: config.modals,
              copy,
            },
          },
          { type: "SalesPdpVideos", props: { id: makeBlockId(), config: config.videos } },
          { type: "SalesPdpMarquee", props: { id: makeBlockId(), config: config.marquee } },
          { type: "SalesPdpStoryProblem", props: { id: makeBlockId(), config: (story as Record<string, unknown>).problem } },
          { type: "SalesPdpStorySolution", props: { id: makeBlockId(), config: (story as Record<string, unknown>).solution } },
          { type: "SalesPdpComparison", props: { id: makeBlockId(), config: config.comparison } },
          {
            type: "SalesPdpGuarantee",
            props: {
              id: makeBlockId(),
              config: config.guarantee,
              feedImages,
            },
          },
          { type: "SalesPdpFaq", props: { id: makeBlockId(), config: config.faq } },
          { type: "SalesPdpReviewWall", props: { id: makeBlockId(), config: config.reviewWall } },
          { type: "SalesPdpFooter", props: { id: makeBlockId(), config: config.footer } },
        ],
      },
    };
  });

  return changed ? next : content;
}

function migratePreSalesTemplate(content: unknown[]): unknown[] {
  if (!Array.isArray(content)) return content;
  let changed = false;

  const next = content.map((item) => {
    if (!item || typeof item !== "object") return item;
    const obj = item as Record<string, unknown>;
    if (obj.type !== "PreSalesTemplate" || typeof obj.props !== "object") return item;

    const props = obj.props as Record<string, unknown>;
    const config = coerceConfig<Record<string, unknown>>(props.config, props.configJson);
    const copy = coerceConfig<Record<string, unknown>>(props.copy, props.copyJson);
    const theme = coerceConfig<Record<string, unknown>>(props.theme, props.themeJson);

    if (!config) return item;

    changed = true;

    return {
      type: "PreSalesPage",
      props: {
        id: typeof props.id === "string" && props.id ? props.id : makeBlockId(),
        anchorId: "top",
        theme: theme ?? undefined,
        themeJson: typeof props.themeJson === "string" ? props.themeJson : undefined,
        content: [
          {
            type: "PreSalesHero",
            props: {
              id: makeBlockId(),
              config: {
                hero: (config as Record<string, unknown>).hero,
                badges: (config as Record<string, unknown>).badges,
              },
            },
          },
          { type: "PreSalesReasons", props: { id: makeBlockId(), config: config.reasons } },
          { type: "PreSalesReviews", props: { id: makeBlockId(), config: config.reviews, copy } },
          { type: "PreSalesMarquee", props: { id: makeBlockId(), config: config.marquee } },
          { type: "PreSalesPitch", props: { id: makeBlockId(), config: config.pitch } },
          { type: "PreSalesReviewWall", props: { id: makeBlockId(), config: config.reviewsWall, copy } },
          { type: "PreSalesFooter", props: { id: makeBlockId(), config: config.footer } },
          { type: "PreSalesFloatingCta", props: { id: makeBlockId(), config: config.floatingCta } },
        ],
      },
    };
  });

  return changed ? next : content;
}

export function normalizePuckData(input: unknown, options?: NormalizePuckDataOptions): Data {
  const fallback = defaultFunnelPuckData() as unknown as Data;
  if (!input || typeof input !== "object") return fallback;

  const cloned = deepClone(input) as Record<string, unknown>;

  if (!cloned.root || typeof cloned.root !== "object") cloned.root = { props: {} };
  const root = cloned.root as Record<string, unknown>;
  if (!root.props || typeof root.props !== "object") root.props = {};
  const rootProps = root.props as Record<string, unknown>;
  if (typeof rootProps.title !== "string") rootProps.title = "";
  if (typeof rootProps.description !== "string") rootProps.description = "";

  if (!Array.isArray(cloned.content)) cloned.content = [];
  if (!cloned.zones || typeof cloned.zones !== "object") cloned.zones = {};

  cloned.content = migrateSalesPdpTemplate(cloned.content as unknown[]);
  cloned.content = migratePreSalesTemplate(cloned.content as unknown[]);
  migratePreSalesListicleBlockConfigs(cloned, options);

  const seen = new Set<string>();
  const walk = (value: unknown) => {
    if (Array.isArray(value)) {
      for (const v of value) walk(v);
      return;
    }
    if (!value || typeof value !== "object") return;

    const obj = value as Record<string, unknown>;
    const type = obj.type;
    const propsRaw = obj.props;
    if (typeof type === "string" && propsRaw && typeof propsRaw === "object") {
      const props = propsRaw as Record<string, unknown>;
      let id = typeof props.id === "string" ? props.id : "";
      if (!id || seen.has(id)) {
        id = makeBlockId();
        props.id = id;
      }
      seen.add(id);
    }

    for (const key of Object.keys(obj)) walk(obj[key]);
  };

  walk(cloned.content);
  walk(cloned.zones);

  return cloned as unknown as Data;
}
