import { createContext, useContext, type CSSProperties, type ReactNode } from "react";

type ImportedThemeTokens = {
  palette?: Record<string, unknown>;
  fonts?: Record<string, unknown>;
};

type ImportedTheme = {
  primary: string;
  secondary: string;
  surface: string;
  accent: string;
  text: string;
  background: string;
  headingFont: string;
  bodyFont: string;
};

type ImportedRuntimeContextValue = {
  runtimeSource?: string;
  headAssets?: unknown;
};

type SlotRenderer = (props?: Record<string, unknown>) => ReactNode;

type ImportedButton = {
  label?: string;
  href?: string;
};

type ImportedBadge = {
  label?: string;
};

type ImportedGridItem = {
  label?: string;
  title?: string;
  text?: string;
  value?: string;
};

type ImportedImageItem = {
  src?: string;
  alt?: string;
};

type ImportedOffer = {
  title?: string;
  subtitle?: string;
  price?: string;
  total?: string;
  regularPrice?: string;
  savings?: string;
  badge?: string;
};

type ImportedBenefit = {
  text?: string;
};

type ImportedTestimonial = {
  name?: string;
  quote?: string;
  role?: string;
  imageSrc?: string;
};

type ImportedComparisonRow = {
  feature?: string;
  primaryValue?: string;
  secondaryValue?: string;
  tertiaryValue?: string;
};

type ImportedAccordionItem = {
  question?: string;
  answer?: string;
};

type ImportedFooterLink = {
  label?: string;
  href?: string;
};

const defaultImportedTheme: ImportedTheme = {
  primary: "#163b7a",
  secondary: "#2f67b3",
  surface: "#ffffff",
  accent: "#d6e6ff",
  text: "#132238",
  background: "#f4f7ff",
  headingFont: "inherit",
  bodyFont: "inherit",
};

const ImportedThemeContext = createContext<ImportedTheme>(defaultImportedTheme);
const ImportedRuntimeContext = createContext<ImportedRuntimeContextValue>({});

function parseTheme(theme: unknown, themeJson?: string): ImportedTheme {
  let payload = theme;
  if ((!payload || typeof payload !== "object") && typeof themeJson === "string" && themeJson.trim()) {
    try {
      payload = JSON.parse(themeJson);
    } catch {
      payload = null;
    }
  }
  const tokens = (payload || {}) as ImportedThemeTokens;
  const palette = (tokens.palette || {}) as Record<string, unknown>;
  const fonts = (tokens.fonts || {}) as Record<string, unknown>;

  const readColor = (key: string, fallback: string) => {
    const value = palette[key];
    return typeof value === "string" && value.trim() ? value : fallback;
  };
  const readFont = (key: string, fallback: string) => {
    const value = fonts[key];
    return typeof value === "string" && value.trim() ? value : fallback;
  };

  return {
    primary: readColor("primary", defaultImportedTheme.primary),
    secondary: readColor("secondary", defaultImportedTheme.secondary),
    surface: readColor("surface", defaultImportedTheme.surface),
    accent: readColor("accent", defaultImportedTheme.accent),
    text: readColor("text", defaultImportedTheme.text),
    background: readColor("background", defaultImportedTheme.background),
    headingFont: readFont("heading", defaultImportedTheme.headingFont),
    bodyFont: readFont("body", defaultImportedTheme.bodyFont),
  };
}

function useImportedTheme() {
  return useContext(ImportedThemeContext);
}

export function useImportedRuntimeContext() {
  return useContext(ImportedRuntimeContext);
}

function themeStyle(theme: ImportedTheme): CSSProperties {
  return {
    ["--import-primary" as "--import-primary"]: theme.primary,
    ["--import-secondary" as "--import-secondary"]: theme.secondary,
    ["--import-surface" as "--import-surface"]: theme.surface,
    ["--import-accent" as "--import-accent"]: theme.accent,
    ["--import-text" as "--import-text"]: theme.text,
    ["--import-background" as "--import-background"]: theme.background,
    fontFamily: theme.bodyFont,
    color: theme.text,
    backgroundColor: theme.background,
  };
}

