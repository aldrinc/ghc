/**
 * Medusa B2C Storefront Runtime Provider
 * 
 * This provider manages direct Medusa Store API interactions for the B2C storefront.
 * It replaces the MOS commerce proxy with direct SDK calls.
 * 
 * Features:
 * - Direct Medusa SDK integration
 * - Browser-managed session persistence
 * - Cart state management
 * - Customer authentication
 * - Country/locale normalization
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "@/api/client";
import { DesignSystemProvider } from "@/components/design-system/DesignSystemProvider";
import { buildImportedDesignSystemTokens } from "@/components/imported-site/importedDesignSystem";
import type {
  MedusaProduct,
  MedusaCart,
  MedusaRegion,
  MedusaCollection,
  MedusaCategory,
  MedusaShippingOption,
  MedusaPaymentProvider,
  MedusaPaymentCollection,
  MedusaCustomer,
  MedusaOrder,
} from "@/types/commerce";
import {
  getMedusaRuntimeConfig,
  isMedusaRuntimeConfigured,
  getCartId,
  setCartId,
  getAuthToken,
  setAuthToken,
  getCountryCode,
  setCountryCode,
  getLocale,
  setLocale,
  listRegions,
  listProducts,
  listCollections,
  listCategories,
  getProductByHandle,
  getCollectionByHandle,
  getCategoryByHandle,
  createCart as createMedusaCart,
  getOrCreateCart,
  getCart,
  updateCart,
  addCartLineItem,
  updateCartLineItem,
  deleteCartLineItem,
  applyPromotionCode as applyMedusaPromotionCode,
  removePromotionCode as removeMedusaPromotionCode,
  listShippingOptions,
  addShippingMethod,
  listPaymentProviders,
  initializePaymentSession,
  completeCart,
  registerCustomer,
  loginCustomer,
  logoutCustomer,
  getCurrentCustomer,
  updateCustomer,
  requestCustomerPasswordReset,
  createCustomerAddress,
  updateCustomerAddress,
  deleteCustomerAddress,
  listOrders,
  getOrder,
  requestOrderTransfer,
  acceptOrderTransfer,
  declineOrderTransfer,
  MedusaApiError,
  type ProductListOptions,
  type ProductListResult,
  type UpdateCustomerInput,
  type CreateAddressInput,
  type UpdateAddressInput,
} from "@/lib/medusa";
import { resolveRuntimeSitePath, useFunnelRuntime } from "@/funnels/funnelRuntime";
import {
  useImportedOneProductShellState,
  type ImportedOneProductShellState,
} from "./importedOneProductShellData";
import type { DesignSystemTokens } from "@/types/designSystems";

// =============================================================================
// Types
// =============================================================================

export type B2CPageType =
  | "home"
  | "store"
  | "collection"
  | "category"
  | "product_detail"
  | "cart"
  | "checkout"
  | "account_dashboard"
  | "account_profile"
  | "account_addresses"
  | "account_orders"
  | "account_order_detail"
  | "order_confirmed"
  | "order_transfer"
  | "order_transfer_accept"
  | "order_transfer_decline";

// =============================================================================
// Checkout Types
// =============================================================================

/**
 * Supported checkout mutation steps.
 * Each step maps to a specific cart update operation.
 */
export type CheckoutStep =
  | "update_email"
  | "update_shipping_address"
  | "update_billing_address"
  | "set_shipping_method"
  | "init_payment_session";

/**
 * Data payload for each checkout step.
 */
export type CheckoutStepData =
  | { step: "update_email"; email: string }
  | { step: "update_shipping_address"; address: Record<string, unknown> }
  | { step: "update_billing_address"; address: Record<string, unknown> }
  | { step: "set_shipping_method"; optionId: string }
  | { step: "init_payment_session"; providerId: string };

/**
 * Country/region checkout contract.
 * Documents the explicit constraints on country-driven cart behavior.
 */
export type CountryCheckoutContract = {
  /**
   * Country is seeded at cart creation and cannot be safely changed mid-checkout.
   * Attempting to do so would invalidate region-dependent state (shipping options,
   * payment providers, tax calculations). If you need a different country, create
   * a new cart or inform the user to start fresh.
   */
  countryMidCheckoutBehavior: "error";
  /**
   * Supported: passing country at cart creation via regionId or countryCode.
   * Not supported: live country replacement during an active checkout session.
   */
  countryChangeSupported: false;
  /**
   * Cart region is determined at creation time from the default region or explicit regionId.
   * Region determines: currency, available shipping options, payment providers, tax rules.
   */
  regionDeterminedAt: "cart_creation";
};

