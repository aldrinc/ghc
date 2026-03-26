/**
 * Medusa B2C Store Page
 * 
 * The main store/catalog page featuring:
 * - Product grid with filtering
 * - Category sidebar
 * - Search and sort controls
 */

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { useB2CRuntime } from "../B2CRuntimeProvider";

export type MedusaB2CStorePageProps = {
  /** Page title override */
  title?: string;
  /** Default category filter */
  defaultCategory?: string;
};

export function MedusaB2CStorePage({ title, defaultCategory }: MedusaB2CStorePageProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    products,
    categories,
    productsLoading,
    productsError,
    refreshProducts,
    navigateToProduct,
    navigateToCategory,
    currentCategory,
    loadCategoryByHandle,
  } = useB2CRuntime();

  const [searchQuery, setSearchQuery] = useState(searchParams.get("q") || "");

  // Load products and category on mount
  useEffect(() => {
    const categoryHandle = searchParams.get("category") || defaultCategory;
    if (categoryHandle) {
      loadCategoryByHandle(categoryHandle).then((cat) => {
        refreshProducts({ categoryId: cat ? [cat.id] : undefined });
      });
    } else {
      refreshProducts();
    }
  }, [searchParams, defaultCategory, loadCategoryByHandle, refreshProducts]);

  const handleSearch = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      setSearchParams({ q: searchQuery.trim() });
      refreshProducts({ q: searchQuery.trim() });
    } else {
      setSearchParams({});
      refreshProducts();
    }
  }, [searchQuery, setSearchParams, refreshProducts]);

  const handleCategoryClick = useCallback((category: typeof categories[0]) => {
    setSearchParams({ category: category.handle });
    refreshProducts({ categoryId: [category.id] });
  }, [setSearchParams, refreshProducts]);

  const displayTitle = title || currentCategory?.name || "All Products";
  const parentCategories = categories.filter((c) => !c.parent_category_id);

  const formatPrice = (amount: number, currencyCode: string = "usd") => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currencyCode.toUpperCase(),
    }).format(amount / 100);
  };

  return (
    <div className="min-h-screen bg-white">
      <main className="py-8 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-medium text-zinc-900 mb-8">{displayTitle}</h1>

          <div className="flex flex-col lg:flex-row gap-8">
            {/* Sidebar */}
            <aside className="w-full lg:w-64 flex-shrink-0">
              {/* Search */}
              <div className="mb-6">
                <form onSubmit={handleSearch}>
                  <input
                    type="search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search products..."
                    className="w-full px-4 py-2 border border-neutral-200 rounded-lg"
                  />
                </form>
              </div>

              {/* Categories */}
              {parentCategories.length > 0 && (
                <div className="mb-6">
                  <h3 className="font-medium text-zinc-900 mb-4">Categories</h3>
                  <ul className="space-y-2">
                    {parentCategories.map((category) => (
                      <li key={category.id}>
                        <button
                          onClick={() => handleCategoryClick(category)}
                          className="text-sm text-neutral-600 hover:text-zinc-900"
                        >
                          {category.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </aside>

            {/* Product Grid */}
            <div className="flex-1">
              {productsError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
                  <p className="text-sm text-red-600">{productsError}</p>
                </div>
              )}

              {productsLoading ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                  {[...Array(6)].map((_, i) => (
                    <div key={i} className="animate-pulse">
                      <div className="aspect-[3/4] bg-neutral-200 rounded-lg mb-4" />
                      <div className="h-4 bg-neutral-200 rounded w-3/4" />
                    </div>
                  ))}
                </div>
              ) : products.length === 0 ? (
                <div className="text-center py-16">
                  <p className="text-neutral-500">No products found</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                  {products.map((product) => (
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
                      <h3 className="font-medium text-zinc-900 line-clamp-1">{product.title}</h3>
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
          </div>
        </div>
      </main>
    </div>
  );
}
