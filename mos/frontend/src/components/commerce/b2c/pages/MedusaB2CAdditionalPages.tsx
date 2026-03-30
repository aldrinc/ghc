import {
  useEffect,
  useMemo,
  useState,
  useCallback,
  type CSSProperties,
  type ReactNode,
} from 'react';
import {
  CardElement,
  Elements,
  useElements,
  useStripe,
} from '@stripe/react-stripe-js';
import {
  loadStripe,
  type Stripe,
  type StripeCardElementOptions,
  type StripeElementsOptions,
} from '@stripe/stripe-js';
import { useLocation, useSearchParams } from 'react-router-dom';
import { useFunnelRuntime } from '@/funnels/puckConfig';
import {
  buildPublicFunnelPath,
  resolvePublicApiBaseUrl,
} from '@/funnels/runtimeRouting';
import { MarkdownViewer } from '@/components/ui/MarkdownViewer';
import { getMedusaRuntimeConfig } from '@/lib/medusa';
import { useB2CRuntime } from '../B2CRuntimeProvider';
import {
  resolveB2CActionRadius,
  resolveB2CBodyFont,
  resolveB2CHeadingFont,
  resolveB2CPillRadius,
  resolveB2CSurfaceRadius,
  useB2CCTATheme,
  useB2CTheme,
} from '../useB2CTheme';
import type {
  MedusaCart,
  MedusaCartAddress,
  MedusaCartLineItem,
  MedusaCustomer,
  MedusaCustomerAddress,
  MedusaOrder,
  MedusaPaymentCollection,
  MedusaPaymentProvider,
  MedusaProduct,
  MedusaShippingOption,
} from '@/types/commerce';
import { B2CStarterShell } from './B2CStarterShell';
import { resolveB2CSitePath } from './sitePath';
import {
  CatalogPagination,
  CatalogSortSelect,
  PRICE_SORT_FETCH_LIMIT,
  PRODUCTS_PER_PAGE,
  SkeletonProductGrid,
  StoreProductCard,
  StorefrontEmptyState,
  StorefrontNotFoundState,
  normalizeCatalogSort,
  sortCatalogProducts,
  type CatalogSortValue,
} from './storefrontPrimitives';

const publicApiBaseUrl = resolvePublicApiBaseUrl();

function useB2CPageTheme() {
  const { tokens, isThemed } = useB2CTheme();
  const ctaTheme = useB2CCTATheme();

  return useMemo(() => {
    const colorBackground = tokens.colorBackground || '#ffffff';
    const colorBackgroundAlt =
      tokens.colorBackgroundAlt || tokens.colorBackground || '#ffffff';
    const colorText = tokens.colorText || '#111827';
    const colorTextMuted = tokens.colorTextMuted || 'rgba(17, 24, 39, 0.72)';
    const colorBorder = tokens.colorBorder || 'rgba(17, 24, 39, 0.22)';
    const colorPrimary = tokens.colorPrimary || '#111827';
    const colorPrimaryText = tokens.colorPrimaryText || '#ffffff';
    const radiusMedium = resolveB2CActionRadius(tokens);
    const radiusLarge = resolveB2CSurfaceRadius(tokens);
    const radiusFull = resolveB2CPillRadius(tokens);
    const bodyFontFamily = resolveB2CBodyFont(tokens);
    const headingFontFamily = resolveB2CHeadingFont(tokens);

    const pageStyle: CSSProperties = {
      backgroundColor: colorBackground,
      color: colorText,
      fontFamily: bodyFontFamily,
    };
    const surfaceStyle: CSSProperties = {
      backgroundColor: colorBackgroundAlt,
      borderColor: colorBorder,
      borderRadius: radiusLarge,
      boxShadow: 'none',
    };
    const headingStyle: CSSProperties = {
      color: colorText,
      fontFamily: headingFontFamily,
      letterSpacing: isThemed ? undefined : 'normal',
    };
    const textStyle: CSSProperties = {
      color: colorText,
    };
    const mutedTextStyle: CSSProperties = {
      color: colorTextMuted,
    };
    const labelStyle: CSSProperties = {
      color: colorText,
      fontFamily: bodyFontFamily,
    };
    const borderStyle: CSSProperties = {
      borderColor: colorBorder,
    };
    const inputStyle: CSSProperties = {
      backgroundColor: colorBackground,
      borderColor: colorBorder,
      color: colorText,
      borderRadius: radiusMedium,
      fontFamily: bodyFontFamily,
      boxShadow: 'none',
    };
    const primaryButtonStyle: CSSProperties = {
      ...ctaTheme.style,
      backgroundColor: ctaTheme.style?.backgroundColor || colorPrimary,
      borderColor: ctaTheme.style?.borderColor || colorPrimary,
      color: ctaTheme.style?.color || colorPrimaryText,
      borderRadius: ctaTheme.style?.borderRadius || radiusMedium,
      fontFamily: bodyFontFamily,
    };
    const primaryPillStyle: CSSProperties = {
      ...primaryButtonStyle,
      borderRadius:
        tokens.radiusFull || ctaTheme.style?.borderRadius || radiusFull,
    };
    const secondaryButtonStyle: CSSProperties = {
      backgroundColor: colorBackground,
      borderColor: colorBorder,
      color: colorText,
      borderRadius: radiusMedium,
      fontFamily: bodyFontFamily,
      boxShadow: 'none',
    };
    const secondaryPillStyle: CSSProperties = {
      ...secondaryButtonStyle,
      borderRadius: tokens.radiusFull || radiusMedium,
    };

    return {
      isThemed,
      tokens,
      pageStyle,
      surfaceStyle,
      headingStyle,
      textStyle,
      mutedTextStyle,
      labelStyle,
      borderStyle,
      inputStyle,
      primaryButtonStyle,
      primaryPillStyle,
      secondaryButtonStyle,
      secondaryPillStyle,
    };
  }, [ctaTheme.style, isThemed, tokens]);
}

function PageShell({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  const theme = useB2CPageTheme();

  return (
    <B2CStarterShell>
      <main
        className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8"
        style={theme.pageStyle}
      >
        <header
          className="space-y-2 border-b border-border pb-4"
          style={theme.borderStyle}
        >
          <h1
            className="text-3xl font-medium text-content"
            style={theme.headingStyle}
          >
            {title}
          </h1>
          {description ? (
            <p
              className="max-w-2xl text-sm text-content-muted"
              style={theme.mutedTextStyle}
            >
              {description}
            </p>
          ) : null}
        </header>
        {children}
      </main>
    </B2CStarterShell>
  );
}

function formatPrice(amount?: number, currencyCode: string = 'usd') {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currencyCode.toUpperCase(),
  }).format((amount || 0) / 100);
}

function formatDate(dateString?: string): string {
  if (!dateString) return '—';
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function useResolvedSitePath() {
  const location = useLocation();
  const runtime = useFunnelRuntime();
  return useMemo(
    () => resolveB2CSitePath(location.pathname, runtime),
    [location.pathname, runtime],
  );
}

type B2CPolicyPageKey =
  | 'privacy_policy'
  | 'terms_of_service'
  | 'returns_refunds_policy'
  | 'shipping_policy'
  | 'contact_support';

type B2CPolicyPageResponse = {
  pageKey: B2CPolicyPageKey;
  title: string;
  markdown: string;
};

async function parseB2CPublicError(resp: Response): Promise<string> {
  try {
    const raw = (await resp.clone().json()) as {
      detail?: unknown;
      message?: unknown;
    };
    if (typeof raw.detail === 'string' && raw.detail.trim()) {
      return raw.detail;
    }
    if (typeof raw.message === 'string' && raw.message.trim()) {
      return raw.message;
    }
  } catch {
    const text = await resp.text();
    if (text.trim()) {
      return text;
    }
  }
  return resp.statusText || 'Request failed';
}

function formatCartItemVariant(item: MedusaCartLineItem): string | null {
  if (item.variant_title?.trim()) {
    return item.variant_title.trim();
  }

  if (Array.isArray(item.variant?.options)) {
    const entries = item.variant.options
      .map((option) => {
        const value = option?.value?.trim();
        const title = option?.option?.title?.trim();
        if (!value) return null;
        return title ? `${title}: ${value}` : value;
      })
      .filter((value): value is string => Boolean(value));
    if (entries.length > 0) {
      return entries.join(' / ');
    }
  }

  if (item.variant?.title?.trim()) {
    return item.variant.title.trim();
  }

  return null;
}

function resolveFreeShippingThreshold(
  options: MedusaShippingOption[],
): number | null {
  const freeOption = options.find(
    (option) =>
      option.price_type === 'flat' &&
      typeof option.amount === 'number' &&
      option.amount <= 0,
  );

  if (!freeOption?.requirements?.length) {
    return null;
  }

  for (const requirement of freeOption.requirements) {
    const requirementType = `${requirement.type || ''} ${requirement.field || ''}`.toLowerCase();
    const amount =
      typeof requirement.amount === 'number'
        ? requirement.amount
        : typeof requirement.value === 'number'
          ? requirement.value
          : null;

    if (
      amount !== null &&
      (requirementType.includes('subtotal') ||
        requirementType.includes('price') ||
        requirementType.includes('total'))
    ) {
      return amount;
    }
  }

  return null;
}

function getDefaultBillingAddress(
  customer: MedusaCustomer | null | undefined,
): MedusaCustomerAddress | null {
  if (!customer?.addresses?.length) {
    return null;
  }

  return (
    customer.addresses.find((address) => address.is_default_billing) ||
    customer.addresses[0] ||
    null
  );
}

function calculateProfileCompletion(customer: MedusaCustomer | null | undefined) {
  const billingAddress = getDefaultBillingAddress(customer);
  const checks = [
    Boolean(customer?.email?.trim()),
    Boolean(customer?.first_name?.trim()),
    Boolean(customer?.last_name?.trim()),
    Boolean(customer?.phone?.trim()),
    Boolean(billingAddress?.address_1?.trim()),
  ];
  const completed = checks.filter(Boolean).length;
  return Math.round((completed / checks.length) * 100);
}

function AccountPageSkeleton({ title }: { title: string }) {
  const theme = useB2CPageTheme();
  const blockStyle: CSSProperties = {
    backgroundColor:
      theme.tokens.colorBackgroundAlt || 'rgba(17, 24, 39, 0.08)',
    borderRadius: theme.tokens.radiusMedium || '16px',
  };

  return (
    <PageShell title={title} description="Loading account details...">
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <div className="animate-pulse space-y-4">
          <div className="h-24 w-full" style={blockStyle} />
          <div className="h-12 w-full" style={blockStyle} />
          <div className="h-12 w-full" style={blockStyle} />
          <div className="h-12 w-full" style={blockStyle} />
        </div>
        <div className="animate-pulse space-y-4">
          <div className="h-32 w-full" style={blockStyle} />
          <div className="h-48 w-full" style={blockStyle} />
        </div>
      </div>
    </PageShell>
  );
}

function CatalogResultsSection({
  filterOptions,
  emptyTitle,
  emptyDescription,
}: {
  filterOptions: {
    collectionId?: string[];
    categoryId?: string[];
  };
  emptyTitle: string;
  emptyDescription: string;
}) {
  const { products, productsLoading, refreshProducts, navigateToProduct } =
    useB2CRuntime();
  const [searchParams, setSearchParams] = useSearchParams();
  const [catalogCount, setCatalogCount] = useState(0);
  const [priceSortLimited, setPriceSortLimited] = useState(false);
  const currentPage = Math.max(
    1,
    Number(searchParams.get('page') || '1') || 1,
  );
  const currentSort = normalizeCatalogSort(searchParams.get('sort'));
  const filterKey = useMemo(() => JSON.stringify(filterOptions), [filterOptions]);

  const updateCatalogParams = useCallback(
    (next: { page?: number; sort?: CatalogSortValue }) => {
      const params = new URLSearchParams(searchParams);
      const nextPage = next.page ?? currentPage;
      const nextSort = next.sort ?? currentSort;

      if (nextSort === 'created_at') {
        params.delete('sort');
      } else {
        params.set('sort', nextSort);
      }

      if (nextPage <= 1) {
        params.delete('page');
      } else {
        params.set('page', String(nextPage));
      }

      setSearchParams(params);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },
    [currentPage, currentSort, searchParams, setSearchParams],
  );

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      const requestLimit =
        currentSort === 'created_at'
          ? PRODUCTS_PER_PAGE
          : PRICE_SORT_FETCH_LIMIT;
      const requestOffset =
        currentSort === 'created_at'
          ? (currentPage - 1) * PRODUCTS_PER_PAGE
          : 0;

      const result = await refreshProducts({
        ...filterOptions,
        limit: requestLimit,
        offset: requestOffset,
      });

      if (cancelled || !result) {
        if (!cancelled) {
          setCatalogCount(0);
          setPriceSortLimited(false);
        }
        return;
      }

      const nextCount =
        currentSort === 'created_at'
          ? result.count
          : Math.min(result.count, result.products.length);
      const totalPages = Math.max(
        1,
        Math.ceil(nextCount / PRODUCTS_PER_PAGE),
      );

      setCatalogCount(nextCount);
      setPriceSortLimited(
        currentSort !== 'created_at' && result.count > result.products.length,
      );

      if (currentPage > totalPages) {
        updateCatalogParams({ page: totalPages });
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [currentPage, currentSort, filterKey, filterOptions, refreshProducts, updateCatalogParams]);

  const sortedProducts = useMemo(() => {
    if (currentSort === 'created_at') {
      return products;
    }
    return sortCatalogProducts(products, currentSort);
  }, [currentSort, products]);

  const visibleProducts = useMemo(() => {
    if (currentSort === 'created_at') {
      return products;
    }

    const start = (currentPage - 1) * PRODUCTS_PER_PAGE;
    return sortedProducts.slice(start, start + PRODUCTS_PER_PAGE);
  }, [currentPage, currentSort, products, sortedProducts]);

  const totalPages = Math.max(1, Math.ceil(catalogCount / PRODUCTS_PER_PAGE));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-end">
        <CatalogSortSelect
          value={currentSort}
          onChange={(value) => updateCatalogParams({ sort: value, page: 1 })}
        />
      </div>

      {priceSortLimited ? (
        <p className="text-sm text-content-muted">
          Price sorting is currently limited to the first{' '}
          {PRICE_SORT_FETCH_LIMIT} products returned by Medusa.
        </p>
      ) : null}

      {productsLoading ? (
        <SkeletonProductGrid />
      ) : visibleProducts.length === 0 ? (
        <StorefrontEmptyState
          title={emptyTitle}
          description={emptyDescription}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-3">
            {visibleProducts.map((product: MedusaProduct) => (
              <StoreProductCard
                key={product.id}
                product={product}
                onClick={() => navigateToProduct(product.handle)}
              />
            ))}
          </div>
          <CatalogPagination
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={(page) => updateCatalogParams({ page })}
          />
        </>
      )}
    </div>
  );
}

export function MedusaB2CPolicyPage({
  pageKey,
  pageTitle,
  description,
}: {
  pageKey: B2CPolicyPageKey;
  pageTitle?: string;
  description?: string;
}) {
  const funnelRuntime = useFunnelRuntime();
  const { countryCode } = useB2CRuntime();
  const theme = useB2CPageTheme();
  const productSlug = funnelRuntime?.productSlug || null;
  const funnelSlug = funnelRuntime?.funnelSlug || null;
  const homePath = funnelRuntime
    ? buildPublicFunnelPath({
        productSlug: funnelRuntime.productSlug,
        funnelSlug: funnelRuntime.funnelSlug,
        bundleMode: funnelRuntime.bundleMode || false,
        sitePath: countryCode || 'us',
      })
    : null;
  const [policyPage, setPolicyPage] = useState<B2CPolicyPageResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!productSlug || !funnelSlug || !homePath) {
      return;
    }

    const controller = new AbortController();
    const websiteUrl = new URL(homePath, window.location.origin).toString();
    const query = new URLSearchParams({ website_url: websiteUrl });
    const url = `${publicApiBaseUrl}/public/funnels/${encodeURIComponent(productSlug)}/${encodeURIComponent(funnelSlug)}/policy-pages/${encodeURIComponent(pageKey)}?${query.toString()}`;

    setLoading(true);
    setError(null);
    setPolicyPage(null);

    fetch(url, { signal: controller.signal })
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(await parseB2CPublicError(resp));
        }
        return (await resp.json()) as B2CPolicyPageResponse;
      })
      .then((payload) => {
        setPolicyPage(payload);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(
          err instanceof Error ? err.message : 'Unable to load policy page',
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [funnelSlug, homePath, pageKey, productSlug]);

  if (!funnelRuntime) {
    throw new Error('MedusaB2CPolicyPage requires funnel runtime context.');
  }

  if (!homePath) {
    throw new Error(
      'MedusaB2CPolicyPage requires a resolvable storefront home route.',
    );
  }

  return (
    <PageShell
      title={policyPage?.title || pageTitle || 'Policy Page'}
      description={description}
    >
      {loading ? (
        <div
          className="rounded-[28px] border border-border bg-surface px-5 py-5 text-sm text-content-muted sm:px-6"
          style={theme.surfaceStyle}
        >
          Loading {pageTitle || 'policy page'}...
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="rounded-[28px] border border-danger/30 bg-danger/10 px-5 py-5 text-sm text-danger sm:px-6"
        >
          Unable to load {pageTitle || 'policy page'}. {error}
        </div>
      ) : null}

      {policyPage ? (
        <div
          className="rounded-[28px] border border-border bg-surface px-5 py-6 sm:px-6"
          style={theme.surfaceStyle}
        >
          <MarkdownViewer
            content={policyPage.markdown}
            className="max-w-none px-0"
          />
        </div>
      ) : null}
    </PageShell>
  );
}

// =============================================================================
// Login/Register Shell
// =============================================================================

type AuthView = 'login' | 'register';

function LoginForm({ onSwitch }: { onSwitch: () => void }) {
  const { login, refreshCustomer, navigateToAccount } = useB2CRuntime();
  const theme = useB2CPageTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      setLoading(true);
      try {
        await login(email, password);
        await refreshCustomer();
        navigateToAccount();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Login failed');
      } finally {
        setLoading(false);
      }
    },
    [email, password, login, refreshCustomer, navigateToAccount],
  );

  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="space-y-2 text-center">
        <h2
          className="text-2xl font-semibold text-content"
          style={theme.headingStyle}
        >
          Welcome back
        </h2>
        <p className="text-sm text-content-muted" style={theme.mutedTextStyle}>
          Sign in to access your account and orders.
        </p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-content px-4 py-2 text-sm font-medium text-white hover:bg-content/80 disabled:opacity-50"
          style={theme.primaryButtonStyle}
        >
          {loading ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
      <p
        className="text-center text-sm text-content-muted"
        style={theme.mutedTextStyle}
      >
        Not a member?{' '}
        <button
          onClick={onSwitch}
          className="font-medium text-content underline"
          style={theme.textStyle}
        >
          Join us
        </button>
      </p>
    </div>
  );
}

