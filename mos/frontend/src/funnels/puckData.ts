import type { Data } from "@measured/puck";
import { defaultFunnelPuckData } from "@/funnels/puckConfig";

function deepClone<T>(value: T): T {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value)) as T;
}

function makeBlockId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return Math.random().toString(36).slice(2);
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

export function normalizePuckData(input: unknown): Data {
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
