import type { Product, ProductOffer, ProductOfferPricePoint } from "@/types/products";

export type PublicCommercePricePoint = ProductOfferPricePoint;

export type PublicCommerceOffer = ProductOffer & {
  pricePoints: PublicCommercePricePoint[];
};

export type PublicFunnelCommerce = {
  publicId: string;
  funnelId: string;
  product: Product;
  selectedOfferId: string | null;
  offers: PublicCommerceOffer[];
};
