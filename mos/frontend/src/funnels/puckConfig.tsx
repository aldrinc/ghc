import { createContext, useContext, type ReactNode } from "react";
import type { Config } from "@measured/puck";
import { Link } from "react-router-dom";
import {
  ImportedAccordion,
  ImportedBadgeStrip,
  ImportedComparisonTable,
  ImportedFooterLinks,
  ImportedItemGrid,
  ImportedNarrativeBlock,
  ImportedOfferSelector,
  ImportedPage,
  ImportedSection,
  ImportedTestimonialsGrid,
} from "@/components/imported-site/ImportedTemplateBlocks";
import {
  ImportedComparisonSection,
  ImportedFaqSection,
  ImportedFeatureSection,
  ImportedFooterSection,
  ImportedHeaderSection,
  ImportedHeroSection,
  ImportedOfferSection,
  ImportedProofBarSection,
  ImportedTestimonialsSection,
} from "@/components/imported-site/ImportedSourceSectionBlocks";
import { ImportedRuntimeSection } from "@/components/imported-site/ImportedRuntimeSection";
import { buildPublicFunnelPath, resolvePublicApiBaseUrl } from "@/funnels/runtimeRouting";
import {
  navigationClickEventForStages,
  resolvePublicFunnelStage,
  type RuntimeTrackingEvent,
} from "@/lib/funnelTracking";
import {
  SalesPdpComparison,
  SalesPdpFaq,
  SalesPdpFooter,
  SalesPdpGuarantee,
  SalesPdpHeader,
  SalesPdpHero,
  SalesPdpMarquee,
  SalesPdpPage,
  SalesPdpReviewSlider,
  SalesPdpReviewWall,
  SalesPdpStoryProblem,
  SalesPdpStorySolution,
  SalesPdpTemplate,
  SalesPdpVideos,
  salesPdpDefaults,
} from "@/funnels/templates/salesPdp/SalesPdpTemplate";
import { SalesPdpReviews } from "@/funnels/templates/salesPdp/SalesPdpReviews";
import {
  PreSalesFloatingCta,
  PreSalesFooter,
  PreSalesHero,
  PreSalesMarquee,
  PreSalesPage,
  PreSalesPitch,
  PreSalesReasons,
  PreSalesReviewWall,
  PreSalesReviews,
  PreSalesTemplate,
  preSalesDefaults,
} from "@/funnels/templates/preSalesListicle/PreSalesTemplate";
import { BlockErrorBoundary } from "@/funnels/BlockErrorBoundary";
import type { PublicFunnelCommerce, PublicFunnelStage, SitePageType } from "@/types/funnels";
import {
  CommerceCatalogHero,
  CommerceProductGrid,
  CommerceProductDetail,
  CommerceCart,
  CommerceCheckout,
  CommerceCategoryList,
  CommerceCategoryHeading,
  CommerceCartSummary,
  CommerceStoreHeader,
  CommerceStoreFooter,
  CommerceStoreTemplate,
} from "@/components/commerce/CommerceBlocks";
import {
  StarterStoreHeader,
  StarterPromoBar,
  StarterHomeHero,
  StarterPolicyPage,
  StarterCollectionRails,
  StarterStoreFooter,
} from "@/components/commerce/StarterStorefrontBlocks";
import {
  MedusaB2CHomePage,
  MedusaB2CStorePage,
  MedusaB2CCollectionPage,
  MedusaB2CCategoryPage,
  MedusaB2CProductPage,
  MedusaB2CCartPage,
  MedusaB2CCheckoutPage,
  MedusaB2CPolicyPage,
  MedusaB2CAccountDashboardPage,
  MedusaB2CAccountProfilePage,
  MedusaB2CAccountAddressesPage,
  MedusaB2CAccountOrdersPage,
  MedusaB2CAccountOrderDetailPage,
  MedusaB2COrderConfirmedPage,
  MedusaB2COrderTransferPage,
  MedusaB2COrderTransferAcceptPage,
  MedusaB2COrderTransferDeclinePage,
} from "@/components/commerce/b2c";

const apiBaseUrl = resolvePublicApiBaseUrl();
const salesPdpFeedImages = salesPdpDefaults.config.reviewWall?.tiles?.map((tile) => tile.image) || [];

type FunnelRuntimeContextValue = {
  productSlug: string;
  funnelSlug: string;
  pageMap: Record<string, string>;
  pageStageMap: Record<string, PublicFunnelStage>;
  pageTypeMap?: Record<string, SitePageType>;
  bundleMode?: boolean;
  entrySlug?: string | null;
  pageStage?: PublicFunnelStage;
  trackEvent?: (event: RuntimeTrackingEvent) => void;
  commerce?: PublicFunnelCommerce | null;
  commerceError?: string | null;
  pageId?: string | null;
  nextPageId?: string | null;
  visitorId?: string | null;
  sessionId?: string | null;
  resolvePagePath?: (slug: string) => string;
  resolveSitePath?: (sitePath: string) => string;
};

const FunnelRuntimeContext = createContext<FunnelRuntimeContextValue | null>(null);

export function FunnelRuntimeProvider({
  value,
  children,
}: {
  value: FunnelRuntimeContextValue;
  children: ReactNode;
}) {
  return <FunnelRuntimeContext.Provider value={value}>{children}</FunnelRuntimeContext.Provider>;
}

export function useFunnelRuntime() {
  return useContext(FunnelRuntimeContext);
}

