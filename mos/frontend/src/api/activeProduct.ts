import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import type { Product } from "@/types/products";

export type ActiveProductSummary = Pick<Product, "id" | "name" | "client_id"> & {
  category?: string | null;
};

export type ActiveProductResponse = {
  active_product_id: string | null;
  active_product: ActiveProductSummary | null;
};

export function useActiveProduct(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<ActiveProductResponse>({
    queryKey: ["clients", "active-product", clientId],
    queryFn: () => get(`/clients/${clientId}/active-product`),
    enabled: Boolean(clientId),
  });
}

export function useSetActiveProduct() {
  const { request } = useApiClient();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (vars: {
      clientId: string;
      productId: string;
      optimisticProduct?: ActiveProductSummary;
    }) => {
      const data = await request<ActiveProductResponse>(`/clients/${vars.clientId}/active-product`, {
        method: "PUT",
        body: JSON.stringify({ product_id: vars.productId }),
      });
      return { ...data, clientId: vars.clientId };
    },
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ["clients", "active-product", vars.clientId] });
      const previous = queryClient.getQueryData<ActiveProductResponse>(["clients", "active-product", vars.clientId]);

      if (vars.optimisticProduct) {
        queryClient.setQueryData<ActiveProductResponse>(["clients", "active-product", vars.clientId], {
          active_product_id: vars.optimisticProduct.id,
          active_product: vars.optimisticProduct,
        });
      }

      return { previous };
    },
    onSuccess: (data) => {
      queryClient.setQueryData<ActiveProductResponse>(["clients", "active-product", data.clientId], {
        active_product_id: data.active_product_id,
        active_product: data.active_product,
      });
    },
    onError: (err: ApiError | Error, vars, ctx) => {
      if (ctx?.previous) {
        queryClient.setQueryData<ActiveProductResponse>(["clients", "active-product", vars.clientId], ctx.previous);
      }
      const message = "message" in err ? err.message : err?.message || "Failed to save product selection";
      toast.error(message);
    },
  });
}

