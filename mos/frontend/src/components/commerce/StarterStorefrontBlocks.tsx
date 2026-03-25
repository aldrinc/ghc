import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { MedusaCategory, MedusaCollection, MedusaProduct } from "@/types/commerce";
import { useFunnelRuntime } from "@/funnels/puckConfig";
import { buildPublicFunnelPath } from "@/funnels/runtimeRouting";
import { useCommerceRuntime } from "@/components/commerce/CommerceBlocks";

type StarterLinkType = "funnelPage" | "nextPage" | "external";

type StarterLinkArgs = {
  linkType?: StarterLinkType;
  targetPageId?: string;
  href?: string;
  funnelRuntime: ReturnType<typeof useFunnelRuntime>;
};

function normalizeStarterLinkType(linkType?: StarterLinkType): StarterLinkType {
  if (linkType === "external" || linkType === "nextPage") {
    return linkType;
  }
  return "funnelPage";
}

function resolvePagePathById({
  pageId,
  funnelRuntime,
}: {
  pageId: string;
  funnelRuntime: ReturnType<typeof useFunnelRuntime>;
}): string {
  if (!funnelRuntime) {
    throw new Error("Starter shell requires funnel runtime context to resolve internal links.");
  }
  const slug = funnelRuntime.pageMap?.[pageId];
  if (!slug) {
    throw new Error(`Starter shell could not resolve internal page target '${pageId}'.`);
  }
  return buildPublicFunnelPath({
    productSlug: funnelRuntime.productSlug,
    funnelSlug: funnelRuntime.funnelSlug,
    slug,
    bundleMode: funnelRuntime.bundleMode,
  });
}

function resolvePagePathByType({
  pageType,
  funnelRuntime,
}: {
  pageType: "home" | "category" | "product_detail" | "cart" | "checkout";
  funnelRuntime: ReturnType<typeof useFunnelRuntime>;
}): string | null {
  if (!funnelRuntime?.pageTypeMap) {
    return null;
  }
  const entry = Object.entries(funnelRuntime.pageTypeMap).find(([, type]) => type === pageType);
  if (!entry) {
    return null;
  }
  const [pageId] = entry;
  return resolvePagePathById({ pageId, funnelRuntime });
}

function resolveStarterLinkHref({
  linkType,
  targetPageId,
  href,
  funnelRuntime,
}: StarterLinkArgs): string {
  const normalizedType = normalizeStarterLinkType(linkType);
  if (normalizedType === "external") {
    const trimmedHref = typeof href === "string" ? href.trim() : "";
    if (!trimmedHref) {
      throw new Error("Starter shell external links require an href.");
    }
    return trimmedHref;
  }

  if (normalizedType === "nextPage") {
    const nextPageId = targetPageId || funnelRuntime?.nextPageId || undefined;
    if (!nextPageId) {
      throw new Error("Starter shell next-page links require a next page target.");
    }
    return resolvePagePathById({ pageId: nextPageId, funnelRuntime });
  }

  if (!targetPageId) {
    throw new Error("Starter shell funnel-page links require a targetPageId.");
  }
  return resolvePagePathById({ pageId: targetPageId, funnelRuntime });
}

function starterPriceLabel(product: MedusaProduct): string | null {
  const variants = product.variants || [];
  for (const variant of variants) {
    const price = variant.prices?.find((entry) => Boolean(entry?.amount)) || variant.prices?.[0];
    if (price && typeof price.amount === "number") {
      return `${(price.currency_code || "usd").toUpperCase()} ${(price.amount / 100).toFixed(2)}`;
    }
  }
  return null;
}

function starterProductImage(product: MedusaProduct): string | null {
  const thumbnail = typeof product.thumbnail === "string" ? product.thumbnail.trim() : "";
  if (thumbnail) {
    return thumbnail;
  }
  const images = (product as { images?: Array<{ url?: string | null }> }).images;
  const firstImage = images?.find((image) => typeof image?.url === "string" && image.url.trim());
  return firstImage?.url?.trim() || null;
}

