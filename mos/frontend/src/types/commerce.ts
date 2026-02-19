import type { Product, ProductVariant } from "@/types/products";

export type PublicCommerceVariant = Omit<ProductVariant, "external_price_id">;

export type PublicCommerceProduct = Product & {
  variants: PublicCommerceVariant[];
  variants_count: number;
};

export type PublicFunnelCommerce = {
  productSlug: string;
  funnelSlug: string;
  funnelId: string;
  product: PublicCommerceProduct;
};