function renderSlot(slot?: SlotRenderer, className?: string) {
  if (!slot) return null;
  return slot(className ? { className } : undefined);
}

function normalizeArray<T extends object>(value: unknown): T[] {
  return Array.isArray(value) ? (value.filter((item) => item && typeof item === "object") as T[]) : [];
}

function sectionSurfaceClass(surface?: string): string {
  if (surface === "primary") return "bg-[var(--import-primary)] text-white";
  if (surface === "muted") return "bg-[color:color-mix(in_srgb,var(--import-background)_74%,white)]";
  return "bg-transparent";
}

function Card({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-[24px] border border-black/10 bg-white/90 p-6 shadow-[0_20px_60px_rgba(15,23,42,0.06)] backdrop-blur-sm">
      {children}
    </div>
  );
}

export function ImportedPage({
  pageName,
  theme,
  themeJson,
  content,
  renderMode,
  sharedRuntimeSource,
  sharedHeadAssets,
}: {
  pageName?: string;
  theme?: unknown;
  themeJson?: string;
  content?: SlotRenderer;
  renderMode?: string;
  sharedRuntimeSource?: string;
  sharedHeadAssets?: unknown;
}) {
  const resolvedTheme = parseTheme(theme, themeJson);
  const sourceMode = renderMode === "source";
  return (
    <ImportedThemeContext.Provider value={resolvedTheme}>
      <ImportedRuntimeContext.Provider
        value={{
          runtimeSource: sharedRuntimeSource,
          headAssets: sharedHeadAssets,
        }}
      >
        <div
          style={sourceMode ? undefined : themeStyle(resolvedTheme)}
          className={sourceMode ? "w-full" : "min-h-screen bg-[var(--import-background)] text-[var(--import-text)]"}
        >
          <div className={sourceMode ? "w-full" : "mx-auto w-full max-w-[1600px]"}>
            {pageName ? (
              <div className="sr-only" aria-hidden="true">
                {pageName}
              </div>
            ) : null}
            {renderSlot(content, sourceMode ? undefined : "space-y-0")}
          </div>
        </div>
      </ImportedRuntimeContext.Provider>
    </ImportedThemeContext.Provider>
  );
}

export function ImportedSection({
  displayName,
  sourceSectionId,
  sectionKey,
  sectionType,
  semanticTagsText,
  surface,
  content,
  renderMode,
}: {
  displayName?: string;
  sourceSectionId?: string;
  sectionKey?: string;
  sectionType?: string;
  semanticTagsText?: string;
  surface?: string;
  content?: SlotRenderer;
  renderMode?: string;
}) {
  const sourceMode = renderMode === "source" || surface === "source";
  const className = sectionSurfaceClass(surface);
  if (sourceMode) {
    return (
      <section
        data-imported-section-id={sourceSectionId}
        data-imported-section-key={sectionKey}
        data-imported-section-type={sectionType}
        data-imported-section-tags={semanticTagsText}
        aria-label={displayName || sectionKey || sectionType || "Imported section"}
        className="w-full"
      >
        {renderSlot(content)}
      </section>
    );
  }
  return (
    <section
      data-imported-section-id={sourceSectionId}
      data-imported-section-key={sectionKey}
      data-imported-section-type={sectionType}
      data-imported-section-tags={semanticTagsText}
      aria-label={displayName || sectionKey || sectionType || "Imported section"}
      className={`w-full px-6 py-10 md:px-10 lg:px-12 ${className}`}
    >
      <div className="mx-auto max-w-[1380px]">{renderSlot(content, "space-y-6")}</div>
    </section>
  );
}

