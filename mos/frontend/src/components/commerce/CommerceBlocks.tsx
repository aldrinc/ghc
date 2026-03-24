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
    return <div className="p-4 text-sm text-content-muted">Commerce context not available</div>;
  }

  // Use currentCategory if set (from ?category= query param), otherwise fall back to first category or generic
  const displayTitle = title || runtime.currentCategory?.name || runtime.categories[0]?.name || "Products";
  const displayDescription = description || runtime.currentCategory?.description || runtime.categories[0]?.description || "";

  // Starter-style: centered with max-width like the starter
  return (
    <section className="py-12">
      <div className="mx-auto max-w-4xl px-6 text-center">
        <h1 className="text-3xl font-bold text-zinc-900">{displayTitle}</h1>
        {displayDescription && (
          <p className="mt-4 text-lg text-zinc-500">{displayDescription}</p>
        )}
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
    return <div className="p-4 text-sm text-zinc-500">Commerce context not available</div>;
  }

  const { products } = runtime;

  if (products.length === 0) {
    return <div className="p-4 text-sm text-zinc-500">No products available</div>;
  }

  const gridCols = columns === 2 ? "md:grid-cols-2" : columns === 4 ? "md:grid-cols-4" : "md:grid-cols-3";

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

  return (
    <div className={`grid gap-6 ${gridCols}`}>
      {products.map((product) => (
        <div
          key={product.id}
          className="group cursor-pointer"
          onClick={() => handleProductClick(product)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              handleProductClick(product);
            }
          }}
          tabIndex={0}
          role="button"
        >
          {/* Image */}
          <div className="relative mb-3 aspect-[4/3] overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50">
            {product.thumbnail ? (
              <img
                src={product.thumbnail}
                alt={product.title}
                className="h-full w-full object-cover transition-transform group-hover:scale-105"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                <span className="text-sm text-zinc-400">No image</span>
              </div>
            )}
          </div>

          {/* Info */}
          <div className="space-y-1">
            <h3 className="text-sm font-medium text-zinc-900 line-clamp-1">{product.title}</h3>
            {product.subtitle && (
              <p className="text-xs text-zinc-500 line-clamp-1">{product.subtitle}</p>
            )}
            <p className="text-sm font-semibold text-zinc-900">
              {formatPrice(product) || "Price not available"}
            </p>
          </div>
        </div>
      ))}
    </div>
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
    <div className="bg-zinc-50 min-h-screen">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8" data-testid="category-container">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-2 text-sm text-zinc-500 mb-6">
          <button
            onClick={handleHomeClick}
            className="hover:text-zinc-900 transition-colors"
          >
            Home
          </button>
          <span className="text-zinc-400">/</span>
          <span className="text-zinc-900 font-medium">{categoryName}</span>
        </nav>

        {/* Page header */}
        <div className="mb-8">
          {isCategoryPage ? (
            <>
              <h1 className="text-2xl font-semibold text-zinc-900">{currentCategory?.name}</h1>
              <p className="mt-1 text-sm text-zinc-500">
                {runtime?.products?.length || 0} product{(runtime?.products?.length || 0) !== 1 ? 's' : ''}
              </p>
            </>
          ) : runtime?.storeName ? (
            <>
              <h1 className="text-2xl font-semibold text-zinc-900">{runtime.storeName}</h1>
              <p className="mt-1 text-sm text-zinc-500">Browse our products</p>
            </>
          ) : null}
        </div>

        <div className="flex flex-col lg:flex-row gap-8">
          {/* Left rail */}
          <aside className="w-full lg:w-56 flex-shrink-0">
            <div className="space-y-6">
              {/* Categories */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-3">
                  Categories
                </h3>
                <ul className="space-y-1">
                  {parentCategories.slice(0, 8).map((cat) => {
                    const isSelected = currentCategory?.id === cat.id;
                    return (
                      <li key={cat.id}>
                        <button
                          onClick={() => runtime?.navigateToCategory(cat.handle)}
                          className={`w-full text-left px-2 py-1.5 text-sm rounded-md transition-colors ${
                            isSelected
                              ? 'bg-zinc-900 text-white font-medium'
                              : 'text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100'
                          }`}
                        >
                          {cat.name}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>

              {/* Collections */}
              {runtime?.collections && runtime.collections.length > 0 && (
                <div className="pt-6 border-t border-zinc-200">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-3">
                    Collections
                  </h3>
                  <ul className="space-y-2">
                    {runtime.collections.slice(0, 6).map((col) => (
                      <li key={col.id} className="text-sm text-zinc-600">
                        {col.title}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </aside>

          {/* Right: Product grid */}
          <div className="flex-1 bg-white rounded-lg border border-zinc-200 p-6">
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
        className="content-container grid grid-cols-1 md:grid-cols-2 gap-2 w-full h-fit"
        data-testid="product-container"
      >
        {/* Left: Visual/Gallery area - stronger visual weight */}
        <div className="bg-neutral-50 p-6 flex items-center justify-center small:p-10 rounded-lg min-h-[400px]">
          {currentProduct.thumbnail ? (
            <img
              src={currentProduct.thumbnail}
              alt={currentProduct.title}
              className="h-auto max-h-[500px] w-full object-contain rounded-md"
            />
          ) : (
            // Placeholder when no image - starter style
            <div className="h-80 w-full flex items-center justify-center bg-neutral-100 rounded-md">
              <span className="text-zinc-400 text-sm">No image available</span>
            </div>
          )}
        </div>
        
        {/* Right: Info/Actions panel on neutral surface - starter style */}
        <div className="flex flex-col bg-neutral-100 w-full gap-6 items-start justify-center small:p-20 p-6 h-full">
          {/* Product info */}
          <div className="w-full">
            <h1 className="text-3xl font-bold text-zinc-900">{currentProduct.title}</h1>
            {currentProduct.subtitle && (
              <p className="mt-1 text-lg text-zinc-500">{currentProduct.subtitle}</p>
            )}
            {currentProduct.description && (
              <p className="mt-4 text-base text-zinc-600">{currentProduct.description}</p>
            )}
          </div>

          {/* Variant selector */}
          {variants.length > 1 && (
            <div className="w-full">
              <label className="block text-sm font-medium text-zinc-700 mb-2">Select Variant</label>
              <select
                value={selectedVariantId || ""}
                onChange={(e) => setSelectedVariantId(e.target.value)}
                className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2.5 text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900"
              >
                {variants.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.title}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Price display */}
          {selectedVariant && selectedVariant.prices && selectedVariant.prices.length > 0 && selectedVariant.prices[0].amount != null && (
            <div className="text-2xl font-semibold text-zinc-900">
              {selectedVariant.prices[0].currency_code?.toUpperCase() || "USD"}{" "}
              {((selectedVariant.prices[0].amount || 0) / 100).toFixed(2)}
            </div>
          )}

          {/* Quantity selector */}
          <div className="flex items-center gap-4">
            <label className="block text-sm font-medium text-zinc-700">Quantity</label>
            <div className="flex items-center border border-zinc-300 rounded-md">
              <button
                onClick={() => setQuantity(Math.max(1, quantity - 1))}
                className="px-3 py-2 text-zinc-600 hover:bg-zinc-50"
              >
                -
              </button>
              <input
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                className="w-16 text-center border-none focus:outline-none focus:ring-0 bg-transparent"
              />
              <button
                onClick={() => setQuantity(quantity + 1)}
                className="px-3 py-2 text-zinc-600 hover:bg-zinc-50"
              >
                +
              </button>
            </div>
          </div>

          {/* Add to cart actions */}
          <div className="flex gap-4 w-full">
            <button
              onClick={handleAddToCart}
              disabled={adding || !selectedVariant}
              className="flex-1 rounded-full bg-zinc-900 px-8 py-3 font-semibold text-white disabled:opacity-50 hover:bg-zinc-800 transition-colors"
            >
              {adding ? "Adding..." : "Add to Cart"}
            </button>
            {added && (
              <button
                onClick={handleViewCart}
                className="rounded-full border border-zinc-300 bg-white px-6 py-3 font-semibold text-zinc-900 hover:bg-zinc-50 transition-colors"
              >
                View Cart
              </button>
            )}
          </div>

          {runtime.cartError && (
            <p className="mt-2 text-sm text-red-500">{runtime.cartError}</p>
          )}
        </div>
      </div>

      {/* Product facts/details section - starter style tabs-like structure */}
      <div className="content-container">
        <div className="border-t border-zinc-200 pt-8">
          <h2 className="text-xl font-semibold text-zinc-900 mb-4">Product Details</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Materials / Ingredients if available */}
            <div className="bg-white rounded-lg border border-zinc-200 p-4">
              <h3 className="text-sm font-semibold text-zinc-700 mb-2">Materials</h3>
              <p className="text-sm text-zinc-500">
                {currentProduct.metadata?.materials as string || "View product details for material information."}
              </p>
            </div>
            {/* Dimensions / specs */}
            <div className="bg-white rounded-lg border border-zinc-200 p-4">
              <h3 className="text-sm font-semibold text-zinc-700 mb-2">Specifications</h3>
              <p className="text-sm text-zinc-500">
                {currentProduct.metadata?.specifications as string || "View product details for specifications."}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Related products section - starter style */}
      {relatedProducts.length > 0 && (
        <div 
          className="content-container"
          data-testid="related-products-container"
        >
          <div className="border-t border-zinc-200 pt-8">
            <h2 className="text-xl font-semibold text-zinc-900 mb-6">Related Products</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {relatedProducts.map((product) => (
                <div
                  key={product.id}
                  className="rounded-lg border border-zinc-200 bg-white p-3 cursor-pointer hover:border-zinc-400 hover:shadow-sm transition-all"
                  onClick={() => handleProductClick(product)}
                >
                  {product.thumbnail && (
                    <img
                      src={product.thumbnail}
                      alt={product.title}
                      className="mb-3 h-32 w-full rounded-md object-cover"
                    />
                  )}
                  <h3 className="text-sm font-semibold text-zinc-900 line-clamp-1">{product.title}</h3>
                  {product.variants?.[0]?.prices?.[0] && product.variants[0].prices[0].amount != null && (
                    <p className="mt-1 text-sm font-medium text-zinc-700">
                      {product.variants[0].prices[0].currency_code?.toUpperCase() || "USD"}{" "}
                      {((product.variants[0].prices[0].amount || 0) / 100).toFixed(2)}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
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
    return <div className="p-4 text-sm text-content-muted">Commerce context not available</div>;
  }

  const { cart, cartLoading } = runtime;

  if (cartLoading && !cart) {
    return <div className="p-4 text-sm text-content-muted">Loading cart...</div>;
  }

  if (!cart || !cart.items || cart.items.length === 0) {
    return <div className="p-8 text-sm text-content-muted text-center">Your cart is empty</div>;
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

  // B2B starter style: item list and summary separation - stronger layout
  return (
    <div className="small:py-12 py-6 bg-neutral-100">
      <div className="content-container" data-testid="cart-container">
        <div className="flex flex-col py-6 gap-y-6">
          {/* Header with item count - starter style heading */}
          <div className="pb-3 flex items-center border-b border-zinc-200">
            <h2 className="text-neutral-950 text-2xl font-semibold">
              You have {totalItems} items in your cart
            </h2>
          </div>
          
          {/* Grid: Items on left, Summary on right - starter grid proportions */}
          <div className="grid grid-cols-1 small:grid-cols-[1fr_360px] gap-6">
            {/* Left: Items list - stronger item cards */}
            <div className="flex flex-col gap-y-4">
              {cart.items.map((item) => (
                <div 
                  key={item.id} 
                  className="flex items-center gap-6 rounded-lg border border-zinc-200 bg-white p-4 shadow-borders-base"
                >
                  {/* Thumbnail if available */}
                  {item.thumbnail && (
                    <img
                      src={item.thumbnail}
                      alt={item.title}
                      className="h-20 w-20 rounded-md object-cover flex-shrink-0"
                    />
                  )}
                  
                  {/* Item details */}
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-zinc-900">{item.title}</h3>
                    {item.variant && (
                      <p className="text-sm text-zinc-500">{item.variant.title}</p>
                    )}
                    {item.description && (
                      <p className="text-sm text-zinc-500 mt-1 line-clamp-2">{item.description}</p>
                    )}
                  </div>
                  
                  {/* Quantity controls */}
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleUpdateQuantity(item.id, item.quantity - 1)}
                      disabled={updating === item.id}
                      className="rounded-md border border-zinc-300 px-2 py-1 text-sm disabled:opacity-50 hover:bg-zinc-50"
                    >
                      -
                    </button>
                    <span className="w-10 text-center text-sm">{item.quantity}</span>
                    <button
                      onClick={() => handleUpdateQuantity(item.id, item.quantity + 1)}
                      disabled={updating === item.id}
                      className="rounded-md border border-zinc-300 px-2 py-1 text-sm disabled:opacity-50 hover:bg-zinc-50"
                    >
                      +
                    </button>
                  </div>
                  
                  {/* Line total */}
                  <div className="text-right w-24">
                    <div className="font-semibold text-zinc-900">
                      {formatCurrency(item.total || item.unit_price * item.quantity)}
                    </div>
                    {item.quantity > 1 && (
                      <div className="text-xs text-zinc-500">
                        {formatCurrency(item.unit_price)} each
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Right: Summary area - starter style cleaner totals */}
            <div className="relative">
              <div className="flex flex-col gap-y-8 sticky top-20">
                {/* Summary card - starter Container style */}
                <div className="bg-white rounded-lg border border-zinc-200 p-6">
                  <h3 className="text-lg font-semibold text-zinc-900 mb-4">Order Summary</h3>
                  
                  {/* Totals - cleaner spacing like starter */}
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Subtotal</span>
                      <span className="text-zinc-900">{formatCurrency(cart.subtotal)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Shipping</span>
                      <span className="text-zinc-900">Calculated at checkout</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Tax</span>
                      <span className="text-zinc-900">Calculated at checkout</span>
                    </div>
                    <div className="flex justify-between pt-3 border-t border-zinc-200 font-medium">
                      <span className="text-zinc-900">Total</span>
                      <span className="text-zinc-900">{formatCurrency(cart.total)}</span>
                    </div>
                  </div>

                  {/* Checkout CTA - starter style rounded-full button */}
                  <button
                    onClick={() => runtime.navigateToCheckout()}
                    className="mt-6 w-full h-10 rounded-full bg-zinc-900 px-6 py-3 font-semibold text-white hover:bg-zinc-800 shadow-borders-base transition-colors"
                  >
                    Proceed to Checkout
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
      <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
        <div className="max-w-md">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-16 h-16 mx-auto text-zinc-300 mb-4">
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 00-3 3h15.75m-12.75-3h11.218c1.121-2.3 2.1-4.684 2.924-7.138a60.114 60.114 0 00-16.536-1.84M7.5 14.25L5.106 5.272M6 20.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm12.75 0a.75.75 0 11-1.5 0 .75.75 0 011.5 0z" />
          </svg>
          <h2 className="text-xl font-semibold text-zinc-900 mb-2">No items in cart</h2>
          <p className="text-zinc-500 mb-6">You need to add items to your cart before proceeding to checkout.</p>
          <div className="flex gap-4 justify-center">
            <button
              onClick={() => runtime.navigateToCart()}
              className="rounded-full bg-zinc-900 px-6 py-3 font-semibold text-white hover:bg-zinc-800 transition-colors"
            >
              View Cart
            </button>
            <button
              onClick={handleContinueShopping}
              className="rounded-full border border-zinc-300 bg-white px-6 py-3 font-semibold text-zinc-900 hover:bg-zinc-50 transition-colors"
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

  // B2B starter style: two-column form + summary with stepper
  return (
    <div className="small:py-12 py-6 bg-neutral-100">
      <div className="mx-auto max-w-7xl px-4">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-8">
          {/* Left column: Checkout form */}
          <div className="w-full grid grid-cols-1 gap-y-4">
            {/* Back to cart link - starter style */}
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                runtime.navigateToCart();
              }}
              className="flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-500"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
              </svg>
              Back to shopping cart
            </a>

            {/* Step indicator - starter style stepper */}
            <div className="flex items-center gap-2 text-sm py-4">
              {steps.map((step, index) => (
                <Fragment key={step.key}>
                  <span 
                    className={index <= currentStepIndex 
                      ? "text-zinc-900 font-medium" 
                      : "text-zinc-400"}
                  >
                    {step.label}
                  </span>
                  {index < steps.length - 1 && (
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 text-zinc-300">
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
                <div className="bg-white rounded-lg border border-zinc-200 p-6">
                  <h2 className="text-lg font-semibold text-zinc-900 mb-4">Contact Information</h2>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Email address"
                    required
                    className="block w-full rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900"
                  />
                </div>

                {/* Shipping Address section */}
                <div className="bg-white rounded-lg border border-zinc-200 p-6">
                  <h2 className="text-lg font-semibold text-zinc-900 mb-4">Shipping Address</h2>
                  <div className="grid gap-4">
                    <div className="grid grid-cols-2 gap-4">
                      <input
                        type="text"
                        value={shippingAddress.first_name}
                        onChange={(e) => setShippingAddress({ ...shippingAddress, first_name: e.target.value })}
                        placeholder="First name"
                        required
                        className="rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900"
                      />
                      <input
                        type="text"
                        value={shippingAddress.last_name}
                        onChange={(e) => setShippingAddress({ ...shippingAddress, last_name: e.target.value })}
                        placeholder="Last name"
                        required
                        className="rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900"
                      />
                    </div>
                    <input
                      type="text"
                      value={shippingAddress.address_1}
                      onChange={(e) => setShippingAddress({ ...shippingAddress, address_1: e.target.value })}
                      placeholder="Address"
                      required
                      className="block w-full rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900"
                    />
                    <div className="grid grid-cols-2 gap-4">
                      <input
                        type="text"
                        value={shippingAddress.city}
                        onChange={(e) => setShippingAddress({ ...shippingAddress, city: e.target.value })}
                        placeholder="City"
                        required
                        className="rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900"
                      />
                      <input
                        type="text"
                        value={shippingAddress.postal_code}
                        onChange={(e) => setShippingAddress({ ...shippingAddress, postal_code: e.target.value })}
                        placeholder="Postal code"
                        required
                        className="rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-zinc-900"
                      />
                    </div>
                    <select
                      value={shippingAddress.country_code}
                      onChange={(e) => setShippingAddress({ ...shippingAddress, country_code: e.target.value })}
                      required
                      className="block w-full rounded-md border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900"
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
                  <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <button
                  type="button"
                  onClick={handleSaveAddress}
                  disabled={loading}
                  className="w-full h-10 rounded-full bg-zinc-900 px-6 py-3 font-medium text-white hover:bg-zinc-800 disabled:opacity-50 transition-colors"
                >
                  {loading ? "Saving..." : "Continue to Shipping"}
                </button>
              </div>
            )}

            {/* Step 2: Shipping Method */}
            {currentStep === "shipping" && (
              <div className="w-full grid grid-cols-1 gap-y-4">
                <div className="bg-white rounded-lg border border-zinc-200 p-6">
                  <h2 className="text-lg font-semibold text-zinc-900 mb-4">Shipping Method</h2>
                  {shippingOptions.length === 0 ? (
                    <p className="text-zinc-500">No shipping options available for your address.</p>
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
                              ? "border-zinc-900 bg-zinc-50"
                              : "border-zinc-200 bg-white hover:border-zinc-400"
                          }`}
                        >
                          <div>
                            <p className="font-medium text-zinc-900">{option.name}</p>
                            {option.description && (
                              <p className="text-sm text-zinc-500">{option.description}</p>
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
                  <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <button
                  type="button"
                  onClick={() => setCurrentStep("address")}
                  className="text-sm text-zinc-500 hover:text-zinc-900 flex items-center gap-1"
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
                <div className="bg-white rounded-lg border border-zinc-200 p-6">
                  <h2 className="text-lg font-semibold text-zinc-900 mb-4">Payment Method</h2>
                  {paymentProviders.length === 0 ? (
                    <p className="text-zinc-500">No payment methods available.</p>
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
                              ? "border-zinc-900 bg-zinc-50"
                              : "border-zinc-200 bg-white hover:border-zinc-400"
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
                  <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <button
                  type="button"
                  onClick={() => setCurrentStep("shipping")}
                  className="text-sm text-zinc-500 hover:text-zinc-900 flex items-center gap-1"
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
                <div className="bg-white rounded-lg border border-zinc-200 p-6">
                  <h2 className="text-lg font-semibold text-zinc-900 mb-4">Review Order</h2>
                  
                  {/* Contact summary */}
                  <div className="mb-4 pb-4 border-b border-zinc-200">
                    <p className="text-sm text-zinc-500">Contact</p>
                    <p className="text-zinc-900">{email}</p>
                  </div>

                  {/* Address summary */}
                  <div className="mb-4 pb-4 border-b border-zinc-200">
                    <p className="text-sm text-zinc-500">Ship to</p>
                    <p className="text-zinc-900">
                      {shippingAddress.first_name} {shippingAddress.last_name}<br />
                      {shippingAddress.address_1}<br />
                      {shippingAddress.city}, {shippingAddress.postal_code}<br />
                      {availableCountries.find(c => c.iso_2 === shippingAddress.country_code)?.display_name || shippingAddress.country_code}
                    </p>
                  </div>

                  {/* Shipping summary */}
                  <div className="mb-4 pb-4 border-b border-zinc-200">
                    <p className="text-sm text-zinc-500">Shipping</p>
                    <p className="text-zinc-900">
                      {shippingOptions.find(o => o.id === selectedShippingOption)?.name || "Selected shipping"}
                    </p>
                  </div>

                  {/* Payment summary */}
                  <div>
                    <p className="text-sm text-zinc-500">Payment</p>
                    <p className="text-zinc-900">
                      {selectedPaymentProvider === "pp_system_default" ? "Pay on Delivery" : 
                       selectedPaymentProvider === "manual" ? "Manual Payment" :
                       selectedPaymentProvider?.replace("pp_", "").replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase()) || "Selected payment"}
                    </p>
                  </div>
                </div>

                {error && (
                  <div className="rounded-md bg-red-50 border border-red-200 p-4 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <button
                  type="button"
                  onClick={handleCompleteCheckout}
                  disabled={loading}
                  className="w-full h-10 rounded-full bg-zinc-900 px-6 py-3 font-medium text-white hover:bg-zinc-800 disabled:opacity-50 transition-colors"
                >
                  {loading ? "Processing..." : "Complete Order"}
                </button>

                <button
                  type="button"
                  onClick={() => setCurrentStep("payment")}
                  className="text-sm text-zinc-500 hover:text-zinc-900 flex items-center gap-1"
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
            <div className="bg-white rounded-lg border border-zinc-200 p-6">
              <h2 className="text-lg font-semibold text-zinc-900 mb-4">Order Summary</h2>
              
              {/* Line items */}
              <div className="space-y-3 mb-4 pb-4 border-b border-zinc-200">
                {cart.items?.map((item) => (
                  <div key={item.id} className="flex items-start justify-between text-sm">
                    <div className="flex-1">
                      <p className="text-zinc-900 font-medium">{item.title}</p>
                      <p className="text-zinc-500">Qty: {item.quantity}</p>
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
                  <span className="text-zinc-500">Subtotal</span>
                  <span className="text-zinc-900">{formatCurrency(subtotal, currencyCode)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Shipping</span>
                  <span className="text-zinc-900">
                    {shippingTotal > 0 ? formatCurrency(shippingTotal, currencyCode) : "Calculated at checkout"}
                  </span>
                </div>
                <div className="flex justify-between pt-2 border-t border-zinc-200 font-medium">
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
    <div className="space-y-2">
      <h3 className="text-lg font-semibold text-content">Categories</h3>
      <ul className="space-y-1">
        {categories.map((category) => (
          <li key={category.id}>
            <button
              onClick={() => handleCategoryClick(category)}
              className="text-content-muted hover:text-content cursor-pointer bg-transparent border-none p-0 text-left"
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
    <header className="sticky top-0 z-50 w-full border-b border-zinc-200 bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between">
          {/* Left: Brand + Nav */}
          <div className="flex items-center gap-8">
            <button
              onClick={handleHomeClick}
              className="text-base font-semibold text-zinc-900 hover:text-zinc-700 transition-colors"
            >
              {storeName}
            </button>

            {mainCategories.length > 0 && (
              <nav className="hidden md:flex items-center gap-6">
                {mainCategories.slice(0, 5).map((category) => (
                  <button
                    key={category.id}
                    onClick={() => handleCategoryClick(category)}
                    className="text-sm text-zinc-600 hover:text-zinc-900 transition-colors"
                  >
                    {category.name}
                  </button>
                ))}
              </nav>
            )}
          </div>

          {/* Right: Search + Cart */}
          <div className="flex items-center gap-4">
            {showSearch && (
              <div className="hidden md:block">
                <input
                  type="text"
                  placeholder="Search products..."
                  disabled
                  className="w-48 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-sm text-zinc-900 placeholder:text-zinc-400 hover:cursor-not-allowed"
                  title="Search coming soon"
                />
              </div>
            )}

            {showCart && (
              <button
                onClick={handleCartClick}
                className="flex items-center gap-2 rounded-md border border-zinc-200 px-3 py-1.5 text-sm hover:bg-zinc-50 transition-colors"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  className="h-4 w-4 text-zinc-600"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.537M6.75 7.5h10.5m-10.5 0l-1.5 6.75a1.5 1.5 0 001.5 1.5h9a1.5 1.5 0 001.5-1.5l-1.5-6.75m-9 0h9"
                  />
                </svg>
                <span className="text-zinc-900 font-medium">
                  {itemCount > 0 ? `${itemCount}` : "0"}
                </span>
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

/**
 * CommerceStoreFooter - Store footer with categories, collections, and links
 * B2B starter parity: cleaner columns, tighter spacing, calmer bottom row.
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
    <footer className="border-t border-zinc-200 bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Main footer content */}
        <div className="grid grid-cols-2 gap-8 py-10 sm:grid-cols-4">
          {/* Brand */}
          <div className="col-span-2 sm:col-span-1">
            <button
              onClick={handleHomeClick}
              className="text-sm font-semibold text-zinc-900 hover:text-zinc-700 transition-colors"
            >
              {storeName}
            </button>
          </div>

          {/* Categories */}
          {showCategories && mainCategories.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-3">
                Categories
              </h3>
              <ul className="space-y-2" data-testid="footer-categories">
                {mainCategories.slice(0, 5).map((category) => (
                  <li key={category.id}>
                    <button
                      onClick={() => handleCategoryClick(category)}
                      className="text-sm text-zinc-600 hover:text-zinc-900 transition-colors"
                      data-testid="category-link"
                    >
                      {category.name}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Collections */}
          {showCollections && collections.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-3">
                Collections
              </h3>
              <ul className="space-y-2">
                {collections.slice(0, 5).map((collection) => (
                  <li key={collection.id} className="text-sm text-zinc-600">
                    {collection.title}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Company */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-3">
              Company
            </h3>
            <ul className="space-y-2">
              <li className="text-sm text-zinc-600">About</li>
              <li className="text-sm text-zinc-600">Contact</li>
              <li className="text-sm text-zinc-600">Terms</li>
              <li className="text-sm text-zinc-600">Privacy</li>
            </ul>
          </div>
        </div>

        {/* Bottom row */}
        <div className="border-t border-zinc-200 py-6">
          <p className="text-xs text-zinc-500">
            © {currentYear} {storeName}. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