function RegisterForm({ onSwitch }: { onSwitch: () => void }) {
  const { register, login, refreshCustomer, navigateToAccount } =
    useB2CRuntime();
  const theme = useB2CPageTheme();
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    password: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      setLoading(true);
      try {
        await register(
          form.email,
          form.password,
          form.firstName,
          form.lastName,
          form.phone,
        );
        // Auto-login after registration
        await login(form.email, form.password);
        await refreshCustomer();
        navigateToAccount();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Registration failed');
      } finally {
        setLoading(false);
      }
    },
    [form, register, login, refreshCustomer, navigateToAccount],
  );

  return (
    <div className="w-full max-w-sm space-y-6">
      <div className="space-y-2 text-center">
        <h2
          className="text-2xl font-semibold text-content"
          style={theme.headingStyle}
        >
          Create an account
        </h2>
        <p className="text-sm text-content-muted" style={theme.mutedTextStyle}>
          Join us for an enhanced shopping experience.
        </p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label
              className="block text-sm font-medium text-content-muted"
              style={theme.labelStyle}
            >
              First name
            </label>
            <input
              type="text"
              value={form.firstName}
              onChange={(e) =>
                setForm((f) => ({ ...f, firstName: e.target.value }))
              }
              required
              className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
              style={theme.inputStyle}
            />
          </div>
          <div>
            <label
              className="block text-sm font-medium text-content-muted"
              style={theme.labelStyle}
            >
              Last name
            </label>
            <input
              type="text"
              value={form.lastName}
              onChange={(e) =>
                setForm((f) => ({ ...f, lastName: e.target.value }))
              }
              required
              className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
              style={theme.inputStyle}
            />
          </div>
        </div>
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            Email
          </label>
          <input
            type="email"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            required
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            Phone
          </label>
          <input
            type="tel"
            value={form.phone}
            onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            Password
          </label>
          <input
            type="password"
            value={form.password}
            onChange={(e) =>
              setForm((f) => ({ ...f, password: e.target.value }))
            }
            required
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-content px-4 py-2 text-sm font-medium text-white hover:bg-content/80 disabled:opacity-50"
          style={theme.primaryButtonStyle}
        >
          {loading ? 'Creating account...' : 'Create account'}
        </button>
      </form>
      <p
        className="text-center text-sm text-content-muted"
        style={theme.mutedTextStyle}
      >
        Already a member?{' '}
        <button
          onClick={onSwitch}
          className="font-medium text-content underline"
          style={theme.textStyle}
        >
          Sign in
        </button>
      </p>
    </div>
  );
}

function AuthShell() {
  const [view, setView] = useState<AuthView>('login');
  return (
    <PageShell
      title="Account"
      description="Sign in or create an account to access your orders and profile."
    >
      <div className="flex justify-center py-8">
        {view === 'login' ? (
          <LoginForm onSwitch={() => setView('register')} />
        ) : (
          <RegisterForm onSwitch={() => setView('login')} />
        )}
      </div>
    </PageShell>
  );
}

function AccountErrorShell({ message }: { message: string }) {
  return (
    <PageShell
      title="Account unavailable"
      description="A customer session exists, but the storefront could not load account data from Medusa."
    >
      <div className="max-w-2xl rounded-xl border border-danger/30 bg-danger/10 p-6">
        <p className="font-medium text-danger">
          Account data could not be loaded.
        </p>
        <p className="mt-2 text-sm text-danger">
          This is a storefront or backend failure, not a sign-in problem. Fix
          the customer or order API and reload this page.
        </p>
        <p className="mt-4 text-sm text-danger">{message}</p>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Account Navigation
// =============================================================================

function AccountNav({
  active,
}: {
  active: 'dashboard' | 'profile' | 'addresses' | 'orders';
}) {
  const {
    navigateToAccount,
    navigateToAccountProfile,
    navigateToAccountAddresses,
    navigateToAccountOrders,
    customer,
    logout,
    navigateToHome,
  } = useB2CRuntime();
  const theme = useB2CPageTheme();
  const navItems = [
    { id: 'dashboard', label: 'Overview', onClick: navigateToAccount },
    { id: 'profile', label: 'Profile', onClick: navigateToAccountProfile },
    {
      id: 'addresses',
      label: 'Addresses',
      onClick: navigateToAccountAddresses,
    },
    { id: 'orders', label: 'Orders', onClick: navigateToAccountOrders },
  ] as const;

  const handleLogout = useCallback(async () => {
    await logout();
    navigateToHome();
  }, [logout, navigateToHome]);

  return (
    <div className="space-y-6">
      <div
        className="rounded-xl border border-border p-4"
        style={theme.surfaceStyle}
      >
        <p className="font-medium text-content" style={theme.headingStyle}>
          {[customer?.first_name, customer?.last_name]
            .filter(Boolean)
            .join(' ') || 'Account'}
        </p>
        <p className="text-sm text-content-muted" style={theme.mutedTextStyle}>
          {customer?.email}
        </p>
      </div>
      <nav className="space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={item.onClick}
            className={`block w-full rounded-lg px-3 py-2 text-left text-sm font-medium ${
              active === item.id
                ? 'bg-surface-2 text-content'
                : 'text-content-muted hover:bg-surface-hover'
            }`}
            style={
              active === item.id
                ? theme.primaryButtonStyle
                : theme.secondaryButtonStyle
            }
          >
            {item.label}
          </button>
        ))}
        <button
          onClick={handleLogout}
          className="block w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-danger hover:bg-danger/10"
        >
          Log out
        </button>
      </nav>
    </div>
  );
}

// =============================================================================
// Account Dashboard
// =============================================================================

export function MedusaB2CAccountDashboardPage() {
  const {
    customer,
    customerLoading,
    isAuthenticated,
    customerError,
    navigateToAccountProfile,
    navigateToAccountOrders,
  } = useB2CRuntime();
  const theme = useB2CPageTheme();
  const profileCompletion = calculateProfileCompletion(customer);

  if (customerLoading && !customer && !customerError) {
    return <AccountPageSkeleton title="Account" />;
  }
  if (customerError) return <AccountErrorShell message={customerError} />;
  if (!isAuthenticated) return <AuthShell />;

  return (
    <PageShell
      title="Account"
      description="Manage your account and view your orders."
    >
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <AccountNav active="dashboard" />
        <div className="space-y-6">
          <div
            className="rounded-xl border border-border p-6"
            style={theme.surfaceStyle}
          >
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <h2
                  className="text-lg font-medium text-content"
                  style={theme.headingStyle}
                >
                  Welcome back
                </h2>
                <p
                  className="mt-2 text-sm text-content-muted"
                  style={theme.mutedTextStyle}
                >
                  You&apos;re signed in as {customer?.email}
                </p>
              </div>
              <div className="min-w-[12rem]">
                <div className="flex items-center justify-between text-sm">
                  <span style={theme.mutedTextStyle}>Profile completion</span>
                  <span style={theme.textStyle}>{profileCompletion}%</span>
                </div>
                <div
                  className="mt-2 h-2 overflow-hidden rounded-full bg-border"
                  style={{
                    backgroundColor:
                      theme.tokens.colorBorder || 'rgba(17, 24, 39, 0.12)',
                  }}
                >
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${profileCompletion}%`,
                      backgroundColor: theme.tokens.colorPrimary || '#111827',
                    }}
                  />
                </div>
                {profileCompletion < 100 ? (
                  <button
                    type="button"
                    onClick={() => navigateToAccountProfile()}
                    className="mt-3 text-sm font-medium underline"
                    style={theme.textStyle}
                  >
                    Complete your profile
                  </button>
                ) : null}
              </div>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div
              className="rounded-xl border border-border p-6"
              style={theme.surfaceStyle}
            >
              <h3
                className="font-medium text-content"
                style={theme.headingStyle}
              >
                Profile
              </h3>
              <p
                className="mt-1 text-sm text-content-muted"
                style={theme.mutedTextStyle}
              >
                Manage your personal information.
              </p>
              <button
                type="button"
                onClick={() => navigateToAccountProfile()}
                className="mt-4 text-sm font-medium underline"
                style={theme.textStyle}
              >
                Open profile
              </button>
            </div>
            <div
              className="rounded-xl border border-border p-6"
              style={theme.surfaceStyle}
            >
              <h3
                className="font-medium text-content"
                style={theme.headingStyle}
              >
                Orders
              </h3>
              <p
                className="mt-1 text-sm text-content-muted"
                style={theme.mutedTextStyle}
              >
                View and track your orders.
              </p>
              <button
                type="button"
                onClick={() => navigateToAccountOrders()}
                className="mt-4 text-sm font-medium underline"
                style={theme.textStyle}
              >
                View orders
              </button>
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Profile Page
// =============================================================================

export function MedusaB2CAccountProfilePage() {
  const {
    customer,
    isAuthenticated,
    customerError,
    updateCustomer,
    requestPasswordReset,
    customerLoading,
  } = useB2CRuntime();
  const theme = useB2CPageTheme();
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [passwordResetError, setPasswordResetError] = useState<string | null>(
    null,
  );
  const [passwordResetSuccess, setPasswordResetSuccess] = useState(false);
  const [passwordResetLoading, setPasswordResetLoading] = useState(false);

  useEffect(() => {
    if (customer) {
      setForm({
        firstName: customer.first_name || '',
        lastName: customer.last_name || '',
        email: customer.email || '',
        phone: customer.phone || '',
      });
    }
  }, [customer]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      setSuccess(false);
      try {
        await updateCustomer({
          first_name: form.firstName,
          last_name: form.lastName,
          email: form.email,
          phone: form.phone,
        });
        setSuccess(true);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Failed to update profile',
        );
      }
    },
    [form, updateCustomer],
  );

  const handlePasswordReset = useCallback(async () => {
    setPasswordResetError(null);
    setPasswordResetSuccess(false);
    setPasswordResetLoading(true);
    try {
      await requestPasswordReset(form.email || customer?.email || undefined);
      setPasswordResetSuccess(true);
    } catch (err) {
      setPasswordResetError(
        err instanceof Error ? err.message : 'Failed to send reset link',
      );
    } finally {
      setPasswordResetLoading(false);
    }
  }, [customer?.email, form.email, requestPasswordReset]);

  if (customerLoading && !customer && !customerError) {
    return <AccountPageSkeleton title="Profile" />;
  }
  if (customerError) return <AccountErrorShell message={customerError} />;
  if (!isAuthenticated) return <AuthShell />;

  return (
    <PageShell title="Profile" description="Manage your personal information.">
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <AccountNav active="profile" />
        <div className="space-y-8">
          <form onSubmit={handleSubmit} className="max-w-md space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label
                  className="block text-sm font-medium text-content-muted"
                  style={theme.labelStyle}
                >
                  First name
                </label>
                <input
                  type="text"
                  value={form.firstName}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, firstName: e.target.value }))
                  }
                  className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
                  style={theme.inputStyle}
                />
              </div>
              <div>
                <label
                  className="block text-sm font-medium text-content-muted"
                  style={theme.labelStyle}
                >
                  Last name
                </label>
                <input
                  type="text"
                  value={form.lastName}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, lastName: e.target.value }))
                  }
                  className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
                  style={theme.inputStyle}
                />
              </div>
            </div>
            <div>
              <label
                className="block text-sm font-medium text-content-muted"
                style={theme.labelStyle}
              >
                Email
              </label>
              <input
                type="email"
                value={form.email}
                onChange={(e) =>
                  setForm((f) => ({ ...f, email: e.target.value }))
                }
                className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
                style={theme.inputStyle}
              />
            </div>
            <div>
              <label
                className="block text-sm font-medium text-content-muted"
                style={theme.labelStyle}
              >
                Phone
              </label>
              <input
                type="tel"
                value={form.phone}
                onChange={(e) =>
                  setForm((f) => ({ ...f, phone: e.target.value }))
                }
                className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
                style={theme.inputStyle}
              />
            </div>
            {error ? <p className="text-sm text-danger">{error}</p> : null}
            {success ? (
              <p className="text-sm text-success">
                Profile updated successfully.
              </p>
            ) : null}
            <button
              type="submit"
              disabled={customerLoading}
              className="rounded-lg bg-content px-4 py-2 text-sm font-medium text-white hover:bg-content/80 disabled:opacity-50"
              style={theme.primaryButtonStyle}
            >
              {customerLoading ? 'Saving...' : 'Save changes'}
            </button>
          </form>

          <div
            className="max-w-md rounded-xl border border-border p-6"
            style={theme.surfaceStyle}
          >
            <h2 className="text-lg font-medium" style={theme.headingStyle}>
              Password
            </h2>
            <p className="mt-2 text-sm" style={theme.mutedTextStyle}>
              Medusa handles customer password updates through a secure reset
              email. We&apos;ll send the reset link to {form.email || customer?.email}.
            </p>
            {passwordResetError ? (
              <p className="mt-4 text-sm text-danger">{passwordResetError}</p>
            ) : null}
            {passwordResetSuccess ? (
              <p className="mt-4 text-sm text-success">
                Reset link sent. Check your inbox to finish updating your
                password.
              </p>
            ) : null}
            <button
              type="button"
              onClick={() => void handlePasswordReset()}
              disabled={passwordResetLoading}
              className="mt-5 rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              style={theme.primaryButtonStyle}
            >
              {passwordResetLoading ? 'Sending...' : 'Email reset link'}
            </button>
          </div>
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Addresses Page
// =============================================================================

function AddressForm({
  address,
  onSave,
  onCancel,
  loading,
}: {
  address?: MedusaCustomerAddress;
  onSave: (data: {
    first_name?: string;
    last_name?: string;
    company?: string;
    address_1?: string;
    address_2?: string;
    city?: string;
    province?: string;
    postal_code?: string;
    country_code?: string;
    phone?: string;
  }) => void;
  onCancel: () => void;
  loading: boolean;
}) {
  const theme = useB2CPageTheme();
  const [form, setForm] = useState({
    first_name: address?.first_name || '',
    last_name: address?.last_name || '',
    company: address?.company || '',
    address_1: address?.address_1 || '',
    address_2: address?.address_2 || '',
    city: address?.city || '',
    province: address?.province || '',
    postal_code: address?.postal_code || '',
    country_code: address?.country_code || 'us',
    phone: address?.phone || '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(form);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-4 rounded-xl border border-border p-6"
      style={theme.surfaceStyle}
    >
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            First name
          </label>
          <input
            type="text"
            value={form.first_name}
            onChange={(e) =>
              setForm((f) => ({ ...f, first_name: e.target.value }))
            }
            required
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            Last name
          </label>
          <input
            type="text"
            value={form.last_name}
            onChange={(e) =>
              setForm((f) => ({ ...f, last_name: e.target.value }))
            }
            required
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
      </div>
      <div>
        <label
          className="block text-sm font-medium text-content-muted"
          style={theme.labelStyle}
        >
          Company (optional)
        </label>
        <input
          type="text"
          value={form.company}
          onChange={(e) => setForm((f) => ({ ...f, company: e.target.value }))}
          className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
          style={theme.inputStyle}
        />
      </div>
      <div>
        <label
          className="block text-sm font-medium text-content-muted"
          style={theme.labelStyle}
        >
          Address line 1
        </label>
        <input
          type="text"
          value={form.address_1}
          onChange={(e) =>
            setForm((f) => ({ ...f, address_1: e.target.value }))
          }
          required
          className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
          style={theme.inputStyle}
        />
      </div>
      <div>
        <label
          className="block text-sm font-medium text-content-muted"
          style={theme.labelStyle}
        >
          Address line 2 (optional)
        </label>
        <input
          type="text"
          value={form.address_2}
          onChange={(e) =>
            setForm((f) => ({ ...f, address_2: e.target.value }))
          }
          className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
          style={theme.inputStyle}
        />
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            City
          </label>
          <input
            type="text"
            value={form.city}
            onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
            required
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            Province/State
          </label>
          <input
            type="text"
            value={form.province}
            onChange={(e) =>
              setForm((f) => ({ ...f, province: e.target.value }))
            }
            required
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            Postal code
          </label>
          <input
            type="text"
            value={form.postal_code}
            onChange={(e) =>
              setForm((f) => ({ ...f, postal_code: e.target.value }))
            }
            required
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            Country code
          </label>
          <select
            value={form.country_code}
            onChange={(e) =>
              setForm((f) => ({ ...f, country_code: e.target.value }))
            }
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          >
            <option value="us">United States</option>
            <option value="ca">Canada</option>
            <option value="gb">United Kingdom</option>
            <option value="de">Germany</option>
            <option value="fr">France</option>
            <option value="au">Australia</option>
          </select>
        </div>
        <div>
          <label
            className="block text-sm font-medium text-content-muted"
            style={theme.labelStyle}
          >
            Phone
          </label>
          <input
            type="tel"
            value={form.phone}
            onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
            className="mt-1 block w-full rounded-lg border border-border px-3 py-2 text-sm focus:border-content focus:outline-none"
            style={theme.inputStyle}
          />
        </div>
      </div>
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-content px-4 py-2 text-sm font-medium text-white hover:bg-content/80 disabled:opacity-50"
          style={theme.primaryButtonStyle}
        >
          {loading ? 'Saving...' : address ? 'Update address' : 'Add address'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={loading}
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-content-muted hover:bg-surface-hover"
          style={theme.secondaryButtonStyle}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export function MedusaB2CAccountAddressesPage() {
  const {
    customer,
    isAuthenticated,
    customerError,
    addCustomerAddress,
    updateCustomerAddress,
    deleteCustomerAddress,
    customerLoading,
  } = useB2CRuntime();
  const theme = useB2CPageTheme();
  const [editingAddress, setEditingAddress] =
    useState<MedusaCustomerAddress | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAdd = useCallback(
    async (data: Parameters<typeof addCustomerAddress>[0]) => {
      setError(null);
      try {
        await addCustomerAddress(data);
        setIsAdding(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to add address');
      }
    },
    [addCustomerAddress],
  );

  const handleUpdate = useCallback(
    async (data: Parameters<typeof updateCustomerAddress>[1]) => {
      if (!editingAddress) return;
      setError(null);
      try {
        await updateCustomerAddress(editingAddress.id, data);
        setEditingAddress(null);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Failed to update address',
        );
      }
    },
    [editingAddress, updateCustomerAddress],
  );

  const handleDelete = useCallback(
    async (addressId: string) => {
      if (!confirm('Are you sure you want to delete this address?')) return;
      setError(null);
      try {
        await deleteCustomerAddress(addressId);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Failed to delete address',
        );
      }
    },
    [deleteCustomerAddress],
  );

  if (customerError) return <AccountErrorShell message={customerError} />;
  if (!isAuthenticated) return <AuthShell />;

  return (
    <PageShell
      title="Addresses"
      description="Manage your shipping and billing addresses."
    >
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <AccountNav active="addresses" />
        <div className="space-y-6">
          {error ? <p className="text-sm text-danger">{error}</p> : null}

          {isAdding ? (
            <AddressForm
              onSave={handleAdd}
              onCancel={() => setIsAdding(false)}
              loading={customerLoading}
            />
          ) : (
            <button
              onClick={() => setIsAdding(true)}
              className="w-full rounded-xl border-2 border-dashed border-border p-6 text-center text-sm font-medium text-content-muted hover:border-content hover:text-content"
              style={theme.surfaceStyle}
            >
              + Add new address
            </button>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            {customer?.addresses?.map((address) => (
              <div
                key={address.id}
                className="rounded-xl border border-border p-4"
                style={theme.surfaceStyle}
              >
                {editingAddress?.id === address.id ? (
                  <AddressForm
                    address={address}
                    onSave={handleUpdate}
                    onCancel={() => setEditingAddress(null)}
                    loading={customerLoading}
                  />
                ) : (
                  <>
                    <p
                      className="font-medium text-content"
                      style={theme.headingStyle}
                    >
                      {[address.first_name, address.last_name]
                        .filter(Boolean)
                        .join(' ') || 'Unnamed address'}
                    </p>
                    {address.company ? (
                      <p
                        className="text-sm text-content-muted"
                        style={theme.mutedTextStyle}
                      >
                        {address.company}
                      </p>
                    ) : null}
                    <p
                      className="text-sm text-content-muted"
                      style={theme.mutedTextStyle}
                    >
                      {address.address_1}
                    </p>
                    {address.address_2 ? (
                      <p
                        className="text-sm text-content-muted"
                        style={theme.mutedTextStyle}
                      >
                        {address.address_2}
                      </p>
                    ) : null}
                    <p
                      className="text-sm text-content-muted"
                      style={theme.mutedTextStyle}
                    >
                      {[address.city, address.province, address.postal_code]
                        .filter(Boolean)
                        .join(', ')}
                    </p>
                    <p
                      className="text-sm text-content-muted"
                      style={theme.mutedTextStyle}
                    >
                      {address.country_code?.toUpperCase()}
                    </p>
                    {address.phone ? (
                      <p
                        className="text-sm text-content-muted"
                        style={theme.mutedTextStyle}
                      >
                        {address.phone}
                      </p>
                    ) : null}
                    <div className="mt-4 flex gap-3">
                      <button
                        onClick={() => setEditingAddress(address)}
                        className="text-sm font-medium text-content underline"
                        style={theme.textStyle}
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(address.id)}
                        className="text-sm font-medium text-danger underline"
                      >
                        Delete
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>

          {!customer?.addresses?.length && !isAdding ? (
            <p className="text-center text-sm text-content-muted">
              No addresses saved yet.
            </p>
          ) : null}
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Orders Page
// =============================================================================

function OrderCard({ order }: { order: MedusaOrder }) {
  const { navigateToOrder } = useB2CRuntime();
  const theme = useB2CPageTheme();

  return (
    <div
      className="rounded-xl border border-border p-4"
      style={theme.surfaceStyle}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="font-medium text-content" style={theme.headingStyle}>
            Order #{order.display_id || order.id.slice(-8)}
          </p>
          <p className="text-sm text-content-muted" style={theme.mutedTextStyle}>
            {formatDate(order.created_at)}
          </p>
        </div>
        <div className="text-right">
          <p className="font-medium text-content" style={theme.headingStyle}>
            {formatPrice(order.total, order.currency_code)}
          </p>
          <span
            className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${
              order.status === 'completed'
                ? 'bg-success/10 text-success'
                : 'bg-surface-2 text-content'
            }`}
          >
            {order.status || 'Pending'}
          </span>
        </div>
      </div>
      {order.items && order.items.length > 0 && (
        <div
          className="mt-4 border-t border-divider pt-4"
          style={theme.borderStyle}
        >
          <p className="text-sm text-content-muted" style={theme.mutedTextStyle}>
            {order.items.length} item(s)
          </p>
        </div>
      )}
      <button
        onClick={() => navigateToOrder(order.id)}
        className="mt-4 text-sm font-medium text-content underline"
        style={theme.textStyle}
      >
        View details
      </button>
    </div>
  );
}