export type B2CRuntimeContextValue = {
  // Configuration
  isConfigured: boolean;
  configError: string | null;

  // Site metadata
  siteId: string | null;
  siteClientId: string | null;
  siteFamily: string;
  siteName: string | null;
  countryCode: string;
  locale: string | null;

  // Catalog data
  regions: MedusaRegion[];
  products: MedusaProduct[];
  collections: MedusaCollection[];
  categories: MedusaCategory[];
  productsLoading: boolean;
  productsError: string | null;
  productsCount: number;

  // Current selections
  currentProduct: MedusaProduct | null;
  currentCategory: MedusaCategory | null;
  currentCollection: MedusaCollection | null;

  // Cart state
  cart: MedusaCart | null;
  cartLoading: boolean;
  cartError: string | null;

  // Customer state
  customer: MedusaCustomer | null;
  customerLoading: boolean;
  customerError: string | null;
  isAuthenticated: boolean;

  // Actions: Country/Locale
  setCountry: (code: string) => void;
  setLocalePreference: (locale: string | null) => void;

  // Actions: Catalog
  refreshProducts: (options?: ProductListOptions) => Promise<ProductListResult | null>;
  refreshCollections: () => Promise<void>;
  refreshCategories: () => Promise<void>;
  loadProductByHandle: (handle: string) => Promise<MedusaProduct | null>;
  loadCollectionByHandle: (handle: string) => Promise<MedusaCollection | null>;
  loadCategoryByHandle: (handle: string) => Promise<MedusaCategory | null>;

  // Actions: Cart
  createCart: (regionId?: string) => Promise<MedusaCart>;
  refreshCart: () => Promise<void>;
  addToCart: (variantId: string, quantity: number) => Promise<void>;
  replaceCartWithVariant: (variantId: string, quantity: number) => Promise<MedusaCart>;
  updateCartItem: (lineId: string, quantity: number) => Promise<void>;
  removeCartItem: (lineId: string) => Promise<void>;
  applyPromotionCode: (code: string) => Promise<void>;
  removePromotionCode: (code: string) => Promise<void>;
  updateCartEmail: (email: string) => Promise<void>;
  updateCartShippingAddress: (address: Record<string, unknown>) => Promise<void>;
  updateCartBillingAddress: (address: Record<string, unknown>) => Promise<void>;

  // Actions: Checkout (consolidated mutations)
  // Note: init_payment_session returns MedusaPaymentCollection; all other steps return MedusaCart
  performCheckoutAction: (step: CheckoutStep, data: CheckoutStepData) => Promise<MedusaCart | MedusaPaymentCollection>;

  // Actions: Shipping
  getShippingOptions: () => Promise<MedusaShippingOption[]>;
  selectShippingMethod: (optionId: string) => Promise<void>;

  // Actions: Payment
  getPaymentProviders: () => Promise<MedusaPaymentProvider[]>;
  initPaymentSession: (providerId: string) => Promise<MedusaPaymentCollection>;
  completeCheckout: () => Promise<{ type: "order" | "cart"; order?: MedusaOrder; cart?: MedusaCart }>;

  // Actions: Customer
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, firstName?: string, lastName?: string, phone?: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshCustomer: () => Promise<void>;
  updateCustomer: (input: UpdateCustomerInput) => Promise<void>;
  requestPasswordReset: (email?: string) => Promise<void>;

  // Actions: Addresses
  addCustomerAddress: (input: CreateAddressInput) => Promise<void>;
  updateCustomerAddress: (addressId: string, input: UpdateAddressInput) => Promise<void>;
  deleteCustomerAddress: (addressId: string) => Promise<void>;

  // Actions: Orders
  listOrders: (limit?: number, offset?: number) => Promise<{ orders: MedusaOrder[]; count: number }>;
  getOrder: (orderId: string) => Promise<MedusaOrder | null>;
  requestOrderTransfer: (orderId: string) => Promise<MedusaOrder>;
  acceptOrderTransfer: (orderId: string, token: string) => Promise<MedusaOrder>;
  declineOrderTransfer: (orderId: string, token: string) => Promise<MedusaOrder>;

  // Navigation helpers
  navigateToHome: () => void;
  navigateToStore: () => void;
  navigateToCollection: (handle: string) => void;
  navigateToCategory: (handle: string) => void;
  navigateToProduct: (handle: string) => void;
  navigateToCart: () => void;
  navigateToCheckout: () => void;
  navigateToAccount: () => void;
  navigateToAccountProfile: () => void;
  navigateToAccountAddresses: () => void;
  navigateToAccountOrders: () => void;
  navigateToOrder: (orderId: string) => void;
  navigateToOrderConfirmed: (orderId: string) => void;

  // Page type resolution
  resolvePageSlug: (pageType: B2CPageType) => string | null;
};

// =============================================================================
// Context
// =============================================================================

const B2CRuntimeContext = createContext<B2CRuntimeContextValue | null>(null);
const ImportedOneProductShellContext = createContext<ImportedOneProductShellState>({ status: "unavailable" });

export function useB2CRuntime(): B2CRuntimeContextValue {
  const context = useContext(B2CRuntimeContext);
  if (!context) {
    throw new Error("useB2CRuntime must be used within a B2CRuntimeProvider");
  }
  return context;
}

export function useMaybeB2CRuntime(): B2CRuntimeContextValue | null {
  return useContext(B2CRuntimeContext);
}

export function useImportedOneProductShellData(): ImportedOneProductShellState {
  return useContext(ImportedOneProductShellContext);
}

// =============================================================================
// Provider
// =============================================================================

export type B2CRuntimeProviderProps = {
  children: ReactNode;
  siteFamily: string;
  siteName?: string | null;
  siteId?: string | null;
  siteClientId?: string | null;
  initialCountryCode?: string;
  initialLocale?: string | null;
  designSystemTokens?: DesignSystemTokens | Record<string, unknown> | null;
};