export function resolveRuntimePagePath(runtime: FunnelRuntimeContextValue, slug: string): string {
  const normalizedSlug = (slug || "").trim();
  if (!normalizedSlug) {
    return "#";
  }
  if (runtime.resolvePagePath) {
    return runtime.resolvePagePath(normalizedSlug);
  }
  if (runtime.bundleMode) {
    return `/${encodeURIComponent(runtime.productSlug)}/${encodeURIComponent(runtime.funnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
  }
  return `/f/${encodeURIComponent(runtime.productSlug)}/${encodeURIComponent(runtime.funnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
}

export function resolveRuntimeSitePath(runtime: FunnelRuntimeContextValue, sitePath: string): string {
  const rawSitePath = (sitePath || "").trim();
  const normalizedSitePath = rawSitePath.replace(/^\/+/, "");
  if (!normalizedSitePath) {
    if (runtime.resolveSitePath) {
      return runtime.resolveSitePath("");
    }
    return buildPublicFunnelPath({
      productSlug: runtime.productSlug,
      funnelSlug: runtime.funnelSlug,
      bundleMode: runtime.bundleMode || false,
      sitePath: "",
    });
  }
  if (runtime.resolveSitePath) {
    return runtime.resolveSitePath(normalizedSitePath);
  }
  return buildPublicFunnelPath({
    productSlug: runtime.productSlug,
    funnelSlug: runtime.funnelSlug,
    bundleMode: runtime.bundleMode || false,
    sitePath: normalizedSitePath,
  });
}

type PageOption = { label: string; value: string };

type ContainerWidth = "sm" | "md" | "lg" | "xl";

function safeJsonStringify(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}

function withBlockBoundary<T extends Record<string, unknown>>(
  blockType: string,
  render: (props: T) => ReactNode
): (props: T) => ReactNode {
  return (props: T) => {
    const id = typeof props.id === "string" ? props.id : undefined;
    return (
      <BlockErrorBoundary blockType={blockType} blockId={id} resetKey={safeJsonStringify(props)}>
        {render(props)}
      </BlockErrorBoundary>
    );
  };
}

function createImportedSourceSectionBlockConfig(
  blockType: string,
  renderBlock: (props: Record<string, unknown>) => ReactNode,
) {
  return {
    fields: {
      textSlots: {
        type: "array",
        arrayFields: {
          label: { type: "text" },
          originalText: { type: "textarea" },
          text: { type: "textarea" },
        },
        defaultItemProps: { label: "", originalText: "", text: "" },
      },
      buttonSlots: {
        type: "array",
        arrayFields: {
          label: { type: "text" },
          originalText: { type: "text" },
          text: { type: "text" },
          href: { type: "text" },
        },
        defaultItemProps: { label: "", originalText: "", text: "", href: "" },
      },
      imageSlots: {
        type: "array",
        arrayFields: {
          label: { type: "text" },
          originalSrc: { type: "text" },
          originalText: { type: "text" },
          src: { type: "text" },
          alt: { type: "text" },
        },
        defaultItemProps: { label: "", originalSrc: "", originalText: "", src: "", alt: "" },
      },
    },
    defaultProps: {
      textSlots: [],
      buttonSlots: [],
      imageSlots: [],
    },
    render: withBlockBoundary(blockType, renderBlock),
  };
}

function containerWidthClass(width?: ContainerWidth): string {
  switch (width) {
    case "sm":
      return "max-w-2xl";
    case "lg":
      return "max-w-6xl";
    case "xl":
      return "max-w-7xl";
    case "md":
    default:
      return "max-w-4xl";
  }
}

function sectionPaddingClass(padding?: "none" | "sm" | "md" | "lg"): { inner: string; outerY: string } {
  if (padding === "none") return { inner: "p-0", outerY: "py-0" };
  if (padding === "lg") return { inner: "p-10", outerY: "py-16" };
  if (padding === "sm") return { inner: "p-5", outerY: "py-10" };
  return { inner: "p-7", outerY: "py-12" };
}

type ButtonProps = {
  label?: string;
  linkType?: "external" | "funnelPage" | "nextPage";
  href?: string;
  targetPageId?: string;
  variant?: "primary" | "secondary";
  size?: "sm" | "md" | "lg";
  width?: "auto" | "full";
  align?: "left" | "center" | "right";
};

function FunnelButton({ label, linkType, href, targetPageId, variant, size, width, align }: ButtonProps) {
  const runtime = useFunnelRuntime();
  const text = label || "Button";
  const sizeClass =
    variant === "secondary"
      ? "rounded-md border border-border bg-surface-2 font-semibold text-content"
      : "rounded-md bg-primary font-semibold text-primary-foreground";
  const pad =
    size === "lg"
      ? "px-6 py-3 text-base"
      : size === "sm"
        ? "px-3 py-2 text-sm"
        : "px-4 py-2 text-sm";
  const widthClass = width === "full" ? "w-full" : "";
  const className = `inline-flex items-center justify-center ${sizeClass} ${pad} ${widthClass}`;
  const resolvedAlign = align || "left";
  const wrapperClass =
    resolvedAlign === "center"
      ? "flex justify-center"
      : resolvedAlign === "right"
        ? "flex justify-end"
        : "flex justify-start";

  if (linkType === "funnelPage" && runtime && targetPageId) {
    const targetSlug = runtime.pageMap[targetPageId];
    const targetStage = runtime.pageStageMap[targetPageId] || resolvePublicFunnelStage(targetSlug);
    const to = targetSlug ? resolveRuntimePagePath(runtime, targetSlug) : "#";
    return (
      <div className={wrapperClass}>
        <Link
          to={to}
          className={className}
          onClick={() =>
            runtime.trackEvent?.(
              navigationClickEventForStages({
                fromStage: runtime.pageStage || "custom",
                toStage: targetStage,
                props: { targetPageId },
              }),
            )
          }
        >
          {text}
        </Link>
      </div>
    );
  }

  if (linkType === "nextPage") {
    if (!runtime) {
      throw new Error("Funnel runtime is required to resolve next page links.");
    }
    if (!runtime.productSlug) {
      throw new Error("Funnel runtime is missing a product slug.");
    }
    if (!runtime.funnelSlug) {
      throw new Error("Funnel runtime is missing a funnel slug.");
    }
    if (!runtime.nextPageId) {
      throw new Error("Next page is not configured for this page.");
    }
    const targetSlug = runtime.pageMap[runtime.nextPageId];
    if (!targetSlug) {
      throw new Error("Next page is not available in this funnel.");
    }
    const targetStage = runtime.pageStageMap[runtime.nextPageId] || resolvePublicFunnelStage(targetSlug);
    const to = resolveRuntimePagePath(runtime, targetSlug);
    return (
      <div className={wrapperClass}>
        <Link
          to={to}
          className={className}
          onClick={() =>
            runtime.trackEvent?.(
              navigationClickEventForStages({
                fromStage: runtime.pageStage || "custom",
                toStage: targetStage,
                props: { targetPageId: runtime.nextPageId },
              }),
            )
          }
        >
          {text}
        </Link>
      </div>
    );
  }

  if (linkType === "external" && href) {
    return (
      <div className={wrapperClass}>
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className={className}
          onClick={() =>
            runtime?.trackEvent?.(
              navigationClickEventForStages({
                fromStage: runtime.pageStage || "custom",
                toStage: resolvePublicFunnelStage(href),
                props: { href },
              }),
            )
          }
        >
          {text}
        </a>
      </div>
    );
  }

  return (
    <div className={wrapperClass}>
      <button className={className}>{text}</button>
    </div>
  );
}

type ImageProps = {
  src?: string;
  prompt?: string;
  imageSource?: "ai" | "unsplash";
  assetPublicId?: string;
  referenceAssetPublicId?: string;
  alt?: string;
  radius?: "none" | "md" | "lg";
};

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

function FunnelImage({ src, assetPublicId, alt, radius }: ImageProps) {
  const resolvedSrc = assetPublicId
    ? `${apiBaseUrl}/public/assets/${assetPublicId}`
    : normalizeFallbackAssetSrc(src);
  if (!resolvedSrc) {
    return <div className="rounded-md border border-dashed border-border bg-surface-2 p-6 text-sm text-content-muted">No image</div>;
  }
  const radiusClass = radius === "none" ? "rounded-none" : radius === "lg" ? "rounded-2xl" : "rounded-md";
  return <img src={resolvedSrc} alt={alt || ""} className={`h-auto w-full ${radiusClass} border border-border`} />;
}

export function createFunnelPuckConfig(pageOptions: PageOption[] = []): Config {
  return {
    root: {
      fields: {
        title: { type: "text" },
        description: { type: "textarea" },
      },
      render: ({ children }) => <div className="w-full">{children}</div>,
    },
    components: {
      Section: {
        fields: {
          purpose: {
            type: "select",
            options: [
              { label: "Section", value: "section" },
              { label: "Header", value: "header" },
              { label: "Footer", value: "footer" },
            ],
          },
          // Modern Section props - bandWidth replaces layout
          bandWidth: {
            type: "select",
            options: [
              { label: "Full bleed", value: "full" },
              { label: "Contained", value: "contained" },
            ],
          },
          // Modern Section props - contentWidth replaces containerWidth
          contentWidth: {
            type: "select",
            options: [
              { label: "Small (640px)", value: "sm" },
              { label: "Medium (768px)", value: "md" },
              { label: "Large (1024px)", value: "lg" },
              { label: "Extra large (1280px)", value: "xl" },
              { label: "Full width", value: "full" },
            ],
          },
          // Modern Section props - contentAlign
          contentAlign: {
            type: "select",
            options: [
              { label: "Left", value: "left" },
              { label: "Center", value: "center" },
              { label: "Right", value: "right" },
            ],
          },
          // Modern Section props - surface replaces variant
          surface: {
            type: "select",
            options: [
              { label: "Default", value: "default" },
              { label: "Muted", value: "muted" },
              { label: "Primary", value: "primary" },
              { label: "Dark", value: "dark" },
            ],
          },
          // Modern Section props - padY replaces padding (vertical)
          padY: {
            type: "select",
            options: [
              { label: "None", value: "none" },
              { label: "Small", value: "sm" },
              { label: "Medium", value: "md" },
              { label: "Large", value: "lg" },
              { label: "Extra large", value: "xl" },
            ],
          },
          // Modern Section props - padX (horizontal)
          padX: {
            type: "select",
            options: [
              { label: "None", value: "none" },
              { label: "Small", value: "sm" },
              { label: "Medium", value: "md" },
              { label: "Large", value: "lg" },
            ],
          },
          content: { type: "slot" },
        },
        defaultProps: {
          purpose: "section",
          bandWidth: "contained",
          contentWidth: "lg",
          contentAlign: "left",
          surface: "default",
          padY: "md",
          padX: "md",
        },
        render: ({
          purpose,
          bandWidth,
          contentWidth,
          contentAlign,
          surface,
          padY,
          padX,
          content,
        }: {
          purpose?: "header" | "section" | "footer";
          bandWidth?: "full" | "contained";
          contentWidth?: "sm" | "md" | "lg" | "xl" | "full";
          contentAlign?: "left" | "center" | "right";
          surface?: "default" | "muted" | "primary" | "dark";
          padY?: "none" | "sm" | "md" | "lg" | "xl";
          padX?: "none" | "sm" | "md" | "lg";
          content?: (props?: Record<string, unknown>) => ReactNode;
        }) => {
          const resolvedPurpose = purpose || "section";

          // Resolve surface (background) style
          const surfaceClass =
            surface === "muted"
              ? "bg-surface-2"
              : surface === "primary"
                ? "bg-primary text-primary-foreground"
                : surface === "dark"
                  ? "bg-content text-white"
                  : "bg-surface";

          // Resolve content width
          const widthClass =
            contentWidth === "sm"
              ? "max-w-xl"
              : contentWidth === "md"
                ? "max-w-3xl"
                : contentWidth === "lg"
                  ? "max-w-5xl"
                  : contentWidth === "xl"
                    ? "max-w-7xl"
                    : "w-full";

          // Resolve vertical padding
          const padYClass =
            padY === "none"
              ? "py-0"
              : padY === "sm"
                ? "py-4"
                : padY === "lg"
                  ? "py-16"
                  : padY === "xl"
                    ? "py-24"
                    : "py-10";

          // Resolve horizontal padding
          const padXClass =
            padX === "none"
              ? "px-0"
              : padX === "sm"
                ? "px-3"
                : padX === "lg"
                  ? "px-8"
                  : "px-6";

          // Resolve content alignment
          const alignClass =
            contentAlign === "center"
              ? "text-center"
              : contentAlign === "right"
                ? "text-right"
                : "text-left";

          const innerContent = content ? content({ className: `space-y-5 ${alignClass}` }) : null;

          // Full bleed: background extends full width, content is contained
          if (bandWidth === "full") {
            return (
              <section className={`${surfaceClass} ${padYClass}`}>
                <div className={`mx-auto ${widthClass} ${padXClass}`}>{innerContent}</div>
              </section>
            );
          }

          // Contained: both background and content are contained
          return (
            <section className={`${padYClass}`}>
              <div className={`mx-auto ${widthClass} ${padXClass}`}>
                <div className={`rounded-2xl border border-border ${surfaceClass} shadow-sm p-6`}>
                  {innerContent}
                </div>
              </div>
            </section>
          );
        },
      },
      Columns: {
        fields: {
          ratio: {
            type: "select",
            options: [
              { label: "1:1", value: "1:1" },
              { label: "2:1", value: "2:1" },
              { label: "1:2", value: "1:2" },
            ],
          },
          gap: {
            type: "select",
            options: [
              { label: "Small", value: "sm" },
              { label: "Medium", value: "md" },
              { label: "Large", value: "lg" },
            ],
          },
          left: { type: "slot" },
          right: { type: "slot" },
        },
        defaultProps: { ratio: "1:1", gap: "md" },
        render: ({
          ratio,
          gap,
          left,
          right,
        }: {
          ratio?: "1:1" | "2:1" | "1:2";
          gap?: "sm" | "md" | "lg";
          left?: (props?: Record<string, unknown>) => ReactNode;
          right?: (props?: Record<string, unknown>) => ReactNode;
        }) => {
          const gridCols =
            ratio === "2:1"
              ? "md:grid-cols-[2fr_1fr]"
              : ratio === "1:2"
                ? "md:grid-cols-[1fr_2fr]"
                : "md:grid-cols-2";
          const gapClass = gap === "lg" ? "gap-10" : gap === "sm" ? "gap-4" : "gap-7";
          return (
            <div className={`grid ${gapClass} ${gridCols} items-start`}>
              <div className="space-y-4">{left ? left({ className: "space-y-4" }) : null}</div>
              <div className="space-y-4">{right ? right({ className: "space-y-4" }) : null}</div>
            </div>
          );
        },
      },
      FeatureGrid: {
        fields: {
          title: { type: "text" },
          columns: {
            type: "select",
            options: [
              { label: "2 columns", value: 2 },
              { label: "3 columns", value: 3 },
            ],
          },
          features: {
            type: "array",
            arrayFields: {
              title: { type: "text" },
              text: { type: "textarea" },
            },
            defaultItemProps: { title: "Feature", text: "" },
          },
        },
        defaultProps: {
          columns: 3,
          features: [
            { title: "Fast to read", text: "Scanable remedies you can apply immediately." },
            { title: "Ingredient guidance", text: "Clear, safe starting points and what to avoid." },
            { title: "Practical recipes", text: "Simple, at-home formulas and dosing notes." },
          ],
        },
        render: ({
          title,
          columns,
          features,
        }: {
          title?: string;
          columns?: number;
          features?: Array<{ title?: string; text?: string }>;
        }) => {
          const colClass = columns === 2 ? "md:grid-cols-2" : "md:grid-cols-3";
          return (
            <div className="space-y-4">
              {title ? <h3 className="text-xl font-semibold text-content">{title}</h3> : null}
              <div className={`grid gap-4 ${colClass}`}>
                {(features || []).map((f, idx) => (
                  <div key={idx} className="rounded-xl border border-border bg-surface p-5 shadow-sm">
                    <div className="text-base font-semibold text-content">{f.title || "Feature"}</div>
                    {f.text ? <div className="mt-2 text-sm leading-relaxed text-content-muted">{f.text}</div> : null}
                  </div>
                ))}
              </div>
            </div>
          );
        },
      },
      Testimonials: {
        fields: {
          title: { type: "text" },
          testimonials: {
            type: "array",
            arrayFields: {
              quote: { type: "textarea" },
              name: { type: "text" },
              role: { type: "text" },
            },
            defaultItemProps: { quote: "", name: "", role: "" },
          },
        },
        defaultProps: {
          title: "What readers are saying",
          testimonials: [
            { quote: "Clear, grounded, and easy to follow. I finally feel confident.", name: "Jamie", role: "Reader" },
            { quote: "The recipes are practical, and the safety notes are so helpful.", name: "Morgan", role: "Herbal enthusiast" },
          ],
        },
        render: ({
          title,
          testimonials,
        }: {
          title?: string;
          testimonials?: Array<{ quote?: string; name?: string; role?: string }>;
        }) => (
          <div className="space-y-4">
            {title ? <h3 className="text-xl font-semibold text-content">{title}</h3> : null}
            <div className="grid gap-4 md:grid-cols-2">
              {(testimonials || []).map((t, idx) => (
                <figure key={idx} className="rounded-xl border border-border bg-surface p-5 shadow-sm">
                  <blockquote className="text-sm leading-relaxed text-content">“{t.quote || ""}”</blockquote>
                  {(t.name || t.role) ? (
                    <figcaption className="mt-3 text-xs text-content-muted">
                      <span className="font-semibold text-content">{t.name || "Anonymous"}</span>
                      {t.role ? ` • ${t.role}` : ""}
                    </figcaption>
                  ) : null}
                </figure>
              ))}
            </div>
          </div>
        ),
      },
      FAQ: {
        fields: {
          title: { type: "text" },
          items: {
            type: "array",
            arrayFields: {
              question: { type: "text" },
              answer: { type: "textarea" },
            },
            defaultItemProps: { question: "Question", answer: "" },
          },
        },
        defaultProps: {
          title: "FAQ",
          items: [
            { question: "Is this medical advice?", answer: "No. This handbook is for educational purposes and does not replace professional care." },
            { question: "Do I need special ingredients?", answer: "No. Many recipes use common, accessible herbs and pantry items." },
            { question: "How do I get access?", answer: "After purchase, you’ll receive a link to download immediately." },
          ],
        },
        render: ({
          title,
          items,
        }: {
          title?: string;
          items?: Array<{ question?: string; answer?: string }>;
        }) => (
          <div className="space-y-4">
            {title ? <h3 className="text-xl font-semibold text-content">{title}</h3> : null}
            <div className="divide-y divide-border rounded-xl border border-border bg-surface shadow-sm">
              {(items || []).map((item, idx) => (
                <div key={idx} className="p-5">
                  <div className="text-sm font-semibold text-content">{item.question || "Question"}</div>
                  {item.answer ? <div className="mt-2 text-sm leading-relaxed text-content-muted">{item.answer}</div> : null}
                </div>
              ))}
            </div>
          </div>
        ),
      },
      Heading: {
        fields: {
          text: { type: "text" },
          level: {
            type: "select",
            options: [
              { label: "H1", value: 1 },
              { label: "H2", value: 2 },
              { label: "H3", value: 3 },
              { label: "H4", value: 4 },
            ],
          },
          align: {
            type: "select",
            options: [
              { label: "Left", value: "left" },
              { label: "Center", value: "center" },
            ],
          },
        },
        defaultProps: { level: 2, align: "left" },
        render: ({ text, level, align }: { text?: string; level?: number; align?: "left" | "center" }) => {
          const resolvedLevel = level === 1 || level === 3 || level === 4 ? level : 2;
          const Tag = resolvedLevel === 1 ? "h1" : resolvedLevel === 3 ? "h3" : resolvedLevel === 4 ? "h4" : "h2";
          const size =
            resolvedLevel === 1
              ? "text-4xl md:text-5xl"
              : resolvedLevel === 2
                ? "text-3xl"
                : resolvedLevel === 3
                  ? "text-2xl"
                  : "text-xl";
          const alignClass = align === "center" ? "text-center" : "text-left";
          return <Tag className={`${size} font-semibold text-content ${alignClass}`}>{text || "Heading"}</Tag>;
        },
      },
      Text: {
        fields: {
          text: { type: "textarea" },
          size: {
            type: "select",
            options: [
              { label: "Small", value: "sm" },
              { label: "Medium", value: "md" },
              { label: "Large", value: "lg" },
            ],
          },
          tone: {
            type: "select",
            options: [
              { label: "Default", value: "default" },
              { label: "Muted", value: "muted" },
            ],
          },
          align: {
            type: "select",
            options: [
              { label: "Left", value: "left" },
              { label: "Center", value: "center" },
            ],
          },
        },
        defaultProps: { size: "md", tone: "default", align: "left" },
        render: ({
          text,
          size,
          tone,
          align,
        }: {
          text?: string;
          size?: "sm" | "md" | "lg";
          tone?: "default" | "muted";
          align?: "left" | "center";
        }) => {
          const sizeClass = size === "lg" ? "text-lg" : size === "sm" ? "text-sm" : "text-base";
          const toneClass = tone === "muted" ? "text-content-muted" : "text-content";
          const alignClass = align === "center" ? "text-center" : "text-left";
          return <p className={`whitespace-pre-wrap ${sizeClass} leading-relaxed ${toneClass} ${alignClass}`}>{text || ""}</p>;
        },
      },
      Button: {
        fields: {
          label: { type: "text" },
          variant: {
            type: "select",
            options: [
              { label: "Primary", value: "primary" },
              { label: "Secondary", value: "secondary" },
            ],
          },
          size: {
            type: "select",
            options: [
              { label: "Small", value: "sm" },
              { label: "Medium", value: "md" },
              { label: "Large", value: "lg" },
            ],
          },
          width: {
            type: "select",
            options: [
              { label: "Auto", value: "auto" },
              { label: "Full width", value: "full" },
            ],
          },
          align: {
            type: "select",
            options: [
              { label: "Left", value: "left" },
              { label: "Center", value: "center" },
              { label: "Right", value: "right" },
            ],
          },
          linkType: {
            type: "select",
            options: [
              { label: "Funnel page", value: "funnelPage" },
              { label: "Next page", value: "nextPage" },
              { label: "External URL", value: "external" },
            ],
          },
          targetPageId: {
            type: "select",
            options: [{ label: "Select a page", value: "" }, ...pageOptions],
          },
          href: { type: "text" },
        },
        defaultProps: { variant: "primary", size: "md", width: "auto", align: "left", linkType: "funnelPage" },
        render: (props: ButtonProps) => <FunnelButton {...props} />,
      },
      Image: {
        fields: {
          prompt: { type: "textarea" },
          imageSource: {
            type: "select",
            options: [
              { label: "AI", value: "ai" },
              { label: "Unsplash", value: "unsplash" },
            ],
          },
          assetPublicId: { type: "text" },
          referenceAssetPublicId: { type: "text" },
          src: { type: "text" },
          alt: { type: "text" },
          radius: {
            type: "select",
            options: [
              { label: "Medium", value: "md" },
              { label: "Large", value: "lg" },
              { label: "None", value: "none" },
            ],
          },
        },
        defaultProps: { radius: "md" },
        render: (props: ImageProps) => <FunnelImage {...props} />,
      },
      SalesPdpPage: {
        fields: {
          anchorId: { type: "text" },
          schemaVersion: {
            type: "select",
            options: [
              { label: "Legacy", value: "legacy" },
              { label: "Import v1", value: "import-v1" },
            ],
          },
          themeJson: { type: "textarea" },
          content: { type: "slot" },
        },
        defaultProps: {
          anchorId: "top",
          schemaVersion: "legacy",
          theme: salesPdpDefaults.theme,
        },
        render: (props: Record<string, unknown>) => <SalesPdpPage {...props} />,
      },
      SalesPdpHeader: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.hero.header,
        },
        render: (props: Record<string, unknown>) => <SalesPdpHeader {...props} />,
      },
      SalesPdpHero: {
        fields: {
          configJson: { type: "textarea" },
          modalsJson: { type: "textarea" },
          copyJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.hero,
          modals: salesPdpDefaults.config.modals,
          copy: salesPdpDefaults.copy,
        },
        render: (props: Record<string, unknown>) => <SalesPdpHero {...props} />,
      },
      SalesPdpVideos: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.videos,
        },
        render: (props: Record<string, unknown>) => <SalesPdpVideos {...props} />,
      },
      SalesPdpMarquee: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.marquee,
        },
        render: (props: Record<string, unknown>) => <SalesPdpMarquee {...props} />,
      },
      SalesPdpStoryProblem: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.story.problem,
        },
        render: (props: Record<string, unknown>) => <SalesPdpStoryProblem {...props} />,
      },
      SalesPdpStorySolution: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.story.solution,
        },
        render: (props: Record<string, unknown>) => <SalesPdpStorySolution {...props} />,
      },
      SalesPdpComparison: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.comparison,
        },
        render: (props: Record<string, unknown>) => <SalesPdpComparison {...props} />,
      },
      SalesPdpGuarantee: {
        fields: {
          configJson: { type: "textarea" },
          feedImagesJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.guarantee,
          feedImages: salesPdpFeedImages,
        },
        render: (props: Record<string, unknown>) => <SalesPdpGuarantee {...props} />,
      },
      SalesPdpFaq: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.faq,
        },
        render: (props: Record<string, unknown>) => <SalesPdpFaq {...props} />,
      },
      SalesPdpReviews: {
        fields: {
          configJson: { type: "textarea" },
        },
        render: (props: Record<string, unknown>) => <SalesPdpReviews {...props} />,
      },
      SalesPdpReviewWall: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.reviewWall,
        },
        render: (props: Record<string, unknown>) => <SalesPdpReviewWall {...props} />,
      },
      SalesPdpFooter: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.footer,
        },
        render: (props: Record<string, unknown>) => <SalesPdpFooter {...props} />,
      },
      SalesPdpReviewSlider: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config.reviewSlider,
        },
        render: (props: Record<string, unknown>) => <SalesPdpReviewSlider {...props} />,
      },
      SalesPdpTemplate: {
        fields: {
          configJson: { type: "textarea" },
          copyJson: { type: "textarea" },
          themeJson: { type: "textarea" },
        },
        defaultProps: {
          config: salesPdpDefaults.config,
          copy: salesPdpDefaults.copy,
          theme: salesPdpDefaults.theme,
        },
        render: (props: Record<string, unknown>) => <SalesPdpTemplate {...props} />,
      },
      PreSalesPage: {
        fields: {
          anchorId: { type: "text" },
          themeJson: { type: "textarea" },
          content: { type: "slot" },
        },
        defaultProps: {
          anchorId: "top",
          theme: preSalesDefaults.theme,
        },
        render: (props: Record<string, unknown>) => <PreSalesPage {...props} />,
      },
      PreSalesHero: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: {
            hero: preSalesDefaults.config.hero,
            badges: preSalesDefaults.config.badges,
          },
        },
        render: withBlockBoundary("PreSalesHero", (props: Record<string, unknown>) => <PreSalesHero {...props} />),
      },
      PreSalesReasons: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: preSalesDefaults.config.reasons,
        },
        render: withBlockBoundary("PreSalesReasons", (props: Record<string, unknown>) => <PreSalesReasons {...props} />),
      },
      PreSalesReviews: {
        fields: {
          configJson: { type: "textarea" },
          copyJson: { type: "textarea" },
        },
        defaultProps: {
          config: preSalesDefaults.config.reviews,
          copy: preSalesDefaults.copy,
        },
        render: withBlockBoundary("PreSalesReviews", (props: Record<string, unknown>) => <PreSalesReviews {...props} />),
      },
      PreSalesMarquee: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: preSalesDefaults.config.marquee,
        },
        render: withBlockBoundary("PreSalesMarquee", (props: Record<string, unknown>) => <PreSalesMarquee {...props} />),
      },
      PreSalesPitch: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: preSalesDefaults.config.pitch,
        },
        render: withBlockBoundary("PreSalesPitch", (props: Record<string, unknown>) => <PreSalesPitch {...props} />),
      },
      PreSalesReviewWall: {
        fields: {
          configJson: { type: "textarea" },
          copyJson: { type: "textarea" },
        },
        defaultProps: {
          config: preSalesDefaults.config.reviewsWall,
          copy: preSalesDefaults.copy,
        },
        render: withBlockBoundary("PreSalesReviewWall", (props: Record<string, unknown>) => <PreSalesReviewWall {...props} />),
      },
      PreSalesFooter: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: preSalesDefaults.config.footer,
        },
        render: withBlockBoundary("PreSalesFooter", (props: Record<string, unknown>) => <PreSalesFooter {...props} />),
      },
      PreSalesFloatingCta: {
        fields: {
          configJson: { type: "textarea" },
        },
        defaultProps: {
          config: preSalesDefaults.config.floatingCta,
        },
        render: withBlockBoundary("PreSalesFloatingCta", (props: Record<string, unknown>) => <PreSalesFloatingCta {...props} />),
      },
      PreSalesTemplate: {
        fields: {
          configJson: { type: "textarea" },
          copyJson: { type: "textarea" },
          themeJson: { type: "textarea" },
        },
        defaultProps: {
          config: preSalesDefaults.config,
          copy: preSalesDefaults.copy,
          theme: preSalesDefaults.theme,
        },
        render: withBlockBoundary("PreSalesTemplate", (props: Record<string, unknown>) => <PreSalesTemplate {...props} />),
      },
      // Commerce blocks for site pages - render from runtime commerce data
      CommerceCatalogHero: {
        fields: {
          title: { type: "text" },
          description: { type: "textarea" },
        },
        defaultProps: {},
        render: withBlockBoundary("CommerceCatalogHero", (props: Record<string, unknown>) => (
          <CommerceCatalogHero
            title={typeof props.title === "string" ? props.title : undefined}
            description={typeof props.description === "string" ? props.description : undefined}
          />
        )),
      },
      CommerceProductGrid: {
        fields: {
          columns: {
            type: "select",
            options: [
              { label: "2 columns", value: 2 },
              { label: "3 columns", value: 3 },
              { label: "4 columns", value: 4 },
            ],
          },
        },
        defaultProps: { columns: 3 },
        render: withBlockBoundary("CommerceProductGrid", (props: Record<string, unknown>) => (
          <CommerceProductGrid
            columns={typeof props.columns === "number" ? props.columns : 3}
          />
        )),
      },
      CommerceProductDetail: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("CommerceProductDetail", () => <CommerceProductDetail />),
      },
      CommerceCart: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("CommerceCart", () => <CommerceCart />),
      },
      CommerceCheckout: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("CommerceCheckout", () => <CommerceCheckout />),
      },
      CommerceCategoryList: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("CommerceCategoryList", () => <CommerceCategoryList />),
      },
      CommerceCategoryHeading: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("CommerceCategoryHeading", () => <CommerceCategoryHeading />),
      },
      CommerceCartSummary: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("CommerceCartSummary", () => <CommerceCartSummary />),
      },
      CommerceStoreHeader: {
        fields: {
          storeName: { type: "text" },
          showSearch: { type: "checkbox" },
          showCart: { type: "checkbox" },
        },
        defaultProps: { storeName: "Store", showSearch: false, showCart: true },
        render: withBlockBoundary("CommerceStoreHeader", (props: Record<string, unknown>) => (
          <CommerceStoreHeader
            storeName={typeof props.storeName === "string" ? props.storeName : "Store"}
            showSearch={props.showSearch === true}
            showCart={props.showCart !== false}
          />
        )),
      },
      CommerceStoreFooter: {
        fields: {
          storeName: { type: "text" },
          showCategories: { type: "checkbox" },
          showCollections: { type: "checkbox" },
        },
        defaultProps: { storeName: "Store", showCategories: true, showCollections: true },
        render: withBlockBoundary("CommerceStoreFooter", (props: Record<string, unknown>) => (
          <CommerceStoreFooter
            storeName={typeof props.storeName === "string" ? props.storeName : "Store"}
            showCategories={props.showCategories !== false}
            showCollections={props.showCollections !== false}
          />
        )),
      },
      StarterStoreHeader: {
        fields: {
          storeName: { type: "text" },
          showSearch: { type: "checkbox" },
          showCart: { type: "checkbox" },
        },
        defaultProps: { storeName: "Store", showSearch: true, showCart: true },
        render: withBlockBoundary("StarterStoreHeader", (props: Record<string, unknown>) => (
          <StarterStoreHeader
            storeName={typeof props.storeName === "string" ? props.storeName : "Store"}
            showSearch={props.showSearch !== false}
            showCart={props.showCart !== false}
          />
        )),
      },
      StarterPromoBar: {
        fields: {
          message: { type: "text" },
          ctaLabel: { type: "text" },
          linkType: {
            type: "select",
            options: [
              { label: "Funnel page", value: "funnelPage" },
              { label: "Next page", value: "nextPage" },
              { label: "External URL", value: "external" },
            ],
          },
          targetPageId: {
            type: "select",
            options: [{ label: "Select a page", value: "" }, ...pageOptions],
          },
          href: { type: "text" },
        },
        defaultProps: {
          message: "Practical tools for herbal practitioners and wellness professionals.",
          ctaLabel: "Browse catalog",
          linkType: "funnelPage",
          targetPageId: "",
          href: "",
        },
        render: withBlockBoundary("StarterPromoBar", (props: Record<string, unknown>) => (
          <StarterPromoBar
            message={typeof props.message === "string" ? props.message : undefined}
            ctaLabel={typeof props.ctaLabel === "string" ? props.ctaLabel : undefined}
            linkType={
              props.linkType === "external" || props.linkType === "nextPage" || props.linkType === "funnelPage"
                ? props.linkType
                : undefined
            }
            targetPageId={typeof props.targetPageId === "string" ? props.targetPageId : undefined}
            href={typeof props.href === "string" ? props.href : undefined}
          />
        )),
      },
      StarterHomeHero: {
        fields: {
          eyebrow: { type: "text" },
          title: { type: "text" },
          description: { type: "textarea" },
          primaryCtaLabel: { type: "text" },
          primaryLinkType: {
            type: "select",
            options: [
              { label: "Funnel page", value: "funnelPage" },
              { label: "Next page", value: "nextPage" },
              { label: "External URL", value: "external" },
            ],
          },
          primaryTargetPageId: {
            type: "select",
            options: [{ label: "Select a page", value: "" }, ...pageOptions],
          },
          primaryHref: { type: "text" },
          featuredProductHandles: {
            type: "array",
            arrayFields: {
              value: { type: "text" },
            },
            defaultItemProps: { value: "" },
          },
        },
        defaultProps: {
          eyebrow: "Honest Herbalist",
          title: "Practical tools for herbal practitioners",
          description: "Explore reference materials, worksheet pads, and client-facing tools grounded in the live catalog.",
          primaryCtaLabel: "Browse catalog",
          primaryLinkType: "funnelPage",
          primaryTargetPageId: "",
          primaryHref: "",
          featuredProductHandles: [{ value: "the-honest-herbalist-handbook" }],
        },
        render: withBlockBoundary("StarterHomeHero", (props: Record<string, unknown>) => (
          <StarterHomeHero
            eyebrow={typeof props.eyebrow === "string" ? props.eyebrow : undefined}
            title={typeof props.title === "string" ? props.title : undefined}
            description={typeof props.description === "string" ? props.description : undefined}
            primaryCtaLabel={typeof props.primaryCtaLabel === "string" ? props.primaryCtaLabel : undefined}
            primaryLinkType={
              props.primaryLinkType === "external" || props.primaryLinkType === "nextPage" || props.primaryLinkType === "funnelPage"
                ? props.primaryLinkType
                : undefined
            }
            primaryTargetPageId={typeof props.primaryTargetPageId === "string" ? props.primaryTargetPageId : undefined}
            primaryHref={typeof props.primaryHref === "string" ? props.primaryHref : undefined}
            featuredProductHandles={
              Array.isArray(props.featuredProductHandles)
                ? props.featuredProductHandles
                    .map((item) => {
                      if (typeof item === "string") return item;
                      if (item && typeof item === "object" && typeof (item as { value?: unknown }).value === "string") {
                        return (item as { value: string }).value;
                      }
                      return "";
                    })
                    .filter(Boolean)
                : undefined
            }
          />
        )),
      },
      StarterPolicyPage: {
        fields: {
          pageKey: {
            type: "select",
            options: [
              { label: "Privacy Policy", value: "privacy_policy" },
              { label: "Terms of Service", value: "terms_of_service" },
              { label: "Returns and Refunds", value: "returns_refunds_policy" },
              { label: "Shipping Policy", value: "shipping_policy" },
              { label: "Contact and Support", value: "contact_support" },
            ],
          },
          pageTitle: { type: "text" },
        },
        defaultProps: {
          pageKey: "privacy_policy",
          pageTitle: "Privacy Policy",
        },
        render: withBlockBoundary("StarterPolicyPage", (props: Record<string, unknown>) => (
          <StarterPolicyPage
            pageKey={
              props.pageKey === "privacy_policy" ||
              props.pageKey === "terms_of_service" ||
              props.pageKey === "returns_refunds_policy" ||
              props.pageKey === "shipping_policy" ||
              props.pageKey === "contact_support"
                ? props.pageKey
                : "privacy_policy"
            }
            pageTitle={typeof props.pageTitle === "string" ? props.pageTitle : undefined}
          />
        )),
      },
      StarterCollectionRails: {
        fields: {
          maxCollections: { type: "number" },
          productsPerCollection: { type: "number" },
        },
        defaultProps: { maxCollections: 3, productsPerCollection: 4 },
        render: withBlockBoundary("StarterCollectionRails", (props: Record<string, unknown>) => (
          <StarterCollectionRails
            maxCollections={typeof props.maxCollections === "number" ? props.maxCollections : 3}
            productsPerCollection={typeof props.productsPerCollection === "number" ? props.productsPerCollection : 4}
          />
        )),
      },
      StarterStoreFooter: {
        fields: {
          storeName: { type: "text" },
          showCategories: { type: "checkbox" },
          showCollections: { type: "checkbox" },
        },
        defaultProps: { storeName: "Store", showCategories: true, showCollections: true },
        render: withBlockBoundary("StarterStoreFooter", (props: Record<string, unknown>) => (
          <StarterStoreFooter
            storeName={typeof props.storeName === "string" ? props.storeName : "Store"}
            showCategories={props.showCategories !== false}
            showCollections={props.showCollections !== false}
          />
        )),
      },
      CommerceStoreTemplate: {
        fields: {
          content: { type: "slot" },
        },
        defaultProps: {},
        render: withBlockBoundary("CommerceStoreTemplate", (props: Record<string, unknown>) => (
          <CommerceStoreTemplate>
            {typeof props.content === "function" ? props.content({ className: "space-y-5" }) : null}
          </CommerceStoreTemplate>
        )),
      },
      MedusaB2CHomePage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CHomePage", () => <MedusaB2CHomePage />),
      },
      MedusaB2CStorePage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CStorePage", () => <MedusaB2CStorePage />),
      },
      MedusaB2CCollectionPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CCollectionPage", () => <MedusaB2CCollectionPage />),
      },
      MedusaB2CCategoryPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CCategoryPage", () => <MedusaB2CCategoryPage />),
      },
      MedusaB2CProductPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CProductPage", () => <MedusaB2CProductPage />),
      },
      MedusaB2CCartPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CCartPage", () => <MedusaB2CCartPage />),
      },
      MedusaB2CCheckoutPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CCheckoutPage", () => <MedusaB2CCheckoutPage />),
      },
      MedusaB2CPolicyPage: {
        fields: {
          pageKey: {
            type: "select",
            options: [
              { label: "Privacy Policy", value: "privacy_policy" },
              { label: "Terms of Service", value: "terms_of_service" },
              { label: "Refund Policy", value: "returns_refunds_policy" },
              { label: "Shipping Policy", value: "shipping_policy" },
              { label: "Contact Support", value: "contact_support" },
            ],
          },
          pageTitle: { type: "text" },
          description: { type: "textarea" },
        },
        defaultProps: {
          pageKey: "privacy_policy",
          pageTitle: "Privacy Policy",
        },
        render: withBlockBoundary(
          "MedusaB2CPolicyPage",
          (props: { pageKey: string; pageTitle?: string; description?: string }) => (
            <MedusaB2CPolicyPage
              pageKey={props.pageKey as
                | "privacy_policy"
                | "terms_of_service"
                | "returns_refunds_policy"
                | "shipping_policy"
                | "contact_support"}
              pageTitle={props.pageTitle}
              description={props.description}
            />
          ),
        ),
      },
      MedusaB2CAccountDashboardPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CAccountDashboardPage", () => <MedusaB2CAccountDashboardPage />),
      },
      MedusaB2CAccountProfilePage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CAccountProfilePage", () => <MedusaB2CAccountProfilePage />),
      },
      MedusaB2CAccountAddressesPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CAccountAddressesPage", () => <MedusaB2CAccountAddressesPage />),
      },
      MedusaB2CAccountOrdersPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CAccountOrdersPage", () => <MedusaB2CAccountOrdersPage />),
      },
      MedusaB2CAccountOrderDetailPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2CAccountOrderDetailPage", () => <MedusaB2CAccountOrderDetailPage />),
      },
      MedusaB2COrderConfirmedPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2COrderConfirmedPage", () => <MedusaB2COrderConfirmedPage />),
      },
      MedusaB2COrderTransferPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2COrderTransferPage", () => <MedusaB2COrderTransferPage />),
      },
      MedusaB2COrderTransferAcceptPage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2COrderTransferAcceptPage", () => <MedusaB2COrderTransferAcceptPage />),
      },
      MedusaB2COrderTransferDeclinePage: {
        fields: {},
        defaultProps: {},
        render: withBlockBoundary("MedusaB2COrderTransferDeclinePage", () => <MedusaB2COrderTransferDeclinePage />),
      },
      Spacer: {
        fields: {
          height: { type: "number" },
        },
        render: ({ height }: { height?: number }) => <div style={{ height: Math.max(0, height || 24) }} />,
      },
      ImportedPage: {
        fields: {
          pageName: { type: "text" },
          themeJson: { type: "textarea" },
          content: { type: "slot" },
        },
        defaultProps: {
          pageName: "Imported Page",
        },
        render: withBlockBoundary("ImportedPage", (props: Record<string, unknown>) => (
          <ImportedPage
            pageName={typeof props.pageName === "string" ? props.pageName : undefined}
            theme={props.theme}
            themeJson={typeof props.themeJson === "string" ? props.themeJson : undefined}
            renderMode={typeof props.renderMode === "string" ? props.renderMode : undefined}
            sharedRuntimeSource={
              typeof props.sharedRuntimeSource === "string" ? props.sharedRuntimeSource : undefined
            }
            sharedHeadAssets={props.sharedHeadAssets}
            content={typeof props.content === "function" ? props.content : undefined}
          />
        )),
      },
      ImportedSection: {
        fields: {
          displayName: { type: "text" },
          sourceSectionId: { type: "text" },
          sectionKey: { type: "text" },
          sectionType: { type: "text" },
          semanticTagsText: { type: "text" },
          surface: {
            type: "select",
            options: [
              { label: "Source", value: "source" },
              { label: "Default", value: "default" },
              { label: "Muted", value: "muted" },
              { label: "Primary", value: "primary" },
            ],
          },
          content: { type: "slot" },
        },
        defaultProps: {
          surface: "default",
        },
        render: withBlockBoundary("ImportedSection", (props: Record<string, unknown>) => (
          <ImportedSection
            displayName={typeof props.displayName === "string" ? props.displayName : undefined}
            sourceSectionId={typeof props.sourceSectionId === "string" ? props.sourceSectionId : undefined}
            sectionKey={typeof props.sectionKey === "string" ? props.sectionKey : undefined}
            sectionType={typeof props.sectionType === "string" ? props.sectionType : undefined}
            semanticTagsText={typeof props.semanticTagsText === "string" ? props.semanticTagsText : undefined}
            surface={typeof props.surface === "string" ? props.surface : undefined}
            renderMode={typeof props.renderMode === "string" ? props.renderMode : undefined}
            content={typeof props.content === "function" ? props.content : undefined}
          />
        )),
      },
      ImportedHeaderSection: createImportedSourceSectionBlockConfig(
        "ImportedHeaderSection",
        (props: Record<string, unknown>) => (
          <ImportedHeaderSection
            id={typeof props.id === "string" ? props.id : undefined}
            sectionLabel={typeof props.sectionLabel === "string" ? props.sectionLabel : undefined}
            componentName={typeof props.componentName === "string" ? props.componentName : undefined}
            sectionTargetId={typeof props.sectionTargetId === "string" ? props.sectionTargetId : undefined}
            textSlots={Array.isArray(props.textSlots) ? (props.textSlots as Array<Record<string, unknown>>) : undefined}
            buttonSlots={
              Array.isArray(props.buttonSlots) ? (props.buttonSlots as Array<Record<string, unknown>>) : undefined
            }
            imageSlots={Array.isArray(props.imageSlots) ? (props.imageSlots as Array<Record<string, unknown>>) : undefined}
          />
        ),
      ),
      ImportedHeroSection: createImportedSourceSectionBlockConfig(
        "ImportedHeroSection",
        (props: Record<string, unknown>) => (
          <ImportedHeroSection
            id={typeof props.id === "string" ? props.id : undefined}
            sectionLabel={typeof props.sectionLabel === "string" ? props.sectionLabel : undefined}
            componentName={typeof props.componentName === "string" ? props.componentName : undefined}
            sectionTargetId={typeof props.sectionTargetId === "string" ? props.sectionTargetId : undefined}
            textSlots={Array.isArray(props.textSlots) ? (props.textSlots as Array<Record<string, unknown>>) : undefined}
            buttonSlots={
              Array.isArray(props.buttonSlots) ? (props.buttonSlots as Array<Record<string, unknown>>) : undefined
            }
            imageSlots={Array.isArray(props.imageSlots) ? (props.imageSlots as Array<Record<string, unknown>>) : undefined}
          />
        ),
      ),
      ImportedProofBarSection: createImportedSourceSectionBlockConfig(
        "ImportedProofBarSection",
        (props: Record<string, unknown>) => (
          <ImportedProofBarSection
            id={typeof props.id === "string" ? props.id : undefined}
            sectionLabel={typeof props.sectionLabel === "string" ? props.sectionLabel : undefined}
            componentName={typeof props.componentName === "string" ? props.componentName : undefined}
            sectionTargetId={typeof props.sectionTargetId === "string" ? props.sectionTargetId : undefined}
            textSlots={Array.isArray(props.textSlots) ? (props.textSlots as Array<Record<string, unknown>>) : undefined}
            buttonSlots={
              Array.isArray(props.buttonSlots) ? (props.buttonSlots as Array<Record<string, unknown>>) : undefined
            }
            imageSlots={Array.isArray(props.imageSlots) ? (props.imageSlots as Array<Record<string, unknown>>) : undefined}
          />
        ),
      ),
      ImportedFeatureSection: createImportedSourceSectionBlockConfig(
        "ImportedFeatureSection",
        (props: Record<string, unknown>) => (
          <ImportedFeatureSection
            id={typeof props.id === "string" ? props.id : undefined}
            sectionLabel={typeof props.sectionLabel === "string" ? props.sectionLabel : undefined}
            componentName={typeof props.componentName === "string" ? props.componentName : undefined}
            sectionTargetId={typeof props.sectionTargetId === "string" ? props.sectionTargetId : undefined}
            textSlots={Array.isArray(props.textSlots) ? (props.textSlots as Array<Record<string, unknown>>) : undefined}
            buttonSlots={
              Array.isArray(props.buttonSlots) ? (props.buttonSlots as Array<Record<string, unknown>>) : undefined
            }
            imageSlots={Array.isArray(props.imageSlots) ? (props.imageSlots as Array<Record<string, unknown>>) : undefined}
          />
        ),
      ),
      ImportedOfferSection: createImportedSourceSectionBlockConfig(
        "ImportedOfferSection",
        (props: Record<string, unknown>) => (
          <ImportedOfferSection
            id={typeof props.id === "string" ? props.id : undefined}
            sectionLabel={typeof props.sectionLabel === "string" ? props.sectionLabel : undefined}
            componentName={typeof props.componentName === "string" ? props.componentName : undefined}
            sectionTargetId={typeof props.sectionTargetId === "string" ? props.sectionTargetId : undefined}
            textSlots={Array.isArray(props.textSlots) ? (props.textSlots as Array<Record<string, unknown>>) : undefined}
            buttonSlots={
              Array.isArray(props.buttonSlots) ? (props.buttonSlots as Array<Record<string, unknown>>) : undefined
            }
            imageSlots={Array.isArray(props.imageSlots) ? (props.imageSlots as Array<Record<string, unknown>>) : undefined}
          />
        ),
      ),
      ImportedTestimonialsSection: createImportedSourceSectionBlockConfig(
        "ImportedTestimonialsSection",
        (props: Record<string, unknown>) => (
          <ImportedTestimonialsSection
            id={typeof props.id === "string" ? props.id : undefined}
            sectionLabel={typeof props.sectionLabel === "string" ? props.sectionLabel : undefined}
            componentName={typeof props.componentName === "string" ? props.componentName : undefined}
            sectionTargetId={typeof props.sectionTargetId === "string" ? props.sectionTargetId : undefined}
            textSlots={Array.isArray(props.textSlots) ? (props.textSlots as Array<Record<string, unknown>>) : undefined}
            buttonSlots={
              Array.isArray(props.buttonSlots) ? (props.buttonSlots as Array<Record<string, unknown>>) : undefined
            }
            imageSlots={Array.isArray(props.imageSlots) ? (props.imageSlots as Array<Record<string, unknown>>) : undefined}
          />
        ),
      ),
      ImportedComparisonSection: createImportedSourceSectionBlockConfig(
        "ImportedComparisonSection",
        (props: Record<string, unknown>) => (
          <ImportedComparisonSection
            id={typeof props.id === "string" ? props.id : undefined}
            sectionLabel={typeof props.sectionLabel === "string" ? props.sectionLabel : undefined}
            componentName={typeof props.componentName === "string" ? props.componentName : undefined}
            sectionTargetId={typeof props.sectionTargetId === "string" ? props.sectionTargetId : undefined}
            textSlots={Array.isArray(props.textSlots) ? (props.textSlots as Array<Record<string, unknown>>) : undefined}
            buttonSlots={
              Array.isArray(props.buttonSlots) ? (props.buttonSlots as Array<Record<string, unknown>>) : undefined
            }
            imageSlots={Array.isArray(props.imageSlots) ? (props.imageSlots as Array<Record<string, unknown>>) : undefined}
          />
        ),
      ),
      ImportedFaqSection: createImportedSourceSectionBlockConfig(
        "ImportedFaqSection",
        (props: Record<string, unknown>) => (
          <ImportedFaqSection
            id={typeof props.id === "string" ? props.id : undefined}
            sectionLabel={typeof props.sectionLabel === "string" ? props.sectionLabel : undefined}
            componentName={typeof props.componentName === "string" ? props.componentName : undefined}
            sectionTargetId={typeof props.sectionTargetId === "string" ? props.sectionTargetId : undefined}
            textSlots={Array.isArray(props.textSlots) ? (props.textSlots as Array<Record<string, unknown>>) : undefined}
            buttonSlots={
              Array.isArray(props.buttonSlots) ? (props.buttonSlots as Array<Record<string, unknown>>) : undefined
            }
            imageSlots={Array.isArray(props.imageSlots) ? (props.imageSlots as Array<Record<string, unknown>>) : undefined}
          />
        ),
      ),
      ImportedFooterSection: createImportedSourceSectionBlockConfig(
        "ImportedFooterSection",
        (props: Record<string, unknown>) => (
          <ImportedFooterSection
            id={typeof props.id === "string" ? props.id : undefined}
            sectionLabel={typeof props.sectionLabel === "string" ? props.sectionLabel : undefined}
            componentName={typeof props.componentName === "string" ? props.componentName : undefined}
            sectionTargetId={typeof props.sectionTargetId === "string" ? props.sectionTargetId : undefined}
            textSlots={Array.isArray(props.textSlots) ? (props.textSlots as Array<Record<string, unknown>>) : undefined}
            buttonSlots={
              Array.isArray(props.buttonSlots) ? (props.buttonSlots as Array<Record<string, unknown>>) : undefined
            }
            imageSlots={Array.isArray(props.imageSlots) ? (props.imageSlots as Array<Record<string, unknown>>) : undefined}
          />
        ),
      ),
      ImportedNarrativeBlock: {
        fields: {
          eyebrow: { type: "text" },
          title: { type: "text" },
          body: { type: "textarea" },
          quote: { type: "textarea" },
          imageSrc: { type: "text" },
          imageAlt: { type: "text" },
          mediaPosition: {
            type: "select",
            options: [
              { label: "Right", value: "right" },
              { label: "Left", value: "left" },
            ],
          },
          align: {
            type: "select",
            options: [
              { label: "Left", value: "left" },
              { label: "Center", value: "center" },
            ],
          },
          badges: {
            type: "array",
            arrayFields: {
              label: { type: "text" },
            },
            defaultItemProps: { label: "" },
          },
          buttons: {
            type: "array",
            arrayFields: {
              label: { type: "text" },
              href: { type: "text" },
            },
            defaultItemProps: { label: "", href: "" },
          },
        },
        defaultProps: {
          mediaPosition: "right",
          align: "left",
          badges: [],
          buttons: [],
        },
        render: withBlockBoundary("ImportedNarrativeBlock", (props: Record<string, unknown>) => (
          <ImportedNarrativeBlock
            eyebrow={typeof props.eyebrow === "string" ? props.eyebrow : undefined}
            title={typeof props.title === "string" ? props.title : undefined}
            body={typeof props.body === "string" ? props.body : undefined}
            quote={typeof props.quote === "string" ? props.quote : undefined}
            imageSrc={typeof props.imageSrc === "string" ? props.imageSrc : undefined}
            imageAlt={typeof props.imageAlt === "string" ? props.imageAlt : undefined}
            mediaPosition={props.mediaPosition === "left" ? "left" : "right"}
            align={props.align === "center" ? "center" : "left"}
            badges={Array.isArray(props.badges) ? (props.badges as Array<{ label?: string }>) : undefined}
            buttons={Array.isArray(props.buttons) ? (props.buttons as Array<{ label?: string; href?: string }>) : undefined}
          />
        )),
      },
      ImportedItemGrid: {
        fields: {
          title: { type: "text" },
          body: { type: "textarea" },
          columns: {
            type: "select",
            options: [
              { label: "1 column", value: 1 },
              { label: "2 columns", value: 2 },
              { label: "3 columns", value: 3 },
              { label: "4 columns", value: 4 },
            ],
          },
          items: {
            type: "array",
            arrayFields: {
              label: { type: "text" },
              title: { type: "text" },
              text: { type: "textarea" },
              value: { type: "text" },
            },
            defaultItemProps: { label: "", title: "", text: "", value: "" },
          },
        },
        defaultProps: {
          columns: 3,
          items: [],
        },
        render: withBlockBoundary("ImportedItemGrid", (props: Record<string, unknown>) => (
          <ImportedItemGrid
            title={typeof props.title === "string" ? props.title : undefined}
            body={typeof props.body === "string" ? props.body : undefined}
            columns={typeof props.columns === "number" ? props.columns : undefined}
            items={Array.isArray(props.items) ? (props.items as Array<{ label?: string; title?: string; text?: string; value?: string }>) : undefined}
          />
        )),
      },
      ImportedBadgeStrip: {
        fields: {
          title: { type: "text" },
          items: {
            type: "array",
            arrayFields: {
              label: { type: "text" },
            },
            defaultItemProps: { label: "" },
          },
        },
        defaultProps: {
          items: [],
        },
        render: withBlockBoundary("ImportedBadgeStrip", (props: Record<string, unknown>) => (
          <ImportedBadgeStrip
            title={typeof props.title === "string" ? props.title : undefined}
            items={Array.isArray(props.items) ? (props.items as Array<{ label?: string }>) : undefined}
          />
        )),
      },
      ImportedOfferSelector: {
        fields: {
          eyebrow: { type: "text" },
          title: { type: "text" },
          body: { type: "textarea" },
          reviewText: { type: "text" },
          ctaLabel: { type: "text" },
          galleryImages: {
            type: "array",
            arrayFields: {
              src: { type: "text" },
              alt: { type: "text" },
            },
            defaultItemProps: { src: "", alt: "" },
          },
          benefits: {
            type: "array",
            arrayFields: {
              text: { type: "text" },
            },
            defaultItemProps: { text: "" },
          },
          offers: {
            type: "array",
            arrayFields: {
              title: { type: "text" },
              subtitle: { type: "text" },
              price: { type: "text" },
              total: { type: "text" },
              regularPrice: { type: "text" },
              savings: { type: "text" },
              badge: { type: "text" },
            },
            defaultItemProps: {
              title: "",
              subtitle: "",
              price: "",
              total: "",
              regularPrice: "",
              savings: "",
              badge: "",
            },
          },
        },
        defaultProps: {
          galleryImages: [],
          benefits: [],
          offers: [],
        },
        render: withBlockBoundary("ImportedOfferSelector", (props: Record<string, unknown>) => (
          <ImportedOfferSelector
            eyebrow={typeof props.eyebrow === "string" ? props.eyebrow : undefined}
            title={typeof props.title === "string" ? props.title : undefined}
            body={typeof props.body === "string" ? props.body : undefined}
            reviewText={typeof props.reviewText === "string" ? props.reviewText : undefined}
            ctaLabel={typeof props.ctaLabel === "string" ? props.ctaLabel : undefined}
            galleryImages={Array.isArray(props.galleryImages) ? (props.galleryImages as Array<{ src?: string; alt?: string }>) : undefined}
            benefits={Array.isArray(props.benefits) ? (props.benefits as Array<{ text?: string }>) : undefined}
            offers={Array.isArray(props.offers) ? (props.offers as Array<{ title?: string; subtitle?: string; price?: string; total?: string; regularPrice?: string; savings?: string; badge?: string }>) : undefined}
          />
        )),
      },
      ImportedTestimonialsGrid: {
        fields: {
          title: { type: "text" },
          body: { type: "textarea" },
          items: {
            type: "array",
            arrayFields: {
              name: { type: "text" },
              quote: { type: "textarea" },
              role: { type: "text" },
              imageSrc: { type: "text" },
            },
            defaultItemProps: { name: "", quote: "", role: "", imageSrc: "" },
          },
        },
        defaultProps: {
          items: [],
        },
        render: withBlockBoundary("ImportedTestimonialsGrid", (props: Record<string, unknown>) => (
          <ImportedTestimonialsGrid
            title={typeof props.title === "string" ? props.title : undefined}
            body={typeof props.body === "string" ? props.body : undefined}
            items={Array.isArray(props.items) ? (props.items as Array<{ name?: string; quote?: string; role?: string; imageSrc?: string }>) : undefined}
          />
        )),
      },
      ImportedComparisonTable: {
        fields: {
          title: { type: "text" },
          body: { type: "textarea" },
          primaryLabel: { type: "text" },
          secondaryLabel: { type: "text" },
          tertiaryLabel: { type: "text" },
          rows: {
            type: "array",
            arrayFields: {
              feature: { type: "text" },
              primaryValue: { type: "text" },
              secondaryValue: { type: "text" },
              tertiaryValue: { type: "text" },
            },
            defaultItemProps: { feature: "", primaryValue: "", secondaryValue: "", tertiaryValue: "" },
          },
        },
        defaultProps: {
          rows: [],
        },
        render: withBlockBoundary("ImportedComparisonTable", (props: Record<string, unknown>) => (
          <ImportedComparisonTable
            title={typeof props.title === "string" ? props.title : undefined}
            body={typeof props.body === "string" ? props.body : undefined}
            primaryLabel={typeof props.primaryLabel === "string" ? props.primaryLabel : undefined}
            secondaryLabel={typeof props.secondaryLabel === "string" ? props.secondaryLabel : undefined}
            tertiaryLabel={typeof props.tertiaryLabel === "string" ? props.tertiaryLabel : undefined}
            rows={Array.isArray(props.rows) ? (props.rows as Array<{ feature?: string; primaryValue?: string; secondaryValue?: string; tertiaryValue?: string }>) : undefined}
          />
        )),
      },
      ImportedAccordion: {
        fields: {
          title: { type: "text" },
          body: { type: "textarea" },
          items: {
            type: "array",
            arrayFields: {
              question: { type: "text" },
              answer: { type: "textarea" },
            },
            defaultItemProps: { question: "", answer: "" },
          },
        },
        defaultProps: {
          items: [],
        },
        render: withBlockBoundary("ImportedAccordion", (props: Record<string, unknown>) => (
          <ImportedAccordion
            title={typeof props.title === "string" ? props.title : undefined}
            body={typeof props.body === "string" ? props.body : undefined}
            items={Array.isArray(props.items) ? (props.items as Array<{ question?: string; answer?: string }>) : undefined}
          />
        )),
      },
      ImportedFooterLinks: {
        fields: {
          brandName: { type: "text" },
          body: { type: "textarea" },
          legalText: { type: "textarea" },
          links: {
            type: "array",
            arrayFields: {
              label: { type: "text" },
              href: { type: "text" },
            },
            defaultItemProps: { label: "", href: "" },
          },
        },
        defaultProps: {
          links: [],
        },
        render: withBlockBoundary("ImportedFooterLinks", (props: Record<string, unknown>) => (
          <ImportedFooterLinks
            brandName={typeof props.brandName === "string" ? props.brandName : undefined}
            body={typeof props.body === "string" ? props.body : undefined}
            legalText={typeof props.legalText === "string" ? props.legalText : undefined}
            links={Array.isArray(props.links) ? (props.links as Array<{ label?: string; href?: string }>) : undefined}
          />
        )),
      },
      ImportedRuntimeSection: {
        fields: {
          textOverrides: {
            type: "array",
            arrayFields: {
              label: { type: "text" },
              originalText: { type: "textarea" },
              text: { type: "textarea" },
            },
            defaultItemProps: { label: "", originalText: "", text: "" },
          },
          buttonOverrides: {
            type: "array",
            arrayFields: {
              label: { type: "text" },
              originalText: { type: "text" },
              text: { type: "text" },
              href: { type: "text" },
            },
            defaultItemProps: { label: "", originalText: "", text: "", href: "" },
          },
          imageOverrides: {
            type: "array",
            arrayFields: {
              label: { type: "text" },
              originalSrc: { type: "text" },
              src: { type: "text" },
              alt: { type: "text" },
            },
            defaultItemProps: { label: "", originalSrc: "", src: "", alt: "" },
          },
        },
        defaultProps: {
          textOverrides: [],
          buttonOverrides: [],
          imageOverrides: [],
        },
        render: withBlockBoundary("ImportedRuntimeSection", (props: Record<string, unknown>) => (
          <ImportedRuntimeSection
            id={typeof props.id === "string" ? props.id : undefined}
            originalType={typeof props.originalType === "string" ? props.originalType : undefined}
            runtimeSource={typeof props.runtimeSource === "string" ? props.runtimeSource : undefined}
            headAssets={props.headAssets}
            sectionLabel={typeof props.sectionLabel === "string" ? props.sectionLabel : undefined}
            componentName={typeof props.componentName === "string" ? props.componentName : undefined}
            sectionTargetId={typeof props.sectionTargetId === "string" ? props.sectionTargetId : undefined}
            textOverrides={
              Array.isArray(props.textOverrides)
                ? (props.textOverrides as Array<Record<string, unknown>>)
                : undefined
            }
            buttonOverrides={
              Array.isArray(props.buttonOverrides)
                ? (props.buttonOverrides as Array<Record<string, unknown>>)
                : undefined
            }
            imageOverrides={
              Array.isArray(props.imageOverrides)
                ? (props.imageOverrides as Array<Record<string, unknown>>)
                : undefined
            }
          />
        )),
      },
    },
  };
}

export function defaultFunnelPuckData() {
  return { root: { props: { title: "", description: "" } }, content: [], zones: {} };
}