function starterRootCategories(categories: MedusaCategory[]): MedusaCategory[] {
  return categories.filter((category) => !category.parent_category_id);
}

function starterCollectionGroups({
  collections,
  products,
}: {
  collections: MedusaCollection[];
  products: MedusaProduct[];
}): Array<{ collection: MedusaCollection; products: MedusaProduct[] }> {
  return collections
    .map((collection) => ({
      collection,
      products: products.filter((product) => product.collection_id === collection.id),
    }))
    .filter((entry) => entry.products.length > 0);
}

function starterShellLinkClass(isMuted = false): string {
  return isMuted
    ? "text-sm text-neutral-500 transition-colors hover:text-zinc-900"
    : "text-sm text-zinc-700 transition-colors hover:text-zinc-900";
}

export function StarterStoreHeader({
  storeName: storeNameProp = "Store",
  showSearch = true,
  showCart = true,
}: {
  storeName?: string;
  showSearch?: boolean;
  showCart?: boolean;
}) {
  const runtime = useCommerceRuntime();
  const funnelRuntime = useFunnelRuntime();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const storeName = runtime?.storeName || storeNameProp;
  const mainCategories = starterRootCategories(runtime?.categories || []).slice(0, 6);
  const cartCount = runtime?.cart?.items?.reduce((sum, item) => sum + item.quantity, 0) || 0;
  const homePath = resolvePagePathByType({ pageType: "home", funnelRuntime });

  return (
    <header
      className="sticky top-0 z-50 border-b border-neutral-200 bg-white/95 font-sans text-zinc-900 backdrop-blur"
      data-testid="starter-store-header"
    >
      <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8 lg:py-4">
        <div className="flex min-w-0 items-center gap-4 lg:gap-8">
          <button
            type="button"
            onClick={() => {
              if (homePath) {
                navigate(homePath);
              }
            }}
            className="flex items-center gap-3 text-left"
            data-testid="starter-store-brand"
          >
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-neutral-50 text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-700">
              HH
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium uppercase tracking-[0.28em] text-zinc-900">{storeName}</span>
              <span className="block truncate text-[11px] uppercase tracking-[0.2em] text-neutral-500">Medusa B2B starter shell</span>
            </span>
          </button>

          {mainCategories.length > 0 ? (
            <nav className="hidden items-center gap-5 lg:flex" aria-label="Store navigation">
              {mainCategories.map((category) => (
                <button
                  key={category.id}
                  type="button"
                  onClick={() => runtime?.navigateToCategory(category.handle)}
                  className={starterShellLinkClass()}
                >
                  {category.name}
                </button>
              ))}
            </nav>
          ) : null}
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          {showSearch ? (
            <div className="hidden items-center rounded-full border border-neutral-200 bg-neutral-50 px-4 py-2 text-sm text-neutral-500 lg:flex">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="mr-2 h-4 w-4">
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-4.35-4.35m1.85-5.4a7.25 7.25 0 11-14.5 0 7.25 7.25 0 0114.5 0Z" />
              </svg>
              <span title="Search UI is visual-only in this rollout">Search for products</span>
            </div>
          ) : null}

          {showCart ? (
            <button
              type="button"
              onClick={() => runtime?.navigateToCart()}
              className="relative inline-flex items-center gap-2 rounded-full border border-neutral-200 bg-white px-3 py-2 text-sm text-zinc-900 transition-colors hover:bg-neutral-50"
              data-testid="starter-header-cart"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-4 w-4">
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 3h1.386c.51 0 .955.343 1.087.835L5.41 6.75m0 0h14.34l-1.348 6.067a1.125 1.125 0 0 1-1.098.883H8.052a1.125 1.125 0 0 1-1.098-.883L5.41 6.75Zm0 0L4.663 5.04M8.25 20.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm9 0a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z" />
              </svg>
              <span className="hidden sm:inline">Cart</span>
              <span className="inline-flex min-w-[1.5rem] items-center justify-center rounded-full bg-zinc-900 px-1.5 py-0.5 text-[11px] font-medium text-white">
                {cartCount}
              </span>
            </button>
          ) : null}

          {mainCategories.length > 0 ? (
            <button
              type="button"
              onClick={() => setMenuOpen((open) => !open)}
              className="inline-flex items-center justify-center rounded-full border border-neutral-200 p-2 text-zinc-900 transition-colors hover:bg-neutral-50 lg:hidden"
              aria-expanded={menuOpen}
              aria-label="Toggle navigation"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-5 w-5">
                {menuOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                )}
              </svg>
            </button>
          ) : null}
        </div>
      </div>

      {menuOpen && mainCategories.length > 0 ? (
        <div className="border-t border-neutral-200 bg-white px-4 py-3 font-sans lg:hidden">
          <nav className="flex flex-col gap-2" aria-label="Mobile store navigation">
            {mainCategories.map((category) => (
              <button
                key={category.id}
                type="button"
                onClick={() => {
                  runtime?.navigateToCategory(category.handle);
                  setMenuOpen(false);
                }}
                className="rounded-xl px-3 py-2 text-left text-sm text-zinc-700 transition-colors hover:bg-neutral-50 hover:text-zinc-900"
              >
                {category.name}
              </button>
            ))}
          </nav>
        </div>
      ) : null}
    </header>
  );
}

