/**
 * Commerce blocks for Puck-based site pages.
 *
 * These blocks render from runtime commerce data fetched from the Medusa Store API,
 * not from static fake content. They use the FunnelRuntimeProvider context to access
 * commerce data and cart state.
 */

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode, Fragment } from "react";
import { useNavigate } from "react-router-dom";
import type {
  MedusaProduct,
  MedusaCart,
  MedusaRegion,
  MedusaCollection,
  MedusaCategory,
  MedusaShippingOption,
  MedusaPaymentProvider,
  MedusaPaymentCollection,
  SiteCommerceCompleteResponse,
} from "@/types/commerce";
import { useFunnelRuntime } from "@/funnels/puckConfig";
import { buildPublicFunnelPath, isStandaloneBundleMode } from "@/funnels/runtimeRouting";

// =============================================================================
// Commerce Runtime Context
// =============================================================================

type CommerceRuntimeContextValue = {
  // Site metadata
  siteFamily: string | null;
  commerceProvider: string | null;
  storeName: string | null;  // Store name for branding

  // Catalog data
  regions: MedusaRegion[];
  products: MedusaProduct[];
  collections: MedusaCollection[];
  categories: MedusaCategory[];

  // Current product (if specified)
  currentProduct: MedusaProduct | null;

  // Cart state
  cart: MedusaCart | null;
  cartLoading: boolean;
  cartError: string | null;

  // Cart actions
  createCart: (regionId: string, countryCode?: string, email?: string, shippingAddress?: Record<string, unknown>, items?: Array<{ variant_id: string; quantity: number }>) => Promise<MedusaCart>;
  getCart: (cartId: string) => Promise<MedusaCart>;
  updateCart: (updates: {
    email?: string;
    shipping_address?: Record<string, unknown>;
    billing_address?: Record<string, unknown>;
  }) => Promise<MedusaCart>;
  addLineItem: (variantId: string, quantity: number, cartIdOverride?: string) => Promise<MedusaCart>;
  updateLineItem: (lineId: string, quantity: number) => Promise<MedusaCart>;
  removeLineItem: (lineId: string) => Promise<void>;

  // Shipping actions
  getShippingOptions: () => Promise<MedusaShippingOption[]>;
  addShippingMethod: (optionId: string) => Promise<MedusaCart>;

  // Payment actions
  getPaymentProviders: (regionId: string) => Promise<MedusaPaymentProvider[]>;
  initializePaymentSession: (providerId: string) => Promise<MedusaPaymentCollection>;
  completeCheckout: () => Promise<SiteCommerceCompleteResponse>;

  // Refresh data
  refreshProducts: (collectionId?: string, categoryId?: string) => Promise<void>;
  refreshCategories: () => Promise<void>;
  refreshCollections: () => Promise<void>;

  // Navigation helpers
  navigateToProduct: (productHandle: string) => void;
  navigateToCategory: (categoryHandle: string) => void;
  navigateToCart: () => void;
  navigateToCheckout: () => void;
};

const CommerceRuntimeContext = createContext<CommerceRuntimeContextValue | null>(null);

export function useCommerceRuntime(): CommerceRuntimeContextValue | null {
  return useContext(CommerceRuntimeContext);
}

// =============================================================================
// Commerce Runtime Provider
// =============================================================================

type CommerceRuntimeProviderProps = {
  children: ReactNode;
  productSlug: string;
  funnelSlug: string;
  apiBaseUrl: string;
  initialRegions?: MedusaRegion[];
  initialProducts?: MedusaProduct[];
  initialCollections?: MedusaCollection[];
  initialCategories?: MedusaCategory[];
  initialCurrentProduct?: MedusaProduct | null;
  initialCurrentCategory?: MedusaCategory | null;
  siteFamily?: string | null;
  commerceProvider?: string | null;
  storeName?: string | null;  // Store name for branding
};

const CART_STORAGE_KEY_PREFIX = "medusa_cart_id:";

export function CommerceRuntimeProvider({
  children,
  productSlug,
  funnelSlug,
  apiBaseUrl,
  initialRegions = [],
  initialProducts = [],
  initialCollections = [],
  initialCategories = [],
  initialCurrentProduct = null,
  initialCurrentCategory = null,
  siteFamily = null,
  commerceProvider = null,
  storeName = null,
}: CommerceRuntimeProviderProps): ReactNode {
  const [regions, setRegions] = useState<MedusaRegion[]>(initialRegions);
  const [products, setProducts] = useState<MedusaProduct[]>(initialProducts);
  const [collections, setCollections] = useState<MedusaCollection[]>(initialCollections);
  const [categories, setCategories] = useState<MedusaCategory[]>(initialCategories);
  const [currentProduct, setCurrentProduct] = useState<MedusaProduct | null>(initialCurrentProduct);
  const [currentCategory, setCurrentCategory] = useState<MedusaCategory | null>(initialCurrentCategory);

  const [cart, setCart] = useState<MedusaCart | null>(null);
  const [cartLoading, setCartLoading] = useState(false);
  const [cartError, setCartError] = useState<string | null>(null);

  // Sync initial props when they change (e.g., after fetch completes or navigation)
  useEffect(() => {
    setRegions(initialRegions);
  }, [initialRegions]);
  useEffect(() => {
    setProducts(initialProducts);
  }, [initialProducts]);
  useEffect(() => {
    setCollections(initialCollections);
  }, [initialCollections]);
  useEffect(() => {
    setCategories(initialCategories);
  }, [initialCategories]);
  useEffect(() => {
    setCurrentProduct(initialCurrentProduct);
  }, [initialCurrentProduct]);
  useEffect(() => {
    setCurrentCategory(initialCurrentCategory);
  }, [initialCurrentCategory]);

  // Store name needs to be synced from props after siteCommerce fetch completes
  const [runtimeStoreName, setRuntimeStoreName] = useState<string | null>(storeName);
  useEffect(() => {
    setRuntimeStoreName(storeName);
  }, [storeName]);

  // Helper to build API URLs
  const buildUrl = useCallback(
    (path: string, params?: Record<string, string>) => {
      const url = new URL(
        `${apiBaseUrl}/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/site${path}`
      );
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined && value !== null) {
            url.searchParams.set(key, value);
          }
        });
      }
      return url.toString();
    },
    [apiBaseUrl, productSlug, funnelSlug]
  );

  // Get cart by ID - define before useEffect that uses it
  const getCart = useCallback(
    async (cartId: string): Promise<MedusaCart> => {
      const response = await fetch(buildUrl("/cart", { cart_id: cartId }));
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to get cart");
      }
      const data = await response.json();
      return data.cart as MedusaCart;
    },
    [buildUrl]
  );

  // Load cart ID from localStorage on mount
  useEffect(() => {
    const cartKey = `${CART_STORAGE_KEY_PREFIX}${productSlug}:${funnelSlug}`;
    const storedCartId = localStorage.getItem(cartKey);
    console.log("[CommerceRuntime] Loading cart, key:", cartKey, "storedCartId:", storedCartId);
    if (storedCartId) {
      setCartLoading(true);
      getCart(storedCartId)
        .then((c) => {
          console.log("[CommerceRuntime] Cart loaded successfully, items:", c.items?.length || 0);
          setCart(c);
        })
        .catch((err) => {
          console.log("[CommerceRuntime] Cart load failed, clearing storage:", err);
          // Cart not found or expired, clear storage
          localStorage.removeItem(cartKey);
        })
        .finally(() => setCartLoading(false));
    } else {
      console.log("[CommerceRuntime] No stored cart ID found");
    }
  }, [productSlug, funnelSlug, getCart]);

  // Cart actions
  const createCart = useCallback(
    async (regionId: string, countryCode?: string, email?: string, shippingAddress?: Record<string, unknown>, items?: Array<{ variant_id: string; quantity: number }>): Promise<MedusaCart> => {
      setCartLoading(true);
      setCartError(null);
      try {
        const response = await fetch(buildUrl("/cart"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            region_id: regionId, 
            country_code: countryCode, 
            email,
            shipping_address: shippingAddress,
            items,
          }),
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to create cart");
        }
        const data = await response.json();
        const newCart = data.cart as MedusaCart;
        setCart(newCart);
        // Store cart ID in localStorage
        const cartKey = `${CART_STORAGE_KEY_PREFIX}${productSlug}:${funnelSlug}`;
        localStorage.setItem(cartKey, newCart.id);
        return newCart;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to create cart";
        setCartError(message);
        throw err;
      } finally {
        setCartLoading(false);
      }
    },
    [buildUrl, productSlug, funnelSlug]
  );

  const updateCart = useCallback(
    async (updates: {
      email?: string;
      shipping_address?: Record<string, unknown>;
      billing_address?: Record<string, unknown>;
    }): Promise<MedusaCart> => {
      if (!cart) throw new Error("No cart to update");
      setCartLoading(true);
      setCartError(null);
      try {
        const response = await fetch(buildUrl(`/cart/${cart.id}`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to update cart");
        }
        const data = await response.json();
        const updatedCart = data.cart as MedusaCart;
        setCart(updatedCart);
        return updatedCart;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to update cart";
        setCartError(message);
        throw err;
      } finally {
        setCartLoading(false);
      }
    },
    [buildUrl, cart]
  );

  const addLineItem = useCallback(
    async (variantId: string, quantity: number, cartIdOverride?: string): Promise<MedusaCart> => {
      const targetCartId = cartIdOverride || cart?.id;
      if (!targetCartId) throw new Error("No cart to add item to");
      setCartLoading(true);
      setCartError(null);
      try {
        const response = await fetch(buildUrl(`/cart/${targetCartId}/items`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ variant_id: variantId, quantity }),
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to add item to cart");
        }
        const data = await response.json();
        const updatedCart = data.cart as MedusaCart;
        setCart(updatedCart);
        return updatedCart;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to add item to cart";
        setCartError(message);
        throw err;
      } finally {
        setCartLoading(false);
      }
    },
    [buildUrl, cart]
  );

  const updateLineItem = useCallback(
    async (lineId: string, quantity: number): Promise<MedusaCart> => {
      if (!cart) throw new Error("No cart to update");
      setCartLoading(true);
      setCartError(null);
      try {
        const response = await fetch(buildUrl(`/cart/${cart.id}/items/${lineId}`), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ quantity }),
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to update line item");
        }
        const data = await response.json();
        const updatedCart = data.cart as MedusaCart;
        setCart(updatedCart);
        return updatedCart;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to update line item";
        setCartError(message);
        throw err;
      } finally {
        setCartLoading(false);
      }
    },
    [buildUrl, cart]
  );

  const removeLineItem = useCallback(
    async (lineId: string): Promise<void> => {
      if (!cart) throw new Error("No cart to remove item from");
      setCartLoading(true);
      setCartError(null);
      try {
        const response = await fetch(buildUrl(`/cart/${cart.id}/items/${lineId}`), {
          method: "DELETE",
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to remove item from cart");
        }
        // Refresh cart after deletion
        const updatedCart = await getCart(cart.id);
        setCart(updatedCart);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to remove item from cart";
        setCartError(message);
        throw err;
      } finally {
        setCartLoading(false);
      }
    },
    [buildUrl, cart, getCart]
  );

  // Shipping actions
  const getShippingOptions = useCallback(async (): Promise<MedusaShippingOption[]> => {
    if (!cart) throw new Error("No cart to get shipping options for");
    const response = await fetch(buildUrl("/shipping-options", { cart_id: cart.id }));
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to get shipping options");
    }
    const data = await response.json();
    return data.shipping_options as MedusaShippingOption[];
  }, [buildUrl, cart]);

  const addShippingMethod = useCallback(
    async (optionId: string): Promise<MedusaCart> => {
      if (!cart) throw new Error("No cart to add shipping method to");
      setCartLoading(true);
      setCartError(null);
      try {
        const response = await fetch(buildUrl("/shipping-methods"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cart_id: cart.id, option_id: optionId }),
        });
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to add shipping method");
        }
        const data = await response.json();
        const updatedCart = data.cart as MedusaCart;
        setCart(updatedCart);
        return updatedCart;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to add shipping method";
        setCartError(message);
        throw err;
      } finally {
        setCartLoading(false);
      }
    },
    [buildUrl, cart]
  );

  // Payment actions
  const getPaymentProviders = useCallback(
    async (regionId: string): Promise<MedusaPaymentProvider[]> => {
      const response = await fetch(buildUrl("/payment-providers", { region_id: regionId }));
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to get payment providers");
      }
      const data = await response.json();
      return data.payment_providers as MedusaPaymentProvider[];
    },
    [buildUrl]
  );

  const initializePaymentSession = useCallback(
    async (providerId: string): Promise<MedusaPaymentCollection> => {
      if (!cart) throw new Error("No cart to initialize payment for");
      setCartLoading(true);
      setCartError(null);
      try {
        const response = await fetch(
          buildUrl(`/checkout/session?cart_id=${cart.id}&provider_id=${providerId}`),
          { method: "POST" }
        );
        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to initialize payment session");
        }
        const data = await response.json();
        return data.payment_collection as MedusaPaymentCollection;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to initialize payment session";
        setCartError(message);
        throw err;
      } finally {
        setCartLoading(false);
      }
    },
    [buildUrl, cart]
  );

  const completeCheckout = useCallback(async (): Promise<SiteCommerceCompleteResponse> => {
    if (!cart) throw new Error("No cart to complete");
    setCartLoading(true);
    setCartError(null);
    try {
      const response = await fetch(buildUrl(`/checkout/complete?cart_id=${cart.id}`), {
        method: "POST",
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to complete checkout");
      }
      const data = await response.json();
      // Clear cart from storage after successful checkout
      const cartKey = `${CART_STORAGE_KEY_PREFIX}${productSlug}:${funnelSlug}`;
      localStorage.removeItem(cartKey);
      setCart(null);
      return data as SiteCommerceCompleteResponse;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to complete checkout";
      setCartError(message);
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, [buildUrl, cart, productSlug, funnelSlug]);

  // Refresh data
  const refreshProducts = useCallback(
    async (collectionId?: string, categoryId?: string): Promise<void> => {
      const params: Record<string, string> = {};
      if (collectionId) params.collection_id = collectionId;
      if (categoryId) params.category_id = categoryId;
      const response = await fetch(buildUrl("/commerce", params));
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to fetch products");
      }
      const data = await response.json();
      setProducts(data.products || []);
    },
    [buildUrl]
  );

  const refreshCategories = useCallback(async (): Promise<void> => {
    const response = await fetch(buildUrl("/commerce"));
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to fetch categories");
    }
    const data = await response.json();
    setCategories(data.categories || []);
  }, [buildUrl]);

  const refreshCollections = useCallback(async (): Promise<void> => {
    const response = await fetch(buildUrl("/commerce"));
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to fetch collections");
    }
    const data = await response.json();
    setCollections(data.collections || []);
  }, [buildUrl]);

  // Navigation helpers using FunnelRuntimeProvider context
  const funnelRuntime = useFunnelRuntime();
  const navigate = useNavigate();

  // Resolve page slug by site page type (home, category, product_detail, cart, checkout)
  // Uses pageTypeMap for site experiences, falls back to pageStageMap for legacy funnels
  const resolvePageSlugByType = useCallback(
    (pageType: string): string | null => {
      console.log("[CommerceRuntime] resolvePageSlugByType called, pageType:", pageType, "funnelRuntime:", funnelRuntime ? "exists" : "null");
      if (!funnelRuntime) return null;
      
      console.log("[CommerceRuntime] pageTypeMap:", funnelRuntime.pageTypeMap);
      console.log("[CommerceRuntime] pageMap:", funnelRuntime.pageMap);
      
      // First try pageTypeMap (site experiences)
      if (funnelRuntime.pageTypeMap) {
        for (const [pageId, type] of Object.entries(funnelRuntime.pageTypeMap)) {
          if (type === pageType) {
            const slug = funnelRuntime.pageMap[pageId] || null;
            console.log("[CommerceRuntime] Found pageType:", pageType, "-> pageId:", pageId, "slug:", slug);
            return slug;
          }
        }
      }
      
      // Fallback to pageStageMap (legacy funnels) - map site types to funnel stages
      const stageMap: Record<string, string> = {
        home: "custom",
        category: "custom",
        product_detail: "sales",
        cart: "checkout",
        checkout: "checkout",
      };
      const targetStage = stageMap[pageType];
      if (!targetStage) return null;
      
      for (const [pageId, stage] of Object.entries(funnelRuntime.pageStageMap)) {
        if (stage === targetStage) {
          return funnelRuntime.pageMap[pageId] || null;
        }
      }
      return null;
    },
    [funnelRuntime]
  );

  const navigateToProduct = useCallback(
    (productHandle: string) => {
      if (!funnelRuntime) return;
      const productSlug = resolvePageSlugByType("product_detail");
      if (!productSlug) {
        console.error("Product detail page not found in site");
        return;
      }
      const path = buildPublicFunnelPath({
        productSlug: funnelRuntime.productSlug,
        funnelSlug: funnelRuntime.funnelSlug,
        slug: productSlug,
        bundleMode: funnelRuntime.bundleMode,
      });
      navigate(`${path}?product=${encodeURIComponent(productHandle)}`);
    },
    [funnelRuntime, resolvePageSlugByType, navigate]
  );

  const navigateToCategory = useCallback(
    (categoryHandle: string) => {
      if (!funnelRuntime) return;
      const categorySlug = resolvePageSlugByType("category");
      if (!categorySlug) {
        console.error("Category page not found in site");
        return;
      }
      const path = buildPublicFunnelPath({
        productSlug: funnelRuntime.productSlug,
        funnelSlug: funnelRuntime.funnelSlug,
        slug: categorySlug,
        bundleMode: funnelRuntime.bundleMode,
      });
      navigate(`${path}?category=${encodeURIComponent(categoryHandle)}`);
    },
    [funnelRuntime, resolvePageSlugByType, navigate]
  );

  const navigateToCart = useCallback(() => {
    if (!funnelRuntime) {
      console.error("[CommerceRuntime] navigateToCart - no funnelRuntime!");
      return;
    }
    const cartSlug = resolvePageSlugByType("cart");
    console.log("[CommerceRuntime] navigateToCart - resolved cartSlug:", cartSlug, "bundleMode:", funnelRuntime.bundleMode);
    if (!cartSlug) {
      console.error("Cart page not found in site");
      return;
    }
    const path = buildPublicFunnelPath({
      productSlug: funnelRuntime.productSlug,
      funnelSlug: funnelRuntime.funnelSlug,
      slug: cartSlug,
      bundleMode: funnelRuntime.bundleMode,
    });
    console.log("[CommerceRuntime] navigateToCart - navigating to:", path);
    navigate(path);
  }, [funnelRuntime, resolvePageSlugByType, navigate]);

  const navigateToCheckout = useCallback(() => {
    if (!funnelRuntime) return;
    const checkoutSlug = resolvePageSlugByType("checkout");
    if (!checkoutSlug) {
      console.error("Checkout page not found in site");
      return;
    }
    const path = buildPublicFunnelPath({
      productSlug: funnelRuntime.productSlug,
      funnelSlug: funnelRuntime.funnelSlug,
      slug: checkoutSlug,
      bundleMode: funnelRuntime.bundleMode,
    });
    navigate(path);
  }, [funnelRuntime, resolvePageSlugByType, navigate]);

  const contextValue: CommerceRuntimeContextValue = {
    siteFamily,
    commerceProvider,
    storeName: runtimeStoreName,
    regions,
    products,
    collections,
    categories,
    currentProduct,
    currentCategory,
    cart,
    cartLoading,
    cartError,
    createCart,
    getCart,
    updateCart,
    addLineItem,
    updateLineItem,
    removeLineItem,
    getShippingOptions,
    addShippingMethod,
    getPaymentProviders,
    initializePaymentSession,
    completeCheckout,
    refreshProducts,
    refreshCategories,
    refreshCollections,
    navigateToProduct,
    navigateToCategory,
    navigateToCart,
    navigateToCheckout,
  };

  return (
    <CommerceRuntimeContext.Provider value={contextValue}>
      {children}
    </CommerceRuntimeContext.Provider>
  );
}

