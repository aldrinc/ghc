import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useActiveProduct, useSetActiveProduct, type ActiveProductSummary } from "@/api/activeProduct";
import { useProducts } from "@/api/products";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import type { Product } from "@/types/products";

export type ProductSummary = Pick<Product, "id" | "title" | "client_id"> & {
  product_type?: string | null;
};

type ProductContextValue = {
  product: ProductSummary | null;
  products: Product[];
  isLoading: boolean;
  selectProduct: (productId: string, fallback?: Partial<ProductSummary>) => void;
  clearProduct: () => void;
  refetch: () => void;
};

const ProductContext = createContext<ProductContextValue | undefined>(undefined);

export function ProductProvider({ children }: { children: ReactNode }) {
  const { workspace } = useWorkspace();
  const clientId = workspace?.id;
  const queryClient = useQueryClient();

  const { data: products = [], isLoading: isLoadingProducts, refetch: refetchProducts } = useProducts(clientId);
  const {
    data: activeProductData,
    isLoading: isLoadingActiveProduct,
    refetch: refetchActiveProduct,
  } = useActiveProduct(clientId);
  const setActiveProduct = useSetActiveProduct();

  const product = activeProductData?.active_product ?? null;

  const selectProduct = useCallback(
    (productId: string, fallback?: Partial<ProductSummary>) => {
      if (!clientId) return;
      if (!productId) return;
      if (product?.id === productId) return;

      const match = products.find((item) => item.id === productId);
      const optimisticProduct: ActiveProductSummary | undefined = match
        ? {
            id: match.id,
            title: match.title,
            client_id: match.client_id,
            product_type: match.product_type ?? null,
          }
        : fallback?.title || fallback?.client_id || fallback?.product_type
        ? {
            id: productId,
            title: fallback?.title || "Product",
            client_id: fallback?.client_id || clientId,
            product_type: fallback?.product_type ?? null,
          }
        : undefined;

      setActiveProduct.mutate({ clientId, productId, optimisticProduct });
    },
    [clientId, product?.id, products, setActiveProduct]
  );

  const clearProduct = useCallback(() => {
    if (!clientId) return;
    queryClient.removeQueries({ queryKey: ["clients", "active-product", clientId] });
    refetchActiveProduct();
  }, [clientId, queryClient, refetchActiveProduct]);

  const value = useMemo(
    () => ({
      product,
      products,
      isLoading: isLoadingProducts || isLoadingActiveProduct,
      selectProduct,
      clearProduct,
      refetch: () => {
        refetchProducts();
        refetchActiveProduct();
      },
    }),
    [
      product,
      products,
      isLoadingProducts,
      isLoadingActiveProduct,
      selectProduct,
      clearProduct,
      refetchProducts,
      refetchActiveProduct,
    ]
  );

  return <ProductContext.Provider value={value}>{children}</ProductContext.Provider>;
}

export function useProductContext() {
  const ctx = useContext(ProductContext);
  if (!ctx) {
    throw new Error("useProductContext must be used within a ProductProvider");
  }
  return ctx;
}
