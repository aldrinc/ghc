import type { CSSProperties } from "react";
import type { MedusaProduct } from "@/types/commerce";
import {
  resolveB2CActionRadius,
  resolveB2CHeadingFont,
  resolveB2CSurfaceRadius,
  useB2CTheme,
} from "../useB2CTheme";

export const PRODUCTS_PER_PAGE = 12;
export const PRICE_SORT_FETCH_LIMIT = 100;

export type CatalogSortValue = "created_at" | "price_asc" | "price_desc";

type ProductPrice = {
  amount: number;
  currencyCode: string;
};

function resolveProductPrice(product: MedusaProduct): ProductPrice | null {
  const calculatedAmount = product.variants?.[0]?.calculated_price?.calculated_amount;
  const calculatedCurrency = product.variants?.[0]?.calculated_price?.currency_code;
  if (typeof calculatedAmount === "number" && calculatedCurrency) {
    return {
      amount: calculatedAmount,
      currencyCode: calculatedCurrency,
    };
  }

  const price = product.variants?.[0]?.prices?.[0];
  if (!price || typeof price.amount !== "number" || !price.currency_code) {
    return null;
  }

  return {
    amount: price.amount,
    currencyCode: price.currency_code,
  };
}

export function normalizeCatalogSort(value: string | null | undefined): CatalogSortValue {
  if (value === "price_asc" || value === "price_desc") {
    return value;
  }
  return "created_at";
}

export function formatPrice(amount?: number, currencyCode: string = "usd"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currencyCode.toUpperCase(),
  }).format((amount || 0) / 100);
}

export function getProductPrimaryImage(product: MedusaProduct): string | null {
  const firstImage = product.images?.find(
    (image) => typeof image?.url === "string" && image.url.trim(),
  )?.url;
  if (firstImage) {
    return firstImage;
  }

  return product.thumbnail?.trim() || null;
}

export function getProductImageGallery(product: MedusaProduct): string[] {
  const images = (product.images || [])
    .map((image) => image?.url?.trim() || null)
    .filter((image): image is string => Boolean(image));

  if (images.length > 0) {
    return images;
  }

  return product.thumbnail?.trim() ? [product.thumbnail.trim()] : [];
}

export function sortCatalogProducts(
  products: MedusaProduct[],
  sort: CatalogSortValue,
): MedusaProduct[] {
  const sorted = [...products];

  if (sort === "price_asc" || sort === "price_desc") {
    const direction = sort === "price_asc" ? 1 : -1;
    sorted.sort((left, right) => {
      const leftPrice = resolveProductPrice(left)?.amount ?? Number.POSITIVE_INFINITY;
      const rightPrice = resolveProductPrice(right)?.amount ?? Number.POSITIVE_INFINITY;
      return (leftPrice - rightPrice) * direction;
    });
    return sorted;
  }

  sorted.sort((left, right) => {
    const leftDate = left.created_at ? new Date(left.created_at).getTime() : 0;
    const rightDate = right.created_at ? new Date(right.created_at).getTime() : 0;
    return rightDate - leftDate;
  });
  return sorted;
}

function buildPaginationItems(
  currentPage: number,
  totalPages: number,
): Array<number | "ellipsis-left" | "ellipsis-right"> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  if (currentPage <= 4) {
    return [1, 2, 3, 4, 5, "ellipsis-right", totalPages];
  }

  if (currentPage >= totalPages - 3) {
    return [
      1,
      "ellipsis-left",
      totalPages - 4,
      totalPages - 3,
      totalPages - 2,
      totalPages - 1,
      totalPages,
    ];
  }

  return [
    1,
    "ellipsis-left",
    currentPage - 1,
    currentPage,
    currentPage + 1,
    "ellipsis-right",
    totalPages,
  ];
}

