import { afterEach, describe, expect, it, vi } from "vitest";
import { MEDUSA_AUTH_TOKEN_STORAGE_KEY } from "./session";

const medusaCtor = vi.fn();

vi.mock("@medusajs/js-sdk", () => ({
  default: class MockMedusa {
    constructor(config: unknown) {
      medusaCtor(config);
      return { config } as object;
    }
  },
}));

import { createMedusaClient, resetMedusaClient, setMedusaRuntimeConfig } from "./config";

describe("medusa config", () => {
  afterEach(() => {
    medusaCtor.mockReset();
    resetMedusaClient();
    setMedusaRuntimeConfig(null);
  });

  it("configures sdk auth to use the custom storefront token key", () => {
    setMedusaRuntimeConfig({
      backendUrl: "https://medusa.example.com",
      publishableKey: "pk_test_123",
      defaultCountryCode: "us",
    });

    createMedusaClient();

    expect(medusaCtor).toHaveBeenCalledWith(
      expect.objectContaining({
        baseUrl: "https://medusa.example.com",
        publishableKey: "pk_test_123",
        auth: expect.objectContaining({
          type: "jwt",
          jwtTokenStorageKey: MEDUSA_AUTH_TOKEN_STORAGE_KEY,
          jwtTokenStorageMethod: "custom",
        }),
      }),
    );
  });
});
