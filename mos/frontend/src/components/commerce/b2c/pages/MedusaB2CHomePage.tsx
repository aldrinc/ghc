/**
 * Medusa B2C Home Page
 * 
 * The storefront homepage featuring:
 * - Hero section with featured content
 * - Featured collections/products
 * - Value propositions
 * - Navigation to store sections
 */

import { useEffect } from "react";
import { useB2CRuntime } from "../B2CRuntimeProvider";
import { B2CStarterShell } from "./B2CStarterShell";

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
    products,
    collections,
    productsLoading,
    refreshProducts,
    navigateToStore,
    navigateToCollection,
    navigateToProduct,
  } = useB2CRuntime();

  // Load products on mount
  useEffect(() => {
    refreshProducts({ limit: 8 });
  }, [refreshProducts]);

  // Filter featured products if specified
  const displayProducts = featuredProducts && featuredProducts.length > 0
    ? products.filter((p) => featuredProducts.includes(p.handle))
    : products.slice(0, 4);

  const displayTitle = heroTitle || "Welcome to our store";
  const displayDescription = heroDescription || "Discover our curated collection of products";

  const formatPrice = (amount: number, currencyCode: string = "usd") => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currencyCode.toUpperCase(),
    }).format(amount / 100);
  };

  return (
    <B2CStarterShell>
      <main>
        {/* Hero Section */}
        <section className="relative bg-neutral-100 py-24 px-4 sm:px-6 lg:px-8">
          <div className="max-w-4xl mx-auto text-center">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-normal text-zinc-900 mb-6">
              {displayTitle}
            </h1>
            <p className="text-lg text-neutral-600 mb-8 max-w-2xl mx-auto">
              {displayDescription}
            </p>
            <button
              onClick={() => navigateToStore()}
              className="inline-flex items-center justify-center px-8 py-3 border border-zinc-900 rounded-full text-sm font-medium text-zinc-900 hover:bg-zinc-900 hover:text-white transition-colors"
            >
              Shop Now
            </button>
          </div>
        </section>

        {/* Featured Collections */}
        {collections.length > 0 && (
          <section className="py-16 px-4 sm:px-6 lg:px-8">
            <div className="max-w-7xl mx-auto">
              <h2 className="text-2xl font-medium text-zinc-900 mb-8">Collections</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {collections.slice(0, 3).map((collection) => (
                  <button
                    key={collection.id}
                    onClick={() => navigateToCollection(collection.handle)}
                    className="group text-left"
                  >
                    <div className="aspect-[4/3] bg-neutral-100 rounded-lg mb-4 overflow-hidden">
                      <div className="w-full h-full flex items-center justify-center text-neutral-400 group-hover:bg-neutral-200 transition-colors">
                        {collection.title}
                      </div>
                    </div>
                    <h3 className="font-medium text-zinc-900 group-hover:text-zinc-600 transition-colors">
                      {collection.title}
                    </h3>
                  </button>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Featured Products */}
        <section className="py-16 px-4 sm:px-6 lg:px-8 bg-neutral-50">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-2xl font-medium text-zinc-900">Featured Products</h2>
              <button
                onClick={() => navigateToStore()}
                className="text-sm text-zinc-600 hover:text-zinc-900 transition-colors"
              >
                View all →
              </button>
            </div>
            
            {productsLoading ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="animate-pulse">
                    <div className="aspect-[3/4] bg-neutral-200 rounded-lg mb-4" />
                    <div className="h-4 bg-neutral-200 rounded w-3/4 mb-2" />
                    <div className="h-4 bg-neutral-200 rounded w-1/2" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {displayProducts.map((product) => (
                  <button
                    key={product.id}
                    onClick={() => navigateToProduct(product.handle)}
                    className="group text-left"
                  >
                    <div className="aspect-[3/4] bg-neutral-100 rounded-lg mb-4 overflow-hidden">
                      {product.thumbnail ? (
                        <img
                          src={product.thumbnail}
                          alt={product.title}
                          className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-neutral-400">
                          {product.title}
                        </div>
                      )}
                    </div>
                    <h3 className="font-medium text-zinc-900 group-hover:text-zinc-600 transition-colors line-clamp-1">
                      {product.title}
                    </h3>
                    {product.variants?.[0]?.prices?.[0] && (
                      <p className="text-sm text-neutral-600 mt-1">
                        {formatPrice(product.variants[0].prices[0].amount, product.variants[0].prices[0].currency_code)}
                      </p>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>
      </main>
    </B2CStarterShell>
  );
}
