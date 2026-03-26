/**
 * Medusa B2C Product Page
 * 
 * Product detail page featuring:
 * - Product gallery
 * - Variant selection
 * - Add to cart
 * - Product information
 */

import { useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useFunnelRuntime } from "@/funnels/puckConfig";
import { parseSitePath } from "@/funnels/runtimeRouting";
import { useB2CRuntime } from "../B2CRuntimeProvider";

export type MedusaB2CProductPageProps = {
  /** Product handle (overrides URL param) */
  productHandle?: string;
};

export function MedusaB2CProductPage({ productHandle: propHandle }: MedusaB2CProductPageProps) {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const runtime = useFunnelRuntime();
  const {
    currentProduct,
    cartLoading,
    loadProductByHandle,
    addToCart,
    navigateToCart,
  } = useB2CRuntime();

  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [addedToCart, setAddedToCart] = useState(false);

  const pathHandle = (() => {
    const hostedPrefix = `/f/${runtime?.productSlug || ""}/${runtime?.funnelSlug || ""}/`;
    const bundlePrefix = `/${runtime?.productSlug || ""}/${runtime?.funnelSlug || ""}/`;
    const stripped = location.pathname.startsWith(hostedPrefix)
      ? location.pathname.slice(hostedPrefix.length)
      : location.pathname.startsWith(bundlePrefix)
        ? location.pathname.slice(bundlePrefix.length)
        : "";
    return parseSitePath(stripped).handle;
  })();

  // Load product on mount
  useEffect(() => {
    const handle = propHandle || pathHandle || searchParams.get("handle") || searchParams.get("product");
    if (handle) {
      loadProductByHandle(handle);
    }
  }, [loadProductByHandle, pathHandle, propHandle, searchParams]);

  // Set default variant when product loads
  useEffect(() => {
    if (currentProduct?.variants && currentProduct.variants.length > 0) {
      setSelectedVariantId(currentProduct.variants[0].id);
    }
  }, [currentProduct]);

  const handleAddToCart = async () => {
    if (!selectedVariantId) return;
    try {
      await addToCart(selectedVariantId, quantity);
      setAddedToCart(true);
      setTimeout(() => setAddedToCart(false), 3000);
    } catch (err) {
      console.error("Failed to add to cart:", err);
    }
  };

  const formatPrice = (amount: number, currencyCode: string = "usd") => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currencyCode.toUpperCase(),
    }).format(amount / 100);
  };

  if (!currentProduct) {
    return (
      <div className="min-h-screen bg-white py-16 px-4">
        <div className="max-w-7xl mx-auto text-center">
          <p className="text-neutral-500">Product not found</p>
        </div>
      </div>
    );
  }

  const variants = currentProduct.variants || [];
  const selectedVariant = variants.find((v) => v.id === selectedVariantId);
  const price = selectedVariant?.prices?.[0];

  return (
    <div className="min-h-screen bg-white">
      <main className="py-8 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
            {/* Gallery */}
            <div className="bg-neutral-100 rounded-lg overflow-hidden">
              {currentProduct.thumbnail ? (
                <img
                  src={currentProduct.thumbnail}
                  alt={currentProduct.title}
                  className="w-full h-full object-contain aspect-square"
                />
              ) : (
                <div className="w-full aspect-square flex items-center justify-center text-neutral-400">
                  No image
                </div>
              )}
            </div>

            {/* Product Info */}
            <div className="flex flex-col">
              <h1 className="text-3xl font-medium text-zinc-900 mb-4">
                {currentProduct.title}
              </h1>
              
              {price && (
                <p className="text-2xl text-zinc-900 mb-6">
                  {formatPrice(price.amount, price.currency_code)}
                </p>
              )}

              {currentProduct.description && (
                <p className="text-neutral-600 mb-6">
                  {currentProduct.description}
                </p>
              )}

              {/* Variant Selection */}
              {variants.length > 1 && (
                <div className="mb-6">
                  <label className="block text-sm font-medium text-zinc-900 mb-2">
                    Variant
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {variants.map((variant) => (
                      <button
                        key={variant.id}
                        onClick={() => setSelectedVariantId(variant.id)}
                        className={`px-4 py-2 border rounded-lg text-sm ${
                          selectedVariantId === variant.id
                            ? "border-zinc-900 bg-zinc-900 text-white"
                            : "border-neutral-200"
                        }`}
                      >
                        {variant.title}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Quantity */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-zinc-900 mb-2">
                  Quantity
                </label>
                <div className="flex items-center border border-neutral-200 rounded-lg w-fit">
                  <button
                    onClick={() => setQuantity(Math.max(1, quantity - 1))}
                    className="px-4 py-2"
                  >
                    -
                  </button>
                  <span className="px-4 py-2">{quantity}</span>
                  <button
                    onClick={() => setQuantity(quantity + 1)}
                    className="px-4 py-2"
                  >
                    +
                  </button>
                </div>
              </div>

              {/* Add to Cart */}
              <div className="flex gap-4">
                <button
                  onClick={handleAddToCart}
                  disabled={cartLoading || !selectedVariantId}
                  className="flex-1 bg-zinc-900 text-white px-8 py-3 rounded-full font-medium disabled:opacity-50"
                >
                  {cartLoading ? "Adding..." : "Add to Cart"}
                </button>
                {addedToCart && (
                  <button
                    onClick={() => navigateToCart()}
                    className="px-8 py-3 border border-zinc-900 rounded-full font-medium"
                  >
                    View Cart
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