// =============================================================================
// Commerce Block Components
// =============================================================================

/**
 * CommerceCatalogHero - Hero section for catalog/category pages
 * Displays category title and description from runtime data.
 * Starter-style: centered heading with description, cleaner typography.
 */
export function CommerceCatalogHero({ title, description }: { title?: string; description?: string }) {
  const runtime = useCommerceRuntime();
  if (!runtime) {
    return <div className="p-4 text-sm text-neutral-400">Commerce context not available</div>;
  }

  // Use currentCategory if set (from ?category= query param), otherwise fall back to first category or generic
  const displayTitle = title || runtime.currentCategory?.name || runtime.categories[0]?.name || "Products";
  const displayDescription = description || runtime.currentCategory?.description || runtime.categories[0]?.description || "";

  // Starter-style: full-width hero with large centered content
  return (
    <section className="h-[75vh] w-full border-b border-neutral-200 relative bg-neutral-100">
      <div className="absolute inset-0 z-[1] flex flex-col justify-center items-center text-center px-6 sm:px-32 gap-6">
        <span>
          <p className="text-neutral-600 text-xs uppercase tracking-wider">
            {displayDescription ? displayTitle : "Browse our collection"}
          </p>
          <h1 className="text-6xl leading-tight text-zinc-900 font-normal mt-6 mb-5">
            {displayTitle}
          </h1>
          {displayDescription && (
            <p className="leading-relaxed text-neutral-500 font-normal text-lg max-w-xl mx-auto">
              {displayDescription}
            </p>
          )}
        </span>
        <button
          onClick={() => {
            // Scroll to products section
            const productsEl = document.querySelector('[data-testid="products-list"]');
            if (productsEl) {
              productsEl.scrollIntoView({ behavior: "smooth", block: "start" });
            }
          }}
          className="px-6 py-2.5 border border-zinc-900 rounded-full text-sm font-medium text-zinc-900 hover:bg-zinc-900 hover:text-white transition-colors duration-200"
        >
          Browse Products
        </button>
      </div>
    </section>
  );
}

/**
 * CommerceProductGrid - Grid of products from runtime data
 * B2B starter parity: cleaner cards, stronger image/info/price hierarchy.
 */