function usePrimitiveStyles() {
  const { tokens, isThemed } = useB2CTheme();

  const textStyle: CSSProperties = {
    color: tokens.colorText || "#111827",
  };
  const mutedTextStyle: CSSProperties = {
    color: tokens.colorTextMuted || "rgba(17, 24, 39, 0.64)",
  };
  const headingStyle: CSSProperties = {
    color: tokens.colorText || "#111827",
    fontFamily: resolveB2CHeadingFont(tokens),
  };
  const surfaceStyle: CSSProperties = {
    backgroundColor: tokens.colorBackgroundAlt || tokens.colorBackground || "#ffffff",
    borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
    borderRadius: resolveB2CSurfaceRadius(tokens),
  };
  const mutedSurfaceStyle: CSSProperties = {
    backgroundColor: tokens.colorBackgroundAlt || "rgba(17, 24, 39, 0.06)",
    borderRadius: resolveB2CActionRadius(tokens),
  };
  const selectedStyle: CSSProperties | undefined = isThemed
    ? {
        backgroundColor: tokens.colorPrimary || undefined,
        borderColor: tokens.colorPrimary || undefined,
        color: tokens.colorPrimaryText || undefined,
      }
    : undefined;
  const primaryActionStyle: CSSProperties = selectedStyle
    ? {
        ...selectedStyle,
        borderRadius: resolveB2CActionRadius(tokens),
      }
    : {
        backgroundColor: "#111827",
        borderColor: "#111827",
        color: "#ffffff",
        borderRadius: resolveB2CActionRadius(tokens),
      };

  return {
    tokens,
    isThemed,
    textStyle,
    mutedTextStyle,
    headingStyle,
    surfaceStyle,
    mutedSurfaceStyle,
    selectedStyle,
    primaryActionStyle,
  };
}

const SKELETON_GRID_CLASSES: Record<number, string> = {
  3: "grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-3",
  4: "grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4",
};

export function SkeletonProductGrid({
  count = PRODUCTS_PER_PAGE,
  columns = 3,
}: {
  count?: number;
  columns?: 3 | 4;
}) {
  const { mutedSurfaceStyle } = usePrimitiveStyles();

  return (
    <div className={SKELETON_GRID_CLASSES[columns] || SKELETON_GRID_CLASSES[3]}>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="animate-pulse space-y-4">
          <div className="aspect-[4/5] w-full" style={mutedSurfaceStyle} />
          <div className="h-4 w-3/4 rounded-full" style={mutedSurfaceStyle} />
          <div className="h-4 w-1/3 rounded-full" style={mutedSurfaceStyle} />
        </div>
      ))}
    </div>
  );
}

export function StoreProductCard({
  product,
  onClick,
}: {
  product: MedusaProduct;
  onClick: () => void;
}) {
  const { headingStyle, mutedTextStyle, surfaceStyle, tokens } = usePrimitiveStyles();
  const imageUrl = getProductPrimaryImage(product);
  const price = resolveProductPrice(product);

  return (
    <button
      type="button"
      onClick={onClick}
      className="group text-left"
    >
      <div
        className="mb-4 aspect-[4/5] overflow-hidden border"
        style={surfaceStyle}
      >
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={product.title}
            className="h-full w-full object-cover transition-opacity duration-200 group-hover:opacity-95"
          />
        ) : (
          <div
            className="flex h-full w-full items-center justify-center px-6 text-center text-sm"
            style={mutedTextStyle}
          >
            {product.title}
          </div>
        )}
      </div>
      <div className="space-y-1">
        <h3
          className="line-clamp-2 text-base font-medium"
          style={headingStyle}
        >
          {product.title}
        </h3>
        {price ? (
          <p className="text-sm" style={mutedTextStyle}>
            {formatPrice(price.amount, price.currencyCode)}
          </p>
        ) : (
          <p
            className="text-sm"
            style={{ color: tokens.colorTextMuted || "rgba(17, 24, 39, 0.52)" }}
          >
            Price unavailable
          </p>
        )}
      </div>
    </button>
  );
}

export function CatalogSortSelect({
  value,
  onChange,
}: {
  value: CatalogSortValue;
  onChange: (value: CatalogSortValue) => void;
}) {
  const { textStyle, mutedTextStyle, surfaceStyle } = usePrimitiveStyles();

  return (
    <label className="flex items-center gap-3 text-sm">
      <span style={mutedTextStyle}>Sort by</span>
      <select
        value={value}
        onChange={(event) => onChange(normalizeCatalogSort(event.target.value))}
        className="h-10 min-w-[12rem] border px-3 text-sm outline-none"
        style={{
          ...surfaceStyle,
          ...textStyle,
          borderRadius: surfaceStyle.borderRadius,
        }}
      >
        <option value="created_at">Latest</option>
        <option value="price_asc">Price: Low to High</option>
        <option value="price_desc">Price: High to Low</option>
      </select>
    </label>
  );
}