export function B2CRuntimeProvider({
  children,
  siteFamily,
  siteName = null,
  siteId = null,
  siteClientId = null,
  initialCountryCode,
  initialLocale,
  designSystemTokens = null,
}: B2CRuntimeProviderProps): ReactNode {
  const funnelRuntime = useFunnelRuntime();
  const navigate = useNavigate();
  const { request: apiRequest, get: apiGet, post: apiPost } = useApiClient();

  // Configuration state
  const runtimeConfig = getMedusaRuntimeConfig();
  const isConfigured = Boolean(runtimeConfig) && isMedusaRuntimeConfigured();
  const [configError, setConfigError] = useState<string | null>(null);

  // Country/locale state
  const [countryCode, setCountryCodeState] = useState(() => 
    initialCountryCode || getCountryCode()
  );
  const [locale, setLocaleState] = useState<string | null>(() => 
    initialLocale || getLocale()
  );

  // Catalog state
  const [regions, setRegions] = useState<MedusaRegion[]>([]);
  const [products, setProducts] = useState<MedusaProduct[]>([]);
  const [collections, setCollections] = useState<MedusaCollection[]>([]);
  const [categories, setCategories] = useState<MedusaCategory[]>([]);
  const [productsLoading, setProductsLoading] = useState(false);
  const [productsError, setProductsError] = useState<string | null>(null);
  const [productsCount, setProductsCount] = useState(0);

  // Current selections
  const [currentProduct, setCurrentProduct] = useState<MedusaProduct | null>(null);
  const [currentCategory, setCurrentCategory] = useState<MedusaCategory | null>(null);
  const [currentCollection, setCurrentCollection] = useState<MedusaCollection | null>(null);

  // Cart state
  const [cart, setCart] = useState<MedusaCart | null>(null);
  const [cartLoading, setCartLoading] = useState(false);
  const [cartError, setCartError] = useState<string | null>(null);

  // Customer state
  const [customer, setCustomer] = useState<MedusaCustomer | null>(null);
  const [customerLoading, setCustomerLoading] = useState(false);
  const [customerError, setCustomerError] = useState<string | null>(null);
  const isAuthenticated = useMemo(() => !!customer, [customer]);

  const importedShell = useImportedOneProductShellState({
    apiGet,
    siteId,
    siteClientId,
    productSlug: funnelRuntime?.productSlug ?? null,
    funnelSlug: funnelRuntime?.funnelSlug ?? null,
  });

  const importedShellBrandName = useMemo(() => {
    if (importedShell.status !== "ready") {
      return null;
    }
    const textSlots = Array.isArray(importedShell.shell.header.sectionProps.textSlots)
      ? (importedShell.shell.header.sectionProps.textSlots as Array<Record<string, unknown>>)
      : [];
    const logoTextSlot = textSlots.find((slot) => String(slot.label || "").trim() === "Logo text");
    const brandName = typeof logoTextSlot?.text === "string" ? logoTextSlot.text.trim() : "";
    return brandName || importedShell.shell.pageName || null;
  }, [importedShell]);

  const importedShellDesignSystemTokens = useMemo(() => {
    if (designSystemTokens || importedShell.status !== "ready") {
      return null;
    }
    return buildImportedDesignSystemTokens({
      theme: importedShell.shell.theme,
      themeJson: importedShell.shell.themeJson,
      headAssets: importedShell.shell.sharedHeadAssets,
      brandName: importedShellBrandName,
    });
  }, [designSystemTokens, importedShell, importedShellBrandName]);

  const siteCartProxyBasePath = useMemo(() => {
    if (siteId) {
      return `/sites/${encodeURIComponent(siteId)}/medusa`;
    }
    const productSlug = funnelRuntime?.productSlug?.trim();
    const funnelSlug = funnelRuntime?.funnelSlug?.trim();
    if (!productSlug || !funnelSlug) {
      return null;
    }
    return `/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/site`;
  }, [funnelRuntime?.funnelSlug, funnelRuntime?.productSlug, siteId]);

  const buildSiteCartProxyPath = useCallback(
    (path: string, params?: Record<string, string | null | undefined>) => {
      if (!siteCartProxyBasePath) {
        return null;
      }
      const searchParams = new URLSearchParams();
      Object.entries(params || {}).forEach(([key, value]) => {
        if (typeof value === "string" && value.length > 0) {
          searchParams.set(key, value);
        }
      });
      const query = searchParams.toString();
      return `${siteCartProxyBasePath}${path}${query ? `?${query}` : ""}`;
    },
    [siteCartProxyBasePath],
  );

  const resolveSiteCartRegionId = useCallback(
    async (explicitRegionId?: string): Promise<string> => {
      const trimmedRegionId = explicitRegionId?.trim();
      if (trimmedRegionId) {
        return trimmedRegionId;
      }

      const configuredRegionId = runtimeConfig?.defaultRegionId?.trim();
      if (configuredRegionId) {
        return configuredRegionId;
      }

      const normalizedCountryCode = countryCode.trim().toLowerCase();
      const availableRegions = regions.length > 0 ? regions : await listRegions();
      const matchingRegion = availableRegions.find((region) =>
        region.countries?.some((country) => country.iso_2.toLowerCase() === normalizedCountryCode)
      );

      if (!matchingRegion) {
        throw new MedusaApiError(`No Medusa region is configured for country code '${normalizedCountryCode}'.`);
      }

      return matchingRegion.id;
    },
    [countryCode, regions, runtimeConfig],
  );

  const getSiteCart = useCallback(
    async (cartId: string): Promise<MedusaCart> => {
      const path = buildSiteCartProxyPath("/cart", { cart_id: cartId });
      if (!path) {
        throw new Error("Site cart proxy is unavailable for this storefront runtime.");
      }
      const response = await apiGet<{ cart: MedusaCart }>(path);
      if (!response.cart?.id) {
        throw new Error("Site cart proxy returned an invalid cart payload.");
      }
      return response.cart;
    },
    [apiGet, buildSiteCartProxyPath],
  );

  const createSiteCart = useCallback(
    async (options?: {
      regionId?: string;
      email?: string;
      shippingAddress?: Record<string, unknown>;
      items?: Array<{ variant_id: string; quantity: number }>;
    }): Promise<MedusaCart> => {
      const path = buildSiteCartProxyPath("/cart");
      if (!path) {
        throw new Error("Site cart proxy is unavailable for this storefront runtime.");
      }
      const regionId = await resolveSiteCartRegionId(options?.regionId);
      const response = await apiPost<{ cart: MedusaCart }>(path, {
        region_id: regionId,
        email: options?.email,
        shipping_address: options?.shippingAddress,
        items: options?.items,
      });
      if (!response.cart?.id) {
        throw new Error("Site cart proxy returned an invalid cart payload.");
      }
      setCartId(response.cart.id);
      return response.cart;
    },
    [apiPost, buildSiteCartProxyPath, resolveSiteCartRegionId],
  );

  const getOrCreateSiteCart = useCallback(async (): Promise<MedusaCart> => {
    const cartId = getCartId();
    if (cartId) {
      try {
        const existingCart = await getSiteCart(cartId);
        if (existingCart?.completed_at) {
          setCartId(null);
        } else {
          return existingCart;
        }
      } catch {
        setCartId(null);
      }
    }
    return createSiteCart();
  }, [createSiteCart, getSiteCart]);

  const updateSiteCart = useCallback(
    async (
      cartId: string,
      updates: {
        email?: string;
        shippingAddress?: Record<string, unknown>;
        billingAddress?: Record<string, unknown>;
      },
    ): Promise<MedusaCart> => {
      const path = buildSiteCartProxyPath(`/cart/${encodeURIComponent(cartId)}`);
      if (!path) {
        throw new Error("Site cart proxy is unavailable for this storefront runtime.");
      }
      const response = await apiPost<{ cart: MedusaCart }>(path, {
        email: updates.email,
        shipping_address: updates.shippingAddress,
        billing_address: updates.billingAddress,
      });
      if (!response.cart?.id) {
        throw new Error("Site cart proxy returned an invalid cart payload.");
      }
      return response.cart;
    },
    [apiPost, buildSiteCartProxyPath],
  );

  const addSiteCartLineItem = useCallback(
    async (cartId: string, variantId: string, quantity: number): Promise<MedusaCart> => {
      const path = buildSiteCartProxyPath(`/cart/${encodeURIComponent(cartId)}/items`);
      if (!path) {
        throw new Error("Site cart proxy is unavailable for this storefront runtime.");
      }
      const response = await apiPost<{ cart: MedusaCart }>(path, {
        variant_id: variantId,
        quantity,
      });
      if (!response.cart?.id) {
        throw new Error("Site cart proxy returned an invalid cart payload.");
      }
      return response.cart;
    },
    [apiPost, buildSiteCartProxyPath],
  );

  const updateSiteCartLineItem = useCallback(
    async (cartId: string, lineId: string, quantity: number): Promise<MedusaCart> => {
      const path = buildSiteCartProxyPath(
        `/cart/${encodeURIComponent(cartId)}/items/${encodeURIComponent(lineId)}`,
      );
      if (!path) {
        throw new Error("Site cart proxy is unavailable for this storefront runtime.");
      }
      const response = await apiPost<{ cart: MedusaCart }>(path, {
        quantity,
      });
      if (!response.cart?.id) {
        throw new Error("Site cart proxy returned an invalid cart payload.");
      }
      return response.cart;
    },
    [apiPost, buildSiteCartProxyPath],
  );

  const deleteSiteCartLineItem = useCallback(
    async (cartId: string, lineId: string): Promise<MedusaCart> => {
      const path = buildSiteCartProxyPath(
        `/cart/${encodeURIComponent(cartId)}/items/${encodeURIComponent(lineId)}`,
      );
      if (!path) {
        throw new Error("Site cart proxy is unavailable for this storefront runtime.");
      }
      await apiRequest<{ deleted: boolean }>(path, { method: "DELETE" });
      return getSiteCart(cartId);
    },
    [apiRequest, buildSiteCartProxyPath, getSiteCart],
  );

  // =============================================================================
  // Initialization
  // =============================================================================

  useEffect(() => {
    if (!isConfigured) {
      setConfigError(
        "Medusa runtime is not configured. " +
        "Please set VITE_MEDUSA_BACKEND_URL and VITE_MEDUSA_PUBLISHABLE_KEY."
      );
      return;
    }

    // Load initial catalog data
    const init = async () => {
      try {
        const [regionsData, collectionsData, categoriesData] = await Promise.all([
          listRegions(),
          listCollections(),
          listCategories(),
        ]);
        setRegions(regionsData);
        setCollections(collectionsData);
        setCategories(categoriesData);
      } catch (err) {
        setConfigError(err instanceof Error ? err.message : "Failed to initialize Medusa runtime");
      }
    };

    init();
  }, [isConfigured]);

  useEffect(() => {
    if (!initialCountryCode) return;
    setCountryCodeState(initialCountryCode);
    setCountryCode(initialCountryCode);
  }, [initialCountryCode]);

  // Load cart on mount
  useEffect(() => {
    if (!isConfigured) return;

    const loadCart = async () => {
      setCartLoading(true);
      try {
        const cartData = siteCartProxyBasePath ? await getOrCreateSiteCart() : await getOrCreateCart();
        setCart(cartData);
      } catch (err) {
        setCartError(err instanceof Error ? err.message : "Failed to load cart");
      } finally {
        setCartLoading(false);
      }
    };

    loadCart();
  }, [getOrCreateSiteCart, isConfigured, siteCartProxyBasePath]);

  // Load customer if auth token exists
  useEffect(() => {
    if (!isConfigured) return;
    if (!getAuthToken()) return;

    const loadCustomer = async () => {
      setCustomerLoading(true);
      setCustomerError(null);
      try {
        const customerData = await getCurrentCustomer();
        setCustomer(customerData);
      } catch (err) {
        if (err instanceof MedusaApiError && err.statusCode === 401) {
          setAuthToken(null);
          setCustomer(null);
          setCustomerError(null);
        } else {
          setCustomerError(err instanceof Error ? err.message : "Failed to load customer account.");
        }
      } finally {
        setCustomerLoading(false);
      }
    };

    loadCustomer();
  }, [isConfigured]);

  // =============================================================================
  // Actions: Country/Locale
  // =============================================================================

  const setCountry = useCallback((code: string) => {
    const normalizedCode = code.toLowerCase();
    setCountryCode(normalizedCode);
    setCountryCodeState(normalizedCode);
  }, []);

  const setLocalePreference = useCallback((localeValue: string | null) => {
    setLocale(localeValue);
    setLocaleState(localeValue);
  }, []);

  // =============================================================================
  // Actions: Catalog
  // =============================================================================

  const refreshProducts = useCallback(async (options: ProductListOptions = {}): Promise<ProductListResult | null> => {
    setProductsLoading(true);
    setProductsError(null);
    try {
      const result = await listProducts(options);
      setProducts(result.products);
      setProductsCount(result.count);
      return result;
    } catch (err) {
      setProductsError(err instanceof Error ? err.message : "Failed to load products");
      setProducts([]);
      setProductsCount(0);
      return null;
    } finally {
      setProductsLoading(false);
    }
  }, []);

  const refreshCollections = useCallback(async () => {
    try {
      const data = await listCollections();
      setCollections(data);
    } catch (err) {
      console.error("Failed to refresh collections:", err);
    }
  }, []);

  const refreshCategories = useCallback(async () => {
    try {
      const data = await listCategories();
      setCategories(data);
    } catch (err) {
      console.error("Failed to refresh categories:", err);
    }
  }, []);

  const loadProductByHandle = useCallback(async (handle: string) => {
    try {
      const product = await getProductByHandle(handle);
      setCurrentProduct(product);
      return product;
    } catch (err) {
      console.error("Failed to load product:", err);
      return null;
    }
  }, []);

  const loadCollectionByHandle = useCallback(async (handle: string) => {
    try {
      const collection = await getCollectionByHandle(handle);
      setCurrentCollection(collection);
      return collection;
    } catch (err) {
      console.error("Failed to load collection:", err);
      return null;
    }
  }, []);

  const loadCategoryByHandle = useCallback(async (handle: string) => {
    try {
      const category = await getCategoryByHandle(handle);
      setCurrentCategory(category);
      return category;
    } catch (err) {
      console.error("Failed to load category:", err);
      return null;
    }
  }, []);

  // =============================================================================
  // Actions: Cart
  // =============================================================================

  /**
   * Create a new cart.
   *
   * Country/Region contract:
   * - If regionId is provided, cart is created with that region.
   * - If no regionId, cart is created with the session's default country code.
   * - Country cannot be changed mid-checkout (would invalidate region-dependent state).
   *   If user needs different country/region, they must start a fresh cart.
   */
  const createCart = useCallback(async (regionId?: string) => {
    setCartLoading(true);
    setCartError(null);
    try {
      const newCart = siteCartProxyBasePath
        ? await createSiteCart({ regionId })
        : regionId
          ? await createMedusaCart({ regionId, countryCode })
          : await getOrCreateCart();
      setCart(newCart);
      return newCart;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create cart";
      setCartError(message);
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, [countryCode, createSiteCart, siteCartProxyBasePath]);

  const refreshCart = useCallback(async () => {
    const cartId = getCartId();
    if (!cartId) {
      setCart(null);
      return;
    }
    setCartLoading(true);
    try {
      const cartData = siteCartProxyBasePath ? await getSiteCart(cartId) : await getCart(cartId);
      if (cartData?.completed_at) {
        setCartId(null);
        setCart(null);
        return;
      }
      setCart(cartData);
    } catch (err) {
      setCartError(err instanceof Error ? err.message : "Failed to refresh cart");
    } finally {
      setCartLoading(false);
    }
  }, [getSiteCart, siteCartProxyBasePath]);

  const addToCart = useCallback(async (variantId: string, quantity: number) => {
    setCartLoading(true);
    setCartError(null);
    try {
      let cartId = getCartId();
      if (!cartId) {
        const newCart = siteCartProxyBasePath ? await getOrCreateSiteCart() : await getOrCreateCart();
        cartId = newCart.id;
      }
      const updatedCart = siteCartProxyBasePath
        ? await addSiteCartLineItem(cartId, variantId, quantity)
        : await addCartLineItem(cartId, variantId, quantity);
      setCart(updatedCart);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to add to cart";
      setCartError(message);
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, [addSiteCartLineItem, getOrCreateSiteCart, siteCartProxyBasePath]);

  const replaceCartWithVariant = useCallback(async (variantId: string, quantity: number): Promise<MedusaCart> => {
    setCartLoading(true);
    setCartError(null);
    try {
      const baseCart = siteCartProxyBasePath ? await getOrCreateSiteCart() : await getOrCreateCart();
      const cartId = baseCart.id;
      if (!cartId) {
        throw new Error("Failed to resolve an active cart for replacement.");
      }

      let workingCart = baseCart;
      const existingItems = Array.isArray(baseCart.items) ? [...baseCart.items] : [];
      for (const item of existingItems) {
        if (!item?.id) continue;
        workingCart = siteCartProxyBasePath
          ? await deleteSiteCartLineItem(cartId, item.id)
          : await deleteCartLineItem(cartId, item.id);
      }

      const updatedCart = siteCartProxyBasePath
        ? await addSiteCartLineItem(workingCart.id || cartId, variantId, quantity)
        : await addCartLineItem(workingCart.id || cartId, variantId, quantity);
      setCart(updatedCart);
      return updatedCart;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to replace cart contents";
      setCartError(message);
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, [addSiteCartLineItem, deleteSiteCartLineItem, getOrCreateSiteCart, siteCartProxyBasePath]);

  const updateCartItem = useCallback(async (lineId: string, quantity: number) => {
    const cartId = getCartId();
    if (!cartId) return;
    setCartLoading(true);
    try {
      const updatedCart = siteCartProxyBasePath
        ? await updateSiteCartLineItem(cartId, lineId, quantity)
        : await updateCartLineItem(cartId, lineId, quantity);
      setCart(updatedCart);
    } catch (err) {
      setCartError(err instanceof Error ? err.message : "Failed to update cart item");
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, [siteCartProxyBasePath, updateSiteCartLineItem]);

  const removeCartItem = useCallback(async (lineId: string) => {
    const cartId = getCartId();
    if (!cartId) return;
    setCartLoading(true);
    try {
      const updatedCart = siteCartProxyBasePath
        ? await deleteSiteCartLineItem(cartId, lineId)
        : await deleteCartLineItem(cartId, lineId);
      setCart(updatedCart);
    } catch (err) {
      setCartError(err instanceof Error ? err.message : "Failed to remove cart item");
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, [deleteSiteCartLineItem, siteCartProxyBasePath]);

  const applyPromotionCode = useCallback(async (code: string) => {
    const cartId = getCartId();
    if (!cartId) {
      throw new Error("No cart available");
    }
    setCartLoading(true);
    setCartError(null);
    try {
      const updatedCart = await applyMedusaPromotionCode(cartId, code);
      setCart(updatedCart);
    } catch (err) {
      setCartError(err instanceof Error ? err.message : "Failed to apply discount code");
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, []);

  const removePromotionCode = useCallback(async (code: string) => {
    const cartId = getCartId();
    if (!cartId) {
      throw new Error("No cart available");
    }
    setCartLoading(true);
    setCartError(null);
    try {
      const updatedCart = await removeMedusaPromotionCode(cartId, code);
      setCart(updatedCart);
    } catch (err) {
      setCartError(err instanceof Error ? err.message : "Failed to remove discount code");
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, []);

  const updateCartEmail = useCallback(async (email: string) => {
    const cartId = getCartId();
    if (!cartId) return;
    setCartLoading(true);
    try {
      const updatedCart = siteCartProxyBasePath
        ? await updateSiteCart(cartId, { email })
        : await updateCart(cartId, { email });
      setCart(updatedCart);
    } catch (err) {
      setCartError(err instanceof Error ? err.message : "Failed to update email");
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, [siteCartProxyBasePath, updateSiteCart]);

  const updateCartShippingAddress = useCallback(async (address: Record<string, unknown>) => {
    const cartId = getCartId();
    if (!cartId) return;
    setCartLoading(true);
    try {
      const updatedCart = siteCartProxyBasePath
        ? await updateSiteCart(cartId, { shippingAddress: address })
        : await updateCart(cartId, { shippingAddress: address });
      setCart(updatedCart);
    } catch (err) {
      setCartError(err instanceof Error ? err.message : "Failed to update address");
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, [siteCartProxyBasePath, updateSiteCart]);

  const updateCartBillingAddress = useCallback(async (address: Record<string, unknown>) => {
    const cartId = getCartId();
    if (!cartId) return;
    setCartLoading(true);
    try {
      const updatedCart = siteCartProxyBasePath
        ? await updateSiteCart(cartId, { billingAddress: address })
        : await updateCart(cartId, { billingAddress: address });
      setCart(updatedCart);
    } catch (err) {
      setCartError(err instanceof Error ? err.message : "Failed to update billing address");
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, [siteCartProxyBasePath, updateSiteCart]);

  /**
   * Consolidated checkout action helper.
   * Performs a checkout step mutation and returns the updated cart state.
   * Use this instead of manually chaining fetch/update/setCart in checkout components.
   *
   * Supported steps:
   * - update_email: Set cart email
   * - update_shipping_address: Set shipping address
   * - update_billing_address: Set billing address
   * - set_shipping_method: Add shipping method to cart
   * - init_payment_session: Initialize payment session (returns payment collection, not cart)
   *
   * Note: init_payment_session returns a MedusaPaymentCollection, not a MedusaCart.
   * The cart state is NOT updated by this step - you must handle the payment collection
   * in your checkout UI.
   */
  const performCheckoutAction = useCallback(async (
    step: CheckoutStep,
    data: CheckoutStepData
  ): Promise<MedusaCart | MedusaPaymentCollection> => {
    const cartId = getCartId();
    if (!cartId) throw new Error("No cart available for checkout action");

    setCartLoading(true);
    setCartError(null);

    try {
      switch (step) {
        case "update_email": {
          if (data.step !== "update_email") throw new Error("Invalid step data");
          const updatedCart = siteCartProxyBasePath
            ? await updateSiteCart(cartId, { email: data.email })
            : await updateCart(cartId, { email: data.email });
          setCart(updatedCart);
          return updatedCart;
        }
        case "update_shipping_address": {
          if (data.step !== "update_shipping_address") throw new Error("Invalid step data");
          const updatedCart = siteCartProxyBasePath
            ? await updateSiteCart(cartId, { shippingAddress: data.address })
            : await updateCart(cartId, { shippingAddress: data.address });
          setCart(updatedCart);
          return updatedCart;
        }
        case "update_billing_address": {
          if (data.step !== "update_billing_address") throw new Error("Invalid step data");
          const updatedCart = siteCartProxyBasePath
            ? await updateSiteCart(cartId, { billingAddress: data.address })
            : await updateCart(cartId, { billingAddress: data.address });
          setCart(updatedCart);
          return updatedCart;
        }
        case "set_shipping_method": {
          if (data.step !== "set_shipping_method") throw new Error("Invalid step data");
          const updatedCart = await addShippingMethod(cartId, data.optionId);
          setCart(updatedCart);
          return updatedCart;
        }
        case "init_payment_session": {
          if (data.step !== "init_payment_session") throw new Error("Invalid step data");
          if (siteId) {
            const response = await apiPost<{ payment_collection: MedusaPaymentCollection }>(
              `/sites/${encodeURIComponent(siteId)}/medusa/checkout/session?cart_id=${encodeURIComponent(cartId)}&provider_id=${encodeURIComponent(data.providerId)}`
            );
            return response.payment_collection;
          }
          // Payment session doesn't update cart - caller handles the payment collection
          return await initializePaymentSession(cartId, data.providerId);
        }
        default:
          throw new Error(`Unknown checkout step: ${step satisfies never}`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : `Checkout action failed: ${step}`;
      setCartError(message);
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, [addShippingMethod, apiPost, siteCartProxyBasePath, siteId, updateSiteCart]);

  // =============================================================================
  // Actions: Shipping
  // =============================================================================

  const getShippingOptions = useCallback(async () => {
    const cartId = getCartId();
    if (!cartId) throw new Error("No cart available");
    return listShippingOptions(cartId);
  }, []);

  const selectShippingMethod = useCallback(async (optionId: string) => {
    const cartId = getCartId();
    if (!cartId) throw new Error("No cart available");
    setCartLoading(true);
    try {
      const updatedCart = await addShippingMethod(cartId, optionId);
      setCart(updatedCart);
    } catch (err) {
      setCartError(err instanceof Error ? err.message : "Failed to select shipping method");
      throw err;
    } finally {
      setCartLoading(false);
    }
  }, []);

  // =============================================================================
  // Actions: Payment
  // =============================================================================

  const getPaymentProviders = useCallback(async () => {
    const cartId = getCartId();
    if (!cartId) throw new Error("No cart available");
    // Get region from cart
    const cartData = await getCart(cartId);
    if (!cartData?.region_id) throw new Error("Cart has no region");
    if (siteId) {
      const response = await apiGet<{
        payment_providers: MedusaPaymentProvider[];
        default_payment_provider_id: string | null;
      }>(
        `/sites/${encodeURIComponent(siteId)}/medusa/payment-providers?region_id=${encodeURIComponent(cartData.region_id)}`
      );
      const defaultProviderId =
        typeof response.default_payment_provider_id === "string"
          ? response.default_payment_provider_id
          : null;
      return (response.payment_providers || []).map((provider) => ({
        ...provider,
        is_default: provider.id === defaultProviderId,
      }));
    }
    return listPaymentProviders(cartData.region_id);
  }, [apiGet, siteId]);

  const initPaymentSession = useCallback(async (providerId: string) => {
    const cartId = getCartId();
    if (!cartId) throw new Error("No cart available");
    setCartLoading(true);
    try {
      if (siteId) {
        const response = await apiPost<{ payment_collection: MedusaPaymentCollection }>(
          `/sites/${encodeURIComponent(siteId)}/medusa/checkout/session?cart_id=${encodeURIComponent(cartId)}&provider_id=${encodeURIComponent(providerId)}`
        );
        return response.payment_collection;
      }
      return await initializePaymentSession(cartId, providerId);
    } finally {
      setCartLoading(false);
    }
  }, [apiPost, siteId]);

  const completeCheckoutAction = useCallback(async () => {
    const cartId = getCartId();
    if (!cartId) throw new Error("No cart available");
    setCartLoading(true);
    try {
      const result = await completeCart(cartId);
      if (result.cart) {
        setCart(result.cart);
      } else {
        setCart(null);
      }
      return result;
    } finally {
      setCartLoading(false);
    }
  }, []);

  // =============================================================================
  // Actions: Customer
  // =============================================================================

  const login = useCallback(async (email: string, password: string) => {
    setCustomerLoading(true);
    setCustomerError(null);
    try {
      const result = await loginCustomer(email, password);
      setAuthToken(result.token);
      setCustomer(result.customer);
      setCustomerError(null);
    } finally {
      setCustomerLoading(false);
    }
  }, []);

  const register = useCallback(async (
    email: string,
    password: string,
    firstName?: string,
    lastName?: string,
    phone?: string
  ) => {
    setCustomerLoading(true);
    setCustomerError(null);
    try {
      await registerCustomer(email, password, firstName, lastName, phone);
    } finally {
      setCustomerLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await logoutCustomer();
    setAuthToken(null);
    setCustomer(null);
    setCustomerError(null);
    setCart(null);
  }, []);

  const refreshCustomer = useCallback(async () => {
    if (!getAuthToken()) return;
    setCustomerLoading(true);
    setCustomerError(null);
    try {
      const customerData = await getCurrentCustomer();
      setCustomer(customerData);
      setCustomerError(null);
    } catch (err) {
      if (err instanceof MedusaApiError && err.statusCode === 401) {
        setAuthToken(null);
        setCustomer(null);
        setCustomerError(null);
      } else {
        setCustomerError(err instanceof Error ? err.message : "Failed to refresh customer account.");
        throw err;
      }
    } finally {
      setCustomerLoading(false);
    }
  }, []);

  const updateCustomerAction = useCallback(async (input: UpdateCustomerInput) => {
    setCustomerLoading(true);
    try {
      const updatedCustomer = await updateCustomer(input);
      setCustomer(updatedCustomer);
    } finally {
      setCustomerLoading(false);
    }
  }, []);

  const requestPasswordResetAction = useCallback(async (email?: string) => {
    const targetEmail = (email || customer?.email || "").trim();
    if (!targetEmail) {
      throw new MedusaApiError("A customer email is required to send a password reset link.");
    }
    await requestCustomerPasswordReset(targetEmail);
  }, [customer?.email]);

  // =============================================================================
  // Actions: Addresses
  // =============================================================================

  const addCustomerAddressAction = useCallback(async (input: CreateAddressInput) => {
    setCustomerLoading(true);
    try {
      const updatedCustomer = await createCustomerAddress(input);
      setCustomer(updatedCustomer);
    } finally {
      setCustomerLoading(false);
    }
  }, []);

  const updateCustomerAddressAction = useCallback(async (addressId: string, input: UpdateAddressInput) => {
    setCustomerLoading(true);
    try {
      const updatedCustomer = await updateCustomerAddress(addressId, input);
      setCustomer(updatedCustomer);
    } finally {
      setCustomerLoading(false);
    }
  }, []);

  const deleteCustomerAddressAction = useCallback(async (addressId: string) => {
    setCustomerLoading(true);
    try {
      await deleteCustomerAddress(addressId);
      // Refresh customer to get updated addresses list
      const customerData = await getCurrentCustomer();
      setCustomer(customerData);
    } finally {
      setCustomerLoading(false);
    }
  }, []);

  // =============================================================================
  // Actions: Orders
  // =============================================================================

  const listOrdersAction = useCallback(async (limit?: number, offset?: number) => {
    const result = await listOrders({ limit, offset });
    return { orders: result.orders, count: result.count };
  }, []);

  const getOrderAction = useCallback(async (orderId: string) => {
    return getOrder(orderId);
  }, []);

  const requestOrderTransferAction = useCallback(async (orderId: string) => {
    return requestOrderTransfer(orderId);
  }, []);

  const acceptOrderTransferAction = useCallback(async (orderId: string, token: string) => {
    return acceptOrderTransfer(orderId, token);
  }, []);

  const declineOrderTransferAction = useCallback(async (orderId: string, token: string) => {
    return declineOrderTransfer(orderId, token);
  }, []);

  // =============================================================================
  // Navigation Helpers
  // =============================================================================

  const resolvePageSlug = useCallback((pageType: B2CPageType): string | null => {
    if (!funnelRuntime?.pageTypeMap) return null;
    
    for (const [pageId, type] of Object.entries(funnelRuntime.pageTypeMap)) {
      if (type === pageType) {
        return funnelRuntime.pageMap[pageId] || null;
      }
    }
    return null;
  }, [funnelRuntime]);

  const buildSitePath = useCallback((pageType: B2CPageType, params?: Record<string, string>): string | null => {
    if (!funnelRuntime) return null;
    const countryPrefix = countryCode || "us";
    let sitePath = countryPrefix;

    switch (pageType) {
      case "home":
        sitePath = countryPrefix;
        break;
      case "store":
        sitePath = `${countryPrefix}/store`;
        break;
      case "collection":
        sitePath = `${countryPrefix}/collections/${params?.handle || ""}`;
        break;
      case "category":
        sitePath = `${countryPrefix}/categories/${params?.handle || ""}`;
        break;
      case "product_detail":
        sitePath = `${countryPrefix}/products/${params?.handle || ""}`;
        break;
      case "cart":
        sitePath = `${countryPrefix}/cart`;
        break;
      case "checkout":
        sitePath = `${countryPrefix}/checkout`;
        break;
      case "account_dashboard":
        sitePath = `${countryPrefix}/account`;
        break;
      case "account_profile":
        sitePath = `${countryPrefix}/account/profile`;
        break;
      case "account_addresses":
        sitePath = `${countryPrefix}/account/addresses`;
        break;
      case "account_orders":
        sitePath = `${countryPrefix}/account/orders`;
        break;
      case "account_order_detail":
        sitePath = `${countryPrefix}/account/orders/details/${params?.orderId || ""}`;
        break;
      case "order_confirmed":
        sitePath = `${countryPrefix}/order/${params?.orderId || ""}/confirmed`;
        break;
      case "order_transfer":
        sitePath = `${countryPrefix}/order/${params?.orderId || ""}/transfer/${params?.token || ""}`;
        break;
      case "order_transfer_accept":
        sitePath = `${countryPrefix}/order/${params?.orderId || ""}/transfer/${params?.token || ""}/accept`;
        break;
      case "order_transfer_decline":
        sitePath = `${countryPrefix}/order/${params?.orderId || ""}/transfer/${params?.token || ""}/decline`;
        break;
      default:
        return null;
    }

    return resolveRuntimeSitePath(funnelRuntime, sitePath);
  }, [countryCode, funnelRuntime]);

  const navigateToHome = useCallback(() => {
    const path = buildSitePath("home");
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToStore = useCallback(() => {
    const path = buildSitePath("store");
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToCollection = useCallback((handle: string) => {
    const path = buildSitePath("collection", { handle });
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToCategory = useCallback((handle: string) => {
    const path = buildSitePath("category", { handle });
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToProduct = useCallback((handle: string) => {
    const path = buildSitePath("product_detail", { handle });
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToCart = useCallback(() => {
    const path = buildSitePath("cart");
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToCheckout = useCallback(() => {
    const path = buildSitePath("checkout");
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToAccount = useCallback(() => {
    const path = buildSitePath("account_dashboard");
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToAccountProfile = useCallback(() => {
    const path = buildSitePath("account_profile");
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToAccountAddresses = useCallback(() => {
    const path = buildSitePath("account_addresses");
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToAccountOrders = useCallback(() => {
    const path = buildSitePath("account_orders");
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToOrder = useCallback((orderId: string) => {
    const path = buildSitePath("account_order_detail", { orderId });
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  const navigateToOrderConfirmed = useCallback((orderId: string) => {
    const path = buildSitePath("order_confirmed", { orderId });
    if (path) navigate(path);
  }, [buildSitePath, navigate]);

  // =============================================================================
  // Context Value
  // =============================================================================

  const value: B2CRuntimeContextValue = {
    isConfigured,
    configError,
    siteId,
    siteClientId,
    siteFamily,
    siteName,
    countryCode,
    locale,
    regions,
    products,
    collections,
    categories,
    productsLoading,
    productsError,
    productsCount,
    currentProduct,
    currentCategory,
    currentCollection,
    cart,
    cartLoading,
    cartError,
    customer,
    customerLoading,
    customerError,
    isAuthenticated,
    setCountry,
    setLocalePreference,
    refreshProducts,
    refreshCollections,
    refreshCategories,
    loadProductByHandle,
    loadCollectionByHandle,
    loadCategoryByHandle,
    createCart,
    refreshCart,
    addToCart,
    replaceCartWithVariant,
    updateCartItem,
    removeCartItem,
    applyPromotionCode,
    removePromotionCode,
    updateCartEmail,
    updateCartShippingAddress,
    updateCartBillingAddress,
    performCheckoutAction,
    getShippingOptions,
    selectShippingMethod,
    getPaymentProviders,
    initPaymentSession,
    completeCheckout: completeCheckoutAction,
    login,
    register,
    logout,
    refreshCustomer,
    updateCustomer: updateCustomerAction,
    requestPasswordReset: requestPasswordResetAction,
    addCustomerAddress: addCustomerAddressAction,
    updateCustomerAddress: updateCustomerAddressAction,
    deleteCustomerAddress: deleteCustomerAddressAction,
    listOrders: listOrdersAction,
    getOrder: getOrderAction,
    requestOrderTransfer: requestOrderTransferAction,
    acceptOrderTransfer: acceptOrderTransferAction,
    declineOrderTransfer: declineOrderTransferAction,
    navigateToHome,
    navigateToStore,
    navigateToCollection,
    navigateToCategory,
    navigateToProduct,
    navigateToCart,
    navigateToCheckout,
    navigateToAccount,
    navigateToAccountProfile,
    navigateToAccountAddresses,
    navigateToAccountOrders,
    navigateToOrder,
    navigateToOrderConfirmed,
    resolvePageSlug,
  };

  if (!isConfigured) {
    return (
      <div className="mx-auto my-10 max-w-3xl rounded-2xl border border-danger/30 bg-danger/10 px-6 py-5 text-sm text-danger">
        {configError || "Medusa runtime configuration is missing for this storefront."}
      </div>
    );
  }

  return (
    <B2CRuntimeContext.Provider value={value}>
      <ImportedOneProductShellContext.Provider value={importedShell}>
        {importedShellDesignSystemTokens ? (
          <DesignSystemProvider tokens={importedShellDesignSystemTokens}>{children}</DesignSystemProvider>
        ) : (
          children
        )}
      </ImportedOneProductShellContext.Provider>
    </B2CRuntimeContext.Provider>
  );
}
