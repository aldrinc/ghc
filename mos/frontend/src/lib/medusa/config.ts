/**
 * Medusa SDK configuration and client bootstrap.
 * 
 * This module provides direct Medusa Store API access for the B2C storefront runtime.
 * It reads configuration from environment variables and provides a configured SDK instance.
 */

import Medusa from "@medusajs/js-sdk";
import { medusaAuthStorage, MEDUSA_AUTH_TOKEN_STORAGE_KEY } from "./session";

export type MedusaRuntimeConfig = {
  /** Medusa backend base URL */
  backendUrl: string;
  /** Medusa publishable API key */
  publishableKey: string;
  /** Optional Stripe Connect account for the active workspace runtime */
  stripeAccountId?: string;
  /** Default region ID for new carts */
  defaultRegionId?: string;
  /** Default country code for new carts */
  defaultCountryCode?: string;
};

let runtimeConfigOverride: MedusaRuntimeConfig | null = null;

export function setMedusaRuntimeConfig(config: MedusaRuntimeConfig | null): void {
  runtimeConfigOverride = config;
  resetMedusaClient();
}

/**
 * Get Medusa runtime configuration from environment variables.
 * Returns null if configuration is incomplete.
 */
export function getMedusaRuntimeConfig(): MedusaRuntimeConfig | null {
  if (runtimeConfigOverride) {
    return runtimeConfigOverride;
  }

  const backendUrl = import.meta.env.VITE_MEDUSA_BACKEND_URL;
  const publishableKey = import.meta.env.VITE_MEDUSA_PUBLISHABLE_KEY;

  if (!backendUrl || !publishableKey) {
    return null;
  }

  return {
    backendUrl: backendUrl.replace(/\/$/, ""), // Remove trailing slash
    publishableKey,
    defaultRegionId: import.meta.env.VITE_MEDUSA_DEFAULT_REGION_ID,
    defaultCountryCode: import.meta.env.VITE_MEDUSA_DEFAULT_COUNTRY_CODE || "us",
  };
}

/**
 * Check if Medusa runtime is properly configured.
 */
export function isMedusaRuntimeConfigured(): boolean {
  return getMedusaRuntimeConfig() !== null;
}

/**
 * Create a configured Medusa SDK instance.
 * Throws if configuration is missing.
 */
export function createMedusaClient(): Medusa {
  const config = getMedusaRuntimeConfig();
  if (!config) {
    throw new Error(
      "Medusa runtime is not configured. " +
      "Please set VITE_MEDUSA_BACKEND_URL and VITE_MEDUSA_PUBLISHABLE_KEY."
    );
  }

  return new Medusa({
    baseUrl: config.backendUrl,
    debug: import.meta.env.DEV,
    publishableKey: config.publishableKey,
    auth: {
      type: "jwt",
      jwtTokenStorageKey: MEDUSA_AUTH_TOKEN_STORAGE_KEY,
      jwtTokenStorageMethod: "custom",
      storage: medusaAuthStorage,
    },
  });
}

/**
 * Singleton SDK instance for direct Medusa API calls.
 * Lazy-initialized on first access.
 */
let _medusaClient: Medusa | null = null;

export function getMedusaClient(): Medusa {
  if (!_medusaClient) {
    _medusaClient = createMedusaClient();
  }
  return _medusaClient;
}

/**
 * Reset the SDK instance (useful for testing).
 */
export function resetMedusaClient(): void {
  _medusaClient = null;
}