export function MedusaB2CAccountOrdersPage() {
  const { isAuthenticated, customerError, listOrders } = useB2CRuntime();
  const [orders, setOrders] = useState<MedusaOrder[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;
    const loadOrders = async () => {
      try {
        setLoading(true);
        const result = await listOrders(10, 0);
        setOrders(result.orders);
        setCount(result.count);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load orders');
      } finally {
        setLoading(false);
      }
    };
    loadOrders();
  }, [isAuthenticated, listOrders]);

  if (customerError) return <AccountErrorShell message={customerError} />;
  if (!isAuthenticated) return <AuthShell />;

  return (
    <PageShell title="Orders" description="View and track your orders.">
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <AccountNav active="orders" />
        <div className="space-y-4">
          {loading ? (
            <p className="text-sm text-content-muted">Loading orders...</p>
          ) : error ? (
            <p className="text-sm text-danger">{error}</p>
          ) : orders.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-content font-medium">No orders yet</p>
              <p className="text-sm text-content-muted mt-1">
                You haven&apos;t placed any orders yet.
              </p>
            </div>
          ) : (
            <>
              <p className="text-sm text-content-muted">
                Showing {orders.length} of {count} orders
              </p>
              <div className="space-y-4">
                {orders.map((order) => (
                  <OrderCard key={order.id} order={order} />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Order Detail Page
// =============================================================================

export function MedusaB2CAccountOrderDetailPage() {
  const { getOrder, isAuthenticated, customerError, requestOrderTransfer } =
    useB2CRuntime();
  const theme = useB2CPageTheme();
  const location = useLocation();
  const orderId = location.pathname.split('/').pop() || '';
  const [order, setOrder] = useState<MedusaOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [transferMessage, setTransferMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!orderId || !isAuthenticated) return;
    const loadOrder = async () => {
      try {
        setLoading(true);
        const orderData = await getOrder(orderId);
        setOrder(orderData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load order');
      } finally {
        setLoading(false);
      }
    };
    loadOrder();
  }, [getOrder, isAuthenticated, orderId]);

  const handleTransferRequest = useCallback(async () => {
    setTransferMessage(null);
    try {
      const transferredOrder = await requestOrderTransfer(orderId);
      setTransferMessage(
        `Transfer request sent for order ${transferredOrder.id}${transferredOrder.email ? ` to ${transferredOrder.email}` : ''}.`,
      );
    } catch (err) {
      setTransferMessage(
        err instanceof Error
          ? err.message
          : 'Failed to request order transfer.',
      );
    }
  }, [orderId, requestOrderTransfer]);

  if (customerError) return <AccountErrorShell message={customerError} />;
  if (!isAuthenticated) return <AuthShell />;

  return (
    <PageShell
      title={`Order #${order?.display_id || orderId.slice(-8)}`}
      description="View your order details."
    >
      <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
        <AccountNav active="orders" />
        <div>
          {loading ? (
            <p className="text-sm text-content-muted">Loading order...</p>
          ) : error ? (
            <p className="text-sm text-danger">{error}</p>
          ) : !order ? (
            <p className="text-sm text-content-muted">Order not found.</p>
          ) : (
            <div className="space-y-6">
              <div
                className="rounded-xl border border-border p-6"
                style={theme.surfaceStyle}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p
                      className="text-sm text-content-muted"
                      style={theme.mutedTextStyle}
                    >
                      Order date
                    </p>
                    <p
                      className="font-medium text-content"
                      style={theme.headingStyle}
                    >
                      {formatDate(order.created_at)}
                    </p>
                  </div>
                  <span
                    className={`inline-flex rounded-full px-3 py-1 text-sm font-medium ${
                      order.status === 'completed'
                        ? 'bg-success/10 text-success'
                        : 'bg-surface-2 text-content'
                    }`}
                  >
                    {order.status || 'Pending'}
                  </span>
                </div>
              </div>

              {order.items && order.items.length > 0 && (
                <div
                  className="rounded-xl border border-border p-6"
                  style={theme.surfaceStyle}
                >
                  <h3
                    className="font-medium text-content mb-4"
                    style={theme.headingStyle}
                  >
                    Items
                  </h3>
                  <div className="space-y-4">
                    {order.items.map((item) => (
                      <div
                        key={item.id}
                        className="flex items-center justify-between"
                      >
                        <div className="flex items-center gap-4">
                          {item.thumbnail && (
                            <img
                              src={item.thumbnail}
                              alt={item.title}
                              className="h-16 w-16 rounded-lg object-cover"
                            />
                          )}
                          <div>
                            <p
                              className="font-medium text-content"
                              style={theme.headingStyle}
                            >
                              {item.title}
                            </p>
                            {item.variant_title && (
                              <p
                                className="text-sm text-content-muted"
                                style={theme.mutedTextStyle}
                              >
                                {item.variant_title}
                              </p>
                            )}
                            <p
                              className="text-sm text-content-muted"
                              style={theme.mutedTextStyle}
                            >
                              Qty: {item.quantity}
                            </p>
                          </div>
                        </div>
                        <p
                          className="font-medium text-content"
                          style={theme.headingStyle}
                        >
                          {formatPrice(item.total, order.currency_code)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div
                className="rounded-xl border border-border p-6"
                style={theme.surfaceStyle}
              >
                <h3
                  className="font-medium text-content mb-4"
                  style={theme.headingStyle}
                >
                  Order summary
                </h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span
                      className="text-content-muted"
                      style={theme.mutedTextStyle}
                    >
                      Subtotal
                    </span>
                    <span className="text-content" style={theme.textStyle}>
                      {formatPrice(order.subtotal, order.currency_code)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span
                      className="text-content-muted"
                      style={theme.mutedTextStyle}
                    >
                      Shipping
                    </span>
                    <span className="text-content" style={theme.textStyle}>
                      {formatPrice(order.shipping_total, order.currency_code)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span
                      className="text-content-muted"
                      style={theme.mutedTextStyle}
                    >
                      Tax
                    </span>
                    <span className="text-content" style={theme.textStyle}>
                      {formatPrice(order.tax_total, order.currency_code)}
                    </span>
                  </div>
                  <div
                    className="flex justify-between border-t border-border pt-2"
                    style={theme.borderStyle}
                  >
                    <span
                      className="font-medium text-content"
                      style={theme.headingStyle}
                    >
                      Total
                    </span>
                    <span
                      className="font-medium text-content"
                      style={theme.headingStyle}
                    >
                      {formatPrice(order.total, order.currency_code)}
                    </span>
                  </div>
                </div>
              </div>

              <div
                className="rounded-xl border border-border p-6"
                style={theme.surfaceStyle}
              >
                <h3
                  className="font-medium text-content mb-4"
                  style={theme.headingStyle}
                >
                  Order transfers
                </h3>
                <p
                  className="text-sm text-content-muted"
                  style={theme.mutedTextStyle}
                >
                  Request a transfer email if this order should move to another
                  owner.
                </p>
                {transferMessage ? (
                  <p
                    className="mt-3 text-sm text-content-muted"
                    style={theme.textStyle}
                  >
                    {transferMessage}
                  </p>
                ) : null}
                <button
                  onClick={() => void handleTransferRequest()}
                  className="mt-4 rounded-lg border border-border px-4 py-2 text-sm font-medium text-content hover:bg-surface-hover"
                  style={theme.secondaryButtonStyle}
                >
                  Request transfer
                </button>
              </div>

              {order.shipping_address && (
                <div
                  className="rounded-xl border border-border p-6"
                  style={theme.surfaceStyle}
                >
                  <h3
                    className="font-medium text-content mb-4"
                    style={theme.headingStyle}
                  >
                    Shipping address
                  </h3>
                  <div
                    className="text-sm text-content-muted"
                    style={theme.mutedTextStyle}
                  >
                    <p>
                      {[
                        order.shipping_address.first_name,
                        order.shipping_address.last_name,
                      ]
                        .filter(Boolean)
                        .join(' ')}
                    </p>
                    <p>{order.shipping_address.address_1}</p>
                    {order.shipping_address.address_2 && (
                      <p>{order.shipping_address.address_2}</p>
                    )}
                    <p>
                      {[
                        order.shipping_address.city,
                        order.shipping_address.province,
                        order.shipping_address.postal_code,
                      ]
                        .filter(Boolean)
                        .join(', ')}
                    </p>
                    <p>{order.shipping_address.country_code?.toUpperCase()}</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Collection Page
// =============================================================================

export function MedusaB2CCollectionPage() {
  const {
    collections,
    loadCollectionByHandle,
    navigateToHome,
    navigateToStore,
  } = useB2CRuntime();
  const sitePath = useResolvedSitePath();
  const [collection, setCollection] = useState(
    collections.find((item) => item.handle === sitePath.handle) || null,
  );
  const [collectionLoading, setCollectionLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const initialCollection =
      collections.find((item) => item.handle === sitePath.handle) || null;

    if (initialCollection) {
      setCollection(initialCollection);
      setCollectionLoading(false);
      return;
    }

    if (!sitePath.handle) {
      setCollection(null);
      setCollectionLoading(false);
      return;
    }

    setCollectionLoading(true);
    const load = async () => {
      const resolvedCollection = await loadCollectionByHandle(sitePath.handle!);
      if (!cancelled) {
        setCollection(resolvedCollection);
        setCollectionLoading(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [collections, loadCollectionByHandle, sitePath.handle]);

  const filterOptions = useMemo(
    () =>
      collection?.id
        ? {
            collectionId: [collection.id],
          }
        : {},
    [collection?.id],
  );

  if (collectionLoading) {
    return (
      <PageShell
        title="Collection"
        description="Loading collection details..."
      >
        <SkeletonProductGrid />
      </PageShell>
    );
  }

  if (!collection) {
    return (
      <B2CStarterShell>
        <main>
          <StorefrontNotFoundState
            title="Collection not found"
            description="The collection you're looking for doesn't exist or is no longer available."
            primaryLabel="Continue shopping"
            onPrimary={navigateToStore}
            secondaryLabel="Go home"
            onSecondary={navigateToHome}
          />
        </main>
      </B2CStarterShell>
    );
  }

  return (
    <PageShell
      title={collection.title}
      description={
        collection.description ||
        'Products from the selected Medusa collection.'
      }
    >
      <CatalogResultsSection
        filterOptions={filterOptions}
        emptyTitle="No collection products yet"
        emptyDescription="This collection doesn't have any products to show yet."
      />
    </PageShell>
  );
}

// =============================================================================
// Category Page
// =============================================================================

export function MedusaB2CCategoryPage() {
  const {
    categories,
    loadCategoryByHandle,
    navigateToCategory,
    navigateToHome,
    navigateToStore,
  } = useB2CRuntime();
  const theme = useB2CPageTheme();
  const sitePath = useResolvedSitePath();
  const categoryHandle = [sitePath.handle, ...sitePath.nestedPath]
    .filter(Boolean)
    .join('/');
  const [category, setCategory] = useState(
    categories.find(
      (item) =>
        item.handle === categoryHandle || item.handle === sitePath.handle,
    ) || null,
  );
  const [categoryLoading, setCategoryLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const initialCategory =
      categories.find(
        (item) =>
          item.handle === categoryHandle || item.handle === sitePath.handle,
      ) || null;

    if (initialCategory) {
      setCategory(initialCategory);
      setCategoryLoading(false);
      return;
    }

    if (!categoryHandle) {
      setCategory(null);
      setCategoryLoading(false);
      return;
    }

    setCategoryLoading(true);
    const load = async () => {
      const resolvedCategory = await loadCategoryByHandle(categoryHandle);
      if (!cancelled) {
        setCategory(resolvedCategory);
        setCategoryLoading(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [categories, categoryHandle, loadCategoryByHandle, sitePath.handle]);

  const breadcrumbs = useMemo(() => {
    if (!category) {
      return [];
    }

    const chain = [category];
    let parentId = category.parent_category_id || null;

    while (parentId) {
      const parent =
        categories.find((item) => item.id === parentId) || null;
      if (!parent) {
        break;
      }
      chain.unshift(parent);
      parentId = parent.parent_category_id || null;
    }

    return chain;
  }, [categories, category]);

  const childCategories = useMemo(
    () =>
      category
        ? categories.filter((item) => item.parent_category_id === category.id)
        : [],
    [categories, category],
  );

  const filterOptions = useMemo(
    () =>
      category?.id
        ? {
            categoryId: [category.id],
          }
        : {},
    [category?.id],
  );

  if (categoryLoading) {
    return (
      <PageShell title="Category" description="Loading category details...">
        <SkeletonProductGrid />
      </PageShell>
    );
  }

  if (!category) {
    return (
      <B2CStarterShell>
        <main>
          <StorefrontNotFoundState
            title="Category not found"
            description="The category you're looking for doesn't exist or has moved."
            primaryLabel="Continue shopping"
            onPrimary={navigateToStore}
            secondaryLabel="Go home"
            onSecondary={navigateToHome}
          />
        </main>
      </B2CStarterShell>
    );
  }

  return (
    <PageShell
      title={category.name}
      description={
        category.description ||
        'Products from the selected Medusa category.'
      }
    >
      {breadcrumbs.length > 0 ? (
        <nav className="flex flex-wrap items-center gap-2 text-sm" aria-label="Breadcrumb">
          <button type="button" onClick={() => navigateToStore()} style={theme.mutedTextStyle}>
            Store
          </button>
          {breadcrumbs.map((crumb, index) => {
            const isCurrent = index === breadcrumbs.length - 1;
            return (
              <div key={crumb.id} className="flex items-center gap-2">
                <span style={theme.mutedTextStyle}>/</span>
                {isCurrent ? (
                  <span style={theme.textStyle}>{crumb.name}</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => navigateToCategory(crumb.handle)}
                    style={theme.mutedTextStyle}
                  >
                    {crumb.name}
                  </button>
                )}
              </div>
            );
          })}
        </nav>
      ) : null}

      {childCategories.length > 0 ? (
        <div className="flex flex-wrap gap-3">
          {childCategories.map((child) => (
            <button
              key={child.id}
              type="button"
              onClick={() => navigateToCategory(child.handle)}
              className="rounded-full border px-4 py-2 text-sm"
              style={theme.secondaryButtonStyle}
            >
              {child.name}
            </button>
          ))}
        </div>
      ) : null}

      <CatalogResultsSection
        filterOptions={filterOptions}
        emptyTitle={`No products in ${category.name}`}
        emptyDescription="This category doesn't have any products to show yet."
      />
    </PageShell>
  );
}

// =============================================================================
// Cart Page
// =============================================================================

export function MedusaB2CCartPage() {
  const {
    cart,
    cartLoading,
    updateCartItem,
    removeCartItem,
    customer,
    getShippingOptions,
    navigateToAccount,
    navigateToStore,
    navigateToCheckout,
  } = useB2CRuntime();
  const theme = useB2CPageTheme();
  const [freeShippingThreshold, setFreeShippingThreshold] = useState<
    number | null
  >(null);

  useEffect(() => {
    let cancelled = false;

    if (!cart?.id || !cart.items?.length) {
      setFreeShippingThreshold(null);
      return;
    }

    const loadShippingThreshold = async () => {
      try {
        const options = await getShippingOptions();
        if (!cancelled) {
          setFreeShippingThreshold(resolveFreeShippingThreshold(options));
        }
      } catch {
        if (!cancelled) {
          setFreeShippingThreshold(null);
        }
      }
    };

    void loadShippingThreshold();

    return () => {
      cancelled = true;
    };
  }, [cart?.id, cart?.items, getShippingOptions]);

  if (cartLoading && !cart) {
    return (
      <PageShell title="Cart" description="Your current Medusa cart contents.">
        <div className="animate-pulse space-y-4">
          <div className="h-24 w-full rounded-xl" style={theme.surfaceStyle} />
          <div className="h-24 w-full rounded-xl" style={theme.surfaceStyle} />
          <div className="h-40 w-full rounded-xl" style={theme.surfaceStyle} />
        </div>
      </PageShell>
    );
  }

  if (!cart?.items?.length) {
    return (
      <PageShell title="Cart" description="Your current Medusa cart contents.">
        <StorefrontEmptyState
          title="Your cart is empty"
          description="Looks like you haven't added anything yet."
          actionLabel="Continue shopping"
          onAction={navigateToStore}
        />
      </PageShell>
    );
  }

  const remainingFreeShipping =
    typeof freeShippingThreshold === 'number'
      ? Math.max(0, freeShippingThreshold - (cart.subtotal || 0))
      : null;
  const freeShippingProgress =
    typeof freeShippingThreshold === 'number' && freeShippingThreshold > 0
      ? Math.min(
          100,
          Math.round(((cart.subtotal || 0) / freeShippingThreshold) * 100),
        )
      : 0;

  return (
    <PageShell title="Cart" description="Your current Medusa cart contents.">
      <div className="space-y-6">
        {!customer ? (
          <div
            className="rounded-xl border border-border p-5"
            style={theme.surfaceStyle}
          >
            <p className="font-medium" style={theme.headingStyle}>
              Already have an account?
            </p>
            <p className="mt-1 text-sm" style={theme.mutedTextStyle}>
              Sign in to link this cart to your order history and saved
              addresses.
            </p>
            <button
              type="button"
              onClick={() => navigateToAccount()}
              className="mt-4 rounded-full px-5 py-2 text-sm font-medium text-white"
              style={theme.primaryPillStyle}
            >
              Sign in
            </button>
          </div>
        ) : null}

        {typeof remainingFreeShipping === 'number' ? (
          <div
            className="rounded-xl border border-border p-5"
            style={theme.surfaceStyle}
          >
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm font-medium" style={theme.headingStyle}>
                {remainingFreeShipping > 0
                  ? `Spend ${formatPrice(remainingFreeShipping, cart.currency_code)} more for free shipping`
                  : "You've unlocked free shipping"}
              </p>
              <span
                className="text-xs uppercase tracking-[0.18em]"
                style={theme.mutedTextStyle}
              >
                Shipping
              </span>
            </div>
            <div
              className="mt-3 h-2 overflow-hidden rounded-full bg-border"
              style={{
                backgroundColor:
                  theme.tokens.colorBorder || 'rgba(17, 24, 39, 0.12)',
              }}
            >
              <div
                className="h-full rounded-full"
                style={{
                  width: `${freeShippingProgress}%`,
                  backgroundColor: theme.tokens.colorPrimary || '#111827',
                }}
              />
            </div>
          </div>
        ) : null}

        <div className="space-y-4">
          {cart.items.map((item) => (
            <div
              key={item.id}
              className="flex flex-col gap-4 rounded-xl border border-border p-4 sm:flex-row sm:items-center sm:justify-between"
              style={theme.surfaceStyle}
            >
              <div className="flex items-center gap-4">
                {item.thumbnail ? (
                  <img
                    src={item.thumbnail}
                    alt={item.product_title || item.title}
                    className="h-20 w-20 rounded-xl object-cover"
                  />
                ) : (
                  <div
                    className="flex h-20 w-20 items-center justify-center rounded-xl border border-dashed"
                    style={theme.borderStyle}
                  >
                    <span className="text-xs" style={theme.mutedTextStyle}>
                      No image
                    </span>
                  </div>
                )}
                <div>
                  <p className="font-medium" style={theme.headingStyle}>
                    {item.product_title || item.title}
                  </p>
                  {formatCartItemVariant(item) ? (
                    <p className="mt-1 text-sm" style={theme.mutedTextStyle}>
                      {formatCartItemVariant(item)}
                    </p>
                  ) : null}
                  <p className="mt-1 text-sm" style={theme.mutedTextStyle}>
                    {formatPrice(item.unit_price, cart.currency_code)} each
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-between gap-4 sm:min-w-[15rem]">
                <div
                  className="flex items-center border border-border"
                  style={theme.surfaceStyle}
                >
                  <button
                    type="button"
                    className="px-3 py-2"
                    style={theme.textStyle}
                    onClick={() =>
                      void updateCartItem(item.id, Math.max(1, item.quantity - 1))
                    }
                  >
                    -
                  </button>
                  <span
                    className="min-w-10 px-2 py-2 text-center"
                    style={theme.textStyle}
                  >
                    {item.quantity}
                  </span>
                  <button
                    type="button"
                    className="px-3 py-2"
                    style={theme.textStyle}
                    onClick={() => void updateCartItem(item.id, item.quantity + 1)}
                  >
                    +
                  </button>
                </div>
                <div className="text-right">
                  <p className="font-medium" style={theme.headingStyle}>
                    {formatPrice(
                      item.total || item.unit_price * item.quantity,
                      cart.currency_code,
                    )}
                  </p>
                  <button
                    type="button"
                    className="mt-1 text-sm text-danger"
                    onClick={() => void removeCartItem(item.id)}
                  >
                    Remove
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div
          className="rounded-xl border border-border p-5"
          style={theme.surfaceStyle}
        >
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span style={theme.mutedTextStyle}>Subtotal</span>
              <span style={theme.textStyle}>
                {formatPrice(cart.subtotal, cart.currency_code)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span style={theme.mutedTextStyle}>Shipping estimate</span>
              <span style={theme.textStyle}>
                {formatPrice(cart.shipping_total, cart.currency_code)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span style={theme.mutedTextStyle}>Taxes</span>
              <span style={theme.textStyle}>
                {formatPrice(cart.tax_total, cart.currency_code)}
              </span>
            </div>
            {cart.discount_total ? (
              <div className="flex items-center justify-between">
                <span style={theme.mutedTextStyle}>Discounts</span>
                <span style={theme.textStyle}>
                  -{formatPrice(cart.discount_total, cart.currency_code)}
                </span>
              </div>
            ) : null}
          </div>
          <div
            className="mt-4 flex flex-col gap-4 border-t pt-4 sm:flex-row sm:items-center sm:justify-between"
            style={theme.borderStyle}
          >
            <p className="text-base font-medium" style={theme.headingStyle}>
              Total
            </p>
            <div className="flex items-center gap-4">
              <p className="text-lg font-medium" style={theme.headingStyle}>
                {formatPrice(cart.total, cart.currency_code)}
              </p>
              <button
                onClick={() => navigateToCheckout()}
                className="rounded-full px-5 py-2 text-sm font-medium text-white"
                style={theme.primaryPillStyle}
              >
                Checkout
              </button>
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  );
}

// =============================================================================
// Checkout Page
// =============================================================================

type CheckoutAddressFormState = {
  first_name: string;
  last_name: string;
  company: string;
  address_1: string;
  address_2: string;
  city: string;
  province: string;
  postal_code: string;
  country_code: string;
  phone: string;
};

type CheckoutFieldErrors = Partial<Record<string, string>>;

function createCheckoutAddressState(
  address?: Partial<MedusaCartAddress> | MedusaCustomerAddress | null,
  fallbackCountryCode?: string,
): CheckoutAddressFormState {
  return {
    first_name: address?.first_name || '',
    last_name: address?.last_name || '',
    company:
      'company' in (address || {}) && typeof address?.company === 'string'
        ? address.company
        : '',
    address_1: address?.address_1 || '',
    address_2: address?.address_2 || '',
    city: address?.city || '',
    province: address?.province || '',
    postal_code: address?.postal_code || '',
    country_code: (
      address?.country_code ||
      fallbackCountryCode ||
      ''
    ).toLowerCase(),
    phone: address?.phone || '',
  };
}

function isAddressReadyForRating(
  address?:
    | Partial<CheckoutAddressFormState>
    | Partial<MedusaCartAddress>
    | null,
): boolean {
  if (!address) return false;
  return Boolean(
    address.first_name?.trim() &&
    address.last_name?.trim() &&
    address.address_1?.trim() &&
    address.city?.trim() &&
    address.postal_code?.trim() &&
    address.country_code?.trim(),
  );
}

function emailLooksValid(email: string): boolean {
  return /^\S+@\S+\.\S+$/.test(email.trim());
}

function getCartItemCount(
  cart: NonNullable<ReturnType<typeof useB2CRuntime>['cart']>,
): number {
  return cart.items?.reduce((count, item) => count + item.quantity, 0) || 0;
}

function getProviderPresentation(providerId: string): {
  label: string;
  badge: string;
  badgeClassName: string;
  kind: 'express' | 'standard';
  helper: string;
} {
  const normalizedId = providerId.toLowerCase();

  if (normalizedId.includes('paypal')) {
    return {
      label: 'PayPal',
      badge: 'PP',
      badgeClassName: 'border-[#003087]/15 bg-[#F5F8FF] text-[#003087]',
      kind: 'express',
      helper: 'Fast wallet redirect handled by PayPal.',
    };
  }

  if (normalizedId.includes('venmo')) {
    return {
      label: 'Venmo',
      badge: 'VM',
      badgeClassName: 'border-[#008CFF]/15 bg-[#F4F8FF] text-[#008CFF]',
      kind: 'express',
      helper: 'Wallet-style redirect through Venmo.',
    };
  }

  if (normalizedId.includes('google') || normalizedId.includes('gpay')) {
    return {
      label: 'G Pay',
      badge: 'GP',
      badgeClassName: 'border-border bg-surface text-content',
      kind: 'express',
      helper: 'Accelerated checkout with Google Pay.',
    };
  }

  if (normalizedId.includes('apple') && normalizedId.includes('pay')) {
    return {
      label: 'Apple Pay',
      badge: 'AP',
      badgeClassName: 'border-border bg-content text-white',
      kind: 'express',
      helper: 'Accelerated checkout with Apple Pay.',
    };
  }

  if (normalizedId.includes('shop') && normalizedId.includes('pay')) {
    return {
      label: 'Shop Pay',
      badge: 'SP',
      badgeClassName: 'border-[#5A31F4]/15 bg-[#F6F3FF] text-[#5A31F4]',
      kind: 'express',
      helper: 'Accelerated checkout with Shop Pay.',
    };
  }

  if (normalizedId.includes('manual')) {
    return {
      label: 'Manual Test',
      badge: 'MT',
      badgeClassName: 'border-border bg-surface-2 text-content-muted',
      kind: 'standard',
      helper: 'Use this provider to complete checkout inside the storefront.',
    };
  }

  if (normalizedId.includes('stripe') || normalizedId.includes('card')) {
    return {
      label: 'Card',
      badge: 'CC',
      badgeClassName: 'border-border bg-surface text-content',
      kind: 'standard',
      helper: 'Card handling is delegated to the active payment provider.',
    };
  }

  return {
    label: providerId
      .replace(/^pp_/, '')
      .replace(/[_-]+/g, ' ')
      .replace(/\b\w/g, (match) => match.toUpperCase()),
    badge: providerId.slice(0, 2).toUpperCase(),
    badgeClassName: 'border-border bg-surface-2 text-content-muted',
    kind: 'standard',
    helper:
      'Provider-specific behavior is handled by the active Medusa runtime.',
  };
}

function getPaymentRedirectUrl(
  paymentCollection: MedusaPaymentCollection,
  providerId: string,
): string | null {
  const session = paymentCollection.payment_sessions?.find(
    (entry) => entry.provider_id === providerId,
  );
  return typeof session?.data?.redirect_url === 'string'
    ? session.data.redirect_url
    : null;
}

function isStripePaymentProvider(
  providerId: string | null | undefined,
): boolean {
  if (!providerId) {
    return false;
  }
  const normalizedId = providerId.toLowerCase();
  return normalizedId.includes('stripe') || normalizedId.includes('card');
}

function getPaymentSessionForProvider(
  paymentCollection: MedusaPaymentCollection | null,
  providerId: string | null | undefined,
) {
  if (!paymentCollection || !providerId) {
    return null;
  }
  return (
    paymentCollection.payment_sessions?.find(
      (entry) => entry.provider_id === providerId,
    ) || null
  );
}

function getStripeClientSecret(
  paymentCollection: MedusaPaymentCollection | null,
  providerId: string | null | undefined,
): string | null {
  const session = getPaymentSessionForProvider(paymentCollection, providerId);
  return typeof session?.data?.client_secret === 'string'
    ? session.data.client_secret
    : null;
}

const stripePromiseCache = new Map<string, Promise<Stripe | null>>();

function getStripePromise(
  publishableKey: string,
  stripeAccountId: string | null,
): Promise<Stripe | null> {
  const cacheKey = `${publishableKey}::${stripeAccountId || ''}`;
  const existingPromise = stripePromiseCache.get(cacheKey);
  if (existingPromise) {
    return existingPromise;
  }
  const nextPromise = loadStripe(
    publishableKey,
    stripeAccountId ? { stripeAccount: stripeAccountId } : undefined,
  );
  stripePromiseCache.set(cacheKey, nextPromise);
  return nextPromise;
}

function CheckoutStripeCardForm({
  cart,
  clientSecret,
  submitting,
  setSubmitting,
  prepareBillingForPayment,
  completeConfirmedCheckout,
  updatePaymentError,
  buttonStyle,
}: {
  cart: MedusaCart;
  clientSecret: string;
  submitting: boolean;
  setSubmitting: (value: boolean) => void;
  prepareBillingForPayment: () => Promise<CheckoutAddressFormState | null>;
  completeConfirmedCheckout: () => Promise<boolean>;
  updatePaymentError: (message: string | null) => void;
  buttonStyle: CSSProperties;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [cardComplete, setCardComplete] = useState(false);
  const [cardBrand, setCardBrand] = useState<string | null>(null);
  const [cardError, setCardError] = useState<string | null>(null);

  const cardOptions = useMemo<StripeCardElementOptions>(
    () => ({
      style: {
        base: {
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
          fontSize: '16px',
          color: '#18181b',
          '::placeholder': {
            color: '#9ca3af',
          },
        },
        invalid: {
          color: '#dc2626',
          iconColor: '#dc2626',
        },
      },
      hidePostalCode: true,
    }),
    [],
  );

  const handleSubmit = useCallback(async () => {
    if (!stripe || !elements) {
      const message = 'Stripe payment form is not ready yet.';
      setCardError(message);
      updatePaymentError(message);
      return;
    }

    const card = elements.getElement(CardElement);
    if (!card) {
      const message = 'Stripe card input is not ready yet.';
      setCardError(message);
      updatePaymentError(message);
      return;
    }

    const billingAddress = await prepareBillingForPayment();
    if (!billingAddress) {
      return;
    }

    setSubmitting(true);
    setCardError(null);
    updatePaymentError(null);

    try {
      const { error, paymentIntent } = await stripe.confirmCardPayment(
        clientSecret,
        {
          payment_method: {
            card,
            billing_details: {
              name:
                [billingAddress.first_name, billingAddress.last_name]
                  .filter(Boolean)
                  .join(' ')
                  .trim() || undefined,
              email: cart.email || undefined,
              phone: billingAddress.phone || undefined,
              address: {
                city: billingAddress.city || undefined,
                country: billingAddress.country_code || undefined,
                line1: billingAddress.address_1 || undefined,
                line2: billingAddress.address_2 || undefined,
                postal_code: billingAddress.postal_code || undefined,
                state: billingAddress.province || undefined,
              },
            },
          },
        },
      );

      if (error) {
        const stripeError = error as {
          message?: string;
          payment_intent?: { status?: string };
        };
        const intentStatus = stripeError.payment_intent?.status;
        if (
          intentStatus === 'requires_capture' ||
          intentStatus === 'succeeded'
        ) {
          const completed = await completeConfirmedCheckout();
          if (completed) {
            return;
          }
        }
        const message = stripeError.message || 'Unable to confirm your card.';
        setCardError(message);
        updatePaymentError(message);
        return;
      }

      if (
        paymentIntent?.status === 'requires_capture' ||
        paymentIntent?.status === 'succeeded'
      ) {
        const completed = await completeConfirmedCheckout();
        if (completed) {
          return;
        }
      }

      const message =
        'Stripe did not return a completed payment intent. Please try again.';
      setCardError(message);
      updatePaymentError(message);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unable to confirm your card.';
      setCardError(message);
      updatePaymentError(message);
    } finally {
      setSubmitting(false);
    }
  }, [
    cart.email,
    clientSecret,
    completeConfirmedCheckout,
    elements,
    prepareBillingForPayment,
    setSubmitting,
    stripe,
    updatePaymentError,
  ]);

  return (
    <div className="space-y-4">
      <div
        className="rounded-md border border-border bg-surface px-4 py-4"
        data-testid="b2c-stripe-card-form"
      >
        <div className="mb-3 flex items-center justify-between gap-3 text-xs text-content-muted">
          <span>Card details</span>
          {cardBrand ? <span>{cardBrand}</span> : null}
        </div>
        <CardElement
          options={cardOptions}
          onChange={(event) => {
            const nextBrand =
              event.brand && event.brand !== 'unknown'
                ? event.brand.charAt(0).toUpperCase() + event.brand.slice(1)
                : null;
            const nextError = event.error?.message || null;
            setCardBrand(nextBrand);
            setCardComplete(event.complete);
            setCardError(nextError);
            updatePaymentError(nextError);
          }}
        />
      </div>
      {cardError ? (
        <p className="text-sm font-medium text-danger">{cardError}</p>
      ) : null}
      <button
        type="button"
        onClick={() => void handleSubmit()}
        disabled={submitting || !cardComplete || !stripe || !elements}
        className="w-full rounded-md bg-content px-6 py-3 text-sm font-medium text-white transition hover:bg-content/80 disabled:cursor-not-allowed disabled:opacity-50"
        style={{ ...buttonStyle, borderRadius: '6px' }}
        data-testid="b2c-stripe-complete-checkout"
      >
        {submitting ? 'Processing…' : 'Pay now'}
      </button>
    </div>
  );
}

const CHECKOUT_DESKTOP_GRID_CLASS =
  'lg:grid-cols-[minmax(0,54%)_minmax(0,46%)]';
const CHECKOUT_CENTER_TRACKS_CLASS =
  'lg:grid-cols-[minmax(0,1fr)_minmax(0,56rem)_minmax(0,1fr)]';
const CHECKOUT_FORM_MAX_WIDTH_CLASS = 'lg:max-w-[27.5rem]';
const CHECKOUT_SUMMARY_MAX_WIDTH_CLASS = 'lg:max-w-[22rem]';
const CHECKOUT_FORM_RAIL_POSITION_CLASS = 'lg:mx-0 lg:ml-auto lg:mr-8';

function CheckoutShell({
  children,
  cartTotal,
  onBackToCart,
  onToggleMobileSummary,
}: {
  children: React.ReactNode;
  cartTotal: string;
  onBackToCart: () => void;
  onToggleMobileSummary: () => void;
}) {
  const theme = useB2CPageTheme();
  const { siteName } = useB2CRuntime();
  const brandName =
    theme.tokens.brandName?.trim() || siteName?.trim() || 'Store';

  return (
    <div
      className="min-h-screen bg-surface text-content"
      style={theme.pageStyle}
      data-testid="b2c-checkout-page"
    >
      <header className="w-full border-b border-border bg-surface">
        <div
          className={`w-full lg:grid ${CHECKOUT_CENTER_TRACKS_CLASS}`}
          data-testid="b2c-checkout-header-frame"
        >
          <div className="hidden lg:block" />
          <div
            className={`grid w-full ${CHECKOUT_DESKTOP_GRID_CLASS}`}
            data-testid="b2c-checkout-header-shell"
          >
            <div className="flex items-center justify-between px-4 py-4 sm:px-8 lg:px-0 lg:py-5">
              <div
                className={`w-full ${CHECKOUT_FORM_MAX_WIDTH_CLASS} ${CHECKOUT_FORM_RAIL_POSITION_CLASS}`}
              >
                <button
                  onClick={onBackToCart}
                  className="w-full text-left text-lg font-bold tracking-tight text-content"
                  style={theme.headingStyle}
                >
                  {brandName}
                </button>
              </div>
              <button
                onClick={onBackToCart}
                className="shrink-0 text-content-muted transition hover:text-content lg:hidden"
                aria-label="Cart"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="22"
                  height="22"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
                  <line x1="3" x2="21" y1="6" y2="6" />
                  <path d="M16 10a4 4 0 0 1-8 0" />
                </svg>
              </button>
            </div>
            <div className="hidden items-center justify-end px-4 py-5 sm:px-8 lg:flex lg:px-0">
              <button
                onClick={onBackToCart}
                className="text-content-muted transition hover:text-content"
                aria-label="Cart"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="22"
                  height="22"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
                  <line x1="3" x2="21" y1="6" y2="6" />
                  <path d="M16 10a4 4 0 0 1-8 0" />
                </svg>
              </button>
            </div>
          </div>
          <div className="hidden lg:block" />
        </div>
      </header>
      <div className="border-b border-border bg-surface px-4 py-3 sm:hidden">
        <button
          type="button"
          onClick={onToggleMobileSummary}
          className="flex w-full items-center justify-between py-2 text-left text-sm font-medium text-content"
          data-testid="b2c-mobile-summary-toggle"
        >
          <span>Order summary</span>
          <span>{cartTotal}</span>
        </button>
      </div>
      {children}
    </div>
  );
}

function CheckoutExpressSection({
  providers,
  disabled,
  disabledReason,
  activeProviderId,
  onSelect,
}: {
  providers: MedusaPaymentProvider[];
  disabled: boolean;
  disabledReason: string;
  activeProviderId: string | null;
  onSelect: (providerId: string) => void;
}) {
  if (!providers.length) {
    return null;
  }

  const theme = useB2CPageTheme();

  return (
    <section data-testid="b2c-checkout-express">
      <p
        className="mb-3 text-center text-xs text-content-muted"
        style={theme.mutedTextStyle}
      >
        Express checkout
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        {providers.map((provider) => {
          const presentation = getProviderPresentation(provider.id);
          const isActive = activeProviderId === provider.id;

          return (
            <button
              key={provider.id}
              type="button"
              onClick={() => onSelect(provider.id)}
              disabled={disabled}
              data-testid={`b2c-express-provider-${provider.id}`}
              className={`flex items-center justify-center gap-2 rounded-md px-4 py-3 text-sm font-semibold transition ${
                disabled
                  ? 'cursor-not-allowed bg-surface-2 text-content-muted'
                  : isActive
                    ? 'bg-content text-white'
                    : 'bg-surface-2 text-content hover:bg-border'
              }`}
              style={isActive ? theme.primaryButtonStyle : undefined}
            >
              <span className="text-sm font-bold">{presentation.label}</span>
            </button>
          );
        })}
      </div>
      <div className="my-6 flex items-center gap-4">
        <div className="h-px flex-1 bg-border" />
        <span className="text-xs uppercase text-content-muted">or</span>
        <div className="h-px flex-1 bg-border" />
      </div>
    </section>
  );
}

function CheckoutSection({
  title,
  description,
  action,
  children,
  disabled = false,
  testId,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  disabled?: boolean;
  testId?: string;
}) {
  const theme = useB2CPageTheme();

  return (
    <section data-testid={testId}>
      <div className="flex flex-wrap items-baseline justify-between gap-4 pb-3">
        <h2
          className="text-lg font-bold text-content"
          style={theme.headingStyle}
        >
          {title}
        </h2>
        {action}
      </div>
      <div
        className={disabled ? 'pointer-events-none opacity-60' : undefined}
        aria-disabled={disabled || undefined}
        {...(disabled ? { inert: '' } : {})}
      >
        {children}
      </div>
    </section>
  );
}

function CheckoutFieldError({
  id,
  message,
}: {
  id?: string;
  message?: string;
}) {
  return message ? (
    <p id={id} role="alert" className="mt-1 text-xs font-medium text-danger">
      {message}
    </p>
  ) : null;
}

function CheckoutAddressFields({
  prefix,
  address,
  errors,
  onChange,
  countries,
  countryLocked,
  countryHint,
}: {
  prefix: 'shipping' | 'billing';
  address: CheckoutAddressFormState;
  errors: CheckoutFieldErrors;
  onChange: (field: keyof CheckoutAddressFormState, value: string) => void;
  countries: Array<{ iso_2: string; display_name?: string }>;
  countryLocked: boolean;
  countryHint?: string | null;
}) {
  const theme = useB2CPageTheme();
  const checkoutInputStyle = {
    ...theme.inputStyle,
    borderRadius: '6px',
    boxShadow: 'none',
  };
  const floatInputClassName =
    'peer w-full rounded-md border border-border bg-surface px-3 pb-2 pt-5 text-sm text-content outline-none transition placeholder:text-transparent focus:border-content focus:ring-2 focus:ring-accent/30';
  const floatLabelClassName =
    'pointer-events-none absolute left-3 top-1.5 origin-left text-[11px] text-content-muted transition-all peer-placeholder-shown:top-3.5 peer-placeholder-shown:text-sm peer-placeholder-shown:text-content-muted peer-focus:top-1.5 peer-focus:text-[11px] peer-focus:text-content-muted';

  const selectValue = address.country_code || countries[0]?.iso_2 || '';

  return (
    <div className="space-y-3 py-1">
      <div className="relative">
        <select
          id={`${prefix}_country_code`}
          value={selectValue}
          onChange={(event) => onChange('country_code', event.target.value)}
          className="w-full appearance-none rounded-md border border-border bg-surface px-3 pb-2 pt-5 text-sm text-content outline-none transition focus:border-content focus:ring-2 focus:ring-accent/30"
          style={checkoutInputStyle}
          disabled={countryLocked && countries.length <= 1}
          aria-label="Country/Region"
          aria-invalid={!!errors[`${prefix}_country_code`] || undefined}
          aria-describedby={errors[`${prefix}_country_code`] ? `${prefix}_country_code_error` : undefined}
          required
        >
          {countries.length ? (
            countries.map((country) => (
              <option key={country.iso_2} value={country.iso_2}>
                {country.display_name || country.iso_2.toUpperCase()}
              </option>
            ))
          ) : (
            <option value={selectValue}>
              {selectValue ? selectValue.toUpperCase() : 'Unavailable'}
            </option>
          )}
        </select>
        <span className="pointer-events-none absolute left-3 top-1.5 text-[11px] text-content-muted">
          Country/Region
        </span>
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-content-muted">
          &#x25BE;
        </span>
        <CheckoutFieldError id={`${prefix}_country_code_error`} message={errors[`${prefix}_country_code`]} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="relative">
          <input
            id={`${prefix}_first_name`}
            value={address.first_name}
            onChange={(event) => onChange('first_name', event.target.value)}
            autoComplete={`${prefix} given-name`}
            placeholder="First name"
            className={floatInputClassName}
            style={checkoutInputStyle}
            required
            aria-invalid={!!errors[`${prefix}_first_name`] || undefined}
            aria-describedby={errors[`${prefix}_first_name`] ? `${prefix}_first_name_error` : undefined}
          />
          <label htmlFor={`${prefix}_first_name`} className={floatLabelClassName}>First name</label>
          <CheckoutFieldError id={`${prefix}_first_name_error`} message={errors[`${prefix}_first_name`]} />
        </div>
        <div className="relative">
          <input
            id={`${prefix}_last_name`}
            value={address.last_name}
            onChange={(event) => onChange('last_name', event.target.value)}
            autoComplete={`${prefix} family-name`}
            placeholder="Last name"
            className={floatInputClassName}
            style={checkoutInputStyle}
            required
            aria-invalid={!!errors[`${prefix}_last_name`] || undefined}
            aria-describedby={errors[`${prefix}_last_name`] ? `${prefix}_last_name_error` : undefined}
          />
          <label htmlFor={`${prefix}_last_name`} className={floatLabelClassName}>Last name</label>
          <CheckoutFieldError id={`${prefix}_last_name_error`} message={errors[`${prefix}_last_name`]} />
        </div>
      </div>
      <div className="relative">
        <input
          id={`${prefix}_company`}
          value={address.company}
          onChange={(event) => onChange('company', event.target.value)}
          autoComplete={`${prefix} organization`}
          placeholder="Company (optional)"
          className={floatInputClassName}
          style={checkoutInputStyle}
        />
        <label htmlFor={`${prefix}_company`} className={floatLabelClassName}>Company (optional)</label>
      </div>
      <div className="relative">
        <input
          id={`${prefix}_address_1`}
          value={address.address_1}
          onChange={(event) => onChange('address_1', event.target.value)}
          autoComplete={`${prefix} address-line1`}
          placeholder="Address"
          className={floatInputClassName}
          style={checkoutInputStyle}
          required
          aria-invalid={!!errors[`${prefix}_address_1`] || undefined}
          aria-describedby={errors[`${prefix}_address_1`] ? `${prefix}_address_1_error` : undefined}
        />
        <label htmlFor={`${prefix}_address_1`} className={floatLabelClassName}>Address</label>
        <CheckoutFieldError id={`${prefix}_address_1_error`} message={errors[`${prefix}_address_1`]} />
      </div>
      <div className="relative">
        <input
          id={`${prefix}_address_2`}
          value={address.address_2}
          onChange={(event) => onChange('address_2', event.target.value)}
          autoComplete={`${prefix} address-line2`}
          placeholder="Apartment, suite, etc. (optional)"
          className={floatInputClassName}
          style={checkoutInputStyle}
        />
        <label htmlFor={`${prefix}_address_2`} className={floatLabelClassName}>
          Apartment, suite, etc. (optional)
        </label>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="relative">
          <input
            id={`${prefix}_city`}
            value={address.city}
            onChange={(event) => onChange('city', event.target.value)}
            autoComplete={`${prefix} address-level2`}
            placeholder="City"
            className={floatInputClassName}
            style={checkoutInputStyle}
            required
            aria-invalid={!!errors[`${prefix}_city`] || undefined}
            aria-describedby={errors[`${prefix}_city`] ? `${prefix}_city_error` : undefined}
          />
          <label htmlFor={`${prefix}_city`} className={floatLabelClassName}>City</label>
          <CheckoutFieldError id={`${prefix}_city_error`} message={errors[`${prefix}_city`]} />
        </div>
        <div className="relative">
          <input
            id={`${prefix}_province`}
            value={address.province}
            onChange={(event) => onChange('province', event.target.value)}
            autoComplete={`${prefix} address-level1`}
            placeholder="State"
            className={floatInputClassName}
            style={checkoutInputStyle}
            required
          />
          <label htmlFor={`${prefix}_province`} className={floatLabelClassName}>State</label>
        </div>
        <div className="relative">
          <input
            id={`${prefix}_postal_code`}
            value={address.postal_code}
            onChange={(event) => onChange('postal_code', event.target.value)}
            autoComplete={`${prefix} postal-code`}
            placeholder="ZIP code"
            className={floatInputClassName}
            style={checkoutInputStyle}
            required
            aria-invalid={!!errors[`${prefix}_postal_code`] || undefined}
            aria-describedby={errors[`${prefix}_postal_code`] ? `${prefix}_postal_code_error` : undefined}
          />
          <label htmlFor={`${prefix}_postal_code`} className={floatLabelClassName}>ZIP code</label>
          <CheckoutFieldError id={`${prefix}_postal_code_error`} message={errors[`${prefix}_postal_code`]} />
        </div>
      </div>
      <div className="relative">
        <input
          id={`${prefix}_phone`}
          value={address.phone}
          onChange={(event) => onChange('phone', event.target.value)}
          autoComplete={`${prefix} tel`}
          placeholder="Phone"
          className={floatInputClassName}
          style={checkoutInputStyle}
        />
        <label htmlFor={`${prefix}_phone`} className={floatLabelClassName}>Phone</label>
      </div>
      {countryHint ? (
        <p className="text-xs text-content-muted" style={theme.mutedTextStyle}>
          {countryHint}
        </p>
      ) : null}
    </div>
  );
}

function CheckoutSummary({
  cart,
  currencyCode,
  shippingCompleted,
  promotionCode,
  promotionSubmitting,
  promotionError,
  onPromotionCodeChange,
  onApplyPromotion,
  onRemovePromotion,
  mobile = false,
}: {
  cart: NonNullable<ReturnType<typeof useB2CRuntime>['cart']>;
  currencyCode: string;
  shippingCompleted: boolean;
  promotionCode: string;
  promotionSubmitting: boolean;
  promotionError?: string;
  onPromotionCodeChange: (value: string) => void;
  onApplyPromotion: () => void;
  onRemovePromotion: (code: string) => void;
  mobile?: boolean;
}) {
  const theme = useB2CPageTheme();
  const displayShippingTotal = shippingCompleted ? cart.shipping_total || 0 : 0;
  const displayTotal =
    (cart.subtotal || 0) +
    displayShippingTotal +
    (cart.tax_total || 0) -
    (cart.discount_total || 0);
  const itemCount = getCartItemCount(cart);

  return (
    <aside
      className={
        mobile
          ? 'border-b border-border pb-5'
          : `sticky top-6 w-full ${CHECKOUT_SUMMARY_MAX_WIDTH_CLASS}`
      }
      data-testid={
        mobile ? 'b2c-checkout-summary-mobile' : 'b2c-checkout-summary'
      }
    >
      <div className="space-y-4">
        <div className="space-y-3">
          {cart.items?.map((item) => (
            <div
              key={item.id}
              className="flex items-start justify-between gap-3 py-1"
            >
              <div className="flex min-w-0 items-start gap-3">
                <div className="relative shrink-0">
                  {item.thumbnail ? (
                    <img
                      src={item.thumbnail}
                      alt={item.title}
                      className="h-14 w-14 rounded-md border border-border bg-surface object-cover"
                    />
                  ) : (
                    <div className="flex h-14 w-14 items-center justify-center rounded-md border border-border bg-surface text-[11px] font-semibold uppercase tracking-[0.18em] text-content-muted">
                      {item.title?.charAt(0) || '?'}
                    </div>
                  )}
                  {item.quantity > 1 ? (
                    <span className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center rounded-full bg-content-muted text-[10px] font-semibold text-white">
                      {item.quantity}
                    </span>
                  ) : null}
                </div>
                <div className="min-w-0 space-y-1">
                  <p
                    className="truncate text-sm font-medium text-content"
                    style={theme.headingStyle}
                  >
                    {item.title}
                  </p>
                  <p
                    className="text-xs text-content-muted"
                    style={theme.mutedTextStyle}
                  >
                    Qty {item.quantity}
                    {item.variant?.title ? ` · ${item.variant.title}` : ''}
                  </p>
                </div>
              </div>
              <p
                className="shrink-0 text-sm font-medium text-content"
                style={theme.headingStyle}
              >
                {formatPrice(
                  item.total ?? item.unit_price * item.quantity,
                  currencyCode,
                )}
              </p>
            </div>
          ))}
        </div>
        <div className="pt-4" data-testid="b2c-checkout-promo">
          <label className="block">
            <div className="flex gap-2">
              <input
                value={promotionCode}
                onChange={(event) => onPromotionCodeChange(event.target.value)}
                placeholder="Discount code or gift card"
                className="min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-content outline-none transition placeholder:text-content-muted focus:border-content focus:ring-2 focus:ring-accent/30"
                style={{
                  ...theme.inputStyle,
                  borderRadius: '6px',
                  boxShadow: 'none',
                }}
              />
              <button
                type="button"
                onClick={onApplyPromotion}
                disabled={promotionSubmitting}
                className="rounded-md border border-border bg-surface-2 px-5 py-2.5 text-sm font-medium text-content-muted transition hover:bg-border disabled:cursor-not-allowed disabled:opacity-50"
              >
                {promotionSubmitting ? 'Applying…' : 'Apply'}
              </button>
            </div>
          </label>
          {promotionError ? (
            <p className="mt-3 text-sm font-medium text-danger">
              {promotionError}
            </p>
          ) : null}
          {cart.promotions?.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {cart.promotions.map((promotion) => (
                <div
                  key={promotion.id}
                  className="inline-flex items-center gap-2 rounded-full border border-border bg-surface-2 px-3 py-1.5 text-xs font-medium text-content-muted"
                  style={theme.surfaceStyle}
                >
                  <span>{promotion.code || 'Applied code'}</span>
                  {promotion.code ? (
                    <button
                      type="button"
                      onClick={() => onRemovePromotion(promotion.code || '')}
                      className="text-content-muted transition hover:text-content"
                      style={theme.mutedTextStyle}
                    >
                      Remove
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <div className="space-y-2 pt-4 text-sm text-content-muted">
          <div className="flex items-center justify-between">
            <span>Subtotal</span>
            <span className="text-content">
              {formatPrice(cart.subtotal, currencyCode)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span>Shipping</span>
            <span className="text-xs text-content-muted">
              {shippingCompleted && displayShippingTotal > 0
                ? formatPrice(displayShippingTotal, currencyCode)
                : 'Enter shipping address'}
            </span>
          </div>
          {cart.tax_total ? (
            <div className="flex items-center justify-between">
              <span>Taxes</span>
              <span className="text-content">
                {formatPrice(cart.tax_total, currencyCode)}
              </span>
            </div>
          ) : null}
          {cart.discount_total ? (
            <div className="flex items-center justify-between">
              <span>Discounts</span>
              <span className="text-content">
                -{formatPrice(cart.discount_total, currencyCode)}
              </span>
            </div>
          ) : null}
        </div>
        <div className="flex items-center justify-between pt-4">
          <p
            className="text-lg font-bold text-content"
            style={theme.headingStyle}
          >
            Total
          </p>
          <p className="text-right">
            <span className="mr-2 text-xs text-content-muted">
              {currencyCode.toUpperCase()}
            </span>
            <span
              className="text-lg font-bold text-content"
              style={theme.headingStyle}
            >
              {formatPrice(displayTotal, currencyCode)}
            </span>
          </p>
        </div>
      </div>
    </aside>
  );
}

function CheckoutFooterLinks() {
  const funnelRuntime = useFunnelRuntime();
  const { countryCode } = useB2CRuntime();
  const theme = useB2CPageTheme();

  const policyLinks = [
    { label: 'Privacy policy', slug: 'privacy-policy' },
    { label: 'Terms of service', slug: 'terms-of-service' },
    { label: 'Shipping policy', slug: 'shipping-policy' },
    { label: 'Refund policy', slug: 'refund-policy' },
  ].map((link) => ({
    label: link.label,
    href: funnelRuntime
      ? buildPublicFunnelPath({
          productSlug: funnelRuntime.productSlug,
          funnelSlug: funnelRuntime.funnelSlug,
          bundleMode: funnelRuntime.bundleMode || false,
          sitePath: `${countryCode || 'us'}/policies/${link.slug}`,
        })
      : `/policies/${link.slug}`,
  }));

  return (
    <div
      className="flex flex-wrap justify-center gap-x-4 gap-y-2 border-t border-border pt-6 text-xs text-content-muted"
      data-testid="b2c-checkout-footer-links"
    >
      {policyLinks.map((link) => (
        <a
          key={link.href}
          href={link.href}
          className="underline underline-offset-2 transition hover:text-content"
          style={theme.textStyle}
        >
          {link.label}
        </a>
      ))}
    </div>
  );
}

export function MedusaB2CCheckoutPage() {
  const {
    cart,
    cartLoading,
    customer,
    isAuthenticated,
    regions,
    navigateToAccount,
    navigateToCart,
    navigateToOrderConfirmed,
    getShippingOptions,
    getPaymentProviders,
    performCheckoutAction,
    completeCheckout,
    applyPromotionCode,
    removePromotionCode,
    updateCartBillingAddress,
  } = useB2CRuntime();
  const theme = useB2CPageTheme();
  const [email, setEmail] = useState('');
  const [shippingAddress, setShippingAddress] =
    useState<CheckoutAddressFormState>(() => createCheckoutAddressState());
  const [billingSameAsShipping, setBillingSameAsShipping] = useState(true);
  const [billingAddress, setBillingAddress] =
    useState<CheckoutAddressFormState>(() => createCheckoutAddressState());
  const [fieldErrors, setFieldErrors] = useState<CheckoutFieldErrors>({});
  const [sectionErrors, setSectionErrors] = useState<CheckoutFieldErrors>({});
  const [shippingOptions, setShippingOptions] = useState<
    MedusaShippingOption[]
  >([]);
  const [shippingOptionsLoading, setShippingOptionsLoading] = useState(false);
  const [shippingOptionsLoaded, setShippingOptionsLoaded] = useState(false);
  const [deliveryVersion, setDeliveryVersion] = useState(0);
  const [shippingVersion, setShippingVersion] = useState(0);
  const [selectedShippingOptionId, setSelectedShippingOptionId] = useState<
    string | null
  >(null);
  const [shippingAddressEdited, setShippingAddressEdited] = useState(false);
  const [paymentProviders, setPaymentProviders] = useState<
    MedusaPaymentProvider[]
  >([]);
  const [paymentProvidersLoading, setPaymentProvidersLoading] = useState(false);
  const [paymentProvidersLoaded, setPaymentProvidersLoaded] = useState(false);
  const [selectedPaymentProviderId, setSelectedPaymentProviderId] = useState<
    string | null
  >(null);
  const [paymentCollection, setPaymentCollection] =
    useState<MedusaPaymentCollection | null>(null);
  const [paymentSessionLoading, setPaymentSessionLoading] = useState(false);
  const [billingAddressEdited, setBillingAddressEdited] = useState(false);
  const [paymentRedirectUrl, setPaymentRedirectUrl] = useState<string | null>(
    null,
  );
  const [submitting, setSubmitting] = useState(false);
  const [mobileSummaryOpen, setMobileSummaryOpen] = useState(false);
  const [hydratedCartId, setHydratedCartId] = useState<string | null>(null);
  const [promotionCode, setPromotionCode] = useState('');
  const [promotionSubmitting, setPromotionSubmitting] = useState(false);
  const medusaRuntimeConfig = getMedusaRuntimeConfig();
  const stripePublishableKey = (
    import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || ''
  ).trim();
  const stripeAccountId = medusaRuntimeConfig?.stripeAccountId || null;
  const stripePromise = useMemo(
    () =>
      stripePublishableKey
        ? getStripePromise(stripePublishableKey, stripeAccountId)
        : null,
    [stripeAccountId, stripePublishableKey],
  );
  const stripeSelected = isStripePaymentProvider(selectedPaymentProviderId);
  const stripeClientSecret = useMemo(
    () => getStripeClientSecret(paymentCollection, selectedPaymentProviderId),
    [paymentCollection, selectedPaymentProviderId],
  );
  const stripeElementsOptions = useMemo<StripeElementsOptions | null>(
    () => (stripeClientSecret ? { clientSecret: stripeClientSecret } : null),
    [stripeClientSecret],
  );

  const activeRegion = useMemo(
    () => regions.find((region) => region.id === cart?.region_id) || null,
    [regions, cart?.region_id],
  );
  const activeCountries = useMemo(
    () => activeRegion?.countries || [],
    [activeRegion],
  );
  const defaultCountryCode = useMemo(
    () =>
      cart?.shipping_address?.country_code ||
      customer?.addresses?.find((address) => address.is_default_shipping)
        ?.country_code ||
      activeCountries[0]?.iso_2 ||
      '',
    [
      activeCountries,
      cart?.shipping_address?.country_code,
      customer?.addresses,
    ],
  );
  const currencyCode = cart?.currency_code || 'usd';
  const activeCartCount = cart ? getCartItemCount(cart) : 0;
  const contactCompleted =
    Boolean(cart?.email?.trim()) && cart?.email === email.trim();
  const deliveryCompleted = isAddressReadyForRating(cart?.shipping_address);
  const cartShippingMethodId =
    cart?.shipping_methods?.[0]?.shipping_option_id || null;
  const shippingCompleted =
    Boolean(cartShippingMethodId) &&
    deliveryVersion > 0 &&
    shippingVersion === deliveryVersion &&
    !shippingAddressEdited;
  const visibleShippingOptionId = shippingAddressEdited
    ? null
    : shippingCompleted
      ? selectedShippingOptionId || cartShippingMethodId
      : selectedShippingOptionId;
  const hasSingleShippingOption = shippingOptions.length === 1;
  const visibleOrderTotal = formatPrice(
    (cart?.subtotal || 0) +
      (shippingCompleted ? cart?.shipping_total || 0 : 0) +
      (cart?.tax_total || 0) -
      (cart?.discount_total || 0),
    currencyCode,
  );
  const expressProviders = useMemo(
    () =>
      paymentProviders.filter(
        (provider) => getProviderPresentation(provider.id).kind === 'express',
      ),
    [paymentProviders],
  );
  const expressDisabled =
    submitting ||
    promotionSubmitting ||
    !contactCompleted ||
    !deliveryCompleted ||
    shippingAddressEdited ||
    shippingOptionsLoading ||
    (!shippingCompleted && !hasSingleShippingOption);
  const expressDisabledReason = !contactCompleted
    ? 'Save your contact email before using accelerated checkout.'
    : !deliveryCompleted || shippingAddressEdited
      ? 'Save your delivery details before using accelerated checkout.'
      : shippingOptionsLoading
        ? 'Loading shipping options for this address.'
        : !shippingCompleted && !hasSingleShippingOption
          ? shippingOptions.length > 1
            ? 'Choose a shipping method before using an accelerated wallet.'
            : sectionErrors.shipping ||
              'No shipping options are available for this address yet.'
          : 'Accelerated checkout will continue with the selected wallet provider.';
  const countryHint =
    activeCountries.length <= 1
      ? 'This checkout is tied to the current storefront country. To ship elsewhere, start a new checkout from that country storefront.'
      : 'Only countries already supported by this checkout region are available here.';

  useEffect(() => {
    if (!cart) return;
    const defaultShippingAddress =
      customer?.addresses?.find((address) => address.is_default_shipping) ||
      customer?.addresses?.[0] ||
      null;
    const defaultBillingAddress =
      customer?.addresses?.find((address) => address.is_default_billing) ||
      defaultShippingAddress;
    if (hydratedCartId !== cart.id) {
      const initialDeliveryVersion = isAddressReadyForRating(
        cart.shipping_address,
      )
        ? 1
        : 0;
      const initialShippingVersion =
        cart.shipping_methods?.[0]?.shipping_option_id && initialDeliveryVersion
          ? initialDeliveryVersion
          : 0;
      setEmail(cart.email || customer?.email || '');
      setShippingAddress(
        createCheckoutAddressState(
          cart.shipping_address || defaultShippingAddress,
          defaultCountryCode,
        ),
      );
      setBillingAddress(
        createCheckoutAddressState(
          cart.billing_address ||
            defaultBillingAddress ||
            cart.shipping_address ||
            defaultShippingAddress,
          defaultCountryCode,
        ),
      );
      setSelectedShippingOptionId(
        cart.shipping_methods?.[0]?.shipping_option_id || null,
      );
      setDeliveryVersion(initialDeliveryVersion);
      setShippingVersion(initialShippingVersion);
      setShippingAddressEdited(false);
      setBillingAddressEdited(false);
      setHydratedCartId(cart.id);
      setFieldErrors({});
      setSectionErrors({});
      setShippingOptionsLoaded(false);
      setPaymentProvidersLoaded(false);
      setPromotionCode('');
      setPromotionSubmitting(false);
      return;
    }

    if (customer?.email && !cart.email && !email.trim()) {
      setEmail(customer.email);
    }

    if (
      !cart.shipping_address &&
      defaultShippingAddress &&
      !shippingAddressEdited &&
      !isAddressReadyForRating(shippingAddress)
    ) {
      setShippingAddress(
        createCheckoutAddressState(defaultShippingAddress, defaultCountryCode),
      );
    }

    if (
      !cart.billing_address &&
      defaultBillingAddress &&
      !billingAddressEdited &&
      !isAddressReadyForRating(billingAddress)
    ) {
      setBillingAddress(
        createCheckoutAddressState(defaultBillingAddress, defaultCountryCode),
      );
    }
  }, [
    billingAddress,
    billingAddressEdited,
    cart,
    customer,
    defaultCountryCode,
    email,
    hydratedCartId,
    shippingAddress,
    shippingAddressEdited,
  ]);

  useEffect(() => {
    if (!cart?.shipping_methods?.[0]?.shipping_option_id) return;
    setSelectedShippingOptionId(cart.shipping_methods[0].shipping_option_id);
  }, [cart?.shipping_methods]);

  const updateSectionError = useCallback(
    (section: string, message?: string | null) => {
      setSectionErrors((current) => {
        const next = { ...current };
        if (!message) {
          delete next[section];
        } else {
          next[section] = message;
        }
        return next;
      });
    },
    [],
  );

  const updateShippingField = useCallback(
    (field: keyof CheckoutAddressFormState, value: string) => {
      setShippingAddressEdited(true);
      setShippingAddress((current) => ({
        ...current,
        [field]: field === 'country_code' ? value.toLowerCase() : value,
      }));
      setFieldErrors((current) => {
        const next = { ...current };
        delete next[`shipping_${field}`];
        return next;
      });
    },
    [],
  );

  const updateBillingField = useCallback(
    (field: keyof CheckoutAddressFormState, value: string) => {
      setBillingAddressEdited(true);
      setBillingAddress((current) => ({
        ...current,
        [field]: field === 'country_code' ? value.toLowerCase() : value,
      }));
      setFieldErrors((current) => {
        const next = { ...current };
        delete next[`billing_${field}`];
        return next;
      });
    },
    [],
  );

  const validateAddress = useCallback(
    (prefix: 'shipping' | 'billing', address: CheckoutAddressFormState) => {
      const nextErrors: CheckoutFieldErrors = {};
      if (!address.first_name.trim())
        nextErrors[`${prefix}_first_name`] = 'Enter a first name.';
      if (!address.last_name.trim())
        nextErrors[`${prefix}_last_name`] = 'Enter a last name.';
      if (!address.address_1.trim())
        nextErrors[`${prefix}_address_1`] = 'Enter a street address.';
      if (!address.city.trim()) nextErrors[`${prefix}_city`] = 'Enter a city.';
      if (!address.postal_code.trim())
        nextErrors[`${prefix}_postal_code`] = 'Enter a ZIP or postal code.';
      if (!address.country_code.trim()) {
        nextErrors[`${prefix}_country_code`] = 'Select a country / region.';
      } else if (
        activeCountries.length &&
        !activeCountries.some(
          (country) => country.iso_2 === address.country_code.toLowerCase(),
        )
      ) {
        nextErrors[`${prefix}_country_code`] =
          'This checkout cannot switch to a different region. Start a new checkout for that country.';
      }
      return nextErrors;
    },
    [activeCountries],
  );

  const loadShippingOptions = useCallback(async () => {
    setShippingOptionsLoading(true);
    setShippingOptionsLoaded(false);
    updateSectionError('shipping', null);
    try {
      const options = await getShippingOptions();
      setShippingOptions(options);
      if (!options.length) {
        updateSectionError(
          'shipping',
          'No shipping options are available for this address yet.',
        );
      }
      return options;
    } catch (err) {
      updateSectionError(
        'shipping',
        err instanceof Error ? err.message : 'Unable to load shipping options.',
      );
      return [];
    } finally {
      setShippingOptionsLoaded(true);
      setShippingOptionsLoading(false);
    }
  }, [getShippingOptions, updateSectionError]);

  const loadPaymentProviders = useCallback(async () => {
    setPaymentProvidersLoading(true);
    setPaymentProvidersLoaded(false);
    updateSectionError('payment', null);
    try {
      const providers = await getPaymentProviders();
      setPaymentProviders(providers);
      if (!providers.length) {
        updateSectionError(
          'payment',
          'No payment methods are available for this checkout yet.',
        );
      }
      return providers;
    } catch (err) {
      updateSectionError(
        'payment',
        err instanceof Error ? err.message : 'Unable to load payment methods.',
      );
      return [];
    } finally {
      setPaymentProvidersLoaded(true);
      setPaymentProvidersLoading(false);
    }
  }, [getPaymentProviders, updateSectionError]);

  useEffect(() => {
    if (
      !cart ||
      !deliveryCompleted ||
      shippingOptions.length ||
      shippingOptionsLoading ||
      shippingOptionsLoaded
    )
      return;
    void loadShippingOptions();
  }, [
    cart,
    deliveryCompleted,
    loadShippingOptions,
    shippingOptions.length,
    shippingOptionsLoaded,
    shippingOptionsLoading,
  ]);

  useEffect(() => {
    if (!shippingCompleted) {
      setPaymentCollection(null);
      setPaymentSessionLoading(false);
      updateSectionError('payment', null);
      return;
    }
    if (
      !cart ||
      paymentProviders.length ||
      paymentProvidersLoading ||
      paymentProvidersLoaded
    )
      return;
    void loadPaymentProviders();
  }, [
    cart,
    loadPaymentProviders,
    paymentProviders.length,
    paymentProvidersLoaded,
    paymentProvidersLoading,
    shippingCompleted,
    updateSectionError,
  ]);

  const saveContact = useCallback(async () => {
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setFieldErrors((current) => ({
        ...current,
        contact_email: 'Enter an email address.',
      }));
      return false;
    }
    if (!emailLooksValid(trimmedEmail)) {
      setFieldErrors((current) => ({
        ...current,
        contact_email: 'Enter a valid email address.',
      }));
      return false;
    }
    try {
      await performCheckoutAction('update_email', {
        step: 'update_email',
        email: trimmedEmail,
      });
      updateSectionError('contact', null);
      return true;
    } catch (err) {
      updateSectionError(
        'contact',
        err instanceof Error ? err.message : 'Unable to save your email.',
      );
      return false;
    }
  }, [email, performCheckoutAction, updateSectionError]);

  const saveDelivery = useCallback(async () => {
    const nextDeliveryVersion = deliveryVersion + 1;
    const trimmedEmail = email.trim();
    const nextFieldErrors: CheckoutFieldErrors = {
      ...validateAddress('shipping', shippingAddress),
    };
    if (!trimmedEmail) {
      nextFieldErrors.contact_email = 'Enter an email address.';
    } else if (!emailLooksValid(trimmedEmail)) {
      nextFieldErrors.contact_email = 'Enter a valid email address.';
    }
    if (Object.keys(nextFieldErrors).length) {
      setFieldErrors((current) => ({ ...current, ...nextFieldErrors }));
      return;
    }

    setSelectedShippingOptionId(null);
    setSelectedPaymentProviderId(null);
    setPaymentCollection(null);
    setPaymentRedirectUrl(null);
    setPaymentProviders([]);
    setShippingOptionsLoaded(false);
    setPaymentProvidersLoaded(false);
    setShippingVersion(0);
    try {
      await performCheckoutAction('update_email', {
        step: 'update_email',
        email: trimmedEmail,
      });
      await performCheckoutAction('update_shipping_address', {
        step: 'update_shipping_address',
        address: shippingAddress,
      });
      setShippingAddressEdited(false);
      setDeliveryVersion(nextDeliveryVersion);
      updateSectionError('delivery', null);
      await loadShippingOptions();
    } catch (err) {
      updateSectionError(
        'delivery',
        err instanceof Error
          ? err.message
          : 'Unable to save your delivery details.',
      );
    }
  }, [
    deliveryVersion,
    email,
    loadShippingOptions,
    performCheckoutAction,
    shippingAddress,
    updateSectionError,
    validateAddress,
  ]);

  const selectShippingOption = useCallback(
    async (optionId: string) => {
      setSelectedPaymentProviderId(null);
      setPaymentCollection(null);
      setPaymentRedirectUrl(null);
      setPaymentProviders([]);
      setPaymentProvidersLoaded(false);
      try {
        await performCheckoutAction('set_shipping_method', {
          step: 'set_shipping_method',
          optionId,
        });
        setSelectedShippingOptionId(optionId);
        setShippingVersion(deliveryVersion);
        updateSectionError('shipping', null);
        if (!paymentProviders.length && !paymentProvidersLoading) {
          await loadPaymentProviders();
        }
      } catch (err) {
        updateSectionError(
          'shipping',
          err instanceof Error
            ? err.message
            : 'Unable to save your shipping method.',
        );
      }
    },
    [
      deliveryVersion,
      loadPaymentProviders,
      paymentProviders.length,
      paymentProvidersLoading,
      performCheckoutAction,
      updateSectionError,
    ],
  );

  const initializePaymentProvider = useCallback(
    async (providerId: string) => {
      setSelectedPaymentProviderId(providerId);
      setPaymentCollection(null);
      setPaymentRedirectUrl(null);
      setPaymentSessionLoading(true);
      try {
        const nextPaymentCollection = await performCheckoutAction(
          'init_payment_session',
          {
            step: 'init_payment_session',
            providerId,
          },
        );
        const resolvedPaymentCollection =
          'payment_sessions' in nextPaymentCollection
            ? nextPaymentCollection
            : null;
        setPaymentCollection(resolvedPaymentCollection);
        const redirectUrl = resolvedPaymentCollection
          ? getPaymentRedirectUrl(resolvedPaymentCollection, providerId)
          : null;
        setPaymentRedirectUrl(redirectUrl);
        updateSectionError('payment', null);
        return resolvedPaymentCollection;
      } finally {
        setPaymentSessionLoading(false);
      }
    },
    [performCheckoutAction, updateSectionError],
  );

  const selectPaymentProvider = useCallback(
    async (providerId: string) => {
      try {
        await initializePaymentProvider(providerId);
      } catch (err) {
        setPaymentCollection(null);
        updateSectionError(
          'payment',
          err instanceof Error
            ? err.message
            : 'Unable to initialize the payment method.',
        );
      }
    },
    [initializePaymentProvider, updateSectionError],
  );

  useEffect(() => {
    if (
      !shippingCompleted ||
      selectedPaymentProviderId ||
      !paymentProviders.length
    ) {
      return;
    }
    const defaultProvider =
      paymentProviders.find((provider) => provider.is_default) || null;
    if (!defaultProvider) {
      return;
    }
    setSelectedPaymentProviderId(defaultProvider.id);
    setPaymentRedirectUrl(null);
    updateSectionError('payment', null);
  }, [
    paymentProviders,
    selectedPaymentProviderId,
    shippingCompleted,
    updateSectionError,
  ]);

  useEffect(() => {
    if (
      !shippingCompleted ||
      !selectedPaymentProviderId ||
      paymentCollection ||
      paymentSessionLoading
    ) {
      return;
    }
    void selectPaymentProvider(selectedPaymentProviderId);
  }, [
    paymentCollection,
    paymentSessionLoading,
    selectedPaymentProviderId,
    selectPaymentProvider,
    shippingCompleted,
  ]);

  const ensurePaymentProviderInitialized = useCallback(
    async (providerId: string) => {
      const existingSession = getPaymentSessionForProvider(
        paymentCollection,
        providerId,
      );
      if (existingSession && paymentCollection) {
        return paymentCollection;
      }
      return await initializePaymentProvider(providerId);
    },
    [initializePaymentProvider, paymentCollection],
  );

  const prepareBillingForPayment = useCallback(async () => {
    updateSectionError('payment', null);
    const nextFieldErrors = billingSameAsShipping
      ? {}
      : validateAddress('billing', billingAddress);
    if (Object.keys(nextFieldErrors).length) {
      setFieldErrors((current) => ({ ...current, ...nextFieldErrors }));
      return null;
    }

    const billingPayload = billingSameAsShipping
      ? shippingAddress
      : billingAddress;
    try {
      if (billingSameAsShipping) {
        setBillingAddressEdited(false);
      }
      await updateCartBillingAddress(billingPayload);
      return billingPayload;
    } catch (err) {
      updateSectionError(
        'payment',
        err instanceof Error
          ? err.message
          : 'Unable to save your billing details.',
      );
      return null;
    }
  }, [
    billingAddress,
    billingSameAsShipping,
    shippingAddress,
    updateCartBillingAddress,
    updateSectionError,
    validateAddress,
  ]);

  const completeConfirmedCheckout = useCallback(async () => {
    try {
      const result = await completeCheckout();
      if (result.type === 'order' && result.order) {
        navigateToOrderConfirmed(result.order.id);
        return true;
      }
      updateSectionError(
        'payment',
        'Checkout could not be completed. Please review your payment details and try again.',
      );
    } catch (err) {
      updateSectionError(
        'payment',
        err instanceof Error ? err.message : 'Unable to complete checkout.',
      );
    }
    return false;
  }, [completeCheckout, navigateToOrderConfirmed, updateSectionError]);

  const completeWithProvider = useCallback(
    async (providerId?: string) => {
      updateSectionError('payment', null);
      const resolvedProviderId = providerId || selectedPaymentProviderId;
      if (!resolvedProviderId) {
        updateSectionError(
          'payment',
          'Choose a payment method before completing checkout.',
        );
        return false;
      }
      if (isStripePaymentProvider(resolvedProviderId)) {
        updateSectionError(
          'payment',
          'Enter your card details in the Stripe form before completing checkout.',
        );
        return false;
      }

      const billingPayload = await prepareBillingForPayment();
      if (!billingPayload) {
        return false;
      }

      setSubmitting(true);
      try {
        const nextPaymentCollection =
          await ensurePaymentProviderInitialized(resolvedProviderId);
        const redirectUrl = nextPaymentCollection
          ? getPaymentRedirectUrl(nextPaymentCollection, resolvedProviderId)
          : null;
        if (redirectUrl) {
          window.location.assign(redirectUrl);
          return true;
        }
        const completed = await completeConfirmedCheckout();
        if (completed) {
          return true;
        }
      } catch (err) {
        updateSectionError(
          'payment',
          err instanceof Error ? err.message : 'Unable to complete checkout.',
        );
      } finally {
        setSubmitting(false);
      }
      return false;
    },
    [
      completeConfirmedCheckout,
      ensurePaymentProviderInitialized,
      prepareBillingForPayment,
      selectedPaymentProviderId,
      updateSectionError,
    ],
  );

  const handleApplyPromotion = useCallback(async () => {
    setPromotionSubmitting(true);
    updateSectionError('promotion', null);
    try {
      await applyPromotionCode(promotionCode);
      setPromotionCode('');
    } catch (err) {
      updateSectionError(
        'promotion',
        err instanceof Error
          ? err.message
          : 'Unable to apply the discount code.',
      );
    } finally {
      setPromotionSubmitting(false);
    }
  }, [applyPromotionCode, promotionCode, updateSectionError]);

  const handleRemovePromotion = useCallback(
    async (code: string) => {
      setPromotionSubmitting(true);
      updateSectionError('promotion', null);
      try {
        await removePromotionCode(code);
      } catch (err) {
        updateSectionError(
          'promotion',
          err instanceof Error
            ? err.message
            : 'Unable to remove the discount code.',
        );
      } finally {
        setPromotionSubmitting(false);
      }
    },
    [removePromotionCode, updateSectionError],
  );

  const handleExpressCheckout = useCallback(
    async (providerId: string) => {
      updateSectionError('payment', null);
      if (!contactCompleted) {
        updateSectionError(
          'payment',
          'Save your contact email before using accelerated checkout.',
        );
        return;
      }
      if (!deliveryCompleted || shippingAddressEdited) {
        updateSectionError(
          'payment',
          'Save your delivery details before using accelerated checkout.',
        );
        return;
      }
      if (!shippingCompleted) {
        if (shippingOptionsLoading) {
          updateSectionError(
            'payment',
            'Shipping options are still loading for this address.',
          );
          return;
        }
        if (shippingOptions.length !== 1) {
          updateSectionError(
            'payment',
            shippingOptions.length > 1
              ? 'Choose a shipping method before using an accelerated wallet.'
              : sectionErrors.shipping ||
                  'No shipping options are available for this address yet.',
          );
          return;
        }
        try {
          const singleOption = shippingOptions[0];
          await performCheckoutAction('set_shipping_method', {
            step: 'set_shipping_method',
            optionId: singleOption.id,
          });
          setSelectedShippingOptionId(singleOption.id);
          setShippingVersion(deliveryVersion);
          updateSectionError('shipping', null);
        } catch (err) {
          updateSectionError(
            'shipping',
            err instanceof Error
              ? err.message
              : 'Unable to save your shipping method.',
          );
          return;
        }
      }
      await completeWithProvider(providerId);
    },
    [
      completeWithProvider,
      contactCompleted,
      deliveryCompleted,
      deliveryVersion,
      performCheckoutAction,
      sectionErrors.shipping,
      shippingAddressEdited,
      shippingCompleted,
      shippingOptions,
      shippingOptionsLoading,
      updateSectionError,
    ],
  );

  const handleDeliveryBlur = useCallback(
    (event: React.FocusEvent<HTMLDivElement>) => {
      if (
        event.relatedTarget &&
        event.currentTarget.contains(event.relatedTarget as Node)
      )
        return;
      if (!shippingAddressEdited) return;
      const trimmedEmail = email.trim();
      if (!trimmedEmail || !emailLooksValid(trimmedEmail)) return;
      if (Object.keys(validateAddress('shipping', shippingAddress)).length)
        return;
      void saveDelivery();
    },
    [
      email,
      saveDelivery,
      shippingAddress,
      shippingAddressEdited,
      validateAddress,
    ],
  );

  const handleEmailBlur = useCallback(async () => {
    if (email.trim() && !contactCompleted) {
      const saved = await saveContact();
      if (!saved) return;
    }
    if (
      shippingAddressEdited &&
      emailLooksValid(email.trim()) &&
      !Object.keys(validateAddress('shipping', shippingAddress)).length
    ) {
      void saveDelivery();
    }
  }, [
    contactCompleted,
    email,
    saveContact,
    saveDelivery,
    shippingAddress,
    shippingAddressEdited,
    validateAddress,
  ]);

  if (cartLoading && !cart) {
    return (
      <div
        className="min-h-screen bg-surface-2 px-4 py-16 text-center text-sm text-content-muted"
        style={theme.pageStyle}
      >
        Loading checkout…
      </div>
    );
  }

  if (!cart || !cart.items?.length) {
    return (
      <div
        className="min-h-screen bg-surface-2 px-4 py-16 sm:px-6 lg:px-8"
        style={theme.pageStyle}
        data-testid="b2c-checkout-empty-state"
      >
        <div
          className="mx-auto max-w-xl rounded-lg border border-border bg-surface px-8 py-10 text-center"
          style={theme.surfaceStyle}
        >
          <p
            className="text-[11px] font-semibold uppercase tracking-[0.28em] text-content-muted"
            style={theme.mutedTextStyle}
          >
            Checkout
          </p>
          <h1
            className="mt-3 text-3xl font-semibold text-content"
            style={theme.headingStyle}
          >
            Your cart is empty
          </h1>
          <p
            className="mt-3 text-sm leading-6 text-content-muted"
            style={theme.mutedTextStyle}
          >
            Add something to your cart before continuing to checkout.
          </p>
          <button
            onClick={() => navigateToCart()}
            className="mt-6 rounded-md bg-content px-6 py-3 text-sm font-medium text-white transition hover:bg-content/80"
            style={{ ...theme.primaryPillStyle, borderRadius: '6px' }}
          >
            Back to cart
          </button>
        </div>
      </div>
    );
  }

  return (
    <CheckoutShell
      cartTotal={visibleOrderTotal}
      onBackToCart={navigateToCart}
      onToggleMobileSummary={() => setMobileSummaryOpen((current) => !current)}
    >
      <main className={`w-full lg:grid ${CHECKOUT_CENTER_TRACKS_CLASS}`}>
        <div className="hidden lg:block" />
        <div
          className={`grid w-full gap-0 ${CHECKOUT_DESKTOP_GRID_CLASS}`}
          data-testid="b2c-checkout-main-shell"
        >
          <div className="py-6 lg:py-8">
            <div
              className={`mx-auto w-full max-w-[640px] space-y-6 px-4 sm:px-8 ${CHECKOUT_FORM_MAX_WIDTH_CLASS} ${CHECKOUT_FORM_RAIL_POSITION_CLASS} lg:px-0`}
              data-testid="b2c-checkout-form-rail"
            >
              {mobileSummaryOpen ? (
                <CheckoutSummary
                  cart={cart}
                  currencyCode={currencyCode}
                  shippingCompleted={shippingCompleted}
                  promotionCode={promotionCode}
                  promotionSubmitting={promotionSubmitting}
                  promotionError={sectionErrors.promotion}
                  onPromotionCodeChange={setPromotionCode}
                  onApplyPromotion={() => void handleApplyPromotion()}
                  onRemovePromotion={(code) => void handleRemovePromotion(code)}
                  mobile
                />
              ) : null}

              <CheckoutExpressSection
                providers={expressProviders}
                disabled={expressDisabled}
                disabledReason={expressDisabledReason}
                activeProviderId={
                  expressProviders.some(
                    (provider) => provider.id === selectedPaymentProviderId,
                  )
                    ? selectedPaymentProviderId
                    : null
                }
                onSelect={(providerId) =>
                  void handleExpressCheckout(providerId)
                }
              />

              <CheckoutSection
                title="Contact"
                action={
                  !isAuthenticated ? (
                    <button
                      onClick={() => navigateToAccount()}
                      className="text-sm text-blue-600 underline underline-offset-2 transition hover:text-blue-800"
                    >
                      Sign in
                    </button>
                  ) : (
                    <span className="text-sm text-success">Signed in</span>
                  )
                }
                testId="b2c-checkout-contact"
              >
                <div className="space-y-3">
                  <div className="relative">
                    <input
                      id="checkout_email"
                      type="email"
                      value={email}
                      onChange={(event) => {
                        setEmail(event.target.value);
                        setFieldErrors((current) => {
                          const next = { ...current };
                          delete next.contact_email;
                          return next;
                        });
                      }}
                      onBlur={() => void handleEmailBlur()}
                      autoComplete="email"
                      placeholder="Email"
                      className="peer w-full rounded-md border border-border bg-surface px-3 pb-2 pt-5 text-sm text-content outline-none transition placeholder:text-transparent focus:border-content focus:ring-2 focus:ring-accent/30"
                      style={{
                        ...theme.inputStyle,
                        borderRadius: '6px',
                        boxShadow: 'none',
                      }}
                      required
                      aria-invalid={!!fieldErrors.contact_email || undefined}
                      aria-describedby={fieldErrors.contact_email ? 'checkout_email_error' : undefined}
                    />
                    <label htmlFor="checkout_email" className="pointer-events-none absolute left-3 top-1.5 origin-left text-[11px] text-content-muted transition-all peer-placeholder-shown:top-3.5 peer-placeholder-shown:text-sm peer-placeholder-shown:text-content-muted peer-focus:top-1.5 peer-focus:text-[11px] peer-focus:text-content-muted">
                      Email
                    </label>
                    <CheckoutFieldError id="checkout_email_error" message={fieldErrors.contact_email} />
                  </div>
                  {sectionErrors.contact ? (
                    <p className="text-sm font-medium text-danger">
                      {sectionErrors.contact}
                    </p>
                  ) : null}
                  <label className="flex items-center gap-2 text-sm text-content-muted">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-border text-content focus:ring-2 focus:ring-accent/30"
                    />
                    <span>Email me with news and offers</span>
                  </label>
                </div>
              </CheckoutSection>

              <CheckoutSection title="Delivery" testId="b2c-checkout-delivery">
                <div onBlur={handleDeliveryBlur}>
                  <CheckoutAddressFields
                    prefix="shipping"
                    address={shippingAddress}
                    errors={fieldErrors}
                    onChange={updateShippingField}
                    countries={activeCountries}
                    countryLocked={activeCountries.length <= 1}
                    countryHint={countryHint}
                  />
                </div>
                {sectionErrors.delivery ? (
                  <p className="mt-2 text-sm font-medium text-danger">
                    {sectionErrors.delivery}
                  </p>
                ) : null}
                <div className="mt-3 flex items-center gap-2 text-sm text-content-muted">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-border text-content focus:ring-2 focus:ring-accent/30"
                  />
                  <span>Save this information for next time</span>
                </div>
              </CheckoutSection>

              <CheckoutSection
                title="Shipping method"
                disabled={!deliveryCompleted}
                testId="b2c-checkout-shipping"
              >
                <div className="space-y-3">
                  {!deliveryCompleted ? (
                    <p className="rounded-md bg-surface-2 px-4 py-3 text-sm text-content-muted">
                      Enter your shipping address to view available shipping
                      methods.
                    </p>
                  ) : null}
                  {deliveryCompleted && shippingOptionsLoading ? (
                    <p className="text-sm text-content-muted">
                      Loading shipping options…
                    </p>
                  ) : null}
                  {sectionErrors.shipping ? (
                    <p className="text-sm font-medium text-danger">
                      {sectionErrors.shipping}
                    </p>
                  ) : null}
                  {deliveryCompleted &&
                  !shippingOptionsLoading &&
                  shippingOptions.length ? (
                    <fieldset
                      className="space-y-2 rounded-md border border-border"
                      data-testid="b2c-shipping-options"
                    >
                      <legend className="sr-only">Shipping method</legend>
                      {shippingOptions.map((option) => {
                        const isSelected =
                          visibleShippingOptionId === option.id;
                        return (
                          <label
                            key={option.id}
                            className={`flex cursor-pointer items-center justify-between gap-4 border-b border-border px-4 py-3 last:border-b-0 transition ${
                              isSelected
                                ? 'bg-surface-2'
                                : 'bg-surface hover:bg-surface-hover'
                            }`}
                          >
                            <div className="flex items-center gap-3">
                              <input
                                type="radio"
                                checked={isSelected}
                                onChange={() =>
                                  void selectShippingOption(option.id)
                                }
                                className="h-4 w-4 border-border text-content focus:ring-2 focus:ring-accent/30"
                              />
                              <p className="text-sm text-content">
                                {option.name}
                              </p>
                            </div>
                            <p className="text-sm font-semibold text-content">
                              {formatPrice(
                                option.amount || 0,
                                option.currency_code || currencyCode,
                              )}
                            </p>
                          </label>
                        );
                      })}
                    </fieldset>
                  ) : null}
                </div>
              </CheckoutSection>

              <CheckoutSection
                title="Payment"
                disabled={!shippingCompleted}
                testId="b2c-checkout-payment"
              >
                <p className="mb-3 text-sm text-content-muted">
                  All transactions are secure and encrypted.
                </p>
                <div className="space-y-3">
                  {!shippingCompleted ? (
                    <p className="text-sm text-content-muted">
                      Choose a shipping method before selecting a payment
                      option.
                    </p>
                  ) : null}
                  {shippingCompleted && paymentProvidersLoading ? (
                    <p className="text-sm text-content-muted">
                      Loading payment methods…
                    </p>
                  ) : null}
                  {sectionErrors.payment ? (
                    <p className="text-sm font-medium text-danger">
                      {sectionErrors.payment}
                    </p>
                  ) : null}
                  {shippingCompleted && paymentProviders.length ? (
                    <fieldset
                      className="rounded-md border border-border"
                      data-testid="b2c-payment-providers"
                    >
                      <legend className="sr-only">Payment method</legend>
                      {paymentProviders.map((provider) => {
                        const isSelected =
                          selectedPaymentProviderId === provider.id;
                        const presentation = getProviderPresentation(
                          provider.id,
                        );
                        return (
                          <label
                            key={provider.id}
                            className={`block cursor-pointer border-b border-border px-4 py-3 last:border-b-0 transition ${
                              isSelected
                                ? 'bg-surface-2'
                                : 'bg-surface hover:bg-surface-hover'
                            }`}
                          >
                            <div className="flex items-center justify-between gap-4">
                              <div className="flex items-center gap-3">
                                <input
                                  type="radio"
                                  checked={isSelected}
                                  onChange={() =>
                                    void selectPaymentProvider(provider.id)
                                  }
                                  className="h-4 w-4 border-border text-content focus:ring-2 focus:ring-accent/30"
                                />
                                <div className="flex items-center gap-2">
                                  <p className="text-sm text-content">
                                    {presentation.label}
                                  </p>
                                  {provider.is_default ? (
                                    <span className="rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-content-muted">
                                      Default
                                    </span>
                                  ) : null}
                                </div>
                              </div>
                            </div>
                          </label>
                        );
                      })}
                    </fieldset>
                  ) : null}
                </div>
                <div className="mt-4 space-y-4">
                  <label className="flex items-center gap-2 text-sm text-content-muted">
                    <input
                      type="checkbox"
                      checked={billingSameAsShipping}
                      onChange={(event) =>
                        setBillingSameAsShipping(event.target.checked)
                      }
                      className="h-4 w-4 rounded border-border text-content focus:ring-2 focus:ring-accent/30"
                    />
                    <span>Use shipping address as billing address</span>
                  </label>
                  {!billingSameAsShipping ? (
                    <div>
                      <h3
                        className="mb-2 text-sm font-bold text-content"
                        style={theme.headingStyle}
                      >
                        Billing address
                      </h3>
                      <CheckoutAddressFields
                        prefix="billing"
                        address={billingAddress}
                        errors={fieldErrors}
                        onChange={updateBillingField}
                        countries={activeCountries}
                        countryLocked={activeCountries.length <= 1}
                        countryHint={countryHint}
                      />
                    </div>
                  ) : null}
                  {stripeSelected ? (
                    !stripePublishableKey ? (
                      <p className="text-sm font-medium text-danger">
                        Stripe publishable key is not configured for this
                        frontend. Set `VITE_STRIPE_PUBLISHABLE_KEY` to render
                        card fields.
                      </p>
                    ) : paymentSessionLoading ? (
                      <p className="text-sm text-content-muted">
                        Initializing secure card form…
                      </p>
                    ) : !stripeClientSecret || !stripeElementsOptions ? (
                      <p className="text-sm font-medium text-danger">
                        Stripe payment session is missing a client secret. The
                        Medusa Stripe provider did not initialize correctly.
                      </p>
                    ) : !stripePromise ? (
                      <p className="text-sm font-medium text-danger">
                        Stripe could not be initialized for this checkout.
                      </p>
                    ) : (
                      <Elements
                        options={stripeElementsOptions}
                        stripe={stripePromise}
                      >
                        <CheckoutStripeCardForm
                          cart={cart}
                          clientSecret={stripeClientSecret}
                          submitting={submitting}
                          setSubmitting={setSubmitting}
                          prepareBillingForPayment={prepareBillingForPayment}
                          completeConfirmedCheckout={completeConfirmedCheckout}
                          updatePaymentError={(message) =>
                            updateSectionError('payment', message)
                          }
                          buttonStyle={theme.primaryPillStyle}
                        />
                      </Elements>
                    )
                  ) : (
                    <button
                      type="button"
                      onClick={() => void completeWithProvider()}
                      disabled={
                        submitting ||
                        !selectedPaymentProviderId ||
                        !shippingCompleted
                      }
                      className="w-full rounded-md bg-content px-6 py-3 text-sm font-medium text-white transition hover:bg-content/80 disabled:cursor-not-allowed disabled:opacity-50"
                      style={{ ...theme.primaryPillStyle, borderRadius: '6px' }}
                      data-testid="b2c-complete-checkout"
                    >
                      {submitting
                        ? 'Processing…'
                        : paymentRedirectUrl
                          ? 'Continue to payment'
                          : 'Pay now'}
                    </button>
                  )}
                </div>
              </CheckoutSection>

              <CheckoutFooterLinks />
            </div>
          </div>

          <div className="hidden border-l border-border bg-surface-2 px-6 py-8 lg:flex lg:justify-start xl:px-10">
            <CheckoutSummary
              cart={cart}
              currencyCode={currencyCode}
              shippingCompleted={shippingCompleted}
              promotionCode={promotionCode}
              promotionSubmitting={promotionSubmitting}
              promotionError={sectionErrors.promotion}
              onPromotionCodeChange={setPromotionCode}
              onApplyPromotion={() => void handleApplyPromotion()}
              onRemovePromotion={(code) => void handleRemovePromotion(code)}
            />
          </div>
        </div>
        <div className="hidden bg-surface-2 lg:block" />
      </main>
    </CheckoutShell>
  );
}

// =============================================================================
// Order Confirmed Page
// =============================================================================

export function MedusaB2COrderConfirmedPage() {
  const { getOrder, navigateToStore } = useB2CRuntime();
  const theme = useB2CPageTheme();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  // Resolve order ID from URL path or query params
  const pathParts = location.pathname.split('/').filter(Boolean);
  const orderId =
    searchParams.get('order_id') ||
    searchParams.get('orderId') ||
    pathParts[pathParts.length - 1] ||
    '';

  const [order, setOrder] = useState<MedusaOrder | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!orderId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const loadOrder = async () => {
      try {
        const orderData = await getOrder(orderId);
        if (!cancelled) setOrder(orderData);
      } catch {
        // Order may not be accessible — show generic confirmation
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void loadOrder();
    return () => {
      cancelled = true;
    };
  }, [getOrder, orderId]);

  return (
    <B2CStarterShell>
      <main
        className="mx-auto flex w-full max-w-4xl flex-col gap-10 px-4 py-14 sm:px-6 lg:px-8"
        style={theme.pageStyle}
      >
        {/* Thank-you header */}
        <div className="text-center">
          <div
            className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full"
            style={{
              backgroundColor: theme.tokens.colorPrimary || '#111827',
            }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke={theme.tokens.colorPrimaryText || '#ffffff'}
              className="h-8 w-8"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="m4.5 12.75 6 6 9-13.5"
              />
            </svg>
          </div>
          <h1
            className="text-3xl font-medium sm:text-4xl"
            style={theme.headingStyle}
          >
            Thank you!
          </h1>
          <p className="mt-3 text-base" style={theme.mutedTextStyle}>
            {order
              ? `Your order #${order.display_id || orderId.slice(-8)} was placed successfully.`
              : 'Your order was placed successfully.'}
          </p>
          <p className="mt-1 text-sm" style={theme.mutedTextStyle}>
            You will receive a confirmation email with your order details.
          </p>
        </div>

        {loading ? (
          <div className="animate-pulse space-y-4">
            <div
              className="h-32 w-full rounded-xl"
              style={theme.surfaceStyle}
            />
            <div
              className="h-40 w-full rounded-xl"
              style={theme.surfaceStyle}
            />
          </div>
        ) : order ? (
          <div className="space-y-6">
            {/* Order items */}
            {order.items && order.items.length > 0 ? (
              <div
                className="rounded-xl border border-border p-6"
                style={theme.surfaceStyle}
              >
                <h2
                  className="mb-4 font-medium"
                  style={theme.headingStyle}
                >
                  Order items
                </h2>
                <div className="space-y-4">
                  {order.items.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-center justify-between gap-4"
                    >
                      <div className="flex items-center gap-4">
                        {item.thumbnail ? (
                          <img
                            src={item.thumbnail}
                            alt={item.title}
                            className="h-16 w-16 rounded-lg object-cover"
                          />
                        ) : (
                          <div
                            className="flex h-16 w-16 items-center justify-center rounded-lg border border-dashed"
                            style={theme.borderStyle}
                          >
                            <span
                              className="text-[10px]"
                              style={theme.mutedTextStyle}
                            >
                              No image
                            </span>
                          </div>
                        )}
                        <div>
                          <p className="font-medium" style={theme.headingStyle}>
                            {item.title}
                          </p>
                          {item.variant_title ? (
                            <p
                              className="text-sm"
                              style={theme.mutedTextStyle}
                            >
                              {item.variant_title}
                            </p>
                          ) : null}
                          <p className="text-sm" style={theme.mutedTextStyle}>
                            Qty: {item.quantity}
                          </p>
                        </div>
                      </div>
                      <p className="font-medium" style={theme.headingStyle}>
                        {formatPrice(item.total, order.currency_code)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Order summary + shipping address side by side on desktop */}
            <div className="grid gap-6 lg:grid-cols-2">
              <div
                className="rounded-xl border border-border p-6"
                style={theme.surfaceStyle}
              >
                <h2
                  className="mb-4 font-medium"
                  style={theme.headingStyle}
                >
                  Order summary
                </h2>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span style={theme.mutedTextStyle}>Subtotal</span>
                    <span style={theme.textStyle}>
                      {formatPrice(order.subtotal, order.currency_code)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span style={theme.mutedTextStyle}>Shipping</span>
                    <span style={theme.textStyle}>
                      {formatPrice(
                        order.shipping_total,
                        order.currency_code,
                      )}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span style={theme.mutedTextStyle}>Tax</span>
                    <span style={theme.textStyle}>
                      {formatPrice(order.tax_total, order.currency_code)}
                    </span>
                  </div>
                  <div
                    className="flex justify-between border-t pt-2"
                    style={theme.borderStyle}
                  >
                    <span className="font-medium" style={theme.headingStyle}>
                      Total
                    </span>
                    <span className="font-medium" style={theme.headingStyle}>
                      {formatPrice(order.total, order.currency_code)}
                    </span>
                  </div>
                </div>
              </div>

              {order.shipping_address ? (
                <div
                  className="rounded-xl border border-border p-6"
                  style={theme.surfaceStyle}
                >
                  <h2
                    className="mb-4 font-medium"
                    style={theme.headingStyle}
                  >
                    Shipping address
                  </h2>
                  <div className="space-y-1 text-sm" style={theme.mutedTextStyle}>
                    <p>
                      {[
                        order.shipping_address.first_name,
                        order.shipping_address.last_name,
                      ]
                        .filter(Boolean)
                        .join(' ')}
                    </p>
                    <p>{order.shipping_address.address_1}</p>
                    {order.shipping_address.address_2 ? (
                      <p>{order.shipping_address.address_2}</p>
                    ) : null}
                    <p>
                      {[
                        order.shipping_address.city,
                        order.shipping_address.province,
                        order.shipping_address.postal_code,
                      ]
                        .filter(Boolean)
                        .join(', ')}
                    </p>
                    <p>
                      {order.shipping_address.country_code?.toUpperCase()}
                    </p>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {/* Continue shopping CTA */}
        <div className="text-center">
          <button
            type="button"
            onClick={navigateToStore}
            className="rounded-full px-6 py-3 text-sm font-medium"
            style={theme.primaryPillStyle}
          >
            Continue shopping
          </button>
        </div>
      </main>
    </B2CStarterShell>
  );
}

// =============================================================================
// Order Transfer Pages
// =============================================================================

export function MedusaB2COrderTransferPage() {
  const { navigateToHome } = useB2CRuntime();
  const location = useLocation();
  const pathParts = location.pathname.split('/');
  const orderId = pathParts[pathParts.length - 3] || '';
  const token = pathParts[pathParts.length - 1] || '';
  const acceptPath = `${location.pathname}/accept`;
  const declinePath = `${location.pathname}/decline`;

  return (
    <PageShell
      title="Order transfer"
      description={`Review the transfer request for order ${orderId}.`}
    >
      <div className="max-w-2xl space-y-4 rounded-xl border border-border p-6">
        <p className="text-sm text-content-muted">
          You&apos;ve received a request to transfer ownership of order{' '}
          <strong>{orderId}</strong>. If you accept, the new owner will take
          over future access to this order.
        </p>
        <p className="text-sm text-content-muted">Transfer token: {token}</p>
        <div className="flex gap-3">
          <a
            href={acceptPath}
            className="rounded-lg bg-content px-4 py-2 text-sm font-medium text-white hover:bg-content/80"
          >
            Accept transfer
          </a>
          <a
            href={declinePath}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-content-muted hover:bg-surface-hover"
          >
            Decline transfer
          </a>
          <button
            onClick={() => navigateToHome()}
            className="rounded-lg px-4 py-2 text-sm font-medium text-content-muted hover:bg-surface-hover"
          >
            Cancel
          </button>
        </div>
      </div>
    </PageShell>
  );
}

export function MedusaB2COrderTransferAcceptPage() {
  const { acceptOrderTransfer } = useB2CRuntime();
  const location = useLocation();
  const pathParts = location.pathname.split('/');
  const orderId = pathParts[pathParts.length - 4] || '';
  const token = pathParts[pathParts.length - 2] || '';
  const [status, setStatus] = useState<
    'idle' | 'loading' | 'success' | 'error'
  >('idle');
  const [error, setError] = useState<string | null>(null);

  const handleAccept = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      await acceptOrderTransfer(orderId, token);
      setStatus('success');
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to accept transfer',
      );
      setStatus('error');
    }
  }, [acceptOrderTransfer, orderId, token]);

  return (
    <PageShell
      title="Accept order transfer"
      description="Confirm the transfer token to accept an order transfer in Medusa."
    >
      <div className="max-w-md space-y-6">
        {status === 'success' ? (
          <div className="rounded-xl bg-success/10 p-6 text-center">
            <p className="font-medium text-success">
              Transfer accepted successfully!
            </p>
            <p className="mt-2 text-sm text-success">
              The order has been transferred to your account.
            </p>
          </div>
        ) : (
          <>
            <p className="text-sm text-content-muted">
              You are about to accept the transfer of order{' '}
              <strong>#{orderId.slice(-8)}</strong> to your account.
            </p>
            {error ? <p className="text-sm text-danger">{error}</p> : null}
            <div className="flex gap-3">
              <button
                onClick={handleAccept}
                disabled={status === 'loading'}
                className="rounded-lg bg-content px-4 py-2 text-sm font-medium text-white hover:bg-content/80 disabled:opacity-50"
              >
                {status === 'loading' ? 'Accepting...' : 'Accept transfer'}
              </button>
            </div>
          </>
        )}
      </div>
    </PageShell>
  );
}

export function MedusaB2COrderTransferDeclinePage() {
  const { declineOrderTransfer } = useB2CRuntime();
  const location = useLocation();
  const pathParts = location.pathname.split('/');
  const orderId = pathParts[pathParts.length - 4] || '';
  const token = pathParts[pathParts.length - 2] || '';
  const [status, setStatus] = useState<
    'idle' | 'loading' | 'success' | 'error'
  >('idle');
  const [error, setError] = useState<string | null>(null);

  const handleDecline = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      await declineOrderTransfer(orderId, token);
      setStatus('success');
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to decline transfer',
      );
      setStatus('error');
    }
  }, [declineOrderTransfer, orderId, token]);

  return (
    <PageShell
      title="Decline order transfer"
      description="Confirm the transfer token to decline an order transfer in Medusa."
    >
      <div className="max-w-md space-y-6">
        {status === 'success' ? (
          <div className="rounded-xl bg-surface-2 p-6 text-center">
            <p className="font-medium text-content">Transfer declined</p>
            <p className="mt-2 text-sm text-content-muted">
              The order transfer has been declined.
            </p>
          </div>
        ) : (
          <>
            <p className="text-sm text-content-muted">
              You are about to decline the transfer of order{' '}
              <strong>#{orderId.slice(-8)}</strong>.
            </p>
            {error ? <p className="text-sm text-danger">{error}</p> : null}
            <div className="flex gap-3">
              <button
                onClick={handleDecline}
                disabled={status === 'loading'}
                className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-content-muted hover:bg-surface-hover disabled:opacity-50"
              >
                {status === 'loading' ? 'Declining...' : 'Decline transfer'}
              </button>
            </div>
          </>
        )}
      </div>
    </PageShell>
  );
}
