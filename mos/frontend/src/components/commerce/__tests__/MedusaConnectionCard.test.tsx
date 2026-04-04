import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MedusaConnectionCard } from "../MedusaConnectionCard";

const hooks = vi.hoisted(() => ({
  useMedusaConfig: vi.fn(),
  useStripeProfiles: vi.fn(),
  useUpdateMedusaConfig: vi.fn(),
  useTestMedusaConnection: vi.fn(),
  useCreateMedusaVariant: vi.fn(),
  useCreateStripeProfile: vi.fn(),
  useUpdateStripeProfile: vi.fn(),
}));

vi.mock("@/api/products", () => ({
  useMedusaConfig: hooks.useMedusaConfig,
  useStripeProfiles: hooks.useStripeProfiles,
  useUpdateMedusaConfig: hooks.useUpdateMedusaConfig,
  useTestMedusaConnection: hooks.useTestMedusaConnection,
  useCreateMedusaVariant: hooks.useCreateMedusaVariant,
  useCreateStripeProfile: hooks.useCreateStripeProfile,
  useUpdateStripeProfile: hooks.useUpdateStripeProfile,
}));

function makeMutation(overrides?: Record<string, unknown>) {
  return { mutateAsync: vi.fn(), isPending: false, ...overrides };
}

function renderCard() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MedusaConnectionCard clientId="client-1" />
    </QueryClientProvider>,
  );
}

describe("MedusaConnectionCard", () => {
  beforeEach(() => {
    hooks.useMedusaConfig.mockReturnValue({
      data: {
        id: "medusa-config-1",
        baseUrl: "https://store.example.com/",
        hasAdminApiKey: true,
        hasPublishableKey: true,
        connectionStatus: "connected",
        lastConnectionCheckAt: null,
        lastConnectionError: null,
        stripeAccountProfileId: null,
        defaultPaymentProviderId: null,
        allowedPaymentProviderIds: [],
        webhookRoutingMode: "shared_ingress",
        createdAt: null,
        updatedAt: null,
      },
      isLoading: false,
      refetch: vi.fn(),
    });
    hooks.useStripeProfiles.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    });
    hooks.useUpdateMedusaConfig.mockReturnValue(makeMutation());
    hooks.useTestMedusaConnection.mockReturnValue(makeMutation());
    hooks.useCreateMedusaVariant.mockReturnValue(makeMutation());
    hooks.useCreateStripeProfile.mockReturnValue(makeMutation());
    hooks.useUpdateStripeProfile.mockReturnValue(makeMutation());
  });

  it("renders an explicit admin link using the configured base url", () => {
    renderCard();

    const adminLink = screen.getByRole("link", { name: /open admin/i });
    expect(adminLink).toHaveAttribute("href", "https://store.example.com/app");
    expect(adminLink).toHaveAttribute("target", "_blank");
  });
});
