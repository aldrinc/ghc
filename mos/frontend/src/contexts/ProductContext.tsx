import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useProducts } from "@/api/products";
import { useWorkspace } from "@/contexts/WorkspaceContext";
import { clearActiveProduct, loadActiveProduct, saveActiveProduct } from "@/lib/products";
import type { Product } from "@/types/products";

export type ProductSummary = Pick<Product, "id" | "name" | "client_id"> & {
  category?: string | null;
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
  const { data: products = [], isLoading, refetch } = useProducts(workspace?.id);
  const [product, setProduct] = useState<ProductSummary | null>(() => loadActiveProduct(workspace?.id));

  useEffect(() => {
    if (!workspace?.id) {
      setProduct(null);
      clearActiveProduct();
      return;
    }
    setProduct(loadActiveProduct(workspace.id));
  }, [workspace?.id]);

  useEffect(() => {
    if (!workspace?.id || !product) return;
    const exists = products.some((item) => item.id === product.id);
    if (!exists) {
      setProduct(null);
      clearActiveProduct(workspace.id);
    }
  }, [product, products, workspace?.id]);

  const selectProduct = useCallback(
    (productId: string, fallback?: Partial<ProductSummary>) => {
      if (!workspace?.id) return;
      const match = products.find((item) => item.id === productId);
      if (!match && !fallback) return;
      const next: ProductSummary = match
        ? {
            id: match.id,
            name: match.name,
            client_id: match.client_id,
            category: match.category ?? null,
          }
        : {
            id: productId,
            name: fallback?.name || "Product",
            client_id: fallback?.client_id || workspace.id,
            category: fallback?.category ?? null,
          };
      setProduct(next);
      saveActiveProduct(workspace.id, next);
    },
    [products, workspace?.id]
  );

  const clearProduct = useCallback(() => {
    if (!workspace?.id) {
      setProduct(null);
      clearActiveProduct();
      return;
    }
    setProduct(null);
    clearActiveProduct(workspace.id);
  }, [workspace?.id]);

  const value = useMemo(
    () => ({
      product,
      products,
      isLoading,
      selectProduct,
      clearProduct,
      refetch,
    }),
    [product, products, isLoading, selectProduct, clearProduct, refetch]
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
