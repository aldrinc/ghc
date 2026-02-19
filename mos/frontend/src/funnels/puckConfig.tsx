import { createContext, useContext, type ReactNode } from "react";
import type { Config } from "@measured/puck";
import { Link } from "react-router-dom";
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
import type { PublicFunnelCommerce } from "@/types/commerce";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8008";
const salesPdpFeedImages = salesPdpDefaults.config.reviewWall?.tiles?.map((tile) => tile.image) || [];

type FunnelRuntimeContextValue = {
  funnelSlug: string;
  pageMap: Record<string, string>;
  bundleMode?: boolean;
  entrySlug?: string | null;
  trackEvent?: (event: { eventType: string; props?: Record<string, unknown> }) => void;
  commerce?: PublicFunnelCommerce | null;
  commerceError?: string | null;
  pageId?: string | null;
  nextPageId?: string | null;
  visitorId?: string | null;
  sessionId?: string | null;
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
  if (runtime.bundleMode) {
    return `/${encodeURIComponent(runtime.funnelSlug)}/${encodeURIComponent(normalizedSlug)}`;
  }
  return `/f/${runtime.funnelSlug}/${encodeURIComponent(normalizedSlug)}`;
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

function sectionPaddingClass(padding?: "sm" | "md" | "lg"): { inner: string; outerY: string } {
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
    const to = targetSlug ? resolveRuntimePagePath(runtime, targetSlug) : "#";
    return (
      <div className={wrapperClass}>
        <Link
          to={to}
          className={className}
          onClick={() => runtime.trackEvent?.({ eventType: "cta_click", props: { targetPageId } })}
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
    const to = resolveRuntimePagePath(runtime, targetSlug);
    return (
      <div className={wrapperClass}>
        <Link
          to={to}
          className={className}
          onClick={() => runtime.trackEvent?.({ eventType: "cta_click", props: { targetPageId: runtime.nextPageId } })}
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
          onClick={() => runtime?.trackEvent?.({ eventType: "cta_click", props: { href } })}
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

function FunnelImage({ src, assetPublicId, alt, radius }: ImageProps) {
  const resolvedSrc = assetPublicId ? `${apiBaseUrl}/public/assets/${assetPublicId}` : src;
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
          layout: {
            type: "select",
            options: [
              { label: "Full width", value: "full" },
              { label: "Contained", value: "contained" },
              { label: "Card", value: "card" },
            ],
          },
          containerWidth: {
            type: "select",
            options: [
              { label: "Small", value: "sm" },
              { label: "Medium", value: "md" },
              { label: "Large", value: "lg" },
              { label: "Extra large", value: "xl" },
            ],
          },
          variant: {
            type: "select",
            options: [
              { label: "Default", value: "default" },
              { label: "Muted", value: "muted" },
            ],
          },
          padding: {
            type: "select",
            options: [
              { label: "Small", value: "sm" },
              { label: "Medium", value: "md" },
              { label: "Large", value: "lg" },
            ],
          },
          content: { type: "slot" },
        },
        defaultProps: { purpose: "section", layout: "full", containerWidth: "lg", variant: "default", padding: "md" },
        render: ({
          purpose,
          layout,
          containerWidth,
          variant,
          padding,
          content,
        }: {
          purpose?: "header" | "section" | "footer";
          layout?: "full" | "contained" | "card";
          containerWidth?: ContainerWidth;
          variant?: "default" | "muted";
          padding?: "sm" | "md" | "lg";
          content?: (props?: Record<string, unknown>) => ReactNode;
        }) => {
          const resolvedPurpose = purpose || "section";
          const resolvedLayout = layout || (resolvedPurpose === "section" ? "card" : "full");

          const effectivePadding =
            padding || (resolvedPurpose === "header" ? "sm" : resolvedPurpose === "footer" ? "md" : "md");
          const { inner, outerY } = sectionPaddingClass(effectivePadding);
          const outerYClass = resolvedPurpose === "header" ? "py-4" : outerY;

          const effectiveVariant = variant || (resolvedPurpose === "footer" ? "muted" : "default");
          const bg = effectiveVariant === "muted" ? "bg-surface-2" : "bg-surface";

          const container = containerWidthClass(containerWidth);
          const innerContent = content ? content({ className: "space-y-5" }) : null;

          if (resolvedLayout === "full") {
            return (
              <section className={`${bg} ${outerYClass}`}>
                <div className={`mx-auto w-full ${container} px-6`}>{innerContent}</div>
              </section>
            );
          }

          if (resolvedLayout === "contained") {
            return (
              <section className={`${outerYClass}`}>
                <div className={`mx-auto w-full ${container} px-6`}>
                  <div className={`${bg} ${inner}`}>{innerContent}</div>
                </div>
              </section>
            );
          }

          return (
            <section className={`${outerYClass}`}>
              <div className={`mx-auto w-full ${container} px-6`}>
                <div className={`rounded-2xl border border-border ${bg} shadow-sm ${inner}`}>{innerContent}</div>
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
          themeJson: { type: "textarea" },
          content: { type: "slot" },
        },
        defaultProps: {
          anchorId: "top",
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
      Spacer: {
        fields: {
          height: { type: "number" },
        },
        render: ({ height }: { height?: number }) => <div style={{ height: Math.max(0, height || 24) }} />,
      },
    },
  };
}

export function defaultFunnelPuckData() {
  return { root: { props: { title: "", description: "" } }, content: [], zones: {} };
}
