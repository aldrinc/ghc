/**
 * Direct Medusa Store API data access layer.
 * 
 * These functions make direct calls to Medusa using the JS SDK.
 * They replace the MOS commerce proxy for catalog, cart, and customer operations.
 */

import { getMedusaClient, getMedusaRuntimeConfig } from "./config";
import { getCartId, setCartId, getAuthToken, setAuthToken, getCountryCode } from "./session";
import type {
  MedusaProduct,
  MedusaCollection,
  MedusaCategory,
  MedusaRegion,
  MedusaCart,
  MedusaShippingOption,
  MedusaPaymentProvider,
  MedusaPaymentCollection,
  MedusaCustomer,
  MedusaOrder,
} from "@/types/commerce";

// =============================================================================
// Error Handling
// =============================================================================

export class MedusaApiError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public responseData?: unknown
  ) {
    super(message);
    this.name = "MedusaApiError";
  }
}

function handleApiError(error: unknown): never {
  if (error instanceof MedusaApiError) {
    throw error;
  }
  
  const message = error instanceof Error ? error.message : "Unknown API error";
  
  // Check for Medusa SDK error structure
  const medusaError = error as { status?: number; response?: { data?: unknown } };
  if (medusaError.status) {
    throw new MedusaApiError(message, medusaError.status, medusaError.response?.data);
  }
  
  throw new MedusaApiError(message);
}

async function medusaStoreFetch<TResponse>(
  path: string,
  options: {
    method?: "POST" | "DELETE";
    body?: Record<string, unknown>;
  } = {},
): Promise<TResponse> {
  const config = getMedusaRuntimeConfig();
  if (!config) {
    throw new MedusaApiError(
      "Medusa runtime is not configured. Please set VITE_MEDUSA_BACKEND_URL and VITE_MEDUSA_PUBLISHABLE_KEY.",
    );
  }

  const authToken = getAuthToken();
  const response = await fetch(`${config.backendUrl}${path}`, {
    method: options.method || "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "x-publishable-api-key": config.publishableKey,
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    },
    body: JSON.stringify(options.body || {}),
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "message" in payload && typeof payload.message === "string"
        ? payload.message
        : typeof payload === "string" && payload.trim()
          ? payload
          : `Medusa request failed with status ${response.status}.`;
    throw new MedusaApiError(message, response.status, payload);
  }

  return payload as TResponse;
}

// =============================================================================
// Regions
// =============================================================================

/**
 * List all available regions from Medusa.
 */
