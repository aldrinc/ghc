/**
 * Medusa B2C Home Page
 *
 * The storefront homepage featuring:
 * - Hero section with featured content
 * - Featured collections/products
 * - Value propositions
 * - Navigation to store sections
 *
 * Theme-aware: Uses design system tokens for colors, typography, and CTAs.
 */

import { useEffect, type CSSProperties } from "react";
import { useB2CRuntime } from "../B2CRuntimeProvider";
import {
  resolveB2CActionRadius,
  resolveB2CHeadingFont,
  useB2CTheme,
  useB2CCTATheme,
} from "../useB2CTheme";
import { B2CStarterShell } from "./B2CStarterShell";
import { StoreProductCard, SkeletonProductGrid } from "./storefrontPrimitives";

export type MedusaB2CHomePageProps = {
  /** Hero title override */
  heroTitle?: string;
  /** Hero description override */
  heroDescription?: string;
  /** Featured product handles to display */
  featuredProducts?: string[];
};

export function MedusaB2CHomePage({
  heroTitle,
  heroDescription,
  featuredProducts,
}: MedusaB2CHomePageProps) {
  const {
    siteName,
    products,
    collections,
    productsLoading,
    refreshProducts,
    navigateToStore,
    navigateToCollection,
    navigateToProduct,
  } = useB2CRuntime();
  const { tokens } = useB2CTheme();
  const ctaTheme = useB2CCTATheme();

  // Load products on mount
  useEffect(() => {
    refreshProducts({ limit: 8 });
  }, [refreshProducts]);

  // Filter featured products if specified
  const displayProducts = featuredProducts && featuredProducts.length > 0
    ? products.filter((p) => featuredProducts.includes(p.handle))
    : products.slice(0, 4);

  const displayTitle = heroTitle || siteName?.trim() || "Storefront";
  const displayDescription = heroDescription || "Browse current products and featured collections.";

  // Theme-aware styles
  const heroStyle: CSSProperties = {
    backgroundColor: tokens.colorBackgroundAlt || tokens.colorBackground || "#f8fafc",
    borderBottomColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
  };

  const heroTitleStyle: CSSProperties = {
    color: tokens.colorText || "#111827",
    fontFamily: resolveB2CHeadingFont(tokens),
  };

  const heroDescriptionStyle: CSSProperties = {
    color: tokens.colorTextMuted || "rgba(17, 24, 39, 0.64)",
  };
  const heroCtaStyle: CSSProperties = {
    ...ctaTheme.style,
    backgroundColor: ctaTheme.style?.backgroundColor || tokens.colorBackground || "#ffffff",
    borderColor: ctaTheme.style?.borderColor || tokens.colorBorder || "#111827",
    color: ctaTheme.style?.color || tokens.colorText || "#111827",
    borderRadius: ctaTheme.style?.borderRadius || resolveB2CActionRadius(tokens),
  };

  const sectionStyle: CSSProperties = {
    backgroundColor: tokens.colorBackground || "#ffffff",
  };

  const sectionAltStyle: CSSProperties = {
    backgroundColor: tokens.colorBackgroundAlt || tokens.colorBackground || "#ffffff",
  };

  const headingStyle: CSSProperties = {
    color: tokens.colorText || "#111827",
    fontFamily: resolveB2CHeadingFont(tokens),
  };

  const textMutedStyle: CSSProperties = {
    color: tokens.colorTextMuted || "rgba(17, 24, 39, 0.64)",
  };

  return (
    <B2CStarterShell>
      <main>
        {/* Hero Section */}
        <section
          className="flex min-h-[70vh] items-center border-b px-4 py-20 sm:px-6 lg:px-8"
          style={heroStyle}
        >
          <div className="mx-auto max-w-3xl text-center">
            <h1
              className="text-3xl font-normal leading-10 sm:text-4xl"
              style={heroTitleStyle}
            >
              {displayTitle}
            </h1>
            <p
              className="mx-auto mt-3 max-w-2xl text-2xl font-normal leading-9"
              style={heroDescriptionStyle}
            >
              {displayDescription}
            </p>
            <button
              onClick={() => navigateToStore()}
              className="mt-8 inline-flex h-10 items-center justify-center rounded-full border px-4 text-sm font-medium transition-colors hover:bg-surface-hover"
              style={heroCtaStyle}
            >
              Shop all products
            </button>
          </div>
        </section>

        {/* Featured Collections */}
        {collections.length > 0 && (
          <section
            className="py-16 px-4 sm:px-6 lg:px-8"
            style={sectionStyle}
          >
            <div className="max-w-7xl mx-auto">
              <h2
                className="mb-8 text-2xl font-medium"
                style={headingStyle}
              >
                Collections
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {collections.slice(0, 3).map((collection) => (
                  <button
                    key={collection.id}
                    onClick={() => navigateToCollection(collection.handle)}
                    className="group text-left"
                  >
                    <div
                      className="aspect-[4/3] rounded-lg mb-4 overflow-hidden transition-colors"
                      style={{
                        backgroundColor: tokens.colorBackgroundAlt || "#f5f5f5",
                        borderRadius: tokens.radiusMedium || undefined,
                      }}
                    >
                      <div
                        className="w-full h-full flex items-center justify-center transition-opacity group-hover:opacity-70"
                        style={{ color: tokens.colorTextMuted || "rgba(17, 24, 39, 0.44)" }}
                      >
                        {collection.title}
                      </div>
                    </div>
                    <h3
                      className="font-medium transition-opacity group-hover:opacity-70"
                      style={headingStyle}
                    >
                      {collection.title}
                    </h3>
                  </button>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Featured Products */}
        <section
          className="py-16 px-4 sm:px-6 lg:px-8"
          style={sectionAltStyle}
        >
          <div className="max-w-7xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <h2
                className="text-2xl font-medium"
                style={headingStyle}
              >
                Featured Products
              </h2>
              <button
                onClick={() => navigateToStore()}
                className="text-sm transition-opacity hover:opacity-70"
                style={textMutedStyle}
              >
                View all →
              </button>
            </div>
            
            {productsLoading ? (
              <SkeletonProductGrid count={4} columns={4} />
            ) : (
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
                {displayProducts.map((product) => (
                  <StoreProductCard
                    key={product.id}
                    product={product}
                    onClick={() => navigateToProduct(product.handle)}
                  />
                ))}
              </div>
            )}
          </div>
        </section>
      </main>
    </B2CStarterShell>
  );
}