export function CommerceProductGrid({ columns = 3 }: { columns?: number }) {
  const runtime = useCommerceRuntime();
  if (!runtime) {
    return <div className="p-4 text-sm text-neutral-500">Commerce context not available</div>;
  }

  const { products } = runtime;

  if (products.length === 0) {
    return (
      <div className="rounded-lg bg-white p-8 text-center text-sm text-neutral-500 shadow-sm">
        No products found.
      </div>
    );
  }

  const gridCols = columns === 2 ? "small:grid-cols-2" : columns === 4 ? "small:grid-cols-4" : "small:grid-cols-3";

  const handleProductClick = (product: MedusaProduct) => {
    if (product.handle) {
      runtime.navigateToProduct(product.handle);
    }
  };

  const formatPrice = (product: MedusaProduct) => {
    if (!product) return null;

    const parseAmount = (amount: unknown): number | null => {
      if (amount === null || amount === undefined) return null;
      if (typeof amount === "number" && !isNaN(amount)) return amount;
      if (typeof amount === "string") {
        const parsed = parseFloat(amount);
        if (!isNaN(parsed)) return parsed;
      }
      return null;
    };

    const variant = product.variants?.[0];
    if (variant && variant.prices && Array.isArray(variant.prices) && variant.prices.length > 0) {
      const usdPrice = variant.prices.find((p) => p && p.currency_code && p.currency_code.toUpperCase() === "USD");
      const price = usdPrice || variant.prices[0];
      if (price) {
        const amount = parseAmount(price.amount);
        if (amount !== null) {
          const currency = price.currency_code?.toUpperCase() || "USD";
          return `${currency} ${(amount / 100).toFixed(2)}`;
        }
      }
    }

    const allVariants = product.variants || [];
    for (const v of allVariants) {
      if (v && v.prices && Array.isArray(v.prices) && v.prices.length > 0) {
        const price = v.prices[0];
        if (price) {
          const amount = parseAmount(price.amount);
          if (amount !== null) {
            const currency = price.currency_code?.toUpperCase() || "USD";
            return `${currency} ${(amount / 100).toFixed(2)}`;
          }
        }
      }
    }
    return null;
  };

  const getInventoryQuantity = (product: MedusaProduct): number => {
    return (product.variants || []).reduce((acc, v) => acc + ((v as Record<string, unknown>).inventory_quantity as number || 0), 0);
  };

  return (
    <ul className={`grid grid-cols-1 ${gridCols} gap-3`} data-testid="products-list">
      {products.map((product) => {
        const inventory = getInventoryQuantity(product);
        const priceStr = formatPrice(product);
        return (
          <li key={product.id}>
            <div
              className="group cursor-pointer"
              onClick={() => handleProductClick(product)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") handleProductClick(product);
              }}
              tabIndex={0}
              role="button"
              data-testid="product-wrapper"
            >
              <div className="flex flex-col gap-4 relative aspect-[3/5] w-full overflow-hidden p-4 bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] group-hover:shadow-[0_0_0_4px_rgba(0,0,0,0.1)] transition-shadow ease-in-out duration-150">
                {/* Thumbnail */}
                <div className="w-full flex-1 flex items-center justify-center p-8">
                  {product.thumbnail ? (
                    <img
                      src={product.thumbnail}
                      alt={product.title}
                      className="h-full w-full object-contain"
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full w-full">
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor" className="w-12 h-12 text-neutral-300">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v13.5A1.5 1.5 0 003.75 21z" />
                      </svg>
                    </div>
                  )}
                </div>

                {/* Product info */}
                <div className="flex flex-col">
                  <span className="text-neutral-500 text-[10px] uppercase tracking-wider">Brand</span>
                  <span className="text-zinc-900 text-sm font-medium line-clamp-1" data-testid="product-title">
                    {product.title}
                  </span>
                </div>

                {/* Price */}
                <div className="flex flex-col">
                  <span className="text-zinc-900 font-semibold text-sm" data-testid="product-price">
                    {priceStr ? `From ${priceStr}` : "Price not available"}
                  </span>
                  <span className="text-neutral-500 text-[10px]">Excl. VAT</span>
                </div>

                {/* Inventory + Quick add */}
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <span className={`text-lg leading-none ${
                      inventory > 50 ? "text-green-500" :
                      inventory > 0 ? "text-orange-500" :
                      "text-red-500"
                    }`}>
                      &bull;
                    </span>
                    <span className="text-neutral-500 text-xs">
                      {inventory > 0 ? `${inventory} left` : "Out of stock"}
                    </span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleProductClick(product);
                    }}
                    className="rounded-full border border-neutral-200 p-1.5 hover:bg-neutral-100 transition-colors"
                    title="View product"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 text-neutral-600">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * CommerceStoreTemplate - Category/store page layout wrapper
 * B2B starter parity: cleaner breadcrumb, stronger left rail, calmer grid container.
 */
export function CommerceStoreTemplate({
  children,
}: {
  children: ReactNode;
}) {
  const runtime = useCommerceRuntime();
  const funnelRuntime = useFunnelRuntime();

  const { currentCategory, categories } = runtime || {};
  const categoryName = currentCategory?.name || "All Products";
  const parentCategories = categories?.filter((c) => !c.parent_category_id) || [];

  const handleHomeClick = () => {
    if (!funnelRuntime) return;
    const homeSlug = Object.entries(funnelRuntime.pageTypeMap || {}).find(
      ([, type]) => type === "home"
    )?.[0];
    if (homeSlug && funnelRuntime.pageMap[homeSlug]) {
      const path = buildPublicFunnelPath({
        productSlug: funnelRuntime.productSlug,
        funnelSlug: funnelRuntime.funnelSlug,
        slug: funnelRuntime.pageMap[homeSlug],
        bundleMode: funnelRuntime.bundleMode,
      });
      window.location.href = path;
    }
  };

  const isCategoryPage = currentCategory !== null && currentCategory !== undefined;

  return (
    <div className="bg-neutral-100 min-h-screen">
      <div className="flex flex-col py-6 mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 gap-4" data-testid="category-container">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1.5 text-sm text-neutral-500">
          <button onClick={handleHomeClick} className="hover:text-zinc-900 transition-colors">
            Home
          </button>
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-3.5 h-3.5 text-neutral-400">
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
          {isCategoryPage ? (
            <span className="text-zinc-900 font-medium">{currentCategory?.name}</span>
          ) : (
            <span className="text-zinc-900 font-medium">All Products</span>
          )}
        </nav>

        <div className="flex flex-col small:flex-row small:items-start gap-3">
          {/* Left rail - B2B starter RefinementList style */}
          <div className="flex flex-col divide-neutral-200 small:w-1/5 w-full gap-3">
            {/* Search + Sort container */}
            <div className="bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] p-0 overflow-hidden">
              <div className="px-4 py-3 border-b border-neutral-100">
                <input
                  type="text"
                  placeholder={`Search in ${categoryName}...`}
                  disabled
                  className="w-full text-sm text-zinc-900 placeholder:text-neutral-400 bg-transparent focus:outline-none"
                  title="Search coming soon"
                />
              </div>
              <div className="px-4 py-3">
                <span className="text-xs font-medium text-neutral-500 uppercase tracking-wider">Sort by</span>
                <select className="w-full mt-1 text-sm text-zinc-900 bg-transparent focus:outline-none" disabled>
                  <option>Latest Arrivals</option>
                  <option>Price: Low to High</option>
                  <option>Price: High to Low</option>
                </select>
              </div>
            </div>

            {/* Categories list */}
            {parentCategories.length > 0 && (
              <div className="bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] overflow-hidden">
                <div className="px-4 py-3 border-b border-neutral-100">
                  <span className="text-xs font-medium text-neutral-500 uppercase tracking-wider">Categories</span>
                </div>
                <ul className="p-2">
                  {parentCategories.slice(0, 12).map((cat) => {
                    const isSelected = currentCategory?.id === cat.id;
                    return (
                      <li key={cat.id}>
                        <button
                          onClick={() => runtime?.navigateToCategory(cat.handle)}
                          className={`w-full text-left px-3 py-2 text-sm rounded-md transition-colors ${
                            isSelected
                              ? 'bg-neutral-100 text-zinc-900 font-medium'
                              : 'text-neutral-600 hover:text-zinc-900 hover:bg-neutral-50'
                          }`}
                        >
                          {cat.name}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </div>

          {/* Right: Product grid */}
          <div className="w-full">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * CommerceProductDetail - Product detail page content
 * Displays current product from runtime data with variants and add-to-cart.
 * Starter-style: left gallery, right info/actions on neutral surface, facts section, related products.
 * Matches Medusa Next.js starter: stronger visual weight for gallery, cleaner info panel.
 */
export function CommerceProductDetail() {
  const runtime = useCommerceRuntime();
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);

  if (!runtime) {
    return <div className="p-4 text-sm text-content-muted">Commerce context not available</div>;
  }

  const { currentProduct, cart, products } = runtime;

  if (!currentProduct) {
    return (
      <div className="p-8 text-center">
        <p className="text-lg text-zinc-600">Product not found</p>
        <p className="text-sm text-zinc-500 mt-2">The requested product could not be loaded.</p>
      </div>
    );
  }

  const variants = currentProduct.variants || [];
  const selectedVariant = selectedVariantId
    ? variants.find((v) => v.id === selectedVariantId)
    : variants[0];

  const handleAddToCart = async () => {
    if (!selectedVariant) return;
    setAdding(true);
    setAdded(false);
    try {
      let currentCartId = cart?.id || null;
      if (!currentCartId) {
        // Create cart first with default region
        const region = runtime.regions[0];
        if (!region) {
          throw new Error("No region available");
        }
        // Use the returned cart immediately for the add operation
        const createdCart = await runtime.createCart(region.id);
        currentCartId = createdCart.id;
      }
      await runtime.addLineItem(selectedVariant.id, quantity, currentCartId);
      setAdded(true);
    } catch (err) {
      console.error("Failed to add to cart:", err);
    } finally {
      setAdding(false);
    }
  };

  const handleViewCart = () => {
    runtime.navigateToCart();
  };

  const handleProductClick = (product: MedusaProduct) => {
    if (product.handle) {
      runtime.navigateToProduct(product.handle);
    }
  };

  // Get related products (products in the same collection or category, excluding current)
  const relatedProducts = products
    .filter(p => p.id !== currentProduct.id)
    .slice(0, 4);

  // Starter-style: two-column layout with gallery left, info/actions on neutral surface
  return (
    <div className="flex flex-col gap-y-2 my-2">
      {/* Main product section - starter-style grid */}
      <div
        className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-2 gap-2 w-full h-fit"
        data-testid="product-container"
      >
        {/* Left: Visual/Gallery area - B2B starter style */}
        <div className="flex flex-col justify-center items-center bg-neutral-100 p-8 pt-4 gap-6 w-full min-h-[500px]">
          <div className="relative w-full flex-1 flex items-center justify-center p-8">
            {currentProduct.thumbnail ? (
              <img
                src={currentProduct.thumbnail}
                alt={currentProduct.title}
                className="max-h-[500px] w-full object-contain"
              />
            ) : (
              <div className="flex items-center justify-center w-full h-64">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor" className="w-16 h-16 text-neutral-300">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v13.5A1.5 1.5 0 003.75 21z" />
                </svg>
              </div>
            )}
          </div>
          {/* Image thumbnails if multiple images exist */}
          {currentProduct.images && currentProduct.images.length > 1 && (
            <div className="flex gap-2 overflow-x-auto pb-2">
              {currentProduct.images.map((img: { id: string; url: string }, idx: number) => (
                <div key={img.id || idx} className="flex-shrink-0 w-10 h-10 rounded-md overflow-hidden border border-neutral-200">
                  <img src={img.url} alt="" className="w-full h-full object-contain" />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Info/Actions panel on neutral surface - B2B starter style */}
        <div className="flex flex-col bg-neutral-100 w-full gap-6 items-start justify-center small:p-16 p-6 h-full">
          {/* Product info - B2B starter uses large 2.5rem heading */}
          <div id="product-info" className="w-full">
            <h1 className="text-[2.5rem] leading-10 text-zinc-900 font-normal" data-testid="product-title">
              {currentProduct.title}
            </h1>
            {currentProduct.subtitle && (
              <p className="mt-4 text-2xl text-neutral-500 whitespace-pre-line" data-testid="product-description">
                {currentProduct.subtitle}
              </p>
            )}
          </div>

          {/* Price display - B2B starter style */}
          {selectedVariant && selectedVariant.prices && selectedVariant.prices.length > 0 && selectedVariant.prices[0].amount != null && (
            <div className="flex flex-col text-neutral-950">
              <span className="font-medium text-xl" data-testid="product-price">
                From {selectedVariant.prices[0].currency_code?.toUpperCase() || "USD"}{" "}
                {((selectedVariant.prices[0].amount || 0) / 100).toFixed(2)}
              </span>
              <span className="text-neutral-600 text-[0.6rem]">Excl. VAT</span>
            </div>
          )}

          {/* Variant selector - B2B starter style table-like */}
          {variants.length > 1 && (
            <div className="w-full">
              <div className="border border-neutral-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-neutral-50 border-b border-neutral-200">
                      <th className="text-left px-4 py-2 font-medium text-neutral-600">Variant</th>
                      <th className="text-right px-4 py-2 font-medium text-neutral-600">Price</th>
                      <th className="text-center px-4 py-2 font-medium text-neutral-600">Qty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {variants.map((v) => {
                      const isSelected = (selectedVariantId || variants[0]?.id) === v.id;
                      const price = v.prices?.[0];
                      return (
                        <tr
                          key={v.id}
                          className={`border-b border-neutral-200 last:border-b-0 cursor-pointer transition-colors ${
                            isSelected ? "bg-neutral-50" : "hover:bg-neutral-50"
                          }`}
                          onClick={() => setSelectedVariantId(v.id)}
                        >
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                                isSelected ? "border-zinc-900" : "border-neutral-300"
                              }`}>
                                {isSelected && <div className="w-2 h-2 rounded-full bg-zinc-900" />}
                              </div>
                              <span className="text-zinc-900">{v.title}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-right text-zinc-900">
                            {price && price.amount != null
                              ? `${price.currency_code?.toUpperCase() || "USD"} ${((price.amount || 0) / 100).toFixed(2)}`
                              : "-"}
                          </td>
                          <td className="px-4 py-3">
                            {isSelected && (
                              <div className="flex items-center justify-center">
                                <div className="flex items-center border border-neutral-200 rounded-md">
                                  <button
                                    onClick={(e) => { e.stopPropagation(); setQuantity(Math.max(1, quantity - 1)); }}
                                    className="px-2 py-1 text-neutral-500 hover:text-zinc-900 hover:bg-neutral-100 transition-colors"
                                  >-</button>
                                  <input
                                    type="number"
                                    min={1}
                                    value={quantity}
                                    onClick={(e) => e.stopPropagation()}
                                    onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                                    className="w-12 text-center border-x border-neutral-200 py-1 bg-transparent text-zinc-900 focus:outline-none"
                                  />
                                  <button
                                    onClick={(e) => { e.stopPropagation(); setQuantity(quantity + 1); }}
                                    className="px-2 py-1 text-neutral-500 hover:text-zinc-900 hover:bg-neutral-100 transition-colors"
                                  >+</button>
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Single variant: just quantity */}
          {variants.length <= 1 && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-neutral-600">Quantity</span>
              <div className="flex items-center border border-neutral-200 rounded-md">
                <button
                  onClick={() => setQuantity(Math.max(1, quantity - 1))}
                  className="px-3 py-1.5 text-neutral-500 hover:text-zinc-900 hover:bg-neutral-100 transition-colors"
                >-</button>
                <input
                  type="number"
                  min={1}
                  value={quantity}
                  onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                  className="w-14 text-center border-x border-neutral-200 py-1.5 bg-transparent text-zinc-900 focus:outline-none"
                />
                <button
                  onClick={() => setQuantity(quantity + 1)}
                  className="px-3 py-1.5 text-neutral-500 hover:text-zinc-900 hover:bg-neutral-100 transition-colors"
                >+</button>
              </div>
            </div>
          )}

          {/* Add to cart actions */}
          <div className="flex gap-3 w-full">
            <button
              onClick={handleAddToCart}
              disabled={adding || !selectedVariant}
              className="flex-1 h-10 rounded-full bg-zinc-900 px-8 text-sm font-medium text-white disabled:opacity-50 hover:bg-zinc-800 transition-colors shadow-none"
            >
              {adding ? "Adding..." : "Add to Cart"}
            </button>
            {added && (
              <button
                onClick={handleViewCart}
                className="h-10 rounded-full shadow-[0_0_0_1px_rgba(0,0,0,0.1)] bg-white px-6 text-sm font-medium text-zinc-900 hover:bg-neutral-100 transition-colors"
              >
                View Cart
              </button>
            )}
          </div>

          {runtime.cartError && (
            <p className="mt-2 text-sm text-red-600">{runtime.cartError}</p>
          )}
        </div>
      </div>

      {/* Product tabs/details section - B2B starter accordion style */}
      <div className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-y-2">
          {/* Description accordion */}
          <details className="bg-neutral-100 rounded-lg group" open>
            <summary className="flex items-center justify-between cursor-pointer small:px-16 px-6 py-6 text-lg font-medium text-zinc-900">
              Description
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 text-neutral-500 group-open:rotate-180 transition-transform">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
              </svg>
            </summary>
            <div className="small:px-16 px-6 pb-8 text-sm text-neutral-700 leading-relaxed max-w-2xl">
              {currentProduct.description || "No description available."}
            </div>
          </details>

          {/* Specifications accordion */}
          <details className="bg-neutral-100 rounded-lg group">
            <summary className="flex items-center justify-between cursor-pointer small:px-16 px-6 py-6 text-lg font-medium text-zinc-900">
              Specifications
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 text-neutral-500 group-open:rotate-180 transition-transform">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
              </svg>
            </summary>
            <div className="small:px-16 px-6 pb-8">
              <table className="w-full text-sm rounded-lg overflow-hidden border border-neutral-200">
                <tbody>
                  {currentProduct.weight && (
                    <tr className="border-b border-neutral-200">
                      <td className="px-4 py-3 border-r border-neutral-200 font-medium text-zinc-900">Weight</td>
                      <td className="px-4 py-3 text-neutral-700">{currentProduct.weight} grams</td>
                    </tr>
                  )}
                  {(currentProduct.height || currentProduct.width || currentProduct.length) && (
                    <tr className="border-b border-neutral-200">
                      <td className="px-4 py-3 border-r border-neutral-200 font-medium text-zinc-900">Dimensions</td>
                      <td className="px-4 py-3 text-neutral-700">
                        {currentProduct.height || "-"}mm x {currentProduct.width || "-"}mm x {currentProduct.length || "-"}mm
                      </td>
                    </tr>
                  )}
                  {currentProduct.metadata && Object.entries(currentProduct.metadata).map(([key, value]) => (
                    <tr key={key} className="border-b border-neutral-200 last:border-b-0">
                      <td className="px-4 py-3 border-r border-neutral-200 font-medium text-zinc-900">{key}</td>
                      <td className="px-4 py-3 text-neutral-700">{value as string}</td>
                    </tr>
                  ))}
                  {!currentProduct.weight && !currentProduct.height && !currentProduct.metadata && (
                    <tr>
                      <td className="px-4 py-3 text-neutral-500" colSpan={2}>No specifications available.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </details>
        </div>
      </div>

      {/* Related products section - B2B starter style */}
      {relatedProducts.length > 0 && (
        <div
          className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-12"
          data-testid="related-products-container"
        >
          <div className="flex justify-between mb-8">
            <span className="text-base font-medium text-zinc-900">Related Products</span>
          </div>
          <ul className="grid grid-cols-1 small:grid-cols-4 gap-3">
            {relatedProducts.map((product) => (
              <li key={product.id}>
                <div
                  className="flex flex-col gap-3 p-4 bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] cursor-pointer hover:shadow-[0_0_0_4px_rgba(0,0,0,0.1)] transition-shadow ease-in-out duration-150"
                  onClick={() => handleProductClick(product)}
                >
                  {product.thumbnail ? (
                    <div className="aspect-square bg-neutral-50 rounded-md flex items-center justify-center p-4">
                      <img
                        src={product.thumbnail}
                        alt={product.title}
                        className="h-full w-full object-contain"
                      />
                    </div>
                  ) : (
                    <div className="aspect-square bg-neutral-50 rounded-md flex items-center justify-center">
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor" className="w-8 h-8 text-neutral-300">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v13.5A1.5 1.5 0 003.75 21z" />
                      </svg>
                    </div>
                  )}
                  <div className="flex flex-col">
                    <span className="text-neutral-500 text-[10px] uppercase tracking-wider">Brand</span>
                    <span className="text-sm font-medium text-zinc-900 line-clamp-1">{product.title}</span>
                  </div>
                  {product.variants?.[0]?.prices?.[0] && product.variants[0].prices[0].amount != null && (
                    <div className="flex flex-col">
                      <span className="text-sm font-semibold text-zinc-900">
                        {product.variants[0].prices[0].currency_code?.toUpperCase() || "USD"}{" "}
                        {((product.variants[0].prices[0].amount || 0) / 100).toFixed(2)}
                      </span>
                      <span className="text-neutral-500 text-[10px]">Excl. VAT</span>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * CommerceCart - Shopping cart display
 * Shows cart contents from runtime data with quantity controls.
 * Starter-style: item list on left, summary on right with cleaner totals.
 */
export function CommerceCart() {
  const runtime = useCommerceRuntime();
  const [updating, setUpdating] = useState<string | null>(null);

  if (!runtime) {
    return <div className="p-4 text-sm text-neutral-400">Commerce context not available</div>;
  }

  const { cart, cartLoading } = runtime;

  if (cartLoading && !cart) {
    return <div className="p-4 text-sm text-neutral-400">Loading cart...</div>;
  }

  if (!cart || !cart.items || cart.items.length === 0) {
    return <div className="p-8 text-sm text-neutral-400 text-center">Your cart is empty</div>;
  }

  const handleUpdateQuantity = async (lineId: string, newQuantity: number) => {
    setUpdating(lineId);
    try {
      if (newQuantity === 0) {
        await runtime.removeLineItem(lineId);
      } else {
        await runtime.updateLineItem(lineId, newQuantity);
      }
    } catch (err) {
      console.error("Failed to update quantity:", err);
    } finally {
      setUpdating(null);
    }
  };

  // Calculate total items for display
  const totalItems = cart.items.reduce((acc, item) => acc + item.quantity, 0);

  // Format currency helper
  const formatCurrency = (amount: number | undefined) => {
    if (amount === undefined) return "";
    return `${cart.currency_code.toUpperCase()} ${(amount / 100).toFixed(2)}`;
  };

  // B2B starter style cart layout
  return (
    <div className="small:py-12 py-6 bg-neutral-100">
      <div className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8" data-testid="cart-container">
        <div className="flex flex-col py-6 gap-y-6">
          {/* Header */}
          <div className="pb-3 flex items-center border-b border-neutral-200">
            <h1 className="text-neutral-950 text-[2rem] leading-10 font-normal">
              Cart
            </h1>
          </div>

          <div className="grid grid-cols-1 small:grid-cols-[1fr_380px] gap-x-8">
            {/* Left: Items list */}
            <div>
              <div className="pb-3 flex items-center justify-between border-b border-neutral-200 mb-4">
                <span className="text-sm text-neutral-600">
                  {totalItems} item{totalItems !== 1 ? "s" : ""} in cart
                </span>
              </div>

              <div className="flex flex-col gap-y-2">
                {cart.items.map((item) => (
                  <div
                    key={item.id}
                    className="flex gap-4 bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] p-4"
                  >
                    {/* Thumbnail */}
                    <div className="flex-shrink-0 w-24 h-24 bg-neutral-50 rounded-md flex items-center justify-center overflow-hidden">
                      {item.thumbnail ? (
                        <img src={item.thumbnail} alt={item.title} className="w-full h-full object-contain p-1" />
                      ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor" className="w-8 h-8 text-neutral-300">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v13.5A1.5 1.5 0 003.75 21z" />
                        </svg>
                      )}
                    </div>

                    {/* Details */}
                    <div className="flex-1 min-w-0 flex flex-col justify-between">
                      <div>
                        <h3 className="text-sm font-medium text-zinc-900 line-clamp-1">{item.title}</h3>
                        {item.variant && (
                          <p className="text-xs text-neutral-500 mt-0.5">{item.variant.title}</p>
                        )}
                      </div>

                      {/* Quantity stepper - B2B starter pill style */}
                      <div className="flex items-center gap-x-3 shadow-[0_0_0_1px_rgba(0,0,0,0.1)] rounded-full w-fit p-px mt-2">
                        <button
                          onClick={() => handleUpdateQuantity(item.id, item.quantity - 1)}
                          disabled={updating === item.id}
                          className="w-6 h-6 flex items-center justify-center text-neutral-600 hover:bg-neutral-100 rounded-full text-sm disabled:opacity-50 transition-colors"
                        >-</button>
                        <input
                          type="number"
                          min={0}
                          value={item.quantity}
                          onChange={(e) => handleUpdateQuantity(item.id, Math.max(0, parseInt(e.target.value) || 0))}
                          className="w-10 h-6 text-center text-neutral-950 text-xs [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none bg-transparent shadow-none focus:outline-none"
                        />
                        <button
                          onClick={() => handleUpdateQuantity(item.id, item.quantity + 1)}
                          disabled={updating === item.id}
                          className="w-6 h-6 flex items-center justify-center text-neutral-600 hover:bg-neutral-100 rounded-full text-sm disabled:opacity-50 transition-colors"
                        >+</button>
                      </div>
                    </div>

                    {/* Price + Delete */}
                    <div className="flex flex-col items-end justify-between">
                      <button
                        onClick={() => handleUpdateQuantity(item.id, 0)}
                        disabled={updating === item.id}
                        className="p-1 text-neutral-400 hover:text-red-500 transition-colors"
                        title="Remove item"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                        </svg>
                      </button>
                      <div className="text-right">
                        <div className="text-sm font-medium text-zinc-900">
                          {formatCurrency(item.total || item.unit_price * item.quantity)}
                        </div>
                        {item.quantity > 1 && (
                          <div className="text-[11px] text-neutral-500">
                            {formatCurrency(item.unit_price)} each
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Right: Summary */}
            <div className="relative mt-6 small:mt-0">
              <div className="flex flex-col gap-y-4 sticky top-24">
                <div className="bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] p-6">
                  {/* Totals */}
                  <div className="flex flex-col gap-y-2 text-sm text-neutral-600">
                    <div className="flex items-center justify-between">
                      <span>Subtotal (excl. shipping and taxes)</span>
                      <span className="text-zinc-900" data-testid="cart-item-subtotal">{formatCurrency(cart.subtotal || cart.item_subtotal)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Shipping</span>
                      <span className="text-zinc-900" data-testid="cart-shipping">{formatCurrency(cart.shipping_total || 0)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Taxes</span>
                      <span className="text-zinc-900" data-testid="cart-taxes">{formatCurrency(cart.tax_total || 0)}</span>
                    </div>
                  </div>

                  <div className="my-4 h-px bg-neutral-200" />

                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-zinc-900">Total</span>
                    <span className="text-lg font-semibold text-zinc-900" data-testid="cart-total">
                      {formatCurrency(cart.total)}
                    </span>
                  </div>

                  <div className="my-4 h-px bg-neutral-200" />

                  {/* Actions */}
                  <button
                    onClick={() => runtime.navigateToCheckout()}
                    className="w-full h-10 rounded-full bg-zinc-900 text-sm font-medium text-white hover:bg-zinc-800 transition-colors shadow-none"
                  >
                    Go to Checkout
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * CommerceCheckout - Checkout form with shipping and payment
 * Handles checkout flow against Medusa Store API.
 * 
 * Flow:
 * 1. Contact + Shipping Address (step 1)
 * 2. Shipping Method (step 2) - loaded after address is saved
 * 3. Payment (step 3) - loaded after shipping is selected
 * 4. Review & Complete (step 4)
 * 
 * Starter-style: stepper treatment, left form / right summary balance.
 */
export function CommerceCheckout() {
  const runtime = useCommerceRuntime();
  const [currentStep, setCurrentStep] = useState<"address" | "shipping" | "payment" | "review">("address");
  const [email, setEmail] = useState("");
  const [shippingAddress, setShippingAddress] = useState({
    first_name: "",
    last_name: "",
    address_1: "",
    city: "",
    postal_code: "",
    country_code: "",
  });
  const [selectedShippingOption, setSelectedShippingOption] = useState<string | null>(null);
  const [selectedPaymentProvider, setSelectedPaymentProvider] = useState<string | null>(null);
  const [shippingOptions, setShippingOptions] = useState<MedusaShippingOption[]>([]);
  const [paymentProviders, setPaymentProviders] = useState<MedusaPaymentProvider[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  const funnelRuntime = useFunnelRuntime();

  if (!runtime) {
    return <div className="p-4 text-sm text-content-muted">Commerce context not available</div>;
  }

  const { cart, regions } = runtime;

  // Get default country from cart region - computed before early return
  // so useEffect hook order remains stable
  const cartRegion = cart ? regions.find((r) => r.id === cart.region_id) : null;
  const availableCountries = cartRegion?.countries || [];
  const defaultCountry = availableCountries[0]?.iso_2 || "";

  // Hydrate email and shipping address from cart on mount/revisit
  // and set default country if not already set
  // This useEffect MUST be declared before any early returns to maintain
  // stable hook order - it handles null cart internally
  useEffect(() => {
    if (initialized) return;
    
    let newEmail = "";
    let newShippingAddress = {
      first_name: "",
      last_name: "",
      address_1: "",
      city: "",
      postal_code: "",
      country_code: defaultCountry,
    };

    // Hydrate from cart if available
    if (cart) {
      if (cart.email) {
        newEmail = cart.email;
      }
      if (cart.shipping_address) {
        newShippingAddress = {
          first_name: cart.shipping_address.first_name || "",
          last_name: cart.shipping_address.last_name || "",
          address_1: cart.shipping_address.address_1 || "",
          city: cart.shipping_address.city || "",
          postal_code: cart.shipping_address.postal_code || "",
          country_code: cart.shipping_address.country_code || defaultCountry,
        };
      }
    }

    if (newEmail) setEmail(newEmail);
    if (newShippingAddress.first_name || newShippingAddress.address_1) {
      setShippingAddress(newShippingAddress);
    } else if (!shippingAddress.country_code && defaultCountry) {
      setShippingAddress(prev => ({ ...prev, country_code: defaultCountry }));
    }
    
    setInitialized(true);
  }, [cart, defaultCountry, initialized]);

  // Empty state when no cart - rendered AFTER all hooks are declared
  // to maintain stable hook order across all renders
  if (!cart) {
    // Clearer empty state with navigation back to shopping
    const handleContinueShopping = () => {
      if (funnelRuntime) {
        const homeSlug = Object.entries(funnelRuntime.pageTypeMap || {}).find(
          ([, type]) => type === "home"
        )?.[0];
        if (homeSlug && funnelRuntime.pageMap[homeSlug]) {
          const path = buildPublicFunnelPath({
            productSlug: funnelRuntime.productSlug,
            funnelSlug: funnelRuntime.funnelSlug,
            slug: funnelRuntime.pageMap[homeSlug],
            bundleMode: funnelRuntime.bundleMode,
          });
          window.location.href = path;
        }
      }
    };

    return (
      <div className="flex flex-col items-center justify-center py-16 px-4 text-center bg-neutral-100">
        <div className="max-w-md">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-16 h-16 mx-auto text-neutral-400 mb-4">
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 00-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.924-7.138a60.114 60.114 0 00-16.536-1.84M7.5 14.25L5.106 5.272M6 20.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm12.75 0a.75.75 0 11-1.5 0 .75.75 0 011.5 0z" />
          </svg>
          <h2 className="text-xl font-semibold text-zinc-900 mb-2">No items in cart</h2>
          <p className="text-neutral-500 mb-6">You need to add items to your cart before proceeding to checkout.</p>
          <div className="flex gap-4 justify-center">
            <button
              onClick={() => runtime.navigateToCart()}
              className="rounded-full bg-zinc-900 px-6 py-3 font-semibold text-white hover:bg-zinc-900-hover transition-colors"
            >
              View Cart
            </button>
            <button
              onClick={handleContinueShopping}
              className="rounded-full border border-neutral-200 bg-white px-6 py-3 font-semibold text-zinc-900 hover:bg-neutral-100 transition-colors"
            >
              Continue Shopping
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Format currency
  const formatCurrency = (amount: number | undefined, currencyCode: string) => {
    if (amount === undefined) return "";
    return `${currencyCode.toUpperCase()} ${(amount / 100).toFixed(2)}`;
  };

  // Step 1: Save email (and optionally shipping address), then load shipping options
  // Note: We only update email to Medusa API for now, as shipping_address on cart update
  // causes a 500 error on the live Medusa server. Shipping address is stored in local state
  // for display/review purposes.
  const handleSaveAddress = async () => {
    if (!email) {
      setError("Please enter your email address");
      return;
    }

    if (!shippingAddress.first_name || !shippingAddress.last_name || !shippingAddress.address_1 || 
        !shippingAddress.city || !shippingAddress.postal_code || !shippingAddress.country_code) {
      setError("Please fill in all shipping address fields");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      // Update cart with email only - shipping_address causes 500 error on live Medusa server
      await runtime.updateCart({ email });

      // Load shipping options
      const options = await runtime.getShippingOptions();
      if (options.length === 0) {
        setError("No shipping options available. Please contact support.");
        setLoading(false);
        return;
      }
      setShippingOptions(options);
      setCurrentStep("shipping");
      
      // Auto-scroll to shipping step after options load
      setTimeout(() => {
        const shippingStepElement = document.getElementById("checkout-shipping-step");
        if (shippingStepElement) {
          shippingStepElement.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }, 100);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to save address";
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Select shipping and load payment providers
  const handleSelectShipping = async (optionId: string) => {
    setLoading(true);
    setError(null);
    try {
      setSelectedShippingOption(optionId);
      await runtime.addShippingMethod(optionId);
      
      // Load payment providers after shipping is selected
      if (cart.region_id) {
        const providers = await runtime.getPaymentProviders(cart.region_id);
        if (providers.length === 0) {
          setError("No payment providers available. Please contact support.");
          setLoading(false);
          return;
        }
        setPaymentProviders(providers);
        setCurrentStep("payment");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to select shipping method");
    } finally {
      setLoading(false);
    }
  };

  // Step 3: Select payment provider
  const handleSelectPayment = (providerId: string) => {
    setSelectedPaymentProvider(providerId);
    setCurrentStep("review");
  };

  // Step 4: Complete checkout
  const handleCompleteCheckout = async () => {
    setLoading(true);
    setError(null);
    try {
      // Initialize payment session if provider selected
      if (selectedPaymentProvider) {
        const paymentCollection = await runtime.initializePaymentSession(selectedPaymentProvider);
        
        // Check if payment session requires redirect
        const sessions = paymentCollection.payment_sessions || [];
        const session = sessions.find((s) => s.provider_id === selectedPaymentProvider);
        if (session?.data?.redirect_url) {
          // Provider requires redirect (e.g., Stripe Checkout)
          window.location.href = session.data.redirect_url as string;
          return;
        }
      }

      // Complete checkout
      const result = await runtime.completeCheckout();
      if (result.type === "order" && result.order) {
        // Navigate to success page
        const currentPath = window.location.pathname;
        window.location.href = `${currentPath}?checkout=success`;
      } else {
        setError("Checkout could not be completed. Please try again.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
    } finally {
      setLoading(false);
    }
  };

  // Calculate totals
  const subtotal = cart.subtotal || 0;
  const shippingTotal = cart.shipping_total || 0;
  const total = cart.total || 0;
  const currencyCode = cart.currency_code || "usd";

  // Step names for stepper display
  const steps = [
    { key: "address", label: "Contact" },
    { key: "shipping", label: "Shipping" },
    { key: "payment", label: "Payment" },
    { key: "review", label: "Review" },
  ];

  // Find current step index
  const currentStepIndex = steps.findIndex(s => s.key === currentStep);

  // B2B starter style checkout layout
  return (
    <div className="small:py-12 py-6 bg-neutral-100">
      <div className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-8">
          {/* Left column: Checkout form */}
          <div className="w-full grid grid-cols-1 gap-y-4">
            {/* Back to cart link */}
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                runtime.navigateToCart();
              }}
              className="flex items-center gap-2 text-sm text-neutral-500 hover:text-zinc-900 transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
              </svg>
              Back to shopping cart
            </a>

            {/* Step indicator */}
            <div className="flex items-center gap-2 text-sm py-3">
              {steps.map((step, index) => (
                <Fragment key={step.key}>
                  <button
                    onClick={() => { if (index < currentStepIndex) setCurrentStep(step.key as typeof currentStep); }}
                    className={`${index <= currentStepIndex ? "text-zinc-900 font-medium" : "text-neutral-400"} ${index < currentStepIndex ? "hover:underline cursor-pointer" : "cursor-default"}`}
                  >
                    {step.label}
                  </button>
                  {index < steps.length - 1 && (
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-3.5 h-3.5 text-neutral-300">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                    </svg>
                  )}
                </Fragment>
              ))}
            </div>

            {/* Step 1: Contact & Address */}
            {currentStep === "address" && (
              <div className="w-full grid grid-cols-1 gap-y-4">
                {/* Contact Information section */}
                <div className="bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] p-6">
                  <h2 className="text-base font-medium text-zinc-900 mb-4">Contact Information</h2>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Email address"
                    required
                    className="block w-full rounded-md border border-neutral-200 bg-neutral-50 px-3.5 py-2.5 text-sm text-zinc-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-zinc-900/20"
                  />
                </div>

                {/* Shipping Address section */}
                <div className="bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] p-6">
                  <h2 className="text-base font-medium text-zinc-900 mb-4">Shipping Address</h2>
                  <div className="grid gap-4">
                    <div className="grid grid-cols-2 gap-4">
                      <input
                        type="text"
                        value={shippingAddress.first_name}
                        onChange={(e) => setShippingAddress({ ...shippingAddress, first_name: e.target.value })}
                        placeholder="First name"
                        required
                        className="rounded-md border border-neutral-200 bg-neutral-50 px-3.5 py-2.5 text-sm text-zinc-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-zinc-900/20"
                      />
                      <input
                        type="text"
                        value={shippingAddress.last_name}
                        onChange={(e) => setShippingAddress({ ...shippingAddress, last_name: e.target.value })}
                        placeholder="Last name"
                        required
                        className="rounded-md border border-neutral-200 bg-neutral-50 px-3.5 py-2.5 text-sm text-zinc-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-zinc-900/20"
                      />
                    </div>
                    <input
                      type="text"
                      value={shippingAddress.address_1}
                      onChange={(e) => setShippingAddress({ ...shippingAddress, address_1: e.target.value })}
                      placeholder="Address"
                      required
                      className="block w-full rounded-md border border-neutral-200 bg-neutral-50 px-3.5 py-2.5 text-sm text-zinc-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-zinc-900/20"
                    />
                    <div className="grid grid-cols-2 gap-4">
                      <input
                        type="text"
                        value={shippingAddress.city}
                        onChange={(e) => setShippingAddress({ ...shippingAddress, city: e.target.value })}
                        placeholder="City"
                        required
                        className="rounded-md border border-neutral-200 bg-neutral-50 px-3.5 py-2.5 text-sm text-zinc-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-zinc-900/20"
                      />
                      <input
                        type="text"
                        value={shippingAddress.postal_code}
                        onChange={(e) => setShippingAddress({ ...shippingAddress, postal_code: e.target.value })}
                        placeholder="Postal code"
                        required
                        className="rounded-md border border-neutral-200 bg-neutral-50 px-3.5 py-2.5 text-sm text-zinc-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-zinc-900/20"
                      />
                    </div>
                    <select
                      value={shippingAddress.country_code}
                      onChange={(e) => setShippingAddress({ ...shippingAddress, country_code: e.target.value })}
                      required
                      className="block w-full rounded-lg border border-neutral-200 bg-neutral-50 px-3.5 py-2.5 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 focus:border-zinc-900/20"
                    >
                      <option value="">Select country</option>
                      {availableCountries.map((c) => (
                        <option key={c.iso_2} value={c.iso_2}>
                          {c.display_name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {error && (
                  <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <button
                  type="button"
                  onClick={handleSaveAddress}
                  disabled={loading}
                  className="w-full h-10 rounded-full bg-zinc-900 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 transition-colors shadow-none"
                >
                  {loading ? "Saving..." : "Continue to Shipping"}
                </button>
              </div>
            )}

            {/* Step 2: Shipping Method */}
            {currentStep === "shipping" && (
              <div className="w-full grid grid-cols-1 gap-y-4">
                <div className="bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] p-6">
                  <h2 className="text-base font-medium text-zinc-900 mb-4">Shipping Method</h2>
                  {shippingOptions.length === 0 ? (
                    <p className="text-neutral-500">No shipping options available for your address.</p>
                  ) : (
                    <div className="space-y-3">
                      {shippingOptions.map((option) => (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => handleSelectShipping(option.id)}
                          disabled={loading}
                          className={`w-full flex items-center justify-between rounded-md border p-4 text-left transition-colors ${
                            selectedShippingOption === option.id
                              ? "border-zinc-900 bg-neutral-50 ring-1 ring-zinc-900"
                              : "border-neutral-200 bg-white hover:border-neutral-300"
                          }`}
                        >
                          <div>
                            <p className="font-medium text-zinc-900">{option.name}</p>
                            {option.description && (
                              <p className="text-sm text-neutral-500">{option.description}</p>
                            )}
                          </div>
                          <span className="font-medium text-zinc-900">
                            {formatCurrency(option.amount, option.currency_code || currencyCode)}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {error && (
                  <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <button
                  type="button"
                  onClick={() => setCurrentStep("address")}
                  className="text-sm text-neutral-500 hover:text-zinc-900 flex items-center gap-1.5 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
                  </svg>
                  Back to address
                </button>
              </div>
            )}

            {/* Step 3: Payment */}
            {currentStep === "payment" && (
              <div className="w-full grid grid-cols-1 gap-y-4">
                <div className="bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] p-6">
                  <h2 className="text-base font-medium text-zinc-900 mb-4">Payment Method</h2>
                  {paymentProviders.length === 0 ? (
                    <p className="text-neutral-500">No payment methods available.</p>
                  ) : (
                    <div className="space-y-3">
                      {paymentProviders.map((provider) => (
                        <button
                          key={provider.id}
                          type="button"
                          onClick={() => handleSelectPayment(provider.id)}
                          disabled={loading}
                          className={`w-full flex items-center justify-between rounded-md border p-4 text-left transition-colors ${
                            selectedPaymentProvider === provider.id
                              ? "border-zinc-900 bg-neutral-50 ring-1 ring-zinc-900"
                              : "border-neutral-200 bg-white hover:border-neutral-300"
                          }`}
                        >
                          <span className="font-medium text-zinc-900">
                            {provider.id === "pp_system_default" ? "Pay on Delivery" : 
                             provider.id === "manual" ? "Manual Payment" :
                             provider.id.replace("pp_", "").replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase())}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {error && (
                  <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <button
                  type="button"
                  onClick={() => setCurrentStep("shipping")}
                  className="text-sm text-neutral-500 hover:text-zinc-900 flex items-center gap-1.5 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
                  </svg>
                  Back to shipping
                </button>
              </div>
            )}

            {/* Step 4: Review */}
            {currentStep === "review" && (
              <div className="w-full grid grid-cols-1 gap-y-4">
                <div className="bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] p-6">
                  <h2 className="text-base font-medium text-zinc-900 mb-4">Review Order</h2>
                  
                  {/* Contact summary */}
                  <div className="mb-4 pb-4 border-b border-neutral-200">
                    <p className="text-sm text-neutral-500">Contact</p>
                    <p className="text-zinc-900">{email}</p>
                  </div>

                  {/* Address summary */}
                  <div className="mb-4 pb-4 border-b border-neutral-200">
                    <p className="text-sm text-neutral-500">Ship to</p>
                    <p className="text-zinc-900">
                      {shippingAddress.first_name} {shippingAddress.last_name}<br />
                      {shippingAddress.address_1}<br />
                      {shippingAddress.city}, {shippingAddress.postal_code}<br />
                      {availableCountries.find(c => c.iso_2 === shippingAddress.country_code)?.display_name || shippingAddress.country_code}
                    </p>
                  </div>

                  {/* Shipping summary */}
                  <div className="mb-4 pb-4 border-b border-neutral-200">
                    <p className="text-sm text-neutral-500">Shipping</p>
                    <p className="text-zinc-900">
                      {shippingOptions.find(o => o.id === selectedShippingOption)?.name || "Selected shipping"}
                    </p>
                  </div>

                  {/* Payment summary */}
                  <div>
                    <p className="text-sm text-neutral-500">Payment</p>
                    <p className="text-zinc-900">
                      {selectedPaymentProvider === "pp_system_default" ? "Pay on Delivery" : 
                       selectedPaymentProvider === "manual" ? "Manual Payment" :
                       selectedPaymentProvider?.replace("pp_", "").replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase()) || "Selected payment"}
                    </p>
                  </div>
                </div>

                {error && (
                  <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <button
                  type="button"
                  onClick={handleCompleteCheckout}
                  disabled={loading}
                  className="w-full h-10 rounded-full bg-zinc-900 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 transition-colors shadow-none"
                >
                  {loading ? "Processing..." : "Complete Order"}
                </button>

                <button
                  type="button"
                  onClick={() => setCurrentStep("payment")}
                  className="text-sm text-neutral-500 hover:text-zinc-900 flex items-center gap-1.5 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
                  </svg>
                  Back to payment
                </button>
              </div>
            )}
          </div>

          {/* Right column: Order summary - sticky - starter style */}
          <div className="lg:sticky lg:top-4 h-fit">
            <div className="bg-white rounded-lg shadow-[0_0_0_1px_rgba(0,0,0,0.08)] p-6">
              <h2 className="text-base font-medium text-zinc-900 mb-4">Order Summary</h2>
              
              {/* Line items */}
              <div className="space-y-3 mb-4 pb-4 border-b border-neutral-200">
                {cart.items?.map((item) => (
                  <div key={item.id} className="flex items-start justify-between text-sm">
                    <div className="flex-1">
                      <p className="text-zinc-900 font-medium">{item.title}</p>
                      <p className="text-neutral-500">Qty: {item.quantity}</p>
                    </div>
                    <p className="text-zinc-900">
                      {formatCurrency(item.unit_price, currencyCode)}
                    </p>
                  </div>
                ))}
              </div>

              {/* Totals - cleaner like starter */}
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-neutral-500">Subtotal</span>
                  <span className="text-zinc-900">{formatCurrency(subtotal, currencyCode)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-neutral-500">Shipping</span>
                  <span className="text-zinc-900">
                    {shippingTotal > 0 ? formatCurrency(shippingTotal, currencyCode) : "Calculated at checkout"}
                  </span>
                </div>
                <div className="flex justify-between pt-2 border-t border-neutral-200 font-medium">
                  <span className="text-zinc-900">Total</span>
                  <span className="text-zinc-900">{formatCurrency(total, currencyCode)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * CommerceCategoryList - List of categories from runtime data
 */
export function CommerceCategoryList() {
  const runtime = useCommerceRuntime();
  if (!runtime) {
    return <div className="p-4 text-sm text-content-muted">Commerce context not available</div>;
  }

  const { categories } = runtime;

  if (categories.length === 0) {
    return null;
  }

  const handleCategoryClick = (category: MedusaCategory) => {
    if (category.handle) {
      runtime.navigateToCategory(category.handle);
    }
  };

  return (
    <div className="space-y-3">
      <h3 className="text-xl font-semibold text-zinc-900">Categories</h3>
      <ul className="space-y-1.5">
        {categories.map((category) => (
          <li key={category.id}>
            <button
              onClick={() => handleCategoryClick(category)}
              className="text-neutral-500 hover:text-zinc-900 cursor-pointer bg-transparent border-none p-0 text-left transition-colors text-sm"
            >
              {category.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * CommerceCategoryHeading - Displays the currently selected category heading
 * Shows the selected category name with breadcrumb-style navigation
 */
export function CommerceCategoryHeading() {
  const runtime = useCommerceRuntime();
  const funnelRuntime = useFunnelRuntime();

  if (!runtime) {
    return null;
  }

  const { currentCategory, categories } = runtime;
  const categoryName = currentCategory?.name || "All Products";

  const handleHomeClick = () => {
    if (!funnelRuntime) return;
    const homeSlug = Object.entries(funnelRuntime.pageTypeMap || {}).find(
      ([, type]) => type === "home"
    )?.[0];
    if (homeSlug && funnelRuntime.pageMap[homeSlug]) {
      const path = buildPublicFunnelPath({
        productSlug: funnelRuntime.productSlug,
        funnelSlug: funnelRuntime.funnelSlug,
        slug: funnelRuntime.pageMap[homeSlug],
        bundleMode: funnelRuntime.bundleMode,
      });
      window.location.href = path;
    }
  };

  return (
    <div className="flex items-center gap-2 text-sm text-zinc-500 py-4">
      <button
        onClick={handleHomeClick}
        className="hover:text-zinc-700 transition-colors"
      >
        Home
      </button>
      <span>/</span>
      <span className="text-zinc-900 font-medium">{categoryName}</span>
    </div>
  );
}

/**
 * CommerceCartSummary - Mini cart summary for headers/sidebars
 */
export function CommerceCartSummary() {
  const runtime = useCommerceRuntime();
  if (!runtime) {
    return null;
  }

  const { cart } = runtime;

  if (!cart || !cart.items || cart.items.length === 0) {
    return (
      <div className="text-sm text-content-muted">
        Cart (0 items)
      </div>
    );
  }

  const itemCount = cart.items.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <div className="text-sm">
      <span className="font-medium text-content">Cart ({itemCount} items)</span>
      <span className="ml-2 text-content-muted">
        {cart.currency_code.toUpperCase()} {(cart.total || 0) / 100}
      </span>
    </div>
  );
}

/**
 * CommerceStoreHeader - Store header with navigation and cart
 * B2B starter parity: tighter visual hierarchy, calmer nav rhythm, cleaner cart affordance.
 * Matches Medusa Next.js starter: compact header, subtle nav links, minimal cart button.
 */
export function CommerceStoreHeader({
  storeName: storeNameProp = "Store",
  showSearch = false,
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

  const handleHomeClick = () => {
    if (!funnelRuntime) return;
    const homeSlug = Object.entries(funnelRuntime.pageTypeMap || {}).find(
      ([, type]) => type === "home"
    )?.[0];
    if (homeSlug && funnelRuntime.pageMap[homeSlug]) {
      const path = buildPublicFunnelPath({
        productSlug: funnelRuntime.productSlug,
        funnelSlug: funnelRuntime.funnelSlug,
        slug: funnelRuntime.pageMap[homeSlug],
        bundleMode: funnelRuntime.bundleMode,
      });
      navigate(path);
    }
  };

  const handleCartClick = () => {
    runtime?.navigateToCart();
  };

  const handleCategoryClick = (category: MedusaCategory) => {
    if (category.handle) {
      runtime?.navigateToCategory(category.handle);
    }
  };

  const categories = runtime?.categories || [];
  const mainCategories = categories.filter((c) => !c.parent_category_id);

  const cart = runtime?.cart;
  const itemCount = cart?.items?.reduce((sum, item) => sum + item.quantity, 0) || 0;

  return (
    <header className="sticky top-0 inset-x-0 z-50 bg-white text-zinc-900 border-b border-neutral-200">
      <div className="flex w-full mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 justify-between items-center small:py-4 py-3">
        {/* Left: Brand + Nav */}
        <div className="flex items-center small:gap-6 gap-4">
          <button
            onClick={handleHomeClick}
            className="flex items-center gap-2 hover:text-zinc-700 transition-colors"
          >
            {/* Store icon */}
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 21v-7.5a.75.75 0 01.75-.75h3a.75.75 0 01.75.75V21m-4.5 0H2.36m11.14 0H18m0 0h3.64m-1.39 0V9.349m-16.5 11.65V9.35m0 0a3.001 3.001 0 003.75-.615A2.993 2.993 0 009.75 9.75c.896 0 1.7-.393 2.25-1.016a2.993 2.993 0 002.25 1.016c.896 0 1.7-.393 2.25-1.016A3.001 3.001 0 0021 9.349m-18 0a2.999 2.999 0 014.308-1.852A2.999 2.999 0 019.75 6h4.5a2.999 2.999 0 014.442 1.497A2.999 2.999 0 0121 9.349" />
            </svg>
            <span className="text-sm font-medium small:text-base">{storeName}</span>
          </button>

          {mainCategories.length > 0 && (
            <nav className="hidden small:flex items-center gap-1">
              {mainCategories.slice(0, 6).map((category) => (
                <button
                  key={category.id}
                  onClick={() => handleCategoryClick(category)}
                  className="text-sm hover:bg-neutral-100 rounded-full px-3 py-1.5 text-zinc-600 hover:text-zinc-900 transition-colors"
                >
                  {category.name}
                </button>
              ))}
            </nav>
          )}
        </div>

        {/* Right: Search + Cart */}
        <div className="flex items-center gap-2">
          {showSearch && (
            <div className="relative hidden small:inline-flex">
              <input
                type="text"
                placeholder="Search for products"
                disabled
                className="bg-neutral-100 text-zinc-900 px-4 py-2 rounded-full pr-10 text-sm shadow-sm hover:cursor-not-allowed"
                title="Search coming soon"
              />
            </div>
          )}

          <div className="h-5 w-px bg-neutral-200 hidden small:block" />

          {showCart && (
            <button
              onClick={handleCartClick}
              className="relative flex items-center gap-1.5 rounded-2xl px-3 py-1.5 text-sm hover:bg-neutral-100 transition-colors"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="h-5 w-5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007zM8.625 10.5a.375.375 0 11-.75 0 .375.375 0 01.75 0zm7.5 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"
                />
              </svg>
              {itemCount > 0 && (
                <span className="absolute -top-1 -right-0.5 flex items-center justify-center bg-zinc-900 text-white text-[10px] font-medium rounded-full min-w-[18px] h-[18px] px-1">
                  {itemCount}
                </span>
              )}
            </button>
          )}

          {/* Mobile menu toggle */}
          {mainCategories.length > 0 && (
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="small:hidden p-1.5 rounded-md hover:bg-neutral-100"
            >
              {menuOpen ? (
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                </svg>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Mobile menu dropdown */}
      {menuOpen && mainCategories.length > 0 && (
        <div className="small:hidden border-t border-neutral-200 bg-white px-4 py-3">
          <nav className="flex flex-col gap-1">
            {mainCategories.slice(0, 8).map((category) => (
              <button
                key={category.id}
                onClick={() => {
                  handleCategoryClick(category);
                  setMenuOpen(false);
                }}
                className="text-left text-sm px-3 py-2 rounded-md text-zinc-600 hover:text-zinc-900 hover:bg-neutral-100 transition-colors"
              >
                {category.name}
              </button>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}

/**
 * CommerceStoreFooter - Store footer with categories, collections, and links
 * B2B starter parity: cleaner columns, tighter spacing, calmer bottom row.
 * Matches Medusa Next.js starter: compact footer with subtle links.
 */
export function CommerceStoreFooter({
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
  const categories = runtime?.categories || [];
  const collections = runtime?.collections || [];
  const mainCategories = categories.filter((c) => !c.parent_category_id);

  const handleHomeClick = () => {
    if (!funnelRuntime) return;
    const homeSlug = Object.entries(funnelRuntime.pageTypeMap || {}).find(
      ([, type]) => type === "home"
    )?.[0];
    if (homeSlug && funnelRuntime.pageMap[homeSlug]) {
      const path = buildPublicFunnelPath({
        productSlug: funnelRuntime.productSlug,
        funnelSlug: funnelRuntime.funnelSlug,
        slug: funnelRuntime.pageMap[homeSlug],
        bundleMode: funnelRuntime.bundleMode,
      });
      navigate(path);
    }
  };

  const handleCategoryClick = (category: MedusaCategory) => {
    if (category.handle) {
      runtime?.navigateToCategory(category.handle);
    }
  };

  const currentYear = new Date().getFullYear();

  return (
    <footer className="border-t border-neutral-200 w-full">
      <div className="flex flex-col w-full mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8">
        {/* Main footer content - B2B starter style: generous padding */}
        <div className="flex flex-col gap-y-6 sm:flex-row items-start justify-between py-20 sm:py-32">
          {/* Brand */}
          <div className="max-w-[200px]">
            <button
              onClick={handleHomeClick}
              className="text-lg font-semibold uppercase text-neutral-500 hover:text-zinc-900 transition-colors tracking-wider leading-snug text-left"
            >
              {storeName}
            </button>
          </div>

          {/* Link columns */}
          <div className="text-sm gap-10 md:gap-x-16 grid grid-cols-2 sm:grid-cols-3">
            {/* Categories */}
            {showCategories && mainCategories.length > 0 && (
              <div className="flex flex-col gap-y-3">
                <span className="text-sm font-semibold text-zinc-900 uppercase">Categories</span>
                <ul className="grid grid-cols-1 gap-2" data-testid="footer-categories">
                  {mainCategories.slice(0, 6).map((category) => {
                    const children = categories.filter(c => c.parent_category_id === category.id);
                    return (
                      <li key={category.id} className="flex flex-col gap-2 text-neutral-500 text-sm">
                        <button
                          onClick={() => handleCategoryClick(category)}
                          className={`text-left hover:text-zinc-900 transition-colors ${children.length > 0 ? "font-medium" : ""}`}
                          data-testid="category-link"
                        >
                          {category.name}
                        </button>
                        {children.length > 0 && (
                          <ul className="grid grid-cols-1 ml-3 gap-2">
                            {children.slice(0, 4).map((child) => (
                              <li key={child.id}>
                                <button
                                  onClick={() => handleCategoryClick(child)}
                                  className="text-left text-neutral-500 hover:text-zinc-900 transition-colors text-sm"
                                >
                                  {child.name}
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Collections */}
            {showCollections && collections.length > 0 && (
              <div className="flex flex-col gap-y-3">
                <span className="text-sm font-semibold text-zinc-900 uppercase">Collections</span>
                <ul className="grid grid-cols-1 gap-2 text-neutral-500 text-sm">
                  {collections.slice(0, 6).map((collection) => (
                    <li key={collection.id}>
                      <span className="hover:text-zinc-900 cursor-pointer transition-colors">
                        {collection.title}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Company */}
            <div className="flex flex-col gap-y-3">
              <span className="text-sm font-semibold text-zinc-900 uppercase">{storeName}</span>
              <ul className="grid grid-cols-1 gap-y-2 text-neutral-500 text-sm">
                <li><span className="hover:text-zinc-900 cursor-pointer transition-colors">About</span></li>
                <li><span className="hover:text-zinc-900 cursor-pointer transition-colors">Contact</span></li>
                <li><span className="hover:text-zinc-900 cursor-pointer transition-colors">Terms of Service</span></li>
                <li><span className="hover:text-zinc-900 cursor-pointer transition-colors">Privacy Policy</span></li>
              </ul>
            </div>
          </div>
        </div>

        {/* Bottom row */}
        <div className="flex w-full mb-16 justify-between text-neutral-400 border-t border-neutral-200 pt-6">
          <span className="text-xs">
            © {currentYear} {storeName}. All rights reserved.
          </span>
          <span className="text-xs">
            Powered by Medusa
          </span>
        </div>
      </div>
    </footer>
  );
}

// =============================================================================
// Starter-Specific Components for Medusa B2B Starter Parity
// These components provide visual shell parity with the upstream Medusa B2B starter
// =============================================================================

/**
 * StarterStoreHeader - Medusa B2B starter-style header
 * Visual shell only: no live search, quote, or account functionality
 * Props: { storeName?: string, showSearch?: boolean, showCart?: boolean }
 */
export function StarterStoreHeader({
  storeName: storeNameProp = "Store",
  showSearch = false,
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

  const handleHomeClick = () => {
    if (!funnelRuntime) return;
    const homeSlug = Object.entries(funnelRuntime.pageTypeMap || {}).find(
      ([, type]) => type === "home"
    )?.[0];
    if (homeSlug && funnelRuntime.pageMap[homeSlug]) {
      const path = buildPublicFunnelPath({
        productSlug: funnelRuntime.productSlug,
        funnelSlug: funnelRuntime.funnelSlug,
        slug: funnelRuntime.pageMap[homeSlug],
        bundleMode: funnelRuntime.bundleMode,
      });
      navigate(path);
    }
  };

  const handleCartClick = () => {
    runtime?.navigateToCart();
  };

  const handleCategoryClick = (category: MedusaCategory) => {
    if (category.handle) {
      runtime?.navigateToCategory(category.handle);
    }
  };

  const categories = runtime?.categories || [];
  const mainCategories = categories.filter((c) => !c.parent_category_id);

  const cart = runtime?.cart;
  const itemCount = cart?.items?.reduce((sum, item) => sum + item.quantity, 0) || 0;

  return (
    <header className="sticky top-0 inset-x-0 z-50 bg-white text-zinc-900 border-b border-neutral-200">
      <div className="flex w-full mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 justify-between items-center small:py-4 py-3">
        {/* Left: Brand + Nav */}
        <div className="flex items-center small:gap-6 gap-4">
          <button
            onClick={handleHomeClick}
            className="flex items-center gap-2 hover:text-zinc-700 transition-colors"
          >
            {/* Store icon */}
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 21v-7.5a.75.75 0 01.75-.75h3a.75.75 0 01.75.75V21m-4.5 0H2.36m11.14 0H18m0 0h3.64m-1.39 0V9.349m-16.5 11.65V9.35m0 0a3.001 3.001 0 003.75-.615A2.993 2.993 0 009.75 9.75c.896 0 1.7-.393 2.25-1.016a2.993 2.993 0 002.25 1.016c.896 0 1.7-.393 2.25-1.016A3.001 3.001 0 0021 9.349m-18 0a2.999 2.999 0 014.308-1.852A2.999 2.999 0 019.75 6h4.5a2.999 2.999 0 014.442 1.497A2.999 2.999 0 0121 9.349" />
            </svg>
            <span className="text-sm font-medium small:text-base">{storeName}</span>
          </button>

          {mainCategories.length > 0 && (
            <nav className="hidden small:flex items-center gap-1">
              {mainCategories.slice(0, 6).map((category) => (
                <button
                  key={category.id}
                  onClick={() => handleCategoryClick(category)}
                  className="text-sm hover:bg-neutral-100 rounded-full px-3 py-1.5 text-zinc-600 hover:text-zinc-900 transition-colors"
                >
                  {category.name}
                </button>
              ))}
            </nav>
          )}
        </div>

        {/* Right: Search + Cart */}
        <div className="flex items-center gap-2">
          {showSearch && (
            <div className="relative hidden small:inline-flex">
              <input
                type="text"
                placeholder="Search for products"
                disabled
                className="bg-neutral-100 text-zinc-900 px-4 py-2 rounded-full pr-10 text-sm shadow-sm hover:cursor-not-allowed"
                title="Search coming soon"
              />
            </div>
          )}

          <div className="h-5 w-px bg-neutral-200 hidden small:block" />

          {showCart && (
            <button
              onClick={handleCartClick}
              className="relative flex items-center gap-1.5 rounded-2xl px-3 py-1.5 text-sm hover:bg-neutral-100 transition-colors"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="h-5 w-5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007zM8.625 10.5a.375.375 0 11-.75 0 .375.375 0 01.75 0zm7.5 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"
                />
              </svg>
              {itemCount > 0 && (
                <span className="absolute -top-1 -right-0.5 flex items-center justify-center bg-zinc-900 text-white text-[10px] font-medium rounded-full min-w-[18px] h-[18px] px-1">
                  {itemCount}
                </span>
              )}
            </button>
          )}

          {/* Mobile menu toggle */}
          {mainCategories.length > 0 && (
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="small:hidden p-1.5 rounded-md hover:bg-neutral-100"
            >
              {menuOpen ? (
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                </svg>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Mobile menu dropdown */}
      {menuOpen && mainCategories.length > 0 && (
        <div className="small:hidden border-t border-neutral-200 bg-white px-4 py-3">
          <nav className="flex flex-col gap-1">
            {mainCategories.slice(0, 8).map((category) => (
              <button
                key={category.id}
                onClick={() => {
                  handleCategoryClick(category);
                  setMenuOpen(false);
                }}
                className="text-left text-sm px-3 py-2 rounded-md text-zinc-600 hover:text-zinc-900 hover:bg-neutral-100 transition-colors"
              >
                {category.name}
              </button>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}

/**
 * StarterPromoBar - Dark announcement strip beneath header
 * Props: { message?: string, ctaLabel?: string, linkType?: "funnelPage"|"nextPage"|"external", targetPageId?: string, href?: string }
 */
export function StarterPromoBar({
  message = "Free shipping on orders over $100",
  ctaLabel,
  linkType = "funnelPage",
  targetPageId,
  href,
}: {
  message?: string;
  ctaLabel?: string;
  linkType?: "funnelPage" | "nextPage" | "external";
  targetPageId?: string;
  href?: string;
}) {
  const funnelRuntime = useFunnelRuntime();
  const navigate = useNavigate();

  const handleClick = () => {
    if (!funnelRuntime) return;

    if (linkType === "external" && href) {
      window.open(href, "_blank");
      return;
    }

    if (linkType === "nextPage" && funnelRuntime.nextPageId) {
      const targetSlug = funnelRuntime.pageMap[funnelRuntime.nextPageId];
      if (targetSlug) {
        const path = buildPublicFunnelPath({
          productSlug: funnelRuntime.productSlug,
          funnelSlug: funnelRuntime.funnelSlug,
          slug: targetSlug,
          bundleMode: funnelRuntime.bundleMode,
        });
        navigate(path);
      }
      return;
    }

    if (linkType === "funnelPage" && targetPageId) {
      const targetSlug = funnelRuntime.pageMap[targetPageId];
      if (targetSlug) {
        const path = buildPublicFunnelPath({
          productSlug: funnelRuntime.productSlug,
          funnelSlug: funnelRuntime.funnelSlug,
          slug: targetSlug,
          bundleMode: funnelRuntime.bundleMode,
        });
        navigate(path);
      }
    }
  };

  return (
    <div className="bg-zinc-900 text-white text-sm">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-2.5 flex items-center justify-center gap-2">
        <span className="text-neutral-300">{message}</span>
        {ctaLabel && (
          <button
            onClick={handleClick}
            className="text-white underline underline-offset-2 hover:text-neutral-300 transition-colors font-medium"
          >
            {ctaLabel}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * StarterHomeHero - Full-bleed hero with centered content
 * Uses real runtime products referenced by featuredProductHandles for media
 * Fails clearly when required hero data is missing
 * Props: { eyebrow?: string, title?: string, description?: string, primaryCtaLabel?: string, primaryLinkType?: "funnelPage"|"nextPage"|"external", primaryTargetPageId?: string, primaryHref?: string, featuredProductHandles?: string[] }
 */
export function StarterHomeHero({
  eyebrow = "New Collection",
  title = "Discover Our Products",
  description = "Quality items for your everyday needs.",
  primaryCtaLabel = "Shop Now",
  primaryLinkType = "funnelPage",
  primaryTargetPageId,
  primaryHref,
  featuredProductHandles = [],
}: {
  eyebrow?: string;
  title?: string;
  description?: string;
  primaryCtaLabel?: string;
  primaryLinkType?: "funnelPage" | "nextPage" | "external";
  primaryTargetPageId?: string;
  primaryHref?: string;
  featuredProductHandles?: string[];
}) {
  const runtime = useCommerceRuntime();
  const funnelRuntime = useFunnelRuntime();
  const navigate = useNavigate();

  // Get featured products from runtime based on handles
  const featuredProducts = featuredProductHandles
    .map((handle) => runtime?.products?.find((p) => p.handle === handle))
    .filter((p): p is MedusaProduct => p !== undefined);

  // For hero media, use the first featured product's thumbnail if available
  const heroProduct = featuredProducts[0];
  const heroImageUrl = heroProduct?.thumbnail;

  // Fail clearly if hero cannot be rendered honestly
  if (featuredProductHandles.length > 0 && !heroImageUrl) {
    throw new Error(
      `StarterHomeHero: featuredProductHandles provided but no product thumbnails available. ` +
      `Handles: ${featuredProductHandles.join(", ")}. ` +
      `Ensure products have thumbnails in Medusa.`
    );
  }

  const handleCtaClick = () => {
    if (!funnelRuntime) return;

    if (primaryLinkType === "external" && primaryHref) {
      window.open(primaryHref, "_blank");
      return;
    }

    if (primaryLinkType === "nextPage" && funnelRuntime.nextPageId) {
      const targetSlug = funnelRuntime.pageMap[funnelRuntime.nextPageId];
      if (targetSlug) {
        const path = buildPublicFunnelPath({
          productSlug: funnelRuntime.productSlug,
          funnelSlug: funnelRuntime.funnelSlug,
          slug: targetSlug,
          bundleMode: funnelRuntime.bundleMode,
        });
        navigate(path);
      }
      return;
    }

    if (primaryLinkType === "funnelPage" && primaryTargetPageId) {
      const targetSlug = funnelRuntime.pageMap[primaryTargetPageId];
      if (targetSlug) {
        const path = buildPublicFunnelPath({
          productSlug: funnelRuntime.productSlug,
          funnelSlug: funnelRuntime.funnelSlug,
          slug: targetSlug,
          bundleMode: funnelRuntime.bundleMode,
        });
        navigate(path);
      }
    }
  };

  return (
    <div className="relative w-full min-h-[60vh] small:min-h-[75vh] bg-neutral-100 border-b border-neutral-200">
      {/* Background image from featured product or neutral fallback */}
      {heroImageUrl ? (
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url(${heroImageUrl})` }}
        >
          <div className="absolute inset-0 bg-black/30" />
        </div>
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-neutral-100 to-neutral-200" />
      )}

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center justify-center text-center px-4 sm:px-6 lg:px-8 py-16 small:py-32 min-h-[60vh] small:min-h-[75vh]">
        <div className="max-w-2xl mx-auto space-y-6">
          {eyebrow && (
            <p className={`text-xs uppercase tracking-wider ${heroImageUrl ? 'text-white/80' : 'text-neutral-600'}`}>
              {eyebrow}
            </p>
          )}
          <h1 className={`text-4xl small:text-5xl lg:text-6xl font-normal leading-tight ${heroImageUrl ? 'text-white' : 'text-zinc-900'}`}>
            {title}
          </h1>
          {description && (
            <p className={`text-lg small:text-xl font-normal ${heroImageUrl ? 'text-white/90' : 'text-neutral-600'}`}>
              {description}
            </p>
          )}
          {primaryCtaLabel && (
            <div className="pt-4">
              <button
                onClick={handleCtaClick}
                className={`inline-flex items-center justify-center rounded-full px-8 py-3 text-sm font-medium transition-colors ${
                  heroImageUrl
                    ? 'bg-white text-zinc-900 hover:bg-neutral-100'
                    : 'bg-zinc-900 text-white hover:bg-zinc-800'
                }`}
              >
                {primaryCtaLabel}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * StarterCollectionRails - Collection-based product rails
 * Groups runtime products by collection_id using runtime.collections metadata
 * Rails only when there are real collections with attached products
 * Fails clearly when collections data is missing
 * Props: { maxCollections?: number, productsPerCollection?: number }
 */
export function StarterCollectionRails({
  maxCollections = 3,
  productsPerCollection = 4,
}: {
  maxCollections?: number;
  productsPerCollection?: number;
}) {
  const runtime = useCommerceRuntime();
  const navigate = useNavigate();

  const collections = runtime?.collections || [];
  const products = runtime?.products || [];

  // Fail clearly if no collections exist
  if (collections.length === 0) {
    throw new Error(
      "StarterCollectionRails: No collections available in runtime. " +
      "Ensure Medusa has collections with products assigned."
    );
  }

  // Group products by collection
  const collectionsWithProducts = collections
    .slice(0, maxCollections)
    .map((collection) => {
      const collectionProducts = products
        .filter((p) => p.collection_id === collection.id)
        .slice(0, productsPerCollection);
      return {
        collection,
        products: collectionProducts,
      };
    })
    .filter((cp) => cp.products.length > 0);

  // Fail clearly if collections exist but have no products
  if (collectionsWithProducts.length === 0) {
    throw new Error(
      `StarterCollectionRails: Collections exist but no products are assigned to them. ` +
      `Collections: ${collections.map((c) => c.title).join(", ")}. ` +
      `Ensure products have collection_id set in Medusa.`
    );
  }

  const handleProductClick = (product: MedusaProduct) => {
    if (product.handle) {
      runtime?.navigateToProduct(product.handle);
    }
  };

  const formatPrice = (product: MedusaProduct) => {
    const variant = product.variants?.[0];
    if (!variant) return null;

    // Try to get price from calculated_price (Medusa v2 format)
    const calculatedPrice = (variant as unknown as { calculated_price?: { calculated_amount: number } }).calculated_price;
    if (calculatedPrice?.calculated_amount) {
      return `$${(calculatedPrice.calculated_amount / 100).toFixed(2)}`;
    }

    // Fallback to prices array
    const price = variant.prices?.[0];
    if (price?.amount) {
      return `$${(price.amount / 100).toFixed(2)}`;
    }

    return null;
  };

  return (
    <div className="w-full bg-neutral-100">
      {collectionsWithProducts.map(({ collection, products: collectionProducts }, index) => (
        <div
          key={collection.id}
          className={`max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-12 small:py-16 ${
            index > 0 ? 'border-t border-neutral-200' : ''
          }`}
        >
          {/* Rail header */}
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-base font-normal text-zinc-900">{collection.title}</h2>
            <button
              onClick={() => {
                if (collection.handle && runtime) {
                  // Navigate to collection page if available
                  const categorySlug = runtime.categories?.find((c) => c.name === collection.title)?.handle;
                  if (categorySlug) {
                    runtime.navigateToCategory(categorySlug);
                  }
                }
              }}
              className="text-sm text-neutral-600 hover:text-zinc-900 transition-colors underline underline-offset-2"
            >
              View all
            </button>
          </div>

          {/* Products grid */}
          <div className="grid grid-cols-1 small:grid-cols-2 lg:grid-cols-4 gap-x-4 gap-y-8">
            {collectionProducts.map((product) => (
              <div
                key={product.id}
                className="group cursor-pointer"
                onClick={() => handleProductClick(product)}
              >
                {/* Product image */}
                <div className="aspect-[3/4] bg-white border border-neutral-200 overflow-hidden mb-3">
                  {product.thumbnail ? (
                    <img
                      src={product.thumbnail}
                      alt={product.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center bg-neutral-50 text-neutral-400 text-sm">
                      No image
                    </div>
                  )}
                </div>

                {/* Product info */}
                <div className="space-y-1">
                  <h3 className="text-sm font-medium text-zinc-900 group-hover:text-neutral-600 transition-colors">
                    {product.title}
                  </h3>
                  <p className="text-sm text-neutral-600">
                    {formatPrice(product) || 'Price unavailable'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * StarterStoreFooter - Medusa B2B starter-style footer
 * Props: { storeName?: string, showCategories?: boolean, showCollections?: boolean }
 */
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
  const categories = runtime?.categories || [];
  const collections = runtime?.collections || [];
  const mainCategories = categories.filter((c) => !c.parent_category_id);

  const handleHomeClick = () => {
    if (!funnelRuntime) return;
    const homeSlug = Object.entries(funnelRuntime.pageTypeMap || {}).find(
      ([, type]) => type === "home"
    )?.[0];
    if (homeSlug && funnelRuntime.pageMap[homeSlug]) {
      const path = buildPublicFunnelPath({
        productSlug: funnelRuntime.productSlug,
        funnelSlug: funnelRuntime.funnelSlug,
        slug: funnelRuntime.pageMap[homeSlug],
        bundleMode: funnelRuntime.bundleMode,
      });
      navigate(path);
    }
  };

  const handleCategoryClick = (category: MedusaCategory) => {
    if (category.handle) {
      runtime?.navigateToCategory(category.handle);
    }
  };

  const currentYear = new Date().getFullYear();

  return (
    <footer className="border-t border-neutral-200 w-full bg-white">
      <div className="flex flex-col w-full mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8">
        {/* Main footer content - B2B starter style: generous padding */}
        <div className="flex flex-col gap-y-6 sm:flex-row items-start justify-between py-20 sm:py-32">
          {/* Brand */}
          <div className="max-w-[200px]">
            <button
              onClick={handleHomeClick}
              className="text-lg font-semibold uppercase text-neutral-500 hover:text-zinc-900 transition-colors tracking-wider leading-snug text-left"
            >
              {storeName}
            </button>
          </div>

          {/* Link columns */}
          <div className="text-sm gap-10 md:gap-x-16 grid grid-cols-2 sm:grid-cols-3">
            {/* Categories */}
            {showCategories && mainCategories.length > 0 && (
              <div className="flex flex-col gap-y-3">
                <span className="text-sm font-semibold text-zinc-900 uppercase">Categories</span>
                <ul className="grid grid-cols-1 gap-2" data-testid="footer-categories">
                  {mainCategories.slice(0, 6).map((category) => {
                    const children = categories.filter((c) => c.parent_category_id === category.id);
                    return (
                      <li key={category.id} className="flex flex-col gap-2 text-neutral-500 text-sm">
                        <button
                          onClick={() => handleCategoryClick(category)}
                          className={`text-left hover:text-zinc-900 transition-colors ${children.length > 0 ? 'font-medium' : ''}`}
                          data-testid="category-link"
                        >
                          {category.name}
                        </button>
                        {children.length > 0 && (
                          <ul className="grid grid-cols-1 ml-3 gap-2">
                            {children.slice(0, 4).map((child) => (
                              <li key={child.id}>
                                <button
                                  onClick={() => handleCategoryClick(child)}
                                  className="text-left text-neutral-500 hover:text-zinc-900 transition-colors text-sm"
                                >
                                  {child.name}
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {/* Collections */}
            {showCollections && collections.length > 0 && (
              <div className="flex flex-col gap-y-3">
                <span className="text-sm font-semibold text-zinc-900 uppercase">Collections</span>
                <ul className="grid grid-cols-1 gap-2 text-neutral-500 text-sm">
                  {collections.slice(0, 6).map((collection) => (
                    <li key={collection.id}>
                      <span className="hover:text-zinc-900 cursor-pointer transition-colors">
                        {collection.title}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Company */}
            <div className="flex flex-col gap-y-3">
              <span className="text-sm font-semibold text-zinc-900 uppercase">{storeName}</span>
              <ul className="grid grid-cols-1 gap-y-2 text-neutral-500 text-sm">
                <li><span className="hover:text-zinc-900 cursor-pointer transition-colors">About</span></li>
                <li><span className="hover:text-zinc-900 cursor-pointer transition-colors">Contact</span></li>
                <li><span className="hover:text-zinc-900 cursor-pointer transition-colors">Terms of Service</span></li>
                <li><span className="hover:text-zinc-900 cursor-pointer transition-colors">Privacy Policy</span></li>
              </ul>
            </div>
          </div>
        </div>

        {/* Bottom row */}
        <div className="flex w-full mb-16 justify-between text-neutral-400 border-t border-neutral-200 pt-6">
          <span className="text-xs">
            © {currentYear} {storeName}. All rights reserved.
          </span>
          <span className="text-xs">
            Powered by Medusa
          </span>
        </div>
      </div>
    </footer>
  );
}
