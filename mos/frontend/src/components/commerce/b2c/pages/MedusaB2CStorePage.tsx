/**
 * Medusa B2C Store Page
 *
 * The main storefront catalog page featuring:
 * - URL-driven sorting and pagination
 * - Category navigation
 * - Theme-aware product cards and loading states
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";
import { useSearchParams } from "react-router-dom";
import { useB2CRuntime } from "../B2CRuntimeProvider";
import { resolveB2CHeadingFont, useB2CTheme } from "../useB2CTheme";
import { B2CStarterShell } from "./B2CStarterShell";
import {
  CatalogPagination,
  CatalogSortSelect,
  PRICE_SORT_FETCH_LIMIT,
  PRODUCTS_PER_PAGE,
  SkeletonProductGrid,
  StoreProductCard,
  StorefrontEmptyState,
  normalizeCatalogSort,
  sortCatalogProducts,
  type CatalogSortValue,
} from "./storefrontPrimitives";

export function MedusaB2CStorePage() {
  const {
    products,
    categories,
    productsLoading,
    productsCount,
    refreshProducts,
    navigateToProduct,
    navigateToCategory,
  } = useB2CRuntime();
  const { tokens, isThemed } = useB2CTheme();
  const [searchParams, setSearchParams] = useSearchParams();
  const [catalogCount, setCatalogCount] = useState(0);
  const [priceSortLimited, setPriceSortLimited] = useState(false);

  const currentPage = Math.max(1, Number(searchParams.get("page") || "1") || 1);
  const currentSort = normalizeCatalogSort(searchParams.get("sort"));

  const updateCatalogParams = useCallback(
    (next: { page?: number; sort?: CatalogSortValue }) => {
      const params = new URLSearchParams(searchParams);
      const nextPage = next.page ?? currentPage;
      const nextSort = next.sort ?? currentSort;

      if (nextSort === "created_at") {
        params.delete("sort");
      } else {
        params.set("sort", nextSort);
      }

      if (nextPage <= 1) {
        params.delete("page");
      } else {
        params.set("page", String(nextPage));
      }

      setSearchParams(params);
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    [currentPage, currentSort, searchParams, setSearchParams],
  );

  useEffect(() => {
    let cancelled = false;

    const loadCatalog = async () => {
      const requestLimit =
        currentSort === "created_at" ? PRODUCTS_PER_PAGE : PRICE_SORT_FETCH_LIMIT;
      const requestOffset =
        currentSort === "created_at"
          ? (currentPage - 1) * PRODUCTS_PER_PAGE
          : 0;

      const result = await refreshProducts({
        limit: requestLimit,
        offset: requestOffset,
      });

      if (cancelled || !result) {
        if (!cancelled) {
          setCatalogCount(0);
          setPriceSortLimited(false);
        }
        return;
      }

      const nextCount =
        currentSort === "created_at"
          ? result.count
          : Math.min(result.count, result.products.length);
      const totalPages = Math.max(1, Math.ceil(nextCount / PRODUCTS_PER_PAGE));

      setCatalogCount(nextCount);
      setPriceSortLimited(
        currentSort !== "created_at" && result.count > result.products.length,
      );

      if (currentPage > totalPages) {
        updateCatalogParams({ page: totalPages });
      }
    };

    void loadCatalog();

    return () => {
      cancelled = true;
    };
  }, [currentPage, currentSort, refreshProducts, updateCatalogParams]);

  const sortedProducts = useMemo(() => {
    if (currentSort === "created_at") {
      return products;
    }
    return sortCatalogProducts(products, currentSort);
  }, [currentSort, products]);

  const visibleProducts = useMemo(() => {
    if (currentSort === "created_at") {
      return products;
    }

    const start = (currentPage - 1) * PRODUCTS_PER_PAGE;
    return sortedProducts.slice(start, start + PRODUCTS_PER_PAGE);
  }, [currentPage, currentSort, products, sortedProducts]);

  const totalPages = Math.max(1, Math.ceil(catalogCount / PRODUCTS_PER_PAGE));

  const pageStyle: CSSProperties = {
    backgroundColor: tokens.colorBackground || "#ffffff",
    color: tokens.colorText || "#111827",
  };
  const headingStyle: CSSProperties = {
    color: tokens.colorText || "#111827",
    fontFamily: resolveB2CHeadingFont(tokens),
  };
  const textMutedStyle: CSSProperties = {
    color: tokens.colorTextMuted || "rgba(17, 24, 39, 0.64)",
  };
  const sidebarStyle: CSSProperties = {
    borderRightColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
  };

  return (
    <B2CStarterShell>
      <div className="min-h-screen" style={pageStyle}>
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-8 lg:flex-row">
            <aside
              className="lg:w-64 lg:flex-shrink-0 lg:border-r lg:border-border lg:pr-8"
              style={sidebarStyle}
            >
              <h2 className="mb-4 text-lg font-medium" style={headingStyle}>
                Categories
              </h2>
              <nav className="space-y-1">
                <button
                  type="button"
                  onClick={() => updateCatalogParams({ page: 1, sort: "created_at" })}
                  className="w-full rounded-lg px-3 py-2 text-left text-sm"
                  style={
                    isThemed
                      ? {
                          backgroundColor: tokens.colorPrimary || undefined,
                          color: tokens.colorPrimaryText || undefined,
                        }
                      : undefined
                  }
                >
                  All Products
                </button>
                {categories.map((category) => (
                  <button
                    key={category.id}
                    type="button"
                    onClick={() => navigateToCategory(category.handle)}
                    className="w-full rounded-lg px-3 py-2 text-left text-sm transition-opacity hover:opacity-70"
                    style={{ color: tokens.colorText || undefined }}
                  >
                    {category.name}
                  </button>
                ))}
              </nav>
            </aside>

            <div className="flex-1">
              <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div>
                  <h1 className="text-3xl font-medium" style={headingStyle}>
                    All Products
                  </h1>
                  <p className="mt-2 text-sm" style={textMutedStyle}>
                    {productsLoading
                      ? "Loading catalog..."
                      : `${catalogCount || productsCount || visibleProducts.length} products`}
                  </p>
                </div>
                <CatalogSortSelect
                  value={currentSort}
                  onChange={(value) => updateCatalogParams({ sort: value, page: 1 })}
                />
              </div>

              {priceSortLimited ? (
                <p className="mb-6 text-sm" style={textMutedStyle}>
                  Price sorting is currently limited to the first {PRICE_SORT_FETCH_LIMIT} products returned by Medusa.
                </p>
              ) : null}

              {productsLoading ? (
                <SkeletonProductGrid />
              ) : visibleProducts.length === 0 ? (
                <StorefrontEmptyState
                  title="No products available"
                  description="This storefront doesn't have any products to show yet."
                />
              ) : (
                <>
                  <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-3">
                    {visibleProducts.map((product) => (
                      <StoreProductCard
                        key={product.id}
                        product={product}
                        onClick={() => navigateToProduct(product.handle)}
                      />
                    ))}
                  </div>
                  <CatalogPagination
                    currentPage={currentPage}
                    totalPages={totalPages}
                    onPageChange={(page) => updateCatalogParams({ page })}
                  />
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </B2CStarterShell>
  );
}
