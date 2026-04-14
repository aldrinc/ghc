import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useStripeProfiles, useCreateStripeProfile, useUpdateStripeProfile } from "./products";
import type { StripeProfile, StripeProfileCreatePayload } from "@/types/commerce";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockRequest = vi.fn();

vi.mock("@/api/client", () => ({
  useApiClient: () => ({
    get: mockGet,
    post: mockPost,
    request: mockRequest,
  }),
}));

vi.mock("@/components/ui/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const queryClient = createTestQueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
};

describe("Stripe Profile Hooks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("useStripeProfiles", () => {
    it("fetches stripe profiles successfully", async () => {
      const mockProfiles: StripeProfile[] = [
        {
          id: "profile-1",
          orgId: "org-1",
          label: "Test Profile",
          stripeAccountId: "acct_123",
          hasSecretKeyRef: true,
          hasWebhookSecretRef: true,
          mode: "shared",
          status: "active",
          createdAt: "2024-01-01T00:00:00Z",
          updatedAt: "2024-01-01T00:00:00Z",
        },
      ];

      mockGet.mockResolvedValueOnce(mockProfiles);

      const { result } = renderHook(() => useStripeProfiles(), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toEqual(mockProfiles);
      expect(mockGet).toHaveBeenCalledWith("/clients/org/stripe-profiles");
    });

    it("handles fetch error", async () => {
      mockGet.mockRejectedValueOnce(new Error("Failed to fetch"));

      const { result } = renderHook(() => useStripeProfiles(), { wrapper });

      await waitFor(() => expect(result.current.isError).toBe(true));

      expect(result.current.error).toBeDefined();
    });
  });

  describe("useCreateStripeProfile", () => {
    it("creates stripe profile successfully", async () => {
      const mockProfile: StripeProfile = {
        id: "profile-1",
        orgId: "org-1",
        label: "Test Profile",
        stripeAccountId: "acct_123",
        hasSecretKeyRef: true,
        hasWebhookSecretRef: true,
        mode: "shared",
        status: "active",
        createdAt: "2024-01-01T00:00:00Z",
        updatedAt: "2024-01-01T00:00:00Z",
      };

      mockPost.mockResolvedValueOnce(mockProfile);

      const { result } = renderHook(() => useCreateStripeProfile(), { wrapper });

      const payload: StripeProfileCreatePayload = {
        label: "Test Profile",
        stripeAccountId: "acct_123",
        secretKeyRef: "stripe/secret/ref",
        webhookSecretRef: "stripe/webhook/ref",
        mode: "shared",
      };

      result.current.mutate(payload);

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(mockPost).toHaveBeenCalledWith("/clients/org/stripe-profiles", payload);
    });
  });

  describe("useUpdateStripeProfile", () => {
    it("updates stripe profile successfully", async () => {
      const mockProfile: StripeProfile = {
        id: "profile-1",
        orgId: "org-1",
        label: "Updated Profile",
        stripeAccountId: "acct_123",
        hasSecretKeyRef: true,
        hasWebhookSecretRef: true,
        mode: "dedicated",
        status: "active",
        createdAt: "2024-01-01T00:00:00Z",
        updatedAt: "2024-01-02T00:00:00Z",
      };

      mockRequest.mockResolvedValueOnce(mockProfile);

      const { result } = renderHook(() => useUpdateStripeProfile("profile-1"), { wrapper });

      result.current.mutate({
        label: "Updated Profile",
        mode: "dedicated",
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(mockRequest).toHaveBeenCalledWith("/clients/org/stripe-profiles/profile-1", {
        method: "PUT",
        body: JSON.stringify({ label: "Updated Profile", mode: "dedicated" }),
      });
    });
  });
});
