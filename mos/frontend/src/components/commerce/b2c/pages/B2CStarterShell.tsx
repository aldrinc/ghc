import { useMemo, useState, type ReactNode } from "react";
import { useB2CRuntime } from "../B2CRuntimeProvider";

type B2CStarterShellProps = {
  children: ReactNode;
};

function shellLinkClass(isMuted = false): string {
  return isMuted
    ? "text-sm text-neutral-500 transition-colors hover:text-zinc-900"
    : "text-sm text-zinc-700 transition-colors hover:text-zinc-900";
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
    navigateToHome,
    navigateToStore,
    navigateToCollection,
    navigateToCategory,
    navigateToCart,
    navigateToAccount,
  } = useB2CRuntime();
  const [menuOpen, setMenuOpen] = useState(false);

  const primaryCategories = useMemo(() => rootCategories(categories).slice(0, 6), [categories]);
  const featuredCollections = useMemo(() => collections.slice(0, 6), [collections]);
  const cartCount = useMemo(
    () => cart?.items?.reduce((sum, item) => sum + item.quantity, 0) || 0,
    [cart?.items],
  );
  const brandName = siteName?.trim() || "Store";
  const accountLabel = customer?.first_name?.trim() || "Account";

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <header
        className="sticky top-0 z-50 border-b border-neutral-200 bg-white/95 font-sans text-zinc-900 backdrop-blur"
        data-testid="b2c-starter-header"
      >
        <div className={`${SHELL_CONTENT_CLASS} flex items-center justify-between gap-4 py-3 lg:py-4`}>
          <div className="flex min-w-0 items-center gap-4 lg:gap-8">
            <button type="button" onClick={navigateToHome} className="flex items-center gap-3 text-left">
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-neutral-50 text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-700">
                {brandName.slice(0, 2).toUpperCase()}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium uppercase tracking-[0.28em] text-zinc-900">
                  {brandName}
                </span>
                <span className="block truncate text-[11px] uppercase tracking-[0.2em] text-neutral-500">
                  B2C starter storefront
                </span>
              </span>
            </button>

            <nav className="hidden items-center gap-5 lg:flex" aria-label="Store navigation">
              <button type="button" onClick={navigateToStore} className={shellLinkClass()}>
                All products
              </button>
              {primaryCategories.map((category) => (
                <button
                  key={category.id}
                  type="button"
                  onClick={() => navigateToCategory(category.handle)}
                  className={shellLinkClass()}
                >
                  {category.name}
                </button>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            <button
              type="button"
              onClick={navigateToAccount}
              className="hidden rounded-full border border-neutral-200 bg-white px-4 py-2 text-sm text-zinc-900 transition hover:bg-neutral-50 sm:inline-flex"
            >
              {accountLabel}
            </button>
            <button
              type="button"
              onClick={navigateToCart}
              className="relative inline-flex items-center gap-2 rounded-full border border-neutral-200 bg-white px-3 py-2 text-sm text-zinc-900 transition hover:bg-neutral-50"
            >
              <span className="hidden sm:inline">Cart</span>
              <span className="inline-flex min-w-[1.5rem] items-center justify-center rounded-full bg-zinc-900 px-1.5 py-0.5 text-[11px] font-medium text-white">
                {cartCount}
              </span>
            </button>
            <button
              type="button"
              onClick={() => setMenuOpen((open) => !open)}
              className="inline-flex items-center justify-center rounded-full border border-neutral-200 p-2 text-zinc-900 transition hover:bg-neutral-50 lg:hidden"
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
          </div>
        </div>

        {menuOpen ? (
          <div className="border-t border-neutral-200 bg-white px-4 py-3 font-sans lg:hidden">
            <nav className="flex flex-col gap-2" aria-label="Mobile store navigation">
              <button
                type="button"
                onClick={() => {
                  navigateToStore();
                  setMenuOpen(false);
                }}
                className="rounded-xl px-3 py-2 text-left text-sm text-zinc-700 transition hover:bg-neutral-50 hover:text-zinc-900"
              >
                All products
              </button>
              {primaryCategories.map((category) => (
                <button
                  key={category.id}
                  type="button"
                  onClick={() => {
                    navigateToCategory(category.handle);
                    setMenuOpen(false);
                  }}
                  className="rounded-xl px-3 py-2 text-left text-sm text-zinc-700 transition hover:bg-neutral-50 hover:text-zinc-900"
                >
                  {category.name}
                </button>
              ))}
              <button
                type="button"
                onClick={() => {
                  navigateToAccount();
                  setMenuOpen(false);
                }}
                className="rounded-xl px-3 py-2 text-left text-sm text-zinc-700 transition hover:bg-neutral-50 hover:text-zinc-900"
              >
                {accountLabel}
              </button>
            </nav>
          </div>
        ) : null}
      </header>

      <div className="flex-1">{children}</div>

      <footer
        className="border-t border-neutral-200 bg-[#faf7f2] font-sans text-zinc-900"
        data-testid="b2c-starter-footer"
      >
        <div className={`${SHELL_CONTENT_CLASS} py-14 lg:py-20`}>
          <div className="grid gap-10 lg:grid-cols-[minmax(0,1.2fr)_repeat(3,minmax(0,1fr))]">
            <div className="max-w-sm">
              <p className="text-xs uppercase tracking-[0.28em] text-neutral-500">{brandName}</p>
              <h2 className="mt-4 text-3xl font-normal tracking-[-0.04em] text-zinc-900">
                Live Medusa storefront pages with cart, checkout, and customer account flows.
              </h2>
              <p className="mt-4 text-sm leading-7 text-neutral-600">
                Browse products, manage your cart, and move through the full starter experience without dropping back into the editor.
              </p>
            </div>

            <div>
              <h3 className="text-xs font-medium uppercase tracking-[0.24em] text-neutral-500">Categories</h3>
              <ul className="mt-5 space-y-3">
                {primaryCategories.length > 0 ? (
                  primaryCategories.map((category) => (
                    <li key={category.id}>
                      <button
                        type="button"
                        onClick={() => navigateToCategory(category.handle)}
                        className={shellLinkClass(true)}
                      >
                        {category.name}
                      </button>
                    </li>
                  ))
                ) : (
                  <li className="text-sm text-neutral-500">Categories appear when catalog data is available.</li>
                )}
              </ul>
            </div>

            <div>
              <h3 className="text-xs font-medium uppercase tracking-[0.24em] text-neutral-500">Collections</h3>
              <ul className="mt-5 space-y-3">
                {featuredCollections.length > 0 ? (
                  featuredCollections.map((collection) => (
                    <li key={collection.id}>
                      <button
                        type="button"
                        onClick={() => navigateToCollection(collection.handle)}
                        className={shellLinkClass(true)}
                      >
                        {collection.title}
                      </button>
                    </li>
                  ))
                ) : (
                  <li className="text-sm text-neutral-500">Collections appear after products are merchandised in Medusa.</li>
                )}
              </ul>
            </div>

            <div>
              <h3 className="text-xs font-medium uppercase tracking-[0.24em] text-neutral-500">Pages</h3>
              <ul className="mt-5 space-y-3">
                <li>
                  <button type="button" onClick={navigateToHome} className={shellLinkClass(true)}>
                    Home
                  </button>
                </li>
                <li>
                  <button type="button" onClick={navigateToStore} className={shellLinkClass(true)}>
                    Catalog
                  </button>
                </li>
                <li>
                  <button type="button" onClick={navigateToCart} className={shellLinkClass(true)}>
                    Cart
                  </button>
                </li>
                <li>
                  <button type="button" onClick={navigateToAccount} className={shellLinkClass(true)}>
                    Account
                  </button>
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-12 flex flex-col gap-3 border-t border-neutral-200 pt-6 text-xs uppercase tracking-[0.2em] text-neutral-500 sm:flex-row sm:items-center sm:justify-between">
            <span>© {new Date().getFullYear()} {brandName}</span>
            <span>Powered by Medusa B2C starter</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
