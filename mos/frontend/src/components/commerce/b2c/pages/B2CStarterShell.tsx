import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type CSSProperties,
} from "react";
import { useB2CRuntime } from "../B2CRuntimeProvider";
import {
  resolveB2CActionRadius,
  resolveB2CBodyFont,
  resolveB2CHeadingFont,
  useB2CTheme,
} from "../useB2CTheme";
import { formatPrice } from "./storefrontPrimitives";

type B2CStarterShellProps = {
  children: ReactNode;
};

function shellLinkClass(isMuted = false): string {
  const baseClasses = "text-sm transition-colors";
  return isMuted ? `${baseClasses} text-content-muted hover:text-content` : `${baseClasses} text-content-muted hover:text-content`;
}

function rootCategories<T extends { parent_category_id?: string | null }>(categories: T[]): T[] {
  return categories.filter((category) => !category.parent_category_id);
}

const SHELL_CONTENT_CLASS = "mx-auto w-full max-w-[1440px] px-4 sm:px-6 lg:px-8";

export function B2CStarterShell({ children }: B2CStarterShellProps) {
  const {
    siteName,
    categories,
    collections,
    cart,
    customer,
    updateCartItem,
    removeCartItem,
    navigateToHome,
    navigateToStore,
    navigateToCollection,
    navigateToCategory,
    navigateToCart,
    navigateToCheckout,
    navigateToAccount,
  } = useB2CRuntime();
  const { tokens, isThemed } = useB2CTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const [miniCartOpen, setMiniCartOpen] = useState(false);
  const miniCartRef = useRef<HTMLDivElement | null>(null);
  const previousCartCountRef = useRef(0);

  const primaryCategories = useMemo(() => rootCategories(categories).slice(0, 6), [categories]);
  const featuredCollections = useMemo(() => collections.slice(0, 6), [collections]);
  const cartCount = useMemo(
    () => cart?.items?.reduce((sum, item) => sum + item.quantity, 0) || 0,
    [cart?.items],
  );
  const miniCartItems = cart?.items?.slice(0, 5) || [];

  // Use themed brand name if available, fallback to siteName
  const brandName = tokens.brandName?.trim() || siteName?.trim() || "Store";
  const accountLabel = customer?.first_name?.trim() || "Account";

  const bodyFontFamily = resolveB2CBodyFont(tokens);
  const headingFontFamily = resolveB2CHeadingFont(tokens);
  const actionRadius = resolveB2CActionRadius(tokens);

  const rootStyle: CSSProperties = {
    backgroundColor: tokens.colorBackground || "#ffffff",
    color: tokens.colorText || "#111827",
    fontFamily: bodyFontFamily,
  };

  const headerStyle: CSSProperties = {
    backgroundColor: tokens.colorBackground || "#ffffff",
    borderBottomColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
  };

  const footerStyle: CSSProperties = {
    backgroundColor: tokens.colorBackgroundAlt || tokens.colorBackground || "#ffffff",
    borderTopColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
  };

  const headingStyle: CSSProperties = {
    color: tokens.colorText || "#111827",
    fontFamily: headingFontFamily,
  };

  const mutedTextStyle: CSSProperties = {
    color: tokens.colorTextMuted || "rgba(17, 24, 39, 0.64)",
  };

  const sectionLabelStyle: CSSProperties = {
    ...mutedTextStyle,
    fontFamily: bodyFontFamily,
  };
  const miniCartStyle: CSSProperties = {
    backgroundColor: tokens.colorBackground || "#ffffff",
    borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
    borderRadius: actionRadius,
    color: tokens.colorText || "#111827",
  };
  const drawerOverlayStyle: CSSProperties = {
    backgroundColor: "rgba(17, 24, 39, 0.45)",
  };

  const logoDisplay = tokens.logoUrl ? (
    <img
      src={tokens.logoUrl}
      alt={brandName}
      className="h-9 w-auto object-contain"
    />
  ) : (
    <span
      className="inline-flex h-8 w-8 items-center justify-center rounded-md border text-[10px] font-semibold uppercase tracking-[0.18em]"
      style={{
        borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
        backgroundColor: tokens.colorBackgroundAlt || tokens.colorBackground || "#fafafa",
        color: tokens.colorText || "#111827",
      }}
    >
      {brandName.slice(0, 2).toUpperCase()}
    </span>
  );

  useEffect(() => {
    if (cartCount > previousCartCountRef.current) {
      setMiniCartOpen(true);
    }
    previousCartCountRef.current = cartCount;
  }, [cartCount]);

  useEffect(() => {
    if (!miniCartOpen) {
      return;
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMiniCartOpen(false);
      }
    };

    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("keydown", handleEscape);
    };
  }, [miniCartOpen]);

  useEffect(() => {
    if (!miniCartOpen) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [miniCartOpen]);

  const handleCartTrigger = () => {
    setMiniCartOpen((open) => !open);
  };

  return (
    <div
      className="flex min-h-screen flex-col bg-surface text-content"
      style={rootStyle}
    >
      <header
        className="sticky inset-x-0 top-0 z-50 border-b border-border bg-surface text-content"
        style={headerStyle}
        data-testid="b2c-starter-header"
      >
        <div className={`${SHELL_CONTENT_CLASS} flex h-16 items-center gap-4`}>
          <div className="flex flex-1 basis-0 items-center gap-4">
            <button
              type="button"
              onClick={() => setMenuOpen((open) => !open)}
              className="inline-flex items-center justify-center rounded-full border border-border p-2 text-content transition hover:bg-surface-hover lg:hidden"
              style={{
                borderRadius: actionRadius,
                ...(isThemed
                  ? {
                      borderColor: tokens.colorBorder || undefined,
                      color: tokens.colorText || undefined,
                    }
                  : {}),
              }}
              aria-expanded={menuOpen}
              aria-label="Toggle navigation"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="h-5 w-5">
                {menuOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                )}
              </svg>
            </button>
            <nav className="hidden items-center gap-6 lg:flex" aria-label="Store navigation">
              <button
                type="button"
                onClick={navigateToStore}
                className={shellLinkClass(false)}
                style={isThemed ? { color: tokens.colorText } : undefined}
              >
                All products
              </button>
              {primaryCategories.map((category) => (
                <button
                  key={category.id}
                  type="button"
                  onClick={() => navigateToCategory(category.handle)}
                  className={shellLinkClass(false)}
                  style={isThemed ? { color: tokens.colorText } : undefined}
                >
                  {category.name}
                </button>
              ))}
            </nav>
          </div>

          <div className="flex shrink-0 items-center justify-center">
            <button type="button" onClick={navigateToHome} className="flex items-center gap-3 text-left">
              {logoDisplay}
              <span className="min-w-0">
                <span
                  className="block truncate text-sm font-semibold uppercase tracking-[0.14em] text-content"
                  style={headingStyle}
                >
                  {brandName}
                </span>
              </span>
            </button>
          </div>

          <div className="flex flex-1 basis-0 items-center justify-end gap-4 sm:gap-6">
            <button
              type="button"
              onClick={() => {
                setMiniCartOpen(false);
                navigateToAccount();
              }}
              className="hidden text-sm transition-colors hover:text-content sm:inline-flex"
              style={{
                ...(isThemed
                  ? {
                      color: tokens.colorText || undefined,
                    }
                  : {}),
              }}
            >
              {accountLabel}
            </button>
            <div
              ref={miniCartRef}
              className="relative"
            >
              <button
                type="button"
                onClick={handleCartTrigger}
                className="relative inline-flex items-center gap-1 text-sm transition-colors hover:text-content"
                style={{
                  ...(isThemed
                    ? {
                        color: tokens.colorText || undefined,
                      }
                    : {}),
                }}
                aria-expanded={miniCartOpen}
                aria-haspopup="dialog"
              >
                <span>Cart</span>
                <span style={mutedTextStyle}>({cartCount})</span>
              </button>

              {miniCartOpen ? (
                <>
                  <button
                    type="button"
                    className="fixed inset-0 z-[70] cursor-default"
                    style={drawerOverlayStyle}
                    aria-label="Close cart"
                    onClick={() => setMiniCartOpen(false)}
                  />
                  <div
                    className="fixed inset-y-0 right-0 z-[80] flex w-full justify-end"
                    role="dialog"
                    aria-label="Cart drawer"
                    aria-modal="true"
                  >
                    <div
                      className="flex h-full w-full max-w-[28rem] flex-col border-l bg-surface px-5 py-5 shadow-2xl sm:px-6"
                      style={miniCartStyle}
                    >
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <p className="text-sm font-semibold" style={headingStyle}>
                            Shopping bag
                          </p>
                          <p className="mt-1 text-xs" style={mutedTextStyle}>
                            {cartCount} item{cartCount === 1 ? "" : "s"} in cart
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setMiniCartOpen(false)}
                          className="text-xs uppercase tracking-[0.18em]"
                          style={mutedTextStyle}
                        >
                          Close
                        </button>
                      </div>

                      {miniCartItems.length === 0 ? (
                        <div className="flex flex-1 flex-col justify-center">
                          <p className="text-sm" style={mutedTextStyle}>
                            Your cart is empty.
                          </p>
                          <button
                            type="button"
                            onClick={() => setMiniCartOpen(false)}
                            className="mt-5 flex h-10 items-center justify-center border px-4 text-sm font-medium transition-colors hover:opacity-90"
                            style={{
                              borderRadius: actionRadius,
                              borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
                              color: tokens.colorText || "#111827",
                            }}
                          >
                            Continue shopping
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="mt-5 flex-1 space-y-4 overflow-y-auto pr-1">
                            {miniCartItems.map((item) => (
                              <div
                                key={item.id}
                                className="rounded-2xl border p-4"
                                style={{
                                  borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
                                  backgroundColor: tokens.colorBackgroundAlt || tokens.colorBackground || "#ffffff",
                                }}
                              >
                                <div className="flex items-start gap-3">
                                  {item.thumbnail ? (
                                    <img
                                      src={item.thumbnail}
                                      alt={item.product_title || item.title}
                                      className="h-16 w-16 rounded-md object-cover"
                                    />
                                  ) : (
                                    <div
                                      className="flex h-16 w-16 items-center justify-center rounded-md border border-dashed"
                                      style={miniCartStyle}
                                    >
                                      <span className="text-[10px]" style={mutedTextStyle}>
                                        No image
                                      </span>
                                    </div>
                                  )}
                                  <div className="min-w-0 flex-1">
                                    <p className="truncate text-sm font-medium" style={headingStyle}>
                                      {item.product_title || item.title}
                                    </p>
                                    {item.variant_title ? (
                                      <p className="mt-1 text-xs" style={mutedTextStyle}>
                                        {item.variant_title}
                                      </p>
                                    ) : null}
                                    <p className="mt-2 text-xs" style={mutedTextStyle}>
                                      {formatPrice(item.unit_price, cart?.currency_code || "usd")} each
                                    </p>
                                  </div>
                                  <button
                                    type="button"
                                    onClick={() => void removeCartItem(item.id)}
                                    className="text-xs transition-opacity hover:opacity-70"
                                    style={mutedTextStyle}
                                  >
                                    Remove
                                  </button>
                                </div>
                                <div className="mt-4 flex items-center justify-between gap-4">
                                  <div
                                    className="flex items-center border"
                                    style={{
                                      borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
                                      borderRadius: actionRadius,
                                    }}
                                  >
                                    <button
                                      type="button"
                                      className="px-3 py-2 text-sm"
                                      style={{ color: tokens.colorText || "#111827" }}
                                      onClick={() => void updateCartItem(item.id, Math.max(1, item.quantity - 1))}
                                    >
                                      -
                                    </button>
                                    <span className="min-w-10 px-2 py-2 text-center text-sm" style={headingStyle}>
                                      {item.quantity}
                                    </span>
                                    <button
                                      type="button"
                                      className="px-3 py-2 text-sm"
                                      style={{ color: tokens.colorText || "#111827" }}
                                      onClick={() => void updateCartItem(item.id, item.quantity + 1)}
                                    >
                                      +
                                    </button>
                                  </div>
                                  <p className="text-sm font-medium" style={headingStyle}>
                                    {formatPrice(item.total || item.unit_price * item.quantity, cart?.currency_code || "usd")}
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>

                          {cartCount > miniCartItems.length ? (
                            <p className="mt-4 text-xs" style={mutedTextStyle}>
                              And {cartCount - miniCartItems.length} more item{cartCount - miniCartItems.length === 1 ? "" : "s"} in cart.
                            </p>
                          ) : null}

                          <div
                            className="mt-5 border-t pt-5"
                            style={{ borderTopColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)" }}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-sm font-medium" style={headingStyle}>
                                Subtotal
                              </span>
                              <span className="text-sm" style={headingStyle}>
                                {formatPrice(cart?.subtotal, cart?.currency_code || "usd")}
                              </span>
                            </div>
                            <div className="mt-4 grid gap-3">
                              <button
                                type="button"
                                onClick={() => setMiniCartOpen(false)}
                                className="flex h-10 w-full items-center justify-center border px-4 text-sm font-medium transition-colors hover:opacity-90"
                                style={{
                                  borderRadius: actionRadius,
                                  borderColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
                                  color: tokens.colorText || "#111827",
                                }}
                              >
                                Continue shopping
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setMiniCartOpen(false);
                                  navigateToCheckout();
                                }}
                                className="flex h-10 w-full items-center justify-center border px-4 text-sm font-medium transition-colors hover:opacity-90"
                                style={{
                                  borderRadius: actionRadius,
                                  borderColor: tokens.colorPrimary || "#111827",
                                  backgroundColor: tokens.colorPrimary || "#111827",
                                  color: tokens.colorPrimaryText || "#ffffff",
                                }}
                              >
                                Checkout
                              </button>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>

        {menuOpen ? (
          <div
            className="border-t border-border bg-surface px-4 py-3 lg:hidden"
            style={{
              borderTopColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
              backgroundColor: tokens.colorBackground || "#ffffff",
            }}
          >
            <nav className="flex flex-col gap-2" aria-label="Mobile store navigation">
              <button
                type="button"
                onClick={() => {
                  navigateToStore();
                  setMiniCartOpen(false);
                  setMenuOpen(false);
                }}
                className="rounded-xl px-3 py-2 text-left text-sm text-content-muted transition hover:bg-surface-hover hover:text-content"
                style={{ borderRadius: actionRadius, ...(isThemed ? { color: tokens.colorText } : {}) }}
              >
                All products
              </button>
              {primaryCategories.map((category) => (
                <button
                  key={category.id}
                  type="button"
                  onClick={() => {
                    navigateToCategory(category.handle);
                    setMiniCartOpen(false);
                    setMenuOpen(false);
                  }}
                  className="rounded-xl px-3 py-2 text-left text-sm text-content-muted transition hover:bg-surface-hover hover:text-content"
                  style={{ borderRadius: actionRadius, ...(isThemed ? { color: tokens.colorText } : {}) }}
                >
                  {category.name}
                </button>
              ))}
              <button
                type="button"
                onClick={() => {
                  navigateToAccount();
                  setMiniCartOpen(false);
                  setMenuOpen(false);
                }}
                className="rounded-xl px-3 py-2 text-left text-sm text-content-muted transition hover:bg-surface-hover hover:text-content"
                style={{ borderRadius: actionRadius, ...(isThemed ? { color: tokens.colorText } : {}) }}
              >
                {accountLabel}
              </button>
            </nav>
          </div>
        ) : null}
      </header>

      <div className="flex-1">{children}</div>

      <footer
        className="border-t border-border bg-surface text-content"
        style={footerStyle}
        data-testid="b2c-starter-footer"
      >
        <div className={`${SHELL_CONTENT_CLASS} py-12 lg:py-14`}>
          <div className="grid gap-10 lg:grid-cols-[minmax(0,1.2fr)_repeat(3,minmax(0,1fr))]">
            <div className="max-w-sm">
              <p
                className="text-xs uppercase tracking-[0.14em] text-content-muted"
                style={mutedTextStyle}
              >
                {brandName}
              </p>
              <p
                className="mt-4 text-sm leading-7 text-content-muted"
                style={mutedTextStyle}
              >
                Browse products, collections, cart, checkout, and account pages from one storefront.
              </p>
            </div>

            <div>
              <h3
                className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted"
                style={sectionLabelStyle}
              >
                Categories
              </h3>
              <ul className="mt-5 space-y-3">
                {primaryCategories.length > 0 ? (
                  primaryCategories.map((category) => (
                    <li key={category.id}>
                      <button
                        type="button"
                        onClick={() => navigateToCategory(category.handle)}
                        className={shellLinkClass(true)}
                        style={isThemed ? { color: tokens.colorTextMuted } : undefined}
                      >
                        {category.name}
                      </button>
                    </li>
                  ))
                ) : (
                  <li
                    className="text-sm text-content-muted"
                    style={mutedTextStyle}
                  >
                    Categories appear when catalog data is available.
                  </li>
                )}
              </ul>
            </div>

            <div>
              <h3
                className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted"
                style={sectionLabelStyle}
              >
                Collections
              </h3>
              <ul className="mt-5 space-y-3">
                {featuredCollections.length > 0 ? (
                  featuredCollections.map((collection) => (
                    <li key={collection.id}>
                      <button
                        type="button"
                        onClick={() => navigateToCollection(collection.handle)}
                        className={shellLinkClass(true)}
                        style={isThemed ? { color: tokens.colorTextMuted } : undefined}
                      >
                        {collection.title}
                      </button>
                    </li>
                  ))
                ) : (
                  <li
                    className="text-sm text-content-muted"
                    style={mutedTextStyle}
                  >
                    Collections appear after products are merchandised in Medusa.
                  </li>
                )}
              </ul>
            </div>

            <div>
              <h3
                className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted"
                style={sectionLabelStyle}
              >
                Pages
              </h3>
              <ul className="mt-5 space-y-3">
                <li>
                  <button
                    type="button"
                    onClick={navigateToHome}
                    className={shellLinkClass(true)}
                    style={isThemed ? { color: tokens.colorTextMuted } : undefined}
                  >
                    Home
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={navigateToStore}
                    className={shellLinkClass(true)}
                    style={isThemed ? { color: tokens.colorTextMuted } : undefined}
                  >
                    Catalog
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={navigateToCart}
                    className={shellLinkClass(true)}
                    style={isThemed ? { color: tokens.colorTextMuted } : undefined}
                  >
                    Cart
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={navigateToAccount}
                    className={shellLinkClass(true)}
                    style={isThemed ? { color: tokens.colorTextMuted } : undefined}
                  >
                    Account
                  </button>
                </li>
              </ul>
            </div>
          </div>

          <div
            className="mt-12 flex flex-col gap-3 border-t border-border pt-6 text-xs text-content-muted sm:flex-row sm:items-center sm:justify-between"
            style={{
              borderTopColor: tokens.colorBorder || "rgba(17, 24, 39, 0.12)",
              color: tokens.colorTextMuted || "rgba(17, 24, 39, 0.64)",
            }}
          >
            <span>© {new Date().getFullYear()} {brandName}</span>
            <button type="button" onClick={navigateToStore} className={shellLinkClass(true)} style={mutedTextStyle}>
              All products
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