export function ImportedNarrativeBlock({
  eyebrow,
  title,
  body,
  quote,
  imageSrc,
  imageAlt,
  mediaPosition,
  align,
  badges,
  buttons,
}: {
  eyebrow?: string;
  title?: string;
  body?: string;
  quote?: string;
  imageSrc?: string;
  imageAlt?: string;
  mediaPosition?: "left" | "right";
  align?: "left" | "center";
  badges?: ImportedBadge[];
  buttons?: ImportedButton[];
}) {
  const theme = useImportedTheme();
  const badgeItems = normalizeArray<ImportedBadge>(badges);
  const buttonItems = normalizeArray<ImportedButton>(buttons);
  const centered = align === "center" && !imageSrc;
  const mediaFirst = mediaPosition === "left";

  const textPanel = (
    <div className={centered ? "mx-auto max-w-3xl text-center" : "max-w-2xl"}>
      {eyebrow ? (
        <div className="mb-4 inline-flex rounded-full border border-[var(--import-primary)]/20 bg-white/70 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--import-primary)]">
          {eyebrow}
        </div>
      ) : null}
      {badgeItems.length ? (
        <div className={`mb-5 flex flex-wrap gap-2 ${centered ? "justify-center" : "justify-start"}`}>
          {badgeItems.map((badge, index) => (
            <span
              key={`${badge.label || "badge"}-${index}`}
              className="rounded-full bg-[var(--import-accent)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--import-primary)]"
            >
              {badge.label || "Badge"}
            </span>
          ))}
        </div>
      ) : null}
      {title ? (
        <h2
          className="text-4xl font-black leading-[1.05] tracking-tight md:text-5xl"
          style={{ fontFamily: theme.headingFont }}
        >
          {title}
        </h2>
      ) : null}
      {body ? <p className="mt-5 text-lg leading-8 text-black/70">{body}</p> : null}
      {quote ? (
        <div className="mt-6 rounded-[20px] border border-[var(--import-primary)]/10 bg-white/70 px-5 py-4 text-base italic leading-7 text-black/75">
          {quote}
        </div>
      ) : null}
      {buttonItems.length ? (
        <div className={`mt-7 flex flex-wrap gap-3 ${centered ? "justify-center" : "justify-start"}`}>
          {buttonItems.map((button, index) => (
            <a
              key={`${button.label || "button"}-${index}`}
              href={button.href || "#"}
              className="inline-flex min-h-12 items-center justify-center rounded-full bg-[var(--import-primary)] px-5 py-3 text-sm font-semibold uppercase tracking-[0.14em] text-white transition-opacity hover:opacity-90"
            >
              {button.label || "Action"}
            </a>
          ))}
        </div>
      ) : null}
    </div>
  );

  if (!imageSrc) {
    return <Card>{textPanel}</Card>;
  }

  const mediaPanel = (
    <div className="overflow-hidden rounded-[28px] border border-black/10 bg-white shadow-[0_24px_60px_rgba(15,23,42,0.08)]">
      <img src={imageSrc} alt={imageAlt || title || "Imported image"} className="h-full w-full object-cover" />
    </div>
  );

  return (
    <div className="grid items-center gap-8 lg:grid-cols-2 lg:gap-12">
      {mediaFirst ? mediaPanel : textPanel}
      {mediaFirst ? textPanel : mediaPanel}
    </div>
  );
}

