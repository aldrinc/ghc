/**
 * Browser-managed session persistence for Medusa B2C storefront.
 * 
 * This module provides a unified storage abstraction for:
 * - Cart ID persistence across page navigations
 * - Customer JWT token for authenticated sessions
 * - Country code / locale preferences
 * 
 * All storage operations go through a single abstraction to avoid
 * ad-hoc localStorage reads/writes scattered throughout the codebase.
 */

import { getMedusaRuntimeConfig } from "./config";

// Storage key prefixes to avoid collisions
const STORAGE_PREFIX = "medusa_b2c:";
const CART_ID_KEY = `${STORAGE_PREFIX}cart_id`;
export const MEDUSA_AUTH_TOKEN_STORAGE_KEY = `${STORAGE_PREFIX}auth_token`;
const AUTH_TOKEN_KEY = MEDUSA_AUTH_TOKEN_STORAGE_KEY;
const COUNTRY_CODE_KEY = `${STORAGE_PREFIX}country_code`;
const LOCALE_KEY = `${STORAGE_PREFIX}locale`;

/**
 * Session state managed by the storefront runtime.
 */
export type MedusaSessionState = {
  /** Active cart ID from Medusa */
  cartId: string | null;
  /** Customer JWT token for authenticated requests */
  authToken: string | null;
  /** Selected country code (e.g., 'us', 'gb') */
  countryCode: string | null;
  /** Selected locale (e.g., 'en-US') */
  locale: string | null;
};

/**
 * Get the default country code from runtime config or fallback.
 */
export function getDefaultCountryCode(): string {
  const config = getMedusaRuntimeConfig();
  return config?.defaultCountryCode || "us";
}

/**
 * Read the current session state from storage.
 */
export function readSessionState(): MedusaSessionState {
  if (typeof window === "undefined") {
    // Server-side rendering fallback
    return {
      cartId: null,
      authToken: null,
      countryCode: getDefaultCountryCode(),
      locale: null,
    };
  }

  return {
    cartId: localStorage.getItem(CART_ID_KEY),
    authToken: localStorage.getItem(AUTH_TOKEN_KEY),
    countryCode: localStorage.getItem(COUNTRY_CODE_KEY) || getDefaultCountryCode(),
    locale: localStorage.getItem(LOCALE_KEY),
  };
}

/**
 * Update session state in storage.
 * Only writes non-null values; null values are removed from storage.
 */
export function updateSessionState(updates: Partial<MedusaSessionState>): void {
  if (typeof window === "undefined") {
    return;
  }

  if (updates.cartId !== undefined) {
    if (updates.cartId) {
      localStorage.setItem(CART_ID_KEY, updates.cartId);
    } else {
      localStorage.removeItem(CART_ID_KEY);
    }
  }

  if (updates.authToken !== undefined) {
    if (updates.authToken) {
      localStorage.setItem(AUTH_TOKEN_KEY, updates.authToken);
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  }

  if (updates.countryCode !== undefined) {
    if (updates.countryCode) {
      localStorage.setItem(COUNTRY_CODE_KEY, updates.countryCode);
    } else {
      localStorage.removeItem(COUNTRY_CODE_KEY);
    }
  }

  if (updates.locale !== undefined) {
    if (updates.locale) {
      localStorage.setItem(LOCALE_KEY, updates.locale);
    } else {
      localStorage.removeItem(LOCALE_KEY);
    }
  }
}

/**
 * Clear all session state from storage.
 * Use this on logout or when resetting the storefront session.
 */
export function clearSessionState(): void {
  if (typeof window === "undefined") {
    return;
  }

  localStorage.removeItem(CART_ID_KEY);
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(COUNTRY_CODE_KEY);
  localStorage.removeItem(LOCALE_KEY);
}

/**
 * Get the active cart ID from storage.
 */
export function getCartId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(CART_ID_KEY);
}

/**
 * Set the active cart ID in storage.
 */
export function setCartId(cartId: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (cartId) {
    localStorage.setItem(CART_ID_KEY, cartId);
  } else {
    localStorage.removeItem(CART_ID_KEY);
  }
}

/**
 * Get the customer auth token from storage.
 */
export function getAuthToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

/**
 * Set the customer auth token in storage.
 */
export function setAuthToken(token: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

/**
 * Get the selected country code from storage.
 */
export function getCountryCode(): string {
  if (typeof window === "undefined") {
    return getDefaultCountryCode();
  }
  return localStorage.getItem(COUNTRY_CODE_KEY) || getDefaultCountryCode();
}

/**
 * Set the selected country code in storage.
 */
export function setCountryCode(countryCode: string): void {
  if (typeof window === "undefined") {
    return;
  }
  localStorage.setItem(COUNTRY_CODE_KEY, countryCode.toLowerCase());
}

/**
 * Get the selected locale from storage.
 */
export function getLocale(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(LOCALE_KEY);
}

/**
 * Set the selected locale in storage.
 */
export function setLocale(locale: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (locale) {
    localStorage.setItem(LOCALE_KEY, locale);
  } else {
    localStorage.removeItem(LOCALE_KEY);
  }
}

export const medusaAuthStorage = {
  getItem(key: string): string | null {
    if (key !== AUTH_TOKEN_KEY) {
      return null;
    }
    return getAuthToken();
  },
  setItem(key: string, value: string): void {
    if (key !== AUTH_TOKEN_KEY) {
      return;
    }
    setAuthToken(value);
  },
  removeItem(key: string): void {
    if (key !== AUTH_TOKEN_KEY) {
      return;
    }
    setAuthToken(null);
  },
};

/**
 * Generate a unique session ID for analytics/tracking.
 * This is separate from the Medusa cart/customer session.
 */
export function generateSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `sess_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
}