export function StarterPromoBar({
  message = "Practical tools for herbal practitioners and wellness professionals.",
  ctaLabel,
  linkType = "funnelPage",
  targetPageId,
  href,
}: {
  message?: string;
  ctaLabel?: string;
  linkType?: StarterLinkType;
  targetPageId?: string;
  href?: string;
}) {
  const navigate = useNavigate();
  const funnelRuntime = useFunnelRuntime();

  const hasAction = typeof ctaLabel === "string" && ctaLabel.trim().length > 0;
  const actionHref = hasAction
    ? resolveStarterLinkHref({
        linkType,
        targetPageId,
        href,
        funnelRuntime,
      })
    : null;

  return (
    <div className="bg-zinc-950 text-white" data-testid="starter-promo-bar">
      <div className="mx-auto flex max-w-[1440px] flex-col items-center justify-between gap-2 px-4 py-3 text-center font-sans sm:flex-row sm:px-6 lg:px-8">
        <p className="text-xs uppercase tracking-[0.24em] text-neutral-200 sm:text-[11px]">{message}</p>
        {hasAction && actionHref ? (
          <button
            type="button"
            onClick={() => {
              if (normalizeStarterLinkType(linkType) === "external") {
                window.location.assign(actionHref);
                return;
              }
              navigate(actionHref);
            }}
            className="text-xs font-medium uppercase tracking-[0.22em] text-white underline-offset-4 transition hover:text-neutral-200 hover:underline"
          >
            {ctaLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function StarterHomeHero({
  eyebrow = "Honest Herbalist",
  title = "Practical tools for herbal practitioners",
  description = "Explore reference materials, worksheet pads, and client-facing tools grounded in the live catalog.",
  primaryCtaLabel,
  primaryLinkType = "funnelPage",
  primaryTargetPageId,
  primaryHref,
  featuredProductHandles,
}: {
  eyebrow?: string;
  title?: string;
  description?: string;
  primaryCtaLabel?: string;
  primaryLinkType?: StarterLinkType;
  primaryTargetPageId?: string;
  primaryHref?: string;
  featuredProductHandles?: string[];
}) {
  const runtime = useCommerceRuntime();
  const funnelRuntime = useFunnelRuntime();
  const navigate = useNavigate();

  if (!runtime) {
    throw new Error("Starter home hero requires commerce runtime context.");
  }

  if ((runtime.products || []).length === 0) {
    return (
      <section className="border-b border-neutral-200 bg-[#f4f1eb] font-sans text-zinc-900" data-testid="starter-home-hero">
        <div className="mx-auto flex min-h-[420px] max-w-[1440px] items-center justify-center px-4 py-16 text-sm uppercase tracking-[0.24em] text-neutral-500 sm:px-6 lg:px-8">
          Loading starter hero…
        </div>
      </section>
    );
  }

  if (!Array.isArray(featuredProductHandles) || featuredProductHandles.length === 0) {
    throw new Error("Starter home hero requires at least one featured product handle.");
  }

  const normalizedHandles = featuredProductHandles
    .map((handle) => (typeof handle === "string" ? handle.trim() : ""))
    .filter(Boolean);

  if (normalizedHandles.length === 0) {
    throw new Error("Starter home hero requires non-empty featured product handles.");
  }

  const featuredProducts = normalizedHandles.map((handle) => runtime.products.find((product) => product.handle === handle) || null);
  const missingProducts = normalizedHandles.filter((_, index) => !featuredProducts[index]);
  if (missingProducts.length > 0) {
    throw new Error(`Starter home hero could not find featured products for handles: ${missingProducts.join(", ")}.`);
  }

  const resolvedProducts = featuredProducts.filter((product): product is MedusaProduct => Boolean(product)).slice(0, 3);
  const missingMediaProducts = resolvedProducts.filter((product) => !starterProductImage(product));
  if (missingMediaProducts.length > 0) {
    throw new Error(
      `Starter home hero requires real product media. Missing thumbnails for: ${missingMediaProducts
        .map((product) => product.title)
        .join(", ")}.`
    );
  }

  const primaryHrefResolved =
    primaryCtaLabel && (primaryTargetPageId || primaryHref || primaryLinkType === "nextPage")
      ? resolveStarterLinkHref({
          linkType: primaryLinkType,
          targetPageId: primaryTargetPageId,
          href: primaryHref,
          funnelRuntime,
        })
      : null;

  return (
    <section className="border-b border-neutral-200 bg-[#f4f1eb] font-sans text-zinc-900" data-testid="starter-home-hero">
      <div className="mx-auto grid min-h-[620px] max-w-[1440px] items-center gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(420px,0.95fr)] lg:px-8 lg:py-20">
        <div className="mx-auto flex max-w-2xl flex-col items-center text-center lg:mx-0 lg:items-start lg:text-left">
          <span className="text-xs font-medium uppercase tracking-[0.32em] text-neutral-500">{eyebrow}</span>
          <h1 className="mt-6 max-w-[12ch] text-5xl font-normal tracking-[-0.05em] text-zinc-900 sm:text-6xl">
            {title}
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-neutral-600">{description}</p>
          {primaryCtaLabel && primaryHrefResolved ? (
            <button
              type="button"
              onClick={() => {
                if (normalizeStarterLinkType(primaryLinkType) === "external") {
                  window.location.assign(primaryHrefResolved);
                  return;
                }
                navigate(primaryHrefResolved);
              }}
              className="mt-8 inline-flex items-center rounded-full bg-zinc-900 px-6 py-3 text-sm font-medium text-white transition hover:bg-zinc-800"
            >
              {primaryCtaLabel}
            </button>
          ) : null}
        </div>

        <div className="relative min-h-[440px]" data-testid="starter-home-hero-media">
          <div className="absolute inset-0 rounded-[2rem] border border-white/70 bg-white/40" />
          {resolvedProducts.map((product, index) => {
            const imageUrl = starterProductImage(product);
            return (
              <article
                key={product.id}
                className={`absolute overflow-hidden rounded-[1.75rem] border border-black/5 bg-white shadow-[0_30px_80px_rgba(15,23,42,0.12)] ${
                  index === 0
                    ? "left-[6%] top-[8%] w-[56%]"
                    : index === 1
                      ? "right-[4%] top-[12%] w-[34%]"
                      : "bottom-[6%] right-[16%] w-[44%]"
                }`}
              >
                <div className="aspect-[4/5] bg-[#f8f6f2] p-6">
                  <img src={imageUrl || undefined} alt={product.title} className="h-full w-full object-contain" />
                </div>
                <div className="border-t border-neutral-200 px-5 py-4">
                  <p className="text-[11px] uppercase tracking-[0.24em] text-neutral-500">Featured product</p>
                  <p className="mt-2 text-sm font-medium text-zinc-900">{product.title}</p>
                  {starterPriceLabel(product) ? (
                    <p className="mt-1 text-sm text-neutral-600">From {starterPriceLabel(product)}</p>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function StarterCollectionRails({
  maxCollections = 3,
  productsPerCollection = 4,
}: {
  maxCollections?: number;
  productsPerCollection?: number;
}) {
  const runtime = useCommerceRuntime();

  if (!runtime) {
    throw new Error("Starter collection rails require commerce runtime context.");
  }

  if ((runtime.products || []).length === 0 && (runtime.collections || []).length === 0) {
    return (
      <div className="bg-white font-sans" data-testid="starter-collection-rails">
        <div className="mx-auto max-w-[1440px] px-4 py-14 text-sm uppercase tracking-[0.24em] text-neutral-500 sm:px-6 lg:px-8">
          Loading collection rails…
        </div>
      </div>
    );
  }

  const groupedCollections = starterCollectionGroups({
    collections: runtime.collections || [],
    products: runtime.products || [],
  }).slice(0, Math.max(1, maxCollections));

  if (groupedCollections.length === 0) {
    throw new Error("Starter home requires at least one collection with attached products to render collection rails.");
  }

  const missingMediaProducts = groupedCollections
    .flatMap((group) => group.products.slice(0, Math.max(1, productsPerCollection)))
    .filter((product) => !starterProductImage(product));

  if (missingMediaProducts.length > 0) {
    throw new Error(
      `Starter home requires real product thumbnails for collection rails. Missing thumbnails for: ${[
        ...new Set(missingMediaProducts.map((product) => product.title)),
      ].join(", ")}.`
    );
  }

  return (
    <div className="bg-white font-sans" data-testid="starter-collection-rails">
      {groupedCollections.map(({ collection, products }) => (
        <section key={collection.id} className="border-b border-neutral-200 last:border-b-0">
          <div className="mx-auto max-w-[1440px] px-4 py-14 sm:px-6 lg:px-8 lg:py-20">
            <div className="mb-8 flex items-end justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-neutral-500">Collection</p>
                <h2 className="mt-3 text-2xl font-normal tracking-[-0.04em] text-zinc-900">{collection.title}</h2>
              </div>
              <p className="text-sm text-neutral-500">Real Medusa collection merchandising</p>
            </div>

            <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              {products.slice(0, Math.max(1, productsPerCollection)).map((product) => (
                <li key={product.id}>
                  <button
                    type="button"
                    onClick={() => runtime.navigateToProduct(product.handle)}
                    className="group flex h-full w-full flex-col overflow-hidden rounded-[1.5rem] border border-neutral-200 bg-[#faf8f5] text-left transition hover:border-neutral-300 hover:bg-[#f6f2eb]"
                  >
                    <div className="aspect-[4/5] border-b border-neutral-200 p-6">
                      <img
                        src={starterProductImage(product) || undefined}
                        alt={product.title}
                        className="h-full w-full object-contain transition duration-300 group-hover:scale-[1.02]"
                      />
                    </div>
                    <div className="flex flex-1 flex-col gap-2 px-5 py-4">
                      <p className="text-[11px] uppercase tracking-[0.24em] text-neutral-500">{collection.title}</p>
                      <h3 className="text-base font-medium text-zinc-900">{product.title}</h3>
                      <p className="mt-auto text-sm text-neutral-600">
                        {starterPriceLabel(product) ? `From ${starterPriceLabel(product)}` : "Price available on product page"}
                      </p>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ))}
    </div>
  );
}

export function StarterStoreFooter({
  storeName: storeNameProp = "Store",
  showCategories = true,
  showCollections = true,
}: {
  storeName?: string;
  showCategories?: boolean;
  showCollections?: boolean;
}) {
  const runtime = useCommerceRuntime();
  const funnelRuntime = useFunnelRuntime();
  const navigate = useNavigate();

  const storeName = runtime?.storeName || storeNameProp;
  const categories = starterRootCategories(runtime?.categories || []).slice(0, 6);
  const collections = (runtime?.collections || []).slice(0, 6);
  const footerPages = [
    { label: "Home", path: resolvePagePathByType({ pageType: "home", funnelRuntime }) },
    { label: "Catalog", path: resolvePagePathByType({ pageType: "category", funnelRuntime }) },
    { label: "Cart", path: resolvePagePathByType({ pageType: "cart", funnelRuntime }) },
    { label: "Checkout", path: resolvePagePathByType({ pageType: "checkout", funnelRuntime }) },
  ].filter((entry): entry is { label: string; path: string } => Boolean(entry.path));

  return (
    <footer className="border-t border-neutral-200 bg-[#faf7f2] font-sans text-zinc-900" data-testid="starter-store-footer">
      <div className="mx-auto max-w-[1440px] px-4 py-14 sm:px-6 lg:px-8 lg:py-20">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1.2fr)_repeat(3,minmax(0,1fr))]">
          <div className="max-w-sm">
            <p className="text-xs uppercase tracking-[0.28em] text-neutral-500">{storeName}</p>
            <h2 className="mt-4 text-3xl font-normal tracking-[-0.04em] text-zinc-900">Starter-aligned storefront shell inside Marketi.</h2>
            <p className="mt-4 text-sm leading-7 text-neutral-600">
              Browse the live Honest Herbalist catalog with the shared Medusa B2B starter rhythm: catalog, cart, and checkout in one coherent public runtime.
            </p>
          </div>

          {showCategories ? (
            <div>
              <h3 className="text-xs font-medium uppercase tracking-[0.24em] text-neutral-500">Categories</h3>
              <ul className="mt-5 space-y-3">
                {categories.length > 0 ? (
                  categories.map((category) => (
                    <li key={category.id}>
                      <button
                        type="button"
                        onClick={() => runtime?.navigateToCategory(category.handle)}
                        className={starterShellLinkClass(true)}
                      >
                        {category.name}
                      </button>
                    </li>
                  ))
                ) : (
                  <li className="text-sm text-neutral-500">Categories appear when live catalog data is available.</li>
                )}
              </ul>
            </div>
          ) : null}

          {showCollections ? (
            <div>
              <h3 className="text-xs font-medium uppercase tracking-[0.24em] text-neutral-500">Collections</h3>
              <ul className="mt-5 space-y-3">
                {collections.length > 0 ? (
                  collections.map((collection) => (
                    <li key={collection.id} className="text-sm text-neutral-500">
                      {collection.title}
                    </li>
                  ))
                ) : (
                  <li className="text-sm text-neutral-500">Collection rails publish only when real Medusa collections are attached.</li>
                )}
              </ul>
            </div>
          ) : null}

          <div>
            <h3 className="text-xs font-medium uppercase tracking-[0.24em] text-neutral-500">Pages</h3>
            <ul className="mt-5 space-y-3">
              {footerPages.map((page) => (
                <li key={page.label}>
                  <button type="button" onClick={() => navigate(page.path)} className={starterShellLinkClass(true)}>
                    {page.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-neutral-200 pt-6 text-xs uppercase tracking-[0.2em] text-neutral-500 sm:flex-row sm:items-center sm:justify-between">
          <span>© {new Date().getFullYear()} {storeName}</span>
          <span>Powered by Medusa · Rendered through Marketi</span>
        </div>
      </div>
    </footer>
  );
}