export function ImportedItemGrid({
  title,
  body,
  columns,
  items,
}: {
  title?: string;
  body?: string;
  columns?: number;
  items?: ImportedGridItem[];
}) {
  const theme = useImportedTheme();
  const itemList = normalizeArray<ImportedGridItem>(items);
  const colClass =
    columns === 4 ? "lg:grid-cols-4" : columns === 3 ? "md:grid-cols-3" : columns === 1 ? "grid-cols-1" : "md:grid-cols-2";

  return (
    <div className="space-y-6">
      {title ? (
        <div>
          <h3 className="text-2xl font-black tracking-tight" style={{ fontFamily: theme.headingFont }}>
            {title}
          </h3>
          {body ? <p className="mt-2 text-base leading-7 text-black/70">{body}</p> : null}
        </div>
      ) : null}
      <div className={`grid gap-4 ${colClass}`}>
        {itemList.map((item, index) => (
          <Card key={`${item.title || item.value || "item"}-${index}`}>
            {item.label ? (
              <div className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--import-primary)]">
                {item.label}
              </div>
            ) : null}
            {item.value ? (
              <div className="mt-2 text-4xl font-black text-[var(--import-primary)]" style={{ fontFamily: theme.headingFont }}>
                {item.value}
              </div>
            ) : null}
            {item.title ? (
              <div className={`font-semibold text-[var(--import-text)] ${item.value ? "mt-2 text-lg" : "text-lg"}`}>
                {item.title}
              </div>
            ) : null}
            {item.text ? <p className="mt-2 text-sm leading-6 text-black/70">{item.text}</p> : null}
          </Card>
        ))}
      </div>
    </div>
  );
}

