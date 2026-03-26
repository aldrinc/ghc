/**
 * Medusa B2C Storefront Runtime - Direct Medusa SDK integration.
 * 
 * This module provides direct Medusa Store API access for the B2C storefront,
 * replacing the MOS commerce proxy with direct SDK calls.
 */

// Configuration and client
export {
  getMedusaRuntimeConfig,
  setMedusaRuntimeConfig,
  isMedusaRuntimeConfigured,
  createMedusaClient,
  getMedusaClient,
  resetMedusaClient,
  type MedusaRuntimeConfig,
} from "./config";

// Session management
export {
  readSessionState,
  updateSessionState,
  clearSessionState,
  getCartId,
  setCartId,
  getAuthToken,
  setAuthToken,
  getCountryCode,
  setCountryCode,
  getLocale,
  setLocale,
  medusaAuthStorage,
  MEDUSA_AUTH_TOKEN_STORAGE_KEY,
  getDefaultCountryCode,
  generateSessionId,
  type MedusaSessionState,
} from "./session";

// Data access layer
export {
  // Errors
  MedusaApiError,
  
  // Regions
  listRegions,
  getRegion,
  
  // Products
  listProducts,
  getProductByHandle,
  getProduct,
  type ProductListOptions,
  
  // Collections
  listCollections,
  getCollectionByHandle,
  
  // Categories
  listCategories,
  getCategoryByHandle,
  
  // Cart
  createCart,
  getOrCreateCart,
  getCart,
  updateCart,
  addCartLineItem,
  updateCartLineItem,
  deleteCartLineItem,
  
  // Shipping
  listShippingOptions,
  addShippingMethod,
  
  // Payment
  listPaymentProviders,
  initializePaymentSession,
  
  // Checkout
  completeCart,
  
  // Customer
  registerCustomer,
  loginCustomer,
  logoutCustomer,
  getCurrentCustomer,
  updateCustomer,
  createCustomerAddress,
  updateCustomerAddress,
  deleteCustomerAddress,
  type UpdateCustomerInput,
  type CreateAddressInput,
  type UpdateAddressInput,
  
  // Orders
  listOrders,
  getOrder,
  requestOrderTransfer,
  acceptOrderTransfer,
  declineOrderTransfer,
  type ListOrdersOptions,
} from "./data";