export async function listRegions(): Promise<MedusaRegion[]> {
  try {
    const client = getMedusaClient();
    const response = await client.store.region.list();
    return response.regions as MedusaRegion[];
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Get a specific region by ID.
 */
export async function getRegion(regionId: string): Promise<MedusaRegion | null> {
  try {
    const client = getMedusaClient();
    const response = await client.store.region.retrieve(regionId);
    return response.region as MedusaRegion;
  } catch (error) {
    const medusaError = error as { status?: number };
    if (medusaError.status === 404) {
      return null;
    }
    return handleApiError(error);
  }
}

// =============================================================================
// Products
// =============================================================================

export type ProductListOptions = {
  limit?: number;
  offset?: number;
  collectionId?: string[];
  categoryId?: string[];
  regionId?: string;
  q?: string;
  order?: string;
};

export type ProductListResult = {
  products: MedusaProduct[];
  count: number;
  offset: number;
  limit: number;
};

/**
 * List products from Medusa with optional filtering.
 */
export async function listProducts(options: ProductListOptions = {}): Promise<ProductListResult> {
  try {
    const client = getMedusaClient();
    const response = await client.store.product.list({
      limit: options.limit ?? 100,
      offset: options.offset ?? 0,
      collection_id: options.collectionId,
      category_id: options.categoryId,
      region_id: options.regionId,
      q: options.q,
      order: options.order,
    });
    
    return {
      products: response.products as MedusaProduct[],
      count: response.count,
      offset: response.offset,
      limit: response.limit,
    };
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Get a product by its handle (slug).
 */
export async function getProductByHandle(handle: string): Promise<MedusaProduct | null> {
  try {
    const client = getMedusaClient();
    const response = await client.store.product.list({ handle });
    return (response.products[0] as MedusaProduct) || null;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Get a product by its ID.
 */
export async function getProduct(productId: string): Promise<MedusaProduct | null> {
  try {
    const client = getMedusaClient();
    const response = await client.store.product.retrieve(productId);
    return response.product as MedusaProduct;
  } catch (error) {
    const medusaError = error as { status?: number };
    if (medusaError.status === 404) {
      return null;
    }
    return handleApiError(error);
  }
}

// =============================================================================
// Collections
// =============================================================================

/**
 * List all collections from Medusa.
 */
export async function listCollections(): Promise<MedusaCollection[]> {
  try {
    const client = getMedusaClient();
    const response = await client.store.collection.list({ limit: 100 });
    return response.collections as MedusaCollection[];
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Get a collection by its handle.
 */
export async function getCollectionByHandle(handle: string): Promise<MedusaCollection | null> {
  try {
    const client = getMedusaClient();
    const response = await client.store.collection.list({ handle });
    return (response.collections[0] as MedusaCollection) || null;
  } catch (error) {
    return handleApiError(error);
  }
}

// =============================================================================
// Categories
// =============================================================================

/**
 * List all categories from Medusa.
 */
export async function listCategories(): Promise<MedusaCategory[]> {
  try {
    const client = getMedusaClient();
    const response = await client.store.category.list({ limit: 100 });
    return response.product_categories as MedusaCategory[];
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Get a category by its handle.
 */
export async function getCategoryByHandle(handle: string): Promise<MedusaCategory | null> {
  try {
    const categories = await listCategories();
    return categories.find((c) => c.handle === handle) || null;
  } catch (error) {
    return handleApiError(error);
  }
}

// =============================================================================
// Cart
// =============================================================================

async function resolveCartRegionId(options: {
  regionId?: string;
  countryCode?: string;
}): Promise<string> {
  const explicitRegionId = options.regionId?.trim();
  if (explicitRegionId) {
    return explicitRegionId;
  }

  const configuredRegionId = getMedusaRuntimeConfig()?.defaultRegionId?.trim();
  if (configuredRegionId) {
    return configuredRegionId;
  }

  const normalizedCountryCode = (options.countryCode || getCountryCode()).trim().toLowerCase();
  const regions = await listRegions();
  const matchingRegion = regions.find((region) =>
    region.countries?.some((country) => country.iso_2.toLowerCase() === normalizedCountryCode)
  );

  if (!matchingRegion) {
    throw new MedusaApiError(`No Medusa region is configured for country code '${normalizedCountryCode}'.`);
  }

  return matchingRegion.id;
}

/**
 * Create a new cart in Medusa.
 */
export async function createCart(options: {
  regionId?: string;
  countryCode?: string;
} = {}): Promise<MedusaCart> {
  try {
    const client = getMedusaClient();
    const regionId = await resolveCartRegionId(options);
    const response = await client.store.cart.create({
      region_id: regionId,
    });

    const cart = response.cart as MedusaCart;
    setCartId(cart.id);
    return cart;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Get the current cart from storage or create a new one.
 */
export async function getOrCreateCart(): Promise<MedusaCart> {
  const existingCartId = getCartId();
  if (existingCartId) {
    try {
      const cart = await getCart(existingCartId);
      if (cart) {
        return cart;
      }
    } catch {
      // Cart not found or expired, create new one
    }
  }
  return createCart();
}

/**
 * Get a cart by ID.
 */
export async function getCart(cartId: string): Promise<MedusaCart | null> {
  try {
    const client = getMedusaClient();
    const response = await client.store.cart.retrieve(cartId);
    return response.cart as MedusaCart;
  } catch (error) {
    const medusaError = error as { status?: number };
    if (medusaError.status === 404) {
      return null;
    }
    return handleApiError(error);
  }
}

/**
 * Update cart details.
 */
export async function updateCart(
  cartId: string,
  updates: {
    email?: string;
    shippingAddress?: Record<string, unknown>;
    billingAddress?: Record<string, unknown>;
  }
): Promise<MedusaCart> {
  try {
    const client = getMedusaClient();
    const response = await client.store.cart.update(cartId, {
      email: updates.email,
      shipping_address: updates.shippingAddress,
      billing_address: updates.billingAddress,
    });
    return response.cart as MedusaCart;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Add a line item to the cart.
 */
export async function addCartLineItem(
  cartId: string,
  variantId: string,
  quantity: number
): Promise<MedusaCart> {
  try {
    const client = getMedusaClient();
    const response = await client.store.cart.createLineItem(cartId, {
      variant_id: variantId,
      quantity,
    });
    return response.cart as MedusaCart;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Update a line item quantity.
 */
export async function updateCartLineItem(
  cartId: string,
  lineId: string,
  quantity: number
): Promise<MedusaCart> {
  try {
    const client = getMedusaClient();
    const response = await client.store.cart.updateLineItem(cartId, lineId, {
      quantity,
    });
    return response.cart as MedusaCart;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Remove a line item from the cart.
 */
export async function deleteCartLineItem(
  cartId: string,
  lineId: string
): Promise<MedusaCart> {
  try {
    const client = getMedusaClient();
    const response = await client.store.cart.deleteLineItem(cartId, lineId);
    return response.cart as MedusaCart;
  } catch (error) {
    return handleApiError(error);
  }
}

// =============================================================================
// Shipping
// =============================================================================

/**
 * List shipping options for a cart.
 */
export async function listShippingOptions(cartId: string): Promise<MedusaShippingOption[]> {
  try {
    const client = getMedusaClient();
    const cart = await getCart(cartId);
    if (!cart) {
      throw new Error("Cart not found");
    }
    const response = await client.store.fulfillment.listCartOptions({ cart_id: cart.id });
    return response.shipping_options as MedusaShippingOption[];
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Add a shipping method to the cart.
 */
export async function addShippingMethod(
  cartId: string,
  optionId: string
): Promise<MedusaCart> {
  try {
    const client = getMedusaClient();
    const response = await client.store.cart.addShippingMethod(cartId, {
      option_id: optionId,
    });
    return response.cart as MedusaCart;
  } catch (error) {
    return handleApiError(error);
  }
}

// =============================================================================
// Payment
// =============================================================================

/**
 * List payment providers for a region.
 */
export async function listPaymentProviders(regionId: string): Promise<MedusaPaymentProvider[]> {
  try {
    const client = getMedusaClient();
    const response = await client.store.payment.listPaymentProviders({ region_id: regionId });
    return response.payment_providers as MedusaPaymentProvider[];
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Initialize a payment session for a cart.
 */
export async function initializePaymentSession(
  cartId: string,
  providerId: string
): Promise<MedusaPaymentCollection> {
  try {
    const client = getMedusaClient();
    const cart = await getCart(cartId);
    if (!cart) {
      throw new Error("Cart not found");
    }
    const response = await client.store.payment.initiatePaymentSession(cart, {
      provider_id: providerId,
    });
    return response.payment_collection as MedusaPaymentCollection;
  } catch (error) {
    return handleApiError(error);
  }
}

// =============================================================================
// Checkout
// =============================================================================

/**
 * Complete the checkout for a cart.
 */
export async function completeCart(cartId: string): Promise<{
  type: "order" | "cart";
  order?: MedusaOrder;
  cart?: MedusaCart;
}> {
  try {
    const client = getMedusaClient();
    const response = await client.store.cart.complete(cartId);
    
    // Clear cart ID on successful order completion
    if (response.type === "order") {
      setCartId(null);
    }
    
    return {
      type: response.type,
      order: response.order as MedusaOrder | undefined,
      cart: response.cart as MedusaCart | undefined,
    };
  } catch (error) {
    return handleApiError(error);
  }
}

export async function applyPromotionCode(cartId: string, code: string): Promise<MedusaCart> {
  const trimmedCode = code.trim();
  if (!trimmedCode) {
    throw new MedusaApiError("Enter a discount code.");
  }

  try {
    const response = await medusaStoreFetch<{ cart: MedusaCart }>(`/store/carts/${cartId}/promotions`, {
      method: "POST",
      body: {
        promo_codes: [trimmedCode],
      },
    });
    return response.cart;
  } catch (error) {
    return handleApiError(error);
  }
}

export async function removePromotionCode(cartId: string, code: string): Promise<MedusaCart> {
  const trimmedCode = code.trim();
  if (!trimmedCode) {
    throw new MedusaApiError("Enter a discount code.");
  }

  try {
    const response = await medusaStoreFetch<{ cart: MedusaCart }>(`/store/carts/${cartId}/promotions`, {
      method: "DELETE",
      body: {
        promo_codes: [trimmedCode],
      },
    });
    return response.cart;
  } catch (error) {
    return handleApiError(error);
  }
}

// =============================================================================
// Customer / Auth
// =============================================================================

export type UpdateCustomerInput = {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
};

export type CreateAddressInput = {
  first_name?: string;
  last_name?: string;
  company?: string;
  address_1?: string;
  address_2?: string;
  city?: string;
  province?: string;
  postal_code?: string;
  country_code?: string;
  phone?: string;
  is_default_billing?: boolean;
  is_default_shipping?: boolean;
};

export type UpdateAddressInput = Partial<CreateAddressInput>;

/**
 * Register a new customer.
 */
export async function registerCustomer(
  email: string,
  password: string,
  firstName?: string,
  lastName?: string,
  phone?: string
): Promise<MedusaCustomer> {
  try {
    const client = getMedusaClient();
    const registrationToken = await client.auth.register("customer", "emailpass", {
      email,
      password,
    });
    if (typeof registrationToken !== "string") {
      throw new Error("Customer registration requires additional authentication steps that are not supported in this storefront.");
    }

    const response = await client.store.customer.create({
      email,
      first_name: firstName,
      last_name: lastName,
      phone,
    }, {}, {
      Authorization: `Bearer ${registrationToken}`,
    });
    return response.customer as MedusaCustomer;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Login a customer.
 */
export async function loginCustomer(
  email: string,
  password: string
): Promise<{ customer: MedusaCustomer; token: string }> {
  try {
    const client = getMedusaClient();
    const token = await client.auth.login("customer", "emailpass", {
      email,
      password,
    });
    if (typeof token !== "string") {
      throw new Error("Customer login requires additional authentication steps that are not supported in this storefront.");
    }

    const activeCartId = getCartId();
    if (activeCartId) {
      await client.store.cart.transferCart(activeCartId);
    }

    const customerResponse = await client.store.customer.retrieve();

    return {
      customer: customerResponse.customer as MedusaCustomer,
      token,
    };
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Logout the current customer.
 */
export async function logoutCustomer(): Promise<void> {
  try {
    const client = getMedusaClient();
    await client.auth.logout();
  } catch (error) {
    // Ignore logout errors
  } finally {
    setCartId(null);
  }
}

/**
 * Get the current logged-in customer.
 */
export async function getCurrentCustomer(): Promise<MedusaCustomer | null> {
  try {
    const client = getMedusaClient();
    const response = await client.store.customer.retrieve();
    return response.customer as MedusaCustomer;
  } catch (error) {
    const medusaError = error as { status?: number };
    if (medusaError.status === 401) {
      return null;
    }
    return handleApiError(error);
  }
}

/**
 * Update the current customer.
 */
export async function updateCustomer(input: UpdateCustomerInput): Promise<MedusaCustomer> {
  try {
    const client = getMedusaClient();
    const response = await client.store.customer.update(input);
    return response.customer as MedusaCustomer;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Request a password reset link for a customer email.
 */
export async function requestCustomerPasswordReset(email: string): Promise<void> {
  const identifier = email.trim();
  if (!identifier) {
    throw new MedusaApiError("A customer email is required to send a password reset link.");
  }

  try {
    const client = getMedusaClient();
    await client.auth.resetPassword("customer", "emailpass", {
      identifier,
    });
  } catch (error) {
    return handleApiError(error);
  }
}

// =============================================================================
// Customer Addresses
// =============================================================================

/**
 * Create a new customer address.
 */
export async function createCustomerAddress(input: CreateAddressInput): Promise<MedusaCustomer> {
  try {
    const client = getMedusaClient();
    const response = await client.store.customer.createAddress(input);
    return response.customer as MedusaCustomer;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Update a customer address.
 */
export async function updateCustomerAddress(
  addressId: string,
  input: UpdateAddressInput
): Promise<MedusaCustomer> {
  try {
    const client = getMedusaClient();
    const response = await client.store.customer.updateAddress(addressId, input);
    return response.customer as MedusaCustomer;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Delete a customer address.
 */
export async function deleteCustomerAddress(addressId: string): Promise<void> {
  try {
    const client = getMedusaClient();
    await client.store.customer.deleteAddress(addressId);
  } catch (error) {
    return handleApiError(error);
  }
}

// =============================================================================
// Orders
// =============================================================================

export type ListOrdersOptions = {
  limit?: number;
  offset?: number;
  fields?: string;
};

/**
 * List orders for the current customer.
 */
export async function listOrders(options: ListOrdersOptions = {}): Promise<{
  orders: MedusaOrder[];
  count: number;
  offset: number;
  limit: number;
}> {
  try {
    const client = getMedusaClient();
    const response = await client.store.order.list({
      limit: options.limit ?? 10,
      offset: options.offset ?? 0,
      order: "-created_at",
      fields: options.fields ?? "*items,*items.variant,*items.product",
    });
    return {
      orders: response.orders as MedusaOrder[],
      count: response.count,
      offset: response.offset,
      limit: response.limit,
    };
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Get an order by ID.
 */
export async function getOrder(orderId: string): Promise<MedusaOrder | null> {
  try {
    const client = getMedusaClient();
    const response = await client.store.order.retrieve(orderId);
    return response.order as MedusaOrder;
  } catch (error) {
    const medusaError = error as { status?: number };
    if (medusaError.status === 404) {
      return null;
    }
    return handleApiError(error);
  }
}

/**
 * Request an order transfer to a customer.
 */
export async function requestOrderTransfer(
  orderId: string
): Promise<MedusaOrder> {
  try {
    const client = getMedusaClient();
    const response = await client.store.order.requestTransfer(orderId, {});
    return response.order as MedusaOrder;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Accept an order transfer.
 */
export async function acceptOrderTransfer(
  orderId: string,
  token: string
): Promise<MedusaOrder> {
  try {
    const client = getMedusaClient();
    const response = await client.store.order.acceptTransfer(orderId, { token });
    return response.order as MedusaOrder;
  } catch (error) {
    return handleApiError(error);
  }
}

/**
 * Decline an order transfer.
 */
export async function declineOrderTransfer(
  orderId: string,
  token: string
): Promise<MedusaOrder> {
  try {
    const client = getMedusaClient();
    const response = await client.store.order.declineTransfer(orderId, { token });
    return response.order as MedusaOrder;
  } catch (error) {
    return handleApiError(error);
  }
}