export function ImportedBadgeStrip({
  title,
  items,
}: {
  title?: string;
  items?: ImportedBadge[];
}) {
  const itemList = normalizeArray<ImportedBadge>(items);
  return (
    <div className="rounded-full border border-black/10 bg-white/80 px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-center justify-center gap-2 md:gap-3">
        {title ? (
          <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--import-primary)]">
            {title}
          </span>
        ) : null}
        {itemList.map((item, index) => (
          <span
            key={`${item.label || "badge"}-${index}`}
            className="rounded-full bg-[var(--import-accent)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--import-primary)]"
          >
            {item.label || "Badge"}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ImportedOfferSelector({
  eyebrow,
  title,
  body,
  reviewText,
  ctaLabel,
  galleryImages,
  benefits,
  offers,
}: {
  eyebrow?: string;
  title?: string;
  body?: string;
  reviewText?: string;
  ctaLabel?: string;
  galleryImages?: ImportedImageItem[];
  benefits?: ImportedBenefit[];
  offers?: ImportedOffer[];
}) {
  const theme = useImportedTheme();
  const imageItems = normalizeArray<ImportedImageItem>(galleryImages);
  const benefitItems = normalizeArray<ImportedBenefit>(benefits);
  const offerItems = normalizeArray<ImportedOffer>(offers);
  const primaryImage = imageItems[0];

  return (
    <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:gap-12">
      <div className="space-y-4">
        <div className="aspect-square overflow-hidden rounded-[28px] border border-black/10 bg-white">
          {primaryImage?.src ? (
            <img
              src={primaryImage.src}
              alt={primaryImage.alt || title || "Imported product image"}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-black/40">No gallery image</div>
          )}
        </div>
        {imageItems.length > 1 ? (
          <div className="grid grid-cols-4 gap-3 md:grid-cols-6">
            {imageItems.slice(0, 6).map((item, index) => (
              <div key={`${item.src || "thumb"}-${index}`} className="aspect-square overflow-hidden rounded-2xl border border-black/10 bg-white">
                {item.src ? (
                  <img src={item.src} alt={item.alt || `Gallery image ${index + 1}`} className="h-full w-full object-cover" />
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <Card>
        {eyebrow ? (
          <div className="mb-4 inline-flex rounded-full border border-[var(--import-primary)]/20 bg-[var(--import-accent)] px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--import-primary)]">
            {eyebrow}
          </div>
        ) : null}
        {reviewText ? <div className="text-sm font-semibold text-[var(--import-primary)]">{reviewText}</div> : null}
        {title ? (
          <h2 className="mt-3 text-4xl font-black tracking-tight" style={{ fontFamily: theme.headingFont }}>
            {title}
          </h2>
        ) : null}
        {body ? <p className="mt-4 text-base leading-7 text-black/70">{body}</p> : null}

        {benefitItems.length ? (
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {benefitItems.map((item, index) => (
              <div key={`${item.text || "benefit"}-${index}`} className="rounded-2xl border border-black/10 bg-[var(--import-background)] px-4 py-3 text-sm font-medium text-[var(--import-text)]">
                {item.text || "Benefit"}
              </div>
            ))}
          </div>
        ) : null}

        {offerItems.length ? (
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {offerItems.map((offer, index) => (
              <div
                key={`${offer.title || "offer"}-${index}`}
                className="rounded-[24px] border border-black/10 bg-white p-5 shadow-sm"
              >
                {offer.badge ? (
                  <div className="mb-3 inline-flex rounded-full bg-[var(--import-primary)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-white">
                    {offer.badge}
                  </div>
                ) : null}
                <div className="text-lg font-bold text-[var(--import-text)]">{offer.title || "Offer"}</div>
                {offer.subtitle ? <div className="mt-1 text-sm text-black/60">{offer.subtitle}</div> : null}
                {offer.price ? (
                  <div className="mt-4 text-2xl font-black text-[var(--import-primary)]" style={{ fontFamily: theme.headingFont }}>
                    {offer.price}
                  </div>
                ) : null}
                {offer.total ? <div className="mt-1 text-sm font-medium text-black/70">Total {offer.total}</div> : null}
                {offer.regularPrice ? <div className="mt-1 text-sm text-black/45 line-through">{offer.regularPrice}</div> : null}
                {offer.savings ? <div className="mt-3 text-sm font-semibold text-emerald-700">{offer.savings}</div> : null}
              </div>
            ))}
          </div>
        ) : null}

        {ctaLabel ? (
          <a
            href="#shop"
            className="mt-8 inline-flex min-h-14 w-full items-center justify-center rounded-full bg-[var(--import-primary)] px-6 py-4 text-sm font-semibold uppercase tracking-[0.16em] text-white transition-opacity hover:opacity-90"
          >
            {ctaLabel}
          </a>
        ) : null}
      </Card>
    </div>
  );
}

export function ImportedTestimonialsGrid({
  title,
  body,
  items,
}: {
  title?: string;
  body?: string;
  items?: ImportedTestimonial[];
}) {
  const theme = useImportedTheme();
  const testimonials = normalizeArray<ImportedTestimonial>(items);

  return (
    <div className="space-y-6">
      {title ? (
        <div className="text-center">
          <h3 className="text-3xl font-black tracking-tight" style={{ fontFamily: theme.headingFont }}>
            {title}
          </h3>
          {body ? <p className="mx-auto mt-3 max-w-3xl text-base leading-7 text-black/70">{body}</p> : null}
        </div>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {testimonials.map((item, index) => (
          <Card key={`${item.name || "testimonial"}-${index}`}>
            {item.imageSrc ? (
              <div className="mb-4 aspect-[4/5] overflow-hidden rounded-[20px] bg-[var(--import-background)]">
                <img src={item.imageSrc} alt={item.name || "Customer"} className="h-full w-full object-cover" />
              </div>
            ) : null}
            <div className="text-lg font-semibold text-[var(--import-text)]">{item.name || "Customer"}</div>
            {item.role ? <div className="mt-1 text-sm text-black/50">{item.role}</div> : null}
            {item.quote ? <p className="mt-3 text-sm leading-6 text-black/70">“{item.quote}”</p> : null}
          </Card>
        ))}
      </div>
    </div>
  );
}

export function ImportedComparisonTable({
  title,
  body,
  primaryLabel,
  secondaryLabel,
  tertiaryLabel,
  rows,
}: {
  title?: string;
  body?: string;
  primaryLabel?: string;
  secondaryLabel?: string;
  tertiaryLabel?: string;
  rows?: ImportedComparisonRow[];
}) {
  const theme = useImportedTheme();
  const rowItems = normalizeArray<ImportedComparisonRow>(rows);

  return (
    <div className="space-y-6">
      {title ? (
        <div className="text-center">
          <h3 className="text-3xl font-black tracking-tight" style={{ fontFamily: theme.headingFont }}>
            {title}
          </h3>
          {body ? <p className="mx-auto mt-3 max-w-3xl text-base leading-7 text-black/70">{body}</p> : null}
        </div>
      ) : null}
      <div className="overflow-hidden rounded-[28px] border border-black/10 bg-white shadow-sm">
        <div className="grid grid-cols-4 bg-[var(--import-background)] text-sm font-semibold uppercase tracking-[0.14em] text-black/60">
          <div className="p-4">Feature</div>
          <div className="bg-[var(--import-primary)] p-4 text-center text-white">{primaryLabel || "Primary"}</div>
          <div className="p-4 text-center">{secondaryLabel || "Option 2"}</div>
          <div className="p-4 text-center">{tertiaryLabel || "Option 3"}</div>
        </div>
        {rowItems.map((row, index) => (
          <div key={`${row.feature || "feature"}-${index}`} className="grid grid-cols-4 border-t border-black/10 text-sm">
            <div className="p-4 font-medium text-[var(--import-text)]">{row.feature || "Feature"}</div>
            <div className="p-4 text-center font-semibold text-[var(--import-primary)]">{row.primaryValue || ""}</div>
            <div className="p-4 text-center text-black/70">{row.secondaryValue || ""}</div>
            <div className="p-4 text-center text-black/70">{row.tertiaryValue || ""}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ImportedAccordion({
  title,
  body,
  items,
}: {
  title?: string;
  body?: string;
  items?: ImportedAccordionItem[];
}) {
  const theme = useImportedTheme();
  const itemList = normalizeArray<ImportedAccordionItem>(items);
  return (
    <div className="space-y-6">
      {title ? (
        <div className="text-center">
          <h3 className="text-3xl font-black tracking-tight" style={{ fontFamily: theme.headingFont }}>
            {title}
          </h3>
          {body ? <p className="mx-auto mt-3 max-w-3xl text-base leading-7 text-black/70">{body}</p> : null}
        </div>
      ) : null}
      <div className="overflow-hidden rounded-[28px] border border-black/10 bg-white shadow-sm">
        {itemList.map((item, index) => (
          <div key={`${item.question || "faq"}-${index}`} className="border-t border-black/10 first:border-t-0">
            <div className="px-6 py-5 text-lg font-semibold text-[var(--import-text)]">{item.question || "Question"}</div>
            {item.answer ? <div className="px-6 pb-6 text-sm leading-7 text-black/70">{item.answer}</div> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

export function ImportedFooterLinks({
  brandName,
  body,
  legalText,
  links,
}: {
  brandName?: string;
  body?: string;
  legalText?: string;
  links?: ImportedFooterLink[];
}) {
  const theme = useImportedTheme();
  const linkItems = normalizeArray<ImportedFooterLink>(links);
  return (
    <div className="rounded-[28px] border border-black/10 bg-white px-6 py-8 shadow-sm">
      <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
        <div className="max-w-xl">
          {brandName ? (
            <div className="text-3xl font-black uppercase tracking-[0.18em]" style={{ fontFamily: theme.headingFont, color: theme.primary }}>
              {brandName}
            </div>
          ) : null}
          {body ? <p className="mt-3 text-sm leading-6 text-black/65">{body}</p> : null}
        </div>
        {linkItems.length ? (
          <div className="flex flex-wrap gap-3 md:justify-end">
            {linkItems.map((link, index) => (
              <a
                key={`${link.label || "link"}-${index}`}
                href={link.href || "#"}
                className="text-sm font-semibold uppercase tracking-[0.14em] text-[var(--import-primary)]"
              >
                {link.label || "Link"}
              </a>
            ))}
          </div>
        ) : null}
      </div>
      {legalText ? <div className="mt-6 border-t border-black/10 pt-5 text-xs leading-6 text-black/50">{legalText}</div> : null}
    </div>
  );
}