export function CatalogPagination({
  currentPage,
  totalPages,
  onPageChange,
}: {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  const { textStyle, mutedTextStyle, selectedStyle, surfaceStyle } = usePrimitiveStyles();

  if (totalPages <= 1) {
    return null;
  }

  const items = buildPaginationItems(currentPage, totalPages);
  const buttonStyle: CSSProperties = {
    ...surfaceStyle,
    ...textStyle,
    borderRadius: surfaceStyle.borderRadius,
  };

  return (
    <nav
      className="mt-10 flex flex-wrap items-center justify-center gap-2"
      aria-label="Pagination"
    >
      <button
        type="button"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        className="h-10 border px-4 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        style={buttonStyle}
      >
        Previous
      </button>
      {items.map((item, index) =>
        typeof item === "number" ? (
          <button
            key={`${item}-${index}`}
            type="button"
            onClick={() => onPageChange(item)}
            className="h-10 border px-4 text-sm"
            style={item === currentPage ? { ...buttonStyle, ...selectedStyle } : buttonStyle}
            aria-current={item === currentPage ? "page" : undefined}
          >
            {item}
          </button>
        ) : (
          <span key={`${item}-${index}`} className="px-2 text-sm" style={mutedTextStyle}>
            ...
          </span>
        ),
      )}
      <button
        type="button"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="h-10 border px-4 text-sm disabled:cursor-not-allowed disabled:opacity-50"
        style={buttonStyle}
      >
        Next
      </button>
    </nav>
  );
}

export function StorefrontEmptyState({
  title,
  description,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  const { headingStyle, mutedTextStyle, primaryActionStyle, surfaceStyle, tokens } =
    usePrimitiveStyles();

  return (
    <div
      className="flex flex-col items-center justify-center gap-4 border px-6 py-14 text-center"
      style={surfaceStyle}
    >
      <div
        className="flex h-14 w-14 items-center justify-center border"
        style={{ ...surfaceStyle, borderRadius: resolveB2CActionRadius(tokens) }}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          className="h-6 w-6"
          style={mutedTextStyle}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M20.25 8.511c.884.284 1.5 1.11 1.5 2.039v7.5a2.25 2.25 0 01-2.25 2.25H4.5a2.25 2.25 0 01-2.25-2.25v-7.5c0-.93.616-1.755 1.5-2.039m16.5 0a2.25 2.25 0 00-.856-1.379L13.5 3.25a2.25 2.25 0 00-3 0L4.606 7.132a2.25 2.25 0 00-.856 1.38m16.5 0L12 13.5 3.75 8.511"
          />
        </svg>
      </div>
      <div className="space-y-2">
        <h2 className="text-xl font-medium" style={headingStyle}>
          {title}
        </h2>
        <p className="max-w-xl text-sm" style={mutedTextStyle}>
          {description}
        </p>
      </div>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="flex h-10 items-center justify-center border px-4 text-sm font-medium"
          style={primaryActionStyle}
        >
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

export function StorefrontNotFoundState({
  title = "Page not found",
  description = "The page you're looking for doesn't exist or has been moved.",
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
}: {
  title?: string;
  description?: string;
  primaryLabel?: string;
  onPrimary?: () => void;
  secondaryLabel?: string;
  onSecondary?: () => void;
}) {
  const { headingStyle, mutedTextStyle, primaryActionStyle, surfaceStyle, textStyle, tokens } =
    usePrimitiveStyles();

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-6 px-4 py-20 text-center">
      <span
        className="border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]"
        style={{ ...mutedTextStyle, borderRadius: resolveB2CActionRadius(tokens) }}
      >
        404
      </span>
      <div className="space-y-3">
        <h1 className="text-3xl font-medium" style={headingStyle}>
          {title}
        </h1>
        <p className="text-sm" style={mutedTextStyle}>
          {description}
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        {primaryLabel && onPrimary ? (
          <button
            type="button"
            onClick={onPrimary}
            className="flex h-10 items-center justify-center border px-4 text-sm font-medium"
            style={primaryActionStyle}
          >
            {primaryLabel}
          </button>
        ) : null}
        {secondaryLabel && onSecondary ? (
          <button
            type="button"
            onClick={onSecondary}
            className="flex h-10 items-center justify-center border px-4 text-sm font-medium"
            style={{
              ...surfaceStyle,
              ...textStyle,
              borderRadius: resolveB2CActionRadius(tokens),
            }}
          >
            {secondaryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
