import type { Product, ProductVariant } from "@/types/products";

// =============================================================================
// Legacy Funnel Commerce Types
// =============================================================================

export type PublicCommerceVariant = Omit<ProductVariant, "external_price_id">;

export type PublicCommerceProduct = Product & {
  variants: PublicCommerceVariant[];
  variants_count: number;
};

export type PublicFunnelCommerce = {
  productSlug: string;
  funnelSlug: string;
  funnelId: string;
  product: PublicCommerceProduct;
};

// =============================================================================
// Medusa Store API Response Types
// =============================================================================

export type MedusaRegion = {
  id: string;
  name: string;
  currency_code: string;
  tax_rate?: number;
  countries?: Array<{
    iso_2: string;
    display_name: string;
  }>;
};

export type MedusaProductVariant = {
  id: string;
  title: string;
  sku?: string;
  barcode?: string;
  allow_backorder?: boolean;
  manage_inventory?: boolean;
  inventory_quantity?: number;
  prices: Array<{
    id: string;
    currency_code: string;
    amount: number;
    original_amount?: number;
  }>;
  options?: Record<string, string>;
};

export type MedusaProduct = {
  id: string;
  title: string;
  handle: string;
  description?: string;
  thumbnail?: string;
  status?: string;
  variants?: MedusaProductVariant[];
  options?: Array<{
    id: string;
    title: string;
    values?: Array<{
      id: string;
      value: string;
    }>;
  }>;
  collection_id?: string;
  categories?: Array<{
    id: string;
    name: string;
  }>;
};

export type MedusaCollection = {
  id: string;
  title: string;
  handle: string;
  products?: MedusaProduct[];
};

export type MedusaCategory = {
  id: string;
  name: string;
  handle: string;
  description?: string;
  parent_category_id?: string;
  category_children?: Array<{
    id: string;
    name: string;
  }>;
};

export type MedusaCartAddress = {
  first_name?: string;
  last_name?: string;
  address_1?: string;
  address_2?: string;
  city?: string;
  province?: string;
  postal_code?: string;
  country_code?: string;
  phone?: string;
};

export type MedusaCartLineItem = {
  id: string;
  cart_id: string;
  title: string;
  description?: string;
  variant_id: string;
  quantity: number;
  unit_price: number;
  subtotal?: number;
  tax_total?: number;
  total?: number;
  variant?: MedusaProductVariant;
};

export type MedusaCart = {
  id: string;
  email?: string;
  region_id: string;
  shipping_address?: MedusaCartAddress;
  billing_address?: MedusaCartAddress;
  items?: MedusaCartLineItem[];
  shipping_methods?: Array<{
    id: string;
    shipping_option_id: string;
    price: number;
  }>;
  subtotal?: number;
  tax_total?: number;
  shipping_total?: number;
  discount_total?: number;
  total?: number;
  currency_code: string;
};

export type MedusaShippingOption = {
  id: string;
  name: string;
  price_type: string;
  amount?: number;
  currency_code?: string;
  region_id: string;
};

export type MedusaPaymentProvider = {
  id: string;
};

export type MedusaPaymentSession = {
  id: string;
  provider_id: string;
  status: string;
  amount: number;
  data?: Record<string, unknown>;
};

export type MedusaPaymentCollection = {
  id: string;
  status: string;
  amount: number;
  currency_code: string;
  payment_sessions?: MedusaPaymentSession[];
};

// =============================================================================
// Site Commerce API Types
// =============================================================================

export type SiteCommerceData = {
  // Site metadata
  siteFamily?: string;
  commerceProvider?: string;
  storeName?: string;  // Store name for branding

  // Catalog data
  regions: MedusaRegion[];
  products: MedusaProduct[];
  collections: MedusaCollection[];
  categories: MedusaCategory[];

  // Current product (if specified)
  currentProduct?: MedusaProduct;

  // Current category (if category_handle provided)
  currentCategory?: MedusaCategory;

  // Cart data (if cart_id provided)
  cart?: MedusaCart;

  // Shipping options (if cart_id provided)
  shippingOptions?: MedusaShippingOption[];

  // Payment providers (if region_id provided)
  paymentProviders?: MedusaPaymentProvider[];

  // Pagination
  productsCount?: number;

  // Errors from critical fetches
  errors?: string[];
};

export type SiteCommerceCartResponse = {
  cart: MedusaCart;
};

export type SiteCommerceShippingOptionsResponse = {
  shipping_options: MedusaShippingOption[];
};

export type SiteCommercePaymentProvidersResponse = {
  payment_providers: MedusaPaymentProvider[];
};

export type SiteCommercePaymentSessionResponse = {
  payment_collection: MedusaPaymentCollection;
};

export type SiteCommerceCompleteResponse = {
  type: "order" | "cart";
  order?: Record<string, unknown>;
  cart?: MedusaCart;
};

// =============================================================================
// Cart State Management Types
// =============================================================================

export type CartState = {
  cartId: string | null;
  cart: MedusaCart | null;
  loading: boolean;
  error: string | null;
};

export type CartAction =
  | { type: "SET_CART_ID"; payload: string | null }
  | { type: "SET_CART"; payload: MedusaCart | null }
  | { type: "SET_LOADING"; payload: boolean }
  | { type: "SET_ERROR"; payload: string | null };

export const cartReducer = (state: CartState, action: CartAction): CartState => {
  switch (action.type) {
    case "SET_CART_ID":
      return { ...state, cartId: action.payload };
    case "SET_CART":
      return { ...state, cart: action.payload };
    case "SET_LOADING":
      return { ...state, loading: action.payload };
    case "SET_ERROR":
      return { ...state, error: action.payload };
    default:
      return state;
  }
};

export const initialCartState: CartState = {
  cartId: null,
  cart: null,
  loading: false,
  error: null,
};

// =============================================================================
// Commerce Runtime Context Types
// =============================================================================

export type CommerceRuntimeContextValue = {
  // Site metadata
  siteFamily: string | null;
  commerceProvider: string | null;

  // Catalog data
  regions: MedusaRegion[];
  products: MedusaProduct[];
  collections: MedusaCollection[];
  categories: MedusaCategory[];

  // Current product (if specified)
  currentProduct: MedusaProduct | null;

  // Current category (if category_handle provided)
  currentCategory: MedusaCategory | null;

  // Cart state
  cart: MedusaCart | null;
  cartLoading: boolean;
  cartError: string | null;

  // Cart actions
  createCart: (regionId: string, countryCode?: string, email?: string) => Promise<MedusaCart>;
  getCart: (cartId: string) => Promise<MedusaCart>;
  updateCart: (updates: { email?: string; shipping_address?: MedusaCartAddress; billing_address?: MedusaCartAddress }) => Promise<MedusaCart>;
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
};
